from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.safety import EvidenceLevel  # noqa: E402
from market import MarketAnalysisService, SyntheticMarketDataAdapter, validate_market_data  # noqa: E402
from market.analysis import structure_from_rows  # noqa: E402


def rows_from_closes(closes: list[float], start_open: float | None = None) -> list[dict]:
    rows = []
    previous = start_open if start_open is not None else closes[0]
    for index, close in enumerate(closes):
        open_ = previous
        high = max(open_, close) + 0.5
        low = min(open_, close) - 0.5
        rows.append({
            "timestamp": f"2026-01-{index+1:02d}T00:00:00+00:00",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        })
        previous = close
    return rows


def volatility_rows(last_range: float) -> list[dict]:
    rows = []
    price = 100.0
    for index in range(9):
        rows.append({
            "timestamp": f"2026-02-{index+1:02d}T00:00:00+00:00",
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
        })
    rows.append({
        "timestamp": "2026-02-10T00:00:00+00:00",
        "open": price,
        "high": price + last_range / 2.0,
        "low": price - last_range / 2.0,
        "close": price,
    })
    return rows


class MarketV1Tests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        service = MarketAnalysisService(Path(tmp.name))
        self.addCleanup(tmp.cleanup)
        return service

    def analyze(self, data_by_timeframe):
        return self.make_service().analyze("XAUUSD", SyntheticMarketDataAdapter(data_by_timeframe), "synthetic_test")

    def test_detects_up_down_range_and_volatility_regimes(self):
        up = self.analyze({"H1": rows_from_closes([100, 103, 106, 109, 113])})
        self.assertEqual(up.regimes[0].regime, "TREND_UP")
        down = self.analyze({"H1": rows_from_closes([113, 109, 106, 103, 100])})
        self.assertEqual(down.regimes[0].regime, "TREND_DOWN")
        ranging = self.analyze({"H1": rows_from_closes([100, 101, 99.5, 100.2, 100.1])})
        self.assertEqual(ranging.regimes[0].regime, "RANGE")
        high_vol = self.analyze({"H1": volatility_rows(50.0)})
        self.assertEqual(high_vol.regimes[0].regime, "HIGH_VOLATILITY")
        low_vol_rows = volatility_rows(30.0)
        low_vol_rows[-1]["high"] = 100.1
        low_vol_rows[-1]["low"] = 99.9
        low_vol = self.analyze({"H1": low_vol_rows})
        self.assertEqual(low_vol.regimes[0].regime, "LOW_VOLATILITY")

    def test_multi_timeframe_alignment_and_conflict(self):
        aligned = self.analyze({
            "H1": rows_from_closes([100, 103, 106, 109, 113]),
            "M15": rows_from_closes([50, 52, 54, 56, 58]),
        })
        self.assertEqual(aligned.mtf_context.alignment, "TREND_UP")
        conflict = self.analyze({
            "H1": rows_from_closes([100, 103, 106, 109, 113]),
            "M15": rows_from_closes([58, 56, 54, 52, 50]),
        })
        self.assertEqual(conflict.mtf_context.alignment, "CONFLICT")
        self.assertTrue(conflict.mtf_context.conflicts)

    def test_structure_tracks_swings_support_and_resistance(self):
        rows = [
            {"timestamp": "2026-03-01T00:00:00+00:00", "open": 100, "high": 101, "low": 99, "close": 100},
            {"timestamp": "2026-03-02T00:00:00+00:00", "open": 100, "high": 106, "low": 100, "close": 104},
            {"timestamp": "2026-03-03T00:00:00+00:00", "open": 104, "high": 105, "low": 98, "close": 101},
            {"timestamp": "2026-03-04T00:00:00+00:00", "open": 101, "high": 108, "low": 101, "close": 106},
            {"timestamp": "2026-03-05T00:00:00+00:00", "open": 106, "high": 107, "low": 97, "close": 102},
            {"timestamp": "2026-03-06T00:00:00+00:00", "open": 102, "high": 109, "low": 102, "close": 108},
            {"timestamp": "2026-03-07T00:00:00+00:00", "open": 108, "high": 108.5, "low": 103, "close": 105},
        ]
        structure = structure_from_rows("XAUUSD", "M5", rows)
        self.assertTrue(structure.swing_highs)
        self.assertTrue(structure.swing_lows)
        self.assertEqual(structure.support, min(row["low"] for row in rows[-5:]))
        self.assertEqual(structure.resistance, max(row["high"] for row in rows[-5:]))

    def test_evidence_levels_are_separated(self):
        result = self.analyze({"H1": rows_from_closes([100, 103, 106, 109, 113])})
        self.assertIn(EvidenceLevel.OBSERVED, {item.evidence_level for item in result.observations})
        self.assertTrue(all(item.evidence_level == EvidenceLevel.INFERRED for item in result.regimes))
        self.assertTrue(all(item.evidence_level == EvidenceLevel.HYPOTHESIS for item in result.signals))
        all_levels = {item.evidence_level for item in result.observations}
        all_levels.update(item.evidence_level for item in result.regimes)
        all_levels.update(item.evidence_level for item in result.signals)
        self.assertNotIn(EvidenceLevel.VALIDATED, all_levels)

    def test_invalid_and_absent_data_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_market_data({})
        bad_rows = [{"timestamp": "2026-01-01T00:00:00+00:00", "open": 1.0}]
        with self.assertRaises(ValueError):
            validate_market_data({"H1": bad_rows})

    def test_persistence_and_strategy_bridge(self):
        service = self.make_service()
        result = service.analyze("XAUUSD", SyntheticMarketDataAdapter({"H1": rows_from_closes([100, 103, 106, 109, 113])}))
        loaded = service.repository.get_analysis(result.analysis_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["result_hash"], result.result_hash)
        strategy = service.hypothesis_to_strategy_spec(result)
        self.assertEqual(strategy.entry_logic_identifier, "market_context_placeholder")
        self.assertEqual(strategy.unknowns["validation_status"], "NOT_BACKTESTED")

    def test_reproducibility_same_input_same_hash(self):
        rows = rows_from_closes([100, 103, 106, 109, 113])
        a = self.analyze({"H1": rows})
        b = self.analyze({"H1": rows})
        self.assertEqual(a.result_hash, b.result_hash)

    def test_anti_lookahead_as_of_ignores_future_rows(self):
        rows = rows_from_closes([100, 103, 106, 109, 113, 160, 80])
        as_of = rows[4]["timestamp"]
        service = self.make_service()
        first = service.analyze("XAUUSD", SyntheticMarketDataAdapter({"H1": rows}), as_of_timestamp=as_of)
        changed = [dict(row) for row in rows]
        changed[5]["open"] = 999
        changed[5]["high"] = 1200
        changed[5]["low"] = 998
        changed[5]["close"] = 1190
        changed[6]["open"] = 1
        changed[6]["high"] = 2
        changed[6]["low"] = 0.5
        changed[6]["close"] = 1.5
        second = service.analyze("XAUUSD", SyntheticMarketDataAdapter({"H1": changed}), as_of_timestamp=as_of)
        self.assertEqual(first.result_hash, second.result_hash)
        self.assertEqual(first.snapshots[0].timestamp, as_of)


if __name__ == "__main__":
    unittest.main()
