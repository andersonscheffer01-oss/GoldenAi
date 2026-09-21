from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import load_settings


@dataclass
class AuditEvent:
    action_type: str
    status: str
    target: str = ""
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    agent: str = "core"
    input_summary: str = ""
    result: str = ""
    error: str = ""
    duration_ms: int | None = None
    files_changed: list[str] = field(default_factory=list)
    commands_executed: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditLogger:
    def __init__(self, log_dir: str | Path | None = None):
        settings = load_settings()
        self.log_dir = Path(log_dir) if log_dir else settings.logs_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_today(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{today}.jsonl"

    def record(self, event: AuditEvent | dict[str, Any]) -> Path:
        payload = asdict(event) if isinstance(event, AuditEvent) else dict(event)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        payload.setdefault("action_id", str(uuid.uuid4()))
        path = self._path_for_today()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return path
