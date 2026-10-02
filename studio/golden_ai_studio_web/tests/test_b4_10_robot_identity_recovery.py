import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis_core.b2_contracts import content_fingerprint
from jarvis_core.robot_identity_recovery import (
    RECOVERY_PATH, PROPOSED_CAMPAIGN_PATH, classify_candidate_readiness,
    classify_compiled_artifacts, classify_parameter_evidence,
    classify_source_artifacts, load_robot_identity_recovery,
    materialize_proposed_run_config, scientific_run_config_fingerprint,
)
from jarvis_core.scientific_campaign_design import load_scientific_campaign


def _candidate(**overrides):
    value = {
        "source_artifacts": [{"sha256": "a" * 64}],
        "compiled_artifacts": [{"sha256": "b" * 64}],
        "source_compiled_relationship": "PARTIAL",
        "compile_evidence": {"status": "COMPILE_SUCCESS", "path_and_timestamp_correlated": True},
        "parameter_evidence": {"status": "DEFAULT_PARAMETERS_VERIFIED"},
        "symbol_scope": "XAUUSD", "timeframe_scope": "M15",
        "dependencies_status": "KNOWN", "identity_collision": False,
        "onTester_semantics": "NOT_DEFINED",
    }
    value.update(overrides)
    return value


def test_source_duplicate_classification_is_hash_based():
    assert classify_source_artifacts([{"sha256": "a"}, {"sha256": "a"}]) == "MULTIPLE_IDENTICAL_SOURCE_COPIES"
    assert classify_source_artifacts([{"sha256": "a"}, {"sha256": "b"}]) == "MULTIPLE_DIFFERENT_SOURCE_VERSIONS"
    assert classify_source_artifacts([{"sha256": "a"}, {"path": "copy.mq5"}]) == "SOURCE_IDENTITY_INCOMPLETE"
    assert classify_source_artifacts([]) == "SOURCE_MISSING"


def test_compiled_artifact_ambiguity_and_missing_are_fail_closed():
    assert classify_compiled_artifacts([{"sha256": "a"}, {"sha256": "b"}]) == "MULTIPLE_COMPILED_VERSIONS"
    assert classify_compiled_artifacts([{"sha256": "a"}, {"path": "copy.ex5"}]) == "COMPILED_PROVENANCE_AMBIGUOUS"
    assert classify_compiled_artifacts([]) == "COMPILED_ARTIFACT_MISSING"


@pytest.mark.parametrize("parameter_status", ["MULTIPLE_PARAMETER_SETS", "PARAMETERS_AMBIGUOUS", "PARAMETERS_UNAVAILABLE"])
def test_unresolved_parameter_set_blocks_readiness(parameter_status):
    candidate = _candidate(parameter_evidence={"status": parameter_status})
    assert classify_parameter_evidence(candidate) == parameter_status
    assert classify_candidate_readiness(candidate)["readiness"] != "READY_WITH_RESTRICTIONS"


def test_resolved_defaults_can_be_ready_with_documented_restrictions():
    result = classify_candidate_readiness(_candidate())
    assert result["readiness"] == "READY_WITH_RESTRICTIONS"
    assert "COMPILER_VERSION_NOT_RECORDED" in result["restrictions"]


def test_dependency_ambiguity_blocks_readiness():
    result = classify_candidate_readiness(_candidate(dependencies_status="UNKNOWN"))
    assert result["readiness"] == "NOT_READY"
    assert "DEPENDENCIES_UNKNOWN" in result["blockers"]


def test_ontester_semantics_are_descriptive_not_performance_authority():
    plain = classify_candidate_readiness(_candidate(onTester_semantics="NOT_DEFINED"))
    described = classify_candidate_readiness(_candidate(onTester_semantics="CUSTOM_NON_PNL_SEMANTICS"))
    assert plain == described


def test_performance_history_cannot_change_identity_readiness(tmp_path, monkeypatch):
    inventory = json.loads(RECOVERY_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "inventory.json"
    monkeypatch.setattr("jarvis_core.robot_identity_recovery.RECOVERY_PATH", path)
    path.write_text(json.dumps(inventory), encoding="utf-8")
    first = load_robot_identity_recovery()
    inventory["legacy_evidence"]["json_artifacts_audited"] = 999999
    inventory["legacy_evidence"]["forensic_performance_summary"] = {"profit": 123456}
    path.write_text(json.dumps(inventory), encoding="utf-8")
    second = load_robot_identity_recovery()
    assert [row["readiness"] for row in first["candidates"]] == [row["readiness"] for row in second["candidates"]]
    assert [row["blockers"] for row in first["candidates"]] == [row["blockers"] for row in second["candidates"]]


def test_campaign_is_versioned_and_b49_manifest_stays_unchanged():
    b49_path = Path(__file__).parents[1] / "jarvis_core" / "data" / "b4_9_scientific_campaign.json"
    b49_hash = content_fingerprint(json.loads(b49_path.read_text(encoding="utf-8")))
    recovery = load_robot_identity_recovery()
    proposed = json.loads(PROPOSED_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert b49_hash == "0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4"
    assert proposed["campaign_id"] != proposed["manifest"]["b4_9_parent"]["campaign_id"]
    assert recovery["campaign_impact"]["proposed_manifest_hash"] == content_fingerprint(proposed["manifest"])
    assert recovery["campaign_impact"]["proposed_status"] == "PROPOSED_NOT_AUTHORIZED"


def test_materialized_and_output_fingerprints_are_deterministic_and_isolated(tmp_path):
    proposal = json.loads(PROPOSED_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    run = dict(proposal["manifest"]["planned_runs"][0])
    template = "[Tester]\nReport=placeholder.htm\nSymbol=XAUUSD\nPeriod=M1\n"
    one = materialize_proposed_run_config(run, proposal["campaign_id"], template, tmp_path)
    repeat = materialize_proposed_run_config(run, proposal["campaign_id"], template, tmp_path)
    assert one == repeat
    assert "Tester\\Jarvis\\" + run["test_run_id"] + ".htm" in one["content"]
    other = dict(run, test_run_id="run_" + "f" * 32)
    different = materialize_proposed_run_config(other, proposal["campaign_id"], template, tmp_path)
    assert different["output_routing_fingerprint"] != one["output_routing_fingerprint"]


def test_scientific_config_fingerprint_binds_campaign_robot_and_semantics():
    proposal = json.loads(PROPOSED_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    campaign_id = proposal["campaign_id"]
    run = proposal["manifest"]["planned_runs"][0]
    first = scientific_run_config_fingerprint(run, campaign_id)
    assert first == scientific_run_config_fingerprint(run, campaign_id)
    changed = dict(run, timeframe="M15")
    assert first != scientific_run_config_fingerprint(changed, campaign_id)
    assert first != scientific_run_config_fingerprint(run, "campaign_" + "f" * 32)


def test_future_window_lifecycle_uses_injected_utc_clock_and_never_executes():
    before = load_scientific_campaign(now=datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc))
    during = load_scientific_campaign(now=datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc))
    after = load_scientific_campaign(now=datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc))
    assert before["planned_runs"][0]["window_lifecycle"] == "WINDOW_PRE_REGISTERED"
    assert during["planned_runs"][0]["window_lifecycle"] == "WINDOW_IN_PROGRESS"
    assert after["planned_runs"][0]["window_lifecycle"] == "WINDOW_COMPLETE_CONTEXT_PENDING"
    assert all(result["execution_ready"] is False for result in (before, during, after))
    assert any("CONTEXT" in item for item in after["execution_blockers"])
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        load_scientific_campaign(now=datetime(2026, 11, 2))


def test_holdout_remains_uninspected_in_both_campaigns():
    b49 = load_scientific_campaign()
    b410 = load_robot_identity_recovery()["campaign_impact"]["proposed_manifest"]
    assert b49["holdout_inspected"] is False
    assert b49["execution_ready"] is False
    assert all(run["split"] == "HOLDOUT" for run in b410["planned_runs"] if run["window"]["from"] >= "2027-01-04")
    assert all(run["materialized_config_fingerprint"] == "NOT_MATERIALIZED" for run in b410["planned_runs"])


def test_read_model_and_ui_expose_readiness_without_execution_controls():
    from jarvis_core.robot_intelligence import build_robot_intelligence_snapshot

    snapshot = build_robot_intelligence_snapshot({"data": {"robots": []}})
    assert snapshot["robot_identity_recovery"]["campaign_impact"]["proposed_status"] == "PROPOSED_NOT_AUTHORIZED"
    source = (Path(__file__).parents[1] / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "ROBOT IDENTITY READINESS" in source
    assert "B4.9 PRE-REGISTERED · NOT EXECUTABLE YET" in source
    assert "B4.10 SCIENTIFIC CAMPAIGN · PROPOSED · NOT AUTHORIZED" in source
    assert "NO EXECUTION CONTROLS" in source
    assert "RUN ALL" not in source
