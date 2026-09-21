from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .metrics import ActivityMetrics
from .models import ActivityEvent
from .repository import ActivityRepository


class ActivityService:
    def __init__(
        self,
        root: str | Path = r"C:\GoldenAI",
        db_path: str | Path | None = None,
        history_path: str | Path | None = None,
        logs_dir: str | Path | None = None,
    ):
        self.root = Path(root)
        self.db_path = Path(db_path) if db_path else self.root / "data" / "golden_ai.db"
        self.history_path = Path(history_path) if history_path else self.root / "studio" / "historico_v2.json"
        self.logs_dir = Path(logs_dir) if logs_dir else self.root / "logs"
        self.repo = ActivityRepository(self.db_path)
        self.metrics = ActivityMetrics(self.repo)
        self.last_error = ""
        self._history_ingested_lines = 0
        self._audit_ingested: dict[str, int] = {}

    def new_session_id(self) -> str:
        return str(uuid.uuid4())

    def start_session(self, session_id: str) -> None:
        self.repo.start_session(session_id)

    def end_session(self, session_id: str) -> None:
        self.repo.end_session(session_id)

    def record_message(
        self,
        conversation_id: str,
        actor: str,
        text: str = "",
        project_path: str = "",
        model: str = "",
        session_id: str = "",
    ) -> None:
        timestamp = datetime.now(timezone.utc)
        metadata = {"length": len(str(text or ""))}
        event = ActivityEvent(
            source="studio",
            event_type="message",
            timestamp=timestamp,
            session_id=session_id,
            conversation_id=str(conversation_id or ""),
            actor=str(actor or ""),
            project_path=str(project_path or ""),
            model=str(model or ""),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        key = f"studio-message:{session_id}:{conversation_id}:{actor}:{timestamp.isoformat()}:{metadata['length']}"
        self.repo.insert_event(key, event)

    def refresh_from_sources(self) -> None:
        self.last_error = ""
        try:
            self._ingest_history()
        except Exception as exc:
            self.last_error = f"Historico indisponivel: {exc}"
        try:
            self._ingest_audit_logs()
        except Exception as exc:
            self.last_error = (self.last_error + " | " if self.last_error else "") + f"Audit indisponivel: {exc}"

    def dashboard(self, current_model: str = "") -> dict:
        self.refresh_from_sources()
        return {
            "summary": self.metrics.summary(),
            "heatmap": self.metrics.heatmap(),
            "tools": self.metrics.tool_ranking(),
            "security": self.metrics.security(),
            "projects": self.metrics.project_ranking(),
            "categories": self.metrics.categories(),
            "models": self.metrics.model_usage(current_model),
            "session_time": self.metrics.session_time(),
            "tokens": self.metrics.token_usage(),
            "last_error": self.last_error,
        }

    def _history_timestamp(self, conversation_id: str, index: int) -> datetime:
        try:
            ms = int(str(conversation_id))
            return datetime.fromtimestamp((ms / 1000.0) + index, tz=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _ingest_history(self) -> None:
        if not self.history_path.exists():
            return
        raw_text = self.history_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if not isinstance(data, list):
            return
        items: list[tuple[str, ActivityEvent]] = []
        for conv in data:
            if not isinstance(conv, dict):
                continue
            conv_id = str(conv.get("id", ""))
            project_path = str(conv.get("context", "") or "")
            messages = conv.get("messages", [])
            if not isinstance(messages, list):
                continue
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    continue
                actor = str(message.get("role", ""))
                if actor not in {"user", "assistant"}:
                    continue
                text = str(message.get("text", "") or "")
                timestamp = self._history_timestamp(conv_id, index)
                event = ActivityEvent(
                    source="history",
                    event_type="message",
                    timestamp=timestamp,
                    conversation_id=conv_id,
                    actor=actor,
                    project_path=project_path,
                    metadata_json=json.dumps({"length": len(text)}, ensure_ascii=False),
                )
                key = f"history:{conv_id}:{index}:{actor}:{len(text)}"
                items.append((key, event))
        self.repo.insert_events_batch(items)

    def _audit_timestamp(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)

    def _ingest_audit_logs(self) -> None:
        if not self.logs_dir.exists():
            return
        for path in sorted(self.logs_dir.glob("audit_*.jsonl")):
            ingested = self._audit_ingested.get(path.name, 0)
            items: list[tuple[str, ActivityEvent]] = []
            line_index = 0
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    line_index = index + 1
                    if index < ingested:
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    event = ActivityEvent(
                        source="audit",
                        event_type="tool",
                        timestamp=self._audit_timestamp(item.get("timestamp", "")),
                        session_id=str(item.get("session_id", "")),
                        tool=str(item.get("tool", "")),
                        status=str(item.get("status", "")),
                        permission_class=str(item.get("permission_class", "")),
                        project_path=str(item.get("target", "")),
                        metadata_json=json.dumps({
                            "action_type": item.get("action_type", ""),
                            "duration_ms": item.get("duration_ms"),
                        }, ensure_ascii=False),
                    )
                    key = f"audit:{path.name}:{item.get('action_id') or index}"
                    items.append((key, event))
            self.repo.insert_events_batch(items)
            self._audit_ingested[path.name] = line_index
