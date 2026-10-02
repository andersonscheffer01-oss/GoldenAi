"""Canonical, read-only Robot Intelligence projections.

This module composes the existing RobotCatalogReadModel with the B4.2 market
snapshot. It deliberately owns no database, discovery side effect, execution
authority, model score, or trading decision.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .temporal_market_context import (
    UNKNOWN,
    build_production_window_contexts,
    link_outcomes_after_context_freeze,
)
from .historical_market_evidence import (
    load_reconciled_post_window_outcomes,
    load_reconciled_temporal_contexts,
)
from .robot_artifact_identity import load_production_artifact_identity


REPERTOIRE_STATES = (
    "DISCOVERED", "CANDIDATE", "ACTIVE", "INACTIVE", "BLOCKED", "ARCHIVED"
)
EVIDENCE_TYPES = ("BACKTEST", "SIMULATION", "REPLAY", "FORWARD", "LIVE", "UNKNOWN")
LABEL_STATES = ("OBSERVED", "DERIVED", "INFERRED", "UNKNOWN")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", "UNKNOWN", "UNAVAILABLE"):
        return []
    return [value]


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get("data")
    return nested if isinstance(nested, dict) else value


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return str(value)


def _fingerprint(value: Any) -> str:
    raw = json.dumps(_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _field(value: Any, source: str, status: str = "OBSERVED",
           method: str = "CATALOG_OR_ARTIFACT") -> dict[str, Any]:
    return {"value": _json(value), "source": source, "status": status,
            "inference_method": method}


def _source_status(robot: dict[str, Any]) -> str:
    if robot.get("source_artifacts"):
        return "SOURCE_AVAILABLE"
    if robot.get("compiled_artifacts"):
        return "COMPILED_REFERENCE_ONLY"
    if robot.get("backtest_artifacts") or robot.get("test_runs"):
        return "HISTORICAL_ONLY"
    return "SOURCE_MISSING"


def normalize_robot_profile(robot: dict[str, Any]) -> dict[str, Any]:
    """Expose catalog facts with explicit authority and uncertainty."""
    status = str(robot.get("status") or "DISCOVERED").upper()
    status = status if status in REPERTOIRE_STATES else "UNKNOWN"
    metadata = {
        "strategy_type": _field(robot.get("strategy_family", "UNKNOWN"), "robot_catalog", "OBSERVED"),
        "symbols": _field(robot.get("supported_symbols") or ["UNKNOWN"], "robot_catalog"),
        "timeframes": _field(robot.get("supported_timeframes") or ["UNKNOWN"], "robot_catalog"),
        "sessions": _field(robot.get("session_preferences", "UNKNOWN"), "robot_catalog"),
        "regime": _field(robot.get("preferred_market_regime", "UNKNOWN"), "robot_catalog"),
        "volatility": _field("UNKNOWN", "not_observed", "UNKNOWN", "NO_HISTORICAL_LABEL"),
        "spread_sensitivity": _field(robot.get("spread_constraints", "UNKNOWN"), "robot_catalog"),
        "risk": _field(robot.get("risk_model", "UNKNOWN"), "robot_catalog"),
        "validation": _field(robot.get("evidence_summary", {}), "robot_catalog"),
    }
    return {
        "robot_id": robot.get("robot_id", "UNKNOWN"),
        "name": robot.get("name", "Unknown robot"),
        "version": robot.get("version", "UNKNOWN"),
        "repertoire_status": status,
        "trading_authorization": "NOT_GRANTED",
        "source_status": _source_status(robot),
        "evidence_status": "AVAILABLE" if robot.get("backtest_count") or robot.get("test_run_count") else "UNKNOWN",
        "metadata_authority": "USER_DECLARED_OVERRIDES_SYSTEM_INFERRED_OVERRIDES_EVIDENCE_DERIVED",
        "metadata": metadata,
        "source_artifacts": list(robot.get("source_artifacts") or []),
        "compiled_artifacts": list(robot.get("compiled_artifacts") or []),
        "campaign_associations": list(robot.get("campaign_associations") or []),
        "temporal_contexts": list(robot.get("temporal_contexts") or []),
        "evidence_counts": dict(robot.get("evidence_summary") or {}),
        "known_limitations": list(robot.get("known_limitations") or []),
        "conflicts": list(robot.get("conflicts") or []),
        "provenance": list(robot.get("provenance") or []),
        "user_overrides": list(robot.get("user_overrides") or []),
        "identity_basis": {
            "robot_id": robot.get("robot_id", "UNKNOWN"),
            "source_artifact_ids": [item.get("artifact_id") for item in robot.get("source_artifacts", [])],
            "compiled_artifact_ids": [item.get("artifact_id") for item in robot.get("compiled_artifacts", [])],
        },
    }


def _evidence_type(item: dict[str, Any]) -> str:
    raw = str(item.get("evidence_type") or item.get("evidence_class") or "").upper()
    mapping = {
        "BACKTEST_EVIDENCE": "BACKTEST", "OPTIMIZATION_EVIDENCE": "BACKTEST",
        "FORWARD_TEST_EVIDENCE": "FORWARD", "LIVE_OBSERVATION": "LIVE",
        "TEST_RESULT": "UNKNOWN",
    }
    return mapping.get(raw, raw if raw in EVIDENCE_TYPES else "UNKNOWN")


def _label(item: dict[str, Any], key: str) -> dict[str, Any]:
    value = item.get(key)
    if value in (None, "", "UNKNOWN", "UNAVAILABLE"):
        return {"value": "UNKNOWN", "status": "UNKNOWN", "method": "NOT_PRESENT"}
    explicit = str(item.get(f"{key}_label_status") or "OBSERVED").upper()
    status = explicit if explicit in LABEL_STATES else "UNKNOWN"
    return {"value": _json(value), "status": status, "method": str(item.get(f"{key}_label_method") or "ARTIFACT")}


def build_evidence_dataset(robots: list[dict[str, Any]],
                           temporal_contexts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize stored evidence without manufacturing associations or metrics."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_runs = 0
    unresolved = 0
    contexts = {str(item.get("test_run_id")): item for item in (temporal_contexts or [])
                if item.get("test_run_id")}
    for robot in robots:
        robot_id = str(robot.get("robot_id") or "UNKNOWN")
        items = list(robot.get("backtest_artifacts") or []) + list(robot.get("optimization_artifacts") or [])
        items += list(robot.get("test_runs") or [])
        for item in items:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("artifact_id") or item.get("test_run_id") or item.get("run_id") or "")
            fingerprint = str(item.get("artifact_hash") or item.get("sha256") or item.get("content_fingerprint") or evidence_id)
            dedupe_key = fingerprint or _fingerprint(item)
            if dedupe_key in seen:
                duplicate_runs += 1
                continue
            seen.add(dedupe_key)
            association = str(item.get("association_status") or ("VERIFIED" if robot_id != "UNKNOWN" else "UNRESOLVED")).upper()
            if association not in {"VERIFIED", "HIGH_CONFIDENCE"}:
                unresolved += 1
            rows.append({
                "evidence_id": evidence_id or "UNKNOWN",
                "robot_id": robot_id,
                "evidence_type": _evidence_type(item),
                "association_status": association,
                "association_confidence": item.get("association_confidence", "UNKNOWN"),
                "symbol": item.get("symbol", "UNKNOWN"),
                "timeframe": item.get("timeframe", "UNKNOWN"),
                "period": item.get("date_range") or item.get("period") or "UNKNOWN",
                "metrics": dict(item.get("metrics") or {}),
                "market_labels": {key: _label(item, key) for key in ("regime", "volatility", "session", "spread")},
                "temporal_context": contexts.get(str(item.get("test_run_id") or
                                                    item.get("run_id") or evidence_id), {
                    "context_status": "UNKNOWN",
                    "context_fingerprint": UNKNOWN,
                    "labels": {},
                }),
                "post_window_outcome": dict(item.get("metrics") or {}),
                "outcome_role": "POST_WINDOW_OUTCOME",
                "provenance": list(item.get("provenance") or []),
                "limitations": ["UNVERIFIED_ASSOCIATION"] if association not in {"VERIFIED", "HIGH_CONFIDENCE"} else [],
                "fingerprint": fingerprint or _fingerprint(item),
            })
    counts = Counter(row["evidence_type"] for row in rows)
    labeled = sum(1 for row in rows if any(label["status"] != "UNKNOWN" for label in row["market_labels"].values()))
    status = "INSUFFICIENT" if not rows else ("USABLE_FOR_DESCRIPTIVE_ANALYSIS" if labeled else "PARTIAL")
    return {
        "status": status,
        "rows": rows,
        "unique_samples": len(rows),
        "duplicate_runs_excluded": duplicate_runs,
        "resolved_associations": len(rows) - unresolved,
        "unresolved_associations": unresolved,
        "evidence_type_counts": dict(counts),
        "labeled_samples": labeled,
        "unlabeled_samples": len(rows) - labeled,
        "temporal_split_ready": bool(rows),
        "leakage_controls": ["FUTURE_OUTCOME_NOT_USED_AS_FEATURE", "EVIDENCE_TYPES_SEPARATED", "DUPLICATE_FINGERPRINT_EXCLUDED", "CONTEXT_FROZEN_BEFORE_OUTCOME_JOIN"],
        "temporal_context_count": len(contexts),
        "limitations": ["NO_EMPIRICAL_MATCHER", "UNKNOWN_MARKET_LABELS_RETAINED"],
    }


def _market_inputs(market: dict[str, Any], symbol: str, timeframe: str) -> dict[str, Any]:
    data = _payload(market)
    scanner = _payload(data.get("scanner"))
    result = (scanner.get("normalized_results") or scanner.get("results") or [None])[0]
    result = result if isinstance(result, dict) else {}
    return {
        "symbol": symbol or data.get("symbol") or result.get("symbol") or "UNKNOWN",
        "timeframe": timeframe or data.get("timeframe") or result.get("timeframe") or "UNKNOWN",
        "regime": data.get("regime") or result.get("market_regime") or "UNKNOWN",
        "volatility": data.get("volatility") or result.get("volatility") or "UNKNOWN",
        "spread": data.get("spread") or result.get("spread") or "UNKNOWN",
        "session": data.get("session") or result.get("session") or "UNKNOWN",
        "snapshot_id": market.get("snapshot_id") or data.get("snapshot_id") or "UNKNOWN",
    }


def _compare(current: Any, allowed: list[Any], label: str, matches: list[str], conflicts: list[str], unknowns: list[str]) -> None:
    values = [_norm(item) for item in allowed if _norm(item) not in {"", "unknown", "unavailable"}]
    current_value = _norm(current)
    if not values or current_value in {"", "unknown", "unavailable"}:
        unknowns.append(label)
    elif any(current_value == value or current_value in value or value in current_value for value in values):
        matches.append(label)
    else:
        conflicts.append(label)


def build_suitability(robots: list[dict[str, Any]], market: dict[str, Any],
                      symbol: str = "", timeframe: str = "") -> dict[str, Any]:
    current = _market_inputs(market, symbol, timeframe)
    results = []
    for robot in robots:
        matches: list[str] = []
        conflicts: list[str] = []
        unknowns: list[str] = []
        metadata = robot.get("metadata") or {}
        _compare(current["symbol"], _list((metadata.get("symbols") or {}).get("value")), "SYMBOL", matches, conflicts, unknowns)
        _compare(current["timeframe"], _list((metadata.get("timeframes") or {}).get("value")), "TIMEFRAME", matches, conflicts, unknowns)
        _compare(current["regime"], _list((metadata.get("regime") or {}).get("value")), "REGIME", matches, conflicts, unknowns)
        status = "CONTRADICTED" if conflicts else ("SUPPORTED" if matches and not unknowns else "PARTIAL" if matches else "UNKNOWN")
        evidence = robot.get("evidence_counts") or {}
        strength = "STRONG" if (evidence.get("BACKTEST_EVIDENCE", 0) or evidence.get("BACKTEST", 0)) and not unknowns else "LIMITED"
        results.append({
            "robot_id": robot.get("robot_id", "UNKNOWN"), "name": robot.get("name", "Unknown robot"),
            "repertoire_status": robot.get("repertoire_status", "UNKNOWN"),
            "trading_authorization": "NOT_GRANTED", "match_status": status,
            "match_type": "STRUCTURAL_AND_DECLARED" if matches else "INSUFFICIENT_EVIDENCE",
            "matches": matches, "contradictions": conflicts, "unknowns": unknowns,
            "evidence_strength": strength,
            "explanation": {
                "why": [f"{item} aligned with current market" for item in matches],
                "why_not": [f"{item} contradicted or unavailable" for item in conflicts + unknowns],
            },
            "provenance": {"market_snapshot_id": current["snapshot_id"], "robot_id": robot.get("robot_id", "UNKNOWN")},
        })
    return {
        "status": "ANALYSIS_ONLY", "market_context": current, "results": results,
        "empirical_matching": "NOT_IMPLEMENTED", "structural_matching": "ENABLED",
        "declared_matching": "ENABLED", "opaque_ai_score": False, "fake_probability": False,
        "approval_required_for_trading": True, "trading_authorization": "NOT_GRANTED",
    }


def build_robot_intelligence_snapshot(catalog: dict[str, Any], market: dict[str, Any] | None = None,
                                      symbol: str = "", timeframe: str = "",
                                      correlation_id: str = "") -> dict[str, Any]:
    """Build the B4.3 product read model from already-owned read models."""
    catalog_data = _payload(catalog)
    raw_robots = [item for item in catalog_data.get("robots", []) if isinstance(item, dict)]
    profiles = [normalize_robot_profile(item) for item in raw_robots]
    temporal_contexts = load_reconciled_temporal_contexts() or build_production_window_contexts()
    dataset = build_evidence_dataset(raw_robots, temporal_contexts)
    outcomes = []
    for robot in raw_robots:
        for item in list(robot.get("backtest_artifacts") or []) + list(robot.get("test_runs") or []):
            if isinstance(item, dict) and (item.get("test_run_id") or item.get("run_id")):
                outcomes.append({**item, "robot_id": robot.get("robot_id", UNKNOWN)})
    temporal_evidence = (load_reconciled_post_window_outcomes() or
                         link_outcomes_after_context_freeze(temporal_contexts, outcomes))
    artifact_identity = load_production_artifact_identity()
    market = market if isinstance(market, dict) else {"status": "SOURCE_DISABLED", "data": {}}
    suitability = build_suitability(profiles, market, symbol, timeframe)
    repertoire = Counter(item["repertoire_status"] for item in profiles)
    payload = {
        "read_only": True, "authority": "JarvisService", "status": "PARTIAL" if profiles else "UNKNOWN",
        "correlation_id": correlation_id or "UNKNOWN", "captured_at": _now(),
        "robots": profiles, "robot_count": len(profiles), "repertoire": dict(repertoire),
        "trading_authorization": "NOT_GRANTED", "evidence_dataset": dataset,
        "temporal_contexts": temporal_contexts,
        "temporal_evidence": temporal_evidence,
        "artifact_identity": artifact_identity,
        "suitability": suitability,
        "temporal_evidence_contract": {
            "market_snapshot_link": suitability["market_context"].get("snapshot_id", "UNKNOWN"),
            "outcome_link": "EVIDENCE_ROW_ID_OR_UNKNOWN", "immutable_context": True,
            "revision_semantics": "NEW_ARTIFACT_OR_NEW_SNAPSHOT; HISTORICAL_ROWS_NOT_REWRITTEN",
        },
        "security": {"analysis_only": True, "execution_authority": "NONE", "approval_boundary": "SEPARATE_FUTURE_GATE"},
        "provenance": {"catalog": "RobotCatalogReadModel", "market": "B4.2 MarketSnapshot", "transformation": "B4.3 read projection"},
    }
    payload["snapshot_id"] = "robot_intelligence_" + _fingerprint({key: payload[key] for key in ("robots", "evidence_dataset", "suitability", "correlation_id")})
    payload["dataset_provenance"] = {"fingerprint": _fingerprint(dataset), "source": "existing_catalog_evidence"}
    return {"ok": True, **payload}


__all__ = [
    "EVIDENCE_TYPES", "LABEL_STATES", "REPERTOIRE_STATES",
    "build_evidence_dataset", "build_robot_intelligence_snapshot",
    "build_suitability", "normalize_robot_profile",
]
