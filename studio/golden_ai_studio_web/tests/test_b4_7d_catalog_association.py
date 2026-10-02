import json
from pathlib import Path

from jarvis_core.production_catalog_association import build_production_association_plan
from jarvis_core.robot_artifact_identity import load_production_artifact_identity
from jarvis_core.robot_catalog import RobotCatalogReadModel


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "tester_campaigns" / "campaign_073cebd5e7df446fa9c85bae75ffbe0a"


def test_production_association_is_idempotent_and_preserves_fixture(tmp_path):
    catalog = RobotCatalogReadModel(storage_path=tmp_path / "robot_catalog.db")
    fixture_source = {"artifact_id": "fixture-source", "kind": "SOURCE", "sha256": "fixture-source-hash"}
    fixture_compiled = {"artifact_id": "fixture-compiled", "kind": "COMPILED", "sha256": "fixture-compiled-hash"}
    catalog.register_test_fixture("fixture_golden_strategy_tester_v1", "GoldenStrategyTesterFixture", "1.01",
                                   fixture_source, fixture_compiled)
    before = catalog.detail("fixture_golden_strategy_tester_v1")["robot"]
    identity = load_production_artifact_identity()
    plan = build_production_association_plan(
        identity, catalog.snapshot(),
        evidence_root=CAMPAIGN / "evidence",
        context_root=CAMPAIGN / "market_evidence" / "b4_7_reconciled",
    )
    assert plan["dry_run_status"] == "SAFE_TO_APPLY"
    assert len(plan["test_runs"]) == 3
    assert len(plan["temporal_contexts"]) == 3
    assert not plan["identity_collisions"]
    assert not plan["fixture_collisions"]
    first = catalog.associate_production_evidence(plan)
    assert first["ok"] is True
    after_first = catalog.detail("fixture_golden_strategy_tester_v1")["robot"]
    assert after_first == before
    catalog.close()

    reloaded = RobotCatalogReadModel(storage_path=tmp_path / "robot_catalog.db")
    production = reloaded.detail("EA_Canal_Pullback_MT5")["robot"]
    assert production["classification"] == "PRODUCTION_ROBOT"
    assert production["status"] == "DISCOVERED"
    assert len(production["compiled_artifacts"]) == 2
    assert {item["sha256"] for item in production["compiled_artifacts"]} == {
        identity["compiled_artifacts"]["historical_tested"]["sha256"],
        identity["compiled_artifacts"]["current_observed"]["sha256"],
    }
    assert len(production["campaign_associations"]) == 1
    assert len(production["test_runs"]) == 3
    assert len(production["temporal_contexts"]) == 3
    assert {item["compiled_hash"] for item in production["test_runs"]} == {
        identity["compiled_artifacts"]["historical_tested"]["sha256"]
    }
    assert all(item["current_artifact_inherits_results"] is False for item in production["test_runs"])

    second_plan = build_production_association_plan(
        identity, reloaded.snapshot(),
        evidence_root=CAMPAIGN / "evidence",
        context_root=CAMPAIGN / "market_evidence" / "b4_7_reconciled",
    )
    assert second_plan["dry_run_status"] == "SAFE_TO_APPLY"
    assert second_plan["objects_to_create"]["robot"] == []
    assert second_plan["objects_to_create"]["compiled_artifacts"] == []
    assert second_plan["objects_to_create"]["campaigns"] == []
    assert second_plan["objects_to_create"]["runs"] == []
    assert second_plan["objects_to_create"]["contexts"] == []
    assert second_plan["relationships_to_create"] == []
    second = reloaded.associate_production_evidence(second_plan)
    assert second["ok"] is True
    final = reloaded.detail("EA_Canal_Pullback_MT5")["robot"]
    assert len(final["compiled_artifacts"]) == 2
    assert len(final["campaign_associations"]) == 1
    assert len(final["test_runs"]) == 3
    assert len(final["temporal_contexts"]) == 3
    assert reloaded.detail("fixture_golden_strategy_tester_v1")["robot"] == before
    reloaded.close()
