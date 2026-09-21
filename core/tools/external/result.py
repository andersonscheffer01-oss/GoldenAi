"""Standardized result object for external tool execution.

No tool should return raw text to the rest of GoldenAI. Every
execution path must produce a ``ToolResult`` so the orchestrator
can make deterministic decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standardized result returned by every external tool execution."""

    success: bool = False
    status: str = "UNKNOWN"
    """High-level status: SUCCESS, NOT_INSTALLED, PERMISSION_DENIED, ERROR, etc."""

    tool_id: str = ""
    action: str = ""
    """What was attempted: detect, health_check, execute, get_version."""

    message: str = ""
    """Human-readable summary."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    duration: float = 0.0
    """Elapsed seconds."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Tool-specific extra data (version, port, model count, etc.)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "tool_id": self.tool_id,
            "action": self.action,
            "message": self.message,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "files_created": list(self.files_created),
            "files_modified": list(self.files_modified),
            "duration": self.duration,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def not_installed(cls, tool_id: str, action: str = "execute") -> "ToolResult":
        return cls(
            success=False,
            status="NOT_INSTALLED",
            tool_id=tool_id,
            action=action,
            message=f"Tool '{tool_id}' is not installed",
        )

    @classmethod
    def permission_denied(cls, tool_id: str, action: str, reason: str) -> "ToolResult":
        return cls(
            success=False,
            status="PERMISSION_DENIED",
            tool_id=tool_id,
            action=action,
            message=f"Permission denied for '{tool_id}': {reason}",
        )

    @classmethod
    def blocked_paid(cls, tool_id: str, action: str = "execute") -> "ToolResult":
        return cls(
            success=False,
            status="BLOCKED_PAID",
            tool_id=tool_id,
            action=action,
            message=f"Tool '{tool_id}' requires payment and paid tools are blocked",
        )

    @classmethod
    def disabled(cls, tool_id: str, action: str = "execute") -> "ToolResult":
        return cls(
            success=False,
            status="DISABLED",
            tool_id=tool_id,
            action=action,
            message=f"Tool '{tool_id}' is disabled",
        )

    @classmethod
    def error(cls, tool_id: str, action: str, message: str, stderr: str = "") -> "ToolResult":
        return cls(
            success=False,
            status="ERROR",
            tool_id=tool_id,
            action=action,
            message=message,
            stderr=stderr,
        )