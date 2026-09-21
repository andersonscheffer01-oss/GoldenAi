"""Gateway Sessions V1 — Minimal session lifecycle for WebSocket connections.

Session ≠ Memory
Session ≠ Conversation History

Session only controls connection/context/operational state.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


_SESSION_TTL = 3600  # 1 hour
_SESSION_SWEEP_INTERVAL = 60  # 1 minute


def _generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(24)


@dataclass
class Session:
    """Represents an active gateway session."""
    session_id: str
    created_at: float
    last_seen: float
    authenticated: bool = False
    client_info: Optional[dict] = None
    conversation_ref: Optional[str] = None

    def is_expired(self, ttl: float = _SESSION_TTL) -> bool:
        return (time.time() - self.last_seen) > ttl

    def touch(self) -> None:
        self.last_seen = time.time()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "authenticated": self.authenticated,
            "client_info": self.client_info,
            "conversation_ref": self.conversation_ref,
        }


@dataclass
class SessionManager:
    """Manages WebSocket session lifecycle.

    - create: new session with unique ID
    - resume: re-attach to existing session (requires auth validation)
    - touch: update last_seen
    - close: mark session as inactive
    - expire: clean up stale sessions
    """
    _sessions: Dict[str, Session] = field(default_factory=dict)
    _last_sweep: float = field(default_factory=time.time)

    def create(self, client_info: Optional[dict] = None) -> Session:
        """Create a new session."""
        now = time.time()
        session = Session(
            session_id=_generate_session_id(),
            created_at=now,
            last_seen=now,
            client_info=client_info,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """Get session by ID. Returns None if expired or missing."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self._close(session_id)
            return None
        return session

    def resume(self, session_id: str, authenticated: bool = False) -> Optional[Session]:
        """Resume an existing session.

        Requires:
        - Session must exist
        - Session must not be expired
        - If authenticated=False, session will not be marked as authenticated
        """
        session = self.get(session_id)
        if session is None:
            return None
        if authenticated:
            session.authenticated = True
        session.touch()
        return session

    def touch(self, session_id: str) -> bool:
        """Update last_seen timestamp. Returns False if session not found/expired."""
        session = self.get(session_id)
        if session is None:
            return False
        session.touch()
        return True

    def close(self, session_id: str) -> bool:
        """Close a session. Returns False if not found."""
        return self._close(session_id)

    def _close(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def sweep_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = time.time()
        if now - self._last_sweep < _SESSION_SWEEP_INTERVAL:
            return 0
        self._last_sweep = now

        expired = [
            sid for sid, session in self._sessions.items()
            if session.is_expired()
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def count(self) -> int:
        return len(self._sessions)

    def list_sessions(self) -> list:
        return [s.to_dict() for s in self._sessions.values()]
