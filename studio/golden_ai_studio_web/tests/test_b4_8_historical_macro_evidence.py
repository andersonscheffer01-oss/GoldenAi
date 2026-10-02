"""B4.8 point-in-time and no-outcome contracts."""
import json
from pathlib import Path

import pytest

from jarvis_core.historical_macro_evidence import (
    build_macro_context, build_production_macro_contexts, load_official_releases,
)
from jarvis_core.robot_intelligence import build_robot_intelligence_snapshot
from jarvis_core.temporal_market_context import LeakageViolation


def test_primary_releases_are_curated_and_time_normalized():
    releases, fingerprint = load_official_releases()
    assert len(releases) == 6
    assert len({item["event_id"] for item in releases}) == 6
    assert all(item["available_at"] == item["released_at_utc"] for item in releases)
    assert all(item["surprise"] == "UNKNOWN" and item["consensus"] is None for item in releases)
    assert all(item["raw_artifact_status"] != "PRESERVED" for item in releases)
    assert fingerprint


def test_ex_ante_excludes_releases_inside_each_window():
    contexts = build_production_macro_contexts()
    assert len(contexts) == 6
    by_key = {(item["window_id"], item["temporal_semantics"]): item for item in contexts}
    r1 = by_key["R1", "EX_ANTE_CONTEXT"]
    r2 = by_key["R2", "EX_ANTE_CONTEXT"]
    r3 = by_key["R3", "EX_ANTE_CONTEXT"]
    assert r1["dimensions"]["US_INFLATION"] == "UNKNOWN"
    assert r1["dimensions"]["US_MONETARY_POLICY"] == "KNOWN"
    assert r2["dimensions"]["US_INFLATION"] == "KNOWN"
    assert r2["dimensions"]["US_LABOR"] == "UNKNOWN"
    assert r3["dimensions"]["US_LABOR"] == "KNOWN"
    assert all(item["event_risk_state"] == "UNKNOWN" for item in (r1, r2, r3))
    assert all("BEA-2026-08-26-PCE-JULY" not in [event["event_id"] for event in item["evidence"]]
               for item in (r1,))


def test_descriptive_event_risk_is_release_based_not_outcome_based():
    contexts = build_production_macro_contexts()
    descriptive = [item for item in contexts if item["temporal_semantics"].startswith("POST_WINDOW")]
    assert [item["event_risk_state"] for item in descriptive] == ["HIGH", "HIGH", "HIGH"]
    assert [len(item["events_in_window"]) for item in descriptive] == [2, 1, 2]
    assert all(item["provenance_quality"] == "PARTIAL_RAW_SOURCE_BYTES_MISSING" for item in descriptive)
    assert descriptive[0]["context_fingerprint"] == build_production_macro_contexts()[1]["context_fingerprint"]


def test_future_cutoff_and_outcome_injection_fail_closed():
    releases, fingerprint = load_official_releases()
    with pytest.raises(LeakageViolation, match="CUTOFF_MUST_MATCH_SEMANTIC_BOUNDARY"):
        build_macro_context("R1", semantics="EX_ANTE_CONTEXT", releases=releases,
                            source_fingerprint=fingerprint, evaluation_time="2026-08-26T12:30:00Z")
    with pytest.raises(LeakageViolation, match="OUTCOME_FEATURE_FORBIDDEN"):
        build_macro_context("R1", semantics="EX_ANTE_CONTEXT",
                            releases=releases + [{"final_balance": 999}], source_fingerprint=fingerprint)
    forged = [dict(item) for item in releases]
    forged[-1]["available_at"] = "2026-08-24T00:00:00+00:00"
    with pytest.raises(LeakageViolation, match="AVAILABLE_BEFORE_RELEASE_FORBIDDEN"):
        build_macro_context("R1", semantics="EX_ANTE_CONTEXT", releases=forged,
                            source_fingerprint=fingerprint)


def test_duplicate_and_naive_release_times_are_rejected(tmp_path):
    releases, _ = load_official_releases()
    original = json.loads((Path(__file__).parents[1] / "jarvis_core" / "data" / "b4_8_official_releases.json").read_text())
    original["releases"].append(dict(original["releases"][0]))
    path = tmp_path / "releases.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_ID"):
        load_official_releases(path)
    original["releases"].pop()
    original["releases"][0]["released_at"] = "2026-07-29T14:00:00"
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        load_official_releases(path)
    assert releases


def test_robot_outcome_cannot_change_macro_context_fingerprint():
    releases, fingerprint = load_official_releases()
    common = {"test_run_id": "run_example", "context_fingerprint": "frozen-technical"}
    first = build_macro_context("R2", semantics="POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT",
                                releases=releases, source_fingerprint=fingerprint,
                                technical_context={**common, "post_window_outcome": {"balance_change": 1}})
    second = build_macro_context("R2", semantics="POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT",
                                 releases=releases, source_fingerprint=fingerprint,
                                 technical_context={**common, "post_window_outcome": {"balance_change": -9999}})
    assert first["context_fingerprint"] == second["context_fingerprint"]
    assert first["scientific_memory"]["scientific_id"] == second["scientific_memory"]["scientific_id"]


def test_missing_macro_artifact_does_not_take_down_robot_read_model(monkeypatch):
    from jarvis_core import robot_intelligence

    def unavailable(*_args):
        raise FileNotFoundError("B4.8 data missing")

    monkeypatch.setattr(robot_intelligence, "build_production_macro_contexts", unavailable)
    result = robot_intelligence.build_robot_intelligence_snapshot({"data": {"robots": []}})
    assert result["ok"] is True
    assert result["macro_contexts"] == []
    assert result["macro_evidence_status"] == "UNAVAILABLE:FileNotFoundError"


def test_existing_control_center_has_separate_macro_and_outcome_tables():
    source = (Path(__file__).parents[1] / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert 'response?.macro_contexts' in source
    assert 'POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT' in source
    assert 'POST_WINDOW_OUTCOME' in source
    assert 'NOT AUTHORIZED FOR LIVE TRADING' in source


def test_existing_robot_read_model_exposes_macro_without_changing_technical_or_catalog():
    result = build_robot_intelligence_snapshot({"data": {"robots": []}}, symbol="XAUUSD", timeframe="M1")
    assert result["read_only"] is True
    assert result["trading_authorization"] == "NOT_GRANTED"
    assert len(result["temporal_contexts"]) == 3
    assert len(result["macro_contexts"]) == 6
    assert result["macro_contexts"][0]["frozen"] is True
    assert result["macro_contexts"][0]["analysis_only"] is True
    assert result["macro_contexts"][0]["test_run_id"].startswith("run_")
    assert result["macro_contexts"][0]["scientific_memory"]["canonical_boundary"] == "CanonicalScientificMemory"
