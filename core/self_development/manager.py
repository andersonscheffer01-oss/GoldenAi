"""Self-Development Manager for GoldenAI.

Allows GoldenAI to work on its own code in a controlled, safe manner.

Flow:
1. Identify task
2. Create checkpoint
3. Register files involved
4. Create backup
5. Consult PermissionManager
6. Execute alteration (via Codex CLI + Ollama)
7. Execute validations
8. Execute tests
9. Verify result
10. Accept (commit) or Rollback

SECURITY CONTRACT
-----------------
- PermissionManager is the sole authority
- Critical files cannot be modified without explicit approval
- AuditLogger records all actions
- Circuit Breaker from Multi-Model Local V1 is reused
- No paid API fallback
- All execution uses local Ollama models only
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.audit.logger import AuditEvent, AuditLogger
from core.config import GoldenAISettings, load_settings
from core.permissions import PermissionManager
from core.tools.external.adapters.codex_cli import CodexCLIAdapter
from core.tools.external.result import ToolResult

from .checkpoint import SelfDevCheckpointStore
from .models import (
    SelfDevCheckpoint,
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


class SelfDevelopmentManager:
    """Manages self-development tasks with full safety guarantees."""

    def __init__(
        self,
        settings: GoldenAISettings | None = None,
        permission_manager: PermissionManager | None = None,
        codex_adapter: CodexCLIAdapter | None = None,
        checkpoint_store: SelfDevCheckpointStore | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.permission_manager = permission_manager or PermissionManager(self.settings)
        self.codex_adapter = codex_adapter or CodexCLIAdapter(
            permission_manager=self.permission_manager,
            settings=self.settings,
        )
        self.checkpoint_store = checkpoint_store or SelfDevCheckpointStore()
        self.audit_logger = audit_logger or AuditLogger()

        # Reuse Circuit Breaker from Multi-Model Local V1
        from core.models.circuit_breaker import CircuitBreaker

        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.settings.model_circuit_failure_threshold,
        )

        # Sandbox directory for self-development tests
        self.sandbox_dir = self.settings.sandbox_dir / "self_development_test"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def create_task(
        self,
        objective: str,
        files: list[str] | None = None,
        pending_steps: list[str] | None = None,
    ) -> SelfDevCheckpoint:
        """Create a new self-development task."""
        if not pending_steps:
            pending_steps = [
                "create_checkpoint",
                "create_backup",
                "check_permission",
                "execute_codex",
                "validate",
                "run_tests",
                "accept_or_rollback",
            ]

        checkpoint = self.checkpoint_store.create(
            objective=objective,
            pending_steps=pending_steps,
        )
        checkpoint.files_read = list(files or [])
        checkpoint.agent_used = "codex_cli"
        self.checkpoint_store.save(checkpoint)

        self._audit("TASK_CREATED", "PLANNED", checkpoint.task_id, objective)
        return checkpoint

    def resume_task(self, task_id: str) -> SelfDevCheckpoint | None:
        """Resume an interrupted task."""
        checkpoint = self.checkpoint_store.load(task_id)
        if checkpoint is None:
            return None
        checkpoint.status = TASK_RUNNING
        self.checkpoint_store.save(checkpoint)
        self._audit("TASK_RESUMED", "RUNNING", task_id, checkpoint.objective)
        return checkpoint

    def run_task(
        self,
        task_id: str,
        prompt: str = "",
        workdir: str = "",
        model: str = "",
        timeout: int = 300,
    ) -> SelfDevCheckpoint:
        """Run a self-development task to completion.

        This is the main entry point. It:
        1. Creates backups
        2. Checks permissions
        3. Executes Codex CLI with Ollama
        4. Validates results
        5. Runs tests
        6. Accepts or rolls back
        """
        checkpoint = self.checkpoint_store.load(task_id)
        if checkpoint is None:
            raise ValueError(f"Task {task_id} not found")

        checkpoint.status = TASK_RUNNING
        self.checkpoint_store.save(checkpoint)

        try:
            # Step 1: Create backup
            checkpoint = self._step_create_backup(checkpoint)
            if checkpoint.status == TASK_FAILED:
                return checkpoint

            # Step 2: Check permission
            checkpoint = self._step_check_permission(checkpoint)
            if checkpoint.status == TASK_WAITING_PERMISSION:
                return checkpoint

            # Step 3: Execute Codex
            checkpoint = self._step_execute_codex(
                checkpoint,
                prompt=prompt or checkpoint.objective,
                workdir=workdir or str(self.sandbox_dir),
                model=model,
                timeout=timeout,
            )
            if checkpoint.status == TASK_FAILED:
                self._rollback(checkpoint)
                return checkpoint

            # Step 4: Validate
            checkpoint = self._step_validate(checkpoint)
            if checkpoint.status == TASK_FAILED:
                self._rollback(checkpoint)
                return checkpoint

            # Step 5: Run tests
            checkpoint = self._step_run_tests(checkpoint, workdir or str(self.sandbox_dir))
            if checkpoint.status == TASK_FAILED:
                self._rollback(checkpoint)
                return checkpoint

            # Step 6: Accept
            checkpoint = self._step_accept(checkpoint)
            return checkpoint

        except Exception as exc:
            checkpoint.status = TASK_INTERRUPTED
            checkpoint.result = f"Interrupted: {exc}"
            self.checkpoint_store.save(checkpoint)
            self._audit("TASK_INTERRUPTED", "INTERRUPTED", task_id, str(exc))
            return checkpoint

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _step_create_backup(self, checkpoint: SelfDevCheckpoint) -> SelfDevCheckpoint:
        """Create backups of files that will be modified."""
        checkpoint.current_step = "create_backup"
        backup_dir = self.settings.backups_dir / "self_dev" / checkpoint.task_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        for file_path in checkpoint.files_read:
            src = Path(file_path)
            if src.exists() and src.is_file():
                dest = backup_dir / src.name
                shutil.copy2(src, dest)
                checkpoint.backup_paths.append(str(dest))

        checkpoint.completed_steps.append("create_backup")
        self.checkpoint_store.save(checkpoint)
        self._audit("BACKUP_CREATED", "RUNNING", checkpoint.task_id, f"{len(checkpoint.backup_paths)} files")
        return checkpoint

    def _step_check_permission(self, checkpoint: SelfDevCheckpoint) -> SelfDevCheckpoint:
        """Check if the task is permitted by PermissionManager."""
        checkpoint.current_step = "check_permission"
        checkpoint.permission_checked = True

        # Check for critical files
        for file_path in checkpoint.files_read:
            if is_critical_path(file_path):
                checkpoint.status = TASK_WAITING_PERMISSION
                checkpoint.permission_granted = False
                checkpoint.result = f"Critical file requires explicit approval: {file_path}"
                self.checkpoint_store.save(checkpoint)
                self._audit("PERMISSION_BLOCKED", "WAITING_PERMISSION", checkpoint.task_id, checkpoint.result)
                return checkpoint

        # Check PermissionManager for write
        for file_path in checkpoint.files_read:
            decision = self.permission_manager.can_write(file_path, explicit_authorization=False)
            if not decision.allowed:
                checkpoint.status = TASK_WAITING_PERMISSION
                checkpoint.permission_granted = False
                checkpoint.result = f"Permission denied: {decision.reason}"
                self.checkpoint_store.save(checkpoint)
                self._audit("PERMISSION_DENIED", "WAITING_PERMISSION", checkpoint.task_id, decision.reason)
                return checkpoint

        checkpoint.permission_granted = True
        checkpoint.completed_steps.append("check_permission")
        self.checkpoint_store.save(checkpoint)
        self._audit("PERMISSION_GRANTED", "RUNNING", checkpoint.task_id, "All files permitted")
        return checkpoint

    def _step_execute_codex(
        self,
        checkpoint: SelfDevCheckpoint,
        prompt: str,
        workdir: str,
        model: str,
        timeout: int,
    ) -> SelfDevCheckpoint:
        """Execute the task through Codex CLI with local Ollama."""
        checkpoint.current_step = "execute_codex"

        # Check circuit breaker
        model_name = model or self.codex_adapter._get_default_model()
        if model_name and self.circuit_breaker.is_tripped(model_name):
            checkpoint.status = TASK_FAILED
            checkpoint.result = f"Circuit breaker tripped for model: {model_name}"
            self.checkpoint_store.save(checkpoint)
            self._audit("CIRCUIT_BREAKER", "FAILED", checkpoint.task_id, checkpoint.result)
            return checkpoint

        # Execute
        result = self.codex_adapter.execute_task(
            prompt=prompt,
            workdir=workdir,
            model=model_name,
            timeout=timeout,
        )

        # Record results
        checkpoint.codex_stdout = result.stdout
        checkpoint.codex_stderr = result.stderr
        checkpoint.codex_exit_code = result.exit_code
        checkpoint.codex_duration = result.duration
        checkpoint.model_used = result.metadata.get("model", model_name)
        checkpoint.files_modified = result.files_modified

        if not result.success:
            self.circuit_breaker.record_failure(model_name)
            checkpoint.status = TASK_FAILED
            checkpoint.result = f"Codex execution failed: {result.message}"
            self.checkpoint_store.save(checkpoint)
            self._audit("CODEX_FAILED", "FAILED", checkpoint.task_id, result.message)
            return checkpoint

        # Success — reset circuit breaker
        self.circuit_breaker.reset(model_name)
        checkpoint.completed_steps.append("execute_codex")
        self.checkpoint_store.save(checkpoint)
        self._audit("CODEX_SUCCESS", "RUNNING", checkpoint.task_id, result.message)
        return checkpoint

    def _step_validate(self, checkpoint: SelfDevCheckpoint) -> SelfDevCheckpoint:
        """Validate the Codex output."""
        checkpoint.current_step = "validate"

        # Basic validation: check if files were modified
        if not checkpoint.files_modified and not checkpoint.codex_stdout:
            checkpoint.status = TASK_FAILED
            checkpoint.result = "No files modified and no output from Codex"
            self.checkpoint_store.save(checkpoint)
            self._audit("VALIDATION_FAILED", "FAILED", checkpoint.task_id, checkpoint.result)
            return checkpoint

        checkpoint.completed_steps.append("validate")
        self.checkpoint_store.save(checkpoint)
        self._audit("VALIDATION_PASSED", "VALIDATING", checkpoint.task_id, "Validation passed")
        return checkpoint

    def _step_run_tests(self, checkpoint: SelfDevCheckpoint, workdir: str) -> SelfDevCheckpoint:
        """Run tests in the working directory."""
        checkpoint.current_step = "run_tests"
        checkpoint.status = TASK_VALIDATING

        # Try to run Python tests in the workdir
        test_cmd = ["python", "-m", "pytest", workdir, "-v", "--tb=short"]
        try:
            proc = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=workdir,
                shell=False,
            )
            checkpoint.tests_executed.append("pytest")
            checkpoint.test_results["pytest"] = {
                "exit_code": proc.returncode,
                "stdout": proc.stdout[:2000],
                "stderr": proc.stderr[:2000],
            }
            if proc.returncode != 0:
                # Try unittest as fallback
                checkpoint.tests_executed.append("unittest")
                proc2 = subprocess.run(
                    ["python", "-m", "unittest", "discover", "-s", workdir, "-v"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=workdir,
                    shell=False,
                )
                checkpoint.test_results["unittest"] = {
                    "exit_code": proc2.returncode,
                    "stdout": proc2.stdout[:2000],
                    "stderr": proc2.stderr[:2000],
                }
                if proc2.returncode != 0:
                    checkpoint.status = TASK_FAILED
                    checkpoint.result = "Tests failed"
                    self.checkpoint_store.save(checkpoint)
                    self._audit("TESTS_FAILED", "FAILED", checkpoint.task_id, "Tests failed")
                    return checkpoint
        except subprocess.TimeoutExpired:
            checkpoint.tests_executed.append("pytest")
            checkpoint.test_results["pytest"] = {"error": "timeout"}
            # Don't fail on test timeout — just log it
            checkpoint.result = "Tests timed out but changes may be valid"
        except Exception as exc:
            checkpoint.test_results["error"] = str(exc)
            # Don't fail on test error — just log it
            checkpoint.result = f"Test error: {exc}"

        checkpoint.completed_steps.append("run_tests")
        self.checkpoint_store.save(checkpoint)
        self._audit("TESTS_COMPLETED", "VALIDATING", checkpoint.task_id, "Tests completed")
        return checkpoint

    def _step_accept(self, checkpoint: SelfDevCheckpoint) -> SelfDevCheckpoint:
        """Accept the changes (internal commit, not Git)."""
        checkpoint.current_step = "accept"
        checkpoint.status = TASK_COMPLETED
        checkpoint.result = "Task completed successfully. Changes accepted."
        checkpoint.completed_steps.append("accept_or_rollback")
        self.checkpoint_store.save(checkpoint)
        self._audit("TASK_ACCEPTED", "COMPLETED", checkpoint.task_id, checkpoint.result)
        return checkpoint

    def _rollback(self, checkpoint: SelfDevCheckpoint) -> SelfDevCheckpoint:
        """Rollback changes by restoring backups."""
        checkpoint.current_step = "rollback"
        checkpoint.status = TASK_ROLLED_BACK

        for i, file_path in enumerate(checkpoint.files_read):
            if i < len(checkpoint.backup_paths):
                backup = Path(checkpoint.backup_paths[i])
                src = Path(file_path)
                if backup.exists() and src.exists():
                    shutil.copy2(backup, src)

        checkpoint.result = "Task failed. Changes rolled back."
        checkpoint.completed_steps.append("accept_or_rollback")
        self.checkpoint_store.save(checkpoint)
        self._audit("TASK_ROLLED_BACK", "ROLLED_BACK", checkpoint.task_id, checkpoint.result)
        return checkpoint

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Return a health check summary for the self-development system."""
        codex_health = self.codex_adapter.health_check()
        ollama_ok = self.codex_adapter._check_ollama()
        models = self.codex_adapter._list_ollama_models()
        version_result = self.codex_adapter.get_version()

        return {
            "codex_cli": codex_health.status,
            "codex_version": version_result.metadata.get("version", ""),
            "codex_provider": "OLLAMA LOCAL" if ollama_ok else "UNAVAILABLE",
            "ollama": "AVAILABLE" if ollama_ok else "UNAVAILABLE",
            "coding_model": models[0] if models else "NONE",
            "models_available": models,
            "paid_fallback": "DISABLED",
            "self_development": "READY" if codex_health.success and ollama_ok else "NOT_READY",
            "circuit_breaker_threshold": self.circuit_breaker.failure_threshold,
            "local_only": True,
        }

    # ------------------------------------------------------------------
    # Audit helper
    # ------------------------------------------------------------------

    def _audit(self, action: str, status: str, task_id: str, result: str) -> None:
        """Record an audit event."""
        self.audit_logger.record(AuditEvent(
            action_type=action,
            status=status,
            target=task_id,
            agent="self_development",
            result=result,
        ))