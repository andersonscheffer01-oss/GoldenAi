"""Handlers for background conditions that do not require a GUI mission."""

import time
from pathlib import Path

from .background import ConditionType, TriggerType


class ConditionAuditExecutor:
    """Record a satisfied allow-listed condition without touching its target."""

    def __init__(self, audit):
        self.audit = audit

    def __call__(self, task, run):
        if task.trigger_type != TriggerType.CONDITION:
            return {"ok": False, "error_code": "INVALID_CONDITION_TASK"}

        config = dict(task.trigger_config or {})
        condition_type = str(config.get("condition_type", config.get("type", ""))).upper()
        if condition_type != ConditionType.FILE_EXISTS.value:
            return {"ok": False, "error_code": "UNSUPPORTED_CONDITION_TYPE"}

        raw_target = config.get("path")
        if not isinstance(raw_target, str) or not raw_target.strip():
            return {"ok": False, "error_code": "CONDITION_TARGET_REQUIRED"}
        target = Path(raw_target).expanduser().resolve(strict=False)
        if not target.is_file():
            return {"ok": False, "error_code": "CONDITION_NOT_SATISFIED"}

        details = {
            "task_id": task.task_id,
            "run_id": run["run_id"],
            "condition_type": condition_type,
            "target": str(target),
            "timestamp": time.time(),
        }
        self.audit.add(
            task_id=task.task_id,
            command="CONDITION_TRIGGER_SATISFIED",
            tool="condition_executor",
            arguments=details,
            risk="LOW",
            status="info",
            result="CONDITION_TRIGGER_SATISFIED",
        )
        return {
            "ok": True,
            "condition_type": condition_type,
            "target": str(target),
            "condition_trigger_satisfied": True,
            "mission_required": False,
        }
