import json
import os
import time
from dataclasses import replace
from pathlib import Path

from jarvis_core.tester_result_bridge import (
    FixtureJsonResultProvider,
    NativeTesterLogProvider,
    compare_results,
)
from jarvis_core.mql5_evidence import (
    EffectiveParameterSet,
    GoldenTestRunManifest,
    TestRunIdentity,
    TesterConfiguration,
)


def _plan(**overrides):
    plan = {
        "campaign_id": "campaign_test",
        "test_run_id": "run_" + "a" * 32,
        "robot_id": "EA_Canal_Pullback_MT5",
        "source_hash": "source-hash",
        "compiled_hash": "compiled-hash",
        "parameter_fingerprint": "parameter-fingerprint",
        "data_root": "",
        "expert_relative_path": "EA_Canal_Pullback_MT5\\EA_Canal_Pullback_MT5.ex5",
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "date_from": "2026.08.24",
        "date_to": "2026.08.28",
        "terminal_version": "5.0.0.6230",
        "config_hash": "config-hash",
        "started_at": "2026-09-30T10:00:00Z",
        "finished_at": "2026-09-30T10:05:00Z",
    }
    plan.update(overrides)
    return plan


def _log(plan, *, model="OHLC", include_metrics=True, duplicate=False):
    model_line = (
        "Tester EURUSD,M1: 1 minutes OHLC ticks generating"
        if model == "OHLC"
        else "Tester EURUSD,M1: every tick based on real ticks generating"
        if model == "REAL TICKS"
        else "Tester EURUSD,M1: localized model description"
    )
    metrics = """
Tester initial deposit 100000.00 USD
Tester final balance 100125.50 USD
Tester OnTester result 42.5
Tester XAUUSD,M1: 321 ticks, 87 bars generated
Tester quality of analyzed history is 100%
""" if include_metrics else ""
    block = f"""MetaTester 5 build 6230, 25 Sep 2026
{model_line}
Tester {plan['symbol']},{plan['timeframe']} (Broker): testing of Experts\\{plan['expert_relative_path']} from {plan['date_from']} 00:00 to {plan['date_to']} 00:00 started
{metrics}Tester test passed
"""
    return block + (block if duplicate else "")


def _provider_contract(tmp_path, **overrides):
    data_root = tmp_path / "data"
    plan = _plan(data_root=str(data_root), **overrides)
    return NativeTesterLogProvider(), plan, NativeTesterLogProvider().expected_contract(plan)


def _write_log(tmp_path, plan, *, name="20260930.log", **kwargs):
    log_dir = Path(plan["data_root"]) / "Tester" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / name
    path.write_text(_log(plan, **kwargs), encoding="utf-8")
    return path


def test_native_log_normalizes_metrics_and_retains_provenance(tmp_path):
    provider, plan, contract = _provider_contract(tmp_path)
    path = _write_log(tmp_path, plan)

    outcome = provider.read(path, contract, artifact_window=(time.time() - 5, time.time() + 5))

    assert outcome.status == "RECONCILED"
    assert outcome.normalized is not None
    normalized = outcome.normalized
    assert normalized.tester_model == "OHLC"
    assert normalized.metrics == {
        "initial_deposit": 100000.0,
        "final_balance": 100125.5,
        "on_tester": 42.5,
        "ticks": 321,
        "bars": 87,
        "history_quality": 100.0,
    }
    assert normalized.raw_metric_provenance["bars"].raw_field == "bars"
    assert normalized.raw_metric_provenance["bars"].raw_value == 87
    assert normalized.raw_metric_provenance["bars"].source_artifact == str(path)
    assert normalized.artifact_hash == outcome.artifact_hash
    assert normalized.normalized_artifact_fingerprint


def test_native_log_can_classify_real_ticks_and_unknown_model(tmp_path):
    provider, plan, contract = _provider_contract(tmp_path)
    real_ticks = _write_log(tmp_path, plan, name="real.log", model="REAL TICKS")
    assert provider.read(real_ticks, contract).normalized.tester_model == "REAL TICKS"

    unknown = _write_log(tmp_path, plan, name="unknown.log", model="UNKNOWN")
    outcome = provider.read(unknown, contract)
    assert outcome.status == "RECONCILED"
    assert outcome.normalized.tester_model == "UNKNOWN"
    assert "TESTER_MODEL_NOT_OBSERVED_IN_LOG" in outcome.normalized.limitations


def test_native_log_rejects_wrong_identity_and_path_escape(tmp_path):
    provider, plan, contract = _provider_contract(tmp_path)
    wrong = dict(plan, symbol="EURUSD")
    wrong_path = _write_log(tmp_path, wrong, name="wrong.log")
    assert provider.read(wrong_path, contract).status == "ARTIFACT_NOT_OWNED"

    outside = tmp_path / "outside.log"
    outside.write_text(_log(plan), encoding="utf-8")
    escaped = provider.read(outside, contract)
    assert escaped.status == "PATH_REJECTED"


def test_native_log_rejects_stale_oversized_and_ambiguous_artifacts(tmp_path):
    provider, plan, contract = _provider_contract(tmp_path)
    stale = _write_log(tmp_path, plan, name="stale.log")
    old = time.time() - 120
    os.utime(stale, (old, old))
    assert provider.read(stale, contract, artifact_window=(time.time() - 5, time.time() + 5)).status == "STALE_ARTIFACT"

    ambiguous = _write_log(tmp_path, plan, name="ambiguous.log", duplicate=True)
    assert provider.read(ambiguous, contract).status == "ARTIFACT_AMBIGUOUS"

def test_native_log_size_boundary_is_enforced(tmp_path):
    provider, plan, contract = _provider_contract(tmp_path)
    path = _write_log(tmp_path, plan)
    bounded = NativeTesterLogProvider(max_bytes=32)
    small_contract = bounded.expected_contract(plan)
    assert bounded.read(path, small_contract).status == "ARTIFACT_TOO_LARGE"


def test_fixture_provider_preserves_b44_contract_and_reconciles(tmp_path):
    identity = TestRunIdentity.create(
        "fixture_golden_strategy_tester_v1", robot_version="1.01",
        source_artifact_id="source-1", compiled_artifact_id="compiled-1",
        source_hash="source-hash", compiled_hash="compiled-hash",
        parameter_fingerprint_value="", test_run_id="run_" + "b" * 32,
    )
    manifest = GoldenTestRunManifest.create(
        identity,
        TesterConfiguration(symbol="EURUSD", timeframe="M1", tester_model="OHLC"),
        EffectiveParameterSet.create({"deterministic_bars": 5}, "USER_DEFINED"),
    )
    path = tmp_path / "fixture-result.json"
    path.write_text(json.dumps({
        "test_run_id": identity.test_run_id,
        "fixture_id": identity.robot_id,
        "robot_id": identity.robot_id,
        "display_name": "GoldenStrategyTesterFixture",
        "symbol": "EURUSD",
        "timeframe": "M1",
        "parameters": {"deterministic_bars": 5},
        "stats": {"bars": 10, "ticks": 20, "total_trades": 0, "total_pnl": 0.0},
    }), encoding="utf-8")

    outcome = FixtureJsonResultProvider().read(path, manifest, campaign_id="campaign_fixture")

    assert outcome.status == "RECONCILED"
    assert outcome.normalized.artifact_kind == "EA_CUSTOM_ARTIFACT"
    assert outcome.normalized.metrics["bars"] == 10
    assert outcome.normalized.raw_metric_provenance["ticks"].provider == "FixtureJsonResultProvider"


def test_provider_comparison_classifies_match_partial_conflict_and_incomparable(tmp_path):
    provider, plan, contract = _provider_contract(tmp_path)
    native_path = _write_log(tmp_path, plan)
    native = provider.read(native_path, contract).normalized
    assert compare_results(native, native) == "MATCH"
    partial = replace(native, metrics={"bars": native.metrics["bars"]})
    conflict = replace(native, metrics={"bars": native.metrics["bars"] + 1})
    incomparable = replace(native, metrics={"total_trades": 0})
    assert compare_results(native, partial) == "PARTIAL_MATCH"
    assert compare_results(native, conflict) == "CONFLICT"
    assert compare_results(native, incomparable) == "NOT_COMPARABLE"


def test_campaign_plans_build_native_contracts_without_execution(tmp_path):
    campaign = Path(__file__).parents[1] / "tester_campaigns" / "campaign_073cebd5e7df446fa9c85bae75ffbe0a"
    provider = NativeTesterLogProvider()
    plans = sorted((campaign / "plans").glob("*.json"))
    assert len(plans) == 3
    for plan_path in plans:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["data_root"] = str(tmp_path / plan["test_run_id"] / "data")
        plan["terminal_version"] = "5.0.0.6230"
        contract = provider.expected_contract(plan)
        path = _write_log(tmp_path / plan["test_run_id"], plan, name=f"{plan['test_run_id']}.log")
        outcome = provider.read(path, contract)
        assert outcome.status == "RECONCILED"
        assert outcome.normalized.test_run_id == plan["test_run_id"]
        assert outcome.normalized.robot_id == plan["robot_id"]
        assert outcome.normalized.parameter_fingerprint == plan["parameter_fingerprint"]
