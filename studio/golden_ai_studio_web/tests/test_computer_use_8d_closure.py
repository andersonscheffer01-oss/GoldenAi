import sqlite3
import time

from jarvis_core.task_manager import (
    BackgroundTaskStatus, TaskDatabase, TaskManager,
)


def _create_v2_database(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE task_schema_version(version INTEGER NOT NULL);
            INSERT INTO task_schema_version VALUES(2);
            CREATE TABLE tasks(
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                status TEXT NOT NULL, data_classification TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, started_at REAL,
                finished_at REAL, cancel_requested_at REAL, error TEXT NOT NULL,
                result TEXT, metadata TEXT NOT NULL, timeout_seconds REAL NOT NULL);
            CREATE TABLE task_steps(
                task_id TEXT NOT NULL, step_id TEXT NOT NULL, position INTEGER NOT NULL,
                intent TEXT NOT NULL, route TEXT NOT NULL, tool TEXT, args TEXT NOT NULL,
                dependencies TEXT NOT NULL, cancellable INTEGER NOT NULL,
                background INTEGER NOT NULL, status TEXT NOT NULL, started_at REAL,
                finished_at REAL, error TEXT NOT NULL, result TEXT,
                PRIMARY KEY(task_id, step_id));
            CREATE TABLE task_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                timestamp REAL NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL);
            CREATE TABLE background_tasks(
                task_id TEXT PRIMARY KEY, user_request TEXT NOT NULL,
                task_type TEXT NOT NULL, trigger_type TEXT NOT NULL,
                trigger_config TEXT NOT NULL, status TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                next_run_at REAL, last_run_at REAL, timezone TEXT NOT NULL,
                enabled INTEGER NOT NULL, run_count INTEGER NOT NULL,
                max_runs INTEGER, misfire_policy TEXT NOT NULL,
                security_scope TEXT NOT NULL, schema_version INTEGER NOT NULL);
            CREATE TABLE task_runs(
                run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                scheduled_for REAL NOT NULL, status TEXT NOT NULL,
                created_at REAL NOT NULL, started_at REAL, finished_at REAL,
                mission_id TEXT, claim_token TEXT, claimed_by TEXT,
                claim_expires_at REAL, error_code TEXT, error_message TEXT,
                UNIQUE(task_id, scheduled_for));
            CREATE TABLE task_approvals(
                approval_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                run_id TEXT NOT NULL, mission_id TEXT, scope TEXT NOT NULL,
                target TEXT NOT NULL, granted_at REAL NOT NULL,
                expires_at REAL NOT NULL, single_use INTEGER NOT NULL,
                consumed_at REAL, status TEXT NOT NULL);
            INSERT INTO background_tasks VALUES(
                'legacy-task','legacy request','condition_audit','IMMEDIATE','{}',
                'SCHEDULED',100,100,100,NULL,'UTC',1,0,NULL,
                'RUN_ONCE_WHEN_AVAILABLE','{}',2);
            INSERT INTO task_runs VALUES(
                'legacy-run','legacy-task',100,'PENDING',100,NULL,NULL,NULL,
                NULL,NULL,NULL,NULL,NULL);
            INSERT INTO task_approvals VALUES(
                'legacy-approval','legacy-task','legacy-run',NULL,
                'write_file','legacy.txt',100,200,1,NULL,'ACTIVE');
        """)


def test_v2_to_v5_migration_preserves_data_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy-v2.db"
    _create_v2_database(path)
    first = TaskDatabase(path)
    assert first.get_background_task("legacy-task").user_request == "legacy request"
    assert first.get_task_run("legacy-run")["run_id"] == "legacy-run"
    assert first.get_task_approval("legacy-approval")["decision"] == "PENDING"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version FROM task_schema_version").fetchone()[0] == 6
        assert db.execute("SELECT COUNT(*) FROM background_tasks").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM task_approvals").fetchone()[0] == 1
        approval_columns = [row[1] for row in db.execute("PRAGMA table_info(task_approvals)")]
        assert approval_columns.count("decision") == 1
    second = TaskDatabase(path)
    assert second.get_background_task("legacy-task").task_id == "legacy-task"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version FROM task_schema_version").fetchone()[0] == 6


def test_e2e_master_flow_and_restart_durability(tmp_path):
    manager = TaskManager(tmp_path)
    manager.scheduler.stop()
    counter = {"mutating_side_effects": 0, "calls": []}
    manager.scheduler.clock = type("Clock", (), {"now": staticmethod(time.time)})()

    def launcher(task, run):
        counter["calls"].append(run["run_id"])
        if run.get("attempt_kind") == "ORIGINAL":
            counter["mutating_side_effects"] += 1
            return {"ok": False, "error_code": "POST_EFFECT_FAILURE",
                    "error": "controlled failure after receipt"}
        return {"ok": True, "result": "existing receipt prevents duplicate side effect"}

    manager.scheduler.launcher = launcher
    task_id = manager.schedule_background(
        "closure master", task_type="condition_audit",
        trigger_config={"retry_budget": 1})
    assert manager.control_center.get_task(task_id)["task_id"] == task_id
    assert manager.pause_background(task_id)["success"] is True
    assert manager.tick_scheduler() == []
    assert manager.resume_background(task_id)["success"] is True
    assert manager.tick_scheduler() == [(task_id, "FAILED")]
    source = manager.background_runs(task_id)[0]
    assert manager.get_retry_eligibility(source["run_id"], record_audit=False)["eligible"] is True
    retry = manager.retry_background_run(source["run_id"])
    assert retry["success"] is True
    child = retry["run"]
    approval_id = manager.create_background_approval(
        task_id, child["run_id"], "controlled_action", "closure-target",
        time.time() + 60, mission_id="closure-mission")
    assert manager.list_pending_background_approvals()[0]["approval_id"] == approval_id
    assert any(item["type"] == "APPROVAL_REQUIRED"
               for item in manager.list_background_notifications())
    for _ in range(3):
        manager.get_pending_background_approval(approval_id)
    assert manager.database.get_task_approval(approval_id)["decision"] == "PENDING"
    assert manager.approve_pending_action(approval_id)["success"] is True
    assert manager.consume_background_approval(
        approval_id, task_id, child["run_id"], "controlled_action", "closure-target") is True
    assert manager.consume_background_approval(
        approval_id, task_id, child["run_id"], "controlled_action", "closure-target") is False
    assert manager.tick_scheduler() == [(task_id, "COMPLETED")]
    assert counter["mutating_side_effects"] == 1
    assert len(manager.background_runs(task_id)) == 2
    assert manager.background(task_id).status == BackgroundTaskStatus.COMPLETED
    assert all(run.get("claim_token") is None
               for run in manager.database.list_task_runs(task_id))
    post_health = manager.scheduler_health()
    assert post_health["overdue_tasks"] == 0
    assert post_health["stale_claims"] == 0
    audit_commands = [item["command"] for item in manager.audit.recent(100)]
    assert {
        "background_task_scheduled", "BACKGROUND_TASK_PAUSED",
        "BACKGROUND_TASK_RESUMED", "background_task_dispatched",
        "background_task_failed", "TASK_RUN_RETRY_REQUESTED",
        "TASK_RUN_RETRY_STARTED", "APPROVAL_GRANTED",
        "TASK_RUN_COMPLETED", "CLAIM_FINALIZED",
    } <= set(audit_commands)
    manager.shutdown()

    restored = TaskManager(tmp_path)
    try:
        assert len(restored.background_runs(task_id)) == 2
        assert restored.background(task_id).status == BackgroundTaskStatus.COMPLETED
        assert restored.database.get_task_approval(approval_id)["decision"] == "APPROVED"
        assert restored.database.get_task_approval(approval_id)["status"] == "CONSUMED"
        assert restored.scheduler_health()["overdue_tasks"] == 0
    finally:
        restored.shutdown()


def test_e2e_cancel_blocks_old_approval_and_retry_without_new_run(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        task_id = manager.schedule_background("closure cancel", task_type="condition_audit")
        run = manager.database.ensure_task_run(task_id, time.time(), time.time())
        manager.database.update_task_run(
            run["run_id"], status="FAILED", finished_at=time.time(),
            error_code="POST_EFFECT_FAILURE")
        approval_id = manager.create_background_approval(
            task_id, run["run_id"], "controlled_action", "cancel-target",
            time.time() + 60)
        pending_cancel = manager.cancel_background(task_id)
        assert pending_cancel["confirmation_required"] is True
        assert manager.cancel_background(task_id, pending_cancel["token"])["success"] is True
        assert manager.approve_pending_action(approval_id)["code"] == "STALE_APPROVAL"
        assert manager.get_retry_eligibility(run["run_id"], record_audit=False)["reason"] == "TASK_CANCELLED"
        assert len(manager.background_runs(task_id)) == 1
        assert manager.background(task_id).status == BackgroundTaskStatus.CANCELLED
    finally:
        manager.shutdown()
