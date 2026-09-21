"""Safe sequential multi-tool plans with one grounded final synthesis."""

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.brain import JarvisBrain
from jarvis_core.gateway.gateway import Gateway
from jarvis_core.gateway.protocol import GatewayMessage, MessageType
from jarvis_core.models import Risk, Tool
from jarvis_core.orchestrator.models import DataClassification, ModelProfile
from jarvis_core.service import JarvisService


ROOT = Path(__file__).resolve().parent.parent


def _service_and_brain():
    service = JarvisService(ROOT)
    brain = JarvisBrain(service.registry, service.legacy_memory,
                        orchestrator=service.orchestrator,
                        memory_v2=service.memory_v2)
    return service, brain


def _replace(service, name, handler):
    service.registry._tools[name] = replace(service.registry.get(name), handler=handler)


def _plan_result(brain, steps):
    brain.interpret = lambda command: {"ok": True, "plan": {"steps": steps}}
    brain.last_llm = {"provider": "planner", "model": "mock"}
    return brain


def test_computer_heavy_executes_both_once_and_returns_only_synthesis():
    service, brain = _service_and_brain()
    calls = {"system_status": 0, "list_processes": 0, "synthesis": 0}

    def status():
        calls["system_status"] += 1
        return {"ok": True, "message": "CPU 87%, RAM 72%", "verified": True}

    def processes():
        calls["list_processes"] += 1
        return {"ok": True, "message": "editor.exe usa 40%", "verified": True}

    _replace(service, "system_status", status)
    _replace(service, "list_processes", processes)
    _plan_result(brain, [{"tool": "system_status", "args": {}},
                         {"tool": "list_processes", "args": {}}])

    def synthesize(command, executions):
        calls["synthesis"] += 1
        assert "87%" in json.dumps(executions)
        return {"ok": True, "response": "CPU em 87%; editor.exe lidera com 40%.",
                "provider": "mock"}

    brain.synthesize_tool_results = synthesize
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command(
                "você pode me dizer o que está deixando meu computador pesado agora?")
    finally:
        brain.close()
        service.close()

    assert calls == {"system_status": 1, "list_processes": 1, "synthesis": 1}
    assert result["message"] == "CPU em 87%; editor.exe lidera com 40%."
    assert '"steps"' not in result["message"]
    assert result["final_synthesis"] is True


def test_performance_diagnosis_is_deterministic_multi_tool_without_llm_planning():
    service, brain = _service_and_brain()
    try:
        result = brain.interpret("por que meu PC está lento?")
    finally:
        brain.close()
        service.close()
    assert result["model"] == "deterministic-fast-path"
    assert [step["tool"] for step in result["plan"]["steps"]] == [
        "system_status", "list_processes"]
    assert brain.last_metrics["llm_result_type"] == "DETERMINISTIC_PLAN"


def test_performance_query_variants_route_to_both_diagnostic_tools():
    service, brain = _service_and_brain()
    variants = (
        "o que está deixando meu computador pesado agora?",
        "por que meu PC está lento?",
        "o que está consumindo meu computador?",
        "qual programa está pesando o PC?",
        "o que está deixando meu PC?",
    )
    try:
        for query in variants:
            result = brain.interpret(query)
            assert [step["tool"] for step in result["plan"]["steps"]] == [
                "system_status", "list_processes"]
    finally:
        brain.close()
        service.close()


def test_simple_status_process_listing_and_conceptual_cpu_are_preserved():
    service, brain = _service_and_brain()
    try:
        assert service._parse("qual o status do sistema?")[0] == "system_status"
        assert service._parse("listar processos")[0] == "list_processes"
        assert service._parse("me explique o que significa CPU") is None
        conceptual = service.orchestrator.decide("me explique o que significa CPU")
        assert conceptual.intent == "conceptual_question"
        assert not conceptual.steps
    finally:
        brain.close()
        service.close()


def test_three_tools_execute_once_with_one_synthesis():
    service, brain = _service_and_brain()
    calls = {name: 0 for name in ("system_status", "get_time", "memory_recent")}
    for name in calls:
        def handler(_name=name, **kwargs):
            calls[_name] += 1
            return {"ok": True, "message": _name, "verified": True}
        _replace(service, name, handler)
    _plan_result(brain, [{"tool": name, "args": {}} for name in calls])
    syntheses = []
    brain.synthesize_tool_results = lambda command, results: (
        syntheses.append(results) or {"ok": True, "response": "Resumo final.",
                                      "provider": "mock"})
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command("faça as três consultas")
    finally:
        brain.close()
        service.close()
    assert calls == {"system_status": 1, "get_time": 1, "memory_recent": 1}
    assert len(syntheses) == 1
    assert result["message"] == "Resumo final."


def test_entire_plan_is_rejected_before_valid_step_for_unknown_tool():
    service, brain = _service_and_brain()
    calls = {"count": 0}
    _replace(service, "system_status", lambda: calls.__setitem__("count", calls["count"] + 1)
             or {"ok": True, "verified": True})
    _plan_result(brain, [{"tool": "system_status", "args": {}},
                         {"tool": "evil_tool", "args": {}}])
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command("plano inválido")
    finally:
        brain.close()
        service.close()
    assert result["ok"] is False
    assert calls["count"] == 0


def test_entire_plan_is_rejected_for_invalid_arguments():
    service, brain = _service_and_brain()
    calls = {"count": 0}
    _replace(service, "system_status", lambda: calls.__setitem__("count", calls["count"] + 1)
             or {"ok": True, "verified": True})
    _plan_result(brain, [{"tool": "system_status", "args": {"bad": 1}}])
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command("argumentos inválidos")
    finally:
        brain.close()
        service.close()
    assert result["ok"] is False
    assert calls["count"] == 0


def test_critical_step_pauses_and_approval_executes_only_it_once():
    service, brain = _service_and_brain()
    calls = {"low": 0, "critical": 0, "post": 0}
    _replace(service, "system_status", lambda: calls.__setitem__("low", calls["low"] + 1)
             or {"ok": True, "message": "low", "verified": True})
    _replace(service, "get_time", lambda: calls.__setitem__("post", calls["post"] + 1)
             or {"ok": True, "message": "post", "verified": True})

    def critical():
        calls["critical"] += 1
        return {"ok": True, "message": "critical", "verified": True}

    service.registry.register(Tool("fake_critical_action", "fake", critical,
                                   Risk.CRITICAL, confirmation=True))
    steps = [{"tool": "system_status", "args": {}},
             {"tool": "fake_critical_action", "args": {}},
             {"tool": "get_time", "args": {}}]
    _plan_result(brain, steps)
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            cancelled_plan = service.execute_command("plano crítico")
            service.deny_confirmation(cancelled_plan["token"])
            approved_plan = service.execute_command("plano crítico")
            approved = service.confirm(approved_plan["token"])
    finally:
        brain.close()
        service.close()
    assert cancelled_plan["plan_paused"] is True
    assert calls["critical"] == 1
    assert calls["post"] == 0
    assert approved["ok"] is True


def test_synthesis_failure_keeps_successful_results_and_readable_fallback():
    service, brain = _service_and_brain()
    _replace(service, "system_status", lambda: {
        "ok": True, "message": "CPU 21%", "verified": True})
    _plan_result(brain, [{"tool": "system_status", "args": {}}])
    brain.synthesize_tool_results = lambda command, results: {
        "ok": False, "error": "provider offline", "provider": "mock"}
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command("resuma o status")
    finally:
        brain.close()
        service.close()
    assert result["ok"] is True
    assert result["synthesis_fallback"] is True
    assert "CPU 21%" in result["message"]
    assert len(result["executions"]) == 1


def test_duplicate_gateway_request_does_not_repeat_multi_tool_plan():
    service, brain = _service_and_brain()
    calls = {"count": 0}
    _replace(service, "system_status", lambda: calls.__setitem__("count", calls["count"] + 1)
             or {"ok": True, "message": "ok", "verified": True})
    _plan_result(brain, [{"tool": "system_status", "args": {}}])
    brain.synthesize_tool_results = lambda command, results: {
        "ok": True, "response": "feito", "provider": "mock"}
    gateway = Gateway(service)
    ws = AsyncMock()
    ws.send_str = AsyncMock()
    session = gateway.sessions.create()
    message = GatewayMessage(type=MessageType.COMMAND, id="multi-duplicate",
                             session_id=session.session_id,
                             payload={"command": "diagnóstico"})

    async def run_twice():
        await gateway._handle_message(ws, message.to_json(), session, True, "127.0.0.1")
        await gateway._handle_message(ws, message.to_json(), session, True, "127.0.0.1")

    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            asyncio.run(run_twice())
    finally:
        brain.close()
        service.close()
    assert calls["count"] == 1


def test_plan_step_limit_is_fail_closed():
    service, brain = _service_and_brain()
    calls = {"count": 0}
    _replace(service, "get_time", lambda: calls.__setitem__("count", calls["count"] + 1)
             or {"ok": True, "verified": True})
    _plan_result(brain, [{"tool": "get_time", "args": {}}] * 6)
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command("muitas etapas")
    finally:
        brain.close()
        service.close()
    assert result["ok"] is False
    assert calls["count"] == 0
    assert "5" in result["error"]


def test_final_synthesis_cannot_return_an_executable_plan_and_keeps_secret_local_policy():
    service, brain = _service_and_brain()
    captured = {}
    brain.orchestrator.last_decision = SimpleNamespace(
        preferred_model_profile=ModelProfile.GENERAL,
        data_classification=DataClassification.SECRET,
    )
    brain.orchestrator.models.providers = {"local": object()}

    def execute(messages, profile, classification):
        captured["messages"] = messages
        captured["classification"] = classification
        return SimpleNamespace(ok=True, output='{"tool":"get_time","args":{}}',
                               provider="local", model="mock", fallback_used=False,
                               latency_ms=1, error="")

    brain.orchestrator.models.execute = execute
    try:
        result = brain.synthesize_tool_results(
            "segredo", [{"tool": "system_status", "ok": True, "result": {}}])
    finally:
        brain.close()
        service.close()
    assert result["ok"] is False
    assert captured["classification"] == DataClassification.SECRET
    assert "FINAL_SYNTHESIS" in captured["messages"][0]["content"]
