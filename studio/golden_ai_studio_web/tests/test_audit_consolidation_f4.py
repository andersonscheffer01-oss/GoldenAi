from dataclasses import replace
import json
from pathlib import Path

from jarvis_core.audit import AuditLog
from jarvis_core.security_compatibility import LegacySecurityBridge
from jarvis_core.service import JarvisService


def test_migrated_legacy_action_has_one_canonical_receipt(tmp_path):
    service = JarvisService(tmp_path)
    calls = []
    tool = service.registry.get("open_file")
    service.registry._tools["open_file"] = replace(
        tool,
        handler=lambda path: calls.append(path) or {"ok": True, "verified": True},
    )
    try:
        result = LegacySecurityBridge(lambda: service).execute(
            {"tool": "open_file", "path": "read-only.txt"}, "audit-session")
        receipts = [row for row in service.audit.recent(50) if row["tool"] == "open_file"]

        assert result["ok"] is True
        assert calls == ["read-only.txt"]
        execution_receipts = [row for row in receipts if row["status"] == "executado"]
        assert len(execution_receipts) == 1
        assert execution_receipts[0]["status"] == "executado"
        assert any(row.get("audit_envelope", {}).get("status") == "ALLOW"
                   for row in receipts)
    finally:
        service.close()


def test_canonical_audit_redacts_sensitive_values(tmp_path):
    audit = AuditLog(tmp_path / "golden_runtime.db")
    audit.add(
        task_id="audit-test",
        command="test",
        tool="fixture",
        arguments={"api_key": "secret-value", "nested": {"token": "token-value"}},
        result={"authorization": "Bearer secret-value"},
        status="completed",
    )

    row = audit.recent(1)[0]
    serialized = json.dumps(row, ensure_ascii=False)
    assert "secret-value" not in serialized
    assert "token-value" not in serialized
    assert "REDACTED" in serialized


def test_confirmation_receipt_and_execution_are_not_duplicated(tmp_path):
    service = JarvisService(tmp_path)
    calls = []
    tool = service.registry.get("delete_file")
    service.registry._tools["delete_file"] = replace(
        tool,
        handler=lambda path: calls.append(path) or {"ok": True, "verified": True},
    )
    try:
        requested = LegacySecurityBridge(lambda: service).execute(
            {"tool": "delete_file", "path": "target.txt"}, "audit-session")
        token = requested["token"]
        approved = service.confirm(token, task_id="audit-session")
        duplicate = service.confirm(token, task_id="audit-session")
        receipts = [row for row in service.audit.recent(50) if row["tool"] == "delete_file"]

        assert requested["confirmation_required"] is True
        assert approved["ok"] is True
        assert duplicate["ok"] is False
        assert calls == [str(Path("target.txt").resolve())]
        assert len([row for row in receipts if row["status"] == "executado"]) == 1
    finally:
        service.close()
