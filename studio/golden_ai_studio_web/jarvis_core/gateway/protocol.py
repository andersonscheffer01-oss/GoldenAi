"""Gateway Protocol V1 — Typed JSON message envelope.

All messages follow this structure:
{
    "version": 1,
    "id": "<unique_request_id>",
    "type": "<message_type>",
    "timestamp": "<ISO-8601>",
    "session_id": "<optional>",
    "payload": {...}
}

Message types:
  Client → Server: hello, auth, ping, command, confirmation_response, session_open, session_resume, session_close
  Server → Client: auth_ok, auth_error, pong, command_ack, command_result, command_error, event, status, health, confirmation_required, session_info, error
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(str, Enum):
    # Client → Server
    HELLO = "hello"
    AUTH = "auth"
    PING = "ping"
    COMMAND = "command"
    CONFIRMATION_RESPONSE = "confirmation_response"
    SESSION_OPEN = "session_open"
    SESSION_RESUME = "session_resume"
    SESSION_CLOSE = "session_close"

    # Server → Client
    AUTH_OK = "auth_ok"
    AUTH_ERROR = "auth_error"
    PONG = "pong"
    COMMAND_ACK = "command_ack"
    COMMAND_RESULT = "command_result"
    COMMAND_ERROR = "command_error"
    EVENT = "event"
    STATUS = "status"
    HEALTH = "health"
    CONFIRMATION_REQUIRED = "confirmation_required"
    SESSION_INFO = "session_info"
    ERROR = "error"


# Messages that require authentication
REQUIRES_AUTH = frozenset({
    MessageType.COMMAND,
    MessageType.CONFIRMATION_RESPONSE,
    MessageType.SESSION_OPEN,
    MessageType.SESSION_RESUME,
    MessageType.SESSION_CLOSE,
})

# Messages that are always allowed (pre-auth)
ALWAYS_ALLOWED = frozenset({
    MessageType.HELLO,
    MessageType.AUTH,
    MessageType.PING,
})

PROTOCOL_VERSION = 1
MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB


@dataclass
class GatewayMessage:
    """Typed message envelope for the WebSocket protocol."""
    type: MessageType
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    version: int = PROTOCOL_VERSION
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayMessage":
        msg_type = data.get("type", "")
        try:
            msg_type = MessageType(msg_type)
        except ValueError:
            raise ValueError(f"Unknown message type: {msg_type}")
        return cls(
            type=msg_type,
            id=data.get("id", uuid.uuid4().hex),
            version=data.get("version", PROTOCOL_VERSION),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            session_id=data.get("session_id"),
            payload=data.get("payload", {}),
        )

    @classmethod
    def from_json(cls, raw: str) -> "GatewayMessage":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        if not isinstance(data, dict):
            raise ValueError("Message must be a JSON object")
        return cls.from_dict(data)

    def reply(self, type: MessageType, payload: Dict[str, Any],
              session_id: Optional[str] = None) -> "GatewayMessage":
        """Create a reply preserving the request correlation ID."""
        return GatewayMessage(
            type=type,
            id=self.id,
            session_id=session_id or self.session_id,
            payload=payload,
        )


def make_error_reply(request_id: str, code: str, message: str,
                     retryable: bool = False,
                     session_id: Optional[str] = None) -> GatewayMessage:
    """Create a structured error reply."""
    return GatewayMessage(
        type=MessageType.ERROR,
        id=request_id,
        session_id=session_id,
        payload={
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    )
