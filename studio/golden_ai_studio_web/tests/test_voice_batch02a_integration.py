"""Hardware-free VoiceService integration for the Batch 02A provider."""

from __future__ import annotations

import asyncio

from jarvis_core.realtime_voice.audio_input import FakeAudioInputProvider
from jarvis_core.realtime_voice.constants import FRAME_BYTES
from jarvis_core.realtime_voice.vad import VADEvent
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


def _fake_factory(**kwargs):
    return FakeAudioInputProvider(**kwargs)


def test_voice_service_explicit_audio_uses_one_provider_and_no_autostart():
    async def exercise():
        service = VoiceService()
        assert service.get_audio_input_provider() is None

        first = await service.start_audio_input(provider_factory=_fake_factory)
        second = await service.start_audio_input(provider_factory=_fake_factory)

        assert first["ok"] is True
        assert second["already_running"] is True
        assert service.get_audio_input_provider() is not None
        assert service.status()["audio_input"]["running"] is True

        stopped = await service.stop_audio_input()
        assert stopped["ok"] is True
        assert stopped["audio_input"]["running"] is False

    asyncio.run(exercise())


def test_voice_service_rejects_legacy_and_provider_capture_overlap():
    async def exercise():
        service = VoiceService()
        await service.start_audio_input(provider_factory=_fake_factory)
        result = service.start(object())
        assert result["ok"] is False
        await service.stop_audio_input()

    asyncio.run(exercise())


def test_voice_service_audio_provider_reaches_existing_vad_and_restarts():
    async def exercise():
        service = VoiceService()
        pipeline = service.get_realtime_voice_pipeline()
        output = []
        pipeline._vad = _SyntheticVAD(
            [VADEvent.SPEECH_STARTED] + [None] * 17 + [VADEvent.ENDPOINT]
        )

        service.arm_wake()
        assert service.activate_wake("audio-activation-1")["ok"] is True
        started = await service.start_audio_input(
            provider_factory=_fake_factory,
            on_transcription=output.append,
        )
        assert started["ok"] is True
        provider = service.get_audio_input_provider()
        assert provider is not None
        for _ in range(19):
            provider.emit_frame(_frame())
        await asyncio.sleep(0.05)
        assert pipeline.state_machine.state.value == "thinking"
        assert output and output[0]

        await service.stop_audio_input()
        assert provider.is_running is False
        assert pipeline._frame_task is None

        service.arm_wake()
        assert service.activate_wake("audio-activation-2")["ok"] is True
        restarted = await service.restart_audio_input(provider_factory=_fake_factory)
        assert restarted["ok"] is True
        await service.stop_audio_input()
        assert provider is service.get_audio_input_provider()

    asyncio.run(exercise())


def test_voice_service_provider_failure_does_not_call_core_or_leave_stream():
    async def exercise():
        service = VoiceService()

        class FailingProvider(FakeAudioInputProvider):
            def start(self):
                self._device_errors += 1
                self._last_error = "device unavailable"
                return {"ok": False, "started": False, "error": self._last_error}

        result = await service.start_audio_input(provider_factory=FailingProvider)
        assert result["ok"] is False
        assert result["audio_input"]["running"] is False
        assert service._realtime_pipeline._frame_task is None
        assert service.service is None

    asyncio.run(exercise())
