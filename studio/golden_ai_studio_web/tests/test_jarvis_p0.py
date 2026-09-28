import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis_core.brain import JarvisBrain
from jarvis_core.models import ResponsePolicy, Tool
from jarvis_core.orchestrator import CentralOrchestrator
from jarvis_core.orchestrator.models import PlanStep, Route
from jarvis_core.response_policy import ack_for_decision
from jarvis_core.service import JarvisService
from jarvis_core.task_manager import TaskManager
from jarvis_core.task_manager.models import TaskPlan, TaskStatus
from jarvis_core.voice_service import VoiceService


class P0PolicyCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_fast_paths_use_zero_llm_calls(self):
        brain = JarvisBrain(self.service.registry, orchestrator=self.service.orchestrator)
        for command in ("abra calculadora", "qual a cotação do dólar", "que horas são"):
            with self.subTest(command=command):
                result = brain.interpret(command)
                self.assertTrue(result["ok"])
                self.assertEqual(0, brain.request_metrics()["total_llm_calls"])

    def test_static_prompt_is_stable_and_catalog_is_runtime(self):
        brain = JarvisBrain(self.service.registry)
        first = brain._system_prompt()
        time.sleep(0.01)
        second = brain._system_prompt()
        self.assertEqual(first, second)
        self.assertNotIn("Ferramentas disponíveis", first)
        brain._allowed_tools = {"get_time"}
        runtime = brain._runtime_context()
        self.assertIn("get_time", runtime)
        self.assertNotIn("open_program", runtime)

    def test_final_policy_and_verified_query(self):
        result = self.service.execute_tool("get_time", {})
        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual("query_completed", result["verification"])
        self.assertEqual(ResponsePolicy.FINAL.value, result["response_policy"])

    def test_unverified_success_uses_cautious_message(self):
        self.service.registry.register(Tool(
            "unverified_action", "Executa ação de teste", lambda: {"ok": True, "message": "Concluído."},
            response_policy=ResponsePolicy.FINAL))
        result = self.service.execute_tool("unverified_action", {})
        self.assertTrue(result["success"])
        self.assertFalse(result["verified"])
        self.assertNotIn("Concluído", result["message"])
        self.assertIn("não consegui confirmar", result["message"])

    def test_failure_never_claims_success(self):
        self.service.registry.register(Tool(
            "failed_action", "Executa ação com falha", lambda: {"ok": False, "error": "Falhou"},
            response_policy=ResponsePolicy.FINAL))
        result = self.service.execute_tool("failed_action", {})
        self.assertFalse(result["success"])
        self.assertFalse(result["verified"])
        self.assertEqual("Falhou", result["error"])

    def test_market_payload_is_verified(self):
        market = MagicMock()
        market.get_exchange_rate.return_value = {
            "ok": True, "price": 5.13, "provider": "awesomeapi", "timestamp": time.time()}
        with patch("jarvis_core.data.market_data.get_market_data_service", return_value=market):
            result = self.service.execute_tool("get_exchange_rate", {"base": "USD", "quote": "BRL"})
        self.assertTrue(result["verified"])
        self.assertEqual("provider_payload", result["verification"])

    def test_file_copy_checks_postcondition(self):
        source = Path(self.temp.name) / "source.txt"
        target = Path(self.temp.name) / "out" / "target.txt"
        source.write_text("golden", encoding="utf-8")
        result = self.service.execute_tool("copy_file", {"source": str(source), "dest": str(target)})
        self.assertTrue(result["verified"])
        self.assertTrue(target.exists())

    def test_ack_only_for_planner_or_slow_tool(self):
        router = CentralOrchestrator(self.service.registry)
        fast = ack_for_decision(router.decide("que horas são"), self.service.registry)
        slow = ack_for_decision(router.decide("prepare meu ambiente"), self.service.registry)
        self.assertFalse(fast["emitted"])
        self.assertTrue(slow["emitted"])
        self.assertNotIn("concluído", slow["message"].lower())

    def test_voice_speaks_ack_before_slow_final_result(self):
        voice = VoiceService()
        voice.service = self.service
        voice._voice = MagicMock()
        spoken = []
        voice._speak = lambda text: spoken.append(text) or True
        brain = MagicMock()
        brain.interpret.return_value = {"ok": True, "plan": {"response": "Análise pronta."}}
        brain.orchestrator.last_decision = self.service.orchestrator.decide(
            "prepare meu ambiente")
        brain.last_llm = {}
        brain.request_metrics.return_value = {"total_llm_calls": 1}
        with patch.object(voice, "_get_brain", return_value=brain):
            voice._handle("prepare meu ambiente")
        self.assertEqual("Recebi. Vou analisar isso.", spoken[0])
        self.assertEqual("Análise pronta.", spoken[1])
        self.assertTrue(voice.last_event["ack"]["emitted"])
        self.assertIn("time_to_ack_ms", voice.last_event["timings"])

    def test_background_ack_running_verified_success(self):
        manager = TaskManager(self.temp.name)
        plan = TaskPlan("slow-safe", (PlanStep(
            "one", "slow", Route.TASK, "slow_safe", {}, background=True),))
        task_id = manager.create(plan)
        started = time.perf_counter()
        ack = ack_for_decision(
            CentralOrchestrator(self.service.registry).decide("prepare meu ambiente"),
            self.service.registry)
        time_to_ack_ms = int((time.perf_counter() - started) * 1000)

        def execute(_step, _token):
            time.sleep(0.1)
            return {"ok": True, "success": True, "verified": True,
                    "verification": "safe_test", "response_policy": "BACKGROUND"}

        future = manager.start(task_id, execute)
        task = future.result(timeout=2)
        self.assertTrue(ack["emitted"])
        self.assertLess(time_to_ack_ms, 50)
        self.assertEqual(TaskStatus.COMPLETED, task.status)
        self.assertTrue(manager.steps(task_id)[0].result["verified"])
        manager.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
