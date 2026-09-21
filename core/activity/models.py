from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ActivityEvent:
    source: str
    event_type: str
    timestamp: datetime
    session_id: str = ""
    conversation_id: str = ""
    actor: str = ""
    tool: str = ""
    status: str = ""
    permission_class: str = ""
    project_path: str = ""
    model: str = ""
    metadata_json: str = "{}"


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    started_at: datetime
    ended_at: datetime | None = None
