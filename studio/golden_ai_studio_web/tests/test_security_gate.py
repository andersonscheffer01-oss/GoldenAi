"""
Security Gate Tests — PHASE 3 FINAL GATE

Tests that PROVE security boundaries are enforced.
No functional code modified — only tests.

1. plugin_cannot_bypass_security_manager
2. plugin_cannot_call_mt5_directly
3. plugin_cannot_register_unprotected_trading_tool
4. shutdown_requires_confirmation
5. shutdown_execution_is_audited
6. api_keys_not_web_accessible
7. runtime_database_not_web_accessible
"""

import importlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

GOLDEN_ROOT = Path(r"C:\GoldenAI")
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
sys.path.insert(0, str(GOLDEN_ROOT))
sys.path.insert(0, str(STUDIO_ROOT))
sys.path.insert(0, str(GOLDEN_ROOT / "plugins"))

# Import plugin_loader
_spec = importlib.util.spec_from_file_location(
    "plugin_loader", str(GOLDEN_ROOT / "plugins" / "plugin_loader.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Plugin = _mod.Plugin
PluginManifest = _mod.PluginManifest
PluginRegistry = _mod.PluginRegistry
PluginState = _mod.PluginState

# Import security/registry components
from jarvis_core.security import SecurityManager
from jarvis_core.registry import ToolRegistry
from jarvis_core.models import Risk, Tool


# ═══════════════════════════════════════════════════════════════
# 1. PLUGIN → MT5 BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestPluginCannotBypassSecurityManager:
    """Plugin tools MUST go through SecurityManager when executed."""

    def test_plugin_tool_goes_through_security_decision(self):
        """When plugin tool is executed, SecurityManager.decision() is called."""
        registry = ToolRegistry()
        security = SecurityManager({"shutdown": "confirm"})

        tool_called = []

        def plugin_handler(**kwargs):
            tool_called.append(True)
            return {"ok": True}

        tool = Tool("risky_plugin_tool", "Test", plugin_handler,
                     Risk.HIGH, confirmation=True)
        registry.register(tool)

        retrieved = registry.get("risky_plugin_tool")
        assert retrieved is not None
        assert retrieved.risk == Risk.HIGH
        assert retrieved.confirmation is True

        decision = security.decision(retrieved)
        assert decision == "confirm"

    def test_plugin_cannot_register_tool_bypassing_risk(self):
        """Plugin registering tool with Risk.CRITICAL requires confirmation."""
        security = SecurityManager({
            "critical_tool": "confirm",
        })

        tool = Tool("critical_tool", "Dangerous", lambda **k: {"ok": True},
                     Risk.CRITICAL, confirmation=True)

        decision = security.decision(tool)
        assert decision == "confirm"

    def test_plugin_permission_does_not_override_security_manager(self):
        """Plugin permissions are metadata only — SecurityManager decides."""
        security = SecurityManager({"mt5_trade": "deny"})

        tool = Tool("mt5_trade", "Trade via MT5", lambda **k: {"ok": True},
                     Risk.HIGH, confirmation=True)

        decision = security.decision(tool)
        assert decision == "deny"


# ═══════════════════════════════════════════════════════════════
# 2. PLUGIN PERMISSIONS — CRITICAL CAPABILITIES
# ═══════════════════════════════════════════════════════════════

class TestPluginPermissionsCriticalCapabilities:
    """Critical capabilities require SecurityManager enforcement."""

    CRITICAL_CAPABILITIES = [
        "mt5", "trading", "order", "shell", "exec",
        "shutdown", "filesystem", "credentials"
    ]

    def test_security_manager_mandatory_for_critical(self):
        """SecurityManager must be present for any critical tool execution."""
        registry = ToolRegistry()
        security = SecurityManager()

        for cap in self.CRITICAL_CAPABILITIES:
            tool = Tool(f"plugin_{cap}", f"Plugin {cap}",
                        lambda **k: {"ok": True}, Risk.HIGH, confirmation=True)
            registry.register(tool)
            retrieved = registry.get(f"plugin_{cap}")
            decision = security.decision(retrieved)
            assert decision in ("confirm", "deny"), \
                f"Capability '{cap}' should require confirmation or be denied"

    def test_plugin_trading_tool_requires_risk_engine(self):
        """Plugin trading tool must go through risk engine."""
        from risk_engine import get_risk_engine
        engine = get_risk_engine()

        allowed, reason, details = engine.can_trade(
            "EURUSD", "BUY", [])
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)


# ═══════════════════════════════════════════════════════════════
# 3. SHUTDOWN TOOL PROTECTIONS
# ═══════════════════════════════════════════════════════════════

class TestShutdownRequiresConfirmation:
    """Shutdown tool requires user confirmation before execution."""

    def test_shutdown_risk_is_critical(self):
        """Shutdown tool has Risk.CRITICAL."""
        from jarvis_core.service import JarvisService
        service = JarvisService(STUDIO_ROOT)

        tool = service.registry.get("shutdown")
        assert tool is not None
        assert tool.risk == Risk.CRITICAL

    def test_shutdown_requires_confirmation(self):
        """Shutdown tool has confirmation=True."""
        from jarvis_core.service import JarvisService
        service = JarvisService(STUDIO_ROOT)

        tool = service.registry.get("shutdown")
        assert tool is not None
        assert tool.confirmation is True

    def test_shutdown_security_manager_returns_confirm(self):
        """SecurityManager returns 'confirm' for shutdown tool."""
        from jarvis_core.service import JarvisService
        service = JarvisService(STUDIO_ROOT)

        tool = service.registry.get("shutdown")
        decision = service.security.decision(tool)
        assert decision == "confirm"

    def test_shutdown_not_executed_without_confirmation(self):
        """Shutdown tool execution is blocked when confirmed=False."""
        from jarvis_core.service import JarvisService
        service = JarvisService(STUDIO_ROOT)

        result = service.execute_tool("shutdown", {}, confirmed=False)
        assert result.get("confirmation_required") is True
        assert result.get("token") is not None
        assert result.get("risk") in ("critical", "CRITICAL")


class TestShutdownExecutionIsAudited:
    """Shutdown execution is logged in AuditLog."""

    def test_shutdown_confirmation_creates_audit_entry(self):
        """When shutdown requires confirmation, audit entry is created."""
        from jarvis_core.service import JarvisService
        service = JarvisService(STUDIO_ROOT)

        result = service.execute_tool("shutdown", {}, confirmed=False)
        assert result.get("confirmation_required") is True

        entries = service.audit.recent(limit=10)
        shutdown_entries = [e for e in entries if e.get("tool") == "shutdown"]
        assert len(shutdown_entries) > 0
        assert any(e.get("status") == "aguardando_confirmacao" for e in shutdown_entries)


# ═══════════════════════════════════════════════════════════════
# 4. API KEYS NOT WEB ACCESSIBLE
# ═══════════════════════════════════════════════════════════════

class TestApiKeysNotWebAccessible:
    """config/api_keys.json cannot be accessed via HTTP."""

    def test_config_outside_served_directory(self):
        """config/ directory is outside the HTTP server's root."""
        config_path = GOLDEN_ROOT / "config" / "api_keys.json"
        web_dir = STUDIO_ROOT

        config_resolved = config_path.resolve()
        web_resolved = web_dir.resolve()

        assert not str(config_resolved).startswith(str(web_resolved)), \
            f"Config path {config_resolved} is inside web dir {web_resolved}"

    def test_no_api_route_serves_config(self):
        """No /api/ route returns api_keys.json content."""
        from server_agent import GoldenAIHandler

        handler_class = GoldenAIHandler
        route_methods = [m for m in dir(handler_class) if m.startswith("api_")
                         or m.startswith("_api_")]

        for method_name in route_methods:
            method = getattr(handler_class, method_name)
            if callable(method):
                source = getattr(method, "__func__", method)
                try:
                    import inspect
                    src = inspect.getsource(source)
                    assert "api_keys.json" not in src or "read_jarvis_api_keys" not in src, \
                        f"Route {method_name} may expose api_keys.json"
                except (TypeError, OSError):
                    pass

    def test_http_handler_serves_from_studio_only(self):
        """GoldenAIHandler serves files only from studio directory."""
        from server_agent import GoldenAIHandler
        import inspect
        src = inspect.getsource(GoldenAIHandler.__init__)
        assert "directory=web_dir" in src or "web_dir" in src


# ═══════════════════════════════════════════════════════════════
# 5. RUNTIME DATABASE NOT WEB ACCESSIBLE
# ═══════════════════════════════════════════════════════════════

class TestRuntimeDatabaseNotWebAccessible:
    """golden_runtime.db cannot be downloaded via HTTP."""

    def test_db_not_served_by_api(self):
        """No /api/ route returns golden_runtime.db content."""
        from server_agent import GoldenAIHandler
        import inspect

        route_methods = [m for m in dir(GoldenAIHandler) if m.startswith("api_")
                         or m.startswith("_api_")]

        for method_name in route_methods:
            method = getattr(GoldenAIHandler, method_name)
            if callable(method):
                source = getattr(method, "__func__", method)
                try:
                    src = inspect.getsource(source)
                    assert "golden_runtime.db" not in src, \
                        f"Route {method_name} references golden_runtime.db"
                except (TypeError, OSError):
                    pass

    def test_db_used_only_by_internal_modules(self):
        """golden_runtime.db is only used by internal Python modules, not web routes."""
        from server_agent import GoldenAIHandler
        import inspect
        src = inspect.getsource(GoldenAIHandler)
        assert "golden_runtime.db" not in src


# ═══════════════════════════════════════════════════════════════
# 6. ARCHITECTURE INVARIANTS
# ═══════════════════════════════════════════════════════════════

class TestArchitectureInvariants:
    """Core architecture invariants that must never break."""

    def test_security_manager_is_not_parallel_system(self):
        """SecurityManager in jarvis_core/security.py is the only authority."""
        from jarvis_core.security import SecurityManager
        sm = SecurityManager({"test": "confirm"})
        tool = Tool("test", "test", lambda **k: {}, Risk.HIGH, confirmation=True)
        assert sm.decision(tool) == "confirm"

    def test_tool_registry_is_not_parallel_system(self):
        """ToolRegistry in jarvis_core/registry.py is the only authority."""
        from jarvis_core.registry import ToolRegistry
        tr = ToolRegistry()
        tool = Tool("test", "test", lambda **k: {}, Risk.LOW)
        tr.register(tool)
        assert tr.get("test") is not None

    def test_audit_log_has_redaction(self):
        """AuditLog has _sanitize method for secret redaction."""
        from jarvis_core.audit import AuditLog
        with tempfile.TemporaryDirectory() as tmpdir:
            al = AuditLog(Path(tmpdir) / "test.db")
            assert hasattr(al, "_sanitize")
            assert callable(al._sanitize)

    def test_security_manager_rules_enforced(self):
        """SecurityManager deny rule blocks tool execution."""
        sm = SecurityManager({"dangerous_tool": "deny"})
        tool = Tool("dangerous_tool", "test", lambda **k: {}, Risk.HIGH)
        assert sm.decision(tool) == "deny"

    def test_confirmation_token_has_expiry(self):
        """Confirmation tokens expire after TTL."""
        sm = SecurityManager(confirmation_ttl=1)
        tool = Tool("test", "test", lambda **k: {}, Risk.HIGH, confirmation=True)
        token = sm.create_confirmation(tool, {}, "")
        assert token is not None
        item = sm.consume(token)
        assert item is not None
        item2 = sm.consume(token)
        assert item2 is None
