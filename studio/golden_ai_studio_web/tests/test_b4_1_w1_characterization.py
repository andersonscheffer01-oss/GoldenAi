"""B4.1 Wave 1 characterization tests.

These tests intentionally capture current behavior. They use temporary
storage, harmless fixtures, and static source inspection only. They are not an
endorsement of legacy semantics and must not be changed into convergence code.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import sys
from pathlib import Path

import pytest

GOLDEN_ROOT = Path(__file__).resolve().parents[3]
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
for _path in (GOLDEN_ROOT, STUDIO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.audit import AuditEvent, AuditLogger
from core.config import GoldenAISettings
from core.execution import ExecutionService, PermissionMode, RiskLevel
from core.permissions import PermissionManager
from jarvis_core.audit import AuditLog
from jarvis_core.models import Risk, Tool
from jarvis_core.registry import ToolRegistry
from jarvis_core.runtime_ownership import describe_task_database
from jarvis_core.security import SecurityManager


def _source(relative: str) -> str:
    return (GOLDEN_ROOT / relative).read_text(encoding="utf-8")


@pytest.fixture
def permission_manager(tmp_path: Path) -> PermissionManager:
    projects = tmp_path / "projetos"
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    protected = tmp_path / "protected"
    projects.mkdir()
    data.mkdir()
    logs.mkdir()
    settings = GoldenAISettings(
        root=tmp_path,
        projects_dir=projects,
        data_dir=data,
        logs_dir=logs,
        allowed_paths=(projects, data, logs),
        protected_paths=(protected,),
        read_only=False,
        write_enabled=True,
        command_execution_enabled=True,
    )
    return PermissionManager(settings)


def _fixture_tool(name: str = "fixture_action", risk: Risk = Risk.HIGH) -> Tool:
    return Tool(name, "Harmless characterization fixture", lambda **_: {"ok": True},
                risk, confirmation=True)


def test_permission_manager_method_inventory_and_path_semantics(
    permission_manager: PermissionManager, tmp_path: Path
):
    methods = {name for name, value in inspect.getmembers(PermissionManager, inspect.isfunction)}
    expected = {
        "is_read_only", "is_protected_dir", "can_read", "can_write",
        "can_execute_command", "can_read_external_safe", "can_launch_allowed_app",
        "can_open_folder", "can_write_approved_coding_task", "can_internet_search",
        "can_internet_fetch", "can_internet_download", "can_execute_downloaded_file",
    }
    assert expected <= methods

    allowed = tmp_path / "projetos" / "fixture.txt"
    outside = tmp_path / "outside.txt"
    assert permission_manager.can_read(allowed).allowed is True
    assert permission_manager.can_read(outside).allowed is False
    assert permission_manager.can_write(tmp_path / "protected" / "x.txt").allowed is False


def test_permission_manager_approval_delegates_to_persistent_execution_service(
    permission_manager: PermissionManager, tmp_path: Path
):
    target = tmp_path / "projetos" / "fixture.txt"
    permission_manager.execution.set_mode(PermissionMode.ASK)

    pending = permission_manager.can_write(target)
    assert pending.allowed is False
    request = permission_manager.execution.latest_requests(1)[0]
    assert request["task_id"] == "permission-manager"
    assert request["target"] == str(target.resolve())
    assert request["scope"] == ""
    assert request["consumed"] == 0

    permission_manager.execution.grant_once(request["request_id"])
    assert permission_manager.can_write(target).allowed is True
    assert permission_manager.can_write(target).allowed is False


def test_execution_service_approval_is_target_and_action_bound_without_expiry(
    tmp_path: Path,
):
    service = ExecutionService(tmp_path)
    service.set_mode(PermissionMode.ASK)
    first = service.authorize_action(
        "task-a", "WRITE", "edit", "target-a", risk_level=RiskLevel.MEDIUM
    )
    service.grant_for_task(first.request_id)
    same_target = service.authorize_action(
        "task-a", "WRITE", "edit", "target-a", risk_level=RiskLevel.MEDIUM
    )
    other_target = service.authorize_action(
        "task-a", "WRITE", "edit", "target-b", risk_level=RiskLevel.MEDIUM
    )
    other_task = service.authorize_action(
        "task-b", "WRITE", "edit", "target-a", risk_level=RiskLevel.MEDIUM
    )

    assert same_target.allowed is True
    assert other_target.status == "WAITING_APPROVAL"
    assert other_task.status == "WAITING_APPROVAL"
    assert "expires" not in type(first).__dataclass_fields__


def test_execution_service_fail_closed_and_unknown_action_behavior(tmp_path: Path):
    service = ExecutionService(tmp_path)
    service.set_mode(PermissionMode.FULL)
    critical = service.authorize_action(
        "task", "CRITICAL", "unknown_trade_fixture", "fixture",
        risk_level=RiskLevel.CRITICAL,
    )
    missing_capability = service.authorize_action(
        "task", "EXECUTE", "unknown_action", "fixture",
        risk_level=RiskLevel.HIGH, capability_exists=False,
    )
    assert critical.status == "BLOCKED"
    assert critical.allowed is False
    assert missing_capability.status == "BLOCKED"
    assert missing_capability.allowed is False
    assert not hasattr(service, "execute")
    assert not hasattr(service, "dispatch")


def test_security_manager_approval_shape_and_single_use():
    security = SecurityManager(confirmation_ttl=60)
    tool = _fixture_tool()
    assert security.decision(tool) == "confirm"
    token = security.create_confirmation(tool, {"target": "a"}, "fixture")
    item = security.pending[token]

    assert {"tool", "arguments", "command", "created_at", "risk", "signature", "expires"} <= set(item)
    assert "task_id" not in item
    assert "user_id" not in item
    assert "mission_id" not in item
    assert "session_id" not in item
    item["arguments"] = {"target": "changed-after-request"}
    consumed = security.consume(token)
    assert consumed is None
    assert security.consume(token) is None


def test_security_manager_expiry_invalid_token_and_rule_precedence():
    security = SecurityManager({"fixture_action": "deny"})
    tool = _fixture_tool()
    assert security.decision(tool) == "deny"
    token = security.create_confirmation(tool, {}, "fixture")
    security.pending[token]["expires"] = 0
    assert security.consume(token) is None
    assert security.consume("invalid-token") is None


def test_tool_registry_fixture_is_security_neutral_until_service_decides():
    registry = ToolRegistry()
    tool = _fixture_tool("registry_fixture", Risk.HIGH)
    registry.register(tool)
    assert registry.get("registry_fixture") is tool
    assert registry.get("missing_fixture") is None
    assert SecurityManager().decision(tool) == "confirm"


def test_auditlogger_schema_and_defaults_are_observable_in_temp_storage(tmp_path: Path):
    logger = AuditLogger(tmp_path / "logs")
    event = AuditEvent(
        action_type="CHARACTERIZATION_ONLY",
        status="COMPLETED",
        target="temporary-fixture",
        input_summary="fixture-token-value",
    )
    path = logger.record(event)
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    assert {
        "action_type", "status", "target", "action_id", "session_id", "agent",
        "input_summary", "result", "error", "duration_ms", "files_changed",
        "commands_executed", "timestamp",
    } <= set(row)
    assert row["action_id"]
    assert row["timestamp"]
    assert row["input_summary"] == "fixture-token-value"


def test_auditlog_schema_redaction_and_recent_are_canonical(tmp_path: Path):
    audit = AuditLog(tmp_path / "golden_runtime.db")
    audit.add(
        task_id="fixture-task",
        command="characterization",
        tool="fixture",
        arguments={"api_key": "fixture-secret", "nested": {"token": "fixture-token"}},
        result={"authorization": "Bearer fixture-secret"},
        risk="LOW",
        status="completed",
        elapsed_ms=1,
    )
    with sqlite3.connect(tmp_path / "golden_runtime.db") as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(jarvis_audit)")}
    assert {"id", "timestamp", "task_id", "command", "tool", "arguments", "risk",
            "status", "result", "elapsed_ms"} <= columns
    row = audit.recent(1)[0]
    serialized = json.dumps(row, ensure_ascii=False)
    assert "fixture-secret" not in serialized
    assert "fixture-token" not in serialized
    assert "REDACTED" in serialized


def test_correlations_are_mapped_without_introducing_a_new_scheme():
    server = _source("studio/golden_ai_studio_web/server_agent.py")
    service = _source("studio/golden_ai_studio_web/jarvis_core/service.py")
    execution = _source("core/execution/service.py")
    legacy_audit = _source("core/audit/logger.py")
    audit = _source("studio/golden_ai_studio_web/jarvis_core/audit.py")
    combined = "\n".join((server, service, execution, legacy_audit, audit))

    assert "session_id" in combined
    assert "conversation_id" in combined
    assert "task_id" in combined
    assert "request_id" in combined
    assert "action_id" in combined
    assert "run_id" in combined
    assert "mission_id" in combined
    assert "correlation_id" in audit
    assert "response_id" not in audit


def test_http_gateway_sse_and_route_reachability_are_source_characterized():
    server = _source("studio/golden_ai_studio_web/server_agent.py")
    dashboard = _source("studio/golden_ai_studio_web/dashboard.html")
    jarvis_ui = _source("studio/golden_ai_studio_web/jarvis_ui/src/app.js")
    market = _source("studio/golden_ai_studio_web/ai_radar.js")
    desktop_center = _source("studio/golden_ai_studio_web/desktop_center.js")
    studio = _source("studio/golden_ai_studio_web/studio_v7.html")
    gateway = _source("studio/golden_ai_studio_web/jarvis_ui/src/gateway-adapter.js")
    gateway_start = _source("studio/golden_ai_studio_web/server_agent.py")

    for route in ("/api/jarvis/chat", "/api/jarvis/golden/overview", "/api/market/analyze"):
        assert route in server
    assert "/api/jarvis/chat" in dashboard
    assert "/api/jarvis/golden/overview" in jarvis_ui
    assert "/api/market/analyze" in market
    assert "/api/jarvis/chat" in desktop_center

    assert "/api/chat" in studio
    assert "/api/agent" in studio
    assert "/stream/chat" in studio
    assert "/api/mt5/auto_trade" in dashboard
    assert "/api/mt5/close_position" in dashboard
    assert "/api/mt5/import_history" in dashboard

    for method, next_method, expected_gate in (
        ("_api_mt5_compile", "_api_mt5_backtest", True),
        ("_api_mt5_backtest", "_api_mt5_analyze_robot", False),
        ("_api_mt5_real_backtest", "_api_mt5_chart_analysis", True),
        ("_api_mt5_auto_trade", "_api_strategy_catalog", True),
        ("_api_mt5_close_position", "_api_position_manager_status", True),
    ):
        section = server[server.index("    def " + method):server.index("    def " + next_method)]
        assert ("_authorize_api_mutation" in section) is expected_gate

    assert ":8766/ws" in gateway
    assert "hello" in gateway and "auth" in gateway
    assert "8766" in gateway_start and "/ws" in gateway_start
    assert "text/event-stream" in server
    assert "Access-Control-Allow-Origin', '*'" in server

    options = server[server.index("    def do_OPTIONS"):server.index("    def log_message")]
    handle_api = server[server.index("    def handle_api"):server.index("    def handle_stream")]
    assert "Authorization" not in options
    assert "Authorization" not in handle_api


def test_provider_bypass_and_memory_task_current_boundaries_are_static_findings():
    server = _source("studio/golden_ai_studio_web/server_agent.py")
    service = _source("studio/golden_ai_studio_web/jarvis_core/service.py")
    boundary = _source("studio/golden_ai_studio_web/jarvis_core/memory/boundary.py")
    task_manager = _source("studio/golden_ai_studio_web/jarvis_core/task_manager/manager.py")

    for provider_marker in (
        "def call_groq_model", "def call_gemini_model", "ollama_chat",
        "get_cline_provider", "get_claude_provider",
    ):
        assert provider_marker in server
    assert "self.memory_boundary.remember" in service
    assert "class CanonicalMemoryBoundary" in boundary
    assert "class TaskManager" in task_manager
    assert "golden_tasks.db" in task_manager


def test_task_database_diagnostic_is_read_only_and_explicit(tmp_path: Path):
    candidate = tmp_path / "candidate.db"
    report = describe_task_database(candidate, caller="characterization")
    assert report["status"] == "NONCANONICAL"
    assert report["finding"] == "NONCANONICAL_TASK_DB_RESOLUTION"
    assert report["caller"] == "characterization"
    assert not candidate.exists()
