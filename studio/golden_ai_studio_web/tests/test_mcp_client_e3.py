import sys
import threading
from pathlib import Path

import pytest

from jarvis_core.mcp_client import (McpCancelled, McpClientError, McpClientManager,
                                     McpServerConfig)
from jarvis_core.service import JarvisService


FIXTURE = Path(__file__).parent / "fixtures" / "mcp_stdio_server.py"


def config(tmp_path, mode="normal", marker=None, timeout=2.0, server_id="fixture"):
    command = [sys.executable, str(FIXTURE), mode]
    if marker:
        command.append(str(marker))
    return McpServerConfig(server_id, "Controlled Fixture", tuple(command),
                           cwd=str(tmp_path), request_timeout=timeout)


def test_explicit_stdio_lifecycle_discovery_and_health(tmp_path):
    manager = McpClientManager()
    client = manager.register_server(config(tmp_path))
    try:
        health = manager.start("fixture")
        assert health["health"] == "healthy"
        tools = manager.list_tools("fixture")
        assert [tool.namespaced_name for tool in tools] == [
            "mcp:fixture:read_echo", "mcp:fixture:write_like"
        ]
        assert manager.health()[0]["server_info"]["name"] == "golden-test-mcp"
    finally:
        manager.close()
    assert client.process is None


def test_schema_validation_rejects_malformed_provider_and_isolates_failure(tmp_path):
    manager = McpClientManager()
    manager.register_server(config(tmp_path, mode="malformed"))
    try:
        manager.start("fixture")
        with pytest.raises(McpClientError, match="invalid tool bad.type"):
            manager.list_tools("fixture")
        assert manager.health()[0]["health"] == "degraded"
    finally:
        manager.close()
    assert manager.health()[0]["running"] is False


def test_timeout_cancellation_and_crash_leave_no_owned_process(tmp_path):
    manager = McpClientManager()
    client = manager.register_server(config(tmp_path, mode="slow", timeout=0.15))
    try:
        manager.start("fixture")
        descriptor = manager.list_tools("fixture")[0]
        with pytest.raises(McpClientError, match="timed out"):
            client._call_tool(descriptor, {"message": "slow"})
        assert client.process is None
    finally:
        manager.close()

    manager = McpClientManager()
    client = manager.register_server(config(tmp_path, mode="normal", timeout=2.0,
                                            server_id="cancelled"))
    try:
        manager.start("cancelled")
        descriptor = manager.list_tools("cancelled")[0]
        event = threading.Event()
        event.set()
        with pytest.raises(McpCancelled):
            client._call_tool(descriptor, {"message": "cancel"}, event)
        assert client.process is None
    finally:
        manager.close()


def test_imported_tools_use_canonical_security_and_audit(tmp_path):
    marker = tmp_path / "mcp-marker.txt"
    manager = McpClientManager()
    manager.register_server(config(tmp_path, marker=marker))
    service = JarvisService(tmp_path / "runtime")
    try:
        manager.start("fixture")
        registered = manager.get("fixture")
        names = manager.register_tools(service, "fixture", read_only_tools={"read_echo"})
        assert names == ["mcp:fixture:read_echo", "mcp:fixture:write_like"]

        read = service.execute_tool(names[0], {"message": "hello"}, task_id="mcp-e3")
        assert read["ok"] is True
        assert read["provider"] == "mcp:fixture"

        protected = service.execute_tool(names[1], {"value": "blocked"}, task_id="mcp-e3")
        assert protected["confirmation_required"] is True
        assert not marker.exists()
        completed = service.confirm(protected["token"], task_id="mcp-e3")
        assert completed["ok"] is True
        assert marker.read_text(encoding="utf-8") == "blocked"

        receipts = [row for row in service.audit.recent(20)
                    if row["task_id"] == "mcp-e3"]
        assert len([row for row in receipts if row["status"] == "executado"]) == 2
    finally:
        manager.close()
        service.close()


def test_unapproved_server_is_never_started(tmp_path):
    manager = McpClientManager()
    manager.register_server(McpServerConfig(
        "untrusted", "Untrusted", (sys.executable, str(FIXTURE), "normal"),
        cwd=str(tmp_path), trust_state="untrusted"))
    with pytest.raises(McpClientError, match="not explicitly approved"):
        manager.start("untrusted")
