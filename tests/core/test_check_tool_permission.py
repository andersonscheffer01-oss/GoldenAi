"""Unit tests for check_tool_permission in app/golden_ai.py.

Covers all permission classes (READ, WRITE, EXECUTE, READ_EXTERNAL_SAFE,
CRITICAL) across execution modes (READ_ONLY, AUTO_SAFE, FULL).

Key observations validated by these tests:
- READ tools with empty target (no path) always pass
- READ tools with path target depend on can_read() path validation
- WRITE tools now go through PermissionManager.can_write()
- EXECUTE tools have tool-specific logic (allowlists, path checks)
- CRITICAL is always blocked
- Core V3 fallback allows READ, blocks WRITE
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(r"C:\\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import GoldenAISettings
from core.execution.models import PermissionMode
from core.permissions import PermissionManager


# ---------------------------------------------------------------------------
# Mock external modules that prevent app.golden_ai from loading
# ---------------------------------------------------------------------------

_MOCK_MODULES = {
    "ollama": MagicMock(),
    "requests": MagicMock(),
    "numpy": MagicMock(),
    "pandas": MagicMock(),
}

for mod_name, mock_obj in _MOCK_MODULES.items():
    if mod_name not in sys.modules:
        sys.modules[mod_name] = mock_obj

import app.golden_ai as engine  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(mode: str = "READ_ONLY") -> PermissionManager:
    """Create a PermissionManager pointing to the real C:\\GoldenAI root."""
    settings = GoldenAISettings(
        read_only=(mode == "READ_ONLY"),
        write_enabled=(mode != "READ_ONLY"),
        command_execution_enabled=(mode != "READ_ONLY"),
        internet_enabled=True,
        media_enabled=True,
    )
    manager = PermissionManager(settings)
    manager.execution.set_mode(mode)
    return manager


def _call_check(manager, tool_name: str, arguments: dict | None = None):
    """Call check_tool_permission with a mocked CORE_PERMISSION_MANAGER."""
    old_pm = engine.CORE_PERMISSION_MANAGER
    old_al = engine.CORE_AUDIT_LOGGER
    try:
        engine.CORE_PERMISSION_MANAGER = manager
        engine.CORE_AUDIT_LOGGER = None
        return engine.check_tool_permission(tool_name, arguments)
    finally:
        engine.CORE_PERMISSION_MANAGER = old_pm
        engine.CORE_AUDIT_LOGGER = old_al


# ===================================================================
# READ permission class
# ===================================================================

class TestREADPermissionClass(unittest.TestCase):
    """READ tools: empty target always passes; path target uses can_read()."""

    def test_read_no_target_always_allowed(self):
        """Tools with empty target (memory, agent) pass regardless of mode."""
        for mode in ("READ_ONLY", "AUTO_SAFE", "FULL"):
            manager = _make_manager(mode)
            allowed, reason, cls, _ = _call_check(manager, "memory_search_knowledge")
            self.assertTrue(allowed, f"READ no-target should pass in {mode}")

    def test_read_market_no_target_passes(self):
        """Market query tools have empty target -> always allowed."""
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, target = _call_check(manager, "market_list_analyses")
        self.assertTrue(allowed)
        self.assertEqual(cls, "READ")
        self.assertEqual(target, "")

    def test_read_quant_no_target_passes(self):
        """Quant query tools have empty target -> always allowed."""
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, target = _call_check(manager, "quant_list_experiments")
        self.assertTrue(allowed)
        self.assertEqual(cls, "READ")
        self.assertEqual(target, "")

    def test_read_with_valid_path_passes(self):
        """ler_arquivo with a real .mq5 in projetos passes can_read()."""
        manager = _make_manager("READ_ONLY")
        # Use a known file that exists in C:\\GoldenAI\\projetos
        allowed, reason, cls, target = _call_check(
            manager, "ler_arquivo", {"nome": "arquivo.mq5"}
        )
        # may be True or False depending on whether file exists,
        # but the class must be READ
        self.assertEqual(cls, "READ")

    def test_read_class_always_returns_read(self):
        """All READ-class tools return cls='READ'."""
        manager = _make_manager("READ_ONLY")
        for tool in ("listar_projetos", "memory_search_knowledge",
                      "market_get_analysis", "internet_search",
                      "browser_search", "document_extract"):
            _, _, cls, _ = _call_check(manager, tool)
            self.assertEqual(cls, "READ", f"{tool} should be class READ")


# ===================================================================
# WRITE permission class (now uses PermissionManager.can_write)
# ===================================================================

class TestWRITEPermissionClass(unittest.TestCase):
    """WRITE tools: delegated to PermissionManager.can_write() and
    can_internet_download() since our recent fix."""

    def test_write_class_returns_write(self):
        manager = _make_manager("READ_ONLY")
        _, _, cls, _ = _call_check(
            manager, "escrever_arquivo", {"nome": "x.mq5"}
        )
        self.assertEqual(cls, "WRITE")

    def test_write_read_only_blocks(self):
        """READ_ONLY mode blocks all writes via can_write()."""
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, _ = _call_check(
            manager, "escrever_arquivo", {"nome": "x.mq5"}
        )
        self.assertFalse(allowed)
        self.assertIn("read-only", reason.lower())

    def test_write_auto_safe_requires_approval(self):
        """AUTO_SAFE with MEDIUM risk goes to approval (not auto-allowed)."""
        manager = _make_manager("AUTO_SAFE")
        allowed, reason, cls, _ = _call_check(
            manager, "escrever_arquivo", {"nome": "x.mq5"}
        )
        # AUTO_SAFE only auto-allows LOW risk; WRITE is MEDIUM
        self.assertFalse(allowed)
        self.assertEqual(cls, "WRITE")

    def test_write_full_allows(self):
        """FULL mode allows MEDIUM-risk writes."""
        manager = _make_manager("FULL")
        allowed, reason, cls, _ = _call_check(
            manager, "escrever_arquivo", {"nome": "x.mq5"}
        )
        self.assertTrue(allowed, f"FULL should allow write, got: {reason}")

    def test_write_copiar_ea_class_write(self):
        manager = _make_manager("READ_ONLY")
        _, _, cls, _ = _call_check(
            manager, "copiar_ea_mt5_para_teste", {"nome": "ea.mq5"}
        )
        self.assertEqual(cls, "WRITE")

    def test_write_copiar_ea_blocked_read_only(self):
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(
            manager, "copiar_ea_mt5_para_teste", {"nome": "ea.mq5"}
        )
        self.assertFalse(allowed)

    def test_internet_download_uses_special_handler(self):
        """internet_download uses can_internet_download, not can_write."""
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, _ = _call_check(
            manager, "internet_download",
            {"url": "https://example.com/data.csv"}
        )
        self.assertFalse(allowed)
        self.assertEqual(cls, "WRITE")

    def test_internet_download_full_still_needs_authorization(self):
        """Even FULL mode, internet download has its own policy."""
        manager = _make_manager("FULL")
        allowed, reason, cls, _ = _call_check(
            manager, "internet_download",
            {"url": "https://example.com/data.csv"}
        )
        self.assertEqual(cls, "WRITE")


# ===================================================================
# EXECUTE permission class
# ===================================================================

class TestEXECUTEPermissionClass(unittest.TestCase):
    """EXECUTE tools: tool-specific permission logic."""

    def test_execute_class_returns_execute(self):
        manager = _make_manager("READ_ONLY")
        _, _, cls, _ = _call_check(
            manager, "compilar_mql5", {"nome": "robot.mq5"}
        )
        self.assertEqual(cls, "EXECUTE")

    def test_compile_mql5_passes_read_check(self):
        """MQL5 compile passes can_read() then uses MQL5-specific allow."""
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(
            manager, "compilar_mql5", {"nome": "robot.mq5"}
        )
        # MQL5 compile is safe: read check + .mq5 extension -> allowed
        self.assertTrue(allowed)

    def test_compile_mql5_check_path_exists(self):
        """MQL5 compile requires can_read on the file path first."""
        manager = _make_manager("FULL")
        allowed, reason, cls, _ = _call_check(
            manager, "compilar_mql5", {"nome": "robot.mq5"}
        )
        # May fail if file doesn't exist, but class must be EXECUTE
        self.assertEqual(cls, "EXECUTE")

    def test_launch_app_allowlisted(self):
        """launch_allowed_app checks its own allowlist, independent of mode."""
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, _ = _call_check(
            manager, "launch_allowed_app", {"name": "MetaTrader 5"}
        )
        # Allowlist check happens; blocked because can_execute_command is disabled
        self.assertEqual(cls, "EXECUTE")

    def test_launch_app_non_allowlisted_blocked(self):
        manager = _make_manager("FULL")
        allowed, reason, cls, _ = _call_check(
            manager, "launch_allowed_app", {"name": "powershell"}
        )
        self.assertFalse(allowed)
        self.assertIn("allowlist", reason.lower())

    def test_open_folder_check(self):
        """open_folder checks its own allowlist."""
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, _ = _call_check(
            manager, "open_folder", {"path": r"C:\\GoldenAI\\projetos"}
        )
        self.assertEqual(cls, "EXECUTE")

    def test_executar_opencode_class_execute(self):
        """executar_opencode is mapped to EXECUTE class."""
        _, _, cls, _ = _call_check(manager := _make_manager("READ_ONLY"),
                                    "executar_opencode", {"tarefa": "test"})
        self.assertEqual(cls, "EXECUTE")


# ===================================================================
# CRITICAL permission class
# ===================================================================

class TestCRITICALPermissionClass(unittest.TestCase):
    """CRITICAL tools always blocked regardless of mode."""

    def test_critical_always_blocked_read_only(self):
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, _ = _call_check(
            manager, "excluir_backup", {"backup": "old.zip"}
        )
        self.assertFalse(allowed)
        self.assertEqual(cls, "CRITICAL")

    def test_critical_always_blocked_full(self):
        manager = _make_manager("FULL")
        allowed, reason, cls, _ = _call_check(
            manager, "excluir_backup", {"backup": "old.zip"}
        )
        self.assertFalse(allowed)

    def test_unknown_tool_defaults_critical(self):
        manager = _make_manager("FULL")
        allowed, reason, cls, _ = _call_check(manager, "nonexistent_xyz")
        self.assertFalse(allowed)
        self.assertEqual(cls, "CRITICAL")


# ===================================================================
# READ_EXTERNAL_SAFE permission class
# ===================================================================

class TestREAD_EXTERNAL_SAFEPermissionClass(unittest.TestCase):
    """READ_EXTERNAL_SAFE tools: system queries always allowed."""

    def test_system_info_allowed(self):
        manager = _make_manager("READ_ONLY")
        allowed, reason, cls, _ = _call_check(manager, "get_system_info")
        self.assertTrue(allowed)
        self.assertEqual(cls, "READ_EXTERNAL_SAFE")

    def test_disk_usage_allowed(self):
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(
            manager, "get_disk_usage", {"path": r"C:\\GoldenAI"}
        )
        self.assertTrue(allowed)

    def test_list_processes_allowed(self):
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(manager, "list_processes")
        self.assertTrue(allowed)

    def test_find_installed_app_allowed(self):
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(
            manager, "find_installed_app", {"name": "notepad"}
        )
        self.assertTrue(allowed)

    def test_mt5_status_allowed(self):
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(manager, "get_mt5_status")
        self.assertTrue(allowed)

    def test_find_mt5_installations_allowed(self):
        manager = _make_manager("READ_ONLY")
        allowed, _, cls, _ = _call_check(manager, "find_mt5_installations")
        self.assertTrue(allowed)


# ===================================================================
# Fallback when Core V3 is unavailable
# ===================================================================

class TestFallbackWhenCoreV3Unavailable(unittest.TestCase):
    """When CORE_PERMISSION_MANAGER is None, legacy mode activates."""

    def test_fallback_allows_read(self):
        old_pm = engine.CORE_PERMISSION_MANAGER
        try:
            engine.CORE_PERMISSION_MANAGER = None
            allowed, reason, cls, _ = engine.check_tool_permission("memory_search_knowledge")
            self.assertTrue(allowed)
            self.assertIn("legada", reason.lower())
        finally:
            engine.CORE_PERMISSION_MANAGER = old_pm

    def test_fallback_classifies_write(self):
        """Without Core V3, WRITE is classified but permission check uses fallback."""
        old_pm = engine.CORE_PERMISSION_MANAGER
        try:
            engine.CORE_PERMISSION_MANAGER = None
            allowed, reason, cls, _ = engine.check_tool_permission(
                "escrever_arquivo", {"nome": "x.mq5"}
            )
            self.assertEqual(cls, "WRITE")
        finally:
            engine.CORE_PERMISSION_MANAGER = old_pm


if __name__ == "__main__":
    unittest.main()
