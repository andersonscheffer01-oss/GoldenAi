import re
import time
import uuid
from dataclasses import replace
from pathlib import Path

from ..audit import AuditLog
from ..orchestrator.models import DataClassification
from .database import TaskDatabase
from .background import (BackgroundTask, BackgroundTaskStatus, MisfirePolicy,
                          TriggerType)
from .scheduler import BackgroundTaskScheduler
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
        self.scheduler = BackgroundTaskScheduler(self.database, audit=self.audit)

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

    def schedule_background(self, user_request, task_type="computer_use",
                            trigger_type=TriggerType.IMMEDIATE, trigger_config=None,
                            timezone="UTC", max_runs=None,
                            misfire_policy=MisfirePolicy.RUN_ONCE_WHEN_AVAILABLE,
                            security_scope=None):
        trigger_type = TriggerType(trigger_type)
        misfire_policy = MisfirePolicy(misfire_policy)
        self._validate_background_config(trigger_config or {}, security_scope or {})
        now = time.time()
        trigger_config = dict(trigger_config or {})
        next_run_at = None
        if trigger_type == TriggerType.IMMEDIATE:
            next_run_at = now
        elif trigger_type == TriggerType.AFTER_DELAY:
            next_run_at = now + float(trigger_config.get("seconds", trigger_config.get("delay", 0)))
        elif trigger_type == TriggerType.AT_TIME:
            next_run_at = float(trigger_config.get("timestamp", trigger_config.get("at", now)))
        elif trigger_type in {TriggerType.USER_IDLE, TriggerType.CONDITION}:
            next_run_at = now
        task = BackgroundTask.new(
            user_request=user_request, task_type=task_type, trigger_type=trigger_type,
            trigger_config=trigger_config, created_at=now, updated_at=now,
            next_run_at=next_run_at,
            timezone=timezone, max_runs=max_runs, misfire_policy=misfire_policy,
            security_scope=security_scope or {})
        self.database.create_background_task(task)
        self._audit(task.task_id, "background_task_scheduled", {
            "trigger_type": trigger_type.value, "task_type": task_type})
        return task.task_id

    def background(self, task_id):
        return self.database.get_background_task(task_id)

    def background_runs(self, task_id, limit=100):
        return self.database.list_task_runs(task_id, limit)

    def start_scheduler(self, launcher):
        self.scheduler.launcher = launcher
        self.scheduler.start()

    def tick_scheduler(self):
        return self.scheduler.tick()

    def cancel_background(self, task_id):
        return self.scheduler.cancel(task_id)

    def disable_background(self, task_id):
        return self.scheduler.disable(task_id)

    def enable_background(self, task_id):
        return self.scheduler.enable(task_id)

    def create_background_approval(self, task_id, run_id, scope, target,
                                   expires_at, mission_id=None, single_use=True):
        return self.database.create_task_approval(
            task_id, run_id, scope, target, time.time(), expires_at,
            mission_id=mission_id, single_use=single_use)

    def consume_background_approval(self, approval_id, task_id, run_id, scope, target):
        return self.database.consume_task_approval(
            approval_id, task_id, run_id, scope, target, time.time())

    def shutdown(self, wait=True):
        self.scheduler.stop(wait=wait)
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

    @staticmethod
    def _validate_background_config(*configs):
        secret = re.compile(r"(?i)(password|passwd|senha|token|secret|api[_-]?key|authorization|cookie|credential)")
        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if secret.search(str(key)):
                        raise ValueError("Segredo não pode ser persistido em tarefa agendada.")
                    visit(child)
            elif isinstance(value, (bytes, bytearray)):
                raise ValueError("Binário não pode ser persistido em tarefa agendada.")
            elif isinstance(value, str) and (value.lower().startswith("data:") or len(value) > 8000):
                raise ValueError("Payload grande não pode ser persistido em tarefa agendada.")
        for config in configs:
            visit(config)

    def _audit(self, task_id, event, details=None):
        self.audit.add(task_id=task_id, command=event, tool="task_manager",
                       arguments=details or {}, risk="LOW", status="info", result=event)
