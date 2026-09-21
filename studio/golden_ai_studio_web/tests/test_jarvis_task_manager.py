import sqlite3
import tempfile
import time
import unittest

from jarvis_core.orchestrator.models import DataClassification, PlanStep, Route
from jarvis_core.task_manager import (
    PlanValidationError, PlannerContracts, StepStatus, TaskDatabase,
    TaskManager, TaskPlan, TaskStatus,
)


def step(step_id, dependencies=(), cancellable=True):
    return PlanStep(step_id, "test", Route.SYSTEM, "get_time", {},
                    tuple(dependencies), "PENDING", cancellable, True)


class PlannerContractsCase(unittest.TestCase):
    def test_valid_plan(self):
        plan = TaskPlan(" Plano ", (step("a"), step("b", ("a",))))
        validated = PlannerContracts.validate(plan)
        self.assertEqual("Plano", validated.title)

    def test_rejects_empty_duplicate_missing_and_cycle(self):
        invalid = (
            TaskPlan("x", ()),
            TaskPlan("x", (step("a"), step("a"))),
            TaskPlan("x", (step("a", ("missing",)),)),
            TaskPlan("x", (step("a", ("b",)), step("b", ("a",)))),
        )
        for plan in invalid:
            with self.subTest(plan=plan):
                with self.assertRaises(PlanValidationError):
                    PlannerContracts.validate(plan)


class TaskManagerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = TaskManager(self.temp.name, max_workers=2)

    def tearDown(self):
        self.manager.shutdown(wait=True)
        self.temp.cleanup()

    def test_persistence_schema_and_events(self):
        task_id = self.manager.create(TaskPlan("Persistir", (step("a"),)))
        restored = TaskDatabase(self.manager.database.path)
        self.assertEqual(TaskStatus.QUEUED, restored.get_task(task_id).status)
        self.assertEqual("a", restored.get_steps(task_id)[0].step.id)
        self.assertEqual("task_created", restored.events(task_id)[0]["event"])
        db = sqlite3.connect(restored.path)
        try:
            self.assertEqual(1, db.execute("SELECT version FROM task_schema_version").fetchone()[0])
        finally:
            db.close()

    def test_background_execution_respects_dependencies(self):
        task_id = self.manager.create(TaskPlan("Executar", (step("a"), step("b", ("a",)))))
        order = []
        future = self.manager.start(task_id, lambda current, token: order.append(current.id) or {"ok": True})
        result = future.result(timeout=3)
        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(["a", "b"], order)
        self.assertTrue(all(item.status == StepStatus.COMPLETED for item in self.manager.steps(task_id)))

    def test_failure_marks_following_step_blocked(self):
        task_id = self.manager.create(TaskPlan("Falhar", (step("a"), step("b", ("a",)))))
        def fail(current, token):
            raise RuntimeError("falha controlada")
        result = self.manager.start(task_id, fail).result(timeout=3)
        self.assertEqual(TaskStatus.FAILED, result.status)
        statuses = [item.status for item in self.manager.steps(task_id)]
        self.assertEqual([StepStatus.FAILED, StepStatus.BLOCKED], statuses)

    def test_cancel_queued_task(self):
        task_id = self.manager.create(TaskPlan("Cancelar", (step("a"),)))
        self.assertTrue(self.manager.cancel(task_id))
        self.assertEqual(TaskStatus.CANCELLED, self.manager.get(task_id).status)
        self.assertEqual(StepStatus.CANCELLED, self.manager.steps(task_id)[0].status)

    def test_cooperative_cancel_running_task(self):
        task_id = self.manager.create(TaskPlan("Cancelar ativa", (step("a"),)))
        def wait_for_cancel(current, token):
            limit = time.time() + 2
            while not token.is_cancelled() and time.time() < limit:
                time.sleep(.01)
            return {"cancel_seen": token.is_cancelled()}
        future = self.manager.start(task_id, wait_for_cancel)
        limit = time.time() + 1
        while self.manager.get(task_id).status != TaskStatus.RUNNING and time.time() < limit:
            time.sleep(.01)
        self.assertTrue(self.manager.cancel(task_id))
        self.assertEqual(TaskStatus.CANCELLED, future.result(timeout=3).status)

    def test_global_timeout_fails_task(self):
        task_id = self.manager.create(TaskPlan("Timeout", (step("a"),), timeout_seconds=.05))
        result = self.manager.start(task_id, lambda current, token: time.sleep(.2)).result(timeout=2)
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("Timeout", result.error)

    def test_restart_marks_running_as_interrupted(self):
        task_id = self.manager.create(TaskPlan("Recuperar", (step("a"),)))
        self.manager.database.update_task(task_id, TaskStatus.RUNNING, started_at=time.time())
        self.manager.database.update_step(task_id, "a", StepStatus.RUNNING, started_at=time.time())
        restored = TaskDatabase(self.manager.database.path)
        self.assertEqual(TaskStatus.INTERRUPTED, restored.get_task(task_id).status)
        self.assertEqual(StepStatus.INTERRUPTED, restored.get_steps(task_id)[0].status)

    def test_resume_does_not_repeat_completed_steps(self):
        task_id = self.manager.create(TaskPlan("Retomar", (step("a"), step("b", ("a",)))))
        self.manager.database.update_step(task_id, "a", StepStatus.COMPLETED,
                                          result={"old": True}, finished_at=time.time())
        self.manager.database.update_task(task_id, TaskStatus.INTERRUPTED)
        called = []
        result = self.manager.start(task_id, lambda current, token: called.append(current.id) or True).result(timeout=3)
        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(["b"], called)

    def test_rejects_secret_binary_and_large_payload(self):
        plans = (
            TaskPlan("Secret", (step("a"),), data_classification=DataClassification.SECRET),
            TaskPlan("Token", (PlanStep("a", "x", Route.SYSTEM, "x", {"token": "abc"}),)),
            TaskPlan("Binary", (PlanStep("a", "x", Route.SYSTEM, "x", {"data": b"abc"}),)),
            TaskPlan("Large", (PlanStep("a", "x", Route.SYSTEM, "x", {"data": "x" * 9000}),)),
        )
        for plan in plans:
            with self.subTest(title=plan.title):
                with self.assertRaises(ValueError):
                    self.manager.create(plan)

    def test_list_filter_and_terminal_cancel(self):
        task_id = self.manager.create(TaskPlan("Lista", (step("a"),)))
        self.manager.start(task_id, lambda current, token: True).result(timeout=3)
        completed = self.manager.list(status=TaskStatus.COMPLETED)
        self.assertEqual([task_id], [item.id for item in completed])
        self.assertFalse(self.manager.cancel(task_id))


if __name__ == "__main__":
    unittest.main()
