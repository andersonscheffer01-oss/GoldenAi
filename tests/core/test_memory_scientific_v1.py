from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory import ScientificMemoryService  # noqa: E402
from core.safety import EvidenceLevel  # noqa: E402
from market import MarketAnalysisService, SyntheticMarketDataAdapter  # noqa: E402
from quant import CostModel, QuantService, build_backtest_spec  # noqa: E402


def rows_from_closes(closes: list[float]) -> list[dict]:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes, start=1):
        rows.append({
            "timestamp": f"2026-04-{index:02d}T00:00:00+00:00",
            "open": previous,
            "high": max(previous, close) + 0.5,
            "low": min(previous, close) - 0.5,
            "close": close,
        })
        previous = close
    return rows


class ScientificMemoryV1Tests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        service = ScientificMemoryService(Path(tmp.name))
        self.addCleanup(tmp.cleanup)
        return service, Path(tmp.name)

    def test_create_retrieve_and_search_knowledge_item(self):
        service, _ = self.make_service()
        item = service.store_knowledge(
            topic="engolfo",
            statement="Engolfo de alta e uma alegacao de fonte, nao validacao interna.",
            evidence_level=EvidenceLevel.SOURCE_CLAIM,
            source_type="USER_NOTE",
            tags=["price_action", "engolfo"],
        )
        loaded = service.get_knowledge(item.knowledge_id)
        self.assertEqual(loaded["knowledge_id"], item.knowledge_id)
        self.assertTrue(service.search_knowledge(topic="engolfo"))
        self.assertTrue(service.search_knowledge(tags=["price_action"]))
        self.assertTrue(service.search_knowledge(evidence_level="SOURCE_CLAIM"))
        self.assertEqual(loaded["source_type"], "USER_NOTE")

    def test_link_experiment_preserves_source(self):
        service, _ = self.make_service()
        item = service.store_knowledge("setup x", "Setup X possui expectativa positiva.", "HYPOTHESIS", "USER_NOTE")
        link = service.link_experiment(item.knowledge_id, "experiment_123")
        self.assertEqual(link["experiment_id"], "experiment_123")

    def test_quant_experiment_becomes_tested_not_validated(self):
        service, root = self.make_service()
        quant = QuantService(root)
        rows = rows_from_closes([100, 101, 102, 103, 104])
        strategy = quant.strategy("setup quant positivo", "close_above_open", parameters={"hold_bars": 1})
        dataset = quant.dataset_from_rows(rows, "synthetic", "XAUUSD", "H1")
        spec = build_backtest_spec(strategy, dataset, cost_model=CostModel())
        experiment_id, payload = quant.run_backtest(spec, rows)
        item = service.store_quant_experiment(experiment_id, spec, payload["result"], payload["artifact_dir"])
        self.assertEqual(item.normalized_evidence_level(), "TESTED")
        self.assertNotEqual(item.normalized_evidence_level(), "VALIDATED")
        self.assertEqual(item.source_id, experiment_id)
        self.assertTrue(service.search_knowledge(experiment_id=experiment_id))

    def test_market_levels_remain_separated(self):
        service, root = self.make_service()
        market = MarketAnalysisService(root)
        result = market.analyze("XAUUSD", SyntheticMarketDataAdapter({"H1": rows_from_closes([100, 103, 106, 109, 113])}), "synthetic")
        items = service.store_market_analysis(result.report, result.analysis_id)
        levels = {item.normalized_evidence_level() for item in items}
        self.assertIn("OBSERVED", levels)
        self.assertIn("INFERRED", levels)
        self.assertIn("HYPOTHESIS", levels)
        self.assertNotIn("VALIDATED", levels)

    def test_hypothesis_request_does_not_promote_to_validated(self):
        service, _ = self.make_service()
        item = service.store_knowledge("setup y", "Hipotese de continuacao.", "VALIDATED", "MARKET")
        self.assertNotEqual(item.normalized_evidence_level(), "VALIDATED")

    def test_supersede_preserves_old_item(self):
        service, _ = self.make_service()
        old = service.store_knowledge("setup z", "Setup Z parecia positivo.", "HYPOTHESIS", "USER_NOTE")
        new = service.store_knowledge("setup z", "Setup Z foi reavaliado.", "TESTED", "QUANT_EXPERIMENT", supersedes_id=old.knowledge_id)
        self.assertEqual(new.supersedes_id, old.knowledge_id)
        self.assertIsNotNone(service.get_knowledge(old.knowledge_id))

    def test_conflict_is_detected_and_preserved(self):
        service, _ = self.make_service()
        service.store_knowledge("estrategia conflito", "Essa estrategia ganha 80%.", "SOURCE_CLAIM", "USER_NOTE")
        service.store_knowledge(
            "estrategia conflito",
            "Experimento interno encontrou resultado negativo.",
            "TESTED",
            "QUANT_EXPERIMENT",
            metadata={"metrics": {"net_profit": -10.0, "win_rate": 0.47}},
        )
        summary = service.get_topic_summary("estrategia conflito")
        self.assertTrue(summary["conflicts"])

    def test_search_returns_source_fields(self):
        service, _ = self.make_service()
        item = service.store_knowledge("fonte", "Resultado observado.", "OBSERVED", "MARKET", source_id="analysis_1")
        result = service.search_knowledge(text="observado")[0]
        self.assertEqual(result["source_id"], item.source_id)
        self.assertEqual(result["evidence_level"], "OBSERVED")

    def test_casual_conversation_does_not_create_memory_by_classifier(self):
        import runpy
        import builtins

        original_input = builtins.input
        builtins.input = lambda prompt="": "sair"
        try:
            motor = runpy.run_path(str(ROOT / "app" / "golden_ai.py"))
        finally:
            builtins.input = original_input
        self.assertFalse(motor["pergunta_pede_memoria"]("Ola, vamos conversar sobre carros."))

    def test_explicit_user_request_creates_source_claim_not_fact(self):
        service, _ = self.make_service()
        item = service.store_knowledge("nota explicita", "Essa estrategia ganha 80%.", "VALIDATED", "USER_NOTE")
        self.assertEqual(item.normalized_evidence_level(), "SOURCE_CLAIM")
        self.assertEqual(item.source_type, "USER_NOTE")

    def test_experiment_can_contradict_source_claim(self):
        service, _ = self.make_service()
        claim = service.store_knowledge("setup contraditorio", "Essa estrategia ganha 80%.", "SOURCE_CLAIM", "USER_NOTE")
        tested = service.store_knowledge(
            "setup contraditorio",
            "Backtest interno encontrou win rate 47% e prejuizo.",
            "TESTED",
            "QUANT_EXPERIMENT",
            source_id="experiment_47",
            metadata={"metrics": {"net_profit": -5.0, "win_rate": 0.47}},
        )
        summary = service.get_topic_summary("setup contraditorio")
        self.assertEqual(claim.normalized_evidence_level(), "SOURCE_CLAIM")
        self.assertEqual(tested.normalized_evidence_level(), "TESTED")
        self.assertTrue(summary["conflicts"])

    def test_memory_answers_already_tested_query(self):
        service, _ = self.make_service()
        service.store_knowledge("setup ema", "Hipotese Quant testada no experimento experiment_ema.", "TESTED", "QUANT_EXPERIMENT", source_id="experiment_ema")
        related = service.find_related_experiments("ema")
        self.assertEqual(related[0]["source_id"], "experiment_ema")

    def test_restarted_database_preserves_memory(self):
        service, root = self.make_service()
        item = service.store_knowledge("persistencia", "Memoria deve sobreviver reinicio.", "OBSERVED", "SYSTEM")
        restarted = ScientificMemoryService(root)
        self.assertEqual(restarted.get_knowledge(item.knowledge_id)["statement"], item.statement)

    def test_no_external_file_is_modified(self):
        service, root = self.make_service()
        external = root / "external_marker.txt"
        external.write_text("inalterado", encoding="utf-8")
        before = external.read_text(encoding="utf-8")
        service.store_knowledge("seguranca", "Nenhuma ordem e executada pela memoria.", "OBSERVED", "SYSTEM")
        self.assertEqual(external.read_text(encoding="utf-8"), before)

    def test_memory_has_no_order_execution_api(self):
        service, _ = self.make_service()
        self.assertFalse(hasattr(service, "send_order"))
        self.assertFalse(hasattr(service, "open_position"))


if __name__ == "__main__":
    unittest.main()
