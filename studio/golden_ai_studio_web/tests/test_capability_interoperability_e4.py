import sys
from pathlib import Path

import pytest

from jarvis_core.mcp_client import McpClientManager, McpServerConfig
from jarvis_core.models import Tool
from jarvis_core.service import JarvisService


FIXTURE = Path(__file__).parent / "fixtures" / "mcp_stdio_server.py"


def _config(tmp_path):
    return McpServerConfig(
        "interop", "Interop Fixture", (sys.executable, str(FIXTURE), "normal"),
        cwd=str(tmp_path), request_timeout=2.0,
    )


def test_common_discovery_and_internal_provider_priority(tmp_path):
    service = JarvisService(tmp_path / "runtime")
    manager = McpClientManager()
    try:
        manager.register_server(_config(tmp_path))
        manager.start("interop")
        names = manager.register_tools(service, "interop", read_only_tools={"read_echo"})
        assert service.registry.get("get_time") is not None
        assert service.registry.get(names[0]).provider == "mcp:interop"

        local = Tool(
            "local_read_echo", "Internal echo", lambda: {"ok": True},
            capability_name="read_echo", priority=0,
        )
        service.registry.register(local)
        assert service.registry.resolve_capability("read_echo") is local
        assert service.registry.resolve_capability("read_echo", "mcp:interop").name == names[0]
    finally:
        manager.close()
        service.close()


def test_collision_is_fail_closed_and_mcp_provenance_is_preserved(tmp_path):
    service = JarvisService(tmp_path / "runtime")
    manager = McpClientManager()
    try:
        manager.register_server(_config(tmp_path))
        manager.start("interop")
        names = manager.register_tools(service, "interop", read_only_tools={"read_echo"})
        with pytest.raises(ValueError):
            service.registry.register(Tool(names[0], "collision", lambda: {"ok": True}))
        result = service.execute_tool(names[0], {"message": "provenance"}, task_id="e4")
        assert result["ok"] is True
        assert result["provider"] == "mcp:interop"
        assert result["server_id"] == "interop"
        assert "memory_id" not in result
    finally:
        manager.close()
        service.close()


def test_unhealthy_mcp_provider_is_not_executable(tmp_path):
    marker = tmp_path / "marker.txt"
    service = JarvisService(tmp_path / "runtime")
    manager = McpClientManager()
    try:
        config = McpServerConfig(
            "health", "Health Fixture", (sys.executable, str(FIXTURE), "normal", str(marker)),
            cwd=str(tmp_path), request_timeout=2.0,
        )
        manager.register_server(config)
        manager.start("health")
        names = manager.register_tools(service, "health")
        manager.stop("health")
        descriptor = service.registry.capability_descriptor(service.registry.get(names[1]))
        assert descriptor["availability"] == "unavailable"
        result = service.execute_tool(names[1], {"value": "must-not-run"}, task_id="e4")
        assert result["ok"] is False
        assert "indisponível" in result["error"]
        assert not marker.exists()
    finally:
        manager.close()
        service.close()
