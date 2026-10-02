"""Dry-run and persistence payloads for the B4.7D production catalog link."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .robot_artifact_identity import CAMPAIGN_ID, LOGICAL_ROBOT_ID, PARAMETER_FINGERPRINT


RUN_TO_WINDOW = {
    "run_1c8069dbd88842a4ad88cd9d6ae6fa7d": "R1",
    "run_a8180c7c559746da9b7a6863f6796292": "R2",
    "run_c078697fe9ce4892bc9665e6f276be58": "R3",
}


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _id(kind: str, digest: str) -> str:
    return f"artifact_{kind}_{str(digest)[:24]}"


def _unique(values: list[dict[str, Any]], key: str) -> bool:
    items = [str(item.get(key) or "") for item in values]
    return len(items) == len(set(items)) and all(items)


def build_production_association_plan(identity: dict[str, Any], catalog_snapshot: dict[str, Any],
                                      *, evidence_root: Path | str,
                                      context_root: Path | str) -> dict[str, Any]:
    historical = identity["compiled_artifacts"]["historical_tested"]
    current = identity["compiled_artifacts"]["current_observed"]
    source = identity["source_artifact"]
    evidence_dir = Path(evidence_root)
    context_dir = Path(context_root)
    evidence_by_run: dict[str, dict[str, Any]] = {}
    for path in sorted(evidence_dir.glob("*.native_log_evidence.json")):
        payload = _read(path)
        normalized = payload.get("provider_outcome", {}).get("normalized", {})
        run_id = str(normalized.get("test_run_id") or "") if isinstance(normalized, dict) else ""
        if run_id in RUN_TO_WINDOW:
            evidence_by_run[run_id] = {"path": path, "payload": payload, "normalized": normalized}
    runs: list[dict[str, Any]] = []
    backtests: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    for run_id, window_id in RUN_TO_WINDOW.items():
        item = evidence_by_run.get(run_id)
        if not item:
            continue
        normalized = item["normalized"]
        artifact_hash = str(normalized.get("artifact_hash") or "")
        evidence = {
            "evidence_id": run_id,
            "test_run_id": run_id,
            "status": "HISTORICAL_PRODUCTION_EVIDENCE",
            "robot_id": LOGICAL_ROBOT_ID,
            "evidence_kind": "TEST_RUN",
            "campaign_id": CAMPAIGN_ID,
            "window_id": window_id,
            "source_hash": normalized.get("source_hash"),
            "compiled_hash": normalized.get("compiled_hash"),
            "parameter_fingerprint": normalized.get("parameter_fingerprint"),
            "symbol": normalized.get("symbol"),
            "timeframe": normalized.get("timeframe"),
            "tester_model": normalized.get("tester_model"),
            "date_from": normalized.get("date_from"),
            "date_to": normalized.get("date_to"),
            "metrics": normalized.get("metrics") or {},
            "artifact_hash": artifact_hash,
            "evidence_path": str(item["path"].resolve()),
            "historical_compiled_artifact_id": historical.get("artifact_id") or _id("compiled", historical["sha256"]),
            "current_compiled_artifact_id": None,
            "outcome_role": "POST_WINDOW_OUTCOME",
            "current_artifact_inherits_results": False,
        }
        runs.append(evidence)
        backtests.append({
            "artifact_id": _id("evidence", artifact_hash or run_id),
            "kind": "BACKTEST_EVIDENCE",
            "relative_path": str(item["path"].resolve()),
            "root": "B4_5_CAMPAIGN_EVIDENCE",
            "sha256": artifact_hash,
            "association_status": "VERIFIED",
            "association_confidence": "HIGH",
            "robot_id": LOGICAL_ROBOT_ID,
            "campaign_id": CAMPAIGN_ID,
            "test_run_id": run_id,
            "compiled_hash": normalized.get("compiled_hash"),
            "parameter_fingerprint": normalized.get("parameter_fingerprint"),
            "outcome_role": "POST_WINDOW_OUTCOME",
        })
        evidence_items.append(evidence)

    contexts: list[dict[str, Any]] = []
    for window_id in ("R1", "R2", "R3"):
        context = _read(context_dir / f"{window_id}.temporal_context.json")
        if not context:
            continue
        contexts.append({
            "context_fingerprint": context.get("context_fingerprint"),
            "window_id": window_id,
            "campaign_id": CAMPAIGN_ID,
            "test_run_id": context.get("test_run_id"),
            "labels_preserved": True,
            "labels_source": "B4_7_CANONICAL_HISTORICAL_MARKET_ARTIFACT",
            "outcome_role": "POST_WINDOW_OUTCOME",
            "context_file": str((context_dir / f"{window_id}.temporal_context.json").resolve()),
        })

    source_artifact = {
        "artifact_id": source.get("artifact_id") or _id("source", source["sha256"]),
        "kind": "SOURCE", "relative_path": source["path"], "root": "GoldenAI",
        "sha256": source["sha256"], "size": source.get("size"),
        "identity_role": "HISTORICAL_SOURCE_ARTIFACT", "association_confidence": "HIGH",
    }
    compiled_artifacts = [
        {**historical, "artifact_id": historical.get("artifact_id") or _id("compiled", historical["sha256"]),
         "kind": "COMPILED", "identity_role": "HISTORICAL_TESTED_COMPILED_ARTIFACT",
         "tested_by_b4_5": True, "campaign_ids": [CAMPAIGN_ID], "association_confidence": "HIGH"},
        {**current, "artifact_id": current.get("artifact_id") or _id("compiled", current["sha256"]),
         "kind": "COMPILED", "identity_role": "CURRENT_OBSERVED_COMPILED_ARTIFACT",
         "tested_by_b4_5": False, "campaign_ids": [], "production_evidence_count": 0,
         "association_confidence": "HIGH"},
    ]
    existing = [item for item in catalog_snapshot.get("robots", []) if isinstance(item, dict)]
    production = next((item for item in existing if item.get("robot_id") == LOGICAL_ROBOT_ID), None)
    existing_artifacts = {str(item.get("artifact_id")): item for item in (production or {}).get("compiled_artifacts", [])}
    existing_source = {str(item.get("sha256")): item for item in (production or {}).get("source_artifacts", [])}
    existing_runs = {str(item.get("test_run_id")): item for item in (production or {}).get("test_runs", [])}
    existing_campaigns = {str(item.get("campaign_id")): item for item in (production or {}).get("campaign_associations", [])}
    existing_contexts = {str(item.get("context_fingerprint")): item for item in (production or {}).get("temporal_contexts", [])}
    collisions: list[str] = []
    for artifact in compiled_artifacts:
        prior = existing_artifacts.get(str(artifact["artifact_id"]))
        if prior and prior.get("sha256") != artifact.get("sha256"):
            collisions.append(f"COMPILED_ARTIFACT:{artifact['artifact_id']}")
    if not _unique(runs, "test_run_id") or not _unique(backtests, "artifact_id") or not _unique(contexts, "context_fingerprint"):
        collisions.append("DUPLICATE_INPUT_EVIDENCE")
    fixture_records = [item for item in existing if item.get("robot_id") == "fixture_golden_strategy_tester_v1"]
    fixture_hashes = {str(artifact.get("sha256")) for item in fixture_records
                      for artifact in list(item.get("source_artifacts") or []) + list(item.get("compiled_artifacts") or [])}
    fixture_collisions = ["FIXTURE_IDENTITY" for item in (LOGICAL_ROBOT_ID,) if item == "fixture_golden_strategy_tester_v1"]
    fixture_collisions.extend(
        f"FIXTURE_ARTIFACT:{artifact['sha256']}" for artifact in compiled_artifacts + [source_artifact]
        if str(artifact.get("sha256")) in fixture_hashes
    )
    relationships_to_create: list[str] = []
    relationships_existing: list[str] = []
    relationship_checks = {
        "LOGICAL_ROBOT_SOURCE": source.get("sha256") in existing_source,
        "HISTORICAL_COMPILED_TO_CAMPAIGN": historical.get("sha256") in {str(item.get("sha256")) for item in (production or {}).get("compiled_artifacts", [])} and CAMPAIGN_ID in existing_campaigns,
        "CURRENT_COMPILED_OBSERVATION": current.get("sha256") in {str(item.get("sha256")) for item in (production or {}).get("compiled_artifacts", [])},
        "RUNS_TO_HISTORICAL_COMPILED": all(item["test_run_id"] in existing_runs for item in runs) and bool(runs),
        "CONTEXTS_TO_RUNS": all(item["context_fingerprint"] in existing_contexts for item in contexts) and bool(contexts),
    }
    for name, present in relationship_checks.items():
        (relationships_existing if present else relationships_to_create).append(name)
    return {
        "dry_run_status": "SAFE_TO_APPLY" if not collisions and not fixture_collisions and len(runs) == 3 and len(contexts) == 3 else "STOP",
        "logical_robot": {"robot_id": LOGICAL_ROBOT_ID, "name": "EA Canal Pullback MT5", "classification": "PRODUCTION_ROBOT", "status": "DISCOVERED"},
        "campaign_id": CAMPAIGN_ID,
        "source_artifacts": [source_artifact],
        "compiled_artifacts": compiled_artifacts,
        "parameter_sets": [{"fingerprint": PARAMETER_FINGERPRINT, "campaign_id": CAMPAIGN_ID, "historical_only": True}],
        "campaigns": [{"campaign_id": CAMPAIGN_ID, "historical_compiled_hash": historical["sha256"], "current_compiled_hash_observed": current["sha256"], "current_artifact_bound": False, "production_run_count": len(runs), "context_count": len(contexts)}],
        "test_runs": runs,
        "evidence_items": evidence_items,
        "backtest_artifacts": backtests,
        "temporal_contexts": contexts,
        "objects_to_create": {
            "robot": [] if production else [LOGICAL_ROBOT_ID],
            "source_artifacts": [] if source.get("sha256") in existing_source else [source_artifact["artifact_id"]],
            "compiled_artifacts": [item["artifact_id"] for item in compiled_artifacts if item["artifact_id"] not in existing_artifacts],
            "campaigns": [] if CAMPAIGN_ID in existing_campaigns else [CAMPAIGN_ID],
            "runs": [item["test_run_id"] for item in runs if item["test_run_id"] not in existing_runs],
            "contexts": [item["context_fingerprint"] for item in contexts if item["context_fingerprint"] not in existing_contexts],
        },
        "objects_existing": {
            "fixture_robot_ids": sorted(item.get("robot_id") for item in existing if item.get("robot_id") and item.get("robot_id") != LOGICAL_ROBOT_ID),
            "robot": [LOGICAL_ROBOT_ID] if production else [],
            "campaigns": [CAMPAIGN_ID] if CAMPAIGN_ID in existing_campaigns else [],
            "runs": [item["test_run_id"] for item in runs if item["test_run_id"] in existing_runs],
            "contexts": [item["context_fingerprint"] for item in contexts if item["context_fingerprint"] in existing_contexts],
        },
        "relationships_to_create": relationships_to_create,
        "relationships_existing": relationships_existing,
        "identity_collisions": collisions,
        "fixture_collisions": fixture_collisions,
        "evidence_collisions": [],
        "lossy_mappings": [],
    }


__all__ = ["RUN_TO_WINDOW", "build_production_association_plan"]
