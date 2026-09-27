"""8D.3 safe retry/recovery contracts over isolated task stores."""

import sqlite3
import time

from jarvis_core.computer_use_mission import ActionState, MissionCheckpointStore
from jarvis_core.task_manager import (
    BackgroundTask, BackgroundTaskScheduler, BackgroundTaskStatus, FakeClock,
    RunStatus, TaskDatabase, TaskManager, TriggerType,
)


def _failed_manager(tmp_path, *, task_type="condition_audit", budget=1,
                    error_code="TRANSIENT"):
    manager = TaskManager(tmp_path)
    task_id = manager.schedule_background(
        "retryable background work", task_type=task_type,
        trigger_config={"retry_budget": budget})
    run = manager.database.ensure_task_run(task_id, 100, 100)
    manager.database.update_task_run(
        run["run_id"], status=RunStatus.FAILED, finished_at=101,
        error_code=error_code, error_message="test failure")
    manager.database.update_background_task(
        task_id, status=BackgroundTaskStatus.FAILED, enabled=False, last_run_at=101)
    return manager, task_id, manager.database.get_task_run(run["run_id"])


def test_schema_v3_migrates_task_run_provenance_additively(tmp_path):
    path = tmp_path / "v3.db"
    store = TaskDatabase(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP INDEX IF EXISTS idx_runs_source")
        db.execute("ALTER TABLE task_runs RENAME TO task_runs_v4")
        db.execute("""CREATE TABLE task_runs(
            run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, scheduled_for REAL NOT NULL,
            status TEXT NOT NULL, created_at REAL NOT NULL, started_at REAL,
            finished_at REAL, mission_id TEXT, claim_token TEXT, claimed_by TEXT,
            claim_expires_at REAL, error_code TEXT, error_message TEXT,
            UNIQUE(task_id, scheduled_for))""")
        db.execute("""INSERT INTO task_runs SELECT run_id,task_id,scheduled_for,status,
            created_at,started_at,finished_at,mission_id,claim_token,claimed_by,
            claim_expires_at,error_code,error_message FROM task_runs_v4""")
        db.execute("DROP TABLE task_runs_v4")
        db.execute("UPDATE task_schema_version SET version=3")
    migrated = TaskDatabase(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(task_runs)")}
        assert db.execute("SELECT version FROM task_schema_version").fetchone()[0] == 4
    assert {"source_run_id", "attempt_kind", "attempt", "recovery_count"} <= columns
    assert migrated.path == path


def test_failed_run_creates_new_child_and_preserves_source(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path)
    try:
        eligibility = manager.get_retry_eligibility(source["run_id"], record_audit=False)
        assert eligibility["eligible"] is True
        assert eligibility["classification"] == "SAFE_TO_RETRY"
        result = manager.retry_background_run(source["run_id"])
        assert result["success"] is True
        child = manager.database.get_task_run(result["run"]["run_id"])
        assert child["run_id"] != source["run_id"]
        assert child["source_run_id"] == source["run_id"]
        assert child["attempt_kind"] == "RETRY"
        assert child["attempt"] == 2
        assert manager.database.get_task_run(source["run_id"])["status"] == RunStatus.FAILED.value
        assert manager.background(task_id).status == BackgroundTaskStatus.SCHEDULED
    finally:
        manager.shutdown()


def test_retry_eligibility_is_read_only_for_task_run_state(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path)
    try:
        before_task = manager.background(task_id)
        before_runs = manager.background_runs(task_id)
        retry = manager.get_retry_eligibility(source["run_id"], record_audit=False)
        recovery = manager.get_recovery_eligibility(source["run_id"], record_audit=False)
        assert retry["eligible"] is True
        assert recovery["eligible"] is False
        assert manager.background(task_id) == before_task
        assert manager.background_runs(task_id) == before_runs
        assert all(not run.get("claim_token") for run in before_runs)
    finally:
        manager.shutdown()


def test_completed_run_is_not_retryable(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path)
    try:
        manager.database.update_task_run(source["run_id"], status=RunStatus.COMPLETED)
        result = manager.retry_background_run(source["run_id"])
        assert result["success"] is False
        assert result["reason"] == "RUN_ALREADY_COMPLETED"
        assert len(manager.background_runs(task_id)) == 1
    finally:
        manager.shutdown()


def test_paused_and_cancelled_tasks_cannot_be_reactivated_by_retry(tmp_path):
    paused, paused_id, paused_run = _failed_manager(tmp_path / "paused")
    cancelled, cancelled_id, cancelled_run = _failed_manager(tmp_path / "cancelled")
    try:
        paused.database.update_background_task(
            paused_id, status=BackgroundTaskStatus.SCHEDULED, enabled=True)
        cancelled.database.update_background_task(
            cancelled_id, status=BackgroundTaskStatus.SCHEDULED, enabled=True)
        paused.database.control_background_task(paused_id, "pause")
        cancelled.database.control_background_task(cancelled_id, "cancel")
        assert paused.get_retry_eligibility(paused_run["run_id"], record_audit=False)["reason"] == "TASK_PAUSED"
        assert cancelled.get_retry_eligibility(cancelled_run["run_id"], record_audit=False)["reason"] == "TASK_CANCELLED"
        assert len(paused.background_runs(paused_id)) == 1
        assert len(cancelled.background_runs(cancelled_id)) == 1
    finally:
        paused.shutdown()
        cancelled.shutdown()


def test_retry_budget_and_idempotent_retry_request(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path, budget=1)
    try:
        first = manager.retry_background_run(source["run_id"])
        assert first["success"] is True
        second = manager.retry_background_run(source["run_id"])
        assert second["success"] is False
        assert second["reason"] == "RETRY_ALREADY_CREATED"
        child = manager.database.get_task_run(first["run"]["run_id"])
        manager.database.update_task_run(child["run_id"], status=RunStatus.FAILED,
                                         error_code="TRANSIENT")
        manager.database.update_background_task(task_id, status=BackgroundTaskStatus.FAILED,
                                                enabled=False)
        exhausted = manager.get_retry_eligibility(child["run_id"], record_audit=False)
        assert exhausted["reason"] == "RETRY_BUDGET_EXHAUSTED"
    finally:
        manager.shutdown()


def test_mutating_retry_requires_fresh_security_confirmation(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path, task_type="computer_use",
                                                error_code="LAUNCH_FAILED")
    try:
        eligibility = manager.get_retry_eligibility(source["run_id"], record_audit=False)
        assert eligibility["classification"] == "REQUIRES_CONFIRMATION"
        pending = manager.retry_background_run(source["run_id"])
        assert pending["confirmation_required"] is True
        assert len(manager.background_runs(task_id)) == 1
        started = manager.retry_background_run(source["run_id"], pending["token"])
        assert started["success"] is True
    finally:
        manager.shutdown()


def test_old_approval_is_not_reused_for_retry(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path, task_type="computer_use")
    try:
        approval_id = manager.database.create_task_approval(
            task_id, source["run_id"], "SAVE", "target.txt", 100, 500)
        pending = manager.retry_background_run(source["run_id"])
        started = manager.retry_background_run(source["run_id"], pending["token"])
        assert started["success"] is True
        approvals = manager.database.list_task_approvals(task_id=task_id)
        assert approvals[0]["approval_id"] == approval_id
        assert approvals[0]["run_id"] == source["run_id"]
        assert all(row["run_id"] != started["run"]["run_id"] for row in approvals)
    finally:
        manager.shutdown()


def test_uncertain_side_effect_blocks_retry_and_recovery(tmp_path):
    manager, _task_id, source = _failed_manager(
        tmp_path, task_type="computer_use", error_code="SIDE_EFFECT_UNCERTAIN")
    try:
        retry = manager.get_retry_eligibility(source["run_id"], record_audit=False)
        recovery = manager.get_recovery_eligibility(source["run_id"], record_audit=False)
        assert retry["classification"] == "UNSAFE_TO_REPLAY"
        assert recovery["classification"] == "UNSAFE_TO_REPLAY"
        assert manager.retry_background_run(source["run_id"])["success"] is False
    finally:
        manager.shutdown()


def test_verified_action_receipt_requires_recovery_and_reuses_same_run(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path, task_type="computer_use")
    try:
        store = MissionCheckpointStore(manager.database)
        checkpoint = store.save_checkpoint(
            mission_id="mission-recovery", mission_version=1, name="safe-boundary",
            current_step=1, next_step=1, context_revision=0,
            snapshot={"context": {"context_version": 0}})
        store.save_receipt(
            mission_id="mission-recovery", step_id="write", action_type="ui_type_editor",
            target="editor", result_state=ActionState.VERIFIED,
            result={"verified": True})
        manager.database.update_task_run(source["run_id"], mission_id="mission-recovery")
        retry = manager.get_retry_eligibility(source["run_id"], record_audit=False)
        assert retry["classification"] == "RECOVERY_ONLY"
        assert retry["reason"] == "CHECKPOINT_AVAILABLE"
        recovery = manager.get_recovery_eligibility(source["run_id"], record_audit=False)
        assert recovery["eligible"] is True
        pending = manager.recover_background_run(source["run_id"])
        assert pending["confirmation_required"] is True
        result = manager.recover_background_run(source["run_id"], pending["token"])
        assert result["success"] is True
        recovered = manager.database.get_task_run(source["run_id"])
        assert recovered["run_id"] == source["run_id"]
        assert recovered["attempt_kind"] == "RECOVERY"
        assert recovered["recovery_count"] == 1
        assert recovered["mission_id"] == "mission-recovery"
        assert recovered["status"] == RunStatus.PENDING.value
        assert checkpoint["checkpoint_id"]
        assert len(store.receipts_for_mission("mission-recovery")) == 1
    finally:
        manager.shutdown()


def test_stale_lease_recovery_is_single_and_restart_idempotent(tmp_path):
    path = tmp_path / "tasks.db"
    store = TaskDatabase(path)
    clock = FakeClock(100)
    task = BackgroundTask.new("stale task", "condition_audit", TriggerType.IMMEDIATE,
                              created_at=100, updated_at=100, next_run_at=100)
    store.create_background_task(task)
    run = store.ensure_task_run(task.task_id, 100, 100)
    store.claim_task_run(run["run_id"], "worker-a", 100, lease_seconds=1)
    assert store.recover_background_runs(200) == 1
    assert store.recover_background_runs(201) == 0
    recovered = store.get_task_run(run["run_id"])
    assert recovered["attempt_kind"] == "RECOVERY"
    assert recovered["recovery_count"] == 1
    assert store.claim_task_run(run["run_id"], "worker-b", 200) is not None


def test_recurring_retry_does_not_consume_next_occurrence(tmp_path):
    path = tmp_path / "tasks.db"
    store = TaskDatabase(path)
    clock = FakeClock(150)
    task = BackgroundTask.new(
        "recurring task", "condition_audit", TriggerType.RECURRING,
        {"mode": "INTERVAL", "seconds": 100, "retry_budget": 1},
        created_at=0, updated_at=0, next_run_at=200)
    store.create_background_task(task)
    source = store.ensure_task_run(task.task_id, 100, 100)
    store.update_task_run(source["run_id"], status=RunStatus.FAILED,
                          error_code="TRANSIENT")
    child = store.create_retry_run(source["run_id"], 150, 150)
    calls = []
    scheduler = BackgroundTaskScheduler(
        store, clock=clock,
        launcher=lambda _task, run: calls.append(run["run_id"]) or {"ok": True})
    scheduler.tick()
    assert calls == [child["run"]["run_id"]]
    assert store.get_background_task(task.task_id).next_run_at == 200
    clock.advance(50)
    scheduler.tick()
    assert len(calls) == 2
    assert len(store.list_task_runs(task.task_id)) == 3


def test_condition_retry_has_one_dispatch_and_no_second_satisfaction(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path)
    marker = tmp_path / "condition.txt"
    marker.write_text("ready", encoding="utf-8")
    try:
        retry = manager.retry_background_run(source["run_id"])
        assert retry["success"] is True
        calls = []
        manager.scheduler.launcher = lambda _task, run: calls.append(run["run_id"]) or {"ok": True}
        manager.scheduler.clock = FakeClock(time.time() + 2)
        manager.database.update_background_task(
            task_id, trigger_config={"condition_type": "FILE_EXISTS",
                                     "path": str(marker), "retry_budget": 1})
        manager.database.update_background_task(task_id, status=BackgroundTaskStatus.SCHEDULED,
                                                enabled=True)
        manager.scheduler.conditions = manager.scheduler.conditions.__class__()
        manager.scheduler.tick()
        assert len(calls) == 1
        assert manager.background(task_id).status == BackgroundTaskStatus.COMPLETED
    finally:
        manager.shutdown()


def test_pause_and_cancel_block_pending_retry_dispatch(tmp_path):
    paused, paused_id, paused_source = _failed_manager(tmp_path / "paused")
    cancelled, cancelled_id, cancelled_source = _failed_manager(tmp_path / "cancelled")
    try:
        paused_retry = paused.retry_background_run(paused_source["run_id"])
        cancelled_retry = cancelled.retry_background_run(cancelled_source["run_id"])
        paused.database.control_background_task(paused_id, "pause")
        cancelled.database.control_background_task(cancelled_id, "cancel")
        paused_calls, cancelled_calls = [], []
        paused.scheduler.launcher = lambda *_: paused_calls.append(True) or {"ok": True}
        cancelled.scheduler.launcher = lambda *_: cancelled_calls.append(True) or {"ok": True}
        paused.scheduler.clock = FakeClock(time.time() + 2)
        cancelled.scheduler.clock = FakeClock(time.time() + 2)
        assert paused.tick_scheduler() == []
        assert cancelled.tick_scheduler() == []
        assert paused_calls == [] and cancelled_calls == []
        assert paused.database.get_task_run(paused_retry["run"]["run_id"])["status"] == RunStatus.PENDING.value
        assert cancelled.database.get_task_run(cancelled_retry["run"]["run_id"])["status"] == RunStatus.CANCELLED.value
    finally:
        paused.shutdown()
        cancelled.shutdown()


def test_control_center_exposes_retry_and_recovery_without_claiming(tmp_path):
    manager, _task_id, source = _failed_manager(tmp_path)
    try:
        view = manager.control_center.get_run(source["run_id"])
        assert view["retry_eligibility"]["classification"] == "SAFE_TO_RETRY"
        assert view["recovery_eligibility"]["eligible"] is False
        assert view["claim_state"]["claimed"] is False
    finally:
        manager.shutdown()


def test_recovery_keeps_verified_receipt_and_does_not_replay_action(tmp_path):
    manager, task_id, source = _failed_manager(tmp_path, task_type="computer_use")
    try:
        store = MissionCheckpointStore(manager.database)
        store.save_checkpoint(mission_id="m", mission_version=1, name="boundary",
                              current_step=1, next_step=1, context_revision=0,
                              snapshot={"context": {"context_version": 0}})
        store.save_receipt(mission_id="m", step_id="write", action_type="ui_type_editor",
                           target="editor", result_state=ActionState.VERIFIED,
                           result={"verified": True})
        manager.database.update_task_run(source["run_id"], mission_id="m")
        pending = manager.recover_background_run(source["run_id"])
        result = manager.recover_background_run(source["run_id"], pending["token"])
        assert result["success"] is True
        calls = []
        manager.scheduler.launcher = lambda _task, run: calls.append(run["run_id"]) or {
            "ok": True, "mission_id": "m"}
        manager.scheduler.clock = FakeClock(time.time() + 2)
        assert manager.tick_scheduler()
        assert calls == [source["run_id"]]
        assert len(store.receipts_for_mission("m")) == 1
    finally:
        manager.shutdown()


def test_audit_records_retry_recovery_and_unsafe_replay_decisions(tmp_path):
    manager, task_id, source = _failed_manager(
        tmp_path, task_type="computer_use", error_code="SIDE_EFFECT_UNCERTAIN")
    try:
        manager.get_retry_eligibility(source["run_id"])
        manager.get_recovery_eligibility(source["run_id"])
        manager.retry_background_run(source["run_id"])
        commands = [row["command"] for row in manager.audit.recent(100)
                    if row["task_id"] == task_id]
        assert "TASK_RUN_RETRY_EVALUATED" in commands
        assert "TASK_RUN_RECOVERY_EVALUATED" in commands
        assert "UNSAFE_REPLAY_BLOCKED" in commands
    finally:
        manager.shutdown()
