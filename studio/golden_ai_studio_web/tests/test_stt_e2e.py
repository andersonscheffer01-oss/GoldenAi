"""Hardware-free Audio -> VAD -> STT -> VoiceService boundary tests."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

from jarvis_core.realtime_voice.audio_input import FakeAudioInputProvider
from jarvis_core.realtime_voice.constants import FRAME_BYTES
from jarvis_core.realtime_voice.integration import RealtimeVoicePipeline
from jarvis_core.realtime_voice.vad import VADEvent
from jarvis_core.voice_foundation import (
    DeterministicFakeSTTProvider,
    TranscriptEvent,
    VoiceCancelledError,
)
from jarvis_core.voice_service import VoiceService


class _SyntheticVAD:
    def __init__(self, events):
        self._events = iter(events)

    def reset(self):
        return None

    async def unload(self):
        return None

    async def feed(self, frame):
        assert len(frame) == FRAME_BYTES
        return next(self._events, None)


def _frame() -> bytes:
    return b"\x01" * FRAME_BYTES


def _speech_then_endpoint():
    return [VADEvent.SPEECH_STARTED] + [None] * 17 + [VADEvent.ENDPOINT]


async def _run_pipeline(provider, callback):
    pipeline = RealtimeVoicePipeline()
    pipeline._vad = _SyntheticVAD(_speech_then_endpoint())
    await pipeline.start(
        on_transcription=callback,
        stt_provider=provider,
        session_id="e2e-session",
    )
    pipeline.state_machine.transition(pipeline.state_machine.state.LISTENING)
    for _ in range(19):
        pipeline.feed_frame(_frame())
    await asyncio.sleep(0.08)
    return pipeline


def test_audio_vad_stt_voice_session_accepts_one_final_without_hardware():
    async def exercise():
        events = []
        provider = DeterministicFakeSTTProvider(["Golden transcript"])
        pipeline = await _run_pipeline(provider, events.append)
        try:
            assert len(provider.calls) == 1
            assert len(events) == 1
            assert isinstance(events[0], TranscriptEvent)
            assert events[0].text == "Golden transcript"
            assert events[0].session_id == "e2e-session"
            assert pipeline.stats["stt_calls"] == 1
            assert pipeline.stats["accepted_finals"] == 1
        finally:
            await pipeline.stop()

    asyncio.run(exercise())


def test_partial_transcript_never_reaches_voice_service_core():
    service = VoiceService()
    service.service = MagicMock()
    service._handle = MagicMock()
    partial = TranscriptEvent(
        text="parcial", is_final=False, sequence=1,
        session_id="s", utterance_id="u", provider="fake",
    )
    final = TranscriptEvent(
        text="final", is_final=True, sequence=2,
        session_id="s", utterance_id="u", provider="fake",
    )
    service._handle_transcript_event(partial)
    service._handle_transcript_event(final)
    assert service._handle.call_count == 1
    assert service._handle.call_args.args[0] == "final"


def test_voice_service_explicit_provider_reaches_existing_core_boundary():
    async def exercise():
        service = VoiceService()
        service.service = MagicMock()
        service._handle = MagicMock()
        pipeline = service.get_realtime_voice_pipeline()
        pipeline._vad = _SyntheticVAD(_speech_then_endpoint())
        service.arm_wake()
        service.activate_wake("e2e-wake")
        provider = DeterministicFakeSTTProvider(["through core boundary"])
        started = await service.start_audio_input(
            provider_factory=lambda **kwargs: FakeAudioInputProvider(**kwargs),
            stt_provider=provider,
        )
        assert started["ok"] is True
        try:
            audio = service.get_audio_input_provider()
            for _ in range(19):
                audio.emit_frame(_frame())
            await asyncio.sleep(0.08)
            assert len(provider.calls) == 1
            assert service._handle.call_count == 1
            assert service._handle.call_args.args[0] == "through core boundary"
        finally:
            await service.stop_audio_input()

    asyncio.run(exercise())


def test_cancelled_provider_result_is_discarded_after_pipeline_cancel():
    async def exercise():
        started = threading.Event()
        callbacks = []

        def delayed(cancellation):
            started.set()
            cancellation.wait(1.0)
            cancellation.throw_if_cancelled()
            return "late"

        provider = DeterministicFakeSTTProvider([delayed])
        pipeline = RealtimeVoicePipeline()
        pipeline._vad = _SyntheticVAD(_speech_then_endpoint())
        await pipeline.start(
            on_transcription=callbacks.append,
            stt_provider=provider,
            session_id="cancel-session",
        )
        pipeline.state_machine.transition(pipeline.state_machine.state.LISTENING)
        for _ in range(19):
            pipeline.feed_frame(_frame())
        assert await asyncio.to_thread(started.wait, 0.5)
        pipeline.cancel_transcription("new session")
        await pipeline.stop()
        await asyncio.sleep(0.05)
        assert callbacks == []

    asyncio.run(exercise())


def test_pipeline_has_one_audio_owner_and_no_direct_core_or_tool_path():
    pipeline = RealtimeVoicePipeline()
    assert pipeline.stt_provider is None
    assert not hasattr(pipeline, "microphone")
    source = __import__("inspect").getsource(RealtimeVoicePipeline._finish_utterance)
    assert "execute_command" not in source
    assert "subprocess" not in source
