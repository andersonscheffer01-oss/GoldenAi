"""VoiceService P1.4C wiring tests — verify TurnManager, barge-in, conversation context."""

import os
import threading
import time

import pytest
from unittest.mock import MagicMock

# Set feature flags before importing
os.environ["JARVIS_STREAMING_VOICE"] = "1"
os.environ["JARVIS_BARGE_IN"] = "1"

from jarvis_core.voice_service import VoiceService


class TestVoiceServiceTurnManager:
    """Verify TurnManager is properly wired into VoiceService."""

    def test_has_turn_manager(self):
        vs = VoiceService()
        assert vs._turn_manager is not None
        assert vs._turn_manager.current_turn_id == 0

    def test_turn_manager_is_thread_safe(self):
        vs = VoiceService()
        # new_turn from main thread
        turn_id = vs._turn_manager.new_turn()
        assert turn_id == 1
        # cancel from another thread
        def cancel():
            vs._turn_manager.cancel_current()
        t = threading.Thread(target=cancel)
        t.start()
        t.join()
        assert vs._turn_manager.get_cancel_event(1).is_set()

    def test_has_barge_in_cancel_event(self):
        vs = VoiceService()
        assert isinstance(vs._barge_in_cancel, threading.Event)
        assert not vs._barge_in_cancel.is_set()

    def test_has_conversation_messages(self):
        vs = VoiceService()
        assert isinstance(vs._conversation_messages, list)
        assert len(vs._conversation_messages) == 0


class TestVoiceServiceBargeInMonitor:
    """Verify barge-in monitor thread management."""

    def test_start_stop_monitor(self):
        vs = VoiceService()
        vs._start_barge_in_monitor()
        assert vs._barge_in_monitor_thread is not None
        assert vs._barge_in_monitor_thread.is_alive()
        vs._stop_barge_in_monitor()
        assert vs._barge_in_monitor_thread is None

    def test_monitor_is_daemon(self):
        vs = VoiceService()
        vs._start_barge_in_monitor()
        assert vs._barge_in_monitor_thread.daemon is True
        vs._stop_barge_in_monitor()

    def test_stop_monitor_when_not_running(self):
        vs = VoiceService()
        vs._stop_barge_in_monitor()  # Should not raise


class TestVoiceServiceStatus:
    """Verify status includes P1.4C fields."""

    def test_status_has_turn_manager(self):
        vs = VoiceService()
        status = vs.status()
        assert "turn_manager" in status
        assert "current_turn_id" in status["turn_manager"]
        assert "barge_in_enabled" in status["turn_manager"]

    def test_status_has_conversation_turns(self):
        vs = VoiceService()
        status = vs.status()
        assert "conversation_turns" in status
        assert status["conversation_turns"] == 0

    def test_push_to_talk_arms_existing_service_without_new_thread(self):
        vs = VoiceService()
        thread = type("AliveThread", (), {"is_alive": lambda self: True})()
        vs.thread = thread
        result = vs.request_utterance()
        assert result["ok"] is True
        assert result["capture_requested"] is True
        assert vs.thread is thread
        assert vs.status()["capture_requested"] is True

    def test_push_to_talk_preserves_gateway_session(self):
        vs = VoiceService()
        vs.thread = type("AliveThread", (), {"is_alive": lambda self: True})()
        result = vs.request_utterance(session_id="gateway-session-7")
        assert result["session_id"] == "gateway-session-7"
        assert vs._desktop_session_id == "gateway-session-7"

    def test_push_to_talk_fails_closed_when_service_is_off(self):
        vs = VoiceService()
        result = vs.request_utterance()
        assert result["ok"] is False
        assert vs.status()["capture_requested"] is False


class TestVoiceServiceStop:
    """Verify stop cleans up turn manager and barge-in."""

    def test_stop_clears_conversation(self):
        vs = VoiceService()
        vs._conversation_messages = [{"role": "user", "content": "test"}]
        vs.stop()
        assert len(vs._conversation_messages) == 0

    def test_stop_clears_barge_in(self):
        vs = VoiceService()
        vs._barge_in_cancel.set()
        vs.stop()
        assert not vs._barge_in_cancel.is_set()

    def test_stop_cleans_turn_manager(self):
        vs = VoiceService()
        vs._turn_manager.new_turn()
        vs.stop()
        assert vs._turn_manager.current_turn_id == 0


class TestDesktopVoiceSingleExecution:
    def test_desktop_utterance_uses_canonical_service_once(self):
        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.execute_command.return_value = {
            "ok": True, "message": "Resposta unica", "tool": "get_time"
        }
        vs._voice = MagicMock()
        spoken = []
        vs._speak = lambda text: spoken.append(text) or True

        vs._handle("que horas sao", timings={
            "utterance_source": "PUSH_TO_TALK",
            "session_id": "gateway-session-7",
            "utterance_id": "utterance-9",
        }, output={"speak": True, "mode": "VOICE"})

        vs.service.execute_command.assert_called_once_with(
            "que horas sao", task_id="gateway-session-7")
        assert spoken == ["Resposta unica"]
        assert vs.last_event["session_id"] == "gateway-session-7"
        assert vs.last_event["utterance_id"] == "utterance-9"
        assert vs.last_event["response_id"]
        assert vs.last_event["tts_owner"] == "VoiceService"
        assert vs.last_event["trace"]["JARVIS_SERVICE_CALL_COUNT"] == 1
        assert vs.last_event["trace"]["FINAL_RESPONSE_COUNT"] == 1
        assert vs.last_event["trace"]["TTS_COUNT"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
