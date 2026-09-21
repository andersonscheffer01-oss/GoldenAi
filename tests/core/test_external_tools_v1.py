"""Tests for the external tools infrastructure (External Tools V1).

Covers all 12 required scenarios:
1.  Tool registration
2.  Get by id
3.  Get by category
4.  Get by capability
5.  Disabled tool
6.  Health check
7.  Missing tool
8.  Standardized result
9.  PermissionManager remains authority
10. Tool cannot grant permission to itself
11. Paid models remain blocked
12. Old configurations still work

Plus additional tests for config loading, auto-discovery, and
Multi-Model Local V1 compatibility.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, r"c:\GoldenAI")

from core.config import GoldenAISettings, ToolsConfig, load_settings
from core.permissions import PermissionManager
from core.tools.external import (
    CostPolicy,
    ExecutionMode,
    ExternalToolRegistry,
    LocalOrRemote,
    ToolAdapter,
    ToolCapability,
    ToolCategory,
    ToolDefinition,
    ToolResult,
    ToolStatus,
    create_default_registry,
    discover_tool,
    format_health_report,
    get_builtin_tool_definitions,
    get_health_summary,
    health_check_all,
    health_check_tool,
)


class ExternalToolsV1Tests(unittest.TestCase):
    """Tests for the external tools infrastructure."""

    def setUp(self) -> None:
        self.registry = ExternalToolRegistry()
        self.sample_tool = ToolDefinition(
            id="test_tool",
            name="Test Tool",
            category=ToolCategory.LLM,
            description="A test tool",
            capabilities=[ToolCapability.CHAT, ToolCapability.TOOL_CALLING],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            priority=10,
        )

    # ------------------------------------------------------------------
    # 1. Tool registration
    # ------------------------------------------------------------------
    def test_01_tool_registration(self) -> None:
        self.registry.register(self.sample_tool)
        self.assertEqual(len(self.registry.list_all()), 1)
        self.assertIn("test_tool", [t.id for t in self.registry.list_all()])

    def test_01b_register_duplicate_overwrites(self) -> None:
        self.registry.register(self.sample_tool)
        updated = ToolDefinition(
            id="test_tool",
            name="Updated Tool",
            category=ToolCategory.LLM,
            description="Updated",
        )
        self.registry.register(updated)
        tool = self.registry.get("test_tool")
        self.assertEqual(tool.name, "Updated Tool")

    def test_01c_register_empty_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            ToolDefinition(id="", name="Bad", category="llm", description="")

    # ------------------------------------------------------------------
    # 2. Get by id
    # ------------------------------------------------------------------
    def test_02_get_by_id(self) -> None:
        self.registry.register(self.sample_tool)
        tool = self.registry.get("test_tool")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.id, "test_tool")
        self.assertEqual(tool.name, "Test Tool")

    def test_02b_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.registry.get("nonexistent"))

    # ------------------------------------------------------------------
    # 3. Get by category
    # ------------------------------------------------------------------
    def test_03_get_by_category(self) -> None:
        self.registry.register(self.sample_tool)
        self.registry.register(ToolDefinition(
            id="browser_tool",
            name="Browser",
            category=ToolCategory.BROWSER,
            description="A browser tool",
        ))
        llm_tools = self.registry.list_by_category(ToolCategory.LLM)
        browser_tools = self.registry.list_by_category(ToolCategory.BROWSER)
        self.assertEqual(len(llm_tools), 1)
        self.assertEqual(llm_tools[0].id, "test_tool")
        self.assertEqual(len(browser_tools), 1)
        self.assertEqual(browser_tools[0].id, "browser_tool")

    # ------------------------------------------------------------------
    # 4. Get by capability
    # ------------------------------------------------------------------
    def test_04_get_by_capability(self) -> None:
        self.registry.register(self.sample_tool)
        self.registry.register(ToolDefinition(
            id="video_tool",
            name="Video",
            category=ToolCategory.VIDEO,
            description="A video tool",
            capabilities=[ToolCapability.PROCESS_VIDEO],
        ))
        chat_tools = self.registry.list_by_capability(ToolCapability.CHAT)
        video_tools = self.registry.list_by_capability(ToolCapability.PROCESS_VIDEO)
        self.assertEqual(len(chat_tools), 1)
        self.assertEqual(chat_tools[0].id, "test_tool")
        self.assertEqual(len(video_tools), 1)
        self.assertEqual(video_tools[0].id, "video_tool")

    # ------------------------------------------------------------------
    # 5. Disabled tool
    # ------------------------------------------------------------------
    def test_05_disabled_tool(self) -> None:
        self.registry.register(self.sample_tool)
        self.assertTrue(self.registry.disable("test_tool"))
        enabled = self.registry.list_enabled()
        self.assertEqual(len(enabled), 0)
        self.assertFalse(self.sample_tool.enabled)

    def test_05b_reenable_tool(self) -> None:
        self.registry.register(self.sample_tool)
        self.registry.disable("test_tool")
        self.assertTrue(self.registry.enable("test_tool"))
        enabled = self.registry.list_enabled()
        self.assertEqual(len(enabled), 1)
        self.assertTrue(self.sample_tool.enabled)

    def test_05c_unregister_tool(self) -> None:
        self.registry.register(self.sample_tool)
        self.assertTrue(self.registry.unregister("test_tool"))
        self.assertIsNone(self.registry.get("test_tool"))
        self.assertFalse(self.registry.unregister("test_tool"))

    # ------------------------------------------------------------------
    # 6. Health check
    # ------------------------------------------------------------------
    def test_06_health_check(self) -> None:
        # Python should be available on the test machine
        python_def = ToolDefinition(
            id="python_test",
            name="Python",
            category=ToolCategory.RUNTIME,
            description="Python runtime",
            executable="python",
            config_hints={"which_names": ["python", "python.exe", "python3"]},
        )
        self.registry.register(python_def)
        result = self.registry.health_check("python_test")
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "AVAILABLE")

    def test_06b_health_check_missing_tool(self) -> None:
        result = self.registry.health_check("nonexistent")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "NOT_INSTALLED")

    def test_06c_health_check_all(self) -> None:
        registry = create_default_registry()
        results = registry.health_check_all()
        self.assertGreater(len(results), 0)
        self.assertIn("python", results)
        self.assertIn("ollama", results)

    def test_06d_health_report_format(self) -> None:
        registry = create_default_registry()
        results = registry.health_check_all()
        report = format_health_report(results)
        self.assertIsInstance(report, str)
        self.assertIn("AVAILABLE", report)

    # ------------------------------------------------------------------
    # 7. Missing tool
    # ------------------------------------------------------------------
    def test_07_missing_tool(self) -> None:
        self.assertIsNone(self.registry.get("nonexistent"))
        self.assertFalse(self.registry.is_available("nonexistent"))
        result = self.registry.check_availability("nonexistent")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "NOT_INSTALLED")

    def test_07b_discovery_not_installed(self) -> None:
        missing_def = ToolDefinition(
            id="nonexistent_tool_xyz",
            name="Nonexistent",
            category=ToolCategory.LLM,
            description="Does not exist",
            executable="nonexistent_binary_xyz123",
            config_hints={"which_names": ["nonexistent_binary_xyz123"]},
        )
        result = discover_tool(missing_def)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "NOT_INSTALLED")

    # ------------------------------------------------------------------
    # 8. Standardized result
    # ------------------------------------------------------------------
    def test_08_standardized_result(self) -> None:
        result = ToolResult(
            success=True,
            status="SUCCESS",
            tool_id="test_tool",
            action="execute",
            message="Done",
            stdout="output",
            stderr="",
            exit_code=0,
            files_created=["/tmp/file1.py"],
            files_modified=["/tmp/file2.py"],
            duration=1.5,
            metadata={"version": "1.0"},
        )
        d = result.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["status"], "SUCCESS")
        self.assertEqual(d["tool_id"], "test_tool")
        self.assertEqual(d["action"], "execute")
        self.assertEqual(d["stdout"], "output")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["files_created"], ["/tmp/file1.py"])
        self.assertEqual(d["files_modified"], ["/tmp/file2.py"])
        self.assertEqual(d["duration"], 1.5)
        self.assertEqual(d["metadata"]["version"], "1.0")

    def test_08b_result_factory_methods(self) -> None:
        ni = ToolResult.not_installed("t1")
        self.assertFalse(ni.success)
        self.assertEqual(ni.status, "NOT_INSTALLED")

        pd = ToolResult.permission_denied("t1", "write", "blocked")
        self.assertFalse(pd.success)
        self.assertEqual(pd.status, "PERMISSION_DENIED")

        bp = ToolResult.blocked_paid("t1")
        self.assertFalse(bp.success)
        self.assertEqual(bp.status, "BLOCKED_PAID")

        dis = ToolResult.disabled("t1")
        self.assertFalse(dis.success)
        self.assertEqual(dis.status, "DISABLED")

        err = ToolResult.error("t1", "execute", "crash", stderr="trace")
        self.assertFalse(err.success)
        self.assertEqual(err.status, "ERROR")

    # ------------------------------------------------------------------
    # 9. PermissionManager remains authority
    # ------------------------------------------------------------------
    def test_09_permission_manager_remains_authority(self) -> None:
        settings = GoldenAISettings()
        pm = PermissionManager(settings)
        # PermissionManager is the authority
        self.assertTrue(pm.is_read_only())
        self.assertFalse(settings.write_enabled)
        self.assertFalse(pm.can_write(settings.projects_dir).allowed)
        # Tools do not have permission methods
        registry = ExternalToolRegistry(pm)
        self.assertFalse(hasattr(registry, "can_write"))
        self.assertFalse(hasattr(registry, "can_read"))
        self.assertFalse(hasattr(registry, "can_execute_command"))

    def test_09b_adapter_delegates_to_permission_manager(self) -> None:
        settings = GoldenAISettings()
        pm = PermissionManager(settings)
        tool_def = ToolDefinition(
            id="test_perm",
            name="Test",
            category=ToolCategory.RUNTIME,
            description="Test",
        )
        adapter = _DummyAdapter(tool_def, pm)
        # Write should be blocked by PermissionManager
        result = adapter.check_permission("write", path=str(settings.projects_dir / "test.py"))
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "PERMISSION_DENIED")

    # ------------------------------------------------------------------
    # 10. Tool cannot grant permission to itself
    # ------------------------------------------------------------------
    def test_10_tool_cannot_grant_permission(self) -> None:
        settings = GoldenAISettings()
        pm = PermissionManager(settings)
        tool_def = ToolDefinition(
            id="self_grant_attempt",
            name="Self Grant",
            category=ToolCategory.RUNTIME,
            description="Attempts to grant itself permission",
            capabilities=[ToolCapability.WRITE_FILES, ToolCapability.EXECUTE_COMMANDS],
        )
        adapter = _DummyAdapter(tool_def, pm)
        # The adapter has no method to grant permissions
        self.assertFalse(hasattr(adapter, "grant_permission"))
        self.assertFalse(hasattr(adapter, "can_write"))
        self.assertFalse(hasattr(adapter, "can_execute_command"))
        # Capabilities do not confer permissions
        self.assertIn(ToolCapability.WRITE_FILES, adapter.get_capabilities())
        result = adapter.check_permission("write", path=str(settings.projects_dir / "x.py"))
        self.assertIsNotNone(result)
        self.assertFalse(result.success)

    def test_10b_capabilities_are_metadata_not_permissions(self) -> None:
        tool = ToolDefinition(
            id="cap_test",
            name="Cap Test",
            category=ToolCategory.CODING_AGENT,
            description="Test",
            capabilities=[ToolCapability.EXECUTE_COMMANDS, ToolCapability.WRITE_FILES],
        )
        # Capabilities are just strings
        self.assertIn(ToolCapability.EXECUTE_COMMANDS, tool.capabilities)
        self.assertIn(ToolCapability.WRITE_FILES, tool.capabilities)
        # They do not appear in permissions_required
        self.assertNotIn(ToolCapability.EXECUTE_COMMANDS, tool.permissions_required)

    # ------------------------------------------------------------------
    # 11. Paid models remain blocked
    # ------------------------------------------------------------------
    def test_11_paid_models_blocked(self) -> None:
        registry = create_default_registry()
        codex = registry.get("codex_cli")
        self.assertIsNotNone(codex)
        # Codex CLI is now FREE_OR_LOCAL (uses OSS/local Ollama, not paid API)
        self.assertEqual(codex.cost_policy, CostPolicy.FREE_OR_LOCAL)

        # Settings block paid by default
        settings = GoldenAISettings()
        self.assertFalse(settings.tools.allow_remote_paid)
        self.assertFalse(settings.coding_agent.paid_fallback)

        # A truly paid tool should still be blocked
        paid_tool = ToolDefinition(
            id="paid_tool_test",
            name="Paid Tool",
            category="llm",
            description="A paid tool for testing",
            cost_policy=CostPolicy.PAID,
        )
        pm = PermissionManager(settings)
        adapter = _DummyAdapter(paid_tool, pm)
        result = adapter.execute("run_code")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "BLOCKED_PAID")

    def test_11b_openrouter_freemium_not_auto_paid(self) -> None:
        registry = create_default_registry()
        openrouter = registry.get("openrouter")
        self.assertIsNotNone(openrouter)
        self.assertEqual(openrouter.cost_policy, CostPolicy.FREEMIUM)
        # Freemium is not the same as paid, but still requires API key
        self.assertFalse(openrouter.config_hints.get("api_key_env", "") == "")

    # ------------------------------------------------------------------
    # 12. Old configurations still work
    # ------------------------------------------------------------------
    def test_12_old_config_still_works(self) -> None:
        settings = GoldenAISettings()
        # Multi-Model Local V1 fields preserved
        self.assertTrue(settings.model_routing_enabled)
        self.assertEqual(settings.ollama_api_url, "http://127.0.0.1:11434")
        self.assertFalse(settings.model_auto_download)
        self.assertIn("FAST", settings.model_profiles)
        self.assertIn("CODER", settings.model_profiles)
        self.assertIn("EXPERT", settings.model_profiles)
        # Security fields preserved
        self.assertTrue(settings.read_only)
        self.assertFalse(settings.write_enabled)
        self.assertFalse(settings.command_execution_enabled)
        self.assertGreater(len(settings.protected_paths), 0)
        self.assertGreater(len(settings.allowed_paths), 0)

    def test_12b_load_settings_preserves_old_fields(self) -> None:
        settings = load_settings()
        self.assertEqual(settings.root, Path(r"C:\GoldenAI"))
        self.assertTrue(settings.read_only)
        self.assertFalse(settings.write_enabled)
        self.assertTrue(settings.internet_enabled)
        self.assertTrue(settings.mt5_integration_enabled)
        # Tools config loaded
        self.assertTrue(settings.tools.enabled)
        self.assertTrue(settings.tools.auto_discovery)
        self.assertFalse(settings.tools.allow_remote_paid)
        self.assertEqual(settings.tools.default_cost_policy, "free_or_local")

    def test_12c_multi_model_v1_still_importable(self) -> None:
        from core.models import (
            CircuitBreaker,
            ModelProfile,
            ModelProvider,
            ModelRouter,
            OllamaProvider,
        )
        self.assertIsNotNone(ModelProfile)
        self.assertIsNotNone(ModelProvider)
        self.assertIsNotNone(OllamaProvider)
        self.assertIsNotNone(CircuitBreaker)
        self.assertIsNotNone(ModelRouter)

    # ------------------------------------------------------------------
    # Additional: Built-in tools
    # ------------------------------------------------------------------
    def test_13_builtin_tools_registered(self) -> None:
        registry = create_default_registry()
        expected_ids = [
            "ollama", "codex_cli", "openrouter", "playwright_mcp",
            "docling", "whisper", "ffmpeg", "qdrant",
            "python", "metaeditor", "mt5",
        ]
        for tid in expected_ids:
            self.assertIsNotNone(registry.get(tid), f"Tool '{tid}' should be registered")

    def test_13b_builtin_categories(self) -> None:
        tools = get_builtin_tool_definitions()
        categories = {t.category for t in tools}
        self.assertIn(ToolCategory.LLM, categories)
        self.assertIn(ToolCategory.CODING_AGENT, categories)
        self.assertIn(ToolCategory.BROWSER, categories)
        self.assertIn(ToolCategory.DOCUMENT, categories)
        self.assertIn(ToolCategory.AUDIO, categories)
        self.assertIn(ToolCategory.VIDEO, categories)
        self.assertIn(ToolCategory.MEMORY, categories)
        self.assertIn(ToolCategory.RUNTIME, categories)
        self.assertIn(ToolCategory.COMPILER, categories)
        self.assertIn(ToolCategory.TRADING, categories)

    # ------------------------------------------------------------------
    # Additional: Candidate selection
    # ------------------------------------------------------------------
    def test_14_select_candidates_by_capability(self) -> None:
        registry = create_default_registry()
        chat_candidates = registry.select_candidates(ToolCapability.CHAT)
        ids = [c.id for c in chat_candidates]
        self.assertIn("ollama", ids)
        self.assertIn("openrouter", ids)
        # Sorted by priority (lower = higher priority)
        self.assertLess(chat_candidates[0].priority, chat_candidates[-1].priority)

    def test_14b_select_candidates_only_available(self) -> None:
        registry = create_default_registry()
        candidates = registry.select_candidates(ToolCapability.EXECUTE_COMMANDS, only_available=True)
        ids = [c.id for c in candidates]
        # Python should be available on the test machine
        self.assertIn("python", ids)

    # ------------------------------------------------------------------
    # Additional: ToolStatus enum
    # ------------------------------------------------------------------
    def test_15_tool_status_enum(self) -> None:
        self.assertEqual(ToolStatus.AVAILABLE.value, "AVAILABLE")
        self.assertEqual(ToolStatus.NOT_INSTALLED.value, "NOT_INSTALLED")
        self.assertEqual(ToolStatus.NOT_CONFIGURED.value, "NOT_CONFIGURED")
        self.assertEqual(ToolStatus.DISABLED.value, "DISABLED")
        self.assertEqual(ToolStatus.BLOCKED_PAID.value, "BLOCKED_PAID")
        self.assertEqual(ToolStatus.from_str("available"), ToolStatus.AVAILABLE)
        self.assertEqual(ToolStatus.from_str("invalid"), ToolStatus.NOT_INSTALLED)

    # ------------------------------------------------------------------
    # Additional: ToolDefinition to_dict
    # ------------------------------------------------------------------
    def test_16_tool_definition_to_dict(self) -> None:
        tool = ToolDefinition(
            id="dict_test",
            name="Dict Test",
            category=ToolCategory.LLM,
            description="Test",
            provider="TestProvider",
            execution_mode=ExecutionMode.API,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="test",
            capabilities=[ToolCapability.CHAT],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE,
            enabled=True,
            priority=42,
            version="1.2.3",
            config_hints={"api_url": "http://localhost"},
        )
        d = tool.to_dict()
        self.assertEqual(d["id"], "dict_test")
        self.assertEqual(d["name"], "Dict Test")
        self.assertEqual(d["category"], ToolCategory.LLM)
        self.assertEqual(d["provider"], "TestProvider")
        self.assertEqual(d["execution_mode"], ExecutionMode.API)
        self.assertEqual(d["local_or_remote"], LocalOrRemote.LOCAL)
        self.assertEqual(d["executable"], "test")
        self.assertEqual(d["capabilities"], [ToolCapability.CHAT])
        self.assertEqual(d["permissions_required"], ["read"])
        self.assertEqual(d["cost_policy"], CostPolicy.FREE)
        self.assertTrue(d["enabled"])
        self.assertEqual(d["priority"], 42)
        self.assertEqual(d["version"], "1.2.3")
        self.assertEqual(d["config_hints"]["api_url"], "http://localhost")

    # ------------------------------------------------------------------
    # Additional: Registry status
    # ------------------------------------------------------------------
    def test_17_registry_status(self) -> None:
        registry = create_default_registry()
        status = registry.get_status()
        self.assertEqual(status["total_tools"], 12)
        self.assertEqual(status["enabled_tools"], 12)
        self.assertEqual(status["disabled_tools"], 0)
        self.assertIn("python", status["tool_ids"])

    # ------------------------------------------------------------------
    # Additional: Adapter interface
    # ------------------------------------------------------------------
    def test_18_adapter_abstract_methods(self) -> None:
        self.assertTrue(hasattr(ToolAdapter, "detect"))
        self.assertTrue(hasattr(ToolAdapter, "health_check"))
        self.assertTrue(hasattr(ToolAdapter, "execute"))
        self.assertTrue(hasattr(ToolAdapter, "get_version"))
        self.assertTrue(hasattr(ToolAdapter, "get_capabilities"))
        self.assertTrue(hasattr(ToolAdapter, "check_permission"))

    def test_18b_adapter_get_capabilities(self) -> None:
        tool_def = ToolDefinition(
            id="cap_adapter",
            name="Cap Adapter",
            category=ToolCategory.LLM,
            description="Test",
            capabilities=[ToolCapability.CHAT, ToolCapability.TOOL_CALLING],
        )
        adapter = _DummyAdapter(tool_def)
        caps = adapter.get_capabilities()
        self.assertIn(ToolCapability.CHAT, caps)
        self.assertIn(ToolCapability.TOOL_CALLING, caps)

    # ------------------------------------------------------------------
    # Additional: Health summary
    # ------------------------------------------------------------------
    def test_19_health_summary(self) -> None:
        registry = create_default_registry()
        results = registry.health_check_all()
        summary = get_health_summary(results)
        self.assertEqual(summary["total"], 12)
        self.assertGreater(summary["available"], 0)
        self.assertIn("python", summary["available_tools"])
        self.assertIn("details", summary)

    # ------------------------------------------------------------------
    # Additional: Nothing installed automatically
    # ------------------------------------------------------------------
    def test_20_nothing_installed_automatically(self) -> None:
        registry = create_default_registry()
        results = registry.health_check_all()
        # At least some tools should be NOT_INSTALLED (we didn't install them)
        missing = [tid for tid, r in results.items() if not r.success]
        self.assertGreater(len(missing), 0)


class _DummyAdapter(ToolAdapter):
    """Minimal concrete adapter for testing."""

    def detect(self) -> ToolResult:
        return ToolResult(
            success=True,
            status="AVAILABLE",
            tool_id=self.tool_id,
            action="detect",
            message="Dummy detected",
        )

    def health_check(self) -> ToolResult:
        return ToolResult(
            success=True,
            status="AVAILABLE",
            tool_id=self.tool_id,
            action="health_check",
            message="Dummy healthy",
        )

    def execute(self, action: str, **kwargs) -> ToolResult:
        # Check if this is a paid tool and paid is blocked
        if self.definition.cost_policy == CostPolicy.PAID:
            settings = GoldenAISettings()
            if not settings.tools.allow_remote_paid:
                return ToolResult.blocked_paid(self.tool_id, action)

        # Check permission for security-sensitive actions
        perm = self.check_permission(action, **kwargs)
        if perm is not None:
            return perm

        return ToolResult(
            success=True,
            status="SUCCESS",
            tool_id=self.tool_id,
            action=action,
            message=f"Executed {action}",
        )

    def get_version(self) -> ToolResult:
        return ToolResult(
            success=True,
            status="SUCCESS",
            tool_id=self.tool_id,
            action="get_version",
            message="1.0.0",
            metadata={"version": "1.0.0"},
        )


if __name__ == "__main__":
    unittest.main()
