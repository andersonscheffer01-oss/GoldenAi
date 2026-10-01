"""Read-only reconciliation for logical robot and compiled artifact identity.

The historical B4.5 binary and the current workspace binary are deliberately
represented as separate observations.  This module never compiles, writes a
catalog, starts MT5, or grants execution authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HISTORICAL_SOURCE_HASH = "0f1ba3526de5e7b679281e38136479beb99dd707fd1b02db1d960ffae103aff4"
HISTORICAL_COMPILED_HASH = "e239e0dfc1c6a10c4bd4f8758b1913946b2423cd0901b8f3486b910fe56267cc"
PARAMETER_FINGERPRINT = "7953a3fa4ca05b223411fca3"
CAMPAIGN_ID = "campaign_073cebd5e7df446fa9c85bae75ffbe0a"
LOGICAL_ROBOT_ID = "EA_Canal_Pullback_MT5"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_manifest_path() -> Path:
    return (_repo_root() / "studio" / "golden_ai_studio_web" / "tester_campaigns" /
            CAMPAIGN_ID / "campaign_manifest.json")


def _default_evidence_root() -> Path:
    return (_repo_root() / "studio" / "golden_ai_studio_web" / "tester_campaigns" /
            CAMPAIGN_ID / "evidence")


def _json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observation(path: Path | None, role: str, expected_hash: str = "") -> dict[str, Any]:
    if path is None:
        return {"role": role, "path": "UNKNOWN", "availability": "UNKNOWN"}
    resolved = path.resolve()
    actual_hash = _sha256(resolved)
    if actual_hash is None:
        return {
            "role": role, "path": str(resolved), "availability": "BYTES_NOT_CURRENTLY_AVAILABLE",
            "sha256": expected_hash or "UNKNOWN",
        }
    stat = resolved.stat()
    return {
        "role": role,
        "path": str(resolved),
        "availability": "BYTES_AVAILABLE",
        "sha256": actual_hash,
        "size": stat.st_size,
        "mtime_observed": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "hash_matches_expected": bool(expected_hash) and actual_hash == expected_hash,
    }


def classify_artifact_identity(*, historical_source_hash: str, current_source_hash: str,
                               historical_compiled_hash: str, current_compiled_hash: str) -> dict[str, str]:
    source_same = bool(historical_source_hash) and historical_source_hash == current_source_hash
    compiled_same = bool(historical_compiled_hash) and historical_compiled_hash == current_compiled_hash
    if source_same and compiled_same:
        status = "SOURCE_SAME_COMPILED_SAME"
    elif source_same and not compiled_same:
        status = "SOURCE_SAME_COMPILED_DIFFERENT"
    elif not source_same and not compiled_same:
        status = "SOURCE_DIFFERENT_COMPILED_DIFFERENT"
    else:
        status = "SOURCE_DIFFERENT_COMPILED_SAME"
    return {
        "source_identity_status": "SOURCE_SAME" if source_same else "SOURCE_DIFFERENT",
        "compiled_identity_status": status,
        "version_relationship": (
            "SAME_LOGICAL_ROBOT_NEW_COMPILED_ARTIFACT" if source_same and not compiled_same
            else "SAME_COMPILED_IDENTITY" if compiled_same else "SEPARATE_ARTIFACT_IDENTITIES"
        ),
    }


def reconcile_artifact_identity(*, manifest_path: Path | str | None = None,
                                source_path: Path | str | None = None,
                                current_compiled_path: Path | str | None = None,
                                historical_compiled_path: Path | str | None = None,
                                evidence_paths: Iterable[Path | str] | None = None,
                                catalog_robot_ids: Iterable[str] = ()) -> dict[str, Any]:
    manifest_file = Path(manifest_path) if manifest_path else _default_manifest_path()
    manifest = _json_file(manifest_file)
    robot = manifest.get("robot") if isinstance(manifest.get("robot"), dict) else {}
    compile_evidence = manifest.get("compile_evidence") if isinstance(manifest.get("compile_evidence"), dict) else {}
    expected_source_hash = str(robot.get("source_hash") or HISTORICAL_SOURCE_HASH)
    expected_compiled_hash = str(robot.get("compiled_hash") or HISTORICAL_COMPILED_HASH)
    source_file = Path(source_path) if source_path else _repo_root() / "projetos" / LOGICAL_ROBOT_ID / f"{LOGICAL_ROBOT_ID}.mq5"
    current_file = (Path(current_compiled_path) if current_compiled_path else
                    _repo_root() / "projetos" / LOGICAL_ROBOT_ID / f"{LOGICAL_ROBOT_ID}.ex5")
    historical_file = Path(historical_compiled_path) if historical_compiled_path else Path(str(robot.get("compiled_path") or ""))
    historical = _observation(historical_file, "HISTORICAL_TESTED_COMPILED", expected_compiled_hash)
    current = _observation(current_file, "CURRENT_OBSERVED_COMPILED")
    source = _observation(source_file, "CURRENT_SOURCE", expected_source_hash)

    paths = [Path(item) for item in evidence_paths] if evidence_paths is not None else sorted(_default_evidence_root().glob("*.native_log_evidence.json"))
    runs: list[dict[str, Any]] = []
    for path in paths:
        payload = _json_file(path)
        normalized = payload.get("provider_outcome", {}).get("normalized", {})
        if not isinstance(normalized, dict):
            continue
        if normalized.get("robot_id") != LOGICAL_ROBOT_ID:
            continue
        runs.append({
            "test_run_id": normalized.get("test_run_id", "UNKNOWN"),
            "source_hash": normalized.get("source_hash", "UNKNOWN"),
            "compiled_hash": normalized.get("compiled_hash", "UNKNOWN"),
            "parameter_fingerprint": normalized.get("parameter_fingerprint", "UNKNOWN"),
            "evidence_path": str(path.resolve()),
        })
    bound_hashes = sorted({str(item["compiled_hash"]) for item in runs})
    historical_evidence_verified = (
        compile_evidence.get("status") == "COMPILE_SUCCESS" and
        expected_compiled_hash == HISTORICAL_COMPILED_HASH and
        bool(runs) and bound_hashes == [HISTORICAL_COMPILED_HASH] and
        all(item["source_hash"] == expected_source_hash for item in runs)
    )
    identity = classify_artifact_identity(
        historical_source_hash=expected_source_hash,
        current_source_hash=str(source.get("sha256") or ""),
        historical_compiled_hash=expected_compiled_hash,
        current_compiled_hash=str(current.get("sha256") or ""),
    )
    catalog_ids = {str(item) for item in catalog_robot_ids}
    historical_available = historical.get("availability") == "BYTES_AVAILABLE" and historical.get("sha256") == expected_compiled_hash
    return {
        "status": "RECONCILED" if historical_evidence_verified else "PARTIAL",
        "read_only": True,
        "logical_robot": {
            "robot_id": str(robot.get("robot_id") or LOGICAL_ROBOT_ID),
            "version": str(robot.get("version") or "UNKNOWN"),
            "classification": str(robot.get("classification") or "PRODUCTION_ROBOT"),
        },
        "source_artifact": {
            **source,
            "historical_sha256": expected_source_hash,
            "identity_status": identity["source_identity_status"],
        },
        "compiled_artifacts": {
            "historical_tested": {
                **historical,
                "expected_sha256": expected_compiled_hash,
                "identity": "HISTORICAL_EXECUTED_COMPILED_ARTIFACT",
                "evidence_verified": historical_evidence_verified,
            },
            "current_observed": {
                **current,
                "identity": "CURRENT_OBSERVED_COMPILED_ARTIFACT",
                "historical_results_inherited": False,
            },
        },
        "source_compiled_relationship": identity,
        "proven_cause_of_difference": "AMBIGUOUS_NO_REPRODUCTION_AUTHORIZED" if identity["compiled_identity_status"] != "SOURCE_SAME_COMPILED_SAME" else "NONE",
        "parameter_set_identity": {
            "campaign_id": str(manifest.get("campaign_id") or CAMPAIGN_ID),
            "fingerprint": PARAMETER_FINGERPRINT,
        },
        "test_execution_identity": {
            "campaign_id": str(manifest.get("campaign_id") or CAMPAIGN_ID),
            "production_run_count": len(runs),
            "runs": runs,
            "bound_compiled_hash": expected_compiled_hash,
        },
        "compile_evidence": {
            "status": str(compile_evidence.get("status") or "UNKNOWN"),
            "compiler": str(compile_evidence.get("compiler") or "UNKNOWN"),
            "compiler_version": str(compile_evidence.get("compiler_version") or "UNKNOWN"),
            "errors": compile_evidence.get("errors", "UNKNOWN"),
            "warnings": compile_evidence.get("warnings", "UNKNOWN"),
            "source_compiled_linkage": str(robot.get("source_compiled_relationship") or "UNKNOWN"),
        },
        "catalog": {
            "versioned_identity_capacity": True,
            "production_associated": LOGICAL_ROBOT_ID in catalog_ids,
            "historical_artifact_associated": False,
            "current_artifact_associated": False,
            "fixture_preserved": "fixture_golden_strategy_tester_v1" in catalog_ids or not catalog_ids,
            "association_status": "DEFERRED_NO_CATALOG_MUTATION",
            "schema_change_required": False,
            "database_mutated": False,
        },
        "historical_artifact_availability": "BYTES_AVAILABLE" if historical_available else "BYTES_NOT_CURRENTLY_AVAILABLE",
        "safety": {
            "trading_authorization": "NOT_GRANTED",
            "current_binary_inherits_historical_results": False,
            "mt5_started": False,
            "mql5_compiled": False,
        },
    }


def load_production_artifact_identity() -> dict[str, Any]:
    """Load the local evidence projection without mutating any persistence."""
    return reconcile_artifact_identity()


__all__ = [
    "CAMPAIGN_ID", "HISTORICAL_COMPILED_HASH", "HISTORICAL_SOURCE_HASH",
    "LOGICAL_ROBOT_ID", "PARAMETER_FINGERPRINT", "classify_artifact_identity",
    "load_production_artifact_identity", "reconcile_artifact_identity",
]
