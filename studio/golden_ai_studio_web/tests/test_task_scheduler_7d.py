"""Non-real regression coverage for Computer Use 7D.1 infrastructure."""
import sqlite3
import threading
from datetime import datetime, timezone

from jarvis_core.task_manager import (
    BackgroundTask, BackgroundTaskScheduler, BackgroundTaskStatus, ConditionEvaluator,
    FakeClock, MisfirePolicy, RunStatus, TaskDatabase, TriggerType,
)


def make_task(clock, trigger=TriggerType.IMMEDIATE, config=None, **kwargs):
    return BackgroundTask.new("test background mission", "computer_use", trigger,
                              config, created_at=clock.now(), updated_at=clock.now(),
                              **kwargs)


def test_schema_v1_migrates_without_losing_legacy_task(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE task_schema_version(version INTEGER NOT NULL);
            INSERT INTO task_schema_version VALUES(1);
            CREATE TABLE tasks(id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
              status TEXT NOT NULL, data_classification TEXT NOT NULL, created_at REAL NOT NULL,
              updated_at REAL NOT NULL, started_at REAL, finished_at REAL, cancel_requested_at REAL,
              error TEXT NOT NULL, result TEXT, metadata TEXT NOT NULL, timeout_seconds REAL NOT NULL);
            CREATE TABLE task_steps(task_id TEXT NOT NULL, step_id TEXT NOT NULL, position INTEGER NOT NULL,
              intent TEXT NOT NULL, route TEXT NOT NULL, tool TEXT, args TEXT NOT NULL,
              dependencies TEXT NOT NULL, cancellable INTEGER NOT NULL, background INTEGER NOT NULL,
              status TEXT NOT NULL, started_at REAL, finished_at REAL, error TEXT NOT NULL, result TEXT,
              PRIMARY KEY(task_id, step_id));
            CREATE TABLE task_events(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
              timestamp REAL NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL);
            INSERT INTO tasks VALUES('legacy','legacy','legacy','QUEUED','PUBLIC',1,1,NULL,NULL,NULL,'','{}','{}',30);
        """)
    store = TaskDatabase(path)
    assert store.get_task("legacy").title == "legacy"
    assert store.connect
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version FROM task_schema_version").fetchone()[0] == 2
        assert db.execute("SELECT name FROM sqlite_master WHERE name='background_tasks'").fetchone()


def test_immediate_delay_and_at_time_dispatch_once(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    calls = []
    scheduler = BackgroundTaskScheduler(store, launcher=lambda task, run: calls.append(run["run_id"]) or {"ok": True}, clock=clock)
    immediate = make_task(clock)
    delayed = make_task(clock, TriggerType.AFTER_DELAY, {"seconds": 5})
    at_time = make_task(clock, TriggerType.AT_TIME, {"timestamp": 110})
    for task in (immediate, delayed, at_time):
        store.create_background_task(task)
    scheduler.tick()
    assert len(calls) == 1
    scheduler.tick()
    assert len(calls) == 1
    clock.advance(5)
    scheduler.tick()
    assert len(calls) == 2
    clock.advance(5)
    scheduler.tick()
    assert len(calls) == 3
    assert all(len(store.list_task_runs(task.task_id)) == 1 for task in (immediate, delayed, at_time))


def test_recurring_interval_has_unique_occurrences_and_max_runs(tmp_path):
    clock = FakeClock(0)
    store = TaskDatabase(tmp_path / "tasks.db")
    calls = []
    scheduler = BackgroundTaskScheduler(store, launcher=lambda task, run: calls.append(run["run_id"]) or {"ok": True}, clock=clock)
    task = make_task(clock, TriggerType.RECURRING, {"mode": "INTERVAL", "seconds": 10}, max_runs=2)
    store.create_background_task(task)
    scheduler.tick()
    assert calls == []
    clock.advance(10)
    scheduler.tick()
    scheduler.tick()
    assert len(calls) == 1
    clock.advance(10)
    scheduler.tick()
    assert len(calls) == 2
    assert len(store.list_task_runs(task.task_id)) == 2
    assert store.get_background_task(task.task_id).status == BackgroundTaskStatus.EXPIRED


def test_daily_and_weekly_recurrence_use_timezone(tmp_path):
    # 2026-01-05 11:00 UTC, Monday.
    clock = FakeClock(datetime(2026, 1, 5, 11, tzinfo=timezone.utc).timestamp())
    store = TaskDatabase(tmp_path / "tasks.db")
    scheduler = BackgroundTaskScheduler(store, clock=clock)
    daily = make_task(clock, TriggerType.RECURRING, {"mode": "DAILY", "time": "12:00"}, timezone="UTC")
    weekly = make_task(clock, TriggerType.RECURRING, {"mode": "WEEKLY", "weekday": 2, "time": "12:00"}, timezone="UTC")
    store.create_background_task(daily)
    store.create_background_task(weekly)
    scheduler.tick()
    assert store.get_background_task(daily.task_id).next_run_at == datetime(2026, 1, 5, 12, tzinfo=timezone.utc).timestamp()
    assert store.get_background_task(weekly.task_id).next_run_at == datetime(2026, 1, 7, 12, tzinfo=timezone.utc).timestamp()


def test_safe_conditions_are_injected_and_allow_listed(tmp_path):
    marker = tmp_path / "ready.txt"
    state = {"app": True, "idle": 30, "mission": "DONE", "service": True}
    evaluator = ConditionEvaluator(
        app_provider=lambda name: state["app"] and name == "notepad.exe",
        idle_provider=lambda: state["idle"],
        mission_provider=lambda _id: state["mission"],
        service_provider=lambda name: state["service"] and name == "ollama",
        now_provider=lambda: datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert evaluator.evaluate({"type": "FILE_NOT_EXISTS", "path": str(marker)})
    marker.write_text("ok", encoding="utf-8")
    assert evaluator.evaluate({"type": "FILE_EXISTS", "path": str(marker)})
    assert evaluator.evaluate({"type": "APP_RUNNING", "app": "notepad.exe"})
    assert evaluator.evaluate({"type": "USER_IDLE", "seconds": 20})
    assert evaluator.evaluate({"type": "TIME_WINDOW", "start": "11:00", "end": "13:00"})
    assert evaluator.evaluate({"type": "MISSION_STATUS", "mission_id": "m", "status": "DONE"})
    assert evaluator.evaluate({"type": "LOCAL_SERVICE_AVAILABLE", "service": "ollama"})


def test_condition_and_user_idle_triggers_wait_then_dispatch(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    state = {"ready": False, "idle": 0}
    evaluator = ConditionEvaluator(idle_provider=lambda: state["idle"])
    calls = []
    scheduler = BackgroundTaskScheduler(store, clock=clock, condition_evaluator=evaluator,
        launcher=lambda task, run: calls.append(task.task_id) or {"ok": True})
    idle = make_task(clock, TriggerType.USER_IDLE, {"seconds": 10})
    condition = make_task(clock, TriggerType.CONDITION,
                          {"type": "FILE_EXISTS", "path": str(tmp_path / "ready")})
    store.create_background_task(idle)
    store.create_background_task(condition)
    scheduler.tick()
    assert calls == []
    state["idle"] = 10
    (tmp_path / "ready").write_text("ok", encoding="utf-8")
    scheduler.tick()
    assert len(calls) == 2


def test_cancel_disable_enable_and_secret_rejection(tmp_path):
    from jarvis_core.task_manager import TaskManager
    manager = TaskManager(tmp_path)
    try:
        try:
            manager.schedule_background("x", trigger_config={"api_key": "hidden"})
            assert False, "secret should be rejected"
        except ValueError:
            pass
        task_id = manager.schedule_background("x")
        manager.disable_background(task_id)
        assert manager.background(task_id).status == BackgroundTaskStatus.DISABLED
        manager.enable_background(task_id)
        assert manager.background(task_id).enabled is True
        manager.cancel_background(task_id)
        assert manager.background(task_id).status == BackgroundTaskStatus.CANCELLED
    finally:
        manager.shutdown()


def test_task_manager_persists_absolute_after_delay_at_creation(tmp_path):
    from jarvis_core.task_manager import TaskManager
    manager = TaskManager(tmp_path)
    try:
        before = __import__("time").time()
        task_id = manager.schedule_background("x", trigger_type=TriggerType.AFTER_DELAY,
                                              trigger_config={"seconds": 120})
        task = manager.background(task_id)
        assert task.next_run_at is not None
        assert before + 119 <= task.next_run_at <= __import__("time").time() + 121
    finally:
        manager.shutdown()


def test_claims_are_atomic_and_expired_claims_recover(tmp_path):
    path = tmp_path / "tasks.db"
    first, second = TaskDatabase(path), TaskDatabase(path)
    clock = FakeClock(100)
    task = make_task(clock)
    first.create_background_task(task)
    run = first.ensure_task_run(task.task_id, 100, 100)
    results = []

    def claim(db, worker):
        results.append(db.claim_task_run(run["run_id"], worker, 100, lease_seconds=50) is not None)

    a, b = threading.Thread(target=claim, args=(first, "a")), threading.Thread(target=claim, args=(second, "b"))
    a.start(); b.start(); a.join(); b.join()
    assert sorted(results) == [False, True]
    assert first.recover_background_runs(200) == 1
    assert first.claim_task_run(run["run_id"], "c", 200) is not None


def test_expired_claim_with_existing_mission_is_not_duplicated(tmp_path):
    store = TaskDatabase(tmp_path / "tasks.db")
    clock = FakeClock(100)
    task = make_task(clock)
    store.create_background_task(task)
    run = store.ensure_task_run(task.task_id, 100, 100)
    claimed = store.claim_task_run(run["run_id"], "owner", 100, lease_seconds=1)
    store.update_task_run(claimed["run_id"], mission_id="mission-existing")
    assert store.claim_task_run(run["run_id"], "other", 200) is None


def test_approval_is_scoped_and_single_use(tmp_path):
    store = TaskDatabase(tmp_path / "tasks.db")
    clock = FakeClock(100)
    task = make_task(clock)
    store.create_background_task(task)
    run = store.ensure_task_run(task.task_id, 100, 100)
    approval = store.create_task_approval(task.task_id, run["run_id"], "SAVE", "target.txt", 100, 200)
    assert not store.consume_task_approval(approval, task.task_id, run["run_id"], "DELETE", "target.txt", 101)
    assert store.consume_task_approval(approval, task.task_id, run["run_id"], "SAVE", "target.txt", 101)
    assert not store.consume_task_approval(approval, task.task_id, run["run_id"], "SAVE", "target.txt", 102)


def test_waiting_confirmation_is_durable_and_has_no_second_dispatch(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    calls = []
    scheduler = BackgroundTaskScheduler(
        store, clock=clock,
        launcher=lambda task, run: calls.append(run["run_id"]) or {
            "status": "WAITING_CONFIRMATION", "mission_id": "mission-1"})
    task = make_task(clock)
    store.create_background_task(task)
    scheduler.tick()
    scheduler.tick()
    assert len(calls) == 1
    assert store.get_background_task(task.task_id).status == BackgroundTaskStatus.WAITING_CONFIRMATION
    assert store.list_task_runs(task.task_id)[0]["status"] == RunStatus.WAITING_CONFIRMATION.value


def test_waiting_confirmation_survives_scheduler_restart(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    task = make_task(clock)
    store.create_background_task(task)
    first_calls = []
    first = BackgroundTaskScheduler(store, clock=clock,
        launcher=lambda _task, run: first_calls.append(run["run_id"]) or {
            "status": "WAITING_CONFIRMATION", "mission_id": "mission-1"})
    first.tick()
    second_calls = []
    second = BackgroundTaskScheduler(store, clock=clock,
        launcher=lambda _task, run: second_calls.append(run["run_id"]) or {"ok": True})
    second.tick()
    assert len(first_calls) == 1
    assert second_calls == []
    assert store.get_background_task(task.task_id).status == BackgroundTaskStatus.WAITING_CONFIRMATION


def test_mission_user_activity_pause_maps_to_waiting_idle(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    task = make_task(clock)
    store.create_background_task(task)
    scheduler = BackgroundTaskScheduler(store, clock=clock,
        launcher=lambda _task, _run: {
            "ok": False, "error": "MISSION_PAUSED_FOR_USER_ACTIVITY",
            "mission": {"status": "PAUSED", "mission_id": "mission-activity"}})
    scheduler.tick()
    run = store.list_task_runs(task.task_id)[0]
    assert store.get_background_task(task.task_id).status == BackgroundTaskStatus.WAITING_USER_IDLE
    assert run["status"] == RunStatus.WAITING_USER_IDLE.value
    assert run["mission_id"] == "mission-activity"


def test_user_activity_precedes_stale_confirmation_state(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    task = make_task(clock)
    store.create_background_task(task)
    scheduler = BackgroundTaskScheduler(store, clock=clock,
        launcher=lambda _task, _run: {
            "ok": False, "status": "WAITING_CONFIRMATION",
            "pause_reason": "USER_ACTIVITY",
            "mission": {"status": "PAUSED", "error": "MISSION_PAUSED_FOR_USER_ACTIVITY",
                        "mission_id": "mission-activity"}})
    scheduler.tick()
    run = store.list_task_runs(task.task_id)[0]
    assert store.get_background_task(task.task_id).status == BackgroundTaskStatus.WAITING_USER_IDLE
    assert run["status"] == RunStatus.WAITING_USER_IDLE.value


def test_reconcile_existing_run_keeps_user_activity_out_of_confirmation(tmp_path):
    from jarvis_core.task_manager import TaskManager

    manager = TaskManager(tmp_path)
    try:
        clock = FakeClock(100)
        task = make_task(clock)
        manager.database.create_background_task(task)
        run = manager.database.ensure_task_run(task.task_id, 100, 100)
        manager.database.update_task_run(run["run_id"], mission_id="mission-activity",
                                         status=RunStatus.WAITING_CONFIRMATION)
        manager.database.update_background_task(task.task_id,
                                                status=BackgroundTaskStatus.WAITING_CONFIRMATION)
        state = manager.reconcile_background_mission_state(task.task_id, {
            "mission": {"mission_id": "mission-activity", "status": "PAUSED",
                        "error": "MISSION_PAUSED_FOR_USER_ACTIVITY",
                        "pause_reason": "USER_ACTIVITY"},
            "status": "WAITING_CONFIRMATION",
        })
        assert state == RunStatus.WAITING_USER_IDLE.value
        assert manager.background(task.task_id).status == BackgroundTaskStatus.WAITING_USER_IDLE
        assert manager.background_runs(task.task_id)[0]["status"] == RunStatus.WAITING_USER_IDLE.value
    finally:
        manager.shutdown()


def test_reconcile_confirmation_requires_explicit_security_result(tmp_path):
    from jarvis_core.task_manager import TaskManager

    manager = TaskManager(tmp_path)
    try:
        clock = FakeClock(100)
        task = make_task(clock)
        manager.database.create_background_task(task)
        run = manager.database.ensure_task_run(task.task_id, 100, 100)
        manager.database.update_task_run(run["run_id"], mission_id="mission-confirm")
        state = manager.reconcile_background_mission_state(task.task_id, {
            "mission": {"mission_id": "mission-confirm", "status": "PAUSED",
                        "error": "MISSION_PAUSED_FOR_USER_ACTIVITY",
                        "pause_reason": "USER_ACTIVITY"},
        })
        assert state == RunStatus.WAITING_USER_IDLE.value
        assert manager.background(task.task_id).status == BackgroundTaskStatus.WAITING_USER_IDLE
    finally:
        manager.shutdown()


def test_waiting_user_idle_is_rechecked_after_scheduler_restart(tmp_path):
    clock = FakeClock(100)
    store = TaskDatabase(tmp_path / "tasks.db")
    idle = {"seconds": 0}
    evaluator = ConditionEvaluator(idle_provider=lambda: idle["seconds"])
    task = make_task(clock, TriggerType.USER_IDLE, {"seconds": 10})
    store.create_background_task(task)
    first = BackgroundTaskScheduler(store, clock=clock, condition_evaluator=evaluator,
        launcher=lambda _task, _run: {"ok": True})
    first.tick()
    assert store.get_background_task(task.task_id).status == BackgroundTaskStatus.WAITING_USER_IDLE
    second_calls = []
    second = BackgroundTaskScheduler(store, clock=clock, condition_evaluator=evaluator,
        launcher=lambda _task, _run: second_calls.append(True) or {"ok": True})
    second.tick()
    assert second_calls == []
    idle["seconds"] = 10
    second.tick()
    assert second_calls == [True]


def test_misfire_skip_does_not_run_stale_one_shot(tmp_path):
    clock = FakeClock(1000)
    store = TaskDatabase(tmp_path / "tasks.db")
    calls = []
    scheduler = BackgroundTaskScheduler(store, clock=clock,
        launcher=lambda task, run: calls.append(run) or {"ok": True})
    task = make_task(clock, TriggerType.AT_TIME, {"timestamp": 1, "misfire_grace_seconds": 1},
                     misfire_policy=MisfirePolicy.SKIP_IF_MISSED)
    store.create_background_task(task)
    scheduler.tick()
    assert not calls
    assert store.get_background_task(task.task_id).enabled is False


def test_scheduler_start_stop_does_not_leave_thread(tmp_path):
    scheduler = BackgroundTaskScheduler(TaskDatabase(tmp_path / "tasks.db"), tick_interval=0.05)
    scheduler.start()
    scheduler.stop()
    assert scheduler._thread is None
