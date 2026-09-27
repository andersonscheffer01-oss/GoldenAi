import json
import time

from jarvis_core.task_manager import (
    BackgroundTask, BackgroundTaskStatus, FakeClock, RunStatus, TaskDatabase,
    TaskManager, TriggerType,
)


def _task(database, clock, task_id="task", status=BackgroundTaskStatus.SCHEDULED,
          task_type="condition_audit"):
    task = BackgroundTask(
        task_id=task_id, user_request="background request", task_type=task_type,
        trigger_type=TriggerType.IMMEDIATE, trigger_config={},
        created_at=clock.now(), updated_at=clock.now(),
        next_run_at=clock.now(), status=status)
    database.create_background_task(task)
    return task


def _approval(database, task, clock, expires_at=200, single_use=True):
    run = database.ensure_task_run(task.task_id, clock.now(), clock.now())
    approval_id = database.create_task_approval(
        task.task_id, run["run_id"], "write_file", "allowed.txt",
        clock.now(), expires_at, mission_id="mission-1", single_use=single_use)
    return run, approval_id


def test_approval_observation_and_notification_reads_are_non_mutating(tmp_path):
    clock = FakeClock(100)
    database = TaskDatabase(tmp_path / "tasks.db")
    task = _task(database, clock)
    run, approval_id = _approval(database, task, clock)
    from jarvis_core.task_manager import BackgroundControlCenter
    center = BackgroundControlCenter(database, now_provider=clock.now)
    before = json.dumps(database.list_task_approvals(), sort_keys=True)

    for _ in range(10):
        assert center.list_pending_approvals()[0]["approval_id"] == approval_id
        assert center.get_pending_approval(approval_id)["pending"] is True
        center.list_notifications()
        center.get_notification_summary()
        center.get_notification(f"approval-required:{approval_id}")

    assert json.dumps(database.list_task_approvals(), sort_keys=True) == before
    assert database.get_task_run(run["run_id"])["status"] == RunStatus.PENDING.value


def test_approval_and_denial_are_audited_and_single_decision(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        task_id = manager.schedule_background("approve me", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        approval_id = manager.create_background_approval(
            task_id, run["run_id"], "write_file", "allowed.txt", time.time() + 60)

        approved = manager.approve_background_approval(approval_id, actor="tester")
        assert approved["success"] is True
        assert approved["code"] == "APPROVAL_APPROVED"
        assert manager.approve_background_approval(approval_id)["code"] == "APPROVAL_ALREADY_DECIDED"
        assert manager.get_pending_background_approval(approval_id)["pending"] is False
        assert any(item["command"] == "APPROVAL_GRANTED" for item in manager.audit.recent(20))
    finally:
        manager.shutdown()


def test_deny_blocks_consumption_without_cancelling_task(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        task_id = manager.schedule_background("deny me", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        approval_id = manager.create_background_approval(
            task_id, run["run_id"], "write_file", "allowed.txt", time.time() + 60)
        denied = manager.deny_background_approval(approval_id, actor="tester")
        assert denied["success"] is True
        assert manager.consume_background_approval(
            approval_id, task_id, run["run_id"], "write_file", "allowed.txt") is False
        assert manager.background(task_id).status == BackgroundTaskStatus.SCHEDULED
    finally:
        manager.shutdown()


def test_approval_deny_race_is_first_decision_wins(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        task_id = manager.schedule_background("race", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        approval_id = manager.create_background_approval(
            task_id, run["run_id"], "write_file", "allowed.txt", time.time() + 60)
        assert manager.deny_background_approval(approval_id)["success"] is True
        blocked = manager.approve_background_approval(approval_id)
        assert blocked["success"] is False
        assert blocked["code"] == "APPROVAL_ALREADY_DECIDED"
        assert manager.database.get_task_approval(approval_id)["decision"] == "DENIED"
    finally:
        manager.shutdown()


def test_expired_approval_is_stale_and_cannot_reactivate_cancelled_task(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        task_id = manager.schedule_background("stale", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        expired_id = manager.create_background_approval(
            task_id, run["run_id"], "write_file", "expired.txt", time.time() - 1)
        expired = manager.approve_background_approval(expired_id)
        assert expired["code"] == "STALE_APPROVAL"

        task_id = manager.schedule_background("cancelled", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        approval_id = manager.create_background_approval(
            task_id, run["run_id"], "write_file", "allowed.txt", time.time() + 60)
        confirmation = manager.cancel_background(task_id)
        assert confirmation["confirmation_required"] is True
        assert manager.cancel_background(task_id, confirmation["token"])["success"] is True
        result = manager.approve_background_approval(approval_id)
        assert result["code"] == "STALE_APPROVAL"
        assert manager.background(task_id).status == BackgroundTaskStatus.CANCELLED
    finally:
        manager.shutdown()


def test_paused_task_approval_does_not_bypass_pause(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        task_id = manager.schedule_background("paused", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        approval_id = manager.create_background_approval(
            task_id, run["run_id"], "write_file", "allowed.txt", time.time() + 60)
        assert manager.pause_background(task_id)["success"] is True
        assert manager.approve_background_approval(approval_id)["success"] is True
        assert manager.background(task_id).status == BackgroundTaskStatus.PAUSED
        assert manager.database.get_task_run(run["run_id"])["status"] == RunStatus.PENDING.value
    finally:
        manager.shutdown()


def test_notifications_are_deduplicated_and_failure_is_structured(tmp_path):
    clock = FakeClock(100)
    database = TaskDatabase(tmp_path / "tasks.db")
    task = _task(database, clock)
    run, approval_id = _approval(database, task, clock)
    database.update_task_run(run["run_id"], status=RunStatus.FAILED,
                             finished_at=101, error_code="FAILED", error_message="boom")
    from jarvis_core.task_manager import BackgroundControlCenter
    center = BackgroundControlCenter(database, now_provider=clock.now)
    first = center.list_notifications()
    second = center.list_notifications()
    assert [item["notification_id"] for item in first] == [item["notification_id"] for item in second]
    assert {item["type"] for item in first} == {"APPROVAL_REQUIRED", "TASK_FAILED"}
    failed = next(item for item in first if item["type"] == "TASK_FAILED")
    assert failed["severity"] == "ERROR"
    assert failed["actionability"] == "RECOVERY_DECISION_REQUIRED"
    assert center.get_notification_summary()["action_required"] == 2
    assert center.get_notification(f"approval-required:{approval_id}")["status"] == "NEW"


def test_approval_schema_migration_is_additive(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db")
    with database.connect() as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(task_approvals)")}
        version = db.execute("SELECT version FROM task_schema_version").fetchone()[0]
    assert {"decision", "decided_at", "decided_by"} <= columns
    assert version == 5
