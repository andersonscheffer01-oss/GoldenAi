import re
import uuid
from dataclasses import replace
from pathlib import Path

from ..audit import AuditLog
from ..orchestrator.models import DataClassification
from .database import TaskDatabase
from .models import TaskStatus
from .planner import PlannerContracts
from .runner import BackgroundJobRunner


class TaskManager:
    DB_NAME = "golden_tasks.db"

    def __init__(self, base_dir, max_workers=2):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.database = TaskDatabase(self.base_dir / "jarvis" / self.DB_NAME)
        self.runner = BackgroundJobRunner(self.database, max_workers=max_workers)
        self.audit = AuditLog(self.base_dir / "golden_runtime.db")

    def create(self, plan):
        plan = PlannerContracts.validate(plan)
        self._validate_persistence(plan)
        plan = replace(plan, metadata={**plan.metadata, "goal": plan.goal,
            "risk": plan.risk, "requires_confirmation": plan.requires_confirmation})
        task_id = str(uuid.uuid4())
        self.database.create_task(task_id, plan)
        self._audit(task_id, "task_created", {"steps": len(plan.steps)})
        return task_id

    def start(self, task_id, executor):
        task = self.database.get_task(task_id)
        if not task or task.status not in {TaskStatus.QUEUED, TaskStatus.INTERRUPTED}:
            raise RuntimeError("Tarefa inexistente ou não pode ser iniciada.")
        self._audit(task_id, "task_started")
        return self.runner.submit(task_id, executor)

    def cancel(self, task_id):
        cancelled = self.runner.cancel(task_id)
        if cancelled:
            self._audit(task_id, "task_cancel_requested")
        return cancelled

    def get(self, task_id):
        return self.database.get_task(task_id)

    def steps(self, task_id):
        return self.database.get_steps(task_id)

    def list(self, limit=50, status=None):
        return self.database.list_tasks(limit, status)

    def events(self, task_id, limit=100):
        return self.database.events(task_id, limit)

    def shutdown(self, wait=True):
        self.runner.shutdown(wait=wait)

    @staticmethod
    def _validate_persistence(plan):
        if plan.data_classification == DataClassification.SECRET:
            raise ValueError("Planos SECRET devem usar referências seguras, não persistência direta.")
        secret = re.compile(r"(?i)^(password|passwd|senha|token|secret|api[_-]?key|authorization|cookie|credential)$")
        for step in plan.steps:
            for key, value in step.args.items():
                if secret.match(str(key)) or isinstance(value, (bytes, bytearray)):
                    raise ValueError("Segredo ou binário não pode ser persistido no plano.")
                if isinstance(value, str) and (value.lower().startswith("data:") or len(value) > 8000):
                    raise ValueError("Payload grande ou binário não pode ser persistido no plano.")

    def _audit(self, task_id, event, details=None):
        self.audit.add(task_id=task_id, command=event, tool="task_manager",
                       arguments=details or {}, risk="LOW", status="info", result=event)
