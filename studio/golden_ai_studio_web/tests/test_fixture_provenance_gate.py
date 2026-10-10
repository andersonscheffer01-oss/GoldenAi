import json
from pathlib import Path

from jarvis_core.mql5_evidence import (
    EffectiveParameterSet,
    GoldenTestRunManifest,
    TestRunIdentity,
    TesterConfiguration,
    artifact_hash,
    parse_result_json,
    parse_set_parameters,
    reconcile_result,
)
from jarvis_core.strategy_tester_adapter import (
    StrategyTesterAdapter,
    StrategyTesterEnvironment,
)


CANONICAL_ID = "fixture_golden_strategy_tester_v1"
DISPLAY_NAME = "GoldenStrategyTesterFixture"


def _manifest(test_run_id="run_" + "a" * 32):
    values = {"deterministic_bars": 5}
    identity = TestRunIdentity.create(
        CANONICAL_ID, robot_version="1.01", source_artifact_id="source-1",
        compiled_artifact_id="compiled-1", source_hash="source-hash",
        compiled_hash="compiled-hash", parameter_fingerprint_value="",
        test_run_id=test_run_id,
    )
    return GoldenTestRunManifest.create(
        identity,
        TesterConfiguration(symbol="EURUSD", timeframe="M1", tester_model="OHLC"),
        EffectiveParameterSet.create(values, "USER_DEFINED"),
    )


def _result(manifest, *, fixture_id=CANONICAL_ID, robot_id=CANONICAL_ID,
            bars=10, ticks=20):
    return {
        "test_run_id": manifest.identity.test_run_id,
        "fixture_id": fixture_id,
        "robot_id": robot_id,
        "display_name": DISPLAY_NAME,
        "symbol": "EURUSD",
        "timeframe": "M1",
        "parameters": {"deterministic_bars": 5},
        "stats": {"bars": bars, "ticks": ticks, "total_trades": 0, "total_pnl": 0.0},
    }


def _environment(tmp_path):
    install = tmp_path / "install"
    data = tmp_path / "metaquotes" / "Terminal" / "D0"
    (install / "terminal64.exe").parent.mkdir(parents=True)
    (install / "terminal64.exe").write_bytes(b"terminal")
    (data / "MQL5" / "Experts").mkdir(parents=True)
    (data / "MQL5" / "Experts" / "Fixture.ex5").write_bytes(b"compiled")
    (data / "MQL5" / "Files").mkdir(parents=True)
    return StrategyTesterEnvironment(
        terminal_path=str(install / "terminal64.exe"),
        installation_path=str(install),
        selected_data_root=str(data),
    ), data


def test_canonical_fixture_identity_and_display_name_are_distinct(tmp_path):
    manifest = _manifest()
    path = tmp_path / "result.json"
    path.write_text(json.dumps(_result(manifest)), encoding="utf-8")
    result = parse_result_json(path)
    assert result.fixture_id == CANONICAL_ID
    assert result.robot_id == CANONICAL_ID
    assert result.display_name == DISPLAY_NAME
    assert result.display_name != result.fixture_id
    assert reconcile_result(manifest, result).status == "RECONCILED"


def test_preset_identity_propagation_is_structured():
    values = parse_set_parameters(
        "FixtureRunId=run_" + "a" * 32 + "\n"
        "FixtureId=fixture_golden_strategy_tester_v1\n"
        "FixtureDisplayName=GoldenStrategyTesterFixture\n"
        "DeterministicBars=5\n"
    )
    assert values["fixtureid"] == CANONICAL_ID
    assert values["fixturedisplayname"] == DISPLAY_NAME
    assert values["deterministicbars"] == 5


def test_wrong_fixture_id_and_wrong_run_id_reconcile_to_mismatch(tmp_path):
    manifest = _manifest()
    wrong_fixture = tmp_path / "wrong-fixture.json"
    wrong_fixture.write_text(json.dumps(_result(manifest, fixture_id="wrong_fixture")), encoding="utf-8")
    mismatch = reconcile_result(manifest, parse_result_json(wrong_fixture))
    assert mismatch.status == "MISMATCH"
    assert "fixture_id" in mismatch.mismatches

    wrong_run = tmp_path / "wrong-run.json"
    payload = _result(manifest)
    payload["test_run_id"] = "run_" + "b" * 32
    wrong_run.write_text(json.dumps(payload), encoding="utf-8")
    assert reconcile_result(manifest, parse_result_json(wrong_run)).status == "MISMATCH"


def test_agent_output_discovery_and_stale_protection(tmp_path):
    environment, data = _environment(tmp_path)
    manifest = _manifest()
    expected = data / "MQL5" / "Files" / "fixture-result.json"
    agent_result = (data.parents[1] / "Tester" / data.name / "Agent-127.0.0.1-3000" /
                    "MQL5" / "Files" / expected.name)
    agent_result.parent.mkdir(parents=True)
    agent_result.write_text(json.dumps(_result(manifest)), encoding="utf-8")
    adapter = StrategyTesterAdapter()
    assert adapter._discover_result_path(environment, expected) == agent_result.resolve()

    calls = []
    blocked = StrategyTesterAdapter(process_factory=lambda *args, **kwargs: calls.append(args)).run(
        manifest, environment, "Fixture.ex5", managed_root=tmp_path / "runs",
        human_action_confirmed=True, timeout_seconds=10, result_json_path=expected,
    )
    assert blocked["status"] == "EXECUTION_BLOCKED"
    assert blocked["error"] == "STALE_RESULT_ARTIFACT_PRESENT"
    assert calls == []


def test_zero_bars_or_ticks_are_invalid_evidence_and_positive_data_is_accepted(tmp_path):
    environment, _ = _environment(tmp_path)
    manifest = _manifest()
    adapter = StrategyTesterAdapter()
    for bars, ticks in ((0, 20), (10, 0)):
        path = tmp_path / f"invalid-{bars}-{ticks}.json"
        path.write_text(json.dumps(_result(manifest, bars=bars, ticks=ticks)), encoding="utf-8")
        checked = adapter._verify_result(manifest, path, allowed_roots=(tmp_path,))
        assert checked["status"] == "INVALID_EVIDENCE"
        assert checked["error"] == "NO_MARKET_DATA"

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_result(manifest, bars=10, ticks=20)), encoding="utf-8")
    checked = adapter._verify_result(manifest, valid, allowed_roots=(tmp_path,))
    assert checked["ok"] is True
    assert checked["status"] == "RECONCILED"


def test_result_artifact_hash_is_bound_to_the_discovered_json(tmp_path):
    manifest = _manifest()
    path = tmp_path / "result.json"
    path.write_text(json.dumps(_result(manifest)), encoding="utf-8")
    result = parse_result_json(path)
    assert result.artifact_hash == artifact_hash(path)
    assert result.artifact_id.endswith(result.artifact_hash[:24])
