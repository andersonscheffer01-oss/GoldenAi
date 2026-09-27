from jarvis_core.task_manager import (
    BackgroundControlCenter, BackgroundTask, BackgroundTaskStatus,
    FakeClock, RunStatus, TaskDatabase, TriggerType,
)


class RunningScheduler:
    def __init__(self, worker_id="health-test-worker"):
        self.worker_id = worker_id

    def status(self):
        return {
            "running": True,
            "worker_id": self.worker_id,
            "tick_interval": 1.0,
            "database_path": "temporary",
        }


def _task(database, clock, task_id, status=BackgroundTaskStatus.SCHEDULED,
          trigger=TriggerType.IMMEDIATE, enabled=True, next_run_at=None):
    task = BackgroundTask(
        task_id=task_id, user_request=f"request {task_id}",
        task_type="condition_audit", trigger_type=trigger,
        trigger_config={}, status=status, created_at=clock.now(),
        updated_at=clock.now(), next_run_at=clock.now() if next_run_at is None else next_run_at,
        enabled=enabled)
    database.create_background_task(task)
    return task


def _center(tmp_path, now=100, **kwargs):
    clock = FakeClock(now)
    database = TaskDatabase(tmp_path / "tasks.db")
    center = BackgroundControlCenter(
        database, RunningScheduler(), now_provider=clock.now, **kwargs)
    return database, center, clock


def test_healthy_idle_scheduler_is_not_a_false_failure(tmp_path):
    database, center, _ = _center(tmp_path)
    health = center.get_scheduler_health()
    assert health["status"] == "HEALTHY"
    assert health["scheduler_alive"] is True
    assert health["scheduler_progressing"] is True
    assert health["due_tasks"] == 0
    assert health["reasons"] == []


def test_health_reads_are_zero_side_effect_and_deterministic(tmp_path):
    database, center, _ = _center(tmp_path)
    with database.connect() as db:
        counts_before = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("background_tasks", "task_runs", "task_approvals")}
    first = center.get_scheduler_health()
    center.get_scheduler_health()
    diagnostics = center.get_scheduler_diagnostics()
    second = center.get_scheduler_health()
    with database.connect() as db:
        counts_after = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in ("background_tasks", "task_runs", "task_approvals")}
    assert first == second
    assert diagnostics["read_only"] is True
    assert counts_before == counts_after


def test_overdue_task_is_detected_from_existing_due_state(tmp_path):
    database, center, _ = _center(tmp_path)
    _task(database, FakeClock(100), "overdue", next_run_at=90)
    health = center.get_scheduler_health()
    assert health["overdue_tasks"] == 1
    assert "OVERDUE_TASK" in health["reasons"]
    assert center.get_scheduler_diagnostics()["overdue_tasks"][0]["task_id"] == "overdue"


def test_paused_and_cancelled_tasks_are_not_false_overdue(tmp_path):
    database, center, clock = _center(tmp_path)
    _task(database, clock, "paused", BackgroundTaskStatus.PAUSED,
          enabled=False, next_run_at=1)
    _task(database, clock, "cancelled", BackgroundTaskStatus.CANCELLED,
          enabled=False, next_run_at=1)
    health = center.get_scheduler_health()
    assert health["overdue_tasks"] == 0


def test_human_waits_are_action_required_not_scheduler_failure(tmp_path):
    database, center, clock = _center(tmp_path)
    task = _task(database, clock, "approval", BackgroundTaskStatus.WAITING_CONFIRMATION,
                 next_run_at=1)
    run = database.ensure_task_run(task.task_id, 100, 100)
    database.create_task_approval(task.task_id, run["run_id"], "write_file", "x.txt",
                                   100, 200)
    health = center.get_scheduler_health()
    assert health["status"] == "ACTION_REQUIRED"
    assert health["pending_approvals"] == 1
    assert health["overdue_tasks"] == 0
    assert "APPROVAL_WAITING" in health["reasons"]


def test_user_idle_and_condition_waits_are_legitimate(tmp_path):
    database, center, clock = _center(tmp_path)
    _task(database, clock, "idle", BackgroundTaskStatus.WAITING_USER_IDLE,
          TriggerType.USER_IDLE, next_run_at=1)
    _task(database, clock, "condition", BackgroundTaskStatus.WAITING_TRIGGER,
          TriggerType.CONDITION, next_run_at=1)
    health = center.get_scheduler_health()
    assert health["overdue_tasks"] == 0
    assert health["status"] == "HEALTHY"


def test_stale_and_active_claims_reuse_lease_semantics_without_mutation(tmp_path):
    database, center, clock = _center(tmp_path)
    stale_task = _task(database, clock, "stale", BackgroundTaskStatus.SCHEDULED)
    stale_run = database.ensure_task_run(stale_task.task_id, 100, 100)
    database.claim_task_run(stale_run["run_id"], "worker", 100, lease_seconds=1)
    valid_task = _task(database, clock, "valid", BackgroundTaskStatus.SCHEDULED)
    valid_run = database.ensure_task_run(valid_task.task_id, 100, 100)
    database.claim_task_run(valid_run["run_id"], "worker", 100, lease_seconds=30)
    clock.advance(2)
    before = database.get_task_run(stale_run["run_id"])
    health = center.get_scheduler_health()
    after = database.get_task_run(stale_run["run_id"])
    assert health["stale_claims"] == 1
    assert health["active_claims"] == 2
    assert before == after
    assert health["status"] == "DEGRADED"


def test_recovery_eligibility_is_observed_but_not_started(tmp_path):
    database, center, clock = _center(
        tmp_path, recovery_eligibility=lambda run_id: {
            "run_id": run_id, "eligible": True, "classification": "RECOVERY_ONLY",
            "reason": "STALE_LEASE"})
    task = _task(database, clock, "recover", BackgroundTaskStatus.SCHEDULED)
    run = database.ensure_task_run(task.task_id, 100, 100)
    database.claim_task_run(run["run_id"], "worker", 100, lease_seconds=1)
    clock.advance(2)
    before = database.get_task_run(run["run_id"])
    health = center.get_scheduler_health()
    diagnostics = center.get_scheduler_diagnostics()
    after = database.get_task_run(run["run_id"])
    assert health["recovery_required"] == 1
    assert diagnostics["recovery_required"][0]["classification"] == "RECOVERY_ONLY"
    assert before == after
    assert len(database.list_task_runs(task.task_id)) == 1


def test_failed_non_retryable_run_is_classified_without_auto_retry(tmp_path):
    database, center, clock = _center(
        tmp_path, retry_eligibility=lambda run_id: {
            "run_id": run_id, "eligible": False, "classification": "UNSAFE_TO_REPLAY",
            "reason": "SIDE_EFFECT_UNCERTAIN"})
    task = _task(database, clock, "failed")
    run = database.ensure_task_run(task.task_id, 100, 100)
    database.update_task_run(run["run_id"], status=RunStatus.FAILED,
                             finished_at=101, error_code="SIDE_EFFECT_UNCERTAIN")
    health = center.get_scheduler_health()
    assert health["recent_failures"] == 1
    assert health["retry_eligible"] == 0
    assert health["retry_blocked"] == 1
    assert center.get_scheduler_diagnostics()["retry_blocked"][0]["classification"] == "UNSAFE_TO_REPLAY"
    assert len(database.list_task_runs(task.task_id)) == 1


def test_pending_approval_count_and_health_reads_do_not_consume(tmp_path):
    database, center, clock = _center(tmp_path)
    task = _task(database, clock, "pending")
    run = database.ensure_task_run(task.task_id, 100, 100)
    approval_id = database.create_task_approval(task.task_id, run["run_id"],
                                                "write_file", "x.txt", 100, 200)
    assert center.get_scheduler_health()["pending_approvals"] == 1
    assert center.get_scheduler_diagnostics()["pending_approvals"][0]["approval_id"] == approval_id
    assert database.get_task_approval(approval_id)["decision"] == "PENDING"


def test_scheduler_health_unknown_without_scheduler_proof(tmp_path):
    clock = FakeClock(100)
    database = TaskDatabase(tmp_path / "tasks.db")
    center = BackgroundControlCenter(database, now_provider=clock.now)
    health = center.get_scheduler_health()
    assert health["status"] == "UNKNOWN"
    assert health["scheduler_alive"] is None
