"""Bounded persistence for validated GoldenAI analysis results."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone


RESULT_SCHEMA_VERSION = 2
MAX_RESULT_BYTES = 512_000
MAX_PAGE_SIZE = 50
MAX_OFFSET = 100_000

_RESULT_FIELDS = frozenset({
    "ok", "status", "analysis_status", "contract_version", "analysis_id",
    "analysis_mode", "request_type", "analysis_style", "strategy_id",
    "result_kind", "opportunity_status", "signal_status", "execution_status",
    "timeframes_evaluated", "horizon_assessments", "opportunities", "symbol",
    "display_name", "provider", "provider_asset_id", "provider_symbol",
    "asset_class", "price_unit", "market_session", "quote", "instrument",
    "timeframe", "started_at", "completed_at", "data_cutoff", "snapshot_id",
    "snapshot", "analysis_status", "market_state", "market_structure",
    "directional_bias", "trend", "momentum", "breakout_context", "volatility",
    "important_levels", "multi_timeframe_summary", "macro_context",
    "news_event_risk", "support_levels", "resistance_levels", "confidence",
    "confidence_semantics", "algorithmic_strength", "entry_scenario",
    "primary_scenario", "alternative_scenario", "invalidation", "target_scenario",
    "summary", "risk_warnings", "risks", "evidence_references", "limitations",
    "temporal_restriction", "position_state", "sources", "context_availability",
    "temporal_authority", "provenance", "correlation_id", "execution_authority",
    "audit_correlation_id", "live_authorized", "order_sent", "position_mutated",
    "persistence", "model", "model_error_code",
    "validation_error_code", "response_validation", "reason_code",
})
_SENSITIVE_MARKERS = (
    "password", "secret", "token", "credential", "authorization", "cookie",
    "prompt", "chain_of_thought", "reasoning_trace", "private_key", "api_key",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ANALYSIS_MODES = {"INDEPENDENT", "STRATEGY"}


class GoldenAnalysisRepository:
    """Uses the existing TaskDatabase connection and its additive schema."""

    def __init__(self, task_database):
        self.database = task_database

    @staticmethod
    def _utc_epoch(value, *, date_end=False):
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                day = date.fromisoformat(raw)
                parsed = datetime.combine(day + (timedelta(days=1) if date_end else timedelta()),
                                          time.min, tzinfo=timezone.utc)
                return parsed.timestamp()
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("INVALID_DATE_FILTER") from exc
        if parsed.tzinfo is None:
            raise ValueError("FILTER_TIMEZONE_REQUIRED")
        return parsed.timestamp()

    @classmethod
    def _safe_value(cls, value, depth=0):
        if depth > 10:
            raise ValueError("RESULT_NESTING_LIMIT")
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("NONFINITE_RESULT_NUMBER")
            return value
        if isinstance(value, str):
            return value[:10_000]
        if isinstance(value, dict):
            cleaned = {}
            for key, item in list(value.items())[:500]:
                name = str(key)[:128]
                lowered = name.casefold().replace("-", "_")
                if any(marker in lowered for marker in _SENSITIVE_MARKERS):
                    continue
                cleaned[name] = cls._safe_value(item, depth + 1)
            return cleaned
        if isinstance(value, (list, tuple)):
            if len(value) > 2_000:
                raise ValueError("RESULT_LIST_LIMIT")
            return [cls._safe_value(item, depth + 1) for item in value]
        raise ValueError("UNSUPPORTED_RESULT_VALUE")

    @classmethod
    def _validated_result(cls, result):
        if not isinstance(result, dict) or result.get("contract_version") != "golden-analysis-v2":
            raise ValueError("UNSUPPORTED_ANALYSIS_CONTRACT")
        if result.get("analysis_mode") not in _ANALYSIS_MODES:
            raise ValueError("INVALID_ANALYSIS_MODE")
        analysis_id = str(result.get("analysis_id") or "")
        if not analysis_id.startswith("panel_analysis_") or not _IDENTIFIER.fullmatch(analysis_id):
            raise ValueError("INVALID_ANALYSIS_ID")
        payload = {key: value for key, value in result.items() if key in _RESULT_FIELDS}
        payload["persistence"] = {"status": "PERSISTED", "persisted": True}
        payload = cls._safe_value(payload)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("RESULT_SIZE_LIMIT")
        return payload, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def save(self, result, audit_correlation_id=""):
        candidate = dict(result) if isinstance(result, dict) else result
        correlation_id = str(audit_correlation_id or
                             (candidate.get("audit_correlation_id")
                              if isinstance(candidate, dict) else "") or
                             (candidate.get("correlation_id")
                              if isinstance(candidate, dict) else ""))[:160]
        if isinstance(candidate, dict) and correlation_id:
            candidate["audit_correlation_id"] = correlation_id
        payload, encoded, digest = self._validated_result(candidate)
        started_raw = str(payload.get("started_at") or payload.get("completed_at") or "")
        completed_raw = str(payload.get("completed_at") or started_raw)
        created_at = self._utc_epoch(started_raw)
        completed_at = self._utc_epoch(completed_raw)
        if created_at is None or completed_at is None:
            raise ValueError("ANALYSIS_TIMESTAMPS_REQUIRED")
        symbol = str(payload.get("symbol") or "").strip().upper()[:64]
        provider_asset_id = str(payload.get("provider_asset_id") or "").strip()[:96]
        provider_symbol = str(payload.get("provider_symbol") or symbol).strip()[:64]
        source_provider = str(payload.get("provider") or "UNKNOWN").strip()[:40]
        asset_class = str(payload.get("asset_class") or "UNKNOWN").strip().upper()[:24]
        timeframe = str(payload.get("timeframe") or "UNKNOWN").strip().upper()[:8]
        mode = str(payload.get("analysis_mode") or "")
        style = str(payload.get("analysis_style") or "AUTO")[:24]
        status = str(payload.get("status") or "UNKNOWN").strip().upper()[:40]
        model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        snapshot_id = str(payload.get("snapshot_id") or "")[:160]
        model_provider = str(model.get("provider") or "NONE")[:80]
        model_name = str(model.get("name") or "NONE")[:120]
        row = (payload["analysis_id"], RESULT_SCHEMA_VERSION, created_at, completed_at,
               started_raw[:80], completed_raw[:80], symbol, provider_asset_id,
               provider_symbol, source_provider, asset_class, timeframe, mode, style,
               status, str(payload.get("result_kind") or "ANALYSIS")[:32], snapshot_id,
               correlation_id, model_provider, model_name, encoded, digest)
        with self.database._lock, self.database.connect() as db:
            existing = db.execute(
                "SELECT result_sha256 FROM golden_analysis_results WHERE analysis_id=?",
                (payload["analysis_id"],)).fetchone()
            if existing:
                if existing[0] == digest:
                    return {"persisted": True, "duplicate": True,
                            "analysis_id": payload["analysis_id"], "result": payload}
                raise ValueError("ANALYSIS_ID_CONFLICT")
            db.execute("""INSERT INTO golden_analysis_results(
                analysis_id,schema_version,created_at,completed_at,created_at_raw,
                completed_at_raw,symbol,provider_asset_id,provider_symbol,source_provider,
                asset_class,timeframe,analysis_mode,analysis_style,analysis_status,result_kind,
                snapshot_id,correlation_id,model_provider,model_name,result_json,result_sha256
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
        return {"persisted": True, "duplicate": False,
                "analysis_id": payload["analysis_id"], "result": payload}

    @staticmethod
    def _record(row, include_result=False):
        record = {
            "analysis_id": row["analysis_id"],
            "schema_version": row["schema_version"],
            "created_at": row["created_at_raw"],
            "completed_at": row["completed_at_raw"],
            "symbol": row["symbol"],
            "provider_asset_id": row["provider_asset_id"],
            "provider_symbol": row["provider_symbol"],
            "source_provider": row["source_provider"],
            "asset_class": row["asset_class"],
            "timeframe": row["timeframe"],
            "analysis_mode": row["analysis_mode"],
            "analysis_style": row["analysis_style"],
            "status": row["analysis_status"],
            "result_kind": row["result_kind"],
            "snapshot_id": row["snapshot_id"],
            "correlation_id": row["correlation_id"],
            "model": {"provider": row["model_provider"], "name": row["model_name"]},
        }
        if include_result:
            record["analysis"] = json.loads(row["result_json"])
        return record

    def get(self, analysis_id):
        identifier = str(analysis_id or "").strip()
        if not _IDENTIFIER.fullmatch(identifier):
            raise ValueError("INVALID_ANALYSIS_ID")
        with self.database.connect(rows=True) as db:
            row = db.execute("SELECT * FROM golden_analysis_results WHERE analysis_id=?",
                             (identifier,)).fetchone()
        return self._record(row, include_result=True) if row else None

    def list(self, *, symbol="", analysis_mode="", date_from="", date_to="",
             status="", limit=25, offset=0):
        if (isinstance(limit, bool) or not isinstance(limit, int)
                or not 1 <= limit <= MAX_PAGE_SIZE
                or isinstance(offset, bool) or not isinstance(offset, int)
                or not 0 <= offset <= MAX_OFFSET):
            raise ValueError("INVALID_PAGINATION")
        symbol = str(symbol or "").strip().upper()[:64]
        mode = str(analysis_mode or "").strip().upper()
        status = str(status or "").strip().upper()
        if mode and mode not in _ANALYSIS_MODES:
            raise ValueError("INVALID_ANALYSIS_MODE")
        if status and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", status):
            raise ValueError("INVALID_ANALYSIS_STATUS")
        start = self._utc_epoch(date_from) if date_from else None
        end = self._utc_epoch(date_to, date_end=True) if date_to else None
        if start is not None and end is not None and start >= end:
            raise ValueError("INVALID_DATE_RANGE")
        clauses, params = [], []
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol)
        if mode:
            clauses.append("analysis_mode=?")
            params.append(mode)
        if status:
            clauses.append("analysis_status=?")
            params.append(status)
        if start is not None:
            clauses.append("created_at>=?")
            params.append(start)
        if end is not None:
            clauses.append("created_at<?")
            params.append(end)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        columns = ("analysis_id,schema_version,created_at,completed_at,created_at_raw,"
                   "completed_at_raw,symbol,provider_asset_id,provider_symbol,source_provider,"
                   "asset_class,timeframe,analysis_mode,analysis_style,analysis_status,result_kind,"
                   "snapshot_id,correlation_id,model_provider,model_name,result_json,result_sha256")
        with self.database.connect(rows=True) as db:
            total = db.execute("SELECT COUNT(*) FROM golden_analysis_results" + where,
                               params).fetchone()[0]
            rows = db.execute(
                f"SELECT {columns} FROM golden_analysis_results{where} "
                "ORDER BY created_at DESC, analysis_id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset)).fetchall()
        return {"items": [self._record(row) for row in rows], "total": total,
                "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}


__all__ = ["GoldenAnalysisRepository", "RESULT_SCHEMA_VERSION"]
