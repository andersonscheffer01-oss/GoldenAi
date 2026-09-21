from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.permissions import PermissionManager


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    permission_required: str
    handler: Callable[..., Any]
    classification: str = "read"
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self, permission_manager: PermissionManager | None = None):
        self.permission_manager = permission_manager or PermissionManager()
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name:
            raise ValueError("tool name is required")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def execute(self, name: str, **kwargs: Any) -> Any:
        tool = self.get(name)
        if tool.classification == "write":
            if name == "internet_download":
                url = kwargs.get("url", "")
                dest = kwargs.get("dest_dir", "")
                decision = self.permission_manager.can_internet_download(url, dest)
            else:
                target = kwargs.get("path") or kwargs.get("target") or ""
                decision = self.permission_manager.can_write(target, explicit_authorization=False)
            if not decision.allowed:
                raise PermissionError(decision.reason)
        if tool.classification == "execute":
            decision = self.permission_manager.can_execute_command(name, explicit_authorization=False)
            if not decision.allowed:
                raise PermissionError(decision.reason)
        return tool.handler(**kwargs)
