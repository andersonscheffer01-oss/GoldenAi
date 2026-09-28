import threading
import time

from jarvis_core.task_manager import BackgroundTaskScheduler, TaskDatabase, TaskManager


def _wait_for_scheduler(scheduler):
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if scheduler.status()["running"]:
            return
        time.sleep(0.01)
    raise AssertionError("scheduler thread did not start")


def test_final_shutdown_joins_scheduler_and_releases_temp_database(tmp_path):
    manager = TaskManager(tmp_path)
    manager.start_scheduler(lambda _task, _run: {"ok": True})
    _wait_for_scheduler(manager.scheduler)

    manager.request_shutdown()
    assert manager._shutdown_requested is True
    assert manager._shutdown_complete is False

    manager.finalize_shutdown()
    manager.finalize_shutdown()

    assert manager._shutdown_complete is True
    assert manager.scheduler.status()["running"] is False
    assert not any(thread.name == "jarvis-background-scheduler" and thread.is_alive()
                   for thread in threading.enumerate())


def test_wait_false_is_nonblocking_request_then_final_join(tmp_path):
    manager = TaskManager(tmp_path)
    manager.start_scheduler(lambda _task, _run: {"ok": True})
    _wait_for_scheduler(manager.scheduler)

    started = time.monotonic()
    manager.shutdown(wait=False)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert manager._shutdown_requested is True
    manager.shutdown(wait=True)
    assert manager.scheduler.status()["running"] is False


def test_scheduler_can_restart_after_explicit_stop(tmp_path):
    scheduler = BackgroundTaskScheduler(TaskDatabase(tmp_path / "tasks.db"), tick_interval=0.05)
    scheduler.start()
    _wait_for_scheduler(scheduler)
    assert scheduler.stop(wait=True) is True
    scheduler.start()
    _wait_for_scheduler(scheduler)
    assert scheduler.stop(wait=True) is True
    assert scheduler.status()["running"] is False
