"""Safe, serializable models for persistent background tasks."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TriggerType(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    AT_TIME = "AT_TIME"
    AFTER_DELAY = "AFTER_DELAY"
    RECURRING = "RECURRING"
    USER_IDLE = "USER_IDLE"
    CONDITION = "CONDITION"


class BackgroundTaskStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    WAITING_TRIGGER = "WAITING_TRIGGER"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    WAITING_USER_IDLE = "WAITING_USER_IDLE"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    DISABLED = "DISABLED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    WAITING_USER_IDLE = "WAITING_USER_IDLE"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MisfirePolicy(str, Enum):
    RUN_ONCE_WHEN_AVAILABLE = "RUN_ONCE_WHEN_AVAILABLE"
    SKIP_IF_MISSED = "SKIP_IF_MISSED"


class ConditionType(str, Enum):
    FILE_EXISTS = "FILE_EXISTS"
    FILE_NOT_EXISTS = "FILE_NOT_EXISTS"
    APP_RUNNING = "APP_RUNNING"
    APP_NOT_RUNNING = "APP_NOT_RUNNING"
    USER_IDLE = "USER_IDLE"
    TIME_WINDOW = "TIME_WINDOW"
    MISSION_STATUS = "MISSION_STATUS"
    LOCAL_SERVICE_AVAILABLE = "LOCAL_SERVICE_AVAILABLE"


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def _json_safe(value: Any) -> Any:
    json.dumps(value, ensure_ascii=False)
    return value


@dataclass(frozen=True)
class BackgroundTask:
    task_id: str
    user_request: str
    task_type: str
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = field(default_factory=dict)
    status: BackgroundTaskStatus = BackgroundTaskStatus.SCHEDULED
    created_at: float = 0.0
    updated_at: float = 0.0
    next_run_at: float | None = None
    last_run_at: float | None = None
    timezone: str = "UTC"
    enabled: bool = True
    run_count: int = 0
    max_runs: int | None = None
    misfire_policy: MisfirePolicy = MisfirePolicy.RUN_ONCE_WHEN_AVAILABLE
    security_scope: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 2

    def __post_init__(self):
        if not _SAFE_ID.match(self.task_id):
            raise ValueError("task_id inválido")
        if not isinstance(self.user_request, str) or not self.user_request.strip():
            raise ValueError("user_request obrigatório")
        if not isinstance(self.trigger_config, dict) or not isinstance(self.security_scope, dict):
            raise ValueError("configurações devem ser objetos JSON")
        _json_safe(self.trigger_config)
        _json_safe(self.security_scope)
        if self.max_runs is not None and int(self.max_runs) < 1:
            raise ValueError("max_runs deve ser positivo")

    @classmethod
    def new(cls, user_request: str, task_type: str, trigger_type: TriggerType,
            trigger_config=None, **kwargs):
        return cls(task_id=str(uuid.uuid4()), user_request=user_request,
                   task_type=task_type, trigger_type=trigger_type,
                   trigger_config=dict(trigger_config or {}), **kwargs)


__all__ = ["BackgroundTask", "BackgroundTaskStatus", "ConditionType", "MisfirePolicy",
           "RunStatus", "TriggerType"]
