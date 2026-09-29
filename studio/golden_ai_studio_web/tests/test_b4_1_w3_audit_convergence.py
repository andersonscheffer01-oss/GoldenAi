"""B4.1 Wave 3 audit authority and correlation tests.

All cases use temporary SQLite/JSONL locations and deterministic fixtures.
They do not invoke providers, MT5, Strategy Tester, desktop hardware, or
the production server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

GOLDEN_ROOT = Path(__file__).resolve().parents[3]
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
for _path in (GOLDEN_ROOT, STUDIO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.execution import ExecutionService, RiskLevel
from jarvis_core.audit import AuditLog
from jarvis_core.models import Risk, Tool
from jarvis_core.security import SecurityManager
from jarvis_core.security_compatibility import ExecutionSecurityFacade


def _tool(name="fixture_tool", risk=Risk.LOW, confirmation=False):
    return Tool(name, "Deterministic Wave 3 fixture", lambda **_: {"ok": True},
                risk=risk, confirmation=confirmation)


def _context(**overrides):
    context = {
        "request_id": "req-fixture-1",
        "correlation_id": "corr-fixture-1",
        "session_id": "session-fixture-1",
        "conversation_id": "conversation-fixture-1",
        "task_id": "task-fixture-1",
        "surface": "test",
        "operation": "fixture",
        "target": "fixture-target",
        "metadata": {"safe_note": "fixture"},
    }
    context.update(overrides)
    return context


def _envelopes(audit):
    return [row["audit_envelope"] for row in audit.recent(100)
            if row.get("audit_envelope")]


def test_canonical_envelope_round_trip_and_nested_secret_redaction(tmp_path):
    audit = AuditLog(tmp_path / "golden_runtime.db")
    audit.add(
        task_id="task-fixture-1",
        command="fixture",
        tool="fixture_tool",
        arguments={"nested": {"token": "W3-secret-token", "path": "safe.txt"}},
        result={"nested": {"authorization": "W3-secret-auth", "ok": True}},
        status="COMPLETED",
        envelope=_context(
            event_id="event-fixture-1",
            action="FIXTURE_RESULT",
            status="COMPLETED",
            error={"secret": "W3-secret-error"},
            metadata={"token": "W3-secret-metadata"},
        ),
        agent="fixture-agent",
        files_changed=["safe.txt"],
        commands_executed=["fixture-command"],
    )

    row = audit.recent(1)[0]
    envelope = row["audit_envelope"]
    expected = {
        "event_id", "timestamp", "request_id", "correlation_id", "session_id",
        "conversation_id", "task_id", "mission_id", "run_id", "approval_id",
        "surface", "operation", "action", "target", "tool", "provider",
        "model", "risk", "security_decision", "status", "result", "error",
        "elapsed_ms", "runtime_profile", "metadata",
    }
    assert expected <= set(envelope)
    assert envelope["event_id"] == "event-fixture-1"
    assert envelope["metadata"]["agent"] == "fixture-agent"
    assert envelope["metadata"]["files_changed"] == ["safe.txt"]
    assert envelope["metadata"]["commands_executed"] == ["fixture-command"]
    serialized = json.dumps(row, ensure_ascii=False)
    for secret in ("W3-secret-token", "W3-secret-auth", "W3-secret-error",
                   "W3-secret-metadata"):
        assert secret not in serialized
    assert "REDACTED" in serialized


def test_security_allow_and_deny_are_canonical_and_correlated(tmp_path):
    allow_audit = AuditLog(tmp_path / "allow.db")
    allow_security = SecurityManager(audit_log=allow_audit)
    allow_security.decision(_tool(), audit_context=_context())
    allow_event = _envelopes(allow_audit)[0]
    assert allow_event["status"] == "ALLOW"
    assert allow_event["security_decision"] == "ALLOW"
    assert allow_event["request_id"] == "req-fixture-1"
    assert allow_event["correlation_id"] == "corr-fixture-1"

    deny_audit = AuditLog(tmp_path / "deny.db")
    deny_security = SecurityManager({"fixture_tool": "deny"}, audit_log=deny_audit)
    deny_security.decision(_tool(), audit_context=_context())
    deny_event = _envelopes(deny_audit)[0]
    assert deny_event["status"] == "DENY"
    assert deny_event["security_decision"] == "DENY"


def test_approval_create_consume_and_single_use_share_correlation(tmp_path):
    audit = AuditLog(tmp_path / "approval.db")
    security = SecurityManager(audit_log=audit)
    tool = _tool("approval_fixture", Risk.HIGH, confirmation=True)
    context = _context(operation="approval_flow", action="fixture")

    assert security.decision(tool, risk=Risk.HIGH,
                             requires_confirmation=True,
                             audit_context=context) == "confirm"
    token = security.create_confirmation(
        tool, {"target": "fixture-target"}, "fixture-command", Risk.HIGH,
        audit_context=context)
    approval_id = security.pending[token]["approval_id"]
    item = security.consume(
        token, expected_tool=tool.name,
        expected_arguments={"target": "fixture-target"},
        audit_context=context)
    assert item["approval_id"] == approval_id

    events = _envelopes(audit)
    created = next(event for event in events if event["status"] == "APPROVAL_CREATED")
    consumed = next(event for event in events if event["status"] == "APPROVAL_CONSUMED")
    assert created["approval_id"] == approval_id
    assert consumed["approval_id"] == approval_id
    assert created["request_id"] == consumed["request_id"]
    assert security.consume(token, audit_context=context) is None
    assert any(event["status"] == "INVALID_APPROVAL" for event in _envelopes(audit))


def test_mismatch_stale_and_expired_approvals_are_audited(tmp_path):
    audit = AuditLog(tmp_path / "failures.db")
    security = SecurityManager(confirmation_ttl=60, audit_log=audit)
    context = _context(operation="approval_failure")

    mismatch_token = security.create_confirmation(
        _tool("mismatch_fixture", Risk.HIGH, True), {"path": "a"}, "cmd",
        Risk.HIGH, audit_context=context)
    assert security.consume(mismatch_token, expected_tool="mismatch_fixture",
                            expected_arguments={"path": "b"},
                            audit_context=context) is None
    assert mismatch_token in security.pending

    stale_token = security.create_confirmation(
        _tool("stale_fixture", Risk.HIGH, True), {"path": "a"}, "cmd",
        Risk.HIGH, audit_context=context)
    security.pending[stale_token]["signature"] = "tampered"
    assert security.consume(stale_token, audit_context=context) is None

    expired_token = security.create_confirmation(
        _tool("expired_fixture", Risk.HIGH, True), {}, "cmd", Risk.HIGH,
        audit_context=context)
    security.pending[expired_token]["expires"] = 0
    assert security.consume(expired_token, audit_context=context) is None

    statuses = {event["status"] for event in _envelopes(audit)}
    assert "MISMATCH" in statuses
    assert "STALE_TARGET" in statuses
    assert "EXPIRED_APPROVAL" in statuses


def test_migrated_safe_read_has_canonical_authority_without_legacy_jsonl(tmp_path):
    audit = AuditLog(tmp_path / "canonical.db")
    security = SecurityManager(audit_log=audit)
    facade = ExecutionSecurityFacade(security)
    service = ExecutionService(tmp_path)
    service.security_facade = facade

    result = service.authorize_action(
        "read-task", "READ", "read_file", "fixture.txt",
        reason="safe fixture read", risk_level=RiskLevel.LOW)

    assert result.allowed is True
    envelopes = _envelopes(audit)
    assert len(envelopes) >= 1
    assert envelopes[-1]["status"] == "ALLOW"
    assert envelopes[-1]["target"] == "fixture.txt"
    assert envelopes[-1]["task_id"] == "read-task"
    assert not list((tmp_path / "logs").glob("audit_*.jsonl"))


def test_optional_correlation_ids_are_present_but_empty_when_unavailable(tmp_path):
    audit = AuditLog(tmp_path / "optional.db")
    audit.add(envelope={"surface": "fixture", "action": "OPTIONAL_IDS"},
              result={"ok": True}, status="COMPLETED")
    envelope = _envelopes(audit)[0]
    assert envelope["request_id"] == ""
    assert envelope["correlation_id"] == ""
    assert envelope["approval_id"] == ""
