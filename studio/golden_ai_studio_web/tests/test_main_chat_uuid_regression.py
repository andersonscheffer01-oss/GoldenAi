"""Regression coverage for the canonical Main Chat request-id path."""

from types import SimpleNamespace
from unittest.mock import patch

import server_agent


class _FakeBrain:
    def __init__(self):
        self.model_router_calls = []
        model_router = SimpleNamespace(
            generate=lambda text: self.model_router_calls.append(text) or "stub response"
        )
        self.orchestrator = SimpleNamespace(
            models=SimpleNamespace(providers={"stub": object()}, boundary=model_router),
            mode="off",
            decide=lambda _text: SimpleNamespace(
                requires_planning=False,
                route=SimpleNamespace(value="GENERAL"),
                preferred_skill="chat",
                confidence=1.0,
            ),
        )
        self.last_llm = {"provider": "stub", "model": "stub-model"}
        self.interpret_calls = []

    def interpret(self, text, **kwargs):
        self.interpret_calls.append((text, kwargs))
        response = self.orchestrator.models.boundary.generate(text)
        return {"ok": True, "plan": {"response": response}}

    def request_metrics(self, *_args):
        return {"llm_calls": 0, "model_router_boundary": "REACHED"}


class _FakeService:
    def __init__(self):
        self.registry = object()
        self.runtime = SimpleNamespace()
        self.orchestrator = None
        self.telemetry = []
        self.metrics = []

    def _attach_research_telemetry(self, result, request_id, session_id, _started):
        self.telemetry.append((result, request_id, session_id))
        return {"routing_metadata": {"request_id": request_id, "session_id": session_id}}

    def record_response_metrics(self, *args):
        self.metrics.append(args)


def test_main_chat_uuid_path_reaches_canonical_brain_boundary_without_provider():
    brain = _FakeBrain()
    service = _FakeService()
    service.orchestrator = brain.orchestrator
    handler = server_agent.GoldenAIHandler.__new__(server_agent.GoldenAIHandler)
    output_mode = SimpleNamespace(
        parse=lambda text, source: {"content": text, "speak": False, "mode": source}
    )
    desktop = SimpleNamespace(service=service)

    with patch("jarvis_core.brain.get_brain", return_value=brain), \
         patch("desktop_center.DESKTOP_CENTER", desktop), \
         patch("jarvis_core.output_mode.get_output_mode_manager", return_value=output_mode):
        result = handler._api_jarvis_chat({
            "text": "Responda somente: MAIN_CHAT_RUNTIME_OK",
            "session_id": "main-chat-uuid-regression",
        })

    assert result["ok"] is True
    assert result["response"] == "stub response"
    assert brain.interpret_calls
    assert brain.model_router_calls == ["Responda somente: MAIN_CHAT_RUNTIME_OK"]
    assert len(service.telemetry) == 1
    assert service.telemetry[0][1]
    assert service.telemetry[0][2] == "main-chat-uuid-regression"
    assert result["routing_metadata"]["request_id"] == service.telemetry[0][1]
