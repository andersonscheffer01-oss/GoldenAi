from datetime import datetime, timezone
import copy

import pytest

from jarvis_core.tester_materialization_preflight import (
    DATA_ROOT_TARGET, TERMINAL_TARGET,
    _render, _safe_relative, build_approval_scope,
    build_execution_preflight_receipt, build_materialization_plan,
)


NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def _plan():
    return build_materialization_plan(clock=lambda: NOW)


def test_all_16_runs_materialize_deterministically_without_provider_calls():
    first, second = _plan(), _plan()
    assert first["materialization_plan_fingerprint"] == second["materialization_plan_fingerprint"]
    assert first["campaign_manifest_hash"] == "0df8521de44446de48141eb59b8ca884baca7fe483407239c4a952c2a25d7f0f"
    assert first["manifest_changed"] is False
    assert len(first["planned_runs"]) == 16
    assert len(first["materialized_config_fingerprints"]) == 16
    assert len(first["output_routing_fingerprints"]) == 16
    assert len({r["materialized_config_fingerprint"] for r in first["planned_runs"]}) == 16
    assert len({r["output_routing_fingerprint"] for r in first["planned_runs"]}) == 16
    assert first["provider_calls"] == {"tester": 0, "market": 0, "model": 0, "mt5_launch": 0}
    assert first["execution_authorized"] is False


def test_robot_specific_contract_and_config_byte_format_are_fixed():
    plan = _plan()
    assert plan["encoding"] == "UTF-8" and plan["bom"] is False
    assert plan["line_endings"] == "LF" and plan["final_newline"] is True
    canal, trend = plan["planned_runs"][0], plan["planned_runs"][8]
    assert (canal["robot_id"], canal["timeframe"]) == ("EA_Canal_Pullback_MT5", "M1")
    assert (trend["robot_id"], trend["timeframe"]) == ("Robo_Tendencia_MA9_21_50_Volume", "M15")
    assert canal["parameter_fingerprint"] != trend["parameter_fingerprint"]
    assert "compile-time defaults" in plan["parameter_serialization"].lower()
    assert "ExpertParameters=Setup_8_Robusto_Base.set" in _render(canal, plan["campaign_id"])
    assert "ExpertParameters=" not in _render(trend, plan["campaign_id"])


def test_fingerprints_have_distinct_operational_and_scientific_meanings():
    plan = _plan()
    run = plan["planned_runs"][0]
    assert run["scientific_config_fingerprint"] != run["materialized_config_fingerprint"]
    assert run["ini_scientific_config_fingerprint"] != run["output_routing_fingerprint"]
    assert "campaign_id" in plan["planned_runs"][0]


def test_output_ownership_is_unique_windows_casefolded_and_never_overwritten():
    plan = _plan()
    paths = [p["report_relative_path"].casefold() for p in plan["output_routing_fingerprints"]]
    paths += [p["result_relative_path"].casefold() for p in plan["output_routing_fingerprints"]]
    assert len(paths) == len(set(paths)) == 32
    assert plan["overwrite_allowed"] is False
    assert plan["stale_output_policy"].startswith("BLOCK_IF_EXPECTED")
    for bad in ("..\\escape.htm", "C:\\outside.htm", "Tester\\CON\\x.htm", "Tester\\bad?.htm"):
        with pytest.raises(ValueError, match="UNSAFE_OUTPUT_PATH"):
            _safe_relative(bad)


def test_cross_robot_timeframe_and_parameter_tampering_fail_closed():
    plan = _plan()
    run = plan["planned_runs"][0]
    swapped = {**run, "robot_id": "Robo_Tendencia_MA9_21_50_Volume"}
    with pytest.raises(ValueError, match="ROBOT_TIMEFRAME_MISMATCH"):
        _render(swapped, plan["campaign_id"])
    assert run["compiled_hash"] != plan["planned_runs"][8]["compiled_hash"]
    assert run["parameter_fingerprint"] != plan["planned_runs"][8]["parameter_fingerprint"]
    changed = {**run, "window": {"from": "2026-11-03", "to": "2026-11-06"}}
    assert _render(changed, plan["campaign_id"]) != _render(run, plan["campaign_id"])


def test_preflight_receipt_is_non_authorizing_and_fails_closed_on_stale_or_unknown_process():
    plan = _plan()
    run = plan["planned_runs"][0]
    receipt = build_execution_preflight_receipt(
        plan, run["test_run_id"], {"compiled_hash": run["compiled_hash"],
        "parameter_fingerprint": run["parameter_fingerprint"],
        "preset_sha256": run["parameter_artifact_contract"]["preset_sha256"],
        "defaults_source_hash": run["source_hash"],
        "scientific_config_fingerprint": run["scientific_config_fingerprint"],
        "materialized_config_fingerprint": run["materialized_config_fingerprint"],
        "output_routing_fingerprint": run["output_routing_fingerprint"],
        "market_window_fingerprint": run["market_window_fingerprint"],
        "context_status": "CONTEXT_READY", "stale_outputs_present": False,
        "user_mt5_process": "CLEAR", "terminal_path": TERMINAL_TARGET, "data_root": DATA_ROOT_TARGET,
        "security_approval_valid": True}, evaluated_at=datetime(2026, 11, 7, tzinfo=timezone.utc))
    assert receipt["checks"]["window_complete"] is True
    assert receipt["status"] == "PREFLIGHT_READY"
    assert receipt["authorizes_execution"] is False
    blocked = build_execution_preflight_receipt(
        plan, run["test_run_id"], {"stale_outputs_present": True,
        "user_mt5_process": "UNKNOWN"}, evaluated_at=datetime(2026, 11, 7, tzinfo=timezone.utc))
    assert blocked["status"] == "PREFLIGHT_BLOCKED"
    assert blocked["checks"]["stale_outputs_absent"] is False
    assert blocked["checks"]["terminal_process_clear"] is False
    swapped = {"compiled_hash": plan["planned_runs"][8]["compiled_hash"],
               "parameter_fingerprint": plan["planned_runs"][8]["parameter_fingerprint"]}
    cross = build_execution_preflight_receipt(
        plan, run["test_run_id"], swapped, evaluated_at=datetime(2026, 11, 7, tzinfo=timezone.utc))
    assert cross["checks"]["compiled_artifact"] is False
    assert cross["checks"]["parameters"] is False
    tampered_plan = copy.deepcopy(plan)
    tampered_plan["planned_runs"][0]["materialized_config_fingerprint"] = "tampered"
    with pytest.raises(ValueError, match="MATERIALIZATION_PLAN_INTEGRITY_MISMATCH"):
        build_execution_preflight_receipt(tampered_plan, run["test_run_id"], {},
                                          evaluated_at=datetime(2026, 11, 7, tzinfo=timezone.utc))


def test_routing_only_change_keeps_ini_science_but_changes_materialized_and_route_hashes():
    from jarvis_core.tester_config_reconciliation import (
        materialize_config, materialized_config_fingerprint,
        output_routing_fingerprint, scientific_config_fingerprint,
    )
    plan = _plan()
    run = plan["planned_runs"][0]
    original = _render(run, plan["campaign_id"])
    expected = materialize_config(original, plan["campaign_id"], run["test_run_id"])
    changed = expected.replace("Tester\\Jarvis\\" + run["test_run_id"] + ".htm",
                               "Tester\\Jarvis\\run_" + "f" * 32 + ".htm")
    assert scientific_config_fingerprint(expected) == scientific_config_fingerprint(changed)
    assert materialized_config_fingerprint(expected) != materialized_config_fingerprint(changed)
    assert output_routing_fingerprint(expected) != output_routing_fingerprint(changed)


def test_approval_scope_is_one_window_development_only_and_single_use():
    plan = _plan()
    window_runs = [r for r in plan["planned_runs"] if r["split"] == "DEVELOPMENT" and
                   r["window"] == plan["planned_runs"][0]["window"]]
    scope = build_approval_scope(plan, window_runs, expires_at="2026-11-08T00:00:00+00:00")
    assert len(scope["runs"]) == 2
    assert scope["single_use"] is True and scope["approval_created"] is False
    with pytest.raises(ValueError, match="RUN_SET_MISMATCH"):
        build_approval_scope(plan, [window_runs[0]], expires_at="later")
    with pytest.raises(ValueError, match="DEVELOPMENT_ONLY"):
        build_approval_scope(plan, [plan["planned_runs"][12]], expires_at="later")
