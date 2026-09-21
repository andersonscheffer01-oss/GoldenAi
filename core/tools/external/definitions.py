"""Tool definition model for the external tools infrastructure.

A ``ToolDefinition`` is a declarative description of an external tool.
It contains metadata only — it does NOT execute anything and does NOT
grant any permission. Execution requires a ``ToolAdapter`` and explicit
PermissionManager approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ToolCategory:
    """String constants for tool categories."""

    LLM = "llm"
    CODING_AGENT = "coding_agent"
    BROWSER = "browser"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    VISION = "vision"
    MEMORY = "memory"
    COMPILER = "compiler"
    RUNTIME = "runtime"
    TRADING = "trading"

    @classmethod
    def all(cls) -> list[str]:
        return [
            cls.LLM,
            cls.CODING_AGENT,
            cls.BROWSER,
            cls.DOCUMENT,
            cls.AUDIO,
            cls.VIDEO,
            cls.VISION,
            cls.MEMORY,
            cls.COMPILER,
            cls.RUNTIME,
            cls.TRADING,
        ]


class ExecutionMode:
    """How a tool is invoked."""

    CLI = "cli"
    """Command-line executable."""

    API = "api"
    """HTTP/REST API endpoint."""

    SDK = "sdk"
    """Python library / SDK import."""

    MCP = "mcp"
    """Model Context Protocol server."""

    SUBPROCESS = "subprocess"
    """Launched as a subprocess with stdin/stdout."""

    @classmethod
    def all(cls) -> list[str]:
        return [cls.CLI, cls.API, cls.SDK, cls.MCP, cls.SUBPROCESS]


class LocalOrRemote:
    """Where the tool runs."""

    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"

    @classmethod
    def all(cls) -> list[str]:
        return [cls.LOCAL, cls.REMOTE, cls.HYBRID]


class CostPolicy:
    """Cost classification for a tool."""

    FREE = "free"
    FREE_OR_LOCAL = "free_or_local"
    PAID = "paid"
    FREEMIUM = "freemium"

    @classmethod
    def all(cls) -> list[str]:
        return [cls.FREE, cls.FREE_OR_LOCAL, cls.PAID, cls.FREEMIUM]


@dataclass
class ToolDefinition:
    """Declarative description of an external tool.

    This is metadata only. It does not execute, does not download,
    and does not grant permissions.
    """

    id: str
    name: str
    category: str
    description: str
    provider: str = ""
    execution_mode: str = ExecutionMode.CLI
    local_or_remote: str = LocalOrRemote.LOCAL
    executable: str = ""
    """Executable name or path when applicable (CLI/subprocess)."""

    capabilities: list[str] = field(default_factory=list)
    """Metadata labels of what the tool CAN do. Not permissions."""

    permissions_required: list[str] = field(default_factory=list)
    """Permission types this tool would need if executed."""

    cost_policy: str = CostPolicy.FREE_OR_LOCAL
    enabled: bool = True
    priority: int = 50
    """Lower = higher priority. 0 = highest."""

    version: str = ""
    """Detected version string, empty if not yet detected."""

    config_hints: dict[str, Any] = field(default_factory=dict)
    """Discovery hints: env var names, known paths, API URL, etc."""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ToolDefinition id is required")
        if not self.name:
            raise ValueError("ToolDefinition name is required")
        if not self.category:
            raise ValueError("ToolDefinition category is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "provider": self.provider,
            "execution_mode": self.execution_mode,
            "local_or_remote": self.local_or_remote,
            "executable": self.executable,
            "capabilities": list(self.capabilities),
            "permissions_required": list(self.permissions_required),
            "cost_policy": self.cost_policy,
            "enabled": self.enabled,
            "priority": self.priority,
            "version": self.version,
            "config_hints": dict(self.config_hints),
        }