from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentTaskStatus(str, Enum):
    CREATED = "CREATED"
    ROUTED = "ROUTED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class Task:
    task_id: str
    description: str
    context: dict[str, Any] = field(default_factory=dict)
    status: AgentTaskStatus = AgentTaskStatus.CREATED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(cls, description: str, context: dict[str, Any] | None = None) -> "Task":
        return cls(task_id=f"agent_task_{uuid.uuid4()}", description=description, context=context or {})


@dataclass
class AgentResult:
    agent: str
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence_level: str = ""
    warnings: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentContext:
    tools: dict[str, Any] = field(default_factory=dict)
    memory: Any = None
    coding_service: Any = None
    root: str = r"C:\GoldenAI"


class BaseAgent:
    name = "base"
    role = "base agent"
    write_enabled = False

    def __init__(self, context: AgentContext | None = None):
        self.context = context or AgentContext()

    def can_handle(self, task: Task) -> bool:
        return False

    def plan(self, task: Task) -> list[str]:
        return []

    def execute(self, task: Task) -> AgentResult:
        return AgentResult(self.name, AgentTaskStatus.COMPLETED.value, "Agente sem acao especializada nesta V1.")

    def review(self, result: AgentResult) -> AgentResult:
        return result

    def _tool(self, name: str, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
        if name not in self.context.tools:
            return None, {"tool": name, "status": "UNAVAILABLE", "arguments": kwargs}
        result = self.context.tools[name](**kwargs)
        return result, {"tool": name, "status": "COMPLETED", "arguments": kwargs}

    def _text(self, task: Task) -> str:
        return str(task.description or "").lower()
