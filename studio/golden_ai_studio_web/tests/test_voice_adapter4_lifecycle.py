"""Offline lifecycle/recovery coverage for Voice Adapter 4.

These tests use only deterministic providers and never open a microphone,
speaker, model, network connection, or persistence path.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jarvis_core.realtime_voice.constants import FRAME_BYTES, MIN_UTTERANCE_MS
from jarvis_core.realtime_voice.integration import RealtimeVoicePipeline
from jarvis_core.realtime_voice.state_machine import ConversationalState
from jarvis_core.voice_foundation import DeterministicFakeSTTProvider, TranscriptEvent
from jarvis_core.voice_service import VoiceService
from jarvis_core.voice_tts import (
    FakeAudioOutputProvider,
    FakeTextToSpeechProvider,
)


class _FakeVoice:
    initial_prompt = ""
    WAKE_WORD = "jarvis"

    def warmup_async(self):
        return None

    def touch_interaction(self):
        return None


def _startable_service(monkeypatch):
    import jarvis_core.voice_service as voice_module

    monkeypatch.setattr(voice_module, "get_voice", lambda: _FakeVoice())
    service = VoiceService()
    service._loop = lambda: service.stop_event.wait(0.5)
    return service


def _prime_pipeline(pipeline: RealtimeVoicePipeline) -> None:
    pipeline.state_machine.transition(ConversationalState.LISTENING)
    pipeline._utterance.start()
    pipeline._utterance.append(b"\x01" * (FRAME_BYTES * 20))
    pipeline._utterance.end()
    assert pipeline._utterance.duration_ms >= MIN_UTTERANCE_MS


def test_session_start_double_start_and_stop_are_deterministic(monkeypatch):
    service = _startable_service(monkeypatch)
    gateway = object()

    first = service.start(gateway)
    session_a = service._session_id
    turn_a = service._current_turn_id
    duplicate = service.start(gateway)
    stopped = service.stop()
    stopped_again = service.stop()

    assert first["ok"] is True
    assert duplicate["ok"] is True
    assert service._session_id == session_a
    assert turn_a > 0
    assert stopped["ok"] is True
    assert stopped_again["ok"] is True
    assert stopped_again["already_stopped"] is True
    assert service.state == "OFF"
    assert service._turn_manager.current_turn_id == 0


def test_restart_isolates_session_and_rejects_late_callback(monkeypatch):
    service = _startable_service(monkeypatch)
    gateway = MagicMock()
    gateway.execute_command.return_value = {"ok": True, "message": "ok"}

    service.start(gateway)
    old_session = service._session_id
    service.stop()
    service.start(gateway)
    new_session = service._session_id

    late = TranscriptEvent(
        text="resposta antiga",
        is_final=True,
        sequence=1,
        session_id=old_session,
        utterance_id="old-utterance",
        provider="fake",
    )
    service._handle_transcript_event(late)

    assert old_session != new_session
    gateway.execute_command.assert_not_called()
    assert service.last_rejection["classification"] == "STALE_EVENT"
    service.stop()


def test_rapid_start_stop_cycles_leave_no_legacy_thread(monkeypatch):
    service = _startable_service(monkeypatch)
    for _ in range(3):
        assert service.start(object())["ok"] is True
        assert service.stop()["ok"] is True
        assert not service.is_running()
    assert service._turn_manager.current_turn_id == 0


def test_stop_during_thinking_invalidates_session_cleanly(monkeypatch):
    service = _startable_service(monkeypatch)
    service.start(object())
    service.state = "PROCESSING"
    result = service.stop()
    assert result["ok"] is True
    assert service.state == "OFF"
    assert service._voice_session.cancellation.is_cancelled is True


def test_stop_during_speaking_flushes_owned_output():
    service = VoiceService()
    provider = FakeTextToSpeechProvider(chunk_delay=0.05)
    output = FakeAudioOutputProvider(maxsize=8)
    service.configure_tts_pipeline(provider, output)
    started = service.start_tts_stream()
    assert started["ok"] is True
    service.feed_tts_stream("Primeira frase. Segunda frase.")
    assert provider.started.wait(0.5)
    service._state_machine.force_idle()
    service.state = "SPEAKING"
    service.stop()
    diagnostics = service.get_streaming_tts().diagnostics()
    assert diagnostics["worker_alive"] is False
    assert diagnostics["queue_depth"] == 0
    assert output.queued == ()
    service.release_tts_pipeline()


def test_stt_failure_recovers_to_listening_without_dispatch():
    async def exercise():
        pipeline = RealtimeVoicePipeline()
        stt = DeterministicFakeSTTProvider([RuntimeError("stt down")])
        callbacks = []
        await pipeline.start(
            stt_provider=stt,
            on_transcription=callbacks.append,
            session_id="session-a",
            turn_id=1,
        )
        try:
            _prime_pipeline(pipeline)
            assert await pipeline._finish_utterance() is None
            assert pipeline.stats["stt_errors"] == 1
            assert pipeline.stats["recovery_attempts"] == 1
            assert pipeline.state_machine.state is ConversationalState.LISTENING
            assert callbacks == []
        finally:
            await pipeline.stop()

    asyncio.run(exercise())


def test_coordinator_failure_recovers_without_ambiguous_completion():
    async def exercise():
        pipeline = RealtimeVoicePipeline()
        stt = DeterministicFakeSTTProvider(["abra o painel"])
        await pipeline.start(stt_provider=stt, session_id="session-a", turn_id=1)
        pipeline._conversation_coordinator.observe_transcript = MagicMock(
            side_effect=RuntimeError("coordinator down")
        )
        try:
            _prime_pipeline(pipeline)
            assert await pipeline._finish_utterance() is None
            assert pipeline.stats["recovery_attempts"] == 1
            assert pipeline.state_machine.state is ConversationalState.LISTENING
        finally:
            await pipeline.stop()

    asyncio.run(exercise())


def test_partial_transcript_never_reaches_voice_service_core():
    service = VoiceService()
    service.service = MagicMock()
    partial = TranscriptEvent(
        text="parcial",
        is_final=False,
        sequence=1,
        session_id=service._session_id,
        utterance_id="u-1",
        provider="fake",
    )
    service._handle_transcript_event(partial)
    service.service.execute_command.assert_not_called()


def test_core_failure_speaks_safe_fallback_and_invalidates_turn():
    service = VoiceService()
    spoken = []
    service._speak = lambda text: spoken.append(text) or True
    service._should_use_streaming = lambda: False
    service._voice = _FakeVoice()
    service.service = SimpleNamespace(
        registry=object(),
        orchestrator=SimpleNamespace(
            decide=lambda *args, **kwargs: SimpleNamespace(
                requires_planning=False, steps=[]
            )
        ),
    )
    service._get_brain = lambda: SimpleNamespace(
        interpret=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("core unavailable")
        )
    )

    service._handle("teste", output={"speak": True, "mode": "VOICE"})

    assert len(spoken) == 1
    assert "Erro" in spoken[0]
    assert service._last_recovery["component"] == "core"
    assert service._last_recovery["result"] == "recovered"
    assert service._current_turn_id > 0


@pytest.mark.parametrize("failure_kind", ["tts", "output"])
def test_tts_and_output_failures_are_bounded_and_recover(failure_kind):
    class FailingOutput(FakeAudioOutputProvider):
        def enqueue(self, chunk):
            raise RuntimeError("output down")

    service = VoiceService()
    provider = FakeTextToSpeechProvider(
        failure=RuntimeError("tts down") if failure_kind == "tts" else None
    )
    output = FailingOutput(maxsize=8) if failure_kind == "output" else FakeAudioOutputProvider(maxsize=8)
    service.configure_tts_pipeline(provider, output)
    service.state = "SPEAKING" if service._state_machine.state is not ConversationalState.STOPPED else "OFF"

    assert service._speak("resposta controlada") is False
    assert service._last_recovery["component"] == "tts"
    assert service._last_recovery["result"] in {"recovered", "shutdown"}
    assert service.get_streaming_tts().diagnostics()["worker_alive"] is False
    service.release_tts_pipeline()


def test_stop_invalidates_generation_and_rejects_late_tts_output():
    service = VoiceService()
    provider = FakeTextToSpeechProvider()
    output = FakeAudioOutputProvider(maxsize=8)
    service.configure_tts_pipeline(provider, output)
    started = service.start_tts_stream()
    identity = started["identity"]
    service.feed_tts_stream("resposta antiga.")
    service.stop()

    assert service.feed_tts_stream("texto tardio") ["ok"] is True
    assert output.queued == ()
    assert service._voice_session.cancellation.is_cancelled is True
    assert service.accepts_core_output(turn_id=identity[1], generation=identity[2]) is False
    service.release_tts_pipeline()


def test_realtime_pipeline_stop_during_pending_transcription_is_bounded():
    async def exercise():
        started = threading.Event()

        def slow(_cancellation):
            started.set()
            time.sleep(0.05)
            return "late result"

        pipeline = RealtimeVoicePipeline()
        stt = DeterministicFakeSTTProvider([slow])
        await pipeline.start(stt_provider=stt, session_id="session-a", turn_id=1)
        _prime_pipeline(pipeline)
        task = asyncio.create_task(pipeline._finish_utterance())
        await asyncio.to_thread(started.wait, 0.5)
        await pipeline.stop()
        await task
        assert pipeline.conversation_coordinator.diagnostics()["cancelled"] is True
        assert pipeline.state_machine.state is ConversationalState.IDLE

    asyncio.run(exercise())


def test_stale_generation_is_rejected_after_recovery():
    service = VoiceService()
    old_turn = service._current_turn_id
    old_generation = service._tts_epoch
    assert service._recover_after_failure("core", "controlled") is True
    assert service.accepts_core_output(
        turn_id=old_turn, generation=old_generation
    ) is False
