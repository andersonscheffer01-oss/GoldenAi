"""Point-in-time market context contracts for scientific evidence.

The module is deliberately storage-neutral.  It freezes market labels before
robot outcomes are attached, rejects future observations, and keeps unknown
context explicit when historical price or macro artifacts are unavailable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .b2_contracts import content_fingerprint


UNKNOWN = "UNKNOWN"
LABEL_STATUSES = ("OBSERVED", "DERIVED", "INFERRED", UNKNOWN)
LABEL_NAMES = ("TREND_STATE", "VOLATILITY_STATE", "STRUCTURE_STATE",
               "SESSION_STATE", "EVENT_RISK_STATE", "USD_STATE",
               "LIQUIDITY_STATE", "CORRELATION_STATE")

# These fields describe the post-window result or the robot execution.  They
# are never valid inputs to a market label, even when nested in a payload.
_OUTCOME_TOKENS = (
    "balance", "equity", "profit", "pnl", "ontester", "on_tester", "trade", "win",
    "loss", "drawdown", "expectancy", "outcome", "position", "score",
)


class LeakageViolation(ValueError):
    """Raised when a context builder receives future or outcome-derived data."""


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return str(value)


def _parse_time(value: Any) -> datetime | None:
    if not value or str(value).upper() == UNKNOWN:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _key(value: Any) -> str:
    return "".join(char for char in str(value).casefold()
                   if char.isalnum())


def _contains_outcome_key(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _key(key)
            if any(token in normalized for token in _OUTCOME_TOKENS):
                return f"{path}.{key}" if path else str(key)
            found = _contains_outcome_key(item, f"{path}.{key}" if path else str(key))
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _contains_outcome_key(item, f"{path}[{index}]")
            if found:
                return found
    return None


def assert_no_outcome_features(observations: Any) -> None:
    """Fail closed if robot results are supplied to the context pipeline."""
    found = _contains_outcome_key(observations)
    if found:
        raise LeakageViolation(f"OUTCOME_FEATURE_FORBIDDEN:{found}")


def _unknown_label(name: str, *, cutoff: str, provenance: str) -> dict[str, Any]:
    return {
        "label": UNKNOWN,
        "status": UNKNOWN,
        "method": "NO_POINT_IN_TIME_DATA",
        "method_version": "jarvis-temporal-context-v1",
        "inputs": [],
        "valid_range": {"from": UNKNOWN, "to": UNKNOWN},
        "cutoff": cutoff,
        "confidence": None,
        "evidence_quality": "INSUFFICIENT",
        "provenance": {"field": name, "source": provenance},
    }


def _label_from_observation(name: str, item: Any, *, cutoff: str,
                            provenance: str) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        return _unknown_label(name, cutoff=cutoff, provenance=provenance)
    available_at = item.get("available_at")
    cutoff_time = _parse_time(cutoff)
    available_time = _parse_time(available_at)
    if cutoff_time and available_time and available_time > cutoff_time:
        raise LeakageViolation(f"FUTURE_OBSERVATION_FORBIDDEN:{name}")
    status = str(item.get("status") or UNKNOWN).upper()
    if status not in LABEL_STATUSES:
        status = UNKNOWN
    if status != UNKNOWN and available_time is None:
        raise LeakageViolation(f"AVAILABLE_AT_REQUIRED:{name}")
    label = item.get("label", item.get("value", UNKNOWN))
    return {
        "label": _json(label if label not in (None, "") else UNKNOWN),
        "status": status,
        "method": str(item.get("method") or "SOURCE_OBSERVATION"),
        "method_version": str(item.get("method_version") or
                               "jarvis-temporal-context-v1"),
        "inputs": _json(item.get("inputs") or []),
        "valid_range": _json(item.get("valid_range") or
                              {"from": UNKNOWN, "to": UNKNOWN}),
        "cutoff": cutoff,
        "confidence": item.get("confidence"),
        "evidence_quality": str(item.get("evidence_quality") or
                                 ("VERIFIED" if status != UNKNOWN else "INSUFFICIENT")),
        "provenance": _json(item.get("provenance") or {"source": provenance}),
    }


@dataclass(frozen=True)
class TemporalMarketSnapshot:
    symbol: str
    timeframe: str
    observed_at: str
    available_at: str
    ingested_at: str
    valid_from: str
    valid_to: str
    cutoff: str
    labels: dict[str, dict[str, Any]]
    source_authority: str
    source_artifacts: tuple[str, ...] = ()
    freshness_state: str = UNKNOWN
    timezone_model: str = "UTC"
    dst_handling: str = "IANA_TZ_DATABASE"
    point_in_time_supported: bool = False
    context_status: str = "UNKNOWN"
    frozen: bool = True
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def context_fingerprint(self) -> str:
        return content_fingerprint({
            "symbol": self.symbol, "timeframe": self.timeframe,
            "observed_at": self.observed_at, "available_at": self.available_at,
            "valid_from": self.valid_from, "valid_to": self.valid_to,
            "cutoff": self.cutoff, "labels": self.labels,
            "source_authority": self.source_authority,
            "source_artifacts": list(self.source_artifacts),
            "freshness_state": self.freshness_state,
            "timezone_model": self.timezone_model,
            "dst_handling": self.dst_handling,
        })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "source_artifacts": list(self.source_artifacts),
            "context_fingerprint": self.context_fingerprint,
            "label_status": {name: value.get("status", UNKNOWN)
                             for name, value in self.labels.items()},
        }


def build_temporal_market_snapshot(*, symbol: str, timeframe: str,
                                   cutoff: str, observations: Mapping[str, Any] | None = None,
                                   observed_at: str = UNKNOWN,
                                   available_at: str = UNKNOWN,
                                   ingested_at: str = UNKNOWN,
                                   valid_from: str = UNKNOWN,
                                   valid_to: str = UNKNOWN,
                                   source_authority: str = "UNKNOWN",
                                   source_artifacts: Iterable[str] = (),
                                   freshness_state: str = UNKNOWN,
                                   timezone_model: str = "UTC",
                                   dst_handling: str = "IANA_TZ_DATABASE") -> dict[str, Any]:
    observations = dict(observations or {})
    assert_no_outcome_features(observations)
    cutoff_time = _parse_time(cutoff)
    if cutoff_time is None and observations:
        raise LeakageViolation("VALID_CUTOFF_REQUIRED")
    labels = {
        name: _label_from_observation(name, observations.get(name), cutoff=cutoff,
                                      provenance=source_authority)
        for name in LABEL_NAMES
    }
    has_observed_label = any(item["status"] != UNKNOWN for item in labels.values())
    future = _parse_time(available_at)
    if cutoff_time and future and future > cutoff_time:
        raise LeakageViolation("FUTURE_SNAPSHOT_FORBIDDEN")
    status = "AVAILABLE" if has_observed_label else "CONTEXT_UNKNOWN"
    snapshot = TemporalMarketSnapshot(
        symbol=str(symbol or UNKNOWN), timeframe=str(timeframe or UNKNOWN),
        observed_at=str(observed_at or UNKNOWN), available_at=str(available_at or UNKNOWN),
        ingested_at=str(ingested_at or UNKNOWN), valid_from=str(valid_from or UNKNOWN),
        valid_to=str(valid_to or UNKNOWN), cutoff=str(cutoff or UNKNOWN), labels=labels,
        source_authority=str(source_authority or UNKNOWN),
        source_artifacts=tuple(str(item) for item in source_artifacts if item),
        freshness_state=str(freshness_state or UNKNOWN),
        timezone_model=str(timezone_model or "UTC"),
        dst_handling=str(dst_handling or "IANA_TZ_DATABASE"),
        point_in_time_supported=bool(cutoff_time and not future),
        context_status=status, frozen=True,
        provenance={"contract": "jarvis-temporal-context-v1",
                    "outcome_excluded_from_labeling": True},
    )
    return {"ok": True, "read_only": True, **snapshot.to_dict()}


def build_production_window_contexts() -> list[dict[str, Any]]:
    """Register B4.5 windows without inventing unavailable market labels."""
    windows = (
        ("run_1c8069dbd88842a4ad88cd9d6ae6fa7d", "2026.08.24", "2026.08.28"),
        ("run_a8180c7c559746da9b7a6863f6796292", "2026.09.01", "2026.09.05"),
        ("run_c078697fe9ce4892bc9665e6f276be58", "2026.09.08", "2026.09.12"),
    )
    contexts = []
    for run_id, date_from, date_to in windows:
        context = build_temporal_market_snapshot(
            symbol="XAUUSD", timeframe="M1", cutoff=f"{date_from.replace('.', '-') }T00:00:00+00:00",
            valid_from=date_from, valid_to=date_to,
            source_authority="B4.5_NATIVE_TESTER_EVIDENCE_ONLY",
            source_artifacts=(f"tester_campaigns/campaign_073cebd5e7df446fa9c85bae75ffbe0a/evidence/{run_id}.native_log_evidence.json",),
            freshness_state="IMMUTABLE_ARTIFACT_REFERENCE_ONLY",
        )
        context.update({"test_run_id": run_id, "window_id": run_id,
                        "window": {"from": date_from, "to": date_to},
                        "memory_lineage": {
                            "authority": "CanonicalScientificMemory",
                            "campaign_id": "campaign_073cebd5e7df446fa9c85bae75ffbe0a",
                            "market_context_id": context["context_fingerprint"],
                            "execution_evidence_id": run_id,
                            "outcome_id": f"POST_WINDOW_OUTCOME:{run_id}",
                            "lifecycle": "CANDIDATE",
                        },
                        "context_status": "BLOCKED_BY_MISSING_HISTORICAL_MARKET_ARTIFACT"})
        contexts.append(context)
    return contexts


def link_outcomes_after_context_freeze(contexts: Iterable[Mapping[str, Any]],
                                       outcomes: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Join outcomes only after frozen contexts; outcome stays post-window."""
    by_run = {str(item.get("test_run_id")): item for item in contexts
              if item.get("test_run_id")}
    rows = []
    for outcome in outcomes:
        run_id = str(outcome.get("test_run_id") or outcome.get("run_id") or UNKNOWN)
        context = by_run.get(run_id)
        rows.append({
            "test_run_id": run_id,
            "robot_id": outcome.get("robot_id", UNKNOWN),
            "context_fingerprint": context.get("context_fingerprint", UNKNOWN) if context else UNKNOWN,
            "market_labels": _json(context.get("labels", {}) if context else {}),
            "post_window_outcome": _json(dict(outcome)),
            "outcome_role": "POST_WINDOW_OUTCOME",
            "label_inputs_excluded": True,
            "provenance": {"context_source": context.get("source_authority", UNKNOWN)
                           if context else UNKNOWN},
        })
    return {"status": "READY" if rows and all(row["context_fingerprint"] != UNKNOWN for row in rows)
             else "PARTIAL", "rows": rows, "count": len(rows),
            "join_order": "CONTEXT_FREEZE_THEN_OUTCOME_JOIN",
            "leakage_guard": "OUTCOMES_NOT_USED_AS_LABEL_INPUTS"}


__all__ = [
    "LABEL_NAMES", "LABEL_STATUSES", "LeakageViolation", "TemporalMarketSnapshot",
    "UNKNOWN", "assert_no_outcome_features", "build_production_window_contexts",
    "build_temporal_market_snapshot", "link_outcomes_after_context_freeze",
]
