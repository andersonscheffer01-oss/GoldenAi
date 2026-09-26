import json
import sqlite3

from jarvis_core.task_manager import (
    BackgroundControlCenter,
    BackgroundTask,
    BackgroundTaskScheduler,
    BackgroundTaskStatus,
    FakeClock,
    RunStatus,
    TaskDatabase,
    TaskManager,
    TriggerType,
)


def make_task(clock, task_id, trigger=TriggerType.IMMEDIATE, config=None, **kwargs):
    return BackgroundTask(
        task_id=task_id,
        user_request=f"request {task_id}",
        task_type="computer_use",
        trigger_type=trigger,
        trigger_config=config or {},
        created_at=clock.now(),
        updated_at=clock.now(),
        next_run_at=kwargs.pop("next_run_at", clock.now()),
        **kwargs,
    )


def make_center(tmp_path, now=100):
    clock = FakeClock(now)
    database = TaskDatabase(tmp_path / "tasks.db")
    scheduler = BackgroundTaskScheduler(database, clock=clock)
    return database, BackgroundControlCenter(database, scheduler, now_provider=clock.now)


def test_empty_control_center_is_deterministic(tmp_path):
    database, center = make_center(tmp_path)

    assert center.get_summary() == {
        "total_tasks": 0,
        "enabled_tasks": 0,
        "running_tasks": 0,
        "waiting_tasks": 0,
        "failed_tasks": 0,
        "completed_tasks": 0,
        "pending_approvals": 0,
        "next_due_task": None,
    }
    snapshot = center.get_snapshot()
    assert snapshot["security_classification"] == "READ_ONLY_BACKGROUND_OBSERVATION"
    assert snapshot["read_only"] is True
    assert snapshot["tasks"] == []
    assert snapshot["recent_runs"] == []
    assert snapshot["scheduler"]["database_path"] == str(database.path)


def test_mixed_task_states_and_waiting_reasons(tmp_path):
    database, center = make_center(tmp_path)
    clock = FakeClock(100)
    tasks = [
        make_task(clock, "waiting-trigger", TriggerType.CONDITION,
                  {"condition_type": "FILE_EXISTS", "path": "marker"},
                  status=BackgroundTaskStatus.WAITING_TRIGGER, next_run_at=120),
        make_task(clock, "waiting-idle", TriggerType.USER_IDLE,
                  {"seconds": 10}, status=BackgroundTaskStatus.WAITING_USER_IDLE,
                  next_run_at=140),
        make_task(clock, "waiting-confirm", status=BackgroundTaskStatus.WAITING_CONFIRMATION,
                  next_run_at=150),
        make_task(clock, "running", status=BackgroundTaskStatus.RUNNING),
        make_task(clock, "failed", status=BackgroundTaskStatus.FAILED, enabled=False),
        make_task(clock, "completed", status=BackgroundTaskStatus.EXPIRED, enabled=False),
    ]
    for task in tasks:
        database.create_background_task(task)

    running = database.ensure_task_run("running", 100, 100)
    database.update_task_run(running["run_id"], status=RunStatus.RUNNING,
                             started_at=100)
    failed = database.ensure_task_run("failed", 100, 100)
    database.update_task_run(failed["run_id"], status=RunStatus.FAILED,
                             finished_at=101, error_code="TEST_FAILURE",
                             error_message="controlled failure")
    completed = database.ensure_task_run("completed", 100, 100)
    database.update_task_run(completed["run_id"], status=RunStatus.COMPLETED,
                             finished_at=101)

    snapshot = center.get_snapshot()
    assert snapshot["summary"] == {
        "total_tasks": 6,
        "enabled_tasks": 4,
        "running_tasks": 1,
        "waiting_tasks": 3,
        "failed_tasks": 1,
        "completed_tasks": 1,
        "pending_approvals": 0,
        "next_due_task": {
            "task_id": "waiting-trigger",
            "status": "WAITING_TRIGGER",
            "next_run_at": 120.0,
            "trigger_type": "CONDITION",
        },
    }
    by_id = {item["task_id"]: item for item in snapshot["tasks"]}
    assert by_id["waiting-trigger"]["waiting_reason"]["code"] == "WAITING_TRIGGER"
    assert by_id["waiting-idle"]["waiting_reason"]["code"] == "WAITING_USER_IDLE"
    assert by_id["waiting-confirm"]["waiting_reason"]["code"] == "WAITING_CONFIRMATION"
    assert by_id["running"]["current_run_id"] == running["run_id"]
    assert by_id["failed"]["failure_reason"] == {
        "code": "TEST_FAILURE", "message": "controlled failure"}


def test_next_due_task_uses_scheduler_persisted_deadline(tmp_path):
    database, center = make_center(tmp_path)
    clock = FakeClock(100)
    late = make_task(clock, "late", next_run_at=130)
    early = make_task(clock, "early", next_run_at=110)
    database.create_background_task(late)
    database.create_background_task(early)

    assert center.get_next_due_task()["task_id"] == "early"
    assert center.list_tasks(limit=2)[0]["task_id"] == "early"


def test_run_history_is_ordered_and_failure_is_structured(tmp_path):
    database, center = make_center(tmp_path)
    clock = FakeClock(100)
    task = make_task(clock, "history")
    database.create_background_task(task)
    first = database.ensure_task_run(task.task_id, 100, 100)
    second = database.ensure_task_run(task.task_id, 110, 110)
    database.update_task_run(first["run_id"], status=RunStatus.FAILED,
                             started_at=100, finished_at=101,
                             error_code="TIMEOUT", error_message="timed out")
    database.update_task_run(second["run_id"], status=RunStatus.COMPLETED,
                             started_at=110, finished_at=111)

    runs = center.list_runs(task.task_id)
    assert [run["run_id"] for run in runs] == [second["run_id"], first["run_id"]]
    assert runs[1]["failure_reason"] == {"code": "TIMEOUT", "message": "timed out"}
    assert "claim_token" not in runs[0]


def test_pending_approval_observation_does_not_consume(tmp_path):
    database, center = make_center(tmp_path)
    clock = FakeClock(100)
    task = make_task(clock, "approval")
    database.create_background_task(task)
    run = database.ensure_task_run(task.task_id, 100, 100)
    approval_id = database.create_task_approval(
        task.task_id, run["run_id"], "write_file", "target.txt", 100, 200)

    before = database.list_task_approvals(task_id=task.task_id)
    pending = center.list_pending_approvals()
    after = database.list_task_approvals(task_id=task.task_id)

    assert pending[0]["approval_id"] == approval_id
    assert before == after
    assert after[0]["status"] == "ACTIVE"
    assert after[0]["consumed_at"] is None


def test_completed_condition_task_is_observable_without_reactivation(tmp_path):
    database, center = make_center(tmp_path)
    clock = FakeClock(100)
    task = make_task(clock, "condition-done", TriggerType.CONDITION,
                     {"condition_type": "FILE_EXISTS", "path": "marker"},
                     status=BackgroundTaskStatus.EXPIRED, enabled=False,
                     run_count=1, max_runs=1)
    database.create_background_task(task)
    run = database.ensure_task_run(task.task_id, 100, 100)
    database.update_task_run(run["run_id"], status=RunStatus.COMPLETED,
                             started_at=100, finished_at=101)

    before = database.get_background_task(task.task_id)
    observed = center.get_task(task.task_id)
    after = database.get_background_task(task.task_id)

    assert observed["status"] == "EXPIRED"
    assert observed["trigger_type"] == "CONDITION"
    assert before == after


def test_read_only_queries_have_no_operational_side_effects(tmp_path):
    database, center = make_center(tmp_path)
    clock = FakeClock(100)
    task = make_task(clock, "stable", TriggerType.CONDITION,
                     {"condition_type": "FILE_EXISTS", "path": "marker"},
                     status=BackgroundTaskStatus.WAITING_TRIGGER)
    database.create_background_task(task)
    before = json.dumps(_counts(database), sort_keys=True)

    center.get_snapshot()
    center.get_summary()
    center.list_tasks()
    center.get_task(task.task_id)
    center.list_runs()
    center.get_next_due_task()
    center.list_pending_approvals()

    after = json.dumps(_counts(database), sort_keys=True)
    assert before == after


def test_task_manager_reuses_canonical_scheduler_and_database(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        assert manager.control_center.scheduler is manager.scheduler
        assert manager.control_center.database is manager.database
        assert manager.control_center.database.path == tmp_path / "jarvis" / "golden_tasks.db"
        assert manager.background_control_snapshot()["summary"]["total_tasks"] == 0
    finally:
        manager.shutdown()


def _counts(database):
    with database.connect() as db:
        return {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("background_tasks", "task_runs", "task_approvals")
        }
