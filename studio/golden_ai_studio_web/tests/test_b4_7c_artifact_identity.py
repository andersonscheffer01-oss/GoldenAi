import json

from jarvis_core.robot_artifact_identity import (
    HISTORICAL_COMPILED_HASH,
    HISTORICAL_SOURCE_HASH,
    classify_artifact_identity,
    reconcile_artifact_identity,
)


def test_identity_classification_distinguishes_source_and_compiled_versions():
    assert classify_artifact_identity(
        historical_source_hash="s", current_source_hash="s",
        historical_compiled_hash="c", current_compiled_hash="c",
    )["compiled_identity_status"] == "SOURCE_SAME_COMPILED_SAME"
    assert classify_artifact_identity(
        historical_source_hash="s", current_source_hash="s",
        historical_compiled_hash="c1", current_compiled_hash="c2",
    )["compiled_identity_status"] == "SOURCE_SAME_COMPILED_DIFFERENT"
    assert classify_artifact_identity(
        historical_source_hash="s1", current_source_hash="s2",
        historical_compiled_hash="c1", current_compiled_hash="c2",
    )["compiled_identity_status"] == "SOURCE_DIFFERENT_COMPILED_DIFFERENT"


def test_reconciliation_keeps_historical_evidence_bound_to_historical_binary(tmp_path):
    source = tmp_path / "EA_Canal_Pullback_MT5.mq5"
    current = tmp_path / "current.ex5"
    historical = tmp_path / "historical.ex5"
    source.write_bytes(b"source")
    current.write_bytes(b"current")
    historical.write_bytes(b"historical")
    import hashlib
    source_hash = hashlib.sha256(b"source").hexdigest()
    current_hash = hashlib.sha256(b"current").hexdigest()
    historical_hash = hashlib.sha256(b"historical").hexdigest()
    manifest = tmp_path / "campaign_manifest.json"
    manifest.write_text(json.dumps({
        "campaign_id": "campaign-test",
        "robot": {"robot_id": "EA_Canal_Pullback_MT5", "version": "1", "classification": "PRODUCTION_ROBOT",
                   "source_hash": source_hash, "compiled_hash": historical_hash,
                   "source_compiled_relationship": "STRONG"},
        "compile_evidence": {"status": "COMPILE_SUCCESS", "compiler": "MetaEditor", "compiler_version": "NOT_PRESENT"},
    }), encoding="utf-8")
    evidence = tmp_path / "run.native_log_evidence.json"
    evidence.write_text(json.dumps({"provider_outcome": {"normalized": {
        "robot_id": "EA_Canal_Pullback_MT5", "test_run_id": "run-test",
        "source_hash": source_hash, "compiled_hash": historical_hash,
        "parameter_fingerprint": "parameters-test",
    }}}), encoding="utf-8")
    result = reconcile_artifact_identity(
        manifest_path=manifest, source_path=source, current_compiled_path=current,
        historical_compiled_path=historical, evidence_paths=[evidence],
        catalog_robot_ids=["fixture_golden_strategy_tester_v1"],
    )
    assert result["compiled_artifacts"]["historical_tested"]["sha256"] == historical_hash
    assert result["compiled_artifacts"]["current_observed"]["sha256"] == current_hash
    assert result["compiled_artifacts"]["current_observed"]["historical_results_inherited"] is False
    assert result["test_execution_identity"]["bound_compiled_hash"] == historical_hash
    assert result["catalog"]["fixture_preserved"] is True
    assert result["catalog"]["database_mutated"] is False


def test_missing_historical_bytes_preserve_identity_without_recreation(tmp_path):
    source = tmp_path / "robot.mq5"
    current = tmp_path / "robot.ex5"
    source.write_bytes(b"source")
    current.write_bytes(b"current")
    manifest = tmp_path / "campaign_manifest.json"
    manifest.write_text(json.dumps({
        "campaign_id": "campaign-test",
        "robot": {"robot_id": "EA_Canal_Pullback_MT5", "source_hash": HISTORICAL_SOURCE_HASH,
                   "compiled_hash": HISTORICAL_COMPILED_HASH},
        "compile_evidence": {"status": "COMPILE_SUCCESS"},
    }), encoding="utf-8")
    result = reconcile_artifact_identity(
        manifest_path=manifest, source_path=source, current_compiled_path=current,
        historical_compiled_path=tmp_path / "missing.ex5",
    )
    assert result["historical_artifact_availability"] == "BYTES_NOT_CURRENTLY_AVAILABLE"
    assert result["compiled_artifacts"]["historical_tested"]["sha256"] == HISTORICAL_COMPILED_HASH
