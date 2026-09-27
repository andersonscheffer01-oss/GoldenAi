"""Integration layer: feature flag, RMS fallback, and VoiceService bridge.

This module wires the realtime voice adapter components into the existing
Golden AI pipeline WITHOUT replacing any current functionality.

Usage:
    JARVIS_REALTIME_VOICE_V2=1  → enables the new pipeline
    JARVIS_REALTIME_VOICE_V2=0  → current pipeline (default)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Optional

from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue, UtteranceBuffer
from jarvis_core.realtime_voice.barge_in import BargeInController
from jarvis_core.realtime_voice.constants import (
    AUDIO_QUEUE_MAXSIZE,
    FRAME_BYTES,
    HYBRID_HANGOVER_MS_DEFAULT,
    HYBRID_RMS_THRESHOLD_DEFAULT,
    LISTENING_TIMEOUT_DEFAULT,
    MIN_UTTERANCE_MS,
    POST_WAKE_BLACKOUT_MS,
    SAMPLE_RATE,
)
from jarvis_core.realtime_voice.hybrid_endpoint import (
    HybridEndpoint,
    HybridEvent,
    rms_energy as hybrid_rms_energy,
)
from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    VoiceStateMachine,
)
from jarvis_core.realtime_voice.vad import SileroVADAdapter, VADEvent
from jarvis_core.realtime_voice import is_hybrid_enabled

log = logging.getLogger(__name__)

# RMS-based fallback (from current voice.py)
_RMS_BLOCK_SIZE = 1024


def rms_energy(frame_bytes: bytes) -> float:
    """Compute mean absolute amplitude (RMS proxy) from int16 PCM bytes."""
    import numpy as np
    samples = np.frombuffer(frame_bytes, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.abs(samples).mean())


class RealtimeVoicePipeline:
    """Optional realtime voice pipeline behind feature flag.

    Wraps VAD adapter, audio queue, barge-in, and state machine into a
    single async pipeline that can be toggled against the current pipeline.
    """

    def __init__(self, state_machine: Optional[VoiceStateMachine] = None) -> None:
        # VoiceService may inject its canonical machine. Standalone tests keep
        # the historical local machine for adapter-only use.
        self._sm = state_machine or VoiceStateMachine()
        self._vad = SileroVADAdapter()
        self._queue = AudioFrameQueue(maxsize=AUDIO_QUEUE_MAXSIZE)
        self._utterance = UtteranceBuffer()
        self._barge_in = BargeInController(self._sm)
        self._hybrid = HybridEndpoint(
            hangover_ms=HYBRID_HANGOVER_MS_DEFAULT,
            rms_threshold=HYBRID_RMS_THRESHOLD_DEFAULT,
        )

        self._frame_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listening_timeout = LISTENING_TIMEOUT_DEFAULT
        self._on_transcription: Optional[Callable[[str], None]] = None
        self._on_state_change: Optional[Callable[[str], None]] = None
        self._stats: dict[str, Any] = {}

        # Metrics
        self._speech_started_at: float = 0.0
        self._last_endpoint_at: float = 0.0

    @property
    def state_machine(self) -> VoiceStateMachine:
        return self._sm

    @property
    def barge_in(self) -> BargeInController:
        return self._barge_in

    @property
    def queue(self) -> AudioFrameQueue:
        return self._queue

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    async def load(self) -> None:
        """Load VAD model."""
        await self._vad.load()
        log.info("[rvpipe] loaded, VAD model: %s", self._vad.model_path)

    async def unload(self) -> None:
        await self.stop()
        await self._vad.unload()

    async def start(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        on_transcription: Optional[Callable[[str], None]] = None,
        on_state_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Start the frame processing loop."""
        self._loop = loop or asyncio.get_event_loop()
        self._on_transcription = on_transcription
        self._on_state_change = on_state_change

        self._queue.uncancel()
        self._vad.reset()
        self._hybrid.reset()
        self._utterance.clear()
        self._stats.clear()
        if self._sm.state is not ConversationalState.LISTENING:
            self._sm.force_idle()

        self._frame_task = asyncio.ensure_future(self._frame_loop())
        log.info("[rvpipe] started")

    async def stop(self) -> None:
        """Stop the frame processing loop."""
        if self._frame_task is not None and not self._frame_task.done():
            self._frame_task.cancel()
            try:
                await self._frame_task
            except asyncio.CancelledError:
                pass
            self._frame_task = None
        self._queue.cancel()
        self._vad.reset()
        self._hybrid.reset()
        self._utterance.clear()
        self._sm.force_idle()
        log.info("[rvpipe] stopped")

    def feed_frame(self, frame: bytes) -> None:
        """Feed a raw audio frame from the mic thread (thread-safe)."""
        self._queue.put_nowait(frame)

    def _emit_state(self, state: ConversationalState) -> None:
        if self._on_state_change is not None:
            try:
                self._on_state_change(state.value)
            except Exception:
                log.exception("on_state_change raised")

    async def _frame_loop(self) -> None:
        """Central routing loop: reads frames, routes to VAD/utterance buffer."""
        blackout_frames = POST_WAKE_BLACKOUT_MS // 30  # approx
        blackout_remaining = 0
        listening_start: float = 0.0

        while True:
            try:
                frame = await self._queue.get()
            except asyncio.CancelledError:
                break

            if frame is None:
                break  # cancelled sentinel
            if frame == b"":
                continue  # timeout, check again

            # Blackout: discard frames after wake word detection
            if blackout_remaining > 0:
                blackout_remaining -= 1
                continue

            state = self._sm.state

            # IDLE: only feed VAD (for potential future wake word)
            if state == ConversationalState.IDLE:
                # Could add wake word detection here
                continue

            # LISTENING: feed VAD + accumulate utterance
            if state == ConversationalState.LISTENING:
                # Check listening timeout
                if listening_start > 0:
                    elapsed = time.monotonic() - listening_start
                    if elapsed > self._listening_timeout:
                        log.debug("listening timeout after %.1fs", elapsed)
                        self._utterance.end()
                        await self._finish_utterance()
                        self._hybrid.reset()
                        self._sm.transition(ConversationalState.IDLE)
                        self._emit_state(ConversationalState.IDLE)
                        listening_start = 0
                        continue

                # Feed VAD
                event = await self._vad.feed(frame)

                if event == VADEvent.SPEECH_STARTED:
                    self._utterance.start()
                    self._speech_started_at = time.monotonic()
                    if listening_start == 0:
                        listening_start = time.monotonic()
                    if is_hybrid_enabled():
                        self._hybrid.on_speech_started()
                    log.debug("speech started")
                elif event == VADEvent.ENDPOINT:
                    if is_hybrid_enabled():
                        hybrid_evt = self._hybrid.on_endpoint_candidate(frame)
                        if hybrid_evt == HybridEvent.ENDPOINT:
                            self._utterance.end()
                            self._last_endpoint_at = time.monotonic()
                            await self._finish_utterance()
                            self._sm.transition(ConversationalState.THINKING)
                            self._emit_state(ConversationalState.THINKING)
                            listening_start = 0
                            continue
                        # else: hangover opened, don't finalize yet
                    else:
                        self._utterance.end()
                        self._last_endpoint_at = time.monotonic()
                        await self._finish_utterance()
                        self._sm.transition(ConversationalState.THINKING)
                        self._emit_state(ConversationalState.THINKING)
                        listening_start = 0
                        continue

                # Accumulate audio
                if self._utterance.active:
                    self._utterance.append(frame)

                # Hybrid hangover processing
                if is_hybrid_enabled() and self._hybrid.in_hangover:
                    energy = hybrid_rms_energy(frame)
                    hybrid_evt = self._hybrid.feed_hangover(frame, energy)
                    if hybrid_evt == HybridEvent.ENDPOINT:
                        self._utterance.end()
                        self._last_endpoint_at = time.monotonic()
                        await self._finish_utterance()
                        self._sm.transition(ConversationalState.THINKING)
                        self._emit_state(ConversationalState.THINKING)
                        listening_start = 0
                    elif hybrid_evt == HybridEvent.SPEECH_RESUMED:
                        log.debug("hybrid: speech resumed after hangover cancel")

            # THINKING: keep VAD warm but don't act
            elif state == ConversationalState.THINKING:
                await self._vad.feed(frame)

            # SPEAKING: check for barge-in
            elif state == ConversationalState.SPEAKING:
                event = await self._vad.feed(frame)
                if event == VADEvent.SPEECH_STARTED:
                    if self._barge_in.check_barge_in():
                        log.info("barge-in detected")
                        self._vad.reset()
                        self._utterance.clear()
                        self._hybrid.reset()
                        self._sm.transition(ConversationalState.INTERRUPTED)
                        self._emit_state(ConversationalState.INTERRUPTED)
                        # Transition to LISTENING
                        self._sm.transition(ConversationalState.LISTENING)
                        self._emit_state(ConversationalState.LISTENING)
                        listening_start = time.monotonic()
                        continue

            # INTERRUPTED: wait for re-listen or IDLE
            elif state == ConversationalState.INTERRUPTED:
                pass

    async def _finish_utterance(self) -> None:
        """Process completed utterance: check minimum duration, extract text."""
        if self._utterance.sample_count == 0:
            self._utterance.clear()
            return

        duration_ms = self._utterance.duration_ms
        if duration_ms < MIN_UTTERANCE_MS:
            log.debug("utterance too short (%dms < %dms)", duration_ms, MIN_UTTERANCE_MS)
            self._utterance.clear()
            return

        audio_bytes = self._utterance.get_audio_bytes()
        self._utterance.clear()

        self._stats["last_utterance_ms"] = duration_ms
        self._stats["last_utterance_samples"] = len(audio_bytes) // 2

        if self._on_transcription is not None:
            try:
                self._on_transcription(audio_bytes.hex())
            except Exception:
                log.exception("on_transcription raised")

    def get_vad_rms_fallback(self, frame: bytes) -> Optional[VADEvent]:
        """RMS-based fallback when Silero is unavailable.

        Compatible with the current voice.py detection logic.
        """
        energy = rms_energy(frame)
        threshold = 500  # matches current SILENCE_THRESHOLD
        if energy >= threshold:
            if not self._utterance.active:
                self._utterance.start()
                return VADEvent.SPEECH_STARTED
            return None
        else:
            if self._utterance.active:
                # Simple silence detection for fallback
                self._utterance.end()
                return VADEvent.ENDPOINT
            return None
