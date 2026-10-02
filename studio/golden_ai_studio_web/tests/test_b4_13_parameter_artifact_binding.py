import copy
import json
from pathlib import Path

import pytest

from jarvis_core.campaign_parameter_provenance import (
    CANAL, TREND, EXPECTED, _canonical, _read_artifact,
    assert_run_parameter_binding, build_campaign_parameter_provenance,
)
from jarvis_core.robot_catalog import parameter_fingerprint
from jarvis_core.tester_materialization_preflight import build_materialization_plan
from jarvis_core.tester_materialization_preflight import (
    DATA_ROOT_TARGET, TERMINAL_TARGET, build_execution_preflight_receipt,
)
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def provenance():
    return build_campaign_parameter_provenance(ROOT)


def test_authoritative_parameter_fingerprints_and_schemas_reconcile(provenance):
    by_robot = {item["robot_id"]: item for item in provenance["robots"]}
    assert by_robot[CANAL]["parameter_fingerprint_recomputed"] == EXPECTED[CANAL]["parameter_fingerprint"]
    assert by_robot[TREND]["parameter_fingerprint_recomputed"] == EXPECTED[TREND]["parameter_fingerprint"]
    assert by_robot[CANAL]["schema_status"] == "COMPATIBLE_WITH_IMPLICIT_SOURCE_DEFAULTS"
    assert by_robot[CANAL]["effective_parameter_count"] == 156
    assert len(by_robot[CANAL]["missing_campaign_parameters"]) == 5
    assert by_robot[CANAL]["unknown_parameters"] == []
    assert by_robot[CANAL]["type_mismatches"] == []
    assert by_robot[TREND]["schema_status"] == "COMPATIBLE"
    assert by_robot[TREND]["input_count"] == 31
    assert by_robot[TREND]["campaign_overrides"] == []


def test_exact_compiled_hashes_are_selected_and_wrong_canal_project_copy_rejected(provenance):
    by_robot = {item["robot_id"]: item for item in provenance["robots"]}
    for robot_id in (CANAL, TREND):
        assert by_robot[robot_id]["compiled_status"] in {
            "AVAILABLE_EXACT", "AVAILABLE_MULTIPLE_COPIES_IDENTICAL"
        }
        assert by_robot[robot_id]["selected_compiled_sha256"] == EXPECTED[robot_id]["compiled_hash"]
    wrong = ROOT / "projetos/EA_Canal_Pullback_MT5/EA_Canal_Pullback_MT5.ex5"
    assert _read_artifact(wrong, EXPECTED[CANAL]["compiled_hash"])["status"] == "HASH_MISMATCH"
    assert by_robot[CANAL]["installed_compiled_status"] == "MATCH"
    assert by_robot[TREND]["installed_compiled_status"] == "NOT_INSTALLED_EXACT"
    assert by_robot[TREND]["runtime_install_status"] == "PROJECT_COPY_ONLY"


def test_parameter_artifacts_keep_exact_bytes_and_installed_canal_semantics(provenance):
    by_robot = {item["robot_id"]: item for item in provenance["robots"]}
    canal = by_robot[CANAL]
    assert canal["parameter_artifact"]["sha256"] == EXPECTED[CANAL]["project_preset_hash"]
    assert canal["installed_parameter_artifact_sha256"] == EXPECTED[CANAL]["installed_preset_hash"]
    assert canal["parameter_fingerprint_match"] is True
    assert canal["source_compiled_relationship"] == "STRONG_HISTORICAL_MANIFEST_AND_TEST_EVIDENCE"
    assert canal["historical_binding_evidence"]["binding_status"] == "VERIFIED"
    assert canal["historical_binding_evidence"]["sha256"] == EXPECTED[CANAL]["historical_manifest_hash"]
    assert canal["compile_evidence"]["status"] == "COMPILE_SUCCESS"
    assert canal["compile_evidence"]["compiled_hash_recorded_in_log"] is False
    trend = by_robot[TREND]
    assert trend["parameter_artifact"]["role"] == "SOURCE_DEFAULTS"
    assert trend["source_compiled_relationship"] == "PARTIAL_PATH_AND_TIMESTAMP_CORROBORATION"
    assert trend["historical_binding_evidence"]["binding_status"] == "VERIFIED_WITH_PARTIAL_LINK"
    assert trend["compile_evidence"]["status"] == "COMPILE_SUCCESS"
    assert trend["compile_evidence"]["compiled_hash_recorded_in_log"] is False


def test_canonical_typed_serialization_is_order_locale_and_roundtrip_stable():
    first = {"alpha": 1.0, "enabled": True, "method": "MODE_EMA"}
    second = {"method": "MODE_EMA", "enabled": True, "alpha": 1.0}
    a, b = _canonical(first), _canonical(second)
    assert a == b
    assert json.loads(a) == first
    assert _canonical(json.loads(a)) == a
    assert parameter_fingerprint(first) == parameter_fingerprint(second)
    changed = dict(first, alpha=1.25)
    assert parameter_fingerprint(changed) != parameter_fingerprint(first)


def test_campaign_binding_rejects_cross_robot_or_changed_artifact_and_parameters(provenance):
    by_robot = {item["robot_id"]: item for item in provenance["robots"]}
    plan = build_materialization_plan()
    canal_run = plan["planned_runs"][0]
    assert_run_parameter_binding(canal_run, by_robot[CANAL])
    with pytest.raises(ValueError, match="CROSS_ROBOT_PARAMETER_BINDING"):
        assert_run_parameter_binding(canal_run, by_robot[TREND])
    wrong_hash = copy.deepcopy(canal_run)
    wrong_hash["compiled_hash"] = by_robot[TREND]["compiled_expected_sha256"]
    with pytest.raises(ValueError, match="COMPILED_HASH_MISMATCH"):
        assert_run_parameter_binding(wrong_hash, by_robot[CANAL])
    wrong_fp = copy.deepcopy(canal_run)
    wrong_fp["parameter_fingerprint"] = "0" * 24
    with pytest.raises(ValueError, match="PARAMETER_FP_MISMATCH"):
        assert_run_parameter_binding(wrong_fp, by_robot[CANAL])


def test_all_sixteen_runs_bind_one_robot_specific_parameter_and_compiled_identity():
    plan = build_materialization_plan()
    assert len(plan["planned_runs"]) == 16
    for run in plan["planned_runs"]:
        contract = run["parameter_artifact_contract"]
        assert contract["parameter_fingerprint"] == run["parameter_fingerprint"]
        assert contract["effective_parameter_snapshot_sha256"]
        assert contract["compiled_artifact_status"] == "AVAILABLE_EXACT"
        assert contract["installed_compiled_path"].casefold().endswith(".ex5")
        if run["robot_id"] == CANAL:
            assert contract["preset_name"] == "Setup_8_Robusto_Base.set"
            assert contract["installed_parameter_artifact_sha256"] == EXPECTED[CANAL]["installed_preset_hash"]
        else:
            assert contract["preset_name"] is None
            assert contract["installed_compiled_status"] == "NOT_INSTALLED_EXACT"


def test_plan_binds_provenance_in_integrity_and_never_authorizes_execution():
    plan = build_materialization_plan()
    assert plan["parameter_provenance_status"] == "VERIFIED_WITH_RESTRICTIONS"
    assert plan["manifest_changed"] is False
    assert plan["execution_authorized"] is False
    assert plan["provider_calls"] == {"tester": 0, "market": 0, "model": 0, "mt5_launch": 0}
    assert plan["materialization_version"] == "jarvis-tester-config-materialization-v1"


def test_preflight_receipt_blocks_parameter_artifact_source_schema_and_binary_drift():
    plan = build_materialization_plan()
    run = plan["planned_runs"][0]
    contract = run["parameter_artifact_contract"]
    observations = {
        "compiled_hash": run["compiled_hash"], "source_hash": contract["source_sha256"],
        "robot_binding_evidence_sha256": contract["robot_binding_evidence_sha256"],
        "source_compiled_relationship": contract["source_compiled_relationship"],
        "parameter_fingerprint": run["parameter_fingerprint"],
        "preset_sha256": contract["preset_sha256"],
        "installed_parameter_artifact_sha256": contract["installed_parameter_artifact_sha256"],
        "parameter_source_sha256": contract["parameter_source_sha256"],
        "effective_parameter_snapshot_sha256": contract["effective_parameter_snapshot_sha256"],
        "effective_parameter_fingerprint": contract["effective_parameter_fingerprint"],
        "schema_status": contract["schema_status"],
        "parameter_drift_status": "NO_DRIFT_OBSERVED", "artifact_drift_status": "NO_DRIFT_OBSERVED",
        "installed_compiled_path": contract["installed_compiled_path"],
        "installed_compiled_status": contract["installed_compiled_status"],
        "scientific_config_fingerprint": run["scientific_config_fingerprint"],
        "materialized_config_fingerprint": run["materialized_config_fingerprint"],
        "output_routing_fingerprint": run["output_routing_fingerprint"],
        "market_window_fingerprint": run["market_window_fingerprint"],
        "context_status": "CONTEXT_READY", "stale_outputs_present": False,
        "user_mt5_process": "CLEAR", "terminal_path": TERMINAL_TARGET,
        "data_root": DATA_ROOT_TARGET, "security_approval_valid": True,
    }
    timestamp = datetime(2026, 11, 7, tzinfo=timezone.utc)
    original = build_execution_preflight_receipt(plan, run["test_run_id"], observations,
                                                 evaluated_at=timestamp)
    assert original["checks"]["parameter_source"] is True
    for field, value, check in (
        ("installed_parameter_artifact_sha256", "stale", "parameter_artifact"),
        ("source_hash", "stale", "source_artifact"),
        ("robot_binding_evidence_sha256", "stale", "campaign_parameter_binding"),
        ("effective_parameter_snapshot_sha256", "stale", "effective_parameter_snapshot"),
        ("schema_status", "MISMATCH", "input_schema"),
        ("parameter_drift_status", "DRIFT", "parameter_drift"),
        ("artifact_drift_status", "DRIFT", "compiled_artifact_binding"),
        ("installed_compiled_status", "HASH_MISMATCH", "compiled_artifact_binding"),
    ):
        changed = dict(observations, **{field: value})
        receipt = build_execution_preflight_receipt(plan, run["test_run_id"], changed,
                                                    evaluated_at=timestamp)
        assert receipt["checks"][check] is False
        assert receipt["authorizes_execution"] is False


def test_approval_scope_binds_parameter_artifact_snapshot_and_source_identity():
    from jarvis_core.tester_materialization_preflight import build_approval_scope
    plan = build_materialization_plan()
    runs = [r for r in plan["planned_runs"] if r["split"] == "DEVELOPMENT" and
            r["window"] == plan["planned_runs"][0]["window"]]
    scope = build_approval_scope(plan, runs, expires_at="2026-11-08T00:00:00+00:00")
    assert scope["approval_created"] is False
    assert all("effective_parameter_snapshot_sha256" in item["parameter_artifact_contract"]
               and "source_sha256" in item["parameter_artifact_contract"] for item in scope["runs"])
