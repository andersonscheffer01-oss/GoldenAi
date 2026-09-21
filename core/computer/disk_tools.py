from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path

from core.permissions import PermissionManager
from .models import DiskUsageInfo


def get_disk_usage(path: str = r"C:\GoldenAI") -> dict:
    manager = PermissionManager()
    decision = manager.can_read_external_safe("disk_usage", path)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason, "path": path}
    resolved = str(Path(path).resolve())
    usage = shutil.disk_usage(resolved)
    used = usage.total - usage.free
    info = DiskUsageInfo(
        path=resolved,
        total_bytes=usage.total,
        used_bytes=used,
        free_bytes=usage.free,
        percent_used=round((used / usage.total) * 100, 2) if usage.total else 0.0,
    )
    data = asdict(info)
    data["ok"] = True
    return data
