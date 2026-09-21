from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PermissionMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    ASK = "ASK"
    AUTO_SAFE = "AUTO_SAFE"
    FULL = "FULL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    CANCELLED = "CANCELLED"


@dataclass
class ExecutionEvent:
    category: str
    action: str
    status: str
    summary: str
    task_id: str = ""
    details: str = ""
    target: str = ""
    agent: str = ""
    tool_name: str = ""
    permission_level: str = ""
    risk_level: str = ""
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=now_iso)


@dataclass
class ApprovalRequest:
    task_id: str
    operation_key: str
    action: str
    target: str
    reason: str
    risk_level: str
    permission_level: str
    status: str = "PENDING"
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=now_iso)
    decided_at: str = ""
    scope: str = ""
    consumed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    reason: str
    mode: str
    status: str
    request_id: str = ""
    risk_level: str = ""
