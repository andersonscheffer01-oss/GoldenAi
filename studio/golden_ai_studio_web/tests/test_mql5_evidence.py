import inspect
import json
from pathlib import Path

from jarvis_core.mql5_evidence import (
    EffectiveParameterSet,
    GoldenTestRunManifest,
    StrategyTesterAdapterDesign,
    TestRunIdentity as RunIdentity,
    TesterConfiguration as TesterConfig,
    artifact_hash,
    normalize_parameters,
    parameter_fingerprint,
    parse_compile_log,
    parse_mql5_inputs,
    parse_result_json,
    parse_set_parameters,
    reconcile_result,
)
from jarvis_core.robot_catalog import RobotCatalogReadModel


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _source() -> str:
    return (
        '#property version "1.0"\n'
        'input double Risk = 0.5; // optimization candidate\n'
        'input ENUM_TIMEFRAMES Timeframe = PERIOD_M15;\n'
        'void OnTick() {}\n'
    )


def _manifest(robot_id="robot_demo"):
    identity = RunIdentity.create(robot_id, robot_version="1.0",
                                      source_artifact_id="source-1",
                                      source_hash="source-hash",
                                      parameter_fingerprint_value=parameter_fingerprint({"risk": 0.5}))
    parameters = EffectiveParameterSet.create({"Risk": 0.5}, "USER_DEFINED")
    tester = TesterConfig(symbol="XAUUSD", timeframe="M15", tester_model="OHLC")
    return GoldenTestRunManifest.create(identity, tester, parameters)


def test_single_canonical_skill_and_contracts_are_registered():
    skill = Path(r"C:\GoldenAI\.agents\skills\golden-mql5\SKILL.md")
    text = skill.read_text(encoding="utf-8")
    assert "name: golden-mql5" in text
    assert "single canonical Golden MQL5 skill" in text
    assert Path(__file__).parents[1].joinpath("jarvis_core", "mql5_evidence.py").exists()


def test_mql5_inputs_and_set_parameters_are_structured_and_fingerprinted():
    definitions = parse_mql5_inputs(_source(), source_artifact_id="source-1")
    assert [(item.name, item.type, item.default) for item in definitions] == [
        ("Risk", "double", 0.5), ("Timeframe", "ENUM_TIMEFRAMES", "PERIOD_M15")
    ]
    assert definitions[0].optimization_suitability == "EXPLICITLY_DOCUMENTED"
    values = parse_set_parameters("; comment\nRisk=0.5||0.1||2\n")
    assert values == {"risk": 0.5}
    assert parameter_fingerprint(values) == parameter_fingerprint({"Risk": 0.5})
    assert normalize_parameters({" B ": 2, "a": True}) == {"a": True, "b": 2}


def test_manifest_binds_identity_parameters_and_bounded_tester_plan(tmp_path):
    manifest = _manifest()
    assert manifest.manifest_hash
    assert manifest.identity.test_run_id.startswith("run_")
    plan = StrategyTesterAdapterDesign.plan(manifest, tmp_path)
    assert plan["execution_mode"] == "DESIGN_ONLY"
    assert plan["trade_authority"] == "NONE"
    assert plan["start"] == "NOT_IMPLEMENTED"
    assert not (tmp_path / manifest.identity.test_run_id).exists()


def test_compile_evidence_requires_actual_log_proof(tmp_path):
    success_log = tmp_path / "success.log"
    _write(success_log, "Result: 0 errors, 2 warnings\n")
    compiled = tmp_path / "robot.ex5"
    _write(compiled, b"compiled")
    success = parse_compile_log(success_log, "robot_demo", "source-1", "source-hash", compiled_path=compiled)
    assert success.status == "COMPILE_SUCCESS"
    assert success.errors == 0
    assert success.warnings == 2
    assert success.compiled_hash == artifact_hash(compiled)

    unknown_log = tmp_path / "unknown.log"
    _write(unknown_log, "MetaEditor output without result summary")
    unknown = parse_compile_log(unknown_log, "robot_demo", "source-1", "source-hash")
    assert unknown.status == "COMPILE_UNKNOWN"
    assert unknown.errors == "NOT_PRESENT"


def test_result_parser_and_reconciliation_keep_missing_data_explicit(tmp_path):
    result_path = tmp_path / "result.json"
    manifest = _manifest()
    _write(result_path, json.dumps({
        "test_run_id": manifest.identity.test_run_id,
        "robot_id": "robot_demo",
        "stats": {"symbol": "XAUUSD", "timeframe": "M15", "total_pnl": 12.0,
                   "profit_factor": 1.2},
    }))
    result = parse_result_json(result_path)
    assert result.test_run_id == manifest.identity.test_run_id
    assert result.metrics["total_pnl"] == 12.0
    assert "parameters" in result.missing_fields
    reconciled = reconcile_result(manifest, result)
    assert reconciled.status == "RECONCILED"
    assert reconcile_result(manifest, result, known_result_hashes=[result.artifact_hash]).status == "DUPLICATE_RESULT"
    assert reconcile_result(manifest, result, stale_run_ids=[manifest.identity.test_run_id]).status == "STALE_RUN"

    mismatch_path = tmp_path / "mismatch.json"
    _write(mismatch_path, json.dumps({"test_run_id": "other", "robot_id": "robot_demo"}))
    mismatch = reconcile_result(manifest, parse_result_json(mismatch_path))
    assert mismatch.status == "MISMATCH"


def test_catalog_persists_compile_and_test_evidence_without_execution(tmp_path):
    root = tmp_path / "approved"
    store = tmp_path / "catalog.db"
    _write(root / "Robot.mq5", _source())
    catalog = RobotCatalogReadModel(approved_roots=[root], storage_path=store)
    discovered = catalog.discover()
    robot_id = discovered["robots"][0]["robot_id"]
    compile_evidence = {"evidence_id": "compile-1", "robot_id": robot_id,
                        "status": "COMPILE_FAILED", "errors": 1, "warnings": 0}
    assert catalog.record_compile_evidence(robot_id, compile_evidence)["ok"] is True
    manifest = _manifest(robot_id)
    assert catalog.record_test_run(robot_id, manifest.to_dict())["ok"] is True
    catalog.close()

    reopened = RobotCatalogReadModel(approved_roots=[root], storage_path=store)
    reopened.discover()
    detail = reopened.detail(robot_id)["robot"]
    assert detail["compile_evidence_count"] == 1
    assert detail["test_run_count"] == 1
    assert detail["parameter_set_count"] == 1
    assert detail["latest_test_status"] == "PLANNED"
    reopened.close()


def test_contract_module_has_no_execution_or_live_trade_surface():
    from jarvis_core import mql5_evidence

    source = inspect.getsource(mql5_evidence).casefold()
    for forbidden in ("subprocess", "metatrader5", "order_send", "send_order", "terminal64"):
        assert forbidden not in source
