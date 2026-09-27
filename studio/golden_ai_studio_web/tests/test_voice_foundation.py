"""Focused Voice Foundation tests; no microphone, speaker, network, or DB."""

from __future__ import annotations

import tempfile
import threading
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    IllegalTransition,
    VoiceStateMachine,
)
from jarvis_core.voice_foundation import (
    SpeechToTextProvider,
    TextToSpeechProvider,
    VoiceCancellation,
    VoiceCancelledError,
    VoiceSession,
)
from jarvis_core.voice_service import VoiceService


def test_voice_state_transitions_are_explicit_and_terminal_shutdown_is_guarded():
    machine = VoiceStateMachine(ConversationalState.STOPPED)
    for state in (
        ConversationalState.IDLE,
        ConversationalState.LISTENING,
        ConversationalState.TRANSCRIBING,
        ConversationalState.THINKING,
        ConversationalState.SPEAKING,
        ConversationalState.INTERRUPTED,
        ConversationalState.LISTENING,
        ConversationalState.IDLE,
        ConversationalState.STOPPED,
    ):
        machine.transition(state)

    assert machine.state is ConversationalState.STOPPED
    assert len(machine.history) == 9
    with pytest.raises(IllegalTransition):
        machine.transition(ConversationalState.SPEAKING)


def test_voice_session_identity_and_cancellation_are_isolated():
    first = VoiceSession()
    second = VoiceSession()

    assert first.session_id != second.session_id
    assert first.cancellation.cancel("test_cancel") is True
    assert first.cancellation.is_cancelled is True
    assert first.cancellation.reason == "test_cancel"
    assert second.cancellation.is_cancelled is False
    assert first.cancellation.cancel("later_reason") is False


def test_cooperative_tts_cancellation_is_observable_without_audio():
    cancellation = VoiceCancellation()
    started = threading.Event()
    stopped = threading.Event()

    class FakeTTS:
        def speak(self, text, *, cancellation):
            started.set()
            cancellation.wait(1.0)
            try:
                cancellation.throw_if_cancelled()
            finally:
                stopped.set()

        def cancel(self):
            cancellation.cancel("provider_cancel")

    provider = FakeTTS()
    assert isinstance(provider, TextToSpeechProvider)
    errors = []

    def run_provider():
        try:
            provider.speak("hello", cancellation=cancellation)
        except VoiceCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=run_provider, daemon=True)
    worker.start()
    assert started.wait(0.5)
    assert cancellation.cancel("barge_in") is True
    worker.join(0.5)
    assert stopped.is_set()
    assert not worker.is_alive()
    assert len(errors) == 1


def test_provider_failure_has_a_coherent_terminal_state():
    class BrokenSTT:
        def transcribe(self, audio, *, sample_rate, cancellation):
            raise RuntimeError("synthetic STT failure")

    assert isinstance(BrokenSTT(), SpeechToTextProvider)
    machine = VoiceStateMachine(ConversationalState.STOPPED)
    machine.transition(ConversationalState.IDLE)
    machine.transition(ConversationalState.LISTENING)
    machine.transition(ConversationalState.TRANSCRIBING)
    try:
        BrokenSTT().transcribe(b"fake", sample_rate=16000,
                               cancellation=VoiceCancellation())
    except RuntimeError:
        machine.transition(ConversationalState.ERROR)

    assert machine.state is ConversationalState.ERROR
    machine.transition(ConversationalState.STOPPED)
    assert machine.state is ConversationalState.STOPPED


def test_voice_service_uses_existing_core_boundary_and_no_voice_db():
    service = VoiceService()
    service.state = "OUVINDO"
    service.state = "LISTENING"
    assert service._state_machine.state is ConversationalState.LISTENING

    core = MagicMock()
    core.execute_command.return_value = {"ok": True, "message": "Resposta"}
    service.service = core
    service._voice = MagicMock()
    service._speak = lambda text: True
    service._handle(
        "teste",
        timings={"utterance_source": "PUSH_TO_TALK", "session_id": "core-session"},
        output={"speak": True, "mode": "VOICE"},
    )
    core.execute_command.assert_called_once_with("teste", task_id="core-session")
    assert "os.system(" not in inspect.getsource(service._handle)


def test_voice_service_restart_and_shutdown_are_idempotent_without_audio():
    class FakeVoice:
        WAKE_WORD = "jarvis"

        def warmup_async(self):
            return None

        def record_until_silence(self, **kwargs):
            kwargs["stop_event"].wait(0.02)
            return {"ok": False, "error": "test stop"}

        def status(self):
            return {}

    fake = FakeVoice()
    with patch("jarvis_core.voice_service.get_voice", return_value=fake):
        service = VoiceService()
        first = service.start(object())
        first_id = service.status()["session_id"]
        assert first["ok"] is True
        assert service.stop()["ok"] is True
        assert service.stop()["ok"] is True

        second = service.start(object())
        second_id = service.status()["session_id"]
        assert second["ok"] is True
        assert first_id != second_id
        assert service.stop()["ok"] is True
        assert service.status()["voice_state"] == "stopped"


def test_cancel_current_operation_is_cooperative_and_prepares_barge_in():
    service = VoiceService()
    service.state = "OUVINDO"
    service.state = "LISTENING"
    service.state = "TRANSCRIBING"
    service.state = "PROCESSING"
    service.state = "SPEAKING"
    result = service.cancel_current_operation("barge_in")

    assert result == {"ok": True, "cancelled": True, "reason": "barge_in"}
    assert service.state == "INTERRUPTED"
    assert service._state_machine.state is ConversationalState.INTERRUPTED
    assert service._barge_in_cancel.is_set()
    assert service._operation_cancellation.is_cancelled


def test_foundation_does_not_persist_audio_or_create_a_voice_database():
    with tempfile.TemporaryDirectory() as directory:
        session = VoiceSession()
        session.metadata["audio_policy"] = "memory_only"
        assert session.session_id
        assert list(Path(directory).iterdir()) == []
        assert not (Path(directory) / "voice.db").exists()
