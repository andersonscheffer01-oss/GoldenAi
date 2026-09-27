"""Deterministic Voice Batch 01 foundation tests.

These tests exercise the existing realtime VAD and frame lifecycle without
loading an acoustic model or opening an audio device.
"""

from __future__ import annotations

import asyncio

import numpy as np

from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue
from jarvis_core.realtime_voice.constants import FRAME_BYTES
from jarvis_core.realtime_voice.integration import RealtimeVoicePipeline
from jarvis_core.realtime_voice.vad import SileroVADAdapter, VADEvent, _Internal
from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    VoiceStateMachine,
)
from jarvis_core.realtime_voice.wake_lifecycle import WakeLifecycle


def _frame(amplitude: int = 0) -> bytes:
    return (np.ones(480, dtype=np.int16) * amplitude).tobytes()


def test_vad_silence_only():
    vad = SileroVADAdapter(speech_start_windows=2)
    assert vad._step(0.1) is None
    assert vad._step(0.1) is None
    assert vad._internal is _Internal.SILENCE


def test_vad_speech_only_and_continue():
    vad = SileroVADAdapter(speech_start_windows=2)
    assert vad._step(0.9) is None
    assert vad._step(0.9) is VADEvent.SPEECH_STARTED
    assert vad._step(0.9) is None
    assert vad._internal is _Internal.SPEECH


def test_vad_speech_to_silence_endpoint():
    vad = SileroVADAdapter(endpoint_ms=64)
    vad._internal = _Internal.SPEECH
    assert vad._step(0.1) is None
    assert vad._step(0.1) is VADEvent.ENDPOINT
    assert vad._internal is _Internal.SILENCE


def test_vad_transient_noise_is_debounced():
    vad = SileroVADAdapter(speech_start_windows=3)
    assert vad._step(0.9) is None
    assert vad._step(0.1) is None
    assert vad._step(0.9) is None
    assert vad._step(0.9) is None
    assert vad._step(0.9) is VADEvent.SPEECH_STARTED


def test_vad_reset_clears_session_state():
    vad = SileroVADAdapter()
    vad._internal = _Internal.SPEECH
    vad._silence_ms = 120
    vad._consecutive_speech_windows = 4
    vad._buffer.extend(b"stale")

    vad.reset()

    assert vad._internal is _Internal.SILENCE
    assert vad._silence_ms == 0
    assert vad._consecutive_speech_windows == 0
    assert vad._buffer == bytearray()


def test_audio_queue_cancel_blocks_late_frames():
    queue = AudioFrameQueue()
    queue.cancel()
    queue.put_nowait(_frame(1000))
    assert queue.empty


def test_realtime_pipeline_reset_and_cancel_are_session_safe():
    async def exercise():
        pipeline = RealtimeVoicePipeline()
        pipeline._vad._internal = _Internal.SPEECH
        pipeline._utterance.start()
        pipeline._stats["stale"] = True

        await pipeline.start()
        assert pipeline.state_machine.state.value == "idle"
        assert pipeline._vad._internal is _Internal.SILENCE
        assert pipeline._utterance.active is False
        assert pipeline.stats == {}

        pipeline.feed_frame(_frame(1200))
        await pipeline.stop()
        assert pipeline._frame_task is None
        assert pipeline.state_machine.state.value == "idle"
        assert pipeline._utterance.active is False

        pipeline.feed_frame(_frame(1200))
        assert pipeline.queue.empty

    asyncio.run(exercise())


def test_wake_lifecycle_reuses_existing_state_machine():
    machine = VoiceStateMachine(ConversationalState.IDLE)
    lifecycle = WakeLifecycle(machine, session_id="session-a")

    assert lifecycle.state_machine is machine
    assert lifecycle.arm() is True
    activation = lifecycle.activate("wake-1", observed_at=10.0)

    assert activation is not None
    assert activation.session_id == "session-a"
    assert activation.sequence == 1
    assert machine.state is ConversationalState.LISTENING


def test_wake_duplicate_activation_is_idempotent():
    lifecycle = WakeLifecycle(VoiceStateMachine(), session_id="session-a")
    lifecycle.arm()
    assert lifecycle.activate("wake-1") is not None
    assert lifecycle.activate("wake-1") is None
    assert lifecycle.activate("wake-2") is None


def test_wake_stale_session_is_blocked():
    lifecycle = WakeLifecycle(VoiceStateMachine(), session_id="session-new")
    lifecycle.arm()
    assert lifecycle.activate("wake-old", session_id="session-old") is None
    assert lifecycle.active is None


def test_wake_cancel_shutdown_and_restart():
    machine = VoiceStateMachine()
    lifecycle = WakeLifecycle(machine, session_id="session-a")
    lifecycle.arm()
    assert lifecycle.activate("wake-1") is not None
    assert lifecycle.cancel() is True
    assert lifecycle.armed is False
    assert lifecycle.activate("wake-2") is None

    lifecycle.arm()
    assert lifecycle.activate("wake-2") is not None
    lifecycle.shutdown()
    assert machine.state is ConversationalState.STOPPED
    assert lifecycle.armed is False


def test_wake_reset_starts_clean_session():
    lifecycle = WakeLifecycle(VoiceStateMachine(), session_id="session-a")
    lifecycle.arm()
    assert lifecycle.activate("wake-1") is not None
    new_session = lifecycle.reset_session("session-b")

    assert new_session == "session-b"
    assert lifecycle.active is None
    assert lifecycle.armed is False
    lifecycle.arm()
    assert lifecycle.activate("wake-1") is not None
