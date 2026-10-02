"""Read-only B4.10 candidate identity recovery over bounded Golden evidence."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .b2_contracts import content_fingerprint
from .scientific_campaign_design import MANIFEST_PATH as B4_9_MANIFEST_PATH
from .tester_config_reconciliation import (
    materialize_config, materialized_config_fingerprint,
    output_routing_fingerprint, MATERIALIZATION_VERSION,
)

RECOVERY_PATH = Path(__file__).parent / "data" / "b4_10_robot_identity_recovery.json"
PROPOSED_CAMPAIGN_PATH = Path(__file__).parent / "data" / "b4_10_proposed_campaign.json"
B4_9_MANIFEST_HASH = "0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4"
_CONFIG_KEYS = (
    "campaign_id", "robot_id", "source_hash", "compiled_hash",
    "parameter_fingerprint", "symbol", "timeframe", "window", "split",
    "tester_model", "optimization", "use_remote", "use_cloud",
    "allow_live_trading",
)


def classify_source_artifacts(artifacts: list[dict[str, Any]]) -> str:
    if artifacts and any(not item.get("sha256") for item in artifacts):
        return "SOURCE_IDENTITY_INCOMPLETE"
    hashes = {str(item.get("sha256") or "").casefold() for item in artifacts
              if item.get("sha256")}
    if not hashes:
        return "SOURCE_MISSING"
    if len(hashes) > 1:
        return "MULTIPLE_DIFFERENT_SOURCE_VERSIONS"
    return "ONE_UNAMBIGUOUS_SOURCE" if len(artifacts) == 1 else "MULTIPLE_IDENTICAL_SOURCE_COPIES"


def classify_compiled_artifacts(artifacts: list[dict[str, Any]]) -> str:
    if artifacts and any(not item.get("sha256") for item in artifacts):
        return "COMPILED_PROVENANCE_AMBIGUOUS"
    hashes = {str(item.get("sha256") or "").casefold() for item in artifacts
              if item.get("sha256")}
    if not hashes:
        return "COMPILED_ARTIFACT_MISSING"
    if len(hashes) > 1:
        return "MULTIPLE_COMPILED_VERSIONS"
    return "ONE_UNAMBIGUOUS_COMPILED_ARTIFACT"


def classify_parameter_evidence(candidate: dict[str, Any]) -> str:
    status = str(candidate.get("parameter_evidence", {}).get("status") or "UNKNOWN")
    allowed = {
        "PARAMETERS_FROZEN_VERIFIED", "DEFAULT_PARAMETERS_VERIFIED",
        "MULTIPLE_PARAMETER_SETS", "PARAMETERS_AMBIGUOUS", "PARAMETERS_UNAVAILABLE",
    }
    return status if status in allowed else "PARAMETERS_AMBIGUOUS"


def classify_candidate_readiness(candidate: dict[str, Any]) -> dict[str, Any]:
    source_status = classify_source_artifacts(candidate.get("source_artifacts") or [])
    compiled_status = classify_compiled_artifacts(candidate.get("compiled_artifacts") or [])
    relationship = str(candidate.get("source_compiled_relationship") or "UNKNOWN")
    compile_evidence = candidate.get("compile_evidence") or {}
    parameter_status = classify_parameter_evidence(candidate)
    blockers: list[str] = []
    if source_status not in {"ONE_UNAMBIGUOUS_SOURCE", "MULTIPLE_IDENTICAL_SOURCE_COPIES"}:
        blockers.append(source_status)
    if compiled_status != "ONE_UNAMBIGUOUS_COMPILED_ARTIFACT":
        blockers.append(compiled_status)
    if relationship not in {"STRONG", "PARTIAL"}:
        blockers.append("SOURCE_COMPILED_RELATIONSHIP_" + relationship)
    if relationship == "PARTIAL" and not compile_evidence.get("path_and_timestamp_correlated"):
        blockers.append("COMPILE_LINKAGE_NOT_CORROBORATED")
    if compile_evidence.get("status") != "COMPILE_SUCCESS":
        blockers.append("COMPILE_SUCCESS_EVIDENCE_MISSING")
    if parameter_status not in {"PARAMETERS_FROZEN_VERIFIED", "DEFAULT_PARAMETERS_VERIFIED"}:
        blockers.append(parameter_status)
    if candidate.get("symbol_scope") in (None, "", "UNKNOWN"):
        blockers.append("SYMBOL_SCOPE_UNKNOWN")
    if candidate.get("timeframe_scope") in (None, "", "UNKNOWN"):
        blockers.append("TIMEFRAME_SCOPE_UNKNOWN")
    if candidate.get("dependencies_status") != "KNOWN":
        blockers.append("DEPENDENCIES_UNKNOWN")
    if candidate.get("identity_collision"):
        blockers.append("LOGICAL_IDENTITY_COLLISION")
    if blockers:
        readiness = "IDENTITY_AMBIGUOUS" if any(
            item in {"MULTIPLE_DIFFERENT_SOURCE_VERSIONS", "MULTIPLE_COMPILED_VERSIONS",
                     "SOURCE_IDENTITY_INCOMPLETE", "COMPILED_PROVENANCE_AMBIGUOUS",
                     "LOGICAL_IDENTITY_COLLISION"} for item in blockers
        ) else "NOT_READY"
    elif relationship == "PARTIAL" or not compile_evidence.get("compiler_version"):
        readiness = "READY_WITH_RESTRICTIONS"
    else:
        readiness = "READY_FOR_CONTROLLED_EVIDENCE"
    return {
        "source_status": source_status,
        "compiled_status": compiled_status,
        "parameter_status": parameter_status,
        "readiness": readiness,
        "blockers": blockers,
        "restrictions": (["SOURCE_TO_COMPILED_LINK_IS_PATH_AND_TIMESTAMP_CORROBORATED_NOT_HASHED",
                          "COMPILER_VERSION_NOT_RECORDED"] if readiness == "READY_WITH_RESTRICTIONS" else []),
    }


def _observed_hash(path: Path) -> tuple[str, int] | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest(), path.stat().st_size
    except OSError:
        return None


def _verify_artifacts(candidate: dict[str, Any], root: Path) -> tuple[dict[str, Any], bool]:
    verified = True
    result = dict(candidate)
    for key in ("source_artifacts", "compiled_artifacts", "parameter_artifacts", "compile_evidence"):
        rows = result.get(key, [])
        was_mapping = isinstance(rows, dict)
        if isinstance(rows, dict):
            rows = [rows]
        for item in rows:
            raw_path = str(item.get("path") or "")
            if not raw_path:
                item["current_bytes_status"] = "NOT_PRESENT"
                continue
            path = Path(raw_path)
            if not path.is_absolute():
                path = root / path
            observed = _observed_hash(path)
            if observed is None:
                item["current_bytes_status"] = "MISSING"
                verified = False
                continue
            actual_hash, size = observed
            item["current_bytes_status"] = "MATCH" if actual_hash == item.get("sha256") else "HASH_MISMATCH"
            item["current_sha256"] = actual_hash
            item["current_size"] = size
            verified = verified and actual_hash == item.get("sha256")
        if key == "compile_evidence" and was_mapping:
            result[key] = rows[0] if rows else {}
        else:
            result[key] = rows
    parameter = result.get("parameter_evidence") or {}
    if parameter.get("path") and parameter.get("sha256"):
        observed = _observed_hash(Path(parameter["path"]) if Path(parameter["path"]).is_absolute()
                                  else root / parameter["path"])
        if observed is None:
            parameter["current_bytes_status"] = "MISSING"
            verified = False
        else:
            parameter["current_sha256"], parameter["current_size"] = observed
            parameter["current_bytes_status"] = (
                "MATCH" if observed[0] == parameter["sha256"] else "HASH_MISMATCH"
            )
            verified = verified and observed[0] == parameter["sha256"]
    result["parameter_evidence"] = parameter
    result["observed_artifacts_reconciled"] = verified
    return result, verified


def _catalog_matches(root: Path, candidates: list[dict[str, Any]]) -> tuple[str, dict[str, list[dict[str, str]]]]:
    path = root / "studio" / "golden_ai_studio_web" / "jarvis" / "robot_catalog.db"
    empty = {str(item["candidate_id"]): [] for item in candidates}
    if not path.is_file():
        return "UNAVAILABLE", empty
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute("SELECT robot_id, payload_json FROM robot_records").fetchall()
    except (OSError, sqlite3.Error):
        return "UNAVAILABLE", empty
    for robot_id, raw in rows:
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            continue
        searchable = json.dumps(record, ensure_ascii=True).casefold()
        for candidate in candidates:
            name = str(candidate["candidate_id"]).casefold()
            source_names = [Path(item["path"]).name.casefold()
                            for item in candidate.get("source_artifacts", [])]
            if name in searchable or any(item in searchable for item in source_names):
                empty[candidate["candidate_id"]].append({
                    "robot_id": str(robot_id), "name": str(record.get("name") or "UNKNOWN"),
                })
    return "READ_ONLY_QUERY_SUCCESS", empty


def _dry_run_association(candidate: dict[str, Any], readiness: dict[str, Any],
                         matches: list[dict[str, str]]) -> dict[str, Any] | None:
    if readiness["readiness"] != "READY_WITH_RESTRICTIONS" or matches:
        return None
    source = candidate["source_artifacts"][0]
    compiled = candidate["compiled_artifacts"][0]
    return {
        "status": "DRY_RUN_ONLY_NOT_PERSISTED",
        "robot_id": candidate["candidate_id"],
        "name": candidate["name"],
        "classification": "PRODUCTION_ROBOT",
        "repertoire_status": "DISCOVERED",
        "trading_authorization": "NOT_GRANTED",
        "source_artifacts": [{"sha256": source["sha256"], "path": source["path"]}],
        "compiled_artifacts": [{"sha256": compiled["sha256"], "path": compiled["path"]}],
        "parameter_fingerprint": candidate["parameter_evidence"]["fingerprint"],
        "schema_change_required": False,
        "would_mutate_catalog": False,
    }


def load_robot_identity_recovery(root: Path | str | None = None) -> dict[str, Any]:
    """Load the frozen forensic inventory and re-hash only its exact artifacts."""
    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    inventory = json.loads(RECOVERY_PATH.read_text(encoding="utf-8"))
    b4_9 = json.loads(B4_9_MANIFEST_PATH.read_text(encoding="utf-8"))
    actual_b4_9_hash = content_fingerprint(b4_9)
    if actual_b4_9_hash != B4_9_MANIFEST_HASH:
        raise ValueError("B4_9_MANIFEST_IMMUTABILITY_VIOLATION")
    candidates = []
    for raw in inventory["candidates"]:
        candidate, bytes_ok = _verify_artifacts(raw, repo)
        readiness = classify_candidate_readiness(candidate)
        if not bytes_ok:
            readiness["readiness"] = "NOT_READY"
            readiness["blockers"].append("OBSERVED_ARTIFACT_HASH_DRIFT")
        candidate.update(readiness)
        candidates.append(candidate)
    catalog_status, catalog = _catalog_matches(repo, candidates)
    for candidate in candidates:
        matches = catalog.get(candidate["candidate_id"], [])
        candidate["catalog_entries"] = matches
        candidate["dry_run_association"] = (
            _dry_run_association(candidate, candidate, matches)
            if catalog_status == "READ_ONLY_QUERY_SUCCESS" else None
        )
    proposed = json.loads(PROPOSED_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    if proposed.get("b4_9_manifest_hash") != actual_b4_9_hash:
        raise ValueError("PROPOSED_CAMPAIGN_B4_9_BASELINE_MISMATCH")
    if proposed.get("campaign_id") == b4_9.get("campaign_id"):
        raise ValueError("CAMPAIGN_VERSION_COLLISION")
    proposed_manifest = proposed["manifest"]
    _validate_proposed_campaign(proposed, proposed_manifest, candidates, b4_9)
    proposed_hash = content_fingerprint(proposed_manifest)
    return {
        "read_only": True,
        "status": "PARTIAL_IDENTITY_RECOVERY",
        "roots_audited": inventory["roots_audited"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "legacy_evidence": inventory["legacy_evidence"],
        "catalog_status": catalog_status,
        "catalog_mutated": False,
        "catalog_schema_changed": False,
        "campaign_impact": {
            "b4_9_manifest_hash": actual_b4_9_hash,
            "b4_9_unchanged": True,
            "b4_9_executable_now": False,
            "multi_robot_campaign_possible": True,
            "proposed_campaign_id": proposed["campaign_id"],
            "proposed_manifest_hash": proposed_hash,
            "proposed_manifest": proposed_manifest,
            "proposed_status": "PROPOSED_NOT_AUTHORIZED",
            "proposed_run_count": len(proposed_manifest.get("planned_runs", [])),
            "execution_ready": False,
            "execution_blockers": proposed["execution_blockers"],
        },
        "provenance": {
            "candidate_source": "BOUNDED_B4_10_FORENSIC_INVENTORY",
            "catalog": "READ_ONLY_SQLITE_QUERY",
            "legacy_results_used_for_identity": False,
            "outcomes_used_for_identity": False,
        },
    }


def _validate_proposed_campaign(proposed: dict[str, Any], manifest: dict[str, Any],
                                candidates: list[dict[str, Any]], b4_9: dict[str, Any]) -> None:
    if manifest.get("status") != "PROPOSED_NOT_AUTHORIZED":
        raise ValueError("PROPOSED_CAMPAIGN_AUTHORIZATION_STATE_INVALID")
    runs = manifest.get("planned_runs")
    if not isinstance(runs, list) or len(runs) != 16:
        raise ValueError("PROPOSED_CAMPAIGN_RUN_COUNT_INVALID")
    if manifest.get("campaign_id") != proposed.get("campaign_id"):
        raise ValueError("PROPOSED_CAMPAIGN_ID_MISMATCH")
    if not manifest.get("b4_9_parent", {}).get("immutable"):
        raise ValueError("B4_9_PARENT_MUST_REMAIN_IMMUTABLE")
    candidate_by_id = {item["candidate_id"]: item for item in candidates}
    canal = b4_9.get("robot") or {}
    ids: set[str] = set()
    splits: dict[str, int] = {}
    expected_windows = [
        {"from": "2026-11-02", "to": "2026-11-06"},
        {"from": "2026-11-09", "to": "2026-11-13"},
        {"from": "2026-11-16", "to": "2026-11-20"},
        {"from": "2026-11-30", "to": "2026-12-04"},
        {"from": "2026-12-07", "to": "2026-12-11"},
        {"from": "2026-12-14", "to": "2026-12-18"},
        {"from": "2027-01-04", "to": "2027-01-08"},
        {"from": "2027-01-11", "to": "2027-01-15"},
    ]
    for run in runs:
        run_id = str(run.get("test_run_id") or "")
        if not re.fullmatch(r"run_[a-f0-9]{32}", run_id) or run_id in ids:
            raise ValueError("PROPOSED_CAMPAIGN_RUN_ID_INVALID")
        ids.add(run_id)
        robot = str(run.get("robot_id") or "")
        if robot not in {"EA_Canal_Pullback_MT5", "Robo_Tendencia_MA9_21_50_Volume"}:
            raise ValueError("PROPOSED_CAMPAIGN_ROBOT_INVALID")
        identity = canal if robot == "EA_Canal_Pullback_MT5" else candidate_by_id[robot]
        if robot != "EA_Canal_Pullback_MT5" and identity.get("readiness") != "READY_WITH_RESTRICTIONS":
            raise ValueError("PROPOSED_ROBOT_NOT_READY")
        expected_source = (identity.get("source_hash") if robot == "EA_Canal_Pullback_MT5"
                           else identity["source_artifacts"][0]["sha256"])
        expected_compiled = (identity.get("compiled_hash") if robot == "EA_Canal_Pullback_MT5"
                             else identity["compiled_artifacts"][0]["sha256"])
        expected_parameters = (identity.get("parameter_fingerprint") if robot == "EA_Canal_Pullback_MT5"
                               else identity["parameter_evidence"]["fingerprint"])
        if (run.get("source_hash"), run.get("compiled_hash"), run.get("parameter_fingerprint")) != (
                expected_source, expected_compiled, expected_parameters):
            raise ValueError("PROPOSED_ROBOT_ARTIFACT_IDENTITY_MISMATCH")
        if run.get("window") not in expected_windows:
            raise ValueError("PROPOSED_CAMPAIGN_WINDOW_INVALID")
        expected_split = ("DEVELOPMENT" if run["window"] in expected_windows[:4]
                          else "VALIDATION" if run["window"] in expected_windows[4:6]
                          else "HOLDOUT")
        if run.get("split") != expected_split:
            raise ValueError("PROPOSED_CAMPAIGN_SPLIT_INVALID")
        splits[expected_split] = splits.get(expected_split, 0) + 1
        if (run.get("tester_model") != "REAL_TICKS" or run.get("optimization") != 0
                or any(run.get(key) != 0 for key in ("use_remote", "use_cloud", "allow_live_trading"))):
            raise ValueError("PROPOSED_CAMPAIGN_SAFETY_INVALID")
        if run.get("scientific_config_fingerprint") != scientific_run_config_fingerprint(
                run, manifest["campaign_id"]):
            raise ValueError("PROPOSED_SCIENTIFIC_CONFIG_FINGERPRINT_MISMATCH")
        if any(run.get(key) != "NOT_MATERIALIZED" for key in
               ("materialized_config_fingerprint", "output_routing_fingerprint")):
            raise ValueError("RUNTIME_FINGERPRINT_MUST_NOT_BE_FABRICATED")
        if run.get("context_status") != "PENDING_PRE_EXECUTION_FREEZE":
            raise ValueError("PROPOSED_CONTEXT_NOT_FROZEN")
    if splits != {"DEVELOPMENT": 8, "VALIDATION": 4, "HOLDOUT": 4}:
        raise ValueError("PROPOSED_CAMPAIGN_SPLIT_COUNTS_INVALID")
    _assert_no_outcomes(manifest)


def materialize_proposed_run_config(run: dict[str, Any], campaign_id: str, content: str,
                                    output_root: Path | str = ".") -> dict[str, str]:
    """Exercise the existing deterministic materializer without creating files."""
    materialized = materialize_config(
        content, campaign_id, str(run["test_run_id"]), output_root
    )
    return {
        "content": materialized,
        "materialized_config_fingerprint": materialized_config_fingerprint(materialized),
        "output_routing_fingerprint": output_routing_fingerprint(materialized),
        "materialization_version": MATERIALIZATION_VERSION,
    }


def scientific_run_config_fingerprint(run: dict[str, Any], campaign_id: str) -> str:
    """Fingerprint frozen scientific identity independently of runtime routing."""
    payload = {"campaign_id": campaign_id}
    payload.update({key: run[key] for key in _CONFIG_KEYS if key != "campaign_id" and key in run})
    missing = set(_CONFIG_KEYS) - set(payload)
    if missing:
        raise ValueError("SCIENTIFIC_CONFIG_FIELDS_MISSING:" + ",".join(sorted(missing)))
    return content_fingerprint(payload)


def _assert_no_outcomes(value: Any) -> None:
    forbidden = {"profit", "pnl", "balance", "equity", "drawdown", "trades", "outcome", "score", "ontester"}
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(char for char in str(key).casefold() if char.isalnum())
            if any(token in normalized for token in forbidden):
                raise ValueError("PROPOSED_CAMPAIGN_OUTCOME_FIELD_FORBIDDEN")
            _assert_no_outcomes(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_outcomes(child)


__all__ = [
    "classify_candidate_readiness", "classify_compiled_artifacts",
    "classify_parameter_evidence", "classify_source_artifacts",
    "load_robot_identity_recovery", "materialize_proposed_run_config",
    "scientific_run_config_fingerprint",
]
