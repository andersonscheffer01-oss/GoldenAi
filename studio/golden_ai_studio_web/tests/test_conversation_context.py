"""Immediate conversation context is isolated by Gateway task/session id."""
from dataclasses import replace
from unittest.mock import patch

from jarvis_core.service import JarvisService


class FakeBrain:
    def __init__(self):
        self.calls = []
        self.last_llm = {"provider": "fake", "model": "context-model"}

    def interpret(self, command, conversation_history=None, **kwargs):
        self.calls.append((command, list(conversation_history or [])))
        return {"ok": True, "plan": {"response": "Resposta contextual."}}


def test_recent_user_and_assistant_turns_are_passed_in_same_session(tmp_path):
    service = JarvisService(tmp_path)
    brain = FakeBrain()
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            service.execute_command("meu nome é teste123", task_id="session-a")
            service.execute_command("qual nome eu acabei de falar?", task_id="session-a")
        history = brain.calls[1][1]
        assert history[-2] == {"role": "user", "content": "meu nome é teste123"}
        assert history[-1]["role"] == "assistant"
    finally:
        service.close()


def test_tool_error_is_structured_in_next_turn_context(tmp_path):
    service = JarvisService(tmp_path)
    tool = service.registry.get("list_processes")
    service.registry._tools["list_processes"] = replace(
        tool, handler=lambda: {"ok": False,
                               "error": "provider_search_failed:invalid_response"})
    brain = FakeBrain()
    try:
        service.execute_command("listar processos", task_id="session-a")
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            service.execute_command("o que aconteceu?", task_id="session-a")
        history = brain.calls[0][1]
        assert any("TOOL_ERROR:" in item["content"] for item in history)
        assert any("provider_search_failed" in item["content"] for item in history)
    finally:
        service.close()


def test_conversation_context_does_not_leak_between_sessions(tmp_path):
    service = JarvisService(tmp_path)
    brain = FakeBrain()
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            service.execute_command("segredo da sessão A", task_id="session-a")
            service.execute_command("o que foi dito?", task_id="session-b")
        assert brain.calls[1][1] == []
    finally:
        service.close()
