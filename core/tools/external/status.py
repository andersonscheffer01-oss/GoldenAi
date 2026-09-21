"""Tool status enumeration for the external tools infrastructure.

These statuses represent the availability state of an external tool
on the current machine. They are metadata only and NEVER grant
permissions or bypass the PermissionManager.
"""
from __future__ import annotations

from enum import Enum


class ToolStatus(str, Enum):
    """Availability state of an external tool."""

    AVAILABLE = "AVAILABLE"
    """Tool is installed and reachable."""

    NOT_INSTALLED = "NOT_INSTALLED"
    """Tool binary/entrypoint was not found on the system."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    """Tool requires configuration (API key, endpoint, etc.) that is missing."""

    UNAVAILABLE = "UNAVAILABLE"
    """Tool is installed but not running or not responding."""

    ERROR = "ERROR"
    """Detection or health check raised an unexpected error."""

    DISABLED = "DISABLED"
    """Tool is explicitly disabled in configuration."""

    BLOCKED_PAID = "BLOCKED_PAID"
    """Tool requires payment and paid tools are blocked by policy."""

    @classmethod
    def from_str(cls, value: str) -> "ToolStatus":
        """Parse a status string, defaulting to NOT_INSTALLED on failure."""
        try:
            return cls(value.upper())
        except (ValueError, AttributeError):
            return cls.NOT_INSTALLED