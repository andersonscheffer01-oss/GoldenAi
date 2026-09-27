"""Synthetic VoiceService -> wake -> VAD integration tests."""

from __future__ import annotations

import asyncio

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


def test_voice_service_owns_shared_state_and_wake_lifecycle():
    service = VoiceService()
    pipeline = service.get_realtime_voice_pipeline()

    assert pipeline.state_machine is service._state_machine
    assert service.arm_wake()["armed"] is True
    activation = service.activate_wake("activation-1")

    assert activation["ok"] is True
    assert service._state_machine is pipeline.state_machine
    assert service.state == "WAKE_DETECTED"
    assert service.activate_wake("activation-1")["ok"] is False


def test_voice_service_rejects_stale_wake_without_core_side_effect():
    service = VoiceService()
    service.arm_wake()
    result = service.activate_wake("activation-old", session_id="old-session")

    assert result == {"ok": False, "reason": "stale_or_duplicate_wake"}
    assert service._state_machine.state.value == "idle"


def test_voice_service_vad_wake_e2e_restart_is_synthetic():
    async def exercise():
        service = VoiceService()
        pipeline = service.get_realtime_voice_pipeline()
        output = []
        pipeline._vad = _SyntheticVAD(
            [VADEvent.SPEECH_STARTED] + [None] * 17 + [VADEvent.ENDPOINT]
        )
        await pipeline.start(on_transcription=output.append)
        service.arm_wake()
        first = service.activate_wake("activation-1")
        assert first["ok"] is True

        for _ in range(19):
            pipeline.feed_frame(_frame())
        await asyncio.sleep(0.05)
        assert pipeline.state_machine.state.value == "thinking"
        assert output and output[0]

        await service.stop_realtime_voice_pipeline()
        assert service._realtime_pipeline is None
        assert service._wake_lifecycle.armed is False

        pipeline = service.get_realtime_voice_pipeline()
        pipeline._vad = _SyntheticVAD([VADEvent.SPEECH_STARTED])
        await pipeline.start()
        service.arm_wake()
        second = service.activate_wake("activation-2")
        assert second["ok"] is True
        await service.stop_realtime_voice_pipeline()
        assert service._state_machine.state.value == "idle"

    asyncio.run(exercise())
