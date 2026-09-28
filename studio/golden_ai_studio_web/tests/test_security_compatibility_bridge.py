from jarvis_core.security_compatibility import LegacySecurityBridge


class FakeCanonicalService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute_tool(self, name, arguments, command="", task_id="desktop"):
        self.calls.append((name, arguments, command, task_id))
        return dict(self.result)


def test_migrated_legacy_tool_reaches_canonical_service_once():
    service = FakeCanonicalService({"ok": True, "message": "opened"})
    bridge = LegacySecurityBridge(lambda: service)

    result = bridge.execute({"tool": "open_file", "path": "read-only.txt"}, "session-1")

    assert result["compatibility_bridge"] is True
    assert result["security_owner"] == "jarvis_core.security.SecurityManager"
    assert result["audit_owner"] == "jarvis_core.audit.AuditLog"
    assert service.calls == [(
        "open_file", {"path": "read-only.txt"}, "legacy:open_file", "session-1")]


def test_migrated_confirmation_is_single_use_and_not_root_approval():
    service = FakeCanonicalService({
        "ok": True,
        "confirmation_required": True,
        "token": "opaque-token",
    })
    bridge = LegacySecurityBridge(lambda: service)

    result = bridge.execute({"tool": "delete_file", "path": "target.txt"}, "session-2")

    assert result["approval_backend"] == "jarvis_core"
    assert result["request_id"] == "jarvis:opaque-token"
    assert result["approval_scope"] == "ONCE"
    assert len(service.calls) == 1


def test_selected_migration_fails_closed_without_canonical_service():
    result = LegacySecurityBridge(lambda: None).execute(
        {"tool": "delete_file", "path": "target.txt"}, "session-3")

    assert result["ok"] is False
    assert result["security_fail_closed"] is True


def test_unsupported_legacy_tool_is_deferred_not_silently_migrated():
    service = FakeCanonicalService({"ok": True})
    result = LegacySecurityBridge(lambda: service).execute(
        {"tool": "write_file", "path": "target.txt", "content": "x"}, "session-4")

    assert result is None
    assert service.calls == []


def test_selected_migration_rejects_extra_arguments_fail_closed():
    service = FakeCanonicalService({"ok": True})
    result = LegacySecurityBridge(lambda: service).execute(
        {"tool": "open_file", "path": "target.txt", "content": "unexpected"}, "session-5")

    assert result["ok"] is False
    assert result["security_fail_closed"] is True
    assert service.calls == []
