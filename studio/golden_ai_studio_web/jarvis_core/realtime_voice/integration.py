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
import uuid
from typing import Any, Callable, Optional

from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue, UtteranceBuffer
from jarvis_core.realtime_voice.barge_in import BargeInController
from jarvis_core.realtime_voice.barge_in import SelfTriggerPolicy
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
from jarvis_core.voice_foundation import (
    SpeechToTextProvider,
    TranscriptAcceptanceGate,
    TranscriptEvent,
    VoiceCancellation,
    VoiceCancelledError,
)

from .conversation_coordinator import (
    ConversationCompletion,
    ConversationResultStatus,
    ConversationStreamCoordinator,
)

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

    def __init__(
        self,
        state_machine: Optional[VoiceStateMachine] = None,
        self_trigger_policy: Optional[SelfTriggerPolicy] = None,
    ) -> None:
        # VoiceService may inject its canonical machine. Standalone tests keep
        # the historical local machine for adapter-only use.
        self._sm = state_machine or VoiceStateMachine()
        self._vad = SileroVADAdapter()
        self._queue = AudioFrameQueue(maxsize=AUDIO_QUEUE_MAXSIZE)
        self._utterance = UtteranceBuffer()
        self._barge_in = BargeInController(
            self._sm, self_trigger_policy=self_trigger_policy
        )
        self._hybrid = HybridEndpoint(
            hangover_ms=HYBRID_HANGOVER_MS_DEFAULT,
            rms_threshold=HYBRID_RMS_THRESHOLD_DEFAULT,
        )

        self._frame_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listening_timeout = LISTENING_TIMEOUT_DEFAULT
        self._on_transcription: Optional[Callable[[Any], None]] = None
        self._on_state_change: Optional[Callable[[str], None]] = None
        self._stats: dict[str, Any] = {}
        self._stt_provider: Optional[SpeechToTextProvider] = None
        self._stt_cancellation = VoiceCancellation()
        self._session_id = ""
        self._turn_id = 0
        self._transcript_gate = TranscriptAcceptanceGate()
        self._conversation_coordinator = ConversationStreamCoordinator()

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

    @property
    def stt_provider(self) -> Optional[SpeechToTextProvider]:
        return self._stt_provider

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def turn_id(self) -> int:
        return self._turn_id

    @property
    def conversation_coordinator(self) -> ConversationStreamCoordinator:
        return self._conversation_coordinator

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
        on_transcription: Optional[Callable[[Any], None]] = None,
        on_state_change: Optional[Callable[[str], None]] = None,
        stt_provider: Optional[SpeechToTextProvider] = None,
        session_id: str = "",
        cancellation: Optional[VoiceCancellation] = None,
        turn_id: int = 0,
    ) -> None:
        """Start the frame processing loop."""
        self._loop = loop or asyncio.get_event_loop()
        self._on_transcription = on_transcription
        self._on_state_change = on_state_change
        self._stt_provider = stt_provider
        self._stt_cancellation = cancellation or VoiceCancellation()
        self._session_id = str(session_id or uuid.uuid4().hex)
        self._transcript_gate.begin(self._session_id)
        self._turn_id = int(turn_id)
        self._conversation_coordinator.begin_session(
            session_id=self._session_id,
            turn_id=self._turn_id,
            epoch=self._transcript_gate.epoch,
        )

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
        self._stt_cancellation.cancel("pipeline_stopped")
        self._transcript_gate.cancel()
        self._conversation_coordinator.cancel("pipeline_stopped")
        self._vad.reset()
        self._hybrid.reset()
        self._utterance.clear()
        self._sm.force_idle()
        log.info("[rvpipe] stopped")

    def cancel_transcription(self, reason: str = "transcription_cancelled") -> None:
        """Invalidate current STT results; worker cancellation remains cooperative."""
        self._stt_cancellation.cancel(reason)
        self._transcript_gate.cancel()
        self._conversation_coordinator.cancel(reason)

    def replace_turn(self, turn_id: int) -> None:
        """Invalidate the old turn and keep the same realtime pipeline owner."""
        self._stt_cancellation.cancel("turn_replaced")
        self._stt_cancellation = VoiceCancellation()
        self._transcript_gate.begin(self._session_id)
        self._turn_id = int(turn_id)
        self._conversation_coordinator.replace_turn(
            turn_id=self._turn_id,
            epoch=self._transcript_gate.epoch,
        )

    def feed_frame(self, frame: bytes) -> None:
        """Feed a raw audio frame from the mic thread (thread-safe)."""
        self._queue.put_nowait(frame)

    def _emit_state(self, state: ConversationalState) -> None:
        if self._on_state_change is not None:
            try:
                self._on_state_change(state.value)
            except Exception:
                log.exception("on_state_change raised")

    async def _feed_vad_safely(self, frame: bytes) -> Optional[VADEvent]:
        """Keep one bad VAD frame/model call from killing the voice loop."""
        try:
            return await self._vad.feed(frame)
        except Exception as exc:
            self._stats["vad_errors"] = int(self._stats.get("vad_errors", 0)) + 1
            self._stats["last_vad_error"] = str(exc)[:240]
            log.warning("VAD failed safely: %s", exc)
            self._vad.reset()
            return None

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
                        completion = await self._finish_utterance(acoustic_endpoint=True)
                        self._hybrid.reset()
                        target = (
                            ConversationalState.LISTENING
                            if completion is not None
                            and completion.status
                            is ConversationResultStatus.WAITING_CONTINUATION
                            else ConversationalState.IDLE
                        )
                        self._sm.transition(target)
                        self._emit_state(target)
                        listening_start = 0
                        continue

                # Feed VAD
                event = await self._feed_vad_safely(frame)

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
                            completion = await self._finish_utterance(
                                acoustic_endpoint=True
                            )
                            self._transition_after_utterance(completion)
                            listening_start = 0
                            continue
                        # else: hangover opened, don't finalize yet
                    else:
                        self._utterance.end()
                        self._last_endpoint_at = time.monotonic()
                        completion = await self._finish_utterance(
                            acoustic_endpoint=True
                        )
                        self._transition_after_utterance(completion)
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
                        completion = await self._finish_utterance(
                            acoustic_endpoint=True
                        )
                        self._transition_after_utterance(completion)
                        listening_start = 0
                    elif hybrid_evt == HybridEvent.SPEECH_RESUMED:
                        log.debug("hybrid: speech resumed after hangover cancel")

            # THINKING: keep VAD warm but don't act
            elif state == ConversationalState.THINKING:
                await self._feed_vad_safely(frame)

            # SPEAKING: check for barge-in
            elif state == ConversationalState.SPEAKING:
                event = await self._feed_vad_safely(frame)
                if event == VADEvent.SPEECH_STARTED:
                    if self._barge_in.trigger_barge_in():
                        log.info("barge-in detected")
                        self._vad.reset()
                        self._utterance.clear()
                        self._hybrid.reset()
                        # VoiceService owns cancellation and state transitions
                        # when this pipeline is attached to the real service.
                        if not self._barge_in.handler_installed:
                            self._sm.transition(ConversationalState.INTERRUPTED)
                            self._emit_state(ConversationalState.INTERRUPTED)
                            self._sm.transition(ConversationalState.LISTENING)
                            self._emit_state(ConversationalState.LISTENING)
                        listening_start = time.monotonic()
                        continue

            # INTERRUPTED: wait for re-listen or IDLE
            elif state == ConversationalState.INTERRUPTED:
                pass

    def _transition_after_utterance(
        self, completion: ConversationCompletion | None
    ) -> None:
        """Return to listening only when the coordinator requests continuation."""
        if (
            completion is not None
            and completion.status is ConversationResultStatus.WAITING_CONTINUATION
        ):
            target = ConversationalState.LISTENING
        else:
            target = ConversationalState.THINKING
        if self._sm.state is not target:
            self._sm.transition(target)
        self._emit_state(target)

    async def _finish_utterance(
        self, *, acoustic_endpoint: bool = True
    ) -> ConversationCompletion | None:
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

        if self._stt_provider is not None:
            utterance_id = uuid.uuid4().hex
            request_epoch = self._transcript_gate.epoch
            request_turn_id = self._turn_id
            self._stats["stt_calls"] = int(self._stats.get("stt_calls", 0)) + 1
            try:
                if self._sm.state is ConversationalState.LISTENING:
                    self._sm.transition(ConversationalState.TRANSCRIBING)
                    self._emit_state(ConversationalState.TRANSCRIBING)
                event = await asyncio.to_thread(
                    self._stt_provider.transcribe,
                    audio_bytes,
                    sample_rate=SAMPLE_RATE,
                    cancellation=self._stt_cancellation,
                    session_id=self._session_id,
                    utterance_id=utterance_id,
                    epoch=request_epoch,
                )
                if not isinstance(event, TranscriptEvent):
                    raise TypeError("STT provider must return TranscriptEvent")
                if (
                    request_epoch != self._transcript_gate.epoch
                    or request_turn_id != self._turn_id
                ):
                    self._stats["discarded_transcripts"] = int(
                        self._stats.get("discarded_transcripts", 0)
                    ) + 1
                    return None
                if event.is_final:
                    if self._transcript_gate.accept(event):
                        completion = self._conversation_coordinator.observe_transcript(
                            event,
                            turn_id=request_turn_id,
                            acoustic_endpoint=acoustic_endpoint,
                        )
                        if not completion.eligible_for_dispatch:
                            self._stats["coordinator_nonfinals"] = int(
                                self._stats.get("coordinator_nonfinals", 0)
                            ) + 1
                            return completion
                        self._stats["accepted_finals"] = int(
                            self._stats.get("accepted_finals", 0)
                        ) + 1
                        if self._on_transcription is not None:
                            self._on_transcription(completion.event)
                        return completion
                    else:
                        self._stats["discarded_transcripts"] = int(
                            self._stats.get("discarded_transcripts", 0)
                        ) + 1
                elif self._on_transcription is not None:
                    # Partial events are observable only; VoiceService never routes them to Core.
                    self._on_transcription(event)
                return None
            except VoiceCancelledError:
                self._stats["cancelled_transcriptions"] = int(
                    self._stats.get("cancelled_transcriptions", 0)
                ) + 1
            except Exception as exc:
                self._stats["stt_errors"] = int(self._stats.get("stt_errors", 0)) + 1
                self._stats["last_stt_error"] = str(exc)[:240]
                log.warning("STT provider failed safely: %s", exc)
            return

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
