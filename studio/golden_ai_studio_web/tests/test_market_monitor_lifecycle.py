from jarvis_core.task_manager import TaskManager


def test_monitor_lifecycle_is_idempotent_and_persisted(tmp_path):
    actor = "device:actor-a"
    manager = TaskManager(tmp_path)
    try:
        started = manager.start_market_monitor(actor)
        again = manager.start_market_monitor(actor)
        assert started["monitor_state"] == "RUNNING"
        assert again["task_id"] == started["task_id"]
        assert len([task for task in manager.database.list_background_tasks(limit=1000)
                    if task.task_type == manager.MONITOR_TASK_TYPE]) == 1
        assert manager.pause_market_monitor(actor)["monitor_state"] == "PAUSED"
        assert manager.resume_market_monitor(actor)["monitor_state"] == "RUNNING"
        recovered = TaskManager(tmp_path)
        status = recovered.monitor_status(actor)
        assert status["monitor_state"] == "RUNNING"
        assert status["scan_state"] == "UNKNOWN"
        assert status["mt5_availability"] == "UNKNOWN"
        assert status["candle_freshness"] == "UNKNOWN"
    finally:
        manager.shutdown()
        recovered.shutdown()


def test_monitor_actor_isolation_and_clean_shutdown(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        manager.start_market_monitor("device:actor-a")
        manager.start_market_monitor("device:actor-b")
        assert manager.monitor_status("device:actor-a")["task_id"] != \
            manager.monitor_status("device:actor-b")["task_id"]
        manager.request_shutdown()
        assert manager.monitor_status("device:actor-a")["monitor_state"] == "STOPPED"
        assert manager.monitor_status("device:actor-b")["monitor_state"] == "STOPPED"
    finally:
        manager.finalize_shutdown()


def test_monitor_start_does_not_dispatch_or_read_market_data(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        status = manager.start_market_monitor("device:actor-a")
        task = manager.background(status["task_id"])
        assert task.enabled is False
        assert task.security_scope["read_only"] is True
        assert task.security_scope["execution_authority"] == "NONE"
        assert status["last_confirmed_batch"] is None
    finally:
        manager.shutdown()


def test_monitor_persists_before_advancing_cursor_and_handles_backoff(tmp_path):
    manager = TaskManager(tmp_path)
    calls = []
    try:
        manager.start_market_monitor("device:actor-a")

        def rank(batch, batch_index):
            calls.append(("rank", batch_index, batch))
            return {"ok": True, "ranked_assets": batch}

        def persist(ranking, batch_index):
            calls.append(("persist", batch_index))
            return {"persisted": True}

        result = manager.process_market_monitor_batch(
            "device:actor-a", ["A", "B"], rank, persist, next_cycle_at=20)
        assert result["status"] == "BATCH_PERSISTED"
        assert calls == [("rank", 0, ["A", "B"]), ("persist", 0)]
        assert manager.monitor_status("device:actor-a")["last_confirmed_batch"] == 0

        failure = manager.process_market_monitor_batch(
            "device:actor-a", ["C"], lambda *_args, **_kwargs: {"ok": False, "status": "NO_TICKS"}, persist)
        assert failure["status"] == "BACKOFF"
        assert manager.monitor_status("device:actor-a")["monitor_state"] == "BACKOFF"
    finally:
        manager.shutdown()


def test_monitor_does_not_advance_on_no_new_candles(tmp_path):
    manager = TaskManager(tmp_path)
    try:
        manager.start_market_monitor("device:actor-a")
        result = manager.process_market_monitor_batch(
            "device:actor-a", ["A"],
            lambda *_args, **_kwargs: {"ok": True, "status": "NO_NEW_CANDLES"},
            lambda *_args, **_kwargs: {"persisted": True})
        assert result["status"] == "NO_NEW_CANDLES"
        status = manager.monitor_status("device:actor-a")
        assert status["last_confirmed_batch"] is None
        assert status["scan_state"] == "WAITING_FOR_NEW_CANDLES"
    finally:
        manager.shutdown()
