from pathlib import Path

import pytest

from jarvis_core.market_read_models import build_market_intelligence_snapshot
from jarvis_core.robot_intelligence import build_evidence_dataset, build_robot_intelligence_snapshot
from jarvis_core.temporal_market_context import (
    LeakageViolation,
    UNKNOWN,
    build_production_window_contexts,
    build_temporal_market_snapshot,
    link_outcomes_after_context_freeze,
)


def test_context_is_frozen_with_unknown_labels_when_historical_inputs_are_absent():
    context = build_temporal_market_snapshot(
        symbol="XAUUSD", timeframe="M1", cutoff="2026-08-24T00:00:00+00:00",
        source_authority="FIXTURE", source_artifacts=("evidence.json",),
    )
    assert context["frozen"] is True
    assert context["context_status"] == "CONTEXT_UNKNOWN"
    assert context["labels"]["TREND_STATE"]["label"] == UNKNOWN
    assert context["provenance"]["outcome_excluded_from_labeling"] is True
    assert context["context_fingerprint"]


def test_future_available_at_is_rejected():
    with pytest.raises(LeakageViolation, match="FUTURE"):
        build_temporal_market_snapshot(
            symbol="XAUUSD", timeframe="M1", cutoff="2026-08-24T00:00:00+00:00",
            observations={"TREND_STATE": {
                "label": "UP", "status": "OBSERVED",
                "available_at": "2026-08-24T00:01:00+00:00",
            }},
        )


def test_observed_label_requires_available_at():
    with pytest.raises(LeakageViolation, match="AVAILABLE_AT_REQUIRED"):
        build_temporal_market_snapshot(
            symbol="XAUUSD", timeframe="M1", cutoff="2026-08-24T00:00:00+00:00",
            observations={"TREND_STATE": {"label": "UP", "status": "OBSERVED"}},
        )


@pytest.mark.parametrize("field", ["balance_change", "final_balance", "OnTester", "robot_trades"])
def test_robot_outcome_fields_are_never_label_inputs(field):
    with pytest.raises(LeakageViolation, match="OUTCOME_FEATURE_FORBIDDEN"):
        build_temporal_market_snapshot(
            symbol="XAUUSD", timeframe="M1", cutoff="2026-08-24T00:00:00+00:00",
            observations={field: 1},
        )


def test_registered_windows_are_independent_and_have_no_fabricated_labels():
    contexts = build_production_window_contexts()
    assert [item["test_run_id"] for item in contexts] == [
        "run_1c8069dbd88842a4ad88cd9d6ae6fa7d",
        "run_a8180c7c559746da9b7a6863f6796292",
        "run_c078697fe9ce4892bc9665e6f276be58",
    ]
    assert len({item["context_fingerprint"] for item in contexts}) == 3
    assert all(item["context_status"].startswith("BLOCKED_") for item in contexts)
    assert all(item["labels"]["VOLATILITY_STATE"]["label"] == UNKNOWN for item in contexts)


def test_outcome_join_happens_after_context_freeze_and_remains_separate():
    contexts = build_production_window_contexts()
    result = link_outcomes_after_context_freeze(contexts, [{
        "test_run_id": contexts[0]["test_run_id"],
        "robot_id": "EA_Canal_Pullback_MT5",
        "final_balance": 100747.18,
    }])
    row = result["rows"][0]
    assert row["outcome_role"] == "POST_WINDOW_OUTCOME"
    assert row["label_inputs_excluded"] is True
    assert row["market_labels"]["TREND_STATE"]["label"] == UNKNOWN
    assert row["post_window_outcome"]["final_balance"] == 100747.18


def test_evidence_dataset_keeps_outcome_separate_from_temporal_labels():
    contexts = build_production_window_contexts()
    dataset = build_evidence_dataset([{
        "robot_id": "robot-a", "backtest_artifacts": [{
            "artifact_id": "run-a", "test_run_id": contexts[0]["test_run_id"],
            "evidence_type": "BACKTEST", "metrics": {"final_balance": 1},
        }],
    }], contexts)
    row = dataset["rows"][0]
    assert row["temporal_context"]["context_fingerprint"]
    assert row["post_window_outcome"] == {"final_balance": 1}
    assert "final_balance" not in row["temporal_context"]["labels"]
    assert "CONTEXT_FROZEN_BEFORE_OUTCOME_JOIN" in dataset["leakage_controls"]


def test_b46_is_exposed_by_existing_robot_and_market_read_models():
    market = build_market_intelligence_snapshot(
        overview={"data": {"assets": [], "macro": {}, "news": []}},
        chart={"data": {}}, scanner={"data": {}}, risk={"data": {}},
        validation={"data": {}}, symbol="XAUUSD", timeframe="M1",
        correlation_id="b46-test", captured_at="2026-08-24T00:00:00+00:00",
    )
    result = build_robot_intelligence_snapshot(
        {"data": {"robots": []}}, market, "XAUUSD", "M1", "b46-test",
    )
    assert market["temporal_context"]["context_status"] == "CONTEXT_UNKNOWN"
    assert len(result["temporal_contexts"]) == 3
    assert result["security"]["execution_authority"] == "NONE"


def test_b46_uses_the_existing_control_center_surface():
    root = Path(__file__).resolve().parents[1]
    app = (root / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    html = (root / "jarvis_ui" / "jarvis.html").read_text(encoding="utf-8")
    assert "gB46TemporalContext" in app
    assert "gB46TemporalContext" in html
    assert "/api/jarvis/golden/robot-intelligence" in app
    assert "POST_WINDOW_OUTCOME" in app
