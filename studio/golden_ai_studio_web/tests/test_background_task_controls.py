import threading

from jarvis_core.task_manager import (
    BackgroundTask,
    BackgroundTaskScheduler,
    BackgroundTaskStatus,
    FakeClock,
    RunStatus,
    TaskDatabase,
    TaskManager,
    TriggerType,
)


def make_task(clock, task_id, trigger=TriggerType.IMMEDIATE, config=None,
              status=BackgroundTaskStatus.SCHEDULED, **kwargs):
    return BackgroundTask(
        task_id=task_id,
        user_request=f"request {task_id}",
        task_type="condition_audit",
        trigger_type=trigger,
        trigger_config=config or {},
        status=status,
        created_at=clock.now(),
        updated_at=clock.now(),
        next_run_at=kwargs.pop("next_run_at", clock.now()),
        **kwargs,
    )


def make_manager(tmp_path, now=100):
    manager = TaskManager(tmp_path)
    clock = FakeClock(now)
    manager.scheduler.clock = clock
    calls = []
    manager.scheduler.launcher = lambda task, run: calls.append(run["run_id"]) or {"ok": True}
    return manager, clock, calls


def create(manager, task):
    manager.database.create_background_task(task)
    return task.task_id


def confirm_cancel(manager, task_id):
    pending = manager.cancel_background(task_id)
    assert pending["confirmation_required"] is True
    return manager.cancel_background(task_id, pending["token"])


def test_pause_blocks_future_dispatch_and_resume_does_not_dispatch_directly(tmp_path):
    manager, clock, calls = make_manager(tmp_path)
    try:
        task_id = create(manager, make_task(clock, "pause-dispatch"))

        paused = manager.pause_background(task_id)
        assert paused["success"] is True
        assert manager.background(task_id).status == BackgroundTaskStatus.PAUSED
        assert manager.background(task_id).enabled is False
        assert manager.tick_scheduler() == []
        assert calls == []

        resumed = manager.resume_background(task_id)
        assert resumed["success"] is True
        assert calls == []
        assert manager.tick_scheduler() == [(task_id, "COMPLETED")]
        assert len(calls) == 1
    finally:
        manager.shutdown()


def test_pause_and_cancel_survive_database_reload_without_reexecution(tmp_path):
    manager, clock, calls = make_manager(tmp_path)
    try:
        paused_id = create(manager, make_task(clock, "paused-reload"))
        cancelled_id = create(manager, make_task(clock, "cancelled-reload"))
        assert manager.pause_background(paused_id)["success"] is True
        assert confirm_cancel(manager, cancelled_id)["success"] is True
        path = manager.database.path
    finally:
        manager.shutdown()

    restored = TaskDatabase(path)
    assert restored.get_background_task(paused_id).status == BackgroundTaskStatus.PAUSED
    assert restored.get_background_task(cancelled_id).status == BackgroundTaskStatus.CANCELLED
    scheduler = BackgroundTaskScheduler(restored, clock=clock,
                                        launcher=lambda *_: calls.append("unexpected") or {"ok": True})
    assert scheduler.tick() == []
    assert calls == []


def test_cancel_blocks_future_dispatch_and_preserves_terminal_intent(tmp_path):
    manager, clock, calls = make_manager(tmp_path)
    try:
        task_id = create(manager, make_task(clock, "cancel"))
        result = confirm_cancel(manager, task_id)
        assert result["new_state"] == BackgroundTaskStatus.CANCELLED.value
        assert manager.tick_scheduler() == []
        assert calls == []
        assert manager.background(task_id).enabled is False
        second = manager.cancel_background(task_id)
        assert second["confirmation_required"] is True
        assert manager.cancel_background(task_id, second["token"])["code"] == "ALREADY_CANCELLED"
    finally:
        manager.shutdown()


def test_controls_are_idempotent_and_invalid_transitions_are_structured(tmp_path):
    manager, clock, _calls = make_manager(tmp_path)
    try:
        paused_id = create(manager, make_task(clock, "idempotent-pause"))
        assert manager.pause_background(paused_id)["code"] == "PAUSED"
        assert manager.pause_background(paused_id)["code"] == "ALREADY_PAUSED"
        assert manager.resume_background(paused_id)["code"] == "RESUMED"
        assert manager.resume_background(paused_id)["code"] == "NOT_PAUSED"

        done_id = create(manager, make_task(clock, "completed",
                                             status=BackgroundTaskStatus.COMPLETED,
                                             enabled=False))
        assert manager.pause_background(done_id)["code"] == "INVALID_STATE_TRANSITION"
        assert manager.resume_background(done_id)["code"] == "INVALID_STATE_TRANSITION"
        assert manager.cancel_background(done_id)["confirmation_required"] is True
        assert manager.cancel_background("missing", "bad-token")["code"] == "INVALID_CONFIRMATION"
    finally:
        manager.shutdown()


def test_recurring_condition_and_user_idle_tasks_remain_blocked_while_paused(tmp_path):
    manager, clock, calls = make_manager(tmp_path)
    marker = tmp_path / "ready.txt"
    try:
        recurring = create(manager, make_task(clock, "recurring", TriggerType.RECURRING,
                                              {"mode": "INTERVAL", "seconds": 10}))
        condition = create(manager, make_task(clock, "condition", TriggerType.CONDITION,
                                              {"condition_type": "FILE_EXISTS", "path": str(marker)}))
        idle = create(manager, make_task(clock, "idle", TriggerType.USER_IDLE,
                                         {"seconds": 1}))
        for task_id in (recurring, condition, idle):
            assert manager.pause_background(task_id)["success"] is True
        marker.write_text("ready", encoding="utf-8")
        manager.scheduler.conditions.idle_provider = lambda: 10.0
        clock.advance(60)
        assert manager.tick_scheduler() == []
        assert calls == []
        for task_id in (recurring, condition, idle):
            assert manager.resume_background(task_id)["success"] is True
        assert len(manager.tick_scheduler()) == 3
        assert len(calls) == 3
    finally:
        manager.shutdown()


def test_waiting_confirmation_pause_does_not_consume_approval_or_dispatch(tmp_path):
    manager, clock, calls = make_manager(tmp_path)
    try:
        task = make_task(clock, "waiting-confirm", status=BackgroundTaskStatus.WAITING_CONFIRMATION)
        task_id = create(manager, task)
        run = manager.database.ensure_task_run(task_id, 100, 100)
        approval_id = manager.database.create_task_approval(
            task_id, run["run_id"], "write_file", "target.txt", 100, 200)
        paused = manager.pause_background(task_id)
        assert paused["success"] is True
        approval = manager.database.list_task_approvals(task_id=task_id)[0]
        assert approval["approval_id"] == approval_id
        assert approval["status"] == "ACTIVE"
        resumed = manager.resume_background(task_id)
        assert resumed["new_state"] == BackgroundTaskStatus.WAITING_CONFIRMATION.value
        assert manager.tick_scheduler() == []
        assert calls == []
    finally:
        manager.shutdown()


def test_active_run_pause_and_cancel_are_cooperative(tmp_path):
    manager, clock, _calls = make_manager(tmp_path)
    try:
        paused_id = create(manager, make_task(clock, "active-pause"))
        paused_run = manager.database.ensure_task_run(paused_id, 100, 100)
        manager.database.update_task_run(paused_run["run_id"], status=RunStatus.RUNNING)
        assert manager.pause_background(paused_id)["active_run_state"]["status"] == RunStatus.RUNNING.value
        assert manager.background(paused_id).status == BackgroundTaskStatus.PAUSED

        cancelled_id = create(manager, make_task(clock, "active-cancel"))
        cancelled_run = manager.database.ensure_task_run(cancelled_id, 100, 100)
        manager.database.update_task_run(cancelled_run["run_id"], status=RunStatus.RUNNING)
        result = confirm_cancel(manager, cancelled_id)
        assert result["active_run_state"]["status"] == RunStatus.RUNNING.value
        assert manager.background(cancelled_id).status == BackgroundTaskStatus.CANCELLED
    finally:
        manager.shutdown()


def test_pause_acknowledged_before_claim_cannot_be_followed_by_claim(tmp_path):
    manager, clock, _calls = make_manager(tmp_path)
    try:
        task_id = create(manager, make_task(clock, "claim-race"))
        ready = threading.Event()
        claimed = []

        def pause_first():
            result = manager.pause_background(task_id)
            assert result["success"] is True
            ready.set()

        def claim_after_pause():
            ready.wait(timeout=2)
            run = manager.database.ensure_task_run(task_id, 100, 100)
            if run:
                claimed.append(manager.database.claim_task_run(run["run_id"], "race", 100))

        first = threading.Thread(target=pause_first)
        second = threading.Thread(target=claim_after_pause)
        first.start(); second.start(); first.join(); second.join()
        assert claimed in ([], [None])
        assert manager.background_runs(task_id) == []
    finally:
        manager.shutdown()


def test_control_transitions_are_audited_once_and_read_only_views_remain_read_only(tmp_path):
    manager, clock, _calls = make_manager(tmp_path)
    try:
        task_id = create(manager, make_task(clock, "audit-controls"))
        before = manager.background_control_snapshot()
        manager.pause_background(task_id)
        manager.resume_background(task_id)
        confirm_cancel(manager, task_id)
        after = manager.background_control_snapshot()
        assert before["security_classification"] == "READ_ONLY_BACKGROUND_OBSERVATION"
        assert after["read_only"] is True
        events = [row["command"] for row in manager.audit.recent(100)
                  if row["task_id"] == task_id]
        assert events.count("BACKGROUND_TASK_PAUSED") == 1
        assert events.count("BACKGROUND_TASK_RESUMED") == 1
        assert events.count("BACKGROUND_TASK_CANCELLED") == 1
    finally:
        manager.shutdown()


def test_security_manager_requires_confirmation_for_cancel(tmp_path):
    manager, clock, _calls = make_manager(tmp_path)
    try:
        task_id = create(manager, make_task(clock, "security-cancel"))
        pending = manager.cancel_background(task_id)
        assert pending["confirmation_required"] is True
        assert manager.background(task_id).status == BackgroundTaskStatus.SCHEDULED
        invalid = manager.cancel_background(task_id, "invalid")
        assert invalid["code"] == "INVALID_CONFIRMATION"
        assert manager.background(task_id).status == BackgroundTaskStatus.SCHEDULED
    finally:
        manager.shutdown()
