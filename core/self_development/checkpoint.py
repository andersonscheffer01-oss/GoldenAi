"""Checkpoint persistence for self-development tasks.

Allows a task to be resumed after:
- Codex closing
- Ollama stopping
- Computer restart
- Model failure
- Process timeout
- User closing Golden
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from core.config import load_settings

from .models import SelfDevCheckpoint, now_iso


class SelfDevCheckpointStore:
    """Persist and retrieve self-development task checkpoints."""

    def __init__(self, store_dir: str | Path | None = None) -> None:
        settings = load_settings()
        self.store_dir = Path(store_dir) if store_dir else settings.data_dir / "self_dev_checkpoints"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.store_dir / f"{task_id}.json"

    def save(self, checkpoint: SelfDevCheckpoint) -> Path:
        """Save a checkpoint to disk."""
        checkpoint.timestamp = now_iso()
        path = self._path(checkpoint.task_id)
        path.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, task_id: str) -> SelfDevCheckpoint | None:
        """Load a checkpoint by task_id. Returns None if not found."""
        path = self._path(task_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SelfDevCheckpoint.from_dict(data)

    def delete(self, task_id: str) -> bool:
        """Delete a checkpoint. Returns True if it existed."""
        path = self._path(task_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> list[SelfDevCheckpoint]:
        """List all saved checkpoints."""
        results: list[SelfDevCheckpoint] = []
        for path in self.store_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                results.append(SelfDevCheckpoint.from_dict(data))
            except Exception:
                continue
        return sorted(results, key=lambda c: c.timestamp, reverse=True)

    def list_by_status(self, status: str) -> list[SelfDevCheckpoint]:
        """List checkpoints filtered by status."""
        return [c for c in self.list_all() if c.status == status]

    def list_interrupted(self) -> list[SelfDevCheckpoint]:
        """List tasks that were interrupted and can be resumed."""
        resumable = [c for c in self.list_all() if c.status in ("RUNNING", "PLANNED", "WAITING_PERMISSION", "VALIDATING", "INTERRUPTED")]
        return sorted(resumable, key=lambda c: c.timestamp, reverse=True)

    def create(
        self,
        objective: str,
        pending_steps: list[str] | None = None,
    ) -> SelfDevCheckpoint:
        """Create a new task checkpoint."""
        task_id = str(uuid.uuid4())
        checkpoint = SelfDevCheckpoint(
            task_id=task_id,
            objective=objective,
            pending_steps=pending_steps or [],
        )
        self.save(checkpoint)
        return checkpoint

    def update(self, task_id: str, **updates: Any) -> SelfDevCheckpoint | None:
        """Update fields on a checkpoint and persist."""
        checkpoint = self.load(task_id)
        if checkpoint is None:
            return None
        for key, value in updates.items():
            if hasattr(checkpoint, key):
                setattr(checkpoint, key, value)
        self.save(checkpoint)
        return checkpoint