"""Safe auto-discovery for external tools.

Discovery methods (in priority order):
1. Explicit path from tool definition ``executable`` field
2. Environment variables listed in ``config_hints["env_vars"]``
3. ``shutil.which()`` on PATH for the executable name
4. Known install paths from ``config_hints["known_paths"]``

This module NEVER:
- Scans the entire disk
- Downloads or installs anything
- Grants permissions
- Bypasses the PermissionManager
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .definitions import ToolDefinition
from .result import ToolResult
from .status import ToolStatus


def discover_tool(definition: ToolDefinition) -> ToolResult:
    """Attempt to discover a tool on the local machine.

    Returns a ``ToolResult`` with:
    - ``success=True`` and ``metadata["path"]`` if found
    - ``success=False`` with appropriate status if not found
    """
    tool_id = definition.id
    hints = definition.config_hints or {}

    # 1. Explicit executable path from definition
    if definition.executable:
        exe_path = Path(definition.executable)
        if exe_path.is_absolute() and exe_path.exists():
            return ToolResult(
                success=True,
                status="AVAILABLE",
                tool_id=tool_id,
                action="detect",
                message=f"Found at explicit path: {exe_path}",
                metadata={"path": str(exe_path), "source": "explicit"},
            )
        # Try as a name on PATH
        which = shutil.which(definition.executable)
        if which:
            return ToolResult(
                success=True,
                status="AVAILABLE",
                tool_id=tool_id,
                action="detect",
                message=f"Found on PATH: {which}",
                metadata={"path": which, "source": "PATH"},
            )

    # 2. Environment variables
    env_vars: list[str] = hints.get("env_vars", [])
    for env_var in env_vars:
        env_val = os.environ.get(env_var, "").strip()
        if env_val:
            p = Path(env_val)
            if p.exists():
                return ToolResult(
                    success=True,
                    status="AVAILABLE",
                    tool_id=tool_id,
                    action="detect",
                    message=f"Found via env var {env_var}: {p}",
                    metadata={"path": str(p), "source": f"env:{env_var}"},
                )

    # 3. shutil.which on candidate names
    which_names: list[str] = hints.get("which_names", [])
    if not which_names and definition.executable:
        which_names = [definition.executable]
    for name in which_names:
        which = shutil.which(name)
        if which:
            return ToolResult(
                success=True,
                status="AVAILABLE",
                tool_id=tool_id,
                action="detect",
                message=f"Found on PATH: {which}",
                metadata={"path": which, "source": "PATH"},
            )

    # 4. Known install paths
    known_paths: list[str] = hints.get("known_paths", [])
    for kp in known_paths:
        p = Path(kp)
        if p.exists():
            return ToolResult(
                success=True,
                status="AVAILABLE",
                tool_id=tool_id,
                action="detect",
                message=f"Found at known path: {p}",
                metadata={"path": str(p), "source": "known_path"},
            )

    # 5. API endpoint check (for remote tools)
    api_url = hints.get("api_url", "")
    api_key_env = hints.get("api_key_env", "")
    if api_url:
        if api_key_env and not os.environ.get(api_key_env, "").strip():
            return ToolResult(
                success=False,
                status="NOT_CONFIGURED",
                tool_id=tool_id,
                action="detect",
                message=f"API endpoint configured but {api_key_env} is not set",
                metadata={"api_url": api_url},
            )
        # For local API tools (like Ollama), we can't check reachability
        # here without network. Return NOT_CONFIGURED if no key, else
        # AVAILABLE (actual reachability is checked in health_check).
        if not api_key_env:
            return ToolResult(
                success=True,
                status="AVAILABLE",
                tool_id=tool_id,
                action="detect",
                message=f"Local API endpoint configured: {api_url}",
                metadata={"api_url": api_url, "source": "config"},
            )

    # 6. Python import check (for SDK tools like docling/playwright/faster_whisper/qdrant_client)
    import_name: str = hints.get("import_name", "")
    if import_name:
        try:
            import importlib.util
            import sys as _sys

            candidates = [import_name]
            if "." in import_name:
                candidates.append(import_name.split(".")[0])
            for cand in candidates:
                if importlib.util.find_spec(cand) is not None:
                    return ToolResult(
                        success=True,
                        status="AVAILABLE",
                        tool_id=tool_id,
                        action="detect",
                        message=f"Found as Python package: {cand}",
                        metadata={"import": cand, "source": "import"},
                    )
        except Exception:
            pass

    return ToolResult.not_installed(tool_id, action="detect")


def discover_all(definitions: list[ToolDefinition]) -> dict[str, ToolResult]:
    """Run discovery for a list of tool definitions.

    Returns a mapping of ``tool_id -> ToolResult``.
    """
    return {d.id: discover_tool(d) for d in definitions}