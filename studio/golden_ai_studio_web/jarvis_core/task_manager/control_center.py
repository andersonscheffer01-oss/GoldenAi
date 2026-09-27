"""Observability and explicit controls over the canonical task system."""
from __future__ import annotations

import time

from .background import BackgroundTaskStatus, RunStatus


READ_ONLY_BACKGROUND_OBSERVATION = "READ_ONLY_BACKGROUND_OBSERVATION"
_RUNNING = {RunStatus.CLAIMED.value, RunStatus.RUNNING.value}
_CURRENT_RUN = _RUNNING | {
    RunStatus.WAITING_USER_IDLE.value,
    RunStatus.WAITING_CONFIRMATION.value,
}
_WAITING = {
    BackgroundTaskStatus.SCHEDULED.value,
    BackgroundTaskStatus.WAITING_TRIGGER.value,
    BackgroundTaskStatus.WAITING_USER_IDLE.value,
    BackgroundTaskStatus.WAITING_CONFIRMATION.value,
    BackgroundTaskStatus.PAUSED.value,
}
_COMPLETED = {
    BackgroundTaskStatus.COMPLETED.value,
    BackgroundTaskStatus.EXPIRED.value,
}
_TERMINAL = _COMPLETED | {
    BackgroundTaskStatus.CANCELLED.value,
    BackgroundTaskStatus.DISABLED.value,
    BackgroundTaskStatus.FAILED.value,
}


class BackgroundControlCenter:
    """Keep read-only views separate from explicit task control operations."""

    def __init__(self, database, scheduler=None, now_provider=None,
                 retry_eligibility=None, recovery_eligibility=None):
        self.database = database
        self.scheduler = scheduler
        self.now_provider = now_provider or time.time
        self.retry_eligibility = retry_eligibility
        self.recovery_eligibility = recovery_eligibility

    def get_scheduler_status(self):
        if self.scheduler is not None and hasattr(self.scheduler, "status"):
            return dict(self.scheduler.status())
        return {
            "running": False,
            "worker_id": "",
            "tick_interval": None,
            "database_path": str(self.database.path),
        }

    def list_tasks(self, *, status=None, enabled=None, task_type=None,
                   trigger_type=None, limit=200, offset=0):
        tasks, runs, approvals = self._state()
        selected = []
        for task in tasks:
            if status is not None and task.status.value != str(getattr(status, "value", status)):
                continue
            if enabled is not None and task.enabled is not bool(enabled):
                continue
            if task_type is not None and task.task_type != str(task_type):
                continue
            if trigger_type is not None and task.trigger_type.value != str(
                    getattr(trigger_type, "value", trigger_type)):
                continue
            selected.append(self._task_view(task, runs, approvals))
        selected.sort(key=lambda item: (
            item["next_run_at"] is None,
            item["next_run_at"] if item["next_run_at"] is not None else float("inf"),
            item["created_at"], item["task_id"]))
        start = max(0, int(offset))
        return selected[start:start + max(1, min(int(limit), 1000))]

    def get_task(self, task_id):
        task = self.database.get_background_task(str(task_id))
        if task is None:
            return None
        runs = self.database.list_task_runs(task.task_id, limit=500)
        approvals = self.database.list_task_approvals(task_id=task.task_id, limit=500)
        return self._task_view(task, runs, approvals)

    def list_runs(self, task_id=None, *, limit=100, offset=0):
        runs = (self.database.list_task_runs(str(task_id), limit=500)
                if task_id is not None else self.database.list_all_task_runs(limit=5000))
        approvals = self.database.list_task_approvals(task_id=task_id, limit=5000)
        views = [self._run_view(run, approvals) for run in runs]
        views.sort(key=self._run_sort_key, reverse=True)
        start = max(0, int(offset))
        return views[start:start + max(1, min(int(limit), 1000))]

    def get_run(self, run_id):
        run = self.database.get_task_run(str(run_id))
        if run is None:
            return None
        approvals = self.database.list_task_approvals(run_id=str(run_id), limit=100)
        return self._run_view(run, approvals)

    def list_pending_approvals(self, *, task_id=None, run_id=None, limit=100,
                               offset=0):
        tasks, _, approvals = self._state()
        views = [self._approval_view(row) for row in
                 self._pending_approval_rows(tasks, approvals)
                 if (task_id is None or row.get("task_id") == str(task_id))
                 and (run_id is None or row.get("run_id") == str(run_id))]
        start = max(0, int(offset))
        return views[start:start + max(1, min(int(limit), 1000))]

    def get_pending_approval(self, approval_id):
        row = self.database.get_task_approval(str(approval_id))
        if row is None:
            return None
        task = self.database.get_background_task(row.get("task_id"))
        stale_reason = self._approval_stale_reason(
            row, task, float(self.now_provider()))
        view = self._approval_view(row)
        view["pending"] = stale_reason is None and row.get("status") == "ACTIVE" \
            and row.get("decision", "PENDING") == "PENDING"
        view["stale_reason"] = stale_reason
        return view

    def list_notifications(self, *, limit=100, offset=0, notification_type=None,
                           severity=None, actionability=None):
        notifications = self._notification_views()
        if notification_type is not None:
            notifications = [item for item in notifications
                             if item["type"] == str(notification_type)]
        if severity is not None:
            notifications = [item for item in notifications
                             if item["severity"] == str(severity)]
        if actionability is not None:
            notifications = [item for item in notifications
                             if item["actionability"] == str(actionability)]
        start = max(0, int(offset))
        return notifications[start:start + max(1, min(int(limit), 1000))]

    def get_notification(self, notification_id):
        return next((item for item in self._notification_views()
                     if item["notification_id"] == str(notification_id)), None)

    def get_notification_summary(self):
        notifications = self._notification_views()
        return {
            "total": len(notifications),
            "action_required": sum(item["actionability"] in {
                "APPROVAL_REQUIRED", "RECOVERY_DECISION_REQUIRED"
            } for item in notifications),
            "by_severity": {
                severity: sum(item["severity"] == severity for item in notifications)
                for severity in ("INFO", "WARNING", "ACTION_REQUIRED", "ERROR")
            },
            "read_only": True,
        }

    def _pending_approval_rows(self, tasks, approvals):
        task_by_id = {task.task_id: task for task in tasks}
        now = float(self.now_provider())
        return [row for row in approvals
                if row.get("status") == "ACTIVE"
                and row.get("decision", "PENDING") == "PENDING"
                and self._approval_stale_reason(
                    row, task_by_id.get(row.get("task_id")), now) is None]

    @staticmethod
    def _approval_stale_reason(row, task, now):
        if float(row.get("expires_at", 0) or 0) < float(now):
            return "APPROVAL_EXPIRED"
        if task is None:
            return "TASK_NOT_FOUND"
        if task.status.value in _TERMINAL:
            return f"TASK_{task.status.value}"
        if row.get("decision", "PENDING") in {"DENIED", "STALE"}:
            return f"APPROVAL_{row.get('decision')}"
        if row.get("status") != "ACTIVE":
            return f"APPROVAL_{row.get('status')}"
        return None

    def _notification_views(self):
        tasks, runs, approvals = self._state()
        task_by_id = {task.task_id: task for task in tasks}
        notifications = []
        for row in self._pending_approval_rows(tasks, approvals):
            notifications.append({
                "notification_id": f"approval-required:{row['approval_id']}",
                "type": "APPROVAL_REQUIRED", "severity": "ACTION_REQUIRED",
                "title": "Ação aguardando aprovação",
                "message": f"A aprovação {row['approval_id']} está aguardando decisão.",
                "created_at": float(row.get("granted_at", 0) or 0),
                "task_id": row.get("task_id"), "run_id": row.get("run_id"),
                "mission_id": row.get("mission_id"),
                "approval_id": row.get("approval_id"), "status": "NEW",
                "source": "background_control_center",
                "actionability": "APPROVAL_REQUIRED",
            })
        failed_runs = {}
        for run in runs:
            if run.get("status") != RunStatus.FAILED.value:
                continue
            if run.get("task_id") not in task_by_id:
                continue
            current = failed_runs.get(run.get("task_id"))
            if current is None or self._run_sort_key(run) > self._run_sort_key(current):
                failed_runs[run.get("task_id")] = run
        for run in failed_runs.values():
            notifications.append({
                "notification_id": f"task-failed:{run['run_id']}",
                "type": "TASK_FAILED", "severity": "ERROR",
                "title": "Tarefa em background falhou",
                "message": run.get("error_message") or run.get("error_code") or "Falha sem detalhes.",
                "created_at": float(run.get("finished_at") or run.get("created_at") or 0),
                "task_id": run.get("task_id"), "run_id": run.get("run_id"),
                "mission_id": run.get("mission_id"), "approval_id": None,
                "status": "NEW", "source": "background_control_center",
                "actionability": "RECOVERY_DECISION_REQUIRED",
            })
        for task in tasks:
            if task.status.value == BackgroundTaskStatus.PAUSED.value:
                notifications.append(self._task_notification(
                    task, "TASK_PAUSED", "WARNING", "Tarefa pausada",
                    "CONTROL_AVAILABLE"))
            elif task.status.value == BackgroundTaskStatus.CANCELLED.value:
                notifications.append(self._task_notification(
                    task, "TASK_CANCELLED", "INFO", "Tarefa cancelada",
                    "INFORMATION_ONLY"))
            elif task.status.value in _COMPLETED:
                notifications.append(self._task_notification(
                    task, "TASK_COMPLETED", "INFO", "Tarefa concluída",
                    "INFORMATION_ONLY"))
        notifications.sort(key=lambda item: (item["created_at"], item["notification_id"]))
        return notifications

    @staticmethod
    def _task_notification(task, notification_type, severity, title, actionability):
        return {
            "notification_id": f"{notification_type.lower()}:{task.task_id}",
            "type": notification_type, "severity": severity, "title": title,
            "message": task.user_request, "created_at": float(task.updated_at),
            "task_id": task.task_id, "run_id": None, "mission_id": None,
            "approval_id": None, "status": "NEW",
            "source": "background_control_center", "actionability": actionability,
        }

    def control_task(self, action, task_id):
        """Delegate one already-authorized control to the canonical scheduler."""
        if self.scheduler is None:
            return {"success": False, "code": "SCHEDULER_UNAVAILABLE",
                    "task_id": str(task_id), "requested_action": str(action)}
        method = {"pause": "pause", "resume": "resume", "cancel": "cancel"}.get(
            str(action).lower())
        if method is None:
            return {"success": False, "code": "UNKNOWN_CONTROL_ACTION",
                    "task_id": str(task_id), "requested_action": str(action)}
        return getattr(self.scheduler, method)(str(task_id))

    def get_next_due_task(self):
        tasks, runs, approvals = self._state()
        candidates = [task for task in tasks
                      if task.enabled and task.status.value not in _TERMINAL | _RUNNING
                      and task.next_run_at is not None]
        candidates.sort(key=self._task_sort_key)
        if not candidates:
            return None
        task = candidates[0]
        view = self._task_view(task, runs, approvals)
        return {
            "task_id": view["task_id"],
            "status": view["status"],
            "next_run_at": view["next_run_at"],
            "trigger_type": view["trigger_type"],
        }

    def get_summary(self):
        tasks, runs, approvals = self._state()
        statuses = [task.status.value for task in tasks]
        pending = self._pending_approval_rows(tasks, approvals)
        return {
            "total_tasks": len(tasks),
            "enabled_tasks": sum(bool(task.enabled) for task in tasks),
            "running_tasks": sum(status in _RUNNING for status in statuses),
            "waiting_tasks": sum(status in _WAITING for status in statuses),
            "failed_tasks": sum(status == BackgroundTaskStatus.FAILED.value
                                 for status in statuses),
            "completed_tasks": sum(status in _COMPLETED for status in statuses),
            "pending_approvals": len(pending),
            "next_due_task": self.get_next_due_task(),
        }

    def get_snapshot(self, *, recent_runs_limit=100):
        tasks, runs, approvals = self._state()
        pending = self._pending_approval_rows(tasks, approvals)
        task_views = [self._task_view(task, runs, approvals) for task in tasks]
        task_views.sort(key=lambda item: (
            item["next_run_at"] is None,
            item["next_run_at"] if item["next_run_at"] is not None else float("inf"),
            item["created_at"], item["task_id"]))
        run_views = [self._run_view(run, approvals) for run in runs]
        run_views.sort(key=self._run_sort_key, reverse=True)
        return {
            "security_classification": READ_ONLY_BACKGROUND_OBSERVATION,
            "read_only": True,
            "scheduler": self.get_scheduler_status(),
            "summary": self._summary_from(task_views, approvals),
            "tasks": task_views,
            "running": [item for item in task_views if item["status"] in _RUNNING],
            "waiting": [item for item in task_views if item["status"] in _WAITING],
            "failed": [item for item in task_views
                       if item["status"] == BackgroundTaskStatus.FAILED.value],
            "completed": [item for item in task_views if item["status"] in _COMPLETED],
            "pending_approvals": [self._approval_view(row) for row in pending],
            "recent_runs": run_views[:max(1, min(int(recent_runs_limit), 1000))],
            "notifications": self._notification_views(),
            "notification_summary": self.get_notification_summary(),
            "action_required_count": self.get_notification_summary()["action_required"],
        }

    def _state(self):
        tasks = self.database.list_background_tasks(limit=1000)
        runs = self.database.list_all_task_runs(limit=5000)
        approvals = self.database.list_task_approvals(limit=5000)
        return tasks, runs, approvals

    def _summary_from(self, task_views, approvals):
        now = float(self.now_provider())
        statuses = [item["status"] for item in task_views]
        return {
            "total_tasks": len(task_views),
            "enabled_tasks": sum(bool(item["enabled"]) for item in task_views),
            "running_tasks": sum(status in _RUNNING for status in statuses),
            "waiting_tasks": sum(status in _WAITING for status in statuses),
            "failed_tasks": sum(status == BackgroundTaskStatus.FAILED.value
                                 for status in statuses),
            "completed_tasks": sum(status in _COMPLETED for status in statuses),
            "pending_approvals": sum(row.get("status") == "ACTIVE" and
                                      row.get("decision", "PENDING") == "PENDING" and
                                      float(row.get("expires_at", 0) or 0) >= now
                                      for row in approvals),
            "next_due_task": self._next_due_from_views(task_views),
        }

    @staticmethod
    def _next_due_from_views(views):
        candidates = [item for item in views if item["enabled"] and
                      item["status"] not in _TERMINAL | _RUNNING and
                      item["next_run_at"] is not None]
        candidates.sort(key=lambda item: (
            item["next_run_at"], item["created_at"], item["task_id"]))
        if not candidates:
            return None
        item = candidates[0]
        return {key: item[key] for key in ("task_id", "status", "next_run_at", "trigger_type")}

    def _task_view(self, task, runs, approvals):
        task_runs = [run for run in runs if run.get("task_id") == task.task_id]
        task_runs.sort(key=self._run_sort_key, reverse=True)
        latest = task_runs[0] if task_runs else None
        current = next((run for run in task_runs if run.get("status") in _CURRENT_RUN), None)
        active_approvals = [row for row in approvals if row.get("task_id") == task.task_id
                            and row in self._pending_approval_rows([task], approvals)]
        failed = next((run for run in task_runs if run.get("status") == RunStatus.FAILED.value), None)
        return {
            "task_id": task.task_id,
            "title": task.user_request,
            "description": task.user_request,
            "task_type": task.task_type,
            "enabled": task.enabled,
            "status": task.status.value,
            "trigger_type": task.trigger_type.value,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "next_run_at": task.next_run_at,
            "last_run_at": task.last_run_at,
            "last_run_status": latest.get("status") if latest else None,
            "current_run_id": current.get("run_id") if current else None,
            "mission_id": (current or latest or {}).get("mission_id"),
            "waiting_reason": self._waiting_reason(task),
            "failure_reason": self._failure_reason(failed),
            "approval_state": {"status": "PENDING" if active_approvals else "NONE",
                               "count": len(active_approvals)},
            "recurrence": (dict(task.trigger_config)
                           if task.trigger_type.value == "RECURRING" else None),
        }

    def _run_view(self, run, approvals):
        now = float(self.now_provider())
        run_approvals = [row for row in approvals if row.get("run_id") == run.get("run_id")]
        active = [row for row in run_approvals if row.get("status") == "ACTIVE"
                   and row.get("decision", "PENDING") == "PENDING"
                   and float(row.get("expires_at", 0) or 0) >= now]
        expires = run.get("claim_expires_at")
        return {
            "run_id": run.get("run_id"),
            "task_id": run.get("task_id"),
            "mission_id": run.get("mission_id"),
            "status": run.get("status"),
            "scheduled_for": run.get("scheduled_for"),
            "created_at": run.get("created_at"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("finished_at"),
            "failure_reason": self._failure_reason(run),
            "claim_state": {
                "claimed": bool(run.get("claim_token")),
                "claimed_by": run.get("claimed_by"),
                "lease_active": bool(expires and float(expires) > now),
                "lease_expires_at": expires,
            },
            "approval_state": {"status": "PENDING" if active else "NONE",
                               "count": len(active)},
            **({"retry_eligibility": self.retry_eligibility(run["run_id"]),
                "recovery_eligibility": self.recovery_eligibility(run["run_id"])}
               if self.retry_eligibility and self.recovery_eligibility else {}),
        }

    @staticmethod
    def _approval_view(row):
        return {key: row.get(key) for key in (
            "approval_id", "task_id", "run_id", "mission_id", "scope", "target",
            "granted_at", "expires_at", "single_use", "status", "decision",
            "decided_at", "decided_by")}

    @staticmethod
    def _failure_reason(run):
        if not run:
            return None
        if not run.get("error_code") and not run.get("error_message"):
            return None
        return {"code": run.get("error_code"), "message": run.get("error_message")}

    @staticmethod
    def _waiting_reason(task):
        status = task.status.value
        reasons = {
            BackgroundTaskStatus.WAITING_TRIGGER.value: "aguardando condição/horário configurado",
            BackgroundTaskStatus.WAITING_USER_IDLE.value: "aguardando usuário ficar ocioso + quiet window",
            BackgroundTaskStatus.WAITING_CONFIRMATION.value: "aguardando autorização humana",
            BackgroundTaskStatus.PAUSED.value: "pausada por controle operacional",
            BackgroundTaskStatus.SCHEDULED.value: "agendada para a próxima execução",
        }
        if status not in reasons:
            return None
        return {"code": status, "explanation": reasons[status]}

    @staticmethod
    def _task_sort_key(task):
        return (task.next_run_at is None,
                task.next_run_at if task.next_run_at is not None else float("inf"),
                task.created_at, task.task_id)

    @staticmethod
    def _run_sort_key(run):
        return (run.get("started_at") or run.get("created_at") or 0,
                run.get("run_id") or "")


__all__ = ["BackgroundControlCenter", "READ_ONLY_BACKGROUND_OBSERVATION"]
