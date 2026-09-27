import re
import time
import uuid
from dataclasses import replace
from pathlib import Path

from ..audit import AuditLog
from ..models import Risk, Tool
from ..orchestrator.models import DataClassification
from ..security import SecurityManager
from .database import TaskDatabase
from .background import (BackgroundTask, BackgroundTaskStatus, MisfirePolicy,
                          RunStatus, TriggerType)
from .scheduler import BackgroundTaskScheduler
from .models import TaskStatus
from .planner import PlannerContracts
from .runner import BackgroundJobRunner
from .condition_executor import ConditionAuditExecutor
from .control_center import BackgroundControlCenter


class TaskManager:
    DB_NAME = "golden_tasks.db"

    def __init__(self, base_dir, max_workers=2, security=None):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.database = TaskDatabase(self.base_dir / "jarvis" / self.DB_NAME)
        self.runner = BackgroundJobRunner(self.database, max_workers=max_workers)
        self.audit = AuditLog(self.base_dir / "golden_runtime.db")
        # JarvisService passes its canonical manager; standalone TaskManager
        # instances keep the same policy for isolated tests and tooling.
        self.security = security or SecurityManager()
        self.background_handlers = {
            "condition_audit": ConditionAuditExecutor(self.audit),
        }
        self.scheduler = BackgroundTaskScheduler(self.database, audit=self.audit)
        self.control_center = BackgroundControlCenter(self.database, self.scheduler)

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

    def background_control_snapshot(self, **kwargs):
        return self.control_center.get_snapshot(**kwargs)

    def execute_background_task(self, task, run):
        """Dispatch a background task to its explicit non-GUI handler."""
        handler = self.background_handlers.get(str(task.task_type).lower())
        if handler is None:
            return {"ok": False, "error_code": "UNSUPPORTED_TASK_TYPE"}
        return handler(task, run)

    def reconcile_background_mission_state(self, task_id, mission_result):
        """Project a durable mission pause onto its existing scheduled run."""
        if not task_id or not isinstance(mission_result, dict):
            return ""
        mission = mission_result.get("mission") or {}
        mission_id = str(mission_result.get("mission_id") or mission.get("mission_id") or "")
        runs = self.database.list_task_runs(str(task_id))
        run = next((item for item in runs if not mission_id or
                    str(item.get("mission_id") or "") == mission_id), None)
        if run is None:
            return ""
        result_error = str(mission_result.get("error") or mission.get("error") or "").upper()
        pause_reason = str(mission_result.get("pause_reason") or
                           mission.get("pause_reason") or "").upper()
        if pause_reason == "USER_ACTIVITY" or result_error in {
                "USER_ACTIVITY_DETECTED", "MISSION_PAUSED_FOR_USER_ACTIVITY"}:
            self.database.update_task_run(
                run["run_id"], status=RunStatus.WAITING_USER_IDLE,
                claim_token=None, claimed_by=None, claim_expires_at=None,
                error_code="USER_ACTIVITY_DETECTED",
                error_message="mission paused for user activity")
            self.database.update_background_task(
                str(task_id), status=BackgroundTaskStatus.WAITING_USER_IDLE)
            self._audit(str(task_id), "background_task_reconciled_user_idle", {
                "run_id": run["run_id"], "mission_id": mission_id})
            return RunStatus.WAITING_USER_IDLE.value
        confirmation_required = bool(mission_result.get("confirmation_required"))
        confirmation_required = confirmation_required or result_error == "USER_CONFIRMATION_REQUIRED"
        confirmation_required = confirmation_required or str(
            mission.get("status") or "").upper() == "WAITING_CONFIRMATION"
        if confirmation_required:
            self.database.update_task_run(
                run["run_id"], status=RunStatus.WAITING_CONFIRMATION,
                claim_token=None, claimed_by=None, claim_expires_at=None)
            self.database.update_background_task(
                str(task_id), status=BackgroundTaskStatus.WAITING_CONFIRMATION)
            self._audit(str(task_id), "background_task_reconciled_confirmation", {
                "run_id": run["run_id"], "mission_id": mission_id})
            return RunStatus.WAITING_CONFIRMATION.value
        return ""

    def start_scheduler(self, launcher, idle_provider=None):
        self.scheduler.launcher = launcher
        if idle_provider is not None:
            self.scheduler.conditions.idle_provider = idle_provider
        self.scheduler.start()

    def tick_scheduler(self):
        return self.scheduler.tick()

    def cancel_background(self, task_id, confirmation_token=None, actor="background_control"):
        return self.control_background("cancel", task_id, confirmation_token, actor)

    def pause_background(self, task_id, confirmation_token=None, actor="background_control"):
        return self.control_background("pause", task_id, confirmation_token, actor)

    def resume_background(self, task_id, confirmation_token=None, actor="background_control"):
        return self.control_background("resume", task_id, confirmation_token, actor)

    def control_background(self, action, task_id, confirmation_token=None,
                           actor="background_control"):
        action = str(action).lower()
        task_id = str(task_id)
        risk = Risk.HIGH if action == "cancel" else Risk.MEDIUM
        tool = Tool(f"background_task_{action}", f"Controla task em background: {action}",
                    lambda **_kwargs: {}, risk=risk, confirmation=(action == "cancel"),
                    parameters={"task_id": str})
        arguments = {"task_id": task_id, "action": action, "actor": str(actor)}
        if confirmation_token:
            item = self.security.consume(confirmation_token)
            if not item or item.get("tool") != tool.name or item.get("arguments") != arguments:
                return {"success": False, "code": "INVALID_CONFIRMATION",
                        "task_id": task_id, "requested_action": action}
        else:
            decision = self.security.decision(tool, risk=risk,
                                              requires_confirmation=tool.confirmation)
            if decision == "deny":
                self._audit(task_id, "BACKGROUND_TASK_CONTROL_DENIED", arguments)
                return {"success": False, "code": "SECURITY_DENIED",
                        "task_id": task_id, "requested_action": action}
            if decision == "confirm":
                token = self.security.create_confirmation(tool, arguments, action, risk)
                return {"success": False, "confirmation_required": True, "token": token,
                        "task_id": task_id, "requested_action": action,
                        "code": "CONFIRMATION_REQUIRED"}
        result = self.control_center.control_task(action, task_id)
        if result.get("success") and result.get("new_state") != result.get("previous_state"):
            event_name = {"pause": "BACKGROUND_TASK_PAUSED",
                          "resume": "BACKGROUND_TASK_RESUMED",
                          "cancel": "BACKGROUND_TASK_CANCELLED"}[action]
            self._audit(task_id, event_name, {
                "action": action, "previous_state": result.get("previous_state"),
                "new_state": result.get("new_state"), "actor": str(actor),
                "active_run_state": result.get("active_run_state")})
        return result

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
