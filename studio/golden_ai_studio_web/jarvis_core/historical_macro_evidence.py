"""B4.8 read-only, point-in-time projection of curated primary releases."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .b2_contracts import content_fingerprint
from .historical_market_evidence import PRODUCTION_WINDOWS
from .scientific_memory import CanonicalScientificMemory, ScientificContractType
from .temporal_market_context import LeakageViolation, assert_no_outcome_features


DERIVATION_VERSION = "jarvis-b4.8-macro-event-v1"
SOURCE_PATH = Path(__file__).parent / "data" / "b4_8_official_releases.json"
HIGH_IMPACT_FAMILIES = frozenset({
    "FOMC_DECISION", "GDP", "PCE_INFLATION", "EMPLOYMENT_SITUATION",
    "PPI_INFLATION", "CPI_INFLATION",
})
SOURCE_HOSTS = frozenset({"www.federalreserve.gov", "www.bea.gov", "www.bls.gov"})


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_RELEASE_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def load_official_releases(path: Path = SOURCE_PATH) -> tuple[list[dict[str, Any]], str]:
    """Load reviewed transcriptions; never fetch or call a provider at runtime."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "b4.8-curated-primary-release-transcription-v1":
        raise ValueError("UNEXPECTED_SOURCE_SCHEMA")
    releases = payload.get("releases")
    if not isinstance(releases, list):
        raise ValueError("RELEASES_REQUIRED")
    assert_no_outcome_features(releases)
    seen: set[str] = set()
    normalized = []
    for item in releases:
        event_id = str(item["event_id"])
        if event_id in seen:
            raise ValueError("DUPLICATE_EVENT_ID")
        seen.add(event_id)
        url = str(item["url"])
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in SOURCE_HOSTS:
            raise ValueError("UNTRUSTED_SOURCE")
        released = _utc(item["released_at"]).isoformat()
        record = dict(item)
        record.update({
            "released_at_utc": released,
            "available_at": released,
            "observed_at": str(item["period_reference"]),
            "ingested_at": str(payload["curated_at"]),
            "source_artifact": str(path.name),
            "source_fingerprint": content_fingerprint(item),
            "point_in_time_status": "PRIMARY_RELEASE_TIME_VERIFIED_RAW_BYTES_MISSING",
            "provenance_class": "PRIMARY_SOURCE_POINT_IN_TIME",
            "surprise": "UNKNOWN",
        })
        normalized.append(record)
    normalized.sort(key=lambda row: (row["available_at"], row["event_id"]))
    return normalized, content_fingerprint(payload)


def build_macro_context(window_id: str, *, semantics: str, releases: list[dict[str, Any]],
                        source_fingerprint: str, technical_context: Mapping[str, Any] | None = None,
                        evaluation_time: str | None = None) -> dict[str, Any]:
    """Freeze ex-ante or post-window descriptive evidence, without robot results."""
    if window_id not in PRODUCTION_WINDOWS:
        raise ValueError("UNKNOWN_WINDOW")
    if semantics not in {"EX_ANTE_CONTEXT", "POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT"}:
        raise ValueError("UNKNOWN_TEMPORAL_SEMANTICS")
    assert_no_outcome_features(releases)
    first, last = PRODUCTION_WINDOWS[window_id]
    start = _utc(first + "T00:00:00+00:00")
    end = _utc((datetime.fromisoformat(last) + timedelta(days=1)).date().isoformat() + "T00:00:00+00:00")
    default_cutoff = start if semantics == "EX_ANTE_CONTEXT" else end
    cutoff = _utc(evaluation_time) if evaluation_time else default_cutoff
    if cutoff != default_cutoff:
        raise LeakageViolation("CUTOFF_MUST_MATCH_SEMANTIC_BOUNDARY")
    available = []
    for item in releases:
        released = _utc(item["available_at"])
        if released < _utc(item["released_at_utc"]):
            raise LeakageViolation("AVAILABLE_BEFORE_RELEASE_FORBIDDEN")
        if released <= cutoff:
            available.append(item)
    in_window = [item for item in available if start <= _utc(item["released_at_utc"]) < end]
    if semantics == "EX_ANTE_CONTEXT":
        in_window = []
    dimensions = {
        "US_MONETARY_POLICY": "KNOWN" if any(item["family"] == "FOMC_DECISION" for item in available) else "UNKNOWN",
        "US_INFLATION": "KNOWN" if any(item["family"] in {"PCE_INFLATION", "CPI_INFLATION", "PPI_INFLATION"} for item in available) else "UNKNOWN",
        "US_LABOR": "KNOWN" if any(item["family"] == "EMPLOYMENT_SITUATION" for item in available) else "UNKNOWN",
        "US_GROWTH": "KNOWN" if any(item["family"] == "GDP" for item in available) else "UNKNOWN",
        "USD_STATE": "UNKNOWN",
        "TREASURY_YIELD_STATE": "UNKNOWN",
    }
    event_risk = ("HIGH" if any(item["family"] in HIGH_IMPACT_FAMILIES for item in in_window)
                  else "UNKNOWN")
    technical = technical_context or {}
    record = {
        "window_id": window_id,
        "window": {"from": first, "to": last},
        "symbol": "XAUUSD", "timeframe": "M1",
        "test_run_id": technical.get("test_run_id", "UNKNOWN"),
        "technical_context_fingerprint": technical.get("context_fingerprint", "UNKNOWN"),
        "temporal_semantics": semantics,
        "evaluation_time": cutoff.isoformat(),
        "available_at_status": "RELEASE_TIME_ONLY_NOT_INGESTION_PROOF",
        "ingested_at": available[0]["ingested_at"] if available else "UNKNOWN",
        "macro_state": "PARTIAL" if any(value == "KNOWN" for value in dimensions.values()) else "UNKNOWN",
        "dimensions": dimensions,
        "event_risk_state": event_risk,
        "event_risk_method": "HIGH_IF_PRIMARY_HIGH_IMPACT_RELEASE_IN_WINDOW_ELSE_UNKNOWN",
        "events_in_window": [item["event_id"] for item in in_window],
        "evidence": [{key: item[key] for key in (
            "event_id", "family", "source", "url", "period_reference", "released_at_utc",
            "available_at", "ingested_at", "measure", "actual", "unit", "consensus", "surprise",
            "revision_status", "raw_artifact_status", "point_in_time_status", "source_fingerprint",
        )} for item in available],
        "source_artifact": SOURCE_PATH.name,
        "source_fingerprint": source_fingerprint,
        "input_fingerprints": [item["source_fingerprint"] for item in available],
        "derivation_version": DERIVATION_VERSION,
        "rule_fingerprint": content_fingerprint({"version": DERIVATION_VERSION,
                                                  "high_impact_families": sorted(HIGH_IMPACT_FAMILIES)}),
        "provenance_quality": "PARTIAL_RAW_SOURCE_BYTES_MISSING",
        "memory_lineage": {
            "relation": "SUPPLEMENTS_FROZEN_TECHNICAL_CONTEXT",
            "technical_context_fingerprint": technical.get("context_fingerprint", "UNKNOWN"),
            "reason": "PRIMARY_MACRO_RELEASE_EVIDENCE_AFTER_B4.7_FREEZE",
        },
        "frozen": True,
        "analysis_only": True,
        "trading_authorization": "NOT_GRANTED",
    }
    record["context_fingerprint"] = content_fingerprint(record)
    memory_record = CanonicalScientificMemory().prepare(
        ScientificContractType.EVIDENCE,
        f"B4.8 {window_id} {semantics} macro evidence {record['context_fingerprint']}",
        source="Official archived release transcription",
        artifact=SOURCE_PATH.name,
        created_at="UNKNOWN",
        observed_at=last,
        source_record_identity=f"{window_id}:{semantics}:{record['context_fingerprint']}",
        provenance={"context_fingerprint": record["context_fingerprint"],
                    "technical_context_fingerprint": record["technical_context_fingerprint"],
                    "evidence_class": "PRIMARY_SOURCE_POINT_IN_TIME"},
    )
    record["scientific_memory"] = {
        "scientific_id": memory_record.scientific_id,
        "contract_type": memory_record.contract_type,
        "canonical_boundary": "CanonicalScientificMemory",
        "persistence": "FILE_BACKED_ONLY_NO_MEMORY_DB_WRITE",
    }
    return record


def build_production_macro_contexts(technical_contexts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    releases, source_fingerprint = load_official_releases()
    by_window = {}
    for item in technical_contexts or []:
        window = item.get("window") or {}
        for window_id, (first, last) in PRODUCTION_WINDOWS.items():
            if str(window.get("from", ""))[:10] == first and str(window.get("to", ""))[:10] == last:
                by_window[window_id] = item
    return [build_macro_context(window_id, semantics=semantics, releases=releases,
                                source_fingerprint=source_fingerprint,
                                technical_context=by_window.get(window_id))
            for window_id in PRODUCTION_WINDOWS
            for semantics in ("EX_ANTE_CONTEXT", "POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT")]


__all__ = ["build_macro_context", "build_production_macro_contexts", "load_official_releases"]
