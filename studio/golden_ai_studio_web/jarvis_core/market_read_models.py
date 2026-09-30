"""Canonical, read-only market intelligence projections.

Golden remains the calculation donor.  This module only normalizes bounded
observations for Jarvis UI/Core consumers; it never imports MT5, calls a
provider, writes a database, or authorizes an operation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .b2_contracts import content_fingerprint


UNKNOWN = "UNKNOWN"
UNAVAILABLE = "UNAVAILABLE"
SOURCE_DISABLED = "SOURCE_DISABLED"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def payload_of(envelope: Any) -> dict[str, Any]:
    value = _dict(envelope)
    payload = value.get("data")
    return _dict(payload) if isinstance(payload, dict) else value


def status_of(envelope: Any) -> str:
    value = _dict(envelope)
    status = str(value.get("availability") or value.get("status") or "").upper()
    if status in {SOURCE_DISABLED, "DISABLED_BY_PROFILE"}:
        return SOURCE_DISABLED
    if status in {UNAVAILABLE, "OFFLINE", "NOT_FOUND", "ERROR"}:
        return UNAVAILABLE
    payload = payload_of(value)
    nested = str(payload.get("status") or "").upper()
    if nested in {SOURCE_DISABLED, "DISABLED_BY_PROFILE"}:
        return SOURCE_DISABLED
    if nested in {UNAVAILABLE, "OFFLINE", "NOT_FOUND", "ERROR"}:
        return UNAVAILABLE
    if value.get("ok") is False and not payload:
        return UNAVAILABLE
    return "AVAILABLE"


def freshness_of(envelope: Any) -> str:
    value = _dict(envelope)
    state = str(value.get("freshness") or "").upper()
    if state:
        return state
    provenance = _dict(value.get("provenance"))
    return str(provenance.get("freshness_state") or UNKNOWN).upper()


def _source_meta(envelope: Any, source_name: str) -> dict[str, Any]:
    value = _dict(envelope)
    provenance = _dict(value.get("provenance"))
    return {
        "status": status_of(value),
        "freshness": freshness_of(value),
        "source": str(provenance.get("provider") or
                       provenance.get("source_module") or source_name),
        "observed_at": value.get("observed_at") or provenance.get("observed_at"),
        "received_at": value.get("received_at") or provenance.get("received_at"),
        "content_fingerprint": value.get("content_fingerprint") or
        provenance.get("content_fingerprint") or UNKNOWN,
    }


def _dedupe(rows: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows if isinstance(rows, list) else []:
        row = _dict(item)
        identity = "|".join(str(row.get(key) or "").strip().casefold() for key in keys)
        if not identity.strip("|") or identity in seen:
            continue
        seen.add(identity)
        result.append(row)
    return result


def normalize_news(rows: Any) -> list[dict[str, Any]]:
    result = []
    for row in _dedupe(rows, ("url", "title", "published_at")):
        result.append({
            "title": str(row.get("title") or UNKNOWN),
            "source": str(row.get("source") or UNKNOWN),
            "published_at": row.get("published_at") or UNKNOWN,
            "url": row.get("url") or UNKNOWN,
            "asset_relevance": row.get("asset_relevance") or row.get("topic") or UNKNOWN,
            "sentiment": row.get("sentiment") if "sentiment" in row else UNKNOWN,
            "provenance": row.get("provenance") or row.get("source") or UNKNOWN,
        })
    return result


def normalize_macro(rows: Any) -> list[dict[str, Any]]:
    result = []
    for row in _dedupe(rows, ("id", "series", "name", "timestamp")):
        result.append({
            "series": row.get("series") or row.get("id") or UNKNOWN,
            "name": row.get("name") or UNKNOWN,
            "value": row.get("value", UNKNOWN),
            "previous": row.get("previous", UNKNOWN),
            "units": row.get("unit") or row.get("units") or UNKNOWN,
            "observation_timestamp": row.get("date") or row.get("observation_timestamp") or UNKNOWN,
            "retrieved_at": row.get("retrieved_at") or row.get("updated_at") or UNKNOWN,
            "status": row.get("status") or "OBSERVED",
            "source": row.get("source") or UNKNOWN,
            "derived": False,
        })
    return result


def normalize_events(rows: Any) -> list[dict[str, Any]]:
    result = []
    for row in _dedupe(rows, ("date", "scheduled_at", "event", "currency")):
        result.append({
            "currency": row.get("currency") or UNKNOWN,
            "event": row.get("event") or UNKNOWN,
            "scheduled_at": row.get("scheduled_at") or row.get("date") or UNKNOWN,
            "importance": row.get("importance", UNKNOWN),
            "actual": row.get("actual", UNKNOWN),
            "forecast": row.get("forecast", UNKNOWN),
            "previous": row.get("previous", UNKNOWN),
            "status": row.get("status") or UNKNOWN,
            "source": row.get("source") or UNKNOWN,
        })
    return result


def session_observation(now: datetime | None = None) -> dict[str, Any]:
    """Return display-only session state using IANA timezone/DST rules."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    instant = instant.astimezone(timezone.utc)
    windows = {
        "ASIA": ("Asia/Tokyo", 9, 18),
        "LONDON": ("Europe/London", 8, 17),
        "NEW_YORK": ("America/New_York", 8, 17),
    }
    sessions = {}
    for name, (zone, start_hour, end_hour) in windows.items():
        local = instant.astimezone(ZoneInfo(zone))
        sessions[name] = {
            "active": start_hour <= local.hour < end_hour,
            "timezone": zone,
            "local_time": local.isoformat(),
            "utc_offset": local.utcoffset().total_seconds() / 3600,
        }
    active = [name for name, item in sessions.items() if item["active"]]
    if sessions["LONDON"]["active"] and sessions["NEW_YORK"]["active"]:
        label = "LONDON_NEW_YORK_OVERLAP"
    elif active:
        label = active[0]
    else:
        label = "OFF_SESSION"
    return {"label": label, "active": active, "sessions": sessions,
            "observed_at": instant.isoformat(), "source": "IANA_TZ_DATABASE",
            "derived": True}


def _performance(validation: dict[str, Any]) -> dict[str, Any]:
    rows = validation.get("history") if isinstance(validation, dict) else []
    rows = rows if isinstance(rows, list) else []
    evidence_counts = Counter(str(row.get("evidence_class") or
                                 row.get("evidence_type") or UNKNOWN).upper()
                              for row in rows if isinstance(row, dict))
    metrics: dict[str, Any] = {}
    for key in ("win_rate", "expectancy", "profit_factor", "drawdown", "risk_reward"):
        values = [row[key] for row in rows if isinstance(row, dict) and key in row
                  and isinstance(row[key], (int, float))]
        if values:
            metrics[key] = round(sum(values) / len(values), 6)
    limitations = []
    if len(rows) < 30:
        limitations.append("SAMPLE_BELOW_30")
    if not metrics:
        limitations.append("NO_VERIFIED_METRICS_IN_SOURCE")
    return {
        "subject": "Golden validation history",
        "evidence_type_counts": dict(evidence_counts),
        "sample_count": len(rows),
        "period": {"from": rows[-1].get("timestamp") if rows and isinstance(rows[-1], dict) else UNKNOWN,
                    "to": rows[0].get("timestamp") if rows and isinstance(rows[0], dict) else UNKNOWN},
        "metrics": metrics,
        "limitations": limitations,
        "status": "AVAILABLE" if rows else UNAVAILABLE,
        "source": "mt5_backtest.py",
        "read_only": True,
    }


def build_market_intelligence_snapshot(*, overview: Any, chart: Any,
                                       scanner: Any, risk: Any, validation: Any,
                                       symbol: str, timeframe: str,
                                       correlation_id: str,
                                       captured_at: str | None = None) -> dict[str, Any]:
    """Build one coherent read model from already-observed donor payloads."""
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    overview_data = payload_of(overview)
    chart_data = payload_of(chart)
    scanner_data = payload_of(scanner)
    risk_data = payload_of(risk)
    validation_data = payload_of(validation)
    sources = {
        "market": _source_meta(overview, "market_data.py"),
        "technical": _source_meta(chart, "market_data.py"),
        "scanner": _source_meta(scanner, "golden_scanner.py"),
        "risk": _source_meta(risk, "risk_engine.py"),
        "validation": _source_meta(validation, "mt5_backtest.py"),
    }
    news = normalize_news(overview_data.get("news"))
    macro = _dict(overview_data.get("macro"))
    macro_rows = normalize_macro(macro.get("indicators"))
    events = normalize_events(overview_data.get("economic_calendar"))
    assets = [dict(item) for item in overview_data.get("assets", [])
              if isinstance(item, dict)]
    normalized_results = scanner_data.get("normalized_results") or scanner_data.get("results") or []
    normalized_results = [dict(item) for item in normalized_results if isinstance(item, dict)]
    selected = normalized_results[0] if normalized_results else {}
    performance = _performance(validation_data)
    sessions = overview_data.get("sessions")
    sessions = sessions if sessions not in (None, "", UNKNOWN) else session_observation()
    status_values = [item["status"] for item in sources.values()]
    if all(value == SOURCE_DISABLED for value in status_values):
        overall_status = SOURCE_DISABLED
    elif any(value == "AVAILABLE" for value in status_values):
        overall_status = "PARTIAL" if any(value != "AVAILABLE" for value in status_values) else "AVAILABLE"
    else:
        overall_status = UNAVAILABLE
    snapshot_seed = {
        "symbol": symbol, "timeframe": timeframe, "correlation_id": correlation_id,
        "market": overview_data, "technical": chart_data, "scanner": normalized_results,
        "risk": risk_data, "validation": validation_data,
    }
    snapshot_id = f"market_snapshot_{content_fingerprint(snapshot_seed)[:24]}"
    scanner_model = {
        "normalized_results": normalized_results,
        "score_semantics": "SCORE_NOT_PROBABILITY",
        "readiness_semantics": "ENTRY_READY_DOES_NOT_AUTHORIZE_TRADE",
        "status": sources["scanner"]["status"],
    }
    validation_model = {
        "stages": validation_data.get("stages") or validation_data.get("history") or [],
        "history": validation_data.get("history") or [],
        "evidence_classes": validation_data.get("evidence_classes") or [],
        "unknown_semantics": "UNKNOWN means insufficient or missing evidence; it is not FAIL",
        "status": sources["validation"]["status"],
    }
    risk_model = {
        **risk_data,
        "market_risk": risk_data.get("market_risk") or risk_data.get("spread_constraints", UNKNOWN),
        "setup_risk": risk_data.get("setup_risk") or risk_data.get("risk_state", UNKNOWN),
        "portfolio_risk": risk_data.get("portfolio_risk") or risk_data.get("exposure", UNKNOWN),
        "event_risk": risk_data.get("event_risk", UNKNOWN),
        "execution_risk": risk_data.get("execution_risk", UNKNOWN),
        "pretrade_context": risk_data.get("pretrade_context") or {
            "strategy_signal": selected.get("selected_setup", UNKNOWN),
            "market_regime": selected.get("market_regime", UNKNOWN),
            "event_risk": risk_data.get("event_risk", UNKNOWN),
            "spread": risk_data.get("spread_constraints", UNKNOWN),
            "correlation": risk_data.get("exposure", UNKNOWN),
            "portfolio_risk": risk_data.get("portfolio_risk", UNKNOWN),
            "execution_authorized": False,
        },
        "status": sources["risk"]["status"],
    }
    matcher_precursors = {
        "regime": selected.get("market_regime", UNKNOWN),
        "setup": selected.get("selected_setup", UNKNOWN),
        "strategy_type": selected.get("mode", UNKNOWN),
        "symbol": symbol,
        "timeframe": timeframe,
        "volatility": selected.get("volatility", chart_data.get("atr", UNKNOWN)),
        "spread": selected.get("spread", UNKNOWN),
        "session": selected.get("session", UNKNOWN),
        "risk": risk_data.get("risk_state", risk_data.get("status", UNKNOWN)),
        "validation": validation_model["status"],
        "performance": performance["status"],
    }
    payload = {
        "ok": True,
        "read_only": True,
        "authority": "JarvisService",
        "status": overall_status,
        "snapshot_id": snapshot_id,
        "captured_at": captured_at,
        "correlation_id": correlation_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "market_map": assets,
        "market_overview": {
            "timestamp": overview_data.get("updated_at") or UNKNOWN,
            "assets": assets,
            "market_state": selected.get("market_regime", UNKNOWN),
            "macro": macro_rows,
            "news": news,
            "events": events,
            "sessions": sessions,
            "opportunities": normalized_results,
            "freshness": sources["market"]["freshness"],
            "provenance": sources["market"],
            "availability": sources["market"]["status"],
        },
        "technical_state": chart_data,
        "support_resistance": chart_data.get("levels", []),
        "structure_events": chart_data.get("structure_events", []),
        "news": news,
        "macro_indicators": macro_rows,
        "economic_calendar": events,
        "market_sessions": sessions,
        "currency_strength": overview_data.get("currency_strength", UNKNOWN),
        "gold": overview_data.get("gold", UNKNOWN),
        "gold_levels": overview_data.get("gold_levels", UNKNOWN),
        "scanner": scanner_model,
        "risk": risk_model,
        "validation": validation_model,
        "performance": performance,
        "source_integrity": {"sources": overview_data.get("sources", []),
                             "configured": overview_data.get("configured", {}),
                             "families": sources},
        "freshness": {name: value["freshness"] for name, value in sources.items()},
        "provenance": {"source_module": "market_read_models.py",
                        "provider": "Golden donor projections",
                        "correlation_id": correlation_id,
                        "captured_at": captured_at,
                        "transformation": "NORMALIZE_ONLY",
                        "derived_fields": ["performance", "matcher_precursors"],
                        "source_families": sources},
        "source_availability": sources,
        "robot_matcher_precursors": matcher_precursors,
        "matcher_authority": "NOT_IMPLEMENTED_IN_B4_2",
        "execution_authority": "NONE",
    }
    return payload


__all__ = [
    "SOURCE_DISABLED", "UNKNOWN", "UNAVAILABLE", "build_market_intelligence_snapshot",
    "normalize_events", "normalize_macro", "normalize_news", "payload_of", "session_observation", "status_of",
]
