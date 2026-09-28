import sys
from dataclasses import replace
from pathlib import Path

from jarvis_core.mcp_client import McpServerConfig
from jarvis_core.service import JarvisService


FIXTURE = Path(__file__).parent / "fixtures" / "mcp_stdio_server.py"


def test_control_center_read_model_is_secret_free(tmp_path):
    service = JarvisService(tmp_path)
    try:
        snapshot = service.capability_governance_snapshot()
        names = {item["name"] for item in snapshot["capabilities"]}
        assert "get_time" in names
        assert snapshot["mcp_servers"] == []
        serialized = repr(snapshot).lower()
        assert "api_key" not in serialized
        assert "password" not in serialized
        assert "token" not in serialized
    finally:
        service.close()


def test_capability_disable_blocks_future_execution_without_deleting_history(tmp_path):
    service = JarvisService(tmp_path)
    calls = []
    original = service.registry.get("get_time")
    service.registry._tools["get_time"] = replace(
        original, handler=lambda: calls.append("called") or {"ok": True, "verified": True}
    )
    try:
        assert service.set_capability_enabled("get_time", False)["ok"] is True
        blocked = service.execute_tool("get_time", {}, task_id="e5")
        assert blocked["ok"] is False
        assert "desabilitada" in blocked["error"]
        assert calls == []
        descriptor = next(item for item in service.capability_governance_snapshot()["capabilities"]
                          if item["name"] == "get_time")
        assert descriptor["availability"] == "disabled"
        assert service.set_capability_enabled("get_time", True)["enabled"] is True
        assert service.execute_tool("get_time", {}, task_id="e5")["ok"] is True
        assert calls == ["called"]
    finally:
        service.close()


def test_mcp_server_governance_enable_disable_is_explicit(tmp_path):
    service = JarvisService(tmp_path / "runtime")
    config = McpServerConfig(
        "governed", "Governed Fixture", (sys.executable, str(FIXTURE), "normal"),
        cwd=str(tmp_path), environment={"TEST_SECRET": "must-not-leak"},
    )
    try:
        service.mcp_clients.register_server(config)
        service.mcp_clients.start("governed")
        names = service.mcp_clients.register_tools(
            service, "governed", read_only_tools={"read_echo"})
        before = service.capability_governance_snapshot()
        assert before["mcp_servers"][0]["enabled"] is True
        assert before["mcp_servers"][0]["running"] is True
        assert "TEST_SECRET" not in repr(before)

        disabled = service.set_mcp_server_enabled("governed", False)
        assert disabled["ok"] is True
        assert disabled["server"]["enabled"] is False
        descriptor = service.registry.capability_descriptor(service.registry.get(names[0]))
        assert descriptor["availability"] == "unavailable"
    finally:
        service.close()
