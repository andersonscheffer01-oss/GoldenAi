from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_file
from core.config import load_settings
from core.permissions import PermissionManager


@dataclass
class CheckpointRecord:
    checkpoint_id: str
    source_path: str
    checkpoint_path: str
    sha256: str
    reason: str
    origin: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CheckpointService:
    def __init__(self, root: str | Path | None = None, permission_manager: PermissionManager | None = None):
        settings = load_settings()
        self.root = Path(root) if root else settings.backups_dir / "checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.permission_manager = permission_manager or PermissionManager(settings)

    def create_checkpoint(self, path: str | Path, reason: str = "", origin: str = "core") -> CheckpointRecord:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        checkpoint_id = str(uuid.uuid4())
        target_dir = self.root / checkpoint_id
        target_dir.mkdir(parents=True, exist_ok=False)
        target = target_dir / source.name
        shutil.copy2(source, target)
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            source_path=str(source),
            checkpoint_path=str(target),
            sha256=sha256_file(source),
            reason=reason,
            origin=origin,
        )
        (target_dir / "checkpoint.json").write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    def list_checkpoints(self, path: str | Path) -> list[CheckpointRecord]:
        source = str(Path(path))
        records: list[CheckpointRecord] = []
        for meta in self.root.glob("*/checkpoint.json"):
            data = json.loads(meta.read_text(encoding="utf-8"))
            if data.get("source_path") == source:
                records.append(CheckpointRecord(**data))
        return sorted(records, key=lambda item: item.timestamp)

    def restore_checkpoint(self, checkpoint_id: str, explicit_authorization: bool = False) -> Path:
        meta = self.root / checkpoint_id / "checkpoint.json"
        if not meta.exists():
            raise FileNotFoundError(meta)
        record = CheckpointRecord(**json.loads(meta.read_text(encoding="utf-8")))
        decision = self.permission_manager.can_write(
            record.source_path,
            explicit_authorization=explicit_authorization,
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        shutil.copy2(record.checkpoint_path, record.source_path)
        return Path(record.source_path)
