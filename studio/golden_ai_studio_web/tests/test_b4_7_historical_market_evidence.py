from datetime import datetime, timedelta, timezone

import pytest

from jarvis_core.historical_market_evidence import (
    HistoricalEvidenceError,
    PRODUCTION_WINDOWS,
    build_historical_artifact,
    build_readonly_mt5_request,
    build_window_context,
    terminal_read_gate,
)
from jarvis_core.temporal_market_context import LeakageViolation, build_production_window_contexts


def _bars(count=48):
    start = datetime(2026, 8, 24, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        price = 2300.0 + index * 0.2
        rows.append({
            "time": int((start + timedelta(minutes=index)).timestamp()),
            "open": price, "high": price + 0.3, "low": price - 0.1, "close": price + 0.2,
            "tick_volume": 10 + index, "spread": 15, "real_volume": 0,
        })
    return rows


def test_artifact_is_deterministic_and_quality_is_explicit():
    first = build_historical_artifact(_bars(), source="FIXTURE", source_version="test-v1")
    second = build_historical_artifact(_bars(), source="FIXTURE", source_version="test-v1")
    assert first.raw_fingerprint == second.raw_fingerprint
    assert first.normalized_fingerprint == second.normalized_fingerprint
    assert first.artifact_id == second.artifact_id
    assert first.quality["quality_status"] == "PASS"
    assert first.availability_semantics == "COMPLETED_M1_BAR_AVAILABLE_AFTER_BAR_CLOSE"


@pytest.mark.parametrize("symbol,timeframe", [("GOLD", "M1"), ("XAUUSD", "M5")])
def test_artifact_rejects_identity_substitution(symbol, timeframe):
    with pytest.raises(HistoricalEvidenceError):
        build_historical_artifact(_bars(), symbol=symbol, timeframe=timeframe, source="FIXTURE")


def test_quality_keeps_invalid_rows_and_marks_gap():
    rows = _bars(4)
    rows[2]["time"] += 5 * 60
    rows.append({"time": "bad", "open": 1, "high": 1, "low": 1, "close": 1})
    artifact = build_historical_artifact(rows, source="FIXTURE")
    assert artifact.quality["invalid_rows"] == 1
    assert artifact.quality["quality_status"] == "FAIL"
    assert artifact.quality["missing_intervals"]


def test_context_is_window_descriptive_and_supersedes_b46_unknown():
    artifact = build_historical_artifact(_bars(), source="FIXTURE")
    prior = build_production_window_contexts()[0]
    context = build_window_context(artifact, prior_context=prior, window_id="R1")
    assert context["context_status"] == "EVIDENCE_BACKED_WINDOW_DESCRIPTIVE"
    assert context["window_semantics"] == "WINDOW_DESCRIPTIVE"
    assert context["prior_context_preserved"] is True
    assert context["memory_lineage"]["supersedes_context_fingerprint"] == prior["context_fingerprint"]
    assert context["labels"]["TREND_STATE"]["label"] == "TREND_UP"
    assert context["session_distribution"]["timezone_model"] == "IANA_TZ_DATABASE"


def test_outcome_fields_cannot_enter_market_context():
    artifact = build_historical_artifact(_bars(), source="FIXTURE")
    artifact.provenance["final_balance"] = 123  # input is not accepted by the label builder
    with pytest.raises(LeakageViolation):
        build_window_context(artifact)


def test_read_request_and_process_gate_never_start_mt5():
    request = build_readonly_mt5_request(
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        data_root="D0E8209F77C8CF37AD8BF550E51FF075",
        windows=PRODUCTION_WINDOWS,
    )
    assert request["requires_human_authorization_before_terminal_start"] is True
    assert terminal_read_gate(terminal_path=request["terminal_path"])["terminal_start_performed"] is False
    blocked = terminal_read_gate(terminal_path=request["terminal_path"], running_processes=[{"pid": 123}])
    assert blocked["status"] == "HUMAN_ACTION_REQUIRED_CLOSE_USER_MT5"
