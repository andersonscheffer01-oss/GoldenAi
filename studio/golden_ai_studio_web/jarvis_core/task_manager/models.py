from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..orchestrator.models import DataClassification, PlanStep


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    BLOCKED = "BLOCKED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"


@dataclass(frozen=True)
class TaskPlan:
    title: str
    steps: tuple[PlanStep, ...]
    description: str = ""
    data_classification: DataClassification = DataClassification.INTERNAL
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    goal: str = ""
    risk: str = "LOW"
    requires_confirmation: bool = False


@dataclass
class TaskRecord:
    id: str
    title: str
    description: str
    status: TaskStatus
    data_classification: DataClassification
    created_at: float
    updated_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    cancel_requested_at: Optional[float] = None
    error: str = ""
    result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0


@dataclass
class StepRecord:
    task_id: str
    step: PlanStep
    position: int
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: str = ""
    result: Any = None
