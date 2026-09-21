from __future__ import annotations

from pathlib import Path

from core.permissions import PermissionManager


def is_safe_external_read_path(path: str) -> dict:
    decision = PermissionManager().can_read_external_safe("mt5_read", Path(path))
    return {"path": path, "allowed": decision.allowed, "reason": decision.reason}
