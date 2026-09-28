from dataclasses import replace

import pytest

from jarvis_core.models import Tool
from jarvis_core.registry import ToolRegistry
from jarvis_core.service import JarvisService


def test_existing_registry_is_the_capability_boundary_and_rejects_duplicates():
    calls = []
    registry = ToolRegistry()
    read = Tool("read_fixture", "Reads fixture", lambda: calls.append("read") or {"ok": True})
    registry.register(read)

    with pytest.raises(ValueError):
        registry.register(read)

    descriptor = registry.capability_descriptor(read)
    assert descriptor["id"] == "read_fixture"
    assert descriptor["provider"] == "jarvis_core"
    assert descriptor["side_effect_class"] == "READ_ONLY"
    assert descriptor["input_schema"]["additionalProperties"] is False
    assert calls == []


def test_skill_router_and_public_catalog_use_the_same_registry(tmp_path):
    service = JarvisService(tmp_path)
    try:
        assert service.orchestrator.skills.get("system") is not None
        catalog = service.registry.public_catalog()
        status = next(item for item in catalog if item["name"] == "get_time")
        mutation = next(item for item in catalog if item["name"] == "delete_file")
        assert status["side_effect_class"] == "READ_ONLY"
        assert mutation["side_effect_class"] in {"LOCAL_MUTATION", "SENSITIVE_OPERATION"}
        assert all(item["provider"] == "jarvis_core" for item in catalog)
    finally:
        service.close()


def test_security_and_audit_remain_on_service_execution_boundary(tmp_path):
    service = JarvisService(tmp_path)
    calls = []
    tool = service.registry.get("get_time")
    service.registry._tools["get_time"] = replace(
        tool, handler=lambda: calls.append("once") or {"ok": True, "verified": True}
    )
    try:
        result = service.execute_tool("get_time", {}, command="capability-test", task_id="e2")
        receipts = [row for row in service.audit.recent(20) if row["tool"] == "get_time"]
        assert result["ok"] is True
        assert calls == ["once"]
        assert len(receipts) == 1

        service.security.rules["delete_file"] = "deny"
        protected = service.execute_tool(
            "delete_file", {"path": str(tmp_path / "should-not-delete.txt")}, task_id="e2"
        )
        assert protected["ok"] is False
        assert "bloqueada" in protected["error"]
        assert not (tmp_path / "should-not-delete.txt").exists()
    finally:
        service.close()
