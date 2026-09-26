from jarvis_core.computer_use_mission import ComputerMissionExecutor
from jarvis_core.service import JarvisService
from jarvis_core.task_manager import (
    BackgroundTask, BackgroundTaskScheduler, BackgroundTaskStatus,
    FakeClock, RunStatus, TaskManager, TriggerType,
)


def _condition_manager(tmp_path, target, task_type="condition_audit"):
    manager = TaskManager(tmp_path)
    task_id = manager.schedule_background(
        "Record the condition when the marker exists.",
        task_type=task_type,
        trigger_type=TriggerType.CONDITION,
        trigger_config={"condition_type": "FILE_EXISTS", "path": str(target)},
        max_runs=1,
        security_scope={"scope": "TEST", "action": "AUDIT_ONLY"},
    )
    return manager, task_id


def test_condition_false_then_true_uses_condition_executor_and_completes(tmp_path):
    marker = tmp_path / "trigger.txt"
    manager, task_id = _condition_manager(tmp_path, marker)
    try:
        calls = []
        scheduler = BackgroundTaskScheduler(
            manager.database, audit=manager.audit,
            launcher=lambda task, run: calls.append(run["run_id"]) or
            manager.execute_background_task(task, run),
        )

        scheduler.tick()
        assert manager.background(task_id).status == BackgroundTaskStatus.WAITING_TRIGGER
        assert manager.background_runs(task_id) == []

        marker.write_text("", encoding="utf-8")
        assert scheduler.tick() == [(task_id, "COMPLETED")]
        assert len(calls) == 1
        assert manager.background(task_id).status == BackgroundTaskStatus.EXPIRED
        assert manager.background(task_id).enabled is False
        assert manager.background(task_id).run_count == 1
        run = manager.background_runs(task_id)[0]
        assert run["status"] == RunStatus.COMPLETED.value
        assert run["mission_id"] is None
        assert marker.read_text(encoding="utf-8") == ""

        events = [row["command"] for row in manager.audit.recent(50)
                  if row["task_id"] == task_id]
        assert "CONDITION_TRIGGER_SATISFIED" in events
        assert "TASK_RUN_COMPLETED" in events
        assert "CLAIM_FINALIZED" in events
    finally:
        manager.shutdown()


def test_condition_audit_routes_without_computer_mission(tmp_path):
    marker = tmp_path / "trigger.txt"
    marker.write_text("", encoding="utf-8")
    manager, task_id = _condition_manager(tmp_path, marker)
    try:
        task = manager.background(task_id)
        run = manager.database.ensure_task_run(task_id, task.next_run_at, task.created_at)
        called = []
        manager.execute_background_task = lambda task, run: called.append(True) or {
            "ok": True, "mission_required": False}
        service = object.__new__(JarvisService)
        service.task_manager = manager

        result = JarvisService._launch_background_task(service, task, run)

        assert called == [True]
        assert result["mission_required"] is False
    finally:
        manager.shutdown()


def test_unknown_background_task_type_fails_closed(tmp_path):
    marker = tmp_path / "trigger.txt"
    marker.write_text("", encoding="utf-8")
    manager, task_id = _condition_manager(tmp_path, marker, task_type="unknown_type")
    try:
        task = manager.background(task_id)
        run = manager.database.ensure_task_run(task_id, task.next_run_at, task.created_at)
        service = object.__new__(JarvisService)
        service.task_manager = manager
        result = JarvisService._launch_background_task(service, task, run)
        assert result == {"ok": False, "error_code": "UNSUPPORTED_TASK_TYPE"}
    finally:
        manager.shutdown()


def test_failed_one_shot_is_terminal_across_ticks_and_restart(tmp_path):
    clock = FakeClock(100)
    manager = TaskManager(tmp_path)
    try:
        task = BackgroundTask.new("fail once", "computer_use", TriggerType.IMMEDIATE,
                                  created_at=100, updated_at=100, next_run_at=100,
                                  max_runs=1)
        manager.database.create_background_task(task)
        task_id = task.task_id
        calls = []
        scheduler = BackgroundTaskScheduler(
            manager.database, clock=clock,
            launcher=lambda _task, run: calls.append(run["run_id"]) or {
                "ok": False, "error_code": "LAUNCH_FAILED"},
        )
        scheduler.tick()
        scheduler.tick()
        assert len(calls) == 1
        assert manager.background(task_id).status == BackgroundTaskStatus.FAILED
        assert manager.background(task_id).enabled is False
        assert len(manager.background_runs(task_id)) == 1

        restarted = BackgroundTaskScheduler(
            manager.database, clock=clock,
            launcher=lambda _task, _run: calls.append("unexpected") or {"ok": True},
        )
        restarted.tick()
        assert len(calls) == 1
    finally:
        manager.shutdown()


def test_recurring_failure_waits_for_future_occurrence(tmp_path):
    clock = FakeClock(100)
    manager = TaskManager(tmp_path)
    try:
        task = BackgroundTask.new(
            "fail recurring", "computer_use", TriggerType.RECURRING,
            {"mode": "INTERVAL", "seconds": 10},
            created_at=100, updated_at=100, max_runs=None,
        )
        manager.database.create_background_task(task)
        task_id = task.task_id
        calls = []
        scheduler = BackgroundTaskScheduler(
            manager.database, clock=clock,
            launcher=lambda _task, run: calls.append(run["run_id"]) or {
                "ok": False, "error_code": "LAUNCH_FAILED"},
        )
        scheduler.tick()
        clock.advance(10)
        scheduler.tick()
        assert len(calls) == 1
        assert manager.background(task_id).status == BackgroundTaskStatus.SCHEDULED
        clock.advance(9)
        scheduler.tick()
        assert len(calls) == 1
        clock.advance(1)
        scheduler.tick()
        assert len(calls) == 2
    finally:
        manager.shutdown()


def test_condition_and_mission_persistence_share_canonical_database(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        class StubService:
            registry = {}
            task_manager = manager

        mission = ComputerMissionExecutor(StubService())
        assert manager.database.path == (tmp_path / "jarvis" / "golden_tasks.db").resolve()
        assert mission.persistence.database is manager.database
    finally:
        manager.shutdown()
