"""Read-only B4.9 pre-registered scientific campaign design."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .b2_contracts import content_fingerprint
from .robot_artifact_identity import (
    HISTORICAL_COMPILED_HASH, HISTORICAL_SOURCE_HASH, LOGICAL_ROBOT_ID,
    PARAMETER_FINGERPRINT,
)

MANIFEST_PATH = Path(__file__).parent / "data" / "b4_9_scientific_campaign.json"
OUTCOME_KEYS = frozenset({"profit", "pnl", "balance", "equity", "drawdown", "trades", "outcome", "score", "ontester"})
SCIENTIFIC_CONFIG_KEYS = (
    "robot_id", "source_hash", "compiled_hash", "parameter_fingerprint",
    "symbol", "timeframe", "window", "tester_model", "optimization",
    "use_remote", "use_cloud", "allow_live_trading",
)


def _assert_no_outcomes(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(char for char in str(key).casefold() if char.isalnum())
            if any(token in normalized for token in OUTCOME_KEYS):
                raise ValueError("OUTCOME_FIELD_FORBIDDEN:" + str(key))
            _assert_no_outcomes(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_outcomes(child)


def validate_campaign(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != "jarvis-b4.9-scientific-campaign-v1":
        raise ValueError("UNEXPECTED_CAMPAIGN_SCHEMA")
    robot = manifest.get("robot") or {}
    if (robot.get("robot_id"), robot.get("source_hash"), robot.get("compiled_hash"),
            robot.get("parameter_fingerprint")) != (
            LOGICAL_ROBOT_ID, HISTORICAL_SOURCE_HASH, HISTORICAL_COMPILED_HASH,
            PARAMETER_FINGERPRINT):
        raise ValueError("ROBOT_ARTIFACT_OR_PARAMETER_IDENTITY_MISMATCH")
    runs = manifest.get("planned_runs")
    if not isinstance(runs, list) or len(runs) != 8:
        raise ValueError("EXPECTED_EIGHT_PLANNED_RUNS")
    ids: set[str] = set()
    windows: set[tuple[str, str]] = set()
    previous_end = ""
    split_counts: dict[str, int] = {}
    for run in runs:
        if run.get("robot_id") != LOGICAL_ROBOT_ID:
            raise ValueError("UNAPPROVED_ROBOT")
        if run.get("source_hash") != HISTORICAL_SOURCE_HASH or run.get("compiled_hash") != HISTORICAL_COMPILED_HASH:
            raise ValueError("ARTIFACT_IDENTITY_MISMATCH")
        if run.get("parameter_fingerprint") != PARAMETER_FINGERPRINT:
            raise ValueError("PARAMETER_IDENTITY_MISMATCH")
        run_id = str(run.get("test_run_id") or "")
        if not run_id or run_id in ids:
            raise ValueError("DUPLICATE_OR_MISSING_RUN_ID")
        ids.add(run_id)
        window = run.get("window") or {}
        start, end = str(window.get("from") or ""), str(window.get("to") or "")
        if not start or not end or start > end or (start, end) in windows or start <= previous_end:
            raise ValueError("WINDOW_ORDER_OR_DUPLICATE_INVALID")
        windows.add((start, end))
        previous_end = end
        split = str(run.get("split") or "")
        split_counts[split] = split_counts.get(split, 0) + 1
        if run.get("symbol") != "XAUUSD" or run.get("timeframe") != "M1":
            raise ValueError("UNFROZEN_MARKET_DIMENSION")
        if run.get("tester_model") != "REAL_TICKS" or run.get("optimization") != 0:
            raise ValueError("TESTER_CONFIGURATION_NOT_FROZEN")
        scientific_config = {key: run[key] for key in SCIENTIFIC_CONFIG_KEYS if key in run}
        if run.get("scientific_config_fingerprint") != content_fingerprint(scientific_config):
            raise ValueError("SCIENTIFIC_CONFIG_FINGERPRINT_MISMATCH")
        if any(run.get(key) != 0 for key in ("use_remote", "use_cloud", "allow_live_trading")):
            raise ValueError("EXECUTION_SAFETY_FLAG_ENABLED")
        if run.get("context_status") != "PENDING_PRE_EXECUTION_FREEZE":
            raise ValueError("CONTEXT_MUST_BE_FROZEN_BEFORE_EXECUTION")
        if any(run.get(key) != "NOT_MATERIALIZED" for key in
               ("materialized_config_fingerprint", "output_routing_fingerprint")):
            raise ValueError("MATERIALIZED_FINGERPRINT_MUST_NOT_BE_FABRICATED")
    if split_counts != {"DEVELOPMENT": 4, "VALIDATION": 2, "HOLDOUT": 2}:
        raise ValueError("TEMPORAL_SPLIT_COUNTS_INVALID")
    _assert_no_outcomes(manifest)
    return {
        "valid": True,
        "manifest_hash": content_fingerprint(manifest),
        "planned_run_count": len(runs),
        "split_counts": split_counts,
        "holdout_inspected": False,
        "execution_ready": False,
        "execution_blockers": [
            "FUTURE_WINDOWS_NOT_ELAPSED",
            "POINT_IN_TIME_MARKET_AND_MACRO_CONTEXT_NOT_FROZEN",
            "MATERIALIZED_TESTER_CONFIG_AND_OUTPUT_ROUTING_NOT_CREATED",
            "HUMAN_CAMPAIGN_AUTHORIZATION_REQUIRED",
        ],
    }


def _window_lifecycle(window: dict[str, Any], now: datetime) -> str:
    start = date.fromisoformat(str(window["from"]))
    end = date.fromisoformat(str(window["to"]))
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    if now < start_at:
        return "WINDOW_PRE_REGISTERED"
    if now < end_at:
        return "WINDOW_IN_PROGRESS"
    return "WINDOW_COMPLETE_CONTEXT_PENDING"


def load_scientific_campaign(path: Path = MANIFEST_PATH,
                             now: datetime | None = None) -> dict[str, Any]:
    """Return a validated planner projection; performs no writes or execution."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validation = validate_campaign(manifest)
    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    observed_now = observed_now.astimezone(timezone.utc)
    runs = [{**run, "window_lifecycle": _window_lifecycle(run["window"], observed_now)}
            for run in manifest["planned_runs"]]
    windows_elapsed = all(run["window_lifecycle"] == "WINDOW_COMPLETE_CONTEXT_PENDING"
                          for run in runs)
    blockers = list(validation["execution_blockers"])
    if windows_elapsed:
        blockers.remove("FUTURE_WINDOWS_NOT_ELAPSED")
    return {
        "status": "PRE_REGISTERED_NOT_EXECUTABLE_YET",
        "read_only": True,
        "campaign_id": manifest["campaign_id"],
        "manifest_hash": validation["manifest_hash"],
        "robot": manifest["robot"],
        "planned_runs": runs,
        "planned_run_count": validation["planned_run_count"],
        "split_counts": validation["split_counts"],
        "holdout_inspected": False,
        "execution_ready": False,
        "execution_blockers": blockers,
        "legacy_evidence_policy": manifest["legacy_evidence_policy"],
        "tester_policy": manifest["tester_policy"],
        "safety": manifest["safety"],
    }


__all__ = ["MANIFEST_PATH", "load_scientific_campaign", "validate_campaign"]
