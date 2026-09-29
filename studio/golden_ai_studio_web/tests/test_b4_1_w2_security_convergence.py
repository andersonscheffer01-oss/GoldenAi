"""B4.1 Wave 2 security convergence tests.

Only temporary storage and deterministic read/approval fixtures are used.
These tests never invoke providers, MT5, desktop hardware, or executors.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

GOLDEN_ROOT = Path(__file__).resolve().parents[3]
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
for _path in (GOLDEN_ROOT, STUDIO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.execution import ExecutionService, RiskLevel
from core.config import GoldenAISettings
from core.permissions import PermissionManager
from jarvis_core.models import Risk, Tool
from jarvis_core.security import SecurityManager
from jarvis_core.security_compatibility import ExecutionSecurityFacade


def _tool(name="fixture_read", risk=Risk.HIGH):
    return Tool(name, "Deterministic fixture", lambda **_: {"ok": True},
                risk=risk, confirmation=True)


def test_confirmation_rejects_action_or_target_mismatch_without_consuming():
    security = SecurityManager(confirmation_ttl=60)
    tool = _tool()
    token = security.create_confirmation(tool, {"path": "target-a"}, "fixture")

    assert security.consume(token, expected_tool="other_tool",
                            expected_arguments={"path": "target-a"}) is None
    assert token in security.pending
    assert security.consume(token, expected_tool=tool.name,
                            expected_arguments={"path": "target-b"}) is None
    assert token in security.pending
    assert security.consume(token, expected_tool=tool.name,
                            expected_arguments={"path": "target-a"}) is not None
    assert security.consume(token) is None


def test_confirmation_tampering_fails_closed_and_invalidates_token():
    security = SecurityManager(confirmation_ttl=60)
    token = security.create_confirmation(_tool(), {"path": "target-a"}, "fixture")
    security.pending[token]["arguments"] = {"path": "target-b"}

    assert security.consume(token) is None
    assert token not in security.pending


def test_execution_service_delegates_safe_read_exactly_once(tmp_path):
    class SpyFacade:
        def __init__(self):
            self.calls = []

        def authorize(self, **kwargs):
            self.calls.append(kwargs)
            return {"allowed": True, "status": "COMPLETED",
                    "reason": "fixture canonical allow"}

    spy = SpyFacade()
    service = ExecutionService(tmp_path)
    service.security_facade = spy
    result = service.authorize_action(
        "fixture-task", "READ", "read_file", "fixture-target",
        reason="safe fixture", risk_level=RiskLevel.LOW)

    assert result.allowed is True
    assert len(spy.calls) == 1
    assert spy.calls[0]["action"] == "read_file"
    assert spy.calls[0]["target"] == "fixture-target"


def test_canonical_read_deny_does_not_fall_back_to_legacy_allow(tmp_path):
    security = SecurityManager({"legacy_read": "deny"})
    service = ExecutionService(tmp_path)
    service.security_facade = ExecutionSecurityFacade(security)

    result = service.authorize_action(
        "fixture-task", "READ", "read_file", "fixture-target",
        risk_level=RiskLevel.LOW)

    assert result.allowed is False
    assert result.status == "BLOCKED"
    assert "SecurityManager" in result.reason


def test_high_risk_scope_is_not_migrated_through_read_facade(tmp_path):
    class SpyFacade:
        def authorize(self, **_kwargs):
            raise AssertionError("high-risk scope must remain frozen")

    service = ExecutionService(tmp_path)
    service.security_facade = SpyFacade()
    result = service.authorize_action(
        "fixture-task", "READ", "read_file", "fixture-target",
        risk_level=RiskLevel.HIGH)

    assert result.allowed is False
    assert result.status == "BLOCKED"


def test_permission_manager_keeps_path_policy_before_canonical_read(tmp_path):
    projects = tmp_path / "projetos"
    projects.mkdir()
    settings = GoldenAISettings(
        root=tmp_path, projects_dir=projects, data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs", allowed_paths=(projects,),
        protected_paths=(tmp_path / "protected",), read_only=False,
        write_enabled=True)
    manager = PermissionManager(settings)
    manager.execution.security_facade = ExecutionSecurityFacade(SecurityManager())

    assert manager.can_read(projects / "fixture.txt").allowed is True
    assert manager.can_read(tmp_path / "outside.txt").allowed is False


def test_task_manager_confirmation_calls_are_bound_at_consume():
    source = (STUDIO_ROOT / "jarvis_core" / "task_manager" / "manager.py").read_text(
        encoding="utf-8")
    assert source.count("expected_tool=tool.name") == 3
    assert source.count("expected_arguments=arguments") == 3


def test_wave_two_scope_does_not_add_an_executor_or_touch_trading():
    execution = (GOLDEN_ROOT / "core" / "execution" / "service.py").read_text(
        encoding="utf-8")
    adapter = (STUDIO_ROOT / "jarvis_core" / "security_compatibility.py").read_text(
        encoding="utf-8")
    adapter_scope = adapter.split("class LegacySecurityBridge", 1)[0]
    assert "def execute" not in adapter_scope
    assert "def dispatch" not in execution
    assert "mt5" not in adapter_scope.casefold()
    assert "order_send" not in adapter_scope.casefold()
