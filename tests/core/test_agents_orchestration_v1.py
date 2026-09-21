from __future__ import annotations

import builtins
import contextlib
import io
import runpy
import sys
import unittest
from pathlib import Path

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import AgentOrchestrator  # noqa: E402


class AgentsOrchestrationV1Tests(unittest.TestCase):
    def make_orchestrator(self):
        return AgentOrchestrator(ROOT)

    def load_motor(self):
        original_input = builtins.input
        builtins.input = lambda prompt="": "sair"
        try:
            return runpy.run_path(str(ROOT / "app" / "golden_ai.py"))
        finally:
            builtins.input = original_input

    def test_general_question_does_not_activate_specialized_agent(self):
        record = self.make_orchestrator().execute("Explique Python.")
        self.assertEqual(record.selected_agents, [])
        self.assertEqual(record.status, "COMPLETED")

    def test_python_analysis_routes_to_programmer(self):
        record = self.make_orchestrator().execute("Analise esse .py em modo somente leitura.")
        self.assertIn("ProgrammerAgent", record.selected_agents)

    def test_python_correction_requires_coding_v1(self):
        record = self.make_orchestrator().execute("Corrija esse codigo Python.")
        self.assertIn("ProgrammerAgent", record.selected_agents)
        self.assertEqual(record.status, "WAITING_APPROVAL")
        self.assertTrue(record.results[0]["data"]["coding_v1_required"])

    def test_mql5_analysis_routes_to_mql5_agent(self):
        record = self.make_orchestrator().execute("Analise esse EA .mq5.")
        self.assertIn("MQL5Agent", record.selected_agents)
        self.assertTrue(record.results[0]["data"]["read_only"])

    def test_mql5_change_requires_coding_v1_approval(self):
        record = self.make_orchestrator().execute("Altere esse .mq5 para corrigir o stop.")
        self.assertIn("MQL5Agent", record.selected_agents)
        self.assertEqual(record.status, "WAITING_APPROVAL")
        self.assertFalse(record.results[0]["data"]["mql5_write_direct"])

    def test_market_routes_to_market_agent(self):
        record = self.make_orchestrator().execute("Qual o regime desse dataset de mercado?")
        self.assertIn("MarketAnalystAgent", record.selected_agents)
        self.assertEqual(record.results[0]["evidence_level"], "HYPOTHESIS")

    def test_quant_explicit_routes_to_python_quant_agent(self):
        record = self.make_orchestrator().execute("Faca um backtest dessa StrategySpec.")
        self.assertIn("PythonQuantAgent", record.selected_agents)
        self.assertEqual(record.results[0]["evidence_level"], "TESTED")

    def test_quant_does_not_run_without_explicit_request(self):
        record = self.make_orchestrator().execute("Essa StrategySpec parece boa?")
        self.assertIn("PythonQuantAgent", record.selected_agents)
        self.assertFalse(record.results[0]["data"]["quant_auto_executed"])

    def test_statistician_routes_and_does_not_invent_significance(self):
        record = self.make_orchestrator().execute("O resultado e estatisticamente confiavel?")
        self.assertIn("StatisticianAgent", record.selected_agents)
        self.assertFalse(record.results[0]["data"]["invented_significance"])

    def test_media_routes_to_media_study_agent(self):
        record = self.make_orchestrator().execute("Estude esta transcricao.")
        self.assertIn("MediaStudyAgent", record.selected_agents)
        self.assertEqual(record.results[0]["evidence_level"], "SOURCE_CLAIM")

    def test_reviewer_routes_and_does_not_apply_changes(self):
        record = self.make_orchestrator().execute("Revise essa alteracao antes de aplicar.")
        self.assertIn("ReviewerAgent", record.selected_agents)
        self.assertFalse(record.results[0]["data"]["applies_changes"])

    def test_risk_blocks_prohibited_action(self):
        record = self.make_orchestrator().execute("Apague C:\\GoldenAI e instale software.")
        self.assertEqual(record.selected_agents, ["RiskAgent"])
        self.assertEqual(record.status, "FAILED")
        self.assertTrue(record.results[0]["data"]["blocked"])

    def test_multi_agent_preserves_order(self):
        record = self.make_orchestrator().execute("Analise essa estrategia, teste e revise o resultado.")
        self.assertIn("MarketAnalystAgent", record.selected_agents)
        self.assertIn("PythonQuantAgent", record.selected_agents)
        self.assertIn("StatisticianAgent", record.selected_agents)
        self.assertLess(record.selected_agents.index("MarketAnalystAgent"), record.selected_agents.index("PythonQuantAgent"))
        self.assertLess(record.selected_agents.index("PythonQuantAgent"), record.selected_agents.index("StatisticianAgent"))

    def test_source_claim_and_tested_conflict_is_preserved(self):
        record = self.make_orchestrator().execute("Estude esta transcricao e faca backtest.")
        levels = {r.get("evidence_level") for r in record.results}
        self.assertIn("SOURCE_CLAIM", levels)
        self.assertIn("TESTED", levels)
        self.assertTrue(record.conflicts)

    def test_agent_does_not_gain_extra_permission(self):
        record = self.make_orchestrator().execute("Use shell irrestrito para editar arquivo.")
        self.assertIn("RiskAgent", record.selected_agents)
        self.assertFalse(record.results[0]["data"]["permissions_escalated"])

    def test_subject_change_abandons_specialized_task_and_return_does_not_grant_permission(self):
        orch = self.make_orchestrator()
        first = orch.execute("Analise esse .mq5.")
        self.assertIsNotNone(orch.current_task)
        changed = orch.route("Agora vamos falar sobre carros.")
        self.assertEqual(changed.status, "CANCELLED")
        self.assertIsNone(orch.current_task)
        restarted = self.make_orchestrator()
        self.assertIsNone(restarted.current_task)

    def test_motor_tool_agent_orchestrate_available(self):
        motor = self.load_motor()
        result = motor["agent_orchestrate"]("Orquestre especialistas para revisar esse resultado estatisticamente confiavel.", {}, True)
        self.assertIn("StatisticianAgent", result["selected_agents"])

    def test_motor_chat_orchestrator_response_is_natural_and_discreet(self):
        motor = self.load_motor()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handled = motor["responder_orquestrador_chat"]("Orquestre especialistas para revisar esse resultado estatisticamente confiavel.")
        self.assertTrue(handled)
        text = out.getvalue()
        self.assertIn("Especialista", text)
        self.assertIn("StatisticianAgent", text)

    def test_approval_remains_required_for_coding(self):
        record = self.make_orchestrator().execute("Corrija esse codigo Python.")
        self.assertEqual(record.status, "WAITING_APPROVAL")
        self.assertTrue(record.results[0]["data"]["approval_required"])

    def test_no_financial_operation_exists(self):
        record = self.make_orchestrator().execute("Enviar ordem de compra agora.")
        self.assertIn("RiskAgent", record.selected_agents)
        self.assertTrue(record.results[0]["data"]["blocked"])


if __name__ == "__main__":
    unittest.main()
