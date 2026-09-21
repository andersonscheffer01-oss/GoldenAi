"""External tools infrastructure for GoldenAI.

This module provides the generic infrastructure for registering,
discovering, health-checking, and (in future phases) executing
external tools such as Ollama, Codex CLI, OpenRouter, Playwright,
Docling, Whisper, FFmpeg, Qdrant, Python, MetaEditor, and MT5.

SECURITY CONTRACT
-----------------
The PermissionManager remains the sole authority for all security
decisions. Tools and adapters NEVER grant permissions to themselves.
Capabilities are metadata only — they do not confer any permission.

Nothing in this module installs, downloads, or executes anything.
"""
from .adapter import ToolAdapter
from .builtin import create_default_registry, get_builtin_tool_definitions
from .capability import ToolCapability
from .definitions import (
    CostPolicy,
    ExecutionMode,
    LocalOrRemote,
    ToolCategory,
    ToolDefinition,
)
from .discovery import discover_all, discover_tool
from .health import (
    format_health_report,
    get_health_summary,
    health_check_all,
    health_check_tool,
)
from .registry import ExternalToolRegistry
from .result import ToolResult
from .status import ToolStatus

__all__ = [
    "ToolAdapter",
    "ToolCapability",
    "ToolCategory",
    "ToolDefinition",
    "ToolResult",
    "ToolStatus",
    "ExternalToolRegistry",
    "ExecutionMode",
    "LocalOrRemote",
    "CostPolicy",
    "discover_tool",
    "discover_all",
    "health_check_tool",
    "health_check_all",
    "format_health_report",
    "get_health_summary",
    "get_builtin_tool_definitions",
    "create_default_registry",
]