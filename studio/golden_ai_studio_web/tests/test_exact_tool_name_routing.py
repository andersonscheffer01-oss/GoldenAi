"""Exact tool-name routing must avoid LLM without bypassing security."""

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.gateway.gateway import Gateway
from jarvis_core.gateway.protocol import GatewayMessage, MessageType
from jarvis_core.service import JarvisService


ROOT = Path(__file__).resolve().parent.parent


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _service():
    return JarvisService(ROOT)


def _replace_handler(service, name, handler):
    tool = service.registry.get(name)
    service.registry._tools[name] = replace(tool, handler=handler)


def test_system_status_exact_tool_name_skips_llm_and_executes_once():
    service = _service()
    calls = {"count": 0}

    def handler():
        calls["count"] += 1
        return {"ok": True, "message": "status ok", "verified": True}

    _replace_handler(service, "system_status", handler)
    try:
        with patch("jarvis_core.brain.get_brain",
                   side_effect=AssertionError("LLM_CALLED")):
            result = service.execute_command("system_status")
    finally:
        service.close()

    assert result["ok"] is True
    assert result["tool"] == "system_status"
    assert calls["count"] == 1


def test_memory_recent_exact_tool_name_skips_llm():
    service = _service()
    calls = {"count": 0}

    def handler(limit=10, namespace="jarvis"):
        calls["count"] += 1
        return {"ok": True, "items": [], "count": 0, "verified": True}

    _replace_handler(service, "memory_recent", handler)
    try:
        with patch("jarvis_core.brain.get_brain",
                   side_effect=AssertionError("LLM_CALLED")):
            result = service.execute_command("memory_recent")
    finally:
        service.close()

    assert result["ok"] is True
    assert result["tool"] == "memory_recent"
    assert calls["count"] == 1


def test_browser_health_exact_tool_name_skips_llm():
    service = _service()
    calls = {"count": 0}

    def handler():
        calls["count"] += 1
        return {"ok": True, "started": False, "verified": True}

    _replace_handler(service, "browser_health", handler)
    try:
        with patch("jarvis_core.brain.get_brain",
                   side_effect=AssertionError("LLM_CALLED")):
            result = service.execute_command("browser_health")
    finally:
        service.close()

    assert result["ok"] is True
    assert result["tool"] == "browser_health"
    assert calls["count"] == 1


def test_natural_language_with_tool_name_does_not_exact_route():
    service = _service()
    brain = MagicMock()
    brain.last_llm = {"provider": "mock", "model": "mock"}
    brain.interpret.return_value = {
        "ok": True,
        "plan": {"response": "system_status é uma ferramenta de status."},
    }
    try:
        with patch("jarvis_core.brain.get_brain", return_value=brain):
            result = service.execute_command("me explique system_status")
    finally:
        service.close()

    assert result["ok"] is True
    assert "system_status" in result["message"]
    brain.interpret.assert_called_once()


def test_required_args_missing_returns_clarification_without_execution_or_llm():
    service = _service()
    calls = {"count": 0}

    def handler(name):
        calls["count"] += 1
        return {"ok": True, "message": name}

    _replace_handler(service, "open_program", handler)
    try:
        with patch("jarvis_core.brain.get_brain",
                   side_effect=AssertionError("LLM_CALLED")):
            result = service.execute_command("open_program")
    finally:
        service.close()

    assert result["ok"] is True
    assert result["clarification_required"] is True
    assert result["tool"] == "open_program"
    assert result["message"] == "Qual programa você quer abrir?"
    assert calls["count"] == 0


def test_shutdown_exact_name_requires_confirmation_and_preserves_security_flow():
    service = _service()
    calls = {"count": 0}

    def handler():
        calls["count"] += 1
        return {"ok": True, "message": "fake shutdown", "verified": True}

    _replace_handler(service, "shutdown", handler)
    try:
        with patch("jarvis_core.brain.get_brain",
                   side_effect=AssertionError("LLM_CALLED")):
            result = service.execute_command("shutdown")
        assert result["confirmation_required"] is True
        assert calls["count"] == 0

        denied = service.deny_confirmation(result["token"])
        assert denied["denied"] is True
        assert calls["count"] == 0

        approved_result = service.execute_command("shutdown")
        confirmed = service.confirm(approved_result["token"])
        assert confirmed["ok"] is True
        assert calls["count"] == 1
    finally:
        service.close()


def test_gateway_duplicate_retry_same_request_id_not_reexecuted():
    mock_service = MagicMock()
    mock_service.execute_command.return_value = {
        "ok": True,
        "tool": "system_status",
        "message": "status ok",
    }
    gw = Gateway(mock_service)
    ws = AsyncMock()
    ws.send_str = AsyncMock()
    session = gw.sessions.create()
    msg = GatewayMessage(
        type=MessageType.COMMAND,
        id="exact-dup-1",
        session_id=session.session_id,
        payload={"command": "system_status"},
    )

    _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))
    ws.send_str.reset_mock()
    _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

    assert mock_service.execute_command.call_count == 1
    assert ws.send_str.call_count == 2
    ack = json.loads(ws.send_str.call_args_list[0][0][0])
    result = json.loads(ws.send_str.call_args_list[1][0][0])
    assert ack["payload"]["duplicate"] is True
    assert result["payload"]["tool"] == "system_status"
