from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


TASK_STATUSES = {
    "CREATED",
    "ANALYZING",
    "PLANNED",
    "WORKING",
    "VALIDATING",
    "AWAITING_APPROVAL",
    "APPROVED",
    "APPLYING",
    "COMPLETED",
    "FAILED",
    "ROLLED_BACK",
    "CANCELLED",
}


@dataclass
class CodingTask:
    task_id: str
    created_at: str
    updated_at: str
    status: str
    user_request: str
    source_path: str
    source_hash: str
    workspace_path: str
    language: str
    analysis: str = ""
    plan: str = ""
    diff: str = ""
    diff_hash: str = ""
    validation_status: str = ""
    approval_status: str = "PENDING"
    approval_token: str = ""
    checkpoint_id: str = ""
    result: str = ""
    rollback_status: str = ""


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    phase: str
    status: str
    output: str = ""


@dataclass(frozen=True)
class ApprovalToken:
    task_id: str
    source_path: str
    source_hash: str
    diff_hash: str
    timestamp: str = field(default_factory=now_iso)

    def as_token(self) -> str:
        return f"{self.task_id}:{self.source_hash}:{self.diff_hash}:{self.timestamp}"
