# ═══════════════════════════════════════════════════════════════════
# memory/session.py
# √ (Golden Jarvis 2.0) Sessão de memória
# ═══════════════════════════════════════════════════════════════════
import uuid
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .database import Database
from .models import SessionInfo


class SessionMemory:
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"

    def __init__(self, db: Database):
        self.db = db
        self._current_id: Optional[str] = None

    def start_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        now = time.time()
        session_id = str(uuid.uuid4())
        self._current_id = session_id
        self.db.session_upsert(session_id, now, now, None, SessionMemory.STATUS_ACTIVE, metadata or {})
        return session_id

    def end_session(self) -> Optional[str]:
        if not self._current_id:
            return None
        ended_at = time.time()
        self.db.session_upsert(self._current_id, self._current_id, ended_at, ended_at, SessionMemory.STATUS_ENDED, {})
        session_id, self._current_id = self._current_id, None
        return session_id

    def current(self) -> Optional[SessionInfo]:
        if not self._current_id:
            return None
        row = self.db.session_get(self._current_id)
        if not row:
            return None
        return SessionInfo(
            session_id=row["session_id"],
            created_at=row["created_at"],
            last_activity=row["last_activity"],
            ended_at=row["ended_at"],
            status=row["status"],
            metadata=row["metadata"],
        )

    def refresh_activity(self) -> None:
        if self._current_id:
            self.db.session_upsert(self._current_id, self._current_id, time.time(), None,
                                   SessionMemory.STATUS_ACTIVE, {})

    def list_recent(self, limit: int = 20) -> list[SessionInfo]:
        rows = self.db.session_list(limit)
        return [
            SessionInfo(
                session_id=r["session_id"],
                created_at=r["created_at"],
                last_activity=r["last_activity"],
                ended_at=r["ended_at"],
                status=r["status"],
                metadata=r["metadata"],
            )
            for r in rows
        ]
