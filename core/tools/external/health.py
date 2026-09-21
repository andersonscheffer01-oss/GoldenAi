"""Health check for external tools.

Produces a simple status report showing whether each registered
tool is available, not installed, not configured, etc.

The health check uses the discovery module and does NOT:
- Install anything
- Download anything
- Grant permissions
- Bypass the PermissionManager
"""
from __future__ import annotations

from typing import Any

from .definitions import ToolDefinition
from .discovery import discover_tool
from .result import ToolResult
from .status import ToolStatus


def health_check_tool(definition: ToolDefinition) -> ToolResult:
    """Run a health check on a single tool.

    For CLI tools: checks if the executable is discoverable.
    For API tools: checks if the endpoint is configured.
    For SDK tools: checks if the module can be imported.
    """
    # First, run discovery
    result = discover_tool(definition)

    # If discovery failed, return that result
    if not result.success:
        return result

    # For SDK tools, try importing the module
    if definition.execution_mode == "sdk":
        module_name = definition.config_hints.get("import_name", "")
        if module_name:
            try:
                __import__(module_name)
                result.metadata["importable"] = True
            except ImportError:
                result.success = False
                result.status = "NOT_INSTALLED"
                result.message = f"Module '{module_name}' is not importable"
                result.metadata["importable"] = False
                return result

    # For local API tools (like Ollama), we could try a quick HTTP check
    # but that requires network access which is gated by PermissionManager.
    # In this infrastructure phase, we just report discovery status.
    result.action = "health_check"
    return result


def health_check_all(definitions: list[ToolDefinition]) -> dict[str, ToolResult]:
    """Run health check for all tools.

    Returns a mapping of ``tool_id -> ToolResult``.
    """
    return {d.id: health_check_tool(d) for d in definitions}


def format_health_report(results: dict[str, ToolResult]) -> str:
    """Format health check results as a human-readable report.

    Example output::

        Ollama         AVAILABLE
        Codex CLI      NOT_INSTALLED
        OpenRouter     NOT_CONFIGURED
        ...
    """
    lines: list[str] = []
    for tool_id, result in results.items():
        name = tool_id.replace("_", " ").title()
        status = result.status
        lines.append(f"{name:<20} {status}")
    return "\n".join(lines)


def get_health_summary(results: dict[str, ToolResult]) -> dict[str, Any]:
    """Return a structured summary of health check results."""
    available = [tid for tid, r in results.items() if r.success]
    missing = [tid for tid, r in results.items() if not r.success]
    return {
        "total": len(results),
        "available": len(available),
        "missing": len(missing),
        "available_tools": available,
        "missing_tools": missing,
        "details": {tid: r.to_dict() for tid, r in results.items()},
    }