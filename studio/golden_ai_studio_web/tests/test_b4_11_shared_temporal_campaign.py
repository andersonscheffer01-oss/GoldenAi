from datetime import datetime, timezone

import pytest

from jarvis_core.shared_temporal_campaign import (
    _assert_no_outcomes,
    build_shared_temporal_preflight,
    market_window_identity,
    sample_identity,
    temporal_state,
    validate_run_binding,
)


def test_plan_preserves_campaign_and_builds_separate_technical_and_macro_windows():
    now = lambda: datetime(2026, 10, 2, tzinfo=timezone.utc)
    plan = build_shared_temporal_preflight(clock=now)
    assert plan["campaign_id"] == "campaign_bf3389bc66f0ac7777a3a06719ac5851"
    assert plan["campaign_manifest_hash"] == "0df8521de44446de48141eb59b8ca884baca7fe483407239c4a952c2a25d7f0f"
    assert plan["b4_9_manifest_hash"] == "0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4"
    assert plan["planned_run_count"] == 16
    assert len(plan["market_windows"]) == 16
    assert len(plan["macro_windows"]) == 8
    assert all(len(window["run_ids"]) == 2 for window in plan["macro_windows"])
    assert all(len(window["run_ids"]) == 1 for window in plan["market_windows"])
    assert len({item["test_run_id"] for item in plan["planned_runs"]}) == 16
    assert len({item["sample_fingerprint"] for item in plan["planned_runs"]}) == 16
    assert all(item["lifecycle"] == "NOT_EXECUTABLE_FUTURE_WINDOW" for item in plan["planned_runs"])
    assert plan["authorized"] is False
    assert plan["campaign_executable_now"] is False


def test_window_fingerprint_is_deterministic_and_timeframe_specific():
    plan = build_shared_temporal_preflight(clock=lambda: datetime(2026, 10, 2, tzinfo=timezone.utc))
    again = build_shared_temporal_preflight(clock=lambda: datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert plan["context_plan_fingerprint"] == again["context_plan_fingerprint"]
    first, second = plan["market_windows"][:1] + plan["market_windows"][8:9]
    assert first["start"] == second["start"] and first["end"] == second["end"]
    assert first["timeframe"] != second["timeframe"]
    assert first["window_fingerprint"] != second["window_fingerprint"]


def test_window_identity_changes_for_each_market_semantic_dimension():
    base = market_window_identity("XAUUSD", "M1", "2026-11-02", "2026-11-06", "UTC")
    assert base == market_window_identity("XAUUSD", "M1", "2026-11-02", "2026-11-06", "UTC")
    variants = [
        market_window_identity("EURUSD", "M1", "2026-11-02", "2026-11-06", "UTC"),
        market_window_identity("XAUUSD", "M5", "2026-11-02", "2026-11-06", "UTC"),
        market_window_identity("XAUUSD", "M1", "2026-11-03", "2026-11-06", "UTC"),
        market_window_identity("XAUUSD", "M1", "2026-11-02", "2026-11-07", "UTC"),
        market_window_identity("XAUUSD", "M1", "2026-11-02", "2026-11-06", "America/New_York"),
    ]
    assert all(item["window_fingerprint"] != base["window_fingerprint"] for item in variants)


def test_identical_market_truth_is_shared_but_run_and_sample_identities_stay_distinct():
    first = market_window_identity("XAUUSD", "M1", "2026-11-02", "2026-11-06")
    second = market_window_identity("XAUUSD", "M1", "2026-11-02", "2026-11-06")
    assert first == second
    sample_a = sample_identity("run_" + "a" * 32, "robot_a", "compiled_a", "params_a",
                               first["window_fingerprint"], "REAL_TICKS")
    sample_b = sample_identity("run_" + "b" * 32, "robot_b", "compiled_b", "params_b",
                               second["window_fingerprint"], "REAL_TICKS")
    assert sample_a != sample_b


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc), "NOT_EXECUTABLE_FUTURE_WINDOW"),
        (datetime(2026, 11, 2, tzinfo=timezone.utc), "NOT_EXECUTABLE_WINDOW_IN_PROGRESS"),
        (datetime(2026, 11, 7, tzinfo=timezone.utc), "TEMPORAL_WINDOW_COMPLETE"),
    ],
)
def test_injected_clock_temporal_gate(now, expected):
    assert temporal_state("2026-11-02", "2026-11-06", now) == expected


def test_run_binding_rejects_cross_robot_parameter_or_artifact_leakage():
    run = build_shared_temporal_preflight(
        clock=lambda: datetime(2026, 10, 2, tzinfo=timezone.utc)
    )["planned_runs"][0]
    expected = {key: run[key] for key in ("robot_id", "compiled_hash", "parameter_fingerprint", "symbol", "timeframe", "window")}
    validate_run_binding(run, **expected)
    for field in ("robot_id", "compiled_hash", "parameter_fingerprint", "timeframe"):
        wrong = dict(expected)
        wrong[field] = "wrong-identity"
        with pytest.raises(ValueError, match="RUN_BINDING_MISMATCH"):
            validate_run_binding(run, **wrong)


def test_campaign_manifest_does_not_create_authority_and_materialization_stays_pending():
    plan = build_shared_temporal_preflight(
        clock=lambda: datetime(2026, 10, 2, tzinfo=timezone.utc)
    )
    assert plan["state"] == "PROPOSED_NOT_AUTHORIZED"
    assert plan["execution_authorized"] is False
    assert plan["materialized_config_ready"] is False
    assert plan["materialized_config_status"] == "MATERIALIZED_CONFIG_PENDING_EXECUTION_PREFLIGHT"
    assert len(plan["scientific_config_fingerprints"]) == 16
    assert len(plan["output_routing_fingerprints"]) == 16
    assert all(item["status"] == "PLAN_ONLY_NOT_MATERIALIZED" for item in plan["output_routing_fingerprints"])


def test_outcome_fields_cannot_enter_context_plan_inputs():
    with pytest.raises(ValueError, match="OUTCOME_FEATURE_FORBIDDEN"):
        _assert_no_outcomes({"labels": {"profit": 12}})
