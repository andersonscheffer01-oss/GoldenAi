from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import sys

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant import CostModel, QuantService, StrategySpec, build_backtest_spec, deterministic_hash, validate_ohlc_rows  # noqa: E402
from quant.backtest import BacktestEngine, result_hash  # noqa: E402


def rows_from_prices(prices: list[tuple[float, float]]) -> list[dict]:
    rows = []
    for index, (open_, close) in enumerate(prices):
        rows.append({
            "timestamp": f"2026-01-{index+1:02d}T00:00:00+00:00",
            "open": open_,
            "high": max(open_, close),
            "low": min(open_, close),
            "close": close,
        })
    return rows


class QuantV1Tests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        service = QuantService(Path(tmp.name))
        self.addCleanup(tmp.cleanup)
        return service, Path(tmp.name)

    def make_specs(self, service, rows, entry="close_above_open", costs=None):
        dataset = service.dataset_from_rows(rows, "synthetic", "TEST", "D1")
        strategy = service.strategy("synthetic strategy", entry, parameters={"hold_bars": 1}, description="Hipotese sintetica")
        spec = build_backtest_spec(strategy, dataset, initial_capital=1000.0, quantity=1.0, cost_model=costs or CostModel())
        return dataset, strategy, spec

    def test_strategy_hash_is_deterministic(self):
        a = StrategySpec(strategy_id="s1", name="A", version="1", description="", parameters={"x": 1}, entry_logic_identifier="never", exit_logic_identifier="hold")
        b = StrategySpec(strategy_id="s1", name="A", version="1", description="", parameters={"x": 1}, entry_logic_identifier="never", exit_logic_identifier="hold")
        self.assertEqual(a.config_hash(), b.config_hash())

    def test_dataset_spec_and_hash(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (2, 3)])
        dataset = service.dataset_from_rows(rows, "synthetic", "ABC", "M1")
        self.assertEqual(dataset.row_count, 2)
        self.assertEqual(dataset.data_hash, deterministic_hash(rows))

    def test_dataset_validation_errors(self):
        self.assertFalse(validate_ohlc_rows([]).ok)
        duplicate = rows_from_prices([(1, 2), (2, 3)])
        duplicate[1]["timestamp"] = duplicate[0]["timestamp"]
        self.assertFalse(validate_ohlc_rows(duplicate).ok)
        bad = rows_from_prices([(1, 2)])
        bad[0]["high"] = 0
        self.assertFalse(validate_ohlc_rows(bad).ok)
        missing = [{"timestamp": "2026-01-01T00:00:00+00:00", "open": 1}]
        self.assertFalse(validate_ohlc_rows(missing).ok)

    def test_profitable_strategy_produces_trade_metrics_and_equity(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 15), (2, 1)])
        _, _, spec = self.make_specs(service, rows)
        exp_id, payload = service.run_backtest(spec, rows)
        result = payload["result"]
        self.assertEqual(result.metrics.total_trades, 1)
        self.assertGreater(result.metrics.net_profit, 0)
        self.assertEqual(len(result.equity_curve), 2)
        self.assertEqual(result.trades[0].signal_time, rows[0]["timestamp"])
        self.assertEqual(result.trades[0].entry_time, rows[1]["timestamp"])

    def test_losing_strategy(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 5), (2, 1)])
        _, _, spec = self.make_specs(service, rows)
        _, payload = service.run_backtest(spec, rows)
        self.assertLess(payload["result"].metrics.net_profit, 0)
        self.assertEqual(payload["result"].metrics.losses, 1)

    def test_no_trades_returns_none_rates(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(2, 1), (2, 1), (2, 1)])
        _, _, spec = self.make_specs(service, rows, entry="close_above_open")
        _, payload = service.run_backtest(spec, rows)
        self.assertEqual(payload["result"].metrics.total_trades, 0)
        self.assertIsNone(payload["result"].metrics.win_rate)

    def test_only_wins_and_only_losses(self):
        service, _ = self.make_service()
        win_rows = rows_from_prices([(1, 2), (10, 12), (1, 2), (20, 25)])
        _, _, spec = self.make_specs(service, win_rows)
        _, win_payload = service.run_backtest(spec, win_rows)
        self.assertEqual(win_payload["result"].metrics.losses, 0)
        loss_rows = rows_from_prices([(1, 2), (10, 8), (1, 2), (20, 19)])
        dataset = service.dataset_from_rows(loss_rows, "synthetic2", "TEST", "D1")
        spec.dataset = dataset
        _, loss_payload = service.run_backtest(spec, loss_rows)
        self.assertEqual(loss_payload["result"].metrics.wins, 0)

    def test_costs_reduce_net_profit(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 12), (2, 1)])
        _, _, zero = self.make_specs(service, rows, costs=CostModel())
        _, p0 = service.run_backtest(zero, rows)
        _, _, costly = self.make_specs(service, rows, costs=CostModel(spread=0.5, commission=0.25, slippage=0.25))
        _, p1 = service.run_backtest(costly, rows)
        self.assertLess(p1["result"].metrics.net_profit, p0["result"].metrics.net_profit)
        self.assertGreater(p1["result"].trades[0].costs, 0)

    def test_drawdown(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 15), (1, 2), (20, 10)])
        _, _, spec = self.make_specs(service, rows)
        _, payload = service.run_backtest(spec, rows)
        self.assertGreater(payload["result"].metrics.max_drawdown_abs, 0)

    def test_reproducibility(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 15), (2, 1)])
        _, _, spec = self.make_specs(service, rows)
        engine = BacktestEngine()
        a = engine.run("fixed", spec, rows)
        b = engine.run("fixed", spec, rows)
        self.assertEqual(result_hash(a), result_hash(b))
        self.assertEqual([asdict(t) for t in a.trades], [asdict(t) for t in b.trades])

    def test_anti_lookahead_future_candle_does_not_change_prior_entry(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 12), (50, 1), (100, 1)])
        _, _, spec = self.make_specs(service, rows)
        a = BacktestEngine().run("fixed", spec, rows)
        changed = [dict(row) for row in rows]
        changed[3]["open"] = 999
        changed[3]["high"] = 1000
        changed[3]["close"] = 998
        b = BacktestEngine().run("fixed", spec, changed)
        self.assertEqual(a.trades[0].signal_time, b.trades[0].signal_time)
        self.assertEqual(a.trades[0].entry_time, b.trades[0].entry_time)
        self.assertEqual(a.trades[0].entry_price, b.trades[0].entry_price)

    def test_persistence_and_artifacts(self):
        service, root = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 15), (2, 1)])
        _, _, spec = self.make_specs(service, rows)
        exp_id, payload = service.run_backtest(spec, rows)
        loaded = service.repo.get_backtest(exp_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["backtest_hash"], spec.config_hash())
        artifact_dir = Path(payload["artifact_dir"])
        self.assertTrue((artifact_dir / "config.json").exists())
        self.assertTrue((artifact_dir / "metrics.json").exists())
        self.assertTrue((artifact_dir / "trades.csv").exists())
        self.assertTrue((artifact_dir / "equity.csv").exists())
        self.assertTrue((artifact_dir / "report.json").exists())

    def test_ab_comparison(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 15), (1, 2), (20, 10)])
        _, _, spec_a = self.make_specs(service, rows, costs=CostModel())
        a, _ = service.run_backtest(spec_a, rows)
        _, _, spec_b = self.make_specs(service, rows, costs=CostModel(commission=1.0))
        b, _ = service.run_backtest(spec_b, rows)
        comparison = service.compare(a, b)
        self.assertIn("net_profit", comparison.differences)
        self.assertIn("nao declara vencedor", comparison.interpretation)

    def test_report_separates_results_from_interpretation(self):
        service, _ = self.make_service()
        rows = rows_from_prices([(1, 2), (10, 15), (2, 1)])
        _, _, spec = self.make_specs(service, rows)
        _, payload = service.run_backtest(spec, rows)
        report = json.loads((Path(payload["artifact_dir"]) / "report.json").read_text(encoding="utf-8"))
        self.assertIn("observed_results", report)
        self.assertIn("interpretation", report)
        self.assertIn("limitations", report)


if __name__ == "__main__":
    unittest.main()
