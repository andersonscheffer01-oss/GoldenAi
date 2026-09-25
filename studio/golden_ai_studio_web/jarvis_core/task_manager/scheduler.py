"""Internal durable scheduler. It dispatches work; it never drives a GUI itself."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .background import (BackgroundTask, BackgroundTaskStatus, ConditionType,
                          MisfirePolicy, RunStatus, TriggerType)
from .clock import SystemClock


class ConditionEvaluator:
    """Allow-listed, dependency-injected condition checks; no eval or shell."""

    def __init__(self, *, app_provider=None, idle_provider=None, mission_provider=None,
                 service_provider=None, now_provider=None):
        self.app_provider = app_provider or (lambda _name: False)
        self.idle_provider = idle_provider or (lambda: 0.0)
        self.mission_provider = mission_provider or (lambda _mission: None)
        self.service_provider = service_provider or (lambda _service: False)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def evaluate(self, config):
        kind = ConditionType(str(config.get("condition_type", config.get("type", ""))).upper())
        if kind == ConditionType.FILE_EXISTS:
            return Path(config["path"]).is_file()
        if kind == ConditionType.FILE_NOT_EXISTS:
            return not Path(config["path"]).exists()
        if kind in {ConditionType.APP_RUNNING, ConditionType.APP_NOT_RUNNING}:
            running = bool(self.app_provider(str(config["app"])))
            return running if kind == ConditionType.APP_RUNNING else not running
        if kind == ConditionType.USER_IDLE:
            return float(self.idle_provider()) >= float(config.get("seconds", config.get("threshold", 0)))
        if kind == ConditionType.TIME_WINDOW:
            now = self.now_provider()
            start, end = str(config["start"]), str(config["end"])
            current = now.strftime("%H:%M")
            return (start <= current <= end) if start <= end else (current >= start or current <= end)
        if kind == ConditionType.MISSION_STATUS:
            return str(self.mission_provider(str(config["mission_id"]))) == str(config["status"])
        if kind == ConditionType.LOCAL_SERVICE_AVAILABLE:
            return bool(self.service_provider(str(config["service"])))
        raise ValueError("CONDITION_TYPE_NOT_ALLOWED")


class BackgroundTaskScheduler:
    """One scheduler per JarvisService, backed by the existing TaskDatabase."""

    def __init__(self, database, audit=None, launcher=None, clock=None,
                 condition_evaluator=None, tick_interval=1.0, worker_id=None,
                 lease_seconds=30.0):
        self.database = database
        self.audit = audit
        self.launcher = launcher
        self.clock = clock or SystemClock()
        self.conditions = condition_evaluator or ConditionEvaluator()
        self.tick_interval = max(0.05, float(tick_interval))
        self.worker_id = worker_id or f"jarvis-scheduler-{uuid.uuid4()}"
        self.lease_seconds = float(lease_seconds)
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self.database.recover_background_runs(self.clock.now())
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="jarvis-background-scheduler",
                                            daemon=True)
            self._thread.start()

    def stop(self, wait=True):
        self._stop.set()
        thread = self._thread
        if wait and thread and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.tick_interval * 3))
        self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # A malformed task cannot kill service shutdown or other tasks.
                pass
            self._stop.wait(self.tick_interval)

    def tick(self):
        now = self.clock.now()
        actions = []
        for task in self.database.list_background_tasks(enabled=True):
            if not task.enabled or task.status in {BackgroundTaskStatus.CANCELLED,
                    BackgroundTaskStatus.DISABLED, BackgroundTaskStatus.COMPLETED}:
                continue
            if task.max_runs is not None and task.run_count >= task.max_runs:
                self.database.update_background_task(task.task_id,
                    status=BackgroundTaskStatus.EXPIRED, enabled=False)
                continue
            if task.next_run_at is None:
                next_run = self._first_run(task, now)
                self.database.update_background_task(task.task_id,
                    next_run_at=next_run, status=BackgroundTaskStatus.SCHEDULED)
                task = self.database.get_background_task(task.task_id)
                if task is None or float(task.next_run_at) > now:
                    continue
            if float(task.next_run_at) > now:
                continue
            if task.trigger_type in {TriggerType.USER_IDLE, TriggerType.CONDITION}:
                try:
                    condition = dict(task.trigger_config)
                    if task.trigger_type == TriggerType.USER_IDLE and not condition.get("type") \
                            and not condition.get("condition_type"):
                        condition["type"] = ConditionType.USER_IDLE.value
                    ready = self.conditions.evaluate(condition)
                except (KeyError, TypeError, ValueError, OSError):
                    self._fail_task(task, "CONDITION_INVALID")
                    continue
                if not ready:
                    status = (BackgroundTaskStatus.WAITING_USER_IDLE
                              if task.trigger_type == TriggerType.USER_IDLE
                              else BackgroundTaskStatus.WAITING_TRIGGER)
                    self.database.update_background_task(task.task_id, status=status)
                    continue
            if self._should_skip_misfire(task, now):
                self._advance(task, now, skipped=True)
                actions.append((task.task_id, "SKIPPED_MISFIRE"))
                continue
            run = self.database.ensure_task_run(task.task_id, task.next_run_at, now)
            claimed = self.database.claim_task_run(run["run_id"], self.worker_id, now,
                                                   self.lease_seconds)
            if not claimed:
                continue
            self.database.update_background_task(task.task_id, status=BackgroundTaskStatus.RUNNING)
            self.database.update_task_run(claimed["run_id"], status=RunStatus.RUNNING.value,
                                          started_at=now)
            actions.append((task.task_id, self._dispatch(task, claimed, now)))
        return actions

    def _dispatch(self, task, run, now):
        self._audit(task.task_id, "background_task_dispatched", {"run_id": run["run_id"]})
        if self.launcher is None:
            self._finish(task, run, now, False, "NO_LAUNCHER")
            return "FAILED"
        try:
            result = self.launcher(task, run)
        except Exception as exc:
            self._finish(task, run, now, False, "LAUNCH_FAILED", str(exc))
            return "FAILED"
        result = result if isinstance(result, dict) else {"ok": True, "result": result}
        mission_id = result.get("mission_id") or (result.get("mission") or {}).get("mission_id")
        if mission_id:
            self.database.update_task_run(run["run_id"], mission_id=mission_id)
        mission = result.get("mission") or {}
        result_status = str(result.get("status") or mission.get("status") or "").upper()
        result_error = str(result.get("error") or mission.get("error") or "").upper()
        if (result_status in {"WAITING_USER_IDLE", "WAITING_FOR_USER_IDLE"} or
                result_error in {"USER_ACTIVITY_DETECTED", "MISSION_PAUSED_FOR_USER_ACTIVITY"}):
            self.database.update_task_run(run["run_id"], status=RunStatus.WAITING_USER_IDLE,
                                          claim_token=None, claimed_by=None, claim_expires_at=None,
                                          error_code="USER_ACTIVITY_DETECTED",
                                          error_message="mission paused for user activity")
            self.database.update_background_task(task.task_id,
                status=BackgroundTaskStatus.WAITING_USER_IDLE)
            self._audit(task.task_id, "background_task_waiting_user_idle", {"run_id": run["run_id"]})
            return "WAITING_USER_IDLE"
        if result_status == "WAITING_CONFIRMATION" or result.get("confirmation_required"):
            self.database.update_task_run(run["run_id"], status=RunStatus.WAITING_CONFIRMATION,
                                          claim_token=None, claimed_by=None, claim_expires_at=None)
            self.database.update_background_task(task.task_id,
                status=BackgroundTaskStatus.WAITING_CONFIRMATION)
            self._audit(task.task_id, "background_task_waiting_confirmation", {"run_id": run["run_id"]})
            return "WAITING_CONFIRMATION"
        if result.get("status") == "WAITING_USER_IDLE":
            self.database.update_task_run(run["run_id"], status=RunStatus.WAITING_USER_IDLE,
                                          claim_token=None, claimed_by=None, claim_expires_at=None)
            self.database.update_background_task(task.task_id,
                status=BackgroundTaskStatus.WAITING_USER_IDLE)
            return "WAITING_USER_IDLE"
        ok = bool(result.get("ok", True))
        self._finish(task, run, now, ok, result.get("error_code"), result.get("error"))
        return "COMPLETED" if ok else "FAILED"

    def _finish(self, task, run, now, ok, error_code=None, error_message=None):
        status = RunStatus.COMPLETED if ok else RunStatus.FAILED
        self.database.update_task_run(run["run_id"], status=status, finished_at=now,
                                      claim_token=None, claimed_by=None, claim_expires_at=None,
                                      error_code=error_code, error_message=error_message)
        if ok:
            self.database.update_background_task(task.task_id, status=BackgroundTaskStatus.COMPLETED,
                                                last_run_at=now, run_count=task.run_count + 1)
            if task.max_runs is not None and task.run_count + 1 >= task.max_runs:
                self.database.update_background_task(task.task_id,
                    status=BackgroundTaskStatus.EXPIRED, enabled=False)
                self._audit(task.task_id, "background_task_expired", {"run_id": run["run_id"]})
                return
            self._advance(task, now)
            self._audit(task.task_id, "background_task_completed", {"run_id": run["run_id"]})
        else:
            self.database.update_background_task(task.task_id, status=BackgroundTaskStatus.FAILED)
            self._audit(task.task_id, "background_task_failed", {"run_id": run["run_id"],
                                                                    "error_code": error_code})

    def _advance(self, task, now, skipped=False):
        if task.trigger_type != TriggerType.RECURRING:
            self.database.update_background_task(task.task_id,
                status=(BackgroundTaskStatus.EXPIRED if skipped else BackgroundTaskStatus.COMPLETED),
                enabled=False, last_run_at=now)
            return
        next_run = self._next_recurring(task, now)
        self.database.update_background_task(task.task_id, status=BackgroundTaskStatus.SCHEDULED,
                                             next_run_at=next_run, last_run_at=now)

    def _first_run(self, task, now):
        cfg = task.trigger_config
        if task.trigger_type == TriggerType.IMMEDIATE:
            return task.created_at or now
        if task.trigger_type == TriggerType.AT_TIME:
            return float(cfg.get("timestamp", cfg.get("at", now)))
        if task.trigger_type == TriggerType.AFTER_DELAY:
            return (task.created_at or now) + float(cfg.get("seconds", cfg.get("delay", 0)))
        if task.trigger_type in {TriggerType.USER_IDLE, TriggerType.CONDITION}:
            return now
        return self._next_recurring(task, now, first=True)

    def _next_recurring(self, task, now, first=False):
        cfg = task.trigger_config
        mode = str(cfg.get("mode", "INTERVAL")).upper()
        if mode == "INTERVAL":
            base = task.created_at if first or not task.last_run_at else task.last_run_at
            return float(base or now) + float(cfg.get("seconds", cfg.get("interval", 60)))
        tz = ZoneInfo(task.timezone)
        local = datetime.fromtimestamp(now, tz)
        if mode == "DAILY":
            hour, minute = self._time(cfg.get("time", "00:00"))
            candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate.timestamp() <= now:
                candidate += timedelta(days=1)
            return candidate.timestamp()
        if mode == "WEEKLY":
            hour, minute = self._time(cfg.get("time", "00:00"))
            weekday = int(cfg.get("weekday", 0)) % 7
            days = (weekday - local.weekday()) % 7
            candidate = (local + timedelta(days=days)).replace(hour=hour, minute=minute,
                                                                second=0, microsecond=0)
            if candidate.timestamp() <= now:
                candidate += timedelta(days=7)
            return candidate.timestamp()
        raise ValueError("RECURRENCE_NOT_ALLOWED")

    @staticmethod
    def _time(value):
        hour, minute = (int(part) for part in str(value).split(":", 1))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("INVALID_TIME")
        return hour, minute

    @staticmethod
    def _should_skip_misfire(task, now):
        grace = float(task.trigger_config.get("misfire_grace_seconds", 60))
        return task.misfire_policy == MisfirePolicy.SKIP_IF_MISSED and now - float(task.next_run_at) > grace

    def _fail_task(self, task, code):
        self.database.update_background_task(task.task_id, status=BackgroundTaskStatus.FAILED,
                                             enabled=False)
        self._audit(task.task_id, "background_task_failed", {"error_code": code})

    def cancel(self, task_id):
        self.database.update_background_task(task_id, status=BackgroundTaskStatus.CANCELLED,
                                             enabled=False)
        self._audit(task_id, "background_task_cancelled")

    def disable(self, task_id):
        self.database.update_background_task(task_id, status=BackgroundTaskStatus.DISABLED,
                                             enabled=False)
        self._audit(task_id, "background_task_disabled")

    def enable(self, task_id):
        task = self.database.get_background_task(task_id)
        if not task:
            raise KeyError(task_id)
        self.database.update_background_task(task_id, status=BackgroundTaskStatus.SCHEDULED,
                                             enabled=True)
        self._audit(task_id, "background_task_enabled")

    def _audit(self, task_id, event, details=None):
        if self.audit is not None and hasattr(self.audit, "add"):
            self.audit.add(task_id=task_id, command=event, tool="background_scheduler",
                           arguments=details or {}, risk="LOW", status="info", result=event)


__all__ = ["BackgroundTaskScheduler", "ConditionEvaluator"]
