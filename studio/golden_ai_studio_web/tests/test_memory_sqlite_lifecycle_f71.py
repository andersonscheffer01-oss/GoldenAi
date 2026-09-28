import threading
import tempfile

from unittest.mock import patch

from jarvis_core.brain import JarvisBrain
from jarvis_core.service import JarvisService
from jarvis_core.task_manager import TaskManager


def test_service_close_waits_for_shadow_worker_and_releases_workspace():
    with tempfile.TemporaryDirectory() as root:
        service = JarvisService(root)
        brain = JarvisBrain(
            service.registry,
            service.legacy_memory,
            service.orchestrator,
            service.memory_v2,
            service.project_memory,
        )
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def shadow_work():
            started.set()
            assert release.wait(2)

        future = brain._shadow_executor.submit(shadow_work)
        assert started.wait(2)

        def close_service():
            with patch("jarvis_core.brain._brain", brain):
                service.close()
            finished.set()

        closer = threading.Thread(target=close_service)
        closer.start()
        assert not finished.wait(0.05)

        release.set()
        assert finished.wait(2)
        closer.join(2)

        assert future.done()
        assert service.task_manager._shutdown_complete is True
        assert service.task_manager.scheduler.status()["running"] is False
        assert all(not thread.is_alive() for thread in brain._shadow_executor._threads)

        # close() is intentionally safe to call again during layered shutdown.
        service.close()


def test_task_manager_shutdown_is_idempotent_and_allows_temp_cleanup():
    with tempfile.TemporaryDirectory() as root:
        manager = TaskManager(root)
        manager.request_shutdown()
        manager.finalize_shutdown()
        manager.finalize_shutdown()
        manager.shutdown(wait=False)

        assert manager._shutdown_complete is True
        assert manager.scheduler.status()["running"] is False
