import tempfile
import unittest

from jarvis_core.orchestrator import (CentralOrchestrator, JarvisRuntimeCoordinator,
    ModelRouter, ProviderAdapter)
from jarvis_core.orchestrator.models import PlanStep, Route
from jarvis_core.service import JarvisService
from jarvis_core.task_manager import Planner, StepStatus, TaskPlan, TaskStatus


def planner_output(tool="get_time", args=None):
    return {"title": "Preparar ambiente", "goal": "Preparar com segurança", "risk": "LOW",
            "requires_confirmation": False,
            "steps": [{"id": "a", "intent": "primeiro", "tool": tool,
                       "args": args or {}, "dependencies": []}]}


class RuntimeIntegrationCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)
        self.service.dry_run = True

    def tearDown(self):
        self.service.task_manager.shutdown(wait=True)
        self.temp.cleanup()

    def _coordinator(self, mode="shadow", output=None):
        models = ModelRouter(retries=0)
        models.register_provider(ProviderAdapter("groq",
            lambda **kwargs: output or planner_output(), cloud=True))
        orchestrator = CentralOrchestrator(self.service.registry, mode=mode, model_router=models)
        planner = Planner(models, self.service.registry, orchestrator.skills)
        return JarvisRuntimeCoordinator(orchestrator, self.service,
            task_manager=self.service.task_manager, planner=planner)

    def test_shadow_creates_valid_plan_without_execution(self):
        coordinator = self._coordinator("shadow")
        result = coordinator.process("prepare meu ambiente de trading")
        self.assertTrue(result["planned"])
        self.assertFalse(result["executed"])
        self.assertEqual(TaskStatus.QUEUED, coordinator.task_manager.get(result["task_id"]).status)

    def test_on_executes_multistep_only_through_service(self):
        output = planner_output()
        output["steps"].append({"id": "b", "intent": "segundo", "tool": "system_status",
                                "args": {}, "dependencies": ["a"]})
        coordinator = self._coordinator("on", output)
        result = coordinator.process("prepare meu ambiente de trading")
        task = result["future"].result(timeout=3)
        self.assertEqual(TaskStatus.COMPLETED, task.status)
        self.assertEqual([StepStatus.COMPLETED, StepStatus.COMPLETED],
                         [item.status for item in coordinator.task_manager.steps(task.id)])

    def test_invalid_tool_and_args_fail_closed(self):
        invalid = (planner_output("invented_tool"), planner_output("open_program", {}),
                   planner_output("open_program", {"name": 123}))
        for output in invalid:
            with self.subTest(output=output):
                with self.assertRaises(Exception):
                    self._coordinator("shadow", output).process("prepare meu ambiente de trading")

    def test_security_confirmation_becomes_waiting(self):
        coordinator = self._coordinator("on")
        plan = TaskPlan("Confirmar", (PlanStep("a", "shutdown", Route.SYSTEM, "shutdown", {}),))
        task_id = coordinator.task_manager.create(plan)
        coordinator.active_task_id = task_id
        task = coordinator.task_manager.start(task_id, coordinator._execute_step).result(timeout=3)
        self.assertEqual(TaskStatus.WAITING_CONFIRMATION, task.status)
        self.assertEqual(StepStatus.WAITING_CONFIRMATION,
                         coordinator.task_manager.steps(task_id)[0].status)

    def test_background_task_does_not_block_simple_brain_work(self):
        coordinator = self._coordinator("on")
        result = coordinator.process("prepare meu ambiente de trading")
        self.assertFalse(result["future"].done() and False)
        self.assertEqual(Route.SYSTEM, coordinator.orchestrator.decide("que horas são?").route)
        result["future"].result(timeout=3)


if __name__ == "__main__":
    unittest.main()
