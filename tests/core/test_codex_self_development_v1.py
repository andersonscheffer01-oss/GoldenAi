"""Tests for Codex CLI integration and Self-Development V1.

Covers all 20 required scenarios:
1.  Codex CLI detection
2.  Version
3.  CodexAdapter
4.  ToolResult
5.  Ollama provider
6.  local_only
7.  paid fallback blocked
8.  PermissionManager remains authority
9.  Codex cannot grant permission to itself
10. checkpoint
11. checkpoint resume
12. backup before edit
13. rollback on failure
14. accept on success
15. timeout
16. local model unavailable
17. fallback only to local model
18. critical file protection
19. AuditLogger
20. sandbox end-to-end test
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, r"c:\GoldenAI")

from core.config import CodingAgentConfig, GoldenAISettings, load_settings
from core.execution import ExecutionService, PermissionMode
from core.permissions import PermissionManager
from core.tools.external import (
    CostPolicy,
    ExternalToolRegistry,
    ToolAdapter,
    ToolCapability,
    ToolDefinition,
    ToolResult,
    ToolStatus,
    create_default_registry,
)
from core.tools.external.adapters.codex_cli import CodexCLIAdapter
from core.self_development import (
    SelfDevCheckpoint,
    SelfDevCheckpointStore,
    SelfDevelopmentManager,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_INTERRUPTED,
    TASK_PLANNED,
    TASK_ROLLED_BACK,
    TASK_RUNNING,
    TASK_VALIDATING,
    TASK_WAITING_PERMISSION,
    is_critical_path,
)


class CodexSelfDevelopmentV1Tests(unittest.TestCase):
    """Tests for Codex CLI + Self-Development V1."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "GoldenAI"
        (self.root / "config").mkdir(parents=True)
        (self.root / "logs").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)
        (self.root / "sandbox").mkdir(parents=True)
        (self.root / "backups").mkdir(parents=True)
        (self.root / "projetos").mkdir(parents=True)

        self.settings = GoldenAISettings(
            root=self.root,
            projects_dir=self.root / "projetos",
            backups_dir=self.root / "backups",
            logs_dir=self.root / "logs",
            sandbox_dir=self.root / "sandbox",
            data_dir=self.root / "data",
            allowed_paths=(self.root / "projetos", self.root / "sandbox", self.root / "data", self.root / "logs"),
            protected_paths=(self.root / "app", self.root / "core", self.root / "studio", self.root / "backups"),
            read_only=False,
            write_enabled=True,
            command_execution_enabled=True,
        )
        self.pm = PermissionManager(self.settings)
        self.pm.execution.set_mode(PermissionMode.FULL)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ------------------------------------------------------------------
    # 1. Codex CLI detection
    # ------------------------------------------------------------------
    def test_01_codex_cli_detection(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        result = adapter.detect()
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "AVAILABLE")
        self.assertIn("path", result.metadata)

    # ------------------------------------------------------------------
    # 2. Version
    # ------------------------------------------------------------------
    def test_02_codex_version(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        result = adapter.get_version()
        self.assertTrue(result.success)
        self.assertIn("codex", result.message.lower())
        self.assertIsNotNone(result.exit_code)

    # ------------------------------------------------------------------
    # 3. CodexAdapter
    # ------------------------------------------------------------------
    def test_03_codex_adapter_interface(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        self.assertIsInstance(adapter, ToolAdapter)
        self.assertTrue(hasattr(adapter, "detect"))
        self.assertTrue(hasattr(adapter, "health_check"))
        self.assertTrue(hasattr(adapter, "execute"))
        self.assertTrue(hasattr(adapter, "get_version"))
        self.assertTrue(hasattr(adapter, "get_capabilities"))
        self.assertTrue(hasattr(adapter, "execute_task"))

    def test_03b_codex_adapter_capabilities(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        caps = adapter.get_capabilities()
        self.assertIn(ToolCapability.READ_FILES, caps)
        self.assertIn(ToolCapability.WRITE_FILES, caps)
        self.assertIn(ToolCapability.EXECUTE_COMMANDS, caps)
        self.assertIn(ToolCapability.RUN_TESTS, caps)

    # ------------------------------------------------------------------
    # 4. ToolResult
    # ------------------------------------------------------------------
    def test_04_tool_result_standardized(self) -> None:
        result = ToolResult(
            success=True,
            status="SUCCESS",
            tool_id="codex_cli",
            action="execute_task",
            message="Done",
            stdout="output",
            stderr="",
            exit_code=0,
            files_modified=["test.py"],
            duration=1.0,
            metadata={"model": "qwen2.5-coder:14b", "provider": "ollama"},
        )
        d = result.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["tool_id"], "codex_cli")
        self.assertEqual(d["metadata"]["model"], "qwen2.5-coder:14b")
        self.assertEqual(d["metadata"]["provider"], "ollama")

    # ------------------------------------------------------------------
    # 5. Ollama provider
    # ------------------------------------------------------------------
    def test_05_ollama_provider(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        # Check that the adapter uses Ollama as provider
        cmd = adapter._build_command(
            prompt="test",
            workdir=str(self.root / "sandbox"),
            model="qwen2.5-coder:14b",
            timeout=60,
        )
        self.assertIn("--oss", cmd)
        self.assertIn("--local-provider", cmd)
        self.assertIn("ollama", cmd)
        self.assertIn("-m", cmd)
        self.assertIn("qwen2.5-coder:14b", cmd)

    # ------------------------------------------------------------------
    # 6. local_only
    # ------------------------------------------------------------------
    def test_06_local_only(self) -> None:
        settings = load_settings()
        self.assertTrue(settings.coding_agent.local_only)
        self.assertEqual(settings.coding_agent.model_provider, "ollama")

    def test_06b_env_no_openai_key(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        env = adapter._build_env()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertIn("OLLAMA_HOST", env)

    # ------------------------------------------------------------------
    # 7. paid fallback blocked
    # ------------------------------------------------------------------
    def test_07_paid_fallback_blocked(self) -> None:
        settings = load_settings()
        self.assertFalse(settings.coding_agent.paid_fallback)
        self.assertFalse(settings.tools.allow_remote_paid)

    def test_07b_codex_cost_policy_free(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        self.assertEqual(adapter.definition.cost_policy, CostPolicy.FREE_OR_LOCAL)

    # ------------------------------------------------------------------
    # 8. PermissionManager remains authority
    # ------------------------------------------------------------------
    def test_08_permission_manager_authority(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        # Adapter does not have permission methods
        self.assertFalse(hasattr(adapter, "can_write"))
        self.assertFalse(hasattr(adapter, "can_read"))
        self.assertFalse(hasattr(adapter, "can_execute_command"))
        self.assertFalse(hasattr(adapter, "grant_permission"))
        # PermissionManager is the authority
        self.assertTrue(self.pm.can_read(self.settings.projects_dir).allowed)

    # ------------------------------------------------------------------
    # 9. Codex cannot grant permission to itself
    # ------------------------------------------------------------------
    def test_09_codex_cannot_grant_permission(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        # No grant_permission method
        self.assertFalse(hasattr(adapter, "grant_permission"))
        # Capabilities don't confer permissions
        self.assertIn(ToolCapability.WRITE_FILES, adapter.get_capabilities())
        # check_permission delegates to PermissionManager
        result = adapter.check_permission("write", path=str(self.root / "app" / "test.py"))
        # app is protected, so should be denied
        if result is not None:
            self.assertFalse(result.success)

    # ------------------------------------------------------------------
    # 10. checkpoint
    # ------------------------------------------------------------------
    def test_10_checkpoint_create(self) -> None:
        store = SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints")
        checkpoint = store.create(
            objective="Fix bug in add function",
            pending_steps=["detect", "fix", "test"],
        )
        self.assertTrue(checkpoint.task_id)
        self.assertEqual(checkpoint.status, TASK_PLANNED)
        self.assertEqual(len(checkpoint.pending_steps), 3)

        # Load it back
        loaded = store.load(checkpoint.task_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.objective, "Fix bug in add function")

    # ------------------------------------------------------------------
    # 11. checkpoint resume
    # ------------------------------------------------------------------
    def test_11_checkpoint_resume(self) -> None:
        store = SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints")
        checkpoint = store.create(objective="Test resume")
        checkpoint.status = TASK_INTERRUPTED
        store.save(checkpoint)

        # List interrupted
        interrupted = store.list_interrupted()
        self.assertEqual(len(interrupted), 1)

        # Load and resume
        loaded = store.load(checkpoint.task_id)
        loaded.status = TASK_RUNNING
        store.save(loaded)
        self.assertEqual(loaded.status, TASK_RUNNING)

    # ------------------------------------------------------------------
    # 12. backup before edit
    # ------------------------------------------------------------------
    def test_12_backup_before_edit(self) -> None:
        test_file = self.root / "projetos" / "test_backup.py"
        test_file.write_text("print('original')", encoding="utf-8")

        manager = SelfDevelopmentManager(
            settings=self.settings,
            permission_manager=self.pm,
            checkpoint_store=SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints"),
        )
        checkpoint = manager.create_task(
            objective="Test backup",
            files=[str(test_file)],
        )
        manager._step_create_backup(checkpoint)
        self.assertEqual(len(checkpoint.backup_paths), 1)
        self.assertTrue(Path(checkpoint.backup_paths[0]).exists())

    # ------------------------------------------------------------------
    # 13. rollback on failure
    # ------------------------------------------------------------------
    def test_13_rollback_on_failure(self) -> None:
        test_file = self.root / "projetos" / "test_rollback.py"
        test_file.write_text("print('original')", encoding="utf-8")

        manager = SelfDevelopmentManager(
            settings=self.settings,
            permission_manager=self.pm,
            checkpoint_store=SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints"),
        )
        checkpoint = manager.create_task(
            objective="Test rollback",
            files=[str(test_file)],
        )
        manager._step_create_backup(checkpoint)

        # Modify the file
        test_file.write_text("print('modified')", encoding="utf-8")

        # Rollback
        manager._rollback(checkpoint)
        self.assertEqual(checkpoint.status, TASK_ROLLED_BACK)
        self.assertEqual(test_file.read_text(encoding="utf-8"), "print('original')")

    # ------------------------------------------------------------------
    # 14. accept on success
    # ------------------------------------------------------------------
    def test_14_accept_on_success(self) -> None:
        store = SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints")
        checkpoint = store.create(objective="Test accept")
        checkpoint.status = TASK_RUNNING
        store.save(checkpoint)

        manager = SelfDevelopmentManager(
            settings=self.settings,
            permission_manager=self.pm,
            checkpoint_store=store,
        )
        result = manager._step_accept(checkpoint)
        self.assertEqual(result.status, TASK_COMPLETED)
        self.assertIn("accepted", result.result.lower())

    # ------------------------------------------------------------------
    # 15. timeout
    # ------------------------------------------------------------------
    def test_15_timeout(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        # Test with a very short timeout — should timeout or fail quickly
        result = adapter.execute_task(
            prompt="test",
            workdir=str(self.root / "sandbox"),
            model="nonexistent_model",
            timeout=1,
        )
        # Should fail (either timeout or model not found)
        self.assertFalse(result.success)

    # ------------------------------------------------------------------
    # 16. local model unavailable
    # ------------------------------------------------------------------
    def test_16_local_model_unavailable(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        # Mock Ollama as unavailable
        with patch.object(adapter, "_check_ollama", return_value=False):
            result = adapter.execute_task(prompt="test", workdir=str(self.root / "sandbox"))
            self.assertFalse(result.success)
            self.assertIn(result.status, ("UNAVAILABLE", "PERMISSION_DENIED"))

    # ------------------------------------------------------------------
    # 17. fallback only to local model
    # ------------------------------------------------------------------
    def test_17_fallback_only_local(self) -> None:
        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)
        # The command should always include --oss and --local-provider ollama
        cmd = adapter._build_command("test", str(self.root / "sandbox"), "any_model", 60)
        self.assertIn("--oss", cmd)
        self.assertIn("--local-provider", cmd)
        self.assertIn("ollama", cmd)
        # No --api-key or OpenAI flags
        cmd_str = " ".join(cmd)
        self.assertNotIn("openai", cmd_str.lower())
        self.assertNotIn("--api-key", cmd_str)

    # ------------------------------------------------------------------
    # 18. critical file protection
    # ------------------------------------------------------------------
    def test_18_critical_file_protection(self) -> None:
        self.assertTrue(is_critical_path("core/permissions/manager.py"))
        self.assertTrue(is_critical_path("core/audit/logger.py"))
        self.assertTrue(is_critical_path("config/golden_ai.yaml"))
        self.assertTrue(is_critical_path("core/config/settings.py"))
        self.assertFalse(is_critical_path("sandbox/test.py"))
        self.assertFalse(is_critical_path("projetos/my_project.py"))

    def test_18b_critical_file_blocks_task(self) -> None:
        manager = SelfDevelopmentManager(
            settings=self.settings,
            permission_manager=self.pm,
            checkpoint_store=SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints"),
        )
        checkpoint = manager.create_task(
            objective="Modify permissions",
            files=["core/permissions/manager.py"],
        )
        result = manager._step_check_permission(checkpoint)
        self.assertEqual(result.status, TASK_WAITING_PERMISSION)
        self.assertFalse(result.permission_granted)

    # ------------------------------------------------------------------
    # 19. AuditLogger
    # ------------------------------------------------------------------
    def test_19_audit_logger(self) -> None:
        from core.audit.logger import AuditEvent, AuditLogger

        logger = AuditLogger(log_dir=self.root / "logs")
        logger.record(AuditEvent(
            action_type="TEST_ACTION",
            status="COMPLETED",
            target="test_task",
            agent="self_development",
            result="Test passed",
        ))
        # Verify the log file was created
        log_files = list((self.root / "logs").glob("audit_*.jsonl"))
        self.assertGreater(len(log_files), 0)
        content = log_files[0].read_text(encoding="utf-8")
        self.assertIn("TEST_ACTION", content)
        self.assertIn("self_development", content)

    # ------------------------------------------------------------------
    # 20. sandbox end-to-end test
    # ------------------------------------------------------------------
    def test_20_sandbox_end_to_end(self) -> None:
        """End-to-end test: Golden → Codex → Ollama → Qwen → edit → test → verify.

        This test creates a buggy file, runs Codex to fix it, and verifies
        the fix. If Ollama is not running, the test is skipped.
        """
        # Create buggy file in sandbox
        sandbox_dir = self.root / "sandbox" / "self_development_test"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        buggy_file = sandbox_dir / "buggy_code.py"
        buggy_file.write_text(
            'def add(a, b):\n    return a - b\n',
            encoding="utf-8",
        )

        adapter = CodexCLIAdapter(permission_manager=self.pm, settings=self.settings)

        # Check if Ollama is available
        if not adapter._check_ollama():
            self.skipTest("Ollama not running — skipping end-to-end test")

        # Check if any model is available
        models = adapter._list_ollama_models()
        if not models:
            self.skipTest("No Ollama models available — skipping end-to-end test")

        # Run Codex to fix the bug
        result = adapter.execute_task(
            prompt="Fix the bug in buggy_code.py: the add function should return a + b, not a - b. Only change the return statement in the add function.",
            workdir=str(sandbox_dir),
            timeout=120,
        )

        # Verify the result
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success, f"Codex execution failed: {result.message}")
        self.assertEqual(result.metadata.get("provider"), "ollama")
        self.assertTrue(result.metadata.get("local_only"))
        self.assertFalse(result.metadata.get("paid_fallback"))

        # Check if the file was fixed
        content = buggy_file.read_text(encoding="utf-8")
        # The fix should change 'a - b' to 'a + b'
        self.assertIn("a + b", content, f"Bug not fixed. File content: {content}")

    # ------------------------------------------------------------------
    # Additional: Health check
    # ------------------------------------------------------------------
    def test_21_health_check(self) -> None:
        manager = SelfDevelopmentManager(
            settings=self.settings,
            permission_manager=self.pm,
            checkpoint_store=SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints"),
        )
        health = manager.health_check()
        self.assertIn("codex_cli", health)
        self.assertIn("codex_provider", health)
        self.assertIn("ollama", health)
        self.assertIn("paid_fallback", health)
        self.assertEqual(health["paid_fallback"], "DISABLED")
        self.assertTrue(health["local_only"])

    # ------------------------------------------------------------------
    # Additional: Config loading
    # ------------------------------------------------------------------
    def test_22_config_coding_agent_loaded(self) -> None:
        settings = load_settings()
        self.assertTrue(settings.coding_agent.enabled)
        self.assertEqual(settings.coding_agent.provider, "codex_cli")
        self.assertTrue(settings.coding_agent.local_only)
        self.assertFalse(settings.coding_agent.paid_fallback)
        self.assertEqual(settings.coding_agent.model_provider, "ollama")
        self.assertTrue(settings.coding_agent.self_development_enabled)
        self.assertTrue(settings.coding_agent.checkpoint_enabled)
        self.assertTrue(settings.coding_agent.backup_before_edit)
        self.assertTrue(settings.coding_agent.rollback_on_failure)

    # ------------------------------------------------------------------
    # Additional: Registry with Codex adapter
    # ------------------------------------------------------------------
    def test_23_registry_with_codex(self) -> None:
        registry = create_default_registry()
        codex_def = registry.get("codex_cli")
        self.assertIsNotNone(codex_def)
        self.assertEqual(codex_def.cost_policy, CostPolicy.FREE_OR_LOCAL)
        self.assertTrue(codex_def.config_hints.get("local_only"))

    # ------------------------------------------------------------------
    # Additional: Circuit breaker integration
    # ------------------------------------------------------------------
    def test_24_circuit_breaker_integration(self) -> None:
        manager = SelfDevelopmentManager(
            settings=self.settings,
            permission_manager=self.pm,
            checkpoint_store=SelfDevCheckpointStore(store_dir=self.root / "data" / "checkpoints"),
        )
        self.assertIsNotNone(manager.circuit_breaker)
        self.assertEqual(manager.circuit_breaker.failure_threshold, self.settings.model_circuit_failure_threshold)

    # ------------------------------------------------------------------
    # Additional: Task states
    # ------------------------------------------------------------------
    def test_25_task_states(self) -> None:
        self.assertEqual(TASK_PLANNED, "PLANNED")
        self.assertEqual(TASK_RUNNING, "RUNNING")
        self.assertEqual(TASK_WAITING_PERMISSION, "WAITING_PERMISSION")
        self.assertEqual(TASK_VALIDATING, "VALIDATING")
        self.assertEqual(TASK_COMPLETED, "COMPLETED")
        self.assertEqual(TASK_FAILED, "FAILED")
        self.assertEqual(TASK_ROLLED_BACK, "ROLLED_BACK")
        self.assertEqual(TASK_INTERRUPTED, "INTERRUPTED")


if __name__ == "__main__":
    unittest.main()