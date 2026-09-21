"""Data models for the Self-Development system.

These models represent the state of a self-development task that
can be persisted and resumed after interruptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Task states
TASK_PLANNED = "PLANNED"
TASK_RUNNING = "RUNNING"
TASK_WAITING_PERMISSION = "WAITING_PERMISSION"
TASK_VALIDATING = "VALIDATING"
TASK_COMPLETED = "COMPLETED"
TASK_FAILED = "FAILED"
TASK_ROLLED_BACK = "ROLLED_BACK"
TASK_INTERRUPTED = "INTERRUPTED"

ALL_TASK_STATES = {
    TASK_PLANNED,
    TASK_RUNNING,
    TASK_WAITING_PERMISSION,
    TASK_VALIDATING,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_ROLLED_BACK,
    TASK_INTERRUPTED,
}

# Critical files that cannot be modified without explicit approval
CRITICAL_PATHS = {
    "core/permissions",
    "core/audit",
    "core/config/settings.py",
    "config/golden_ai.yaml",
    "core/safety",
    "core/execution",
    "core/coding/rollback.py",
    "core/tools/checkpoint.py",
    "core/tools/hashing.py",
}


def is_critical_path(path: str) -> bool:
    """Check whether a path is in the critical set."""
    normalized = str(path).replace("\\", "/").lower()
    for critical in CRITICAL_PATHS:
        if critical in normalized:
            return True
    return False


@dataclass
class SelfDevCheckpoint:
    """Persistable checkpoint for a self-development task."""

    task_id: str
    objective: str = ""
    status: str = TASK_PLANNED
    current_step: str = ""
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    backup_paths: list[str] = field(default_factory=list)
    model_used: str = ""
    agent_used: str = ""
    tests_executed: list[str] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    timestamp: str = field(default_factory=now_iso)

    # Codex execution metadata
    codex_stdout: str = ""
    codex_stderr: str = ""
    codex_exit_code: int | None = None
    codex_duration: float = 0.0

    # Permission tracking
    permission_checked: bool = False
    permission_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "status": self.status,
            "current_step": self.current_step,
            "completed_steps": list(self.completed_steps),
            "pending_steps": list(self.pending_steps),
            "files_read": list(self.files_read),
            "files_modified": list(self.files_modified),
            "backup_paths": list(self.backup_paths),
            "model_used": self.model_used,
            "agent_used": self.agent_used,
            "tests_executed": list(self.tests_executed),
            "test_results": dict(self.test_results),
            "result": self.result,
            "timestamp": self.timestamp,
            "codex_stdout": self.codex_stdout,
            "codex_stderr": self.codex_stderr,
            "codex_exit_code": self.codex_exit_code,
            "codex_duration": self.codex_duration,
            "permission_checked": self.permission_checked,
            "permission_granted": self.permission_granted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelfDevCheckpoint":
        return cls(
            task_id=data.get("task_id", ""),
            objective=data.get("objective", ""),
            status=data.get("status", TASK_PLANNED),
            current_step=data.get("current_step", ""),
            completed_steps=data.get("completed_steps", []),
            pending_steps=data.get("pending_steps", []),
            files_read=data.get("files_read", []),
            files_modified=data.get("files_modified", []),
            backup_paths=data.get("backup_paths", []),
            model_used=data.get("model_used", ""),
            agent_used=data.get("agent_used", ""),
            tests_executed=data.get("tests_executed", []),
            test_results=data.get("test_results", {}),
            result=data.get("result", ""),
            timestamp=data.get("timestamp", now_iso()),
            codex_stdout=data.get("codex_stdout", ""),
            codex_stderr=data.get("codex_stderr", ""),
            codex_exit_code=data.get("codex_exit_code"),
            codex_duration=data.get("codex_duration", 0.0),
            permission_checked=data.get("permission_checked", False),
            permission_granted=data.get("permission_granted", False),
        )