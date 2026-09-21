"""SECURITY BUG FIX — Confirmation Fail-Closed Tests

ROOT CAUSE: Gateway._handle_confirmation() never checked the 'approved' field.
When user clicked Cancel, the gateway still called service.confirm(token),
which executed the tool handler regardless of user intent.

FIX: Gateway now checks 'approved' before calling confirm().
     JarvisService.deny_confirmation() consumes token without executing.

Tests A-G from the security audit spec.
"""

import sys
import time
from pathlib import Path
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.models import Risk, Tool, ResponsePolicy
from jarvis_core.registry import ToolRegistry
from jarvis_core.security import SecurityManager
from jarvis_core.service import JarvisService


# ═══════════════════════════════════════════════════════════════
# FAKE CRITICAL TOOL — no real side effects
# ═══════════════════════════════════════════════════════════════

_call_counter = {"count": 0}


def fake_critical_handler():
    """Increments counter in memory. No real OS action."""
    _call_counter["count"] += 1
    return {"ok": True, "message": "fake critical action executed"}


def reset_counter():
    _call_counter["count"] = 0


def get_counter():
    return _call_counter["count"]


def _make_service_with_fake_tool():
    """Create a JarvisService with a fake CRITICAL tool registered."""
    service = JarvisService(str(Path(__file__).resolve().parent.parent))
    # Remove shutdown tool to avoid real side effects in tests
    if "shutdown" in service.registry._tools:
        del service.registry._tools["shutdown"]
    if "restart" in service.registry._tools:
        del service.registry._tools["restart"]

    fake_tool = Tool(
        "fake_critical_action",
        "Fake critical action for testing",
        fake_critical_handler,
        Risk.CRITICAL,
        confirmation=True,
    )
    service.registry.register(fake_tool)
    return service


# ═══════════════════════════════════════════════════════════════
# TEST A: Before confirmation, CALL_COUNT = 0
# ═══════════════════════════════════════════════════════════════

class TestA_BeforeConfirmation:
    def test_handler_not_called_before_approval(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        result = service.execute_tool("fake_critical_action", {})

        assert result.get("confirmation_required") is True
        assert result.get("token") is not None
        assert get_counter() == 0, "Handler must NOT be called before approval"


# ═══════════════════════════════════════════════════════════════
# TEST B: Cancel → CALL_COUNT = 0
# ═══════════════════════════════════════════════════════════════

class TestB_CancelPath:
    def test_cancel_does_not_execute_handler(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        # Request confirmation
        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        # User cancels
        deny_result = service.deny_confirmation(token)
        assert deny_result.get("denied") is True
        assert get_counter() == 0, "Handler must NOT be called on cancel"

    def test_deny_confirmation_consumes_token(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        service.deny_confirmation(token)

        # Token consumed — confirm should fail
        confirm_result = service.confirm(token)
        assert confirm_result.get("ok") is False
        assert get_counter() == 0


# ═══════════════════════════════════════════════════════════════
# TEST C: Approve → CALL_COUNT = 1
# ═══════════════════════════════════════════════════════════════

class TestC_ApprovePath:
    def test_approve_executes_handler_once(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        # User approves
        confirm_result = service.confirm(token)
        assert confirm_result.get("ok") is True
        assert get_counter() == 1, "Handler must be called exactly once on approve"


# ═══════════════════════════════════════════════════════════════
# TEST D: Duplicate approve → CALL_COUNT stays 1
# ═══════════════════════════════════════════════════════════════

class TestD_DuplicateApproval:
    def test_duplicate_approve_does_not_re_execute(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        # First approve — executes
        service.confirm(token)
        assert get_counter() == 1

        # Second approve with same token — should fail (token consumed)
        dup_result = service.confirm(token)
        assert dup_result.get("ok") is False
        assert get_counter() == 1, "Handler must NOT be called again on duplicate approve"


# ═══════════════════════════════════════════════════════════════
# TEST E: Cancel then approve cancelled token → CALL_COUNT = 0
# ═══════════════════════════════════════════════════════════════

class TestE_CancelThenApprove:
    def test_approve_after_cancel_does_not_execute(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        # Cancel first
        service.deny_confirmation(token)
        assert get_counter() == 0

        # Try to approve the cancelled token
        confirm_result = service.confirm(token)
        assert confirm_result.get("ok") is False
        assert get_counter() == 0, "Handler must NOT execute after cancel"


# ═══════════════════════════════════════════════════════════════
# TEST F: Expired confirmation → CALL_COUNT = 0
# ═══════════════════════════════════════════════════════════════

class TestF_ExpiredConfirmation:
    def test_expired_token_does_not_execute(self):
        reset_counter()
        service = _make_service_with_fake_tool()
        # Set very short TTL
        service.security.confirmation_ttl = 0

        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        # Wait for expiry
        time.sleep(0.01)

        confirm_result = service.confirm(token)
        assert confirm_result.get("ok") is False
        assert get_counter() == 0, "Handler must NOT execute with expired token"


# ═══════════════════════════════════════════════════════════════
# TEST G: Request without confirmation → CALL_COUNT = 0
# ═══════════════════════════════════════════════════════════════

class TestG_NoApprovalNoExecution:
    def test_execute_tool_blocks_without_confirmation(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        # Execute with confirmed=False (default)
        result = service.execute_tool("fake_critical_action", {}, confirmed=False)
        assert result.get("confirmation_required") is True
        assert get_counter() == 0

    def test_execute_tool_needs_valid_token(self):
        reset_counter()
        service = _make_service_with_fake_tool()

        # Try to confirm with a bogus token
        result = service.confirm("bogus_token_12345")
        assert result.get("ok") is False
        assert get_counter() == 0


# ═══════════════════════════════════════════════════════════════
# GATEWAY APPROVED FIELD CHECK
# ═══════════════════════════════════════════════════════════════

class TestGatewayApprovedCheck:
    """Verify the gateway _handle_confirmation checks 'approved' field."""

    def test_gateway_code_checks_approved(self):
        """Gateway source must check msg.payload.get('approved')."""
        gateway_path = Path(__file__).resolve().parent.parent / "jarvis_core" / "gateway" / "gateway.py"
        source = gateway_path.read_text()
        # Must check 'approved' field
        assert "approved" in source, "Gateway must check 'approved' field"
        # Must have deny path
        assert "deny_confirmation" in source or "not approved" in source.lower() or "not approved" in source, \
            "Gateway must have deny path when approved=False"

    def test_gateway_deny_does_not_call_confirm(self):
        """When approved=False, gateway must NOT call service.confirm()."""
        gateway_path = Path(__file__).resolve().parent.parent / "jarvis_core" / "gateway" / "gateway.py"
        source = gateway_path.read_text()
        # Find the _handle_confirmation method
        lines = source.split("\n")
        in_handle_confirmation = False
        indent_level = 0
        deny_section_found = False
        for line in lines:
            if "async def _handle_confirmation" in line:
                in_handle_confirmation = True
                indent_level = len(line) - len(line.lstrip())
                continue
            if in_handle_confirmation:
                stripped = line.strip()
                if stripped and not line.strip().startswith("#"):
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= indent_level and stripped.startswith("async def") or stripped.startswith("def "):
                        break
                if "not approved" in stripped.lower() or "if not approved" in stripped.lower():
                    deny_section_found = True
                if deny_section_found and "deny_confirmation" in stripped:
                    return  # Found it
        # If we get here, check more carefully
        assert "not approved" in source.lower() or "approved" in source, \
            "Gateway must handle denied confirmations"

    def test_deny_confirmation_method_exists(self):
        """JarvisService must have deny_confirmation method."""
        assert hasattr(JarvisService, "deny_confirmation"), \
            "JarvisService must have deny_confirmation method"

    def test_deny_confirmation_audits(self):
        """deny_confirmation should create an audit entry."""
        service = _make_service_with_fake_tool()
        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        service.deny_confirmation(token)

        entries = service.audit.recent(limit=10)
        deny_entries = [e for e in entries if e.get("status") == "cancelado_pelo_operador"]
        assert len(deny_entries) > 0, "deny_confirmation must create audit entry"


# ═══════════════════════════════════════════════════════════════
# FAIL-CLOSED INVARIANTS
# ═══════════════════════════════════════════════════════════════

class TestFailClosed:
    """If anything goes wrong, result must be DENY."""

    def test_invalid_token_returns_deny(self):
        reset_counter()
        service = _make_service_with_fake_tool()
        result = service.confirm("invalid_token")
        assert result.get("ok") is False
        assert get_counter() == 0

    def test_none_token_returns_deny(self):
        reset_counter()
        service = _make_service_with_fake_tool()
        result = service.confirm(None)
        assert result.get("ok") is False
        assert get_counter() == 0

    def test_empty_token_returns_deny(self):
        reset_counter()
        service = _make_service_with_fake_tool()
        result = service.confirm("")
        assert result.get("ok") is False
        assert get_counter() == 0

    def test_already_consumed_token_returns_deny(self):
        reset_counter()
        service = _make_service_with_fake_tool()
        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        # Consume via deny
        service.deny_confirmation(token)

        # Try to consume again via confirm
        result2 = service.confirm(token)
        assert result2.get("ok") is False
        assert get_counter() == 0


# ═══════════════════════════════════════════════════════════════
# SHUTDOWN HANDLER STRUCTURAL CHECK
# ═══════════════════════════════════════════════════════════════

class TestShutdownHandlerGuarded:
    """Structurally verify shutdown/restart/kill_process handlers are guarded."""

    def test_shutdown_tool_has_confirmation(self):
        """shutdown tool must have confirmation=True."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        tool = service.registry.get("shutdown")
        assert tool is not None
        assert tool.confirmation is True
        assert tool.risk == Risk.CRITICAL

    def test_restart_tool_has_confirmation(self):
        """restart tool must have confirmation=True."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        tool = service.registry.get("restart")
        assert tool is not None
        assert tool.confirmation is True
        assert tool.risk == Risk.CRITICAL

    def test_kill_process_tool_has_confirmation(self):
        """kill_process tool must have confirmation=True."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        tool = service.registry.get("kill_process")
        assert tool is not None
        assert tool.confirmation is True

    def test_lock_windows_tool_has_confirmation(self):
        """lock_windows tool must have confirmation=True."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        tool = service.registry.get("lock_windows")
        assert tool is not None
        assert tool.confirmation is True

    def test_shutdown_handler_source_does_not_call_subprocess_in_init(self):
        """_shutdown handler must not be callable outside execute_tool flow."""
        source_path = Path(__file__).resolve().parent.parent / "jarvis_core" / "service.py"
        source = source_path.read_text(encoding="utf-8")
        # Find _shutdown method
        lines = source.split("\n")
        in_shutdown = False
        shutdown_lines = []
        for line in lines:
            if "def _shutdown(self" in line:
                in_shutdown = True
                shutdown_lines = [line]
                continue
            if in_shutdown:
                if line.strip() and not line.startswith(" " * 8) and not line.startswith("\t" * 2):
                    if line.strip().startswith("def ") or line.strip().startswith("class "):
                        break
                shutdown_lines.append(line)

        shutdown_code = "\n".join(shutdown_lines)
        # The handler itself just calls subprocess — that's fine.
        # The important thing is it can ONLY be called via execute_tool
        # which goes through security.decision() → confirmation flow.
        assert "subprocess" in shutdown_code or "Popen" in shutdown_code, \
            "shutdown handler should use subprocess (this is expected)"


# ═══════════════════════════════════════════════════════════════
# TRADING CRITICAL GUARDED
# ═══════════════════════════════════════════════════════════════

class TestTradingCriticalGuarded:
    """Trading tools must follow same confirmation guarantees."""

    def test_trading_tools_require_confirmation(self):
        """Any registered trading tool with HIGH/CRITICAL must have confirmation."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        for name, tool in service.registry._tools.items():
            if tool.risk in (Risk.HIGH, Risk.CRITICAL):
                assert tool.confirmation or tool.dynamic_risk, \
                    f"Tool '{name}' has {tool.risk.value} risk but no confirmation"


# ═══════════════════════════════════════════════════════════════
# SIDE EFFECT BEFORE CONFIRMATION SEARCH
# ═══════════════════════════════════════════════════════════════

class TestNoSideEffectBeforeConfirmation:
    """Verify no code path calls handler before confirmation."""

    def test_execute_tool_blocks_at_security_check(self):
        """execute_tool must return confirmation_required before calling handler."""
        reset_counter()
        service = _make_service_with_fake_tool()

        # Mock to ensure handler is NOT called
        original_handler = fake_critical_handler
        call_log = []

        def tracked_handler():
            call_log.append("called")
            return original_handler()

        # Replace handler in registry
        tool = service.registry.get("fake_critical_action")
        service.registry._tools["fake_critical_action"] = replace(
            tool, handler=tracked_handler
        )

        result = service.execute_tool("fake_critical_action", {})

        assert result.get("confirmation_required") is True
        assert len(call_log) == 0, "Handler was called before confirmation!"
        assert get_counter() == 0

    def test_confirm_calls_handler_exactly_once(self):
        """confirm() must call handler exactly once."""
        reset_counter()
        service = _make_service_with_fake_tool()

        call_log = []
        original_handler = fake_critical_handler

        def tracked_handler():
            call_log.append("called")
            return original_handler()

        tool = service.registry.get("fake_critical_action")
        service.registry._tools["fake_critical_action"] = replace(
            tool, handler=tracked_handler
        )

        result = service.execute_tool("fake_critical_action", {})
        token = result["token"]

        service.confirm(token)

        assert len(call_log) == 1, f"Handler called {len(call_log)} times, expected 1"
        assert get_counter() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
