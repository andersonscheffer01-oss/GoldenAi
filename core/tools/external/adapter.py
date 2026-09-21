"""Abstract base adapter for external tools.

The ``ToolAdapter`` is the interface that every concrete tool
integration must implement. It provides:

* ``detect()``        — discover if the tool exists on this machine
* ``health_check()``  — verify the tool is reachable and functional
* ``execute()``        — run an action through the tool
* ``get_version()``    — retrieve the tool version string
* ``get_capabilities()`` — return capability metadata

SECURITY CONTRACT
-----------------
The adapter NEVER grants permissions. Before any action that writes,
executes a command, downloads, compiles, or starts a process, the
adapter MUST call ``check_permission()`` which delegates to the
``PermissionManager``. The PermissionManager is the sole authority.

This module does NOT provide unrestricted shell access.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from core.permissions import PermissionManager

from .definitions import ToolDefinition
from .result import ToolResult
from .status import ToolStatus


class ToolAdapter(ABC):
    """Base interface for all external tool adapters.

    Subclasses implement the tool-specific logic for detection,
    health checking, and execution. The base class enforces the
    security contract: every potentially dangerous action must
    pass through ``check_permission``.
    """

    def __init__(
        self,
        definition: ToolDefinition,
        permission_manager: PermissionManager | None = None,
    ) -> None:
        self.definition = definition
        self.permission_manager = permission_manager or PermissionManager()

    @property
    def tool_id(self) -> str:
        return self.definition.id

    # ------------------------------------------------------------------
    # Security extension point
    # ------------------------------------------------------------------

    def check_permission(self, action: str, **kwargs: Any) -> ToolResult | None:
        """Check whether an action is permitted by the PermissionManager.

        Returns ``None`` if the action is allowed, or a ``ToolResult``
        with ``status="PERMISSION_DENIED"`` if blocked.

        This is the ONLY security gate. Tools cannot grant permissions
        to themselves — they can only ask the PermissionManager.
        """
        if action in ("write", "write_file"):
            path = kwargs.get("path", "")
            decision = self.permission_manager.can_write(path, explicit_authorization=False)
            if not decision.allowed:
                return ToolResult.permission_denied(self.tool_id, action, decision.reason)

        elif action in ("execute", "execute_command", "run_command"):
            command = kwargs.get("command", self.tool_id)
            decision = self.permission_manager.can_execute_command(command, explicit_authorization=False)
            if not decision.allowed:
                return ToolResult.permission_denied(self.tool_id, action, decision.reason)

        elif action == "download":
            url = kwargs.get("url", "")
            decision = self.permission_manager.can_internet_download(url=url)
            if not decision.allowed:
                return ToolResult.permission_denied(self.tool_id, action, decision.reason)

        elif action == "compile":
            decision = self.permission_manager.can_execute_command(
                f"compile:{self.tool_id}", explicit_authorization=False
            )
            if not decision.allowed:
                return ToolResult.permission_denied(self.tool_id, action, decision.reason)

        elif action == "start_process":
            decision = self.permission_manager.can_launch_allowed_app(self.tool_id)
            if not decision.allowed:
                return ToolResult.permission_denied(self.tool_id, action, decision.reason)

        # If action is not security-sensitive (e.g. read, detect), allow.
        return None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def detect(self) -> ToolResult:
        """Discover whether the tool is installed/available on this machine.

        Must NOT download or install anything.
        """
        ...

    @abstractmethod
    def health_check(self) -> ToolResult:
        """Verify the tool is reachable and functional."""
        ...

    @abstractmethod
    def execute(self, action: str, **kwargs: Any) -> ToolResult:
        """Execute an action through the tool.

        Must call ``check_permission`` before any security-sensitive
        operation.
        """
        ...

    @abstractmethod
    def get_version(self) -> ToolResult:
        """Retrieve the tool version string, if detectable."""
        ...

    def get_capabilities(self) -> list[str]:
        """Return the capability metadata from the definition."""
        return list(self.definition.capabilities)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _timed(self, action: str, fn, **kwargs) -> ToolResult:
        """Run a function and wrap its result in a timed ToolResult."""
        start = time.monotonic()
        try:
            result = fn(**kwargs)
            if not isinstance(result, ToolResult):
                result = ToolResult(
                    success=True,
                    status="SUCCESS",
                    tool_id=self.tool_id,
                    action=action,
                    message=str(result),
                    duration=time.monotonic() - start,
                )
            else:
                result.duration = time.monotonic() - start
            return result
        except Exception as exc:
            return ToolResult.error(self.tool_id, action, str(exc), stderr=str(exc))
