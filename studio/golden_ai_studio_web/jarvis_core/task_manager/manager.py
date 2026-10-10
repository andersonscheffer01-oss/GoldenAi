import re
import hashlib
import threading
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
from ..computer_use_mission import ActionState, MissionCheckpointStore
from .paths import resolve_task_database_path


class TaskManager:
    DB_NAME = "golden_tasks.db"

    def __init__(self, base_dir, max_workers=2, security=None,
                 runtime_mode="compatibility", database_path=None):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.database_resolution = resolve_task_database_path(
            self.base_dir, database_path, runtime_mode)
        self.database = TaskDatabase(
            self.database_resolution.resolved_path,
            runtime_classification=self.database_resolution.classification)
        self.runner = BackgroundJobRunner(self.database, max_workers=max_workers)
        self.audit = AuditLog(self.base_dir / "golden_runtime.db")
        # JarvisService passes its canonical manager; standalone TaskManager
        # instances keep the same policy for isolated tests and tooling.
        self.security = security or SecurityManager()
        self.background_handlers = {
            "condition_audit": ConditionAuditExecutor(self.audit),
        }
        self.scheduler = BackgroundTaskScheduler(self.database, audit=self.audit)
        self.control_center = BackgroundControlCenter(
            self.database, self.scheduler,
            retry_eligibility=lambda run_id: self.get_retry_eligibility(
                run_id, record_audit=False),
            recovery_eligibility=lambda run_id: self.get_recovery_eligibility(
                run_id, record_audit=False))
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._monitor_lock = threading.RLock()

    # The monitor is represented by one canonical background-task record per
    # actor. Its execution loop is intentionally owned by a later integration;
    # these methods only establish durable, race-safe lifecycle state.
    MONITOR_TASK_TYPE = "golden_trend_monitor"
    MONITOR_STATES = {"STOPPED", "STARTING", "RUNNING", "PAUSED", "BACKOFF", "ERROR"}

    @classmethod
    def _monitor_task_id(cls, actor_id):
        actor = str(actor_id or "").strip()
        if not actor.startswith("device:"):
            raise ValueError("actor_id do monitor deve ser uma identidade device")
        digest = hashlib.sha256(actor.encode("utf-8")).hexdigest()[:32]
        return f"monitor:{digest}"

    def _monitor_task(self, actor_id):
        task_id = self._monitor_task_id(actor_id)
        task = self.database.get_background_task(task_id)
        if task is None or task.task_type != self.MONITOR_TASK_TYPE:
            return None
        if task.security_scope.get("actor_id") != str(actor_id):
            return None
        return task

    @staticmethod
    def _monitor_config(task):
        config = dict(task.trigger_config or {}) if task else {}
        state = str(config.get("monitor_state") or "STOPPED").upper()
        return config, state if state in TaskManager.MONITOR_STATES else "ERROR"

    def monitor_status(self, actor_id):
        """Return durable monitor state without starting work or reading MT5."""
        with self._monitor_lock:
            task = self._monitor_task(actor_id)
            if task is None:
                return {"ok": True, "found": False, "actor_id": str(actor_id),
                        "monitor_state": "STOPPED", "scan_state": "UNKNOWN",
                        "mt5_availability": "UNKNOWN", "candle_freshness": "UNKNOWN"}
            config, state = self._monitor_config(task)
            return {
                "ok": True,
                "found": True, "task_id": task.task_id, "actor_id": str(actor_id),
                "monitor_state": state,
                "scan_state": config.get("scan_state", "UNKNOWN"),
                "mt5_availability": config.get("mt5_availability", "UNKNOWN"),
                "candle_freshness": config.get("candle_freshness", "UNKNOWN"),
                "last_confirmed_batch": config.get("last_confirmed_batch"),
                "scan_id": config.get("scan_id", ""),
                "base_revision": config.get("base_revision"),
                "next_cycle_at": config.get("next_cycle_at"),
                "recoverable_error": config.get("recoverable_error"),
                "authorized_universe_count": config.get("authorized_universe_count", 31),
                "batch_size": config.get("batch_size", 4),
                "enabled": bool(task.enabled),
            }

    def start_market_monitor(self, actor_id, authorized_universe_count=31,
                             batch_size=4, next_cycle_at=None, scan_id="",
                             base_revision=None):
        """Create or resume the single durable monitor record for an actor."""
        with self._monitor_lock:
            actor = str(actor_id)
            task_id = self._monitor_task_id(actor)
            task = self._monitor_task(actor)
            now = time.time()
            if task is None:
                config = {
                    "monitor_schema_version": 1, "monitor_state": "STARTING",
                    "scan_state": "UNKNOWN", "mt5_availability": "UNKNOWN",
                    "candle_freshness": "UNKNOWN", "authorized_universe_count": int(authorized_universe_count),
                    "batch_size": min(4, max(1, int(batch_size))),
                    "scan_id": str(scan_id or ""),
                    "base_revision": base_revision,
                    "last_confirmed_batch": None, "next_cycle_at": next_cycle_at,
                    "recoverable_error": None,
                }
                task = BackgroundTask(
                    task_id=task_id,
                    user_request="Monitoramento GoldenAI read-only",
                    task_type=self.MONITOR_TASK_TYPE,
                    trigger_type=TriggerType.CONDITION,
                    trigger_config=config, status=BackgroundTaskStatus.SCHEDULED,
                    created_at=now, updated_at=now, next_run_at=None,
                    enabled=False, security_scope={"actor_id": actor,
                                                   "read_only": True,
                                                   "execution_authority": "NONE"})
                self.database.create_background_task(task)
            else:
                config, _ = self._monitor_config(task)
                config.update({"monitor_state": "STARTING",
                               "authorized_universe_count": int(authorized_universe_count),
                               "batch_size": min(4, max(1, int(batch_size))),
                               "scan_id": str(scan_id or config.get("scan_id") or ""),
                               "base_revision": base_revision if base_revision is not None
                               else config.get("base_revision"),
                               "next_cycle_at": next_cycle_at,
                               "recoverable_error": None})
                self.database.update_background_task(task_id, trigger_config=config,
                                                     status=BackgroundTaskStatus.SCHEDULED,
                                                     enabled=False)
            config["monitor_state"] = "RUNNING"
            self.database.update_background_task(task_id, trigger_config=config,
                                                 status=BackgroundTaskStatus.SCHEDULED,
                                                 enabled=False)
            return self.monitor_status(actor)

    def pause_market_monitor(self, actor_id, reason="operator_requested"):
        return self._set_market_monitor_state(actor_id, "PAUSED", reason=reason)

    def resume_market_monitor(self, actor_id):
        return self._set_market_monitor_state(actor_id, "RUNNING")

    def stop_market_monitor(self, actor_id, reason="operator_requested"):
        return self._set_market_monitor_state(actor_id, "STOPPED", reason=reason)

    def _set_market_monitor_state(self, actor_id, state, reason=None):
        if state not in self.MONITOR_STATES:
            raise ValueError("estado de monitor inválido")
        with self._monitor_lock:
            task = self._monitor_task(actor_id)
            if task is None:
                return {"found": False, "monitor_state": "STOPPED"}
            config, _ = self._monitor_config(task)
            config["monitor_state"] = state
            if reason:
                config["state_reason"] = str(reason)[:200]
            self.database.update_background_task(
                task.task_id, trigger_config=config,
                status=(BackgroundTaskStatus.PAUSED if state == "PAUSED"
                        else BackgroundTaskStatus.SCHEDULED),
                enabled=False)
            return self.monitor_status(actor_id)

    def process_market_monitor_batch(self, actor_id, assets, rank_batch,
                                     persist_scan, batch_index=None,
                                     next_cycle_at=None):
        """Run one bounded canonical ranking batch, then persist its cursor.

        ``rank_batch`` and ``persist_scan`` are injected by JarvisService so
        this coordinator does not gain a second market reader or persistence
        authority. No concurrent batch is started by this method.
        """
        if not callable(rank_batch) or not callable(persist_scan):
            raise TypeError("monitor handlers must be callable")
        batch = list(assets or [])
        if not 1 <= len(batch) <= 4:
            return {"ok": False, "status": "INVALID_BATCH_SIZE"}
        with self._monitor_lock:
            task = self._monitor_task(actor_id)
            if task is None:
                return {"ok": False, "status": "MONITOR_NOT_FOUND"}
            config, state = self._monitor_config(task)
            if state != "RUNNING":
                return {"ok": False, "status": "MONITOR_NOT_RUNNING",
                        "monitor_state": state}
            if batch_index is None:
                batch_index = int(config.get("next_batch_index") or 0)
            try:
                ranking = rank_batch(batch, batch_index=batch_index)
                if not isinstance(ranking, dict) or ranking.get("ok") is False:
                    raise RuntimeError(str((ranking or {}).get("error_code") or
                                           (ranking or {}).get("status") or "RANKING_FAILED"))
                if str(ranking.get("status") or "").upper() == "NO_NEW_CANDLES":
                    config.update({"next_cycle_at": next_cycle_at,
                                   "scan_state": "WAITING_FOR_NEW_CANDLES"})
                    self.database.update_background_task(task.task_id,
                                                         trigger_config=config)
                    return {"ok": True, "status": "NO_NEW_CANDLES",
                            "monitor_state": "RUNNING", "batch_index": batch_index}
                persisted = persist_scan(ranking, batch_index=batch_index)
                if not isinstance(persisted, dict) or not persisted.get("persisted"):
                    raise RuntimeError(str((persisted or {}).get("error_code") or
                                           (persisted or {}).get("status") or "PERSISTENCE_FAILED"))
            except Exception as exc:
                config.update({"monitor_state": "BACKOFF",
                               "recoverable_error": str(exc)[:120],
                               "next_cycle_at": next_cycle_at})
                self.database.update_background_task(task.task_id,
                                                     trigger_config=config)
                return {"ok": False, "status": "BACKOFF",
                        "error_code": "MONITOR_BATCH_FAILED",
                        "monitor_state": "BACKOFF"}
            config.update({"monitor_state": "RUNNING",
                           "scan_state": "BATCH_PERSISTED",
                           "last_confirmed_batch": batch_index,
                           "next_batch_index": batch_index + 1,
                           "next_cycle_at": next_cycle_at,
                           "recoverable_error": None})
            self.database.update_background_task(task.task_id,
                                                 trigger_config=config)
            return {"ok": True, "status": "BATCH_PERSISTED",
                    "monitor_state": "RUNNING", "batch_index": batch_index,
                    "next_batch_index": batch_index + 1}

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

    def _mission_safety(self, run):
        """Inspect existing mission receipts/checkpoints without executing work."""
        mission_id = str(run.get("mission_id") or "")
        if not mission_id:
            return {"classification": "NONE", "checkpoint_id": "", "receipt_count": 0}
        store = MissionCheckpointStore(self.database)
        receipts = store.receipts_for_mission(mission_id)
        if any(item.get("result_state") == ActionState.IN_FLIGHT_UNKNOWN.value
               for item in receipts):
            return {"classification": "UNSAFE_TO_REPLAY",
                    "reason": "SIDE_EFFECT_UNCERTAIN",
                    "checkpoint_id": "", "receipt_count": len(receipts)}
        checkpoint, error = store.latest(mission_id)
        if checkpoint:
            return {"classification": "RECOVERY_ONLY",
                    "reason": "CHECKPOINT_AVAILABLE",
                    "checkpoint_id": checkpoint.get("checkpoint_id", ""),
                    "receipt_count": len(receipts)}
        return {"classification": "NOT_ELIGIBLE",
                "reason": error or "MISSION_CHECKPOINT_NOT_FOUND",
                "checkpoint_id": "", "receipt_count": len(receipts)}

    @staticmethod
    def _retry_budget(task):
        try:
            return max(0, min(3, int(task.trigger_config.get("retry_budget", 1))))
        except (AttributeError, TypeError, ValueError):
            return 1

    def _retry_eligibility(self, run_id):
        run = self.database.get_task_run(str(run_id))
        if not run:
            return {"eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RUN_NOT_FOUND", "run_id": str(run_id)}
        task = self.database.get_background_task(run["task_id"])
        base = {"run_id": run["run_id"], "task_id": run["task_id"],
                "status": run.get("status"), "source_run_id": run.get("source_run_id"),
                "attempt": int(run.get("attempt") or 1),
                "retry_budget": self._retry_budget(task) if task else 0}
        if not task:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "TASK_NOT_FOUND"}
        if task.status == BackgroundTaskStatus.CANCELLED:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "TASK_CANCELLED"}
        if task.status == BackgroundTaskStatus.PAUSED:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "TASK_PAUSED"}
        if run["status"] == RunStatus.COMPLETED.value:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RUN_ALREADY_COMPLETED"}
        if run["status"] != RunStatus.FAILED.value:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RUN_NOT_FAILED"}
        if run.get("error_code") in {"SECURITY_DENIED", "APPROVAL_REQUIRED",
                                      "USER_CONFIRMATION_REQUIRED"}:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "SECURITY_OR_APPROVAL_REQUIRED"}
        if run.get("error_code") in {"SIDE_EFFECT_UNCERTAIN", "ACTION_IN_FLIGHT_UNKNOWN"}:
            return {**base, "eligible": False, "classification": "UNSAFE_TO_REPLAY",
                    "reason": "SIDE_EFFECT_UNCERTAIN"}
        existing = [item for item in self.database.list_task_runs(run["task_id"], 500)
                    if item.get("source_run_id") == run["run_id"] and
                    item.get("attempt_kind") == "RETRY"]
        if existing:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RETRY_ALREADY_CREATED", "retry_run_id": existing[0]["run_id"]}
        if int(run.get("attempt") or 1) > self._retry_budget(task):
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RETRY_BUDGET_EXHAUSTED"}
        safety = self._mission_safety(run)
        if safety["classification"] == "UNSAFE_TO_REPLAY":
            return {**base, "eligible": False, **safety}
        if safety["classification"] == "RECOVERY_ONLY":
            return {**base, "eligible": False, **safety}
        if safety["classification"] == "NOT_ELIGIBLE":
            return {**base, "eligible": False, **safety}
        classification = ("REQUIRES_CONFIRMATION"
                          if str(task.task_type).lower() == "computer_use"
                          else "SAFE_TO_RETRY")
        return {**base, "eligible": True, "classification": classification,
                "reason": "FAILED_BEFORE_SIDE_EFFECT"}

    def get_retry_eligibility(self, run_id, record_audit=True):
        result = self._retry_eligibility(run_id)
        if record_audit:
            self._audit(result.get("task_id", "desktop"),
                        "TASK_RUN_RETRY_EVALUATED", {
                            "run_id": str(run_id), "eligible": result.get("eligible"),
                            "classification": result.get("classification"),
                            "reason": result.get("reason")})
        return result

    def _recovery_eligibility(self, run_id):
        run = self.database.get_task_run(str(run_id))
        if not run:
            return {"eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RUN_NOT_FOUND", "run_id": str(run_id)}
        task = self.database.get_background_task(run["task_id"])
        base = {"run_id": run["run_id"], "task_id": run["task_id"],
                "status": run.get("status"), "mission_id": run.get("mission_id"),
                "recovery_count": int(run.get("recovery_count") or 0)}
        if not task:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "TASK_NOT_FOUND"}
        if task.status in {BackgroundTaskStatus.CANCELLED, BackgroundTaskStatus.PAUSED}:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "TASK_CANCELLED" if task.status == BackgroundTaskStatus.CANCELLED
                    else "TASK_PAUSED"}
        if run.get("error_code") in {"SIDE_EFFECT_UNCERTAIN", "ACTION_IN_FLIGHT_UNKNOWN"}:
            return {**base, "eligible": False, "classification": "UNSAFE_TO_REPLAY",
                    "reason": "SIDE_EFFECT_UNCERTAIN"}
        if run.get("recovery_count"):
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RECOVERY_ALREADY_APPLIED"}
        now = time.time()
        stale = (run["status"] in {RunStatus.CLAIMED.value, RunStatus.RUNNING.value}
                 and (run.get("claim_expires_at") is None or
                      float(run["claim_expires_at"]) <= now))
        failed_mission = (run["status"] == RunStatus.FAILED.value and
                          bool(run.get("mission_id")))
        if not stale and not failed_mission:
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "RUN_NOT_STALE_OR_RECOVERABLE"}
        safety = self._mission_safety(run)
        if safety["classification"] == "UNSAFE_TO_REPLAY":
            return {**base, "eligible": False, **safety}
        if run.get("mission_id") and not safety.get("checkpoint_id"):
            return {**base, "eligible": False, "classification": "NOT_ELIGIBLE",
                    "reason": "MISSION_CHECKPOINT_NOT_FOUND"}
        classification = ("REQUIRES_CONFIRMATION"
                          if str(task.task_type).lower() == "computer_use"
                          else "RECOVERY_ONLY")
        return {**base, "eligible": True, "classification": classification,
                "reason": "STALE_LEASE" if stale else "CHECKPOINT_AVAILABLE",
                "checkpoint_id": safety.get("checkpoint_id", "")}

    def get_recovery_eligibility(self, run_id, record_audit=True):
        result = self._recovery_eligibility(run_id)
        if record_audit:
            self._audit(result.get("task_id", "desktop"),
                        "TASK_RUN_RECOVERY_EVALUATED", {
                            "run_id": str(run_id), "eligible": result.get("eligible"),
                            "classification": result.get("classification"),
                            "reason": result.get("reason")})
        return result

    def _authorize_retry_action(self, action, task, run, confirmation_token, actor):
        is_mutating = str(task.task_type).lower() == "computer_use"
        risk = Risk.HIGH if is_mutating else Risk.MEDIUM
        tool = Tool(f"background_task_{action}", f"Safe {action} of background run",
                    lambda **_kwargs: {}, risk=risk, confirmation=is_mutating,
                    parameters={"task_id": str, "run_id": str, "action": str})
        arguments = {"task_id": str(task.task_id), "run_id": str(run["run_id"]),
                     "action": action, "actor": str(actor)}
        audit_context = {
            "request_id": f"task:{task.task_id}:{action}",
            "correlation_id": f"task:{task.task_id}:{run['run_id']}",
            "task_id": str(task.task_id), "run_id": str(run["run_id"]),
            "surface": "task_manager", "operation": "background_retry",
            "action": action, "target": str(run["run_id"]),
        }
        if confirmation_token:
            item = self.security.consume(
                confirmation_token, expected_tool=tool.name,
                expected_arguments=arguments, audit_context=audit_context)
            if not item:
                return {"success": False, "code": "INVALID_CONFIRMATION"}
        else:
            decision = self.security.decision(tool, risk=risk,
                                              requires_confirmation=tool.confirmation,
                                              audit_context=audit_context)
            if decision == "deny":
                return {"success": False, "code": "SECURITY_DENIED"}
            if decision == "confirm":
                return {"success": False, "confirmation_required": True,
                        "token": self.security.create_confirmation(
                            tool, arguments, action, risk,
                            audit_context=audit_context), "code": "CONFIRMATION_REQUIRED"}
        return {"success": True}

    def retry_background_run(self, run_id, confirmation_token=None,
                             actor="background_control"):
        result = self.get_retry_eligibility(run_id)
        task = self.database.get_background_task(result.get("task_id"))
        run = self.database.get_task_run(str(run_id))
        self._audit(result.get("task_id", "desktop"), "TASK_RUN_RETRY_REQUESTED",
                    {"run_id": str(run_id), "actor": str(actor)})
        if not result.get("eligible"):
            event = "UNSAFE_REPLAY_BLOCKED" if result.get("classification") == "UNSAFE_TO_REPLAY" \
                else "TASK_RUN_RETRY_BLOCKED"
            self._audit(result.get("task_id", "desktop"), event, {
                "run_id": str(run_id), "reason": result.get("reason"),
                "classification": result.get("classification")})
            return {"success": False, "code": result.get("reason"), **result}
        if result.get("classification") == "RECOVERY_ONLY":
            return {"success": False, "code": "RECOVERY_REQUIRED", **result}
        authorized = self._authorize_retry_action(
            "retry", task, run, confirmation_token, actor)
        if not authorized.get("success"):
            if authorized.get("code") == "SECURITY_DENIED":
                self._audit(task.task_id, "TASK_RUN_RETRY_BLOCKED", {
                    "run_id": str(run_id), "reason": "SECURITY_DENIED"})
            return {**authorized, "run_id": str(run_id), "task_id": task.task_id}
        now = time.time()
        scheduled_for = max(now, max((item.get("scheduled_for") or 0
                                      for item in self.database.list_task_runs(task.task_id, 500)),
                                     default=0) + 0.001)
        created = self.database.create_retry_run(str(run_id), scheduled_for, now)
        if not created.get("created"):
            return {"success": False, "code": created.get("code"), **created}
        self._audit(task.task_id, "TASK_RUN_RETRY_STARTED", {
            "source_run_id": str(run_id), "run_id": created["run"]["run_id"],
            "attempt": created["run"].get("attempt"), "actor": str(actor)})
        return {"success": True, "code": "RETRY_STARTED", **created,
                "source_run_id": str(run_id)}

    def recover_background_run(self, run_id, confirmation_token=None,
                               actor="background_control"):
        result = self.get_recovery_eligibility(run_id)
        task = self.database.get_background_task(result.get("task_id"))
        run = self.database.get_task_run(str(run_id))
        if not result.get("eligible"):
            event = "UNSAFE_REPLAY_BLOCKED" if result.get("classification") == "UNSAFE_TO_REPLAY" \
                else "TASK_RUN_RECOVERY_BLOCKED"
            self._audit(result.get("task_id", "desktop"), event, {
                "run_id": str(run_id), "reason": result.get("reason"),
                "classification": result.get("classification")})
            return {"success": False, "code": result.get("reason"), **result}
        authorized = self._authorize_retry_action(
            "recovery", task, run, confirmation_token, actor)
        if not authorized.get("success"):
            return {**authorized, "run_id": str(run_id), "task_id": task.task_id}
        recovered = self.database.recover_task_run(
            str(run_id), reason=result.get("reason", "RECOVERY"))
        if not recovered.get("recovered"):
            return {"success": False, "code": recovered.get("code"), **recovered}
        self._audit(task.task_id, "TASK_RUN_RECOVERY_STARTED", {
            "run_id": str(run_id), "reason": result.get("reason"),
            "checkpoint_id": result.get("checkpoint_id", ""), "actor": str(actor)})
        return {"success": True, "code": "RECOVERY_STARTED", **recovered}

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
        audit_context = {
            "request_id": f"task:{task_id}:{action}",
            "correlation_id": f"task:{task_id}:{action}",
            "task_id": task_id, "surface": "task_manager",
            "operation": "background_control", "action": action,
            "target": task_id,
        }
        if confirmation_token:
            item = self.security.consume(
                confirmation_token, expected_tool=tool.name,
                expected_arguments=arguments, audit_context=audit_context)
            if not item:
                return {"success": False, "code": "INVALID_CONFIRMATION",
                        "task_id": task_id, "requested_action": action}
        else:
            decision = self.security.decision(tool, risk=risk,
                                              requires_confirmation=tool.confirmation,
                                              audit_context=audit_context)
            if decision == "deny":
                self._audit(task_id, "BACKGROUND_TASK_CONTROL_DENIED", arguments)
                return {"success": False, "code": "SECURITY_DENIED",
                        "task_id": task_id, "requested_action": action}
            if decision == "confirm":
                token = self.security.create_confirmation(
                    tool, arguments, action, risk, audit_context=audit_context)
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

    def list_background_notifications(self, **kwargs):
        return self.control_center.list_notifications(**kwargs)

    def get_background_notification(self, notification_id):
        return self.control_center.get_notification(notification_id)

    def background_notification_summary(self):
        return self.control_center.get_notification_summary()

    def scheduler_health(self, **kwargs):
        return self.control_center.get_scheduler_health(**kwargs)

    def scheduler_diagnostics(self, **kwargs):
        return self.control_center.get_scheduler_diagnostics(**kwargs)

    def list_pending_background_approvals(self, **kwargs):
        return self.control_center.list_pending_approvals(**kwargs)

    def get_pending_background_approval(self, approval_id):
        return self.control_center.get_pending_approval(approval_id)

    def _authorize_approval_decision(self, action, approval, task,
                                     confirmation_token, actor):
        is_computer_use = task is not None and str(task.task_type).lower() == "computer_use"
        risk = Risk.HIGH if is_computer_use else Risk.MEDIUM
        tool = Tool(
            f"background_approval_{action}",
            f"Decide aprovação de background: {action}",
            lambda **_kwargs: {}, risk=risk, confirmation=is_computer_use,
            parameters={"approval_id": str, "task_id": str,
                        "action": str, "actor": str})
        arguments = {
            "approval_id": str(approval.get("approval_id")),
            "task_id": str(approval.get("task_id")),
            "action": str(action), "actor": str(actor),
        }
        audit_context = {
            "request_id": f"approval:{approval.get('approval_id')}",
            "correlation_id": f"approval:{approval.get('approval_id')}",
            "task_id": str(approval.get("task_id")),
            "run_id": str(approval.get("run_id") or ""),
            "approval_id": str(approval.get("approval_id")),
            "surface": "task_manager", "operation": "approval_decision",
            "action": str(action), "target": str(approval.get("approval_id")),
        }
        if confirmation_token:
            item = self.security.consume(
                confirmation_token, expected_tool=tool.name,
                expected_arguments=arguments, audit_context=audit_context)
            if not item:
                return {"success": False, "code": "INVALID_CONFIRMATION"}
        else:
            decision = self.security.decision(
                tool, risk=risk, requires_confirmation=tool.confirmation,
                audit_context=audit_context)
            if decision == "deny":
                return {"success": False, "code": "SECURITY_DENIED"}
            if decision == "confirm":
                return {
                    "success": False, "confirmation_required": True,
                    "token": self.security.create_confirmation(
                        tool, arguments, action, risk,
                        audit_context=audit_context),
                    "code": "CONFIRMATION_REQUIRED",
                }
        return {"success": True}

    def decide_background_approval(self, approval_id, decision,
                                   confirmation_token=None,
                                   actor="background_control"):
        approval = self.database.get_task_approval(str(approval_id))
        if approval is None:
            return {"success": False, "code": "APPROVAL_NOT_FOUND",
                    "approval_id": str(approval_id)}
        task = self.database.get_background_task(approval.get("task_id"))
        action = "approve" if str(decision).upper() == "APPROVED" else "deny"
        authorized = self._authorize_approval_decision(
            action, approval, task, confirmation_token, actor)
        if not authorized.get("success"):
            if authorized.get("code") == "SECURITY_DENIED":
                self._audit(approval.get("task_id", "desktop"),
                            "APPROVAL_DECISION_BLOCKED", {
                                "approval_id": str(approval_id),
                                "decision": str(decision).upper(),
                                "actor": str(actor), "reason": "SECURITY_DENIED"})
            return {**authorized, "approval_id": str(approval_id)}
        result = self.database.decide_task_approval(
            str(approval_id), str(decision), str(actor), time.time())
        event = {
            "APPROVED": "APPROVAL_GRANTED",
            "DENIED": "APPROVAL_DENIED",
        }.get(str(decision).upper(), "APPROVAL_DECISION_BLOCKED")
        if result.get("code") == "STALE_APPROVAL":
            event = "APPROVAL_STALE"
        elif result.get("code") in {"APPROVAL_ALREADY_DECIDED", "APPROVAL_NOT_ACTIVE"}:
            event = "APPROVAL_REUSE_BLOCKED"
        self._audit(approval.get("task_id", "desktop"), event, {
            "approval_id": str(approval_id),
            "decision": str(decision).upper(), "actor": str(actor),
            "code": result.get("code")})
        return {**result, "approval_id": str(approval_id)}

    def approve_background_approval(self, approval_id,
                                    confirmation_token=None,
                                    actor="background_control"):
        return self.decide_background_approval(
            approval_id, "APPROVED", confirmation_token, actor)

    def deny_background_approval(self, approval_id,
                                 confirmation_token=None,
                                 actor="background_control"):
        return self.decide_background_approval(
            approval_id, "DENIED", confirmation_token, actor)

    def approve_pending_action(self, approval_id, confirmation_token=None,
                               actor="background_control"):
        return self.approve_background_approval(approval_id, confirmation_token, actor)

    def deny_pending_action(self, approval_id, confirmation_token=None,
                            actor="background_control"):
        return self.deny_background_approval(approval_id, confirmation_token, actor)

    def request_shutdown(self):
        """Request stop without waiting for owned workers to finish."""
        if self._shutdown_complete:
            return
        self._shutdown_requested = True
        self._stop_market_monitors_for_shutdown()
        self.scheduler.stop(wait=False)
        self.runner.shutdown(wait=False)

    def finalize_shutdown(self):
        """Join owned workers and complete final resource shutdown."""
        if self._shutdown_complete:
            return
        self._shutdown_requested = True
        self._stop_market_monitors_for_shutdown()
        self.scheduler.stop(wait=True)
        self.runner.shutdown(wait=True)
        self._shutdown_complete = True

    def shutdown(self, wait=True):
        """Preserve the API while exposing request and final shutdown phases."""
        if wait:
            self.finalize_shutdown()
        else:
            self.request_shutdown()

    def _stop_market_monitors_for_shutdown(self):
        """Persist a clean STOPPED state without dispatching a scan."""
        with self._monitor_lock:
            for task in self.database.list_background_tasks(limit=1000, enabled=None):
                if task.task_type != self.MONITOR_TASK_TYPE:
                    continue
                actor = task.security_scope.get("actor_id")
                if actor:
                    self._set_market_monitor_state(actor, "STOPPED",
                                                    reason="core_shutdown")

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
