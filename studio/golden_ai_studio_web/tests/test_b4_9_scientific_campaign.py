import copy
import json
from pathlib import Path

import pytest

from jarvis_core.scientific_campaign_design import (
    MANIFEST_PATH, load_scientific_campaign, validate_campaign,
)
from jarvis_core.robot_intelligence import build_robot_intelligence_snapshot


def test_manifest_is_pre_registered_and_read_only():
    campaign = load_scientific_campaign()
    assert campaign["read_only"] is True
    assert campaign["planned_run_count"] == 8
    assert campaign["split_counts"] == {"DEVELOPMENT": 4, "VALIDATION": 2, "HOLDOUT": 2}
    assert campaign["holdout_inspected"] is False
    assert campaign["execution_ready"] is False
    assert len(campaign["manifest_hash"]) == 64
    assert campaign["safety"]["tester_executed"] is False


def test_run_ids_windows_and_artifact_identity_are_unique_and_frozen():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    runs = manifest["planned_runs"]
    assert len({run["test_run_id"] for run in runs}) == len(runs)
    assert len({(run["window"]["from"], run["window"]["to"]) for run in runs}) == len(runs)
    assert all(run["compiled_hash"] == manifest["robot"]["compiled_hash"] for run in runs)
    assert all(run["parameter_fingerprint"] == manifest["robot"]["parameter_fingerprint"] for run in runs)
    assert len({run["scientific_config_fingerprint"] for run in runs}) == len(runs)
    assert all(run["materialized_config_fingerprint"] == "NOT_MATERIALIZED" for run in runs)
    assert all(run["output_routing_fingerprint"] == "NOT_MATERIALIZED" for run in runs)
    assert validate_campaign(manifest)["valid"] is True


@pytest.mark.parametrize("mutate, expected", [
    (lambda value: value["planned_runs"][7].update(window={"from": "2026-11-16", "to": "2026-11-20"}), "WINDOW_ORDER_OR_DUPLICATE_INVALID"),
    (lambda value: value["planned_runs"][0].update(compiled_hash="0" * 64), "ARTIFACT_IDENTITY_MISMATCH"),
    (lambda value: value["planned_runs"][0].update(parameter_fingerprint="unknown"), "PARAMETER_IDENTITY_MISMATCH"),
    (lambda value: value["planned_runs"][0].update(final_balance=999), "OUTCOME_FIELD_FORBIDDEN"),
])
def test_invalid_or_leaky_campaign_fails_closed(mutate, expected):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = copy.deepcopy(manifest)
    mutate(manifest)
    with pytest.raises(ValueError, match=expected):
        validate_campaign(manifest)


def test_planner_is_exposed_through_existing_robot_read_model_only():
    snapshot = build_robot_intelligence_snapshot({"data": {"robots": []}})
    assert snapshot["scientific_campaign"]["campaign_id"] == "campaign_b49_xauusd_m1_temporal_01"
    assert snapshot["scientific_campaign"]["execution_ready"] is False
    source = (Path(__file__).parents[1] / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "SCIENTIFIC CAMPAIGN · PLANNING ONLY" in source
    assert "BACKTEST NOT EXECUTED" in source
    assert "RUN ALL" not in source
