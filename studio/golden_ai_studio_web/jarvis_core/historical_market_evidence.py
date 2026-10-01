"""Canonical historical market evidence contracts for B4.7.

This module is deliberately independent from MT5 initialization and from
robot outcomes.  Callers provide already-read rows, which makes normalization
and label derivation deterministic and testable without starting a terminal.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .b2_contracts import content_fingerprint, utc_now
from .temporal_market_context import (
    UNKNOWN,
    assert_no_outcome_features,
    build_temporal_market_snapshot,
)


SCHEMA_VERSION = "jarvis-historical-market-artifact-v1"
LABEL_METHOD_VERSION = "jarvis-window-descriptive-market-labels-v1"
CANONICAL_SYMBOL = "XAUUSD"
CANONICAL_TIMEFRAME = "M1"
UTC = timezone.utc

PRODUCTION_WINDOWS = {
    "R1": ("2026-08-24", "2026-08-28"),
    "R2": ("2026-09-01", "2026-09-05"),
    "R3": ("2026-09-08", "2026-09-12"),
}


class HistoricalEvidenceError(ValueError):
    """Raised when historical evidence violates its explicit contract."""


@dataclass(frozen=True)
class HistoricalBar:
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: float | int | None = None
    spread: float | int | None = None
    real_volume: float | int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalMarketArtifact:
    artifact_id: str
    symbol: str
    timeframe: str
    start_time: str
    end_time: str
    source: str
    source_version: str
    retrieved_at: str
    source_timezone: str
    canonical_timezone: str
    row_count: int
    schema_version: str
    raw_fingerprint: str
    normalized_fingerprint: str
    availability_semantics: str
    provenance: dict[str, Any]
    bars: tuple[HistoricalBar, ...] = ()
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_bars: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["bars"] = [bar.to_dict() for bar in self.bars] if include_bars else []
        return payload


def _row_value(row: Any, *names: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        for name in names:
            if name in row:
                return row[name]
    for name in names:
        if hasattr(row, name):
            return getattr(row, name)
    return default


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime.fromtimestamp(float(value), tz=UTC)
    else:
        raw = str(value or "").strip().replace("Z", "+00:00")
        if not raw:
            raise HistoricalEvidenceError("TIMESTAMP_REQUIRED")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise HistoricalEvidenceError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


def _number(value: Any, *, allow_none: bool = True) -> float | int | None:
    if value in (None, "") and allow_none:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalEvidenceError("INVALID_NUMERIC_FIELD") from exc
    if not math.isfinite(number):
        raise HistoricalEvidenceError("NON_FINITE_NUMERIC_FIELD")
    return number


def _raw_row(row: Any) -> dict[str, Any]:
    return {
        "time": _row_value(row, "time", "timestamp", "timestamp_utc"),
        "open": _row_value(row, "open"),
        "high": _row_value(row, "high"),
        "low": _row_value(row, "low"),
        "close": _row_value(row, "close"),
        "tick_volume": _row_value(row, "tick_volume", "volume"),
        "spread": _row_value(row, "spread"),
        "real_volume": _row_value(row, "real_volume"),
    }


def _normalize_row(row: Any) -> HistoricalBar:
    timestamp = _timestamp(_row_value(row, "time", "timestamp", "timestamp_utc"))
    values = {
        "open": _number(_row_value(row, "open"), allow_none=False),
        "high": _number(_row_value(row, "high"), allow_none=False),
        "low": _number(_row_value(row, "low"), allow_none=False),
        "close": _number(_row_value(row, "close"), allow_none=False),
        "tick_volume": _number(_row_value(row, "tick_volume", "volume")),
        "spread": _number(_row_value(row, "spread")),
        "real_volume": _number(_row_value(row, "real_volume")),
    }
    if values["high"] < max(values["open"], values["close"]):
        raise HistoricalEvidenceError("OHLC_HIGH_INVARIANT")
    if values["low"] > min(values["open"], values["close"]):
        raise HistoricalEvidenceError("OHLC_LOW_INVARIANT")
    if values["low"] <= 0 or values["open"] <= 0 or values["high"] <= 0 or values["close"] <= 0:
        raise HistoricalEvidenceError("NON_POSITIVE_OHLC")
    if any(value is not None and value < 0 for value in (values["tick_volume"], values["spread"], values["real_volume"])):
        raise HistoricalEvidenceError("NEGATIVE_VOLUME_OR_SPREAD")
    return HistoricalBar(timestamp_utc=timestamp.isoformat(), **values)


def assess_bar_quality(bars: Iterable[HistoricalBar], invalid_rows: int = 0) -> dict[str, Any]:
    rows = list(bars)
    timestamps = [datetime.fromisoformat(row.timestamp_utc).timestamp() for row in rows]
    duplicates = sorted({str(ts) for ts in timestamps if timestamps.count(ts) > 1})
    monotonic = timestamps == sorted(timestamps) and len(duplicates) == 0
    missing_intervals = []
    for previous, current in zip(timestamps, timestamps[1:]):
        gap_minutes = int(round((current - previous) / 60))
        if gap_minutes > 1:
            missing_intervals.append({
                "from": datetime.fromtimestamp(previous + 60, tz=UTC).isoformat(),
                "to": datetime.fromtimestamp(current - 60, tz=UTC).isoformat(),
                "estimated_missing_bars": max(0, gap_minutes - 1),
                "classification": "MARKET_CLOSURE_OR_SOURCE_GAP",
            })
    if invalid_rows or duplicates or not monotonic:
        status = "FAIL"
    elif missing_intervals:
        status = "PASS_WITH_MARKET_GAPS"
    else:
        status = "PASS"
    return {
        "quality_status": status,
        "observed_bars": len(rows),
        "expected_or_estimated_bars": len(rows) + sum(item["estimated_missing_bars"] for item in missing_intervals),
        "invalid_rows": int(invalid_rows),
        "duplicate_timestamps": duplicates,
        "monotonic_timestamps": monotonic,
        "missing_intervals": missing_intervals,
        "weekend_or_closure_gaps_explicit": True,
    }


def build_historical_artifact(
    rows: Iterable[Any],
    *,
    symbol: str = CANONICAL_SYMBOL,
    timeframe: str = CANONICAL_TIMEFRAME,
    source: str,
    source_version: str = "UNKNOWN",
    source_timezone: str = "UNKNOWN",
    retrieved_at: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> HistoricalMarketArtifact:
    if str(symbol) != CANONICAL_SYMBOL:
        raise HistoricalEvidenceError("SYMBOL_IDENTITY_REQUIRED_XAUUSD")
    if str(timeframe).upper() != CANONICAL_TIMEFRAME:
        raise HistoricalEvidenceError("TIMEFRAME_IDENTITY_REQUIRED_M1")
    raw_rows = list(rows)
    raw_payload = [_raw_row(row) for row in raw_rows]
    normalized: list[HistoricalBar] = []
    invalid_rows = 0
    for row in raw_rows:
        try:
            normalized.append(_normalize_row(row))
        except HistoricalEvidenceError:
            invalid_rows += 1
    normalized.sort(key=lambda item: item.timestamp_utc)
    if not normalized:
        raise HistoricalEvidenceError("NO_VALID_HISTORICAL_BARS")
    raw_fingerprint = content_fingerprint({"symbol": symbol, "timeframe": timeframe, "rows": raw_payload})
    normalized_fingerprint = content_fingerprint([row.to_dict() for row in normalized])
    start_time = normalized[0].timestamp_utc
    end_time = normalized[-1].timestamp_utc
    artifact_id = "historical_market_" + content_fingerprint({
        "symbol": symbol, "timeframe": timeframe, "raw_fingerprint": raw_fingerprint,
        "normalized_fingerprint": normalized_fingerprint,
    })[:32]
    quality = assess_bar_quality(normalized, invalid_rows)
    metadata = dict(provenance or {})
    metadata.update({
        "artifact_contract": SCHEMA_VERSION,
        "raw_rows_preserved": True,
        "robot_results_excluded": True,
    })
    return HistoricalMarketArtifact(
        artifact_id=artifact_id, symbol=symbol, timeframe=CANONICAL_TIMEFRAME,
        start_time=start_time, end_time=end_time, source=str(source),
        source_version=str(source_version), retrieved_at=str(retrieved_at or utc_now()),
        source_timezone=str(source_timezone), canonical_timezone="UTC",
        row_count=len(normalized), schema_version=SCHEMA_VERSION,
        raw_fingerprint=raw_fingerprint, normalized_fingerprint=normalized_fingerprint,
        availability_semantics="COMPLETED_M1_BAR_AVAILABLE_AFTER_BAR_CLOSE",
        provenance=metadata, bars=tuple(normalized), quality=quality,
    )


def _returns(bars: list[HistoricalBar]) -> list[float]:
    return [math.log(current.close / previous.close)
            for previous, current in zip(bars, bars[1:])
            if previous.close > 0 and current.close > 0]


def _label(name: str, value: str, *, available_at: str, artifact: HistoricalMarketArtifact,
           inputs: list[str], evidence_quality: str = "VERIFIED",
           valid_from: str | None = None, valid_to: str | None = None) -> dict[str, Any]:
    return {
        "label": value,
        "status": "DERIVED",
        "method": "WINDOW_DESCRIPTIVE",
        "method_version": LABEL_METHOD_VERSION,
        "inputs": inputs,
        "valid_range": {"from": valid_from or artifact.start_time,
                        "to": valid_to or artifact.end_time},
        "cutoff": available_at,
        "available_at": available_at,
        "confidence": None,
        "evidence_quality": evidence_quality,
        "provenance": {"field": name, "artifact_id": artifact.artifact_id,
                        "normalized_fingerprint": artifact.normalized_fingerprint},
    }


def _trend_label(bars: list[HistoricalBar], available_at: str, artifact: HistoricalMarketArtifact) -> dict[str, Any]:
    returns = _returns(bars)
    if len(returns) < 9:
        return _label("TREND_STATE", UNKNOWN, available_at=available_at, artifact=artifact, inputs=[] , evidence_quality="INSUFFICIENT")
    total = sum(returns)
    persistence = abs(sum(1 if value > 0 else -1 if value < 0 else 0 for value in returns)) / len(returns)
    noise = median(abs(value) for value in returns)
    normalized_move = abs(total) / max(noise * math.sqrt(len(returns)), 1e-12)
    if persistence >= 0.55 and normalized_move >= 1.0:
        value = "TREND_UP" if total > 0 else "TREND_DOWN"
    elif persistence <= 0.35 or normalized_move < 0.5:
        value = "RANGE"
    else:
        value = "MIXED"
    return _label("TREND_STATE", value, available_at=available_at, artifact=artifact,
                  inputs=["close", "log_returns", "directional_persistence", "normalized_move"])


def _volatility_label(bars: list[HistoricalBar], available_at: str, artifact: HistoricalMarketArtifact) -> dict[str, Any]:
    returns = _returns(bars)
    if len(returns) < 12:
        return _label("VOLATILITY_STATE", UNKNOWN, available_at=available_at, artifact=artifact, inputs=[], evidence_quality="INSUFFICIENT")
    midpoint = len(returns) // 2
    baseline = median(abs(value) for value in returns[:midpoint])
    recent = median(abs(value) for value in returns[midpoint:])
    if baseline <= 0:
        value = UNKNOWN
        quality = "INSUFFICIENT"
    else:
        ratio = recent / baseline
        value = "LOW" if ratio < 0.75 else "NORMAL" if ratio <= 1.5 else "HIGH" if ratio <= 2.5 else "EXTREME"
        quality = "VERIFIED"
    return _label("VOLATILITY_STATE", value, available_at=available_at, artifact=artifact,
                  inputs=["close", "rolling_return_magnitude", "first_half_baseline", "second_half_ratio"], evidence_quality=quality)


def _structure_label(bars: list[HistoricalBar], available_at: str, artifact: HistoricalMarketArtifact) -> dict[str, Any]:
    if len(bars) < 12:
        return _label("STRUCTURE_STATE", UNKNOWN, available_at=available_at, artifact=artifact, inputs=[], evidence_quality="INSUFFICIENT")
    midpoint = len(bars) // 2
    first, second = bars[:midpoint], bars[midpoint:]
    first_move = first[-1].close - first[0].close
    second_move = second[-1].close - second[0].close
    first_high = max(row.high for row in first)
    first_low = min(row.low for row in first)
    second_close = second[-1].close
    breaks_range = second_close > first_high or second_close < first_low
    if breaks_range:
        value = "BREAKOUT"
    elif first_move * second_move < 0 and abs(first_move) > 0 and abs(second_move) > 0:
        value = "REVERSAL_TRANSITION"
    elif first_move * second_move > 0:
        value = "TREND_CONTINUATION"
    else:
        value = "RANGE"
    return _label("STRUCTURE_STATE", value, available_at=available_at, artifact=artifact,
                  inputs=["first_half_high_low", "half_window_direction", "completed_window_close"],
                  evidence_quality="VERIFIED")


def _session_distribution(bars: list[HistoricalBar]) -> dict[str, Any]:
    counts = {"ASIA": 0, "LONDON": 0, "NEW_YORK": 0, "LONDON_NEW_YORK_OVERLAP": 0, "OFF_SESSION": 0}
    for row in bars:
        instant = datetime.fromisoformat(row.timestamp_utc).astimezone(UTC)
        london = 8 <= instant.astimezone(ZoneInfo("Europe/London")).hour < 17
        new_york = 8 <= instant.astimezone(ZoneInfo("America/New_York")).hour < 17
        asia = 9 <= instant.astimezone(ZoneInfo("Asia/Tokyo")).hour < 18
        if london and new_york:
            counts["LONDON_NEW_YORK_OVERLAP"] += 1
        elif london:
            counts["LONDON"] += 1
        elif new_york:
            counts["NEW_YORK"] += 1
        elif asia:
            counts["ASIA"] += 1
        else:
            counts["OFF_SESSION"] += 1
    total = sum(counts.values())
    return {"counts": counts,
            "percentages": {key: round(value * 100 / total, 4) if total else 0.0 for key, value in counts.items()},
            "timezone_model": "IANA_TZ_DATABASE", "canonical_timezone": "UTC"}


def build_window_context(artifact: HistoricalMarketArtifact, *, prior_context: Mapping[str, Any] | None = None,
                         window_id: str = "", window_start: str | None = None,
                         window_end: str | None = None) -> dict[str, Any]:
    """Freeze descriptive market labels before any outcome can be joined."""
    if not artifact.bars:
        raise HistoricalEvidenceError("NO_BARS_FOR_CONTEXT")
    assert_no_outcome_features(artifact.provenance)
    analysis_start = _timestamp(window_start) if window_start else datetime.fromisoformat(artifact.start_time)
    analysis_end = _timestamp(window_end) if window_end else datetime.fromisoformat(artifact.end_time)
    analysis_bars = [bar for bar in artifact.bars
                     if analysis_start <= datetime.fromisoformat(bar.timestamp_utc) <= analysis_end]
    if not analysis_bars:
        raise HistoricalEvidenceError("NO_BARS_IN_ANALYSIS_WINDOW")
    last = datetime.fromisoformat(analysis_bars[-1].timestamp_utc).astimezone(UTC)
    available_at = (last + timedelta(minutes=1)).isoformat()
    observations = {
        "TREND_STATE": _trend_label(analysis_bars, available_at, artifact),
        "VOLATILITY_STATE": _volatility_label(analysis_bars, available_at, artifact),
        "STRUCTURE_STATE": _structure_label(analysis_bars, available_at, artifact),
        "SESSION_STATE": _label("SESSION_STATE", "MIXED_WINDOW", available_at=available_at,
                                artifact=artifact, inputs=["timestamp_utc", "IANA_TZ_DATABASE"],
                                valid_from=analysis_bars[0].timestamp_utc,
                                valid_to=analysis_bars[-1].timestamp_utc),
    }
    for item in observations.values():
        item["valid_range"] = {"from": analysis_bars[0].timestamp_utc,
                               "to": analysis_bars[-1].timestamp_utc}
    context = build_temporal_market_snapshot(
        symbol=artifact.symbol, timeframe=artifact.timeframe, cutoff=available_at,
        observations=observations, observed_at=available_at, available_at=available_at,
        ingested_at=artifact.retrieved_at, valid_from=analysis_bars[0].timestamp_utc,
        valid_to=analysis_bars[-1].timestamp_utc,
        source_authority="B4.7_CANONICAL_HISTORICAL_MARKET_ARTIFACT",
        source_artifacts=(artifact.artifact_id,), freshness_state="IMMUTABLE_ARTIFACT",
    )
    context.update({
        "window_id": window_id or artifact.artifact_id,
        "window_semantics": "WINDOW_DESCRIPTIVE",
        "session_distribution": _session_distribution(analysis_bars),
        "historical_artifact": artifact.to_dict(include_bars=False),
        "context_status": "EVIDENCE_BACKED_WINDOW_DESCRIPTIVE",
        "provenance": {
            **context.get("provenance", {}),
            "artifact_id": artifact.artifact_id,
            "raw_fingerprint": artifact.raw_fingerprint,
            "normalized_fingerprint": artifact.normalized_fingerprint,
            "outcome_excluded_from_labeling": True,
        },
    })
    if prior_context:
        previous_fingerprint = str(prior_context.get("context_fingerprint") or UNKNOWN)
        context["memory_lineage"] = {
            "authority": "CanonicalScientificMemory", "lifecycle": "CANDIDATE",
            "supersedes_context_fingerprint": previous_fingerprint,
            "supersession_reason": "B4.7_CANONICAL_HISTORICAL_MARKET_EVIDENCE",
        }
        context["prior_context_preserved"] = True
    return context


def build_readonly_mt5_request(*, terminal_path: str, data_root: str, symbol: str = CANONICAL_SYMBOL,
                               timeframe: str = CANONICAL_TIMEFRAME, windows: Mapping[str, tuple[str, str]] | None = None,
                               warmup_days: int = 7) -> dict[str, Any]:
    """Create an auditable request without importing or initializing MT5."""
    if symbol != CANONICAL_SYMBOL or timeframe != CANONICAL_TIMEFRAME:
        raise HistoricalEvidenceError("READ_REQUEST_IDENTITY_MISMATCH")
    selected = dict(windows or PRODUCTION_WINDOWS)
    return {
        "mode": "READ_ONLY_HISTORICAL_DATA",
        "terminal_path": str(terminal_path), "data_root": str(data_root),
        "symbol": symbol, "timeframe": timeframe, "windows": selected,
        "warmup_days": int(warmup_days),
        "operations": ["terminal_info", "symbol_info", "copy_rates_range", "shutdown"],
        "forbidden_operations": ["order_send", "positions mutation", "EA attachment", "Strategy Tester", "account mutation", "AutoTrading change"],
        "requires_human_authorization_before_terminal_start": True,
    }


def terminal_read_gate(*, terminal_path: str, running_processes: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Fail closed before terminal interaction when ownership is ambiguous."""
    processes = [dict(item) for item in running_processes]
    if processes:
        return {"status": "HUMAN_ACTION_REQUIRED_CLOSE_USER_MT5", "processes": processes,
                "reason": "USER_OWNED_MT5_PROCESS_PRESENT"}
    return {"status": "AUTHORIZE_READ_ONLY_MT5_HISTORICAL_DATA", "terminal_path": str(terminal_path),
            "processes": [], "terminal_start_performed": False}


def _reconciled_root(root: Path | str | None = None) -> Path:
    return Path(root).resolve() if root else (
        Path(__file__).resolve().parents[1] / "tester_campaigns" /
        "campaign_073cebd5e7df446fa9c85bae75ffbe0a" / "market_evidence" /
        "b4_7_reconciled"
    )


def load_reconciled_temporal_contexts(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Read frozen B4.7 contexts without creating or mutating persistence."""
    import json
    directory = _reconciled_root(root)
    contexts = []
    for period_id in ("R1", "R2", "R3"):
        path = directory / f"{period_id}.temporal_context.json"
        if not path.is_file():
            return []
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(item, dict) or not item.get("test_run_id") or not item.get("context_fingerprint"):
            return []
        historical = item.get("historical_artifact") if isinstance(item.get("historical_artifact"), dict) else {}
        provenance = historical.get("provenance") if isinstance(historical.get("provenance"), dict) else {}
        requested = provenance.get("requested_period") if isinstance(provenance.get("requested_period"), dict) else {}
        item.setdefault("window", {"from": requested.get("from") or item.get("valid_from", UNKNOWN),
                                    "to": requested.get("to") or item.get("valid_to", UNKNOWN)})
        contexts.append(item)
    return contexts


def load_reconciled_post_window_outcomes(root: Path | str | None = None) -> dict[str, Any] | None:
    """Read the already-separated outcome join; never use it for labels."""
    import json
    path = _reconciled_root(root) / "post_window_outcome_join.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "READY":
        return None
    return payload


def write_artifact(artifact: HistoricalMarketArtifact, path: Path | str) -> Path:
    """Persist an immutable evidence file; callers must choose a new path."""
    destination = Path(path)
    if destination.exists():
        raise FileExistsError("IMMUTABLE_ARTIFACT_PATH_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json_dumps(artifact.to_dict()), encoding="utf-8", newline="\n")
    return destination


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


__all__ = [
    "CANONICAL_SYMBOL", "CANONICAL_TIMEFRAME", "HistoricalBar", "HistoricalEvidenceError",
    "HistoricalMarketArtifact", "LABEL_METHOD_VERSION", "PRODUCTION_WINDOWS",
    "SCHEMA_VERSION", "assess_bar_quality", "build_historical_artifact",
    "build_readonly_mt5_request", "build_window_context", "terminal_read_gate", "write_artifact",
    "load_reconciled_post_window_outcomes", "load_reconciled_temporal_contexts",
]
