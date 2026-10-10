import json
from pathlib import Path

from jarvis_core.mql5_evidence import (
    EffectiveParameterSet,
    GoldenTestRunManifest,
    TestRunIdentity,
    TesterConfiguration,
    parameter_fingerprint,
)
from jarvis_core.strategy_tester_adapter import (
    StrategyTesterAdapter,
    discover_environment,
    manifest_from_dict,
)
from jarvis_core.robot_catalog import RobotCatalogReadModel


def _manifest(robot_id="robot_demo"):
    values = {"risk": 0.5}
    identity = TestRunIdentity.create(
        robot_id, robot_version="1.0", source_artifact_id="source-1",
        source_hash="source-hash", parameter_fingerprint_value=parameter_fingerprint(values),
    )
    return GoldenTestRunManifest.create(
        identity, TesterConfiguration(symbol="XAUUSD", timeframe="M15", tester_model="OHLC"),
        EffectiveParameterSet.create(values, "USER_DEFINED"),
    )


def _environment(tmp_path):
    install = tmp_path / "mt5"
    data_parent = tmp_path / "data"
    data = data_parent / "instance"
    install.mkdir(parents=True)
    (install / "terminal64.exe").write_bytes(b"terminal-test-double")
    (data / "MQL5" / "Experts").mkdir(parents=True)
    (data / "MQL5" / "Experts" / "Fixture.ex5").write_bytes(b"compiled-fixture")
    (data / "MQL5" / "Files").mkdir(parents=True)
    return discover_environment([install], data_parent, data), data


def test_discovery_is_read_only_and_requires_explicit_data_root(tmp_path):
    install = tmp_path / "mt5"
    data_parent = tmp_path / "data"
    install.mkdir(parents=True)
    (install / "terminal64.exe").write_bytes(b"terminal")
    for name in ("one", "two"):
        (data_parent / name / "MQL5").mkdir(parents=True)
    environment = discover_environment([install], data_parent)
    assert environment.ambiguity == "MULTIPLE_DATA_ROOTS"
    assert not (tmp_path / "tester_runs").exists()


def test_manifest_round_trip_rejects_hash_mutation():
    manifest = _manifest()
    assert manifest_from_dict(manifest.to_dict()).manifest_hash == manifest.manifest_hash
    mutated = manifest.to_dict()
    mutated["tester"]["symbol"] = "EURUSD"
    try:
        manifest_from_dict(mutated)
    except ValueError as exc:
        assert str(exc) == "MANIFEST_HASH_MISMATCH"
    else:
        raise AssertionError("mutated manifest was accepted")


def test_config_is_local_only_and_never_contains_credentials(tmp_path):
    environment, _ = _environment(tmp_path)
    artifact = StrategyTesterAdapter().build_config(
        _manifest(), environment, "Fixture.ex5", run_root=tmp_path / "run",
    )
    assert "Optimization=0" in artifact.content
    assert "UseRemote=0" in artifact.content
    assert "UseCloud=0" in artifact.content
    assert "AllowLiveTrading=0" in artifact.content
    assert "Password" not in artifact.content
    assert "terminal-test-double" not in artifact.content
    assert Path(artifact.path).is_file()


def test_human_gate_does_not_start_process(tmp_path):
    environment, _ = _environment(tmp_path)
    calls = []

    def process_factory(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("process must not start before human gate")

    result = StrategyTesterAdapter(process_factory=process_factory).run(
        _manifest(), environment, "Fixture.ex5", managed_root=tmp_path / "runs",
    )
    assert result["status"] == "HUMAN_ACTION_REQUIRED"
    assert result["gate"]["WAITING_FOR_USER:"] == "YES"
    assert calls == []


def test_single_controlled_run_reconciles_result_and_is_bounded(tmp_path):
    environment, _ = _environment(tmp_path)
    manifest = _manifest()
    run_root = tmp_path / "runs" / manifest.identity.test_run_id
    run_root.mkdir(parents=True)

    class CompletedProcess:
        returncode = 0

        def poll(self):
            return 0

        def terminate(self):
            raise AssertionError("completed process must not be terminated")

        def wait(self, timeout=None):
            return 0

    calls = []

    def process_factory(command, **kwargs):
        calls.append((command, kwargs))
        (run_root / "result.json").write_text(json.dumps({
            "test_run_id": manifest.identity.test_run_id,
            "robot_id": manifest.identity.robot_id,
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "parameters": {"risk": 0.5},
            "stats": {"total_pnl": 1.0, "bars": 10, "ticks": 20},
        }), encoding="utf-8")
        return CompletedProcess()

    result = StrategyTesterAdapter(process_factory=process_factory).run(
        manifest, environment, "Fixture.ex5", managed_root=tmp_path / "runs",
        human_action_confirmed=True, timeout_seconds=10,
        result_json_path=run_root / "result.json",
    )
    assert result["ok"] is True
    assert result["status"] == "COMPLETED"
    assert len(calls) == 1
    assert calls[0][0][0] == environment.terminal_path
    assert "Optimization=0" in Path(result["config"]["path"]).read_text(encoding="utf-8")


def test_missing_fixture_and_result_fail_closed(tmp_path):
    environment, _ = _environment(tmp_path)
    adapter = StrategyTesterAdapter()
    try:
        adapter.build_config(_manifest(), environment, "Missing.ex5", run_root=tmp_path / "run")
    except ValueError as exc:
        assert str(exc) == "COMPILED_EA_REQUIRED"
    else:
        raise AssertionError("missing fixture was accepted")

    class CompletedProcess:
        returncode = 0

        def poll(self):
            return 0

    result = StrategyTesterAdapter(process_factory=lambda *args, **kwargs: CompletedProcess()).run(
        _manifest(), environment, "Fixture.ex5", managed_root=tmp_path / "runs",
        human_action_confirmed=True, timeout_seconds=10,
    )
    assert result["status"] == "FAILED"
    assert result["result"]["error"] == "RESULT_JSON_REQUIRED"


def test_timeout_and_crash_are_bounded_failures(tmp_path):
    environment, _ = _environment(tmp_path)

    class StuckProcess:
        returncode = -15

        def poll(self):
            return None

        def terminate(self):
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

    timeout_result = StrategyTesterAdapter(
        process_factory=lambda *args, **kwargs: StuckProcess(), poll_interval=0.05,
    ).run(_manifest(), environment, "Fixture.ex5", managed_root=tmp_path / "timeout",
          human_action_confirmed=True, timeout_seconds=1)
    assert timeout_result["status"] == "CANCELLED"
    assert timeout_result["timed_out"] is True

    class CrashedProcess:
        returncode = 7

        def poll(self):
            return self.returncode

    crash_result = StrategyTesterAdapter(
        process_factory=lambda *args, **kwargs: CrashedProcess(),
    ).run(_manifest(), environment, "Fixture.ex5", managed_root=tmp_path / "crash",
          human_action_confirmed=True, timeout_seconds=10)
    assert crash_result["status"] == "FAILED"
    assert crash_result["exit_code"] == 7


def test_reconciled_run_persists_in_existing_catalog_store(tmp_path):
    source_root = tmp_path / "catalog-root"
    source_root.mkdir()
    (source_root / "Robot.mq5").write_text("#property version \\\"1.0\\\"\nvoid OnTick() {}\n", encoding="utf-8")
    catalog = RobotCatalogReadModel(approved_roots=[source_root], storage_path=tmp_path / "robot_catalog.db")
    robot_id = catalog.discover()["robots"][0]["robot_id"]
    environment, _ = _environment(tmp_path)
    manifest = _manifest(robot_id)
    run_root = tmp_path / "catalog-runs" / manifest.identity.test_run_id
    run_root.mkdir(parents=True)

    class CompletedProcess:
        returncode = 0

        def poll(self):
            return 0

    def process_factory(*args, **kwargs):
        (run_root / "result.json").write_text(json.dumps({
            "test_run_id": manifest.identity.test_run_id,
            "robot_id": robot_id,
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "parameters": {"risk": 0.5},
            "stats": {"bars": 10, "ticks": 20},
        }), encoding="utf-8")
        return CompletedProcess()

    result = StrategyTesterAdapter(
        catalog=catalog, process_factory=process_factory,
    ).run(manifest, environment, "Fixture.ex5", managed_root=tmp_path / "catalog-runs",
          human_action_confirmed=True, timeout_seconds=10,
          result_json_path=run_root / "result.json")
    assert result["status"] == "COMPLETED"
    detail = catalog.detail(robot_id)["robot"]
    assert detail["test_run_count"] == 1
    assert detail["latest_test_status"] == "COMPLETED"
    catalog.close()
