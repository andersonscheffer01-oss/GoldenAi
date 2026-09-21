"""Central registry for external tools.

The ``ExternalToolRegistry`` is the single source of truth for all
external tools known to GoldenAI. It supports:

* register(tool)           — register a tool definition
* unregister(tool_id)       — remove a tool
* disable(tool_id)          — disable without removing
* enable(tool_id)           — re-enable
* get(tool_id)              — fetch by id
* list_all()                — all registered tools
* list_by_category(cat)     — filter by category
* list_by_capability(cap)   — filter by capability
* is_available(tool_id)     — check availability via discovery
* health_check_all()        — run health check on all tools
* select_candidates(cap)    — deterministic candidate selection by capability

This registry does NOT:
- Perform intelligent AI-based selection
- Grant permissions
- Execute tools directly (that requires an adapter)
- Download or install anything
"""
from __future__ import annotations

from typing import Any

from core.permissions import PermissionManager

from .definitions import ToolDefinition
from .discovery import discover_all, discover_tool
from .health import health_check_all, health_check_tool
from .result import ToolResult
from .status import ToolStatus


class ExternalToolRegistry:
    """Central registry for external tool definitions."""

    def __init__(
        self,
        permission_manager: PermissionManager | None = None,
    ) -> None:
        self.permission_manager = permission_manager or PermissionManager()
        self._tools: dict[str, ToolDefinition] = {}
        self._disabled: set[str] = set()
        self._adapters: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        if not tool.id:
            raise ValueError("ToolDefinition id is required")
        self._tools[tool.id] = tool

    def unregister(self, tool_id: str) -> bool:
        """Remove a tool from the registry. Returns True if it existed."""
        existed = tool_id in self._tools
        self._tools.pop(tool_id, None)
        self._disabled.discard(tool_id)
        self._adapters.pop(tool_id, None)
        return existed

    def disable(self, tool_id: str) -> bool:
        """Disable a tool without removing it."""
        if tool_id not in self._tools:
            return False
        self._disabled.add(tool_id)
        self._tools[tool_id].enabled = False
        return True

    def enable(self, tool_id: str) -> bool:
        """Re-enable a previously disabled tool."""
        if tool_id not in self._tools:
            return False
        self._disabled.discard(tool_id)
        self._tools[tool_id].enabled = True
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, tool_id: str) -> ToolDefinition | None:
        """Fetch a tool by id. Returns None if not found."""
        return self._tools.get(tool_id)

    def list_all(self) -> list[ToolDefinition]:
        """Return all registered tools (including disabled)."""
        return list(self._tools.values())

    def list_enabled(self) -> list[ToolDefinition]:
        """Return only enabled tools."""
        return [t for t in self._tools.values() if t.id not in self._disabled and t.enabled]

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """Return all tools in a given category."""
        return [t for t in self._tools.values() if t.category == category]

    def list_by_capability(self, capability: str) -> list[ToolDefinition]:
        """Return all tools that declare a given capability."""
        return [t for t in self._tools.values() if capability in t.capabilities]

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self, tool_id: str) -> bool:
        """Check if a tool is discoverable on this machine."""
        tool = self.get(tool_id)
        if tool is None:
            return False
        if tool_id in self._disabled or not tool.enabled:
            return False
        result = discover_tool(tool)
        return result.success

    def check_availability(self, tool_id: str) -> ToolResult:
        """Return a detailed ToolResult for availability check."""
        tool = self.get(tool_id)
        if tool is None:
            return ToolResult.not_installed(tool_id, action="check_availability")
        if tool_id in self._disabled or not tool.enabled:
            return ToolResult.disabled(tool_id, action="check_availability")
        return discover_tool(tool)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self, tool_id: str) -> ToolResult:
        """Run health check on a single tool."""
        tool = self.get(tool_id)
        if tool is None:
            return ToolResult.not_installed(tool_id, action="health_check")
        if tool_id in self._disabled or not tool.enabled:
            return ToolResult.disabled(tool_id, action="health_check")
        return health_check_tool(tool)

    def health_check_all(self) -> dict[str, ToolResult]:
        """Run health check on all registered tools."""
        return health_check_all(list(self._tools.values()))

    # ------------------------------------------------------------------
    # Candidate selection (deterministic, no AI)
    # ------------------------------------------------------------------

    def select_candidates(self, capability: str, only_available: bool = False) -> list[ToolDefinition]:
        """Select tools that have a given capability.

        This is deterministic selection — no AI ranking.
        Results are sorted by priority (lower = higher priority).

        If ``only_available`` is True, only tools that pass discovery
        are returned.
        """
        candidates = self.list_by_capability(capability)
        if only_available:
            candidates = [c for c in candidates if self.is_available(c.id)]
        return sorted(candidates, key=lambda t: t.priority)

    # ------------------------------------------------------------------
    # Adapter registration (extension point for future)
    # ------------------------------------------------------------------

    def register_adapter(self, tool_id: str, adapter: Any) -> None:
        """Register a concrete adapter for a tool.

        This is the extension point for future tool integration.
        The adapter must implement the ToolAdapter interface.
        """
        if tool_id not in self._tools:
            raise ValueError(f"Cannot register adapter: tool '{tool_id}' is not registered")
        self._adapters[tool_id] = adapter

    def get_adapter(self, tool_id: str) -> Any | None:
        """Get the adapter for a tool, if one is registered."""
        return self._adapters.get(tool_id)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return a summary of the registry state."""
        return {
            "total_tools": len(self._tools),
            "enabled_tools": len(self.list_enabled()),
            "disabled_tools": len(self._disabled),
            "registered_adapters": len(self._adapters),
            "tool_ids": list(self._tools.keys()),
        }