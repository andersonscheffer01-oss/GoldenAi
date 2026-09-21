from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.safety import EvidenceLevel


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def stable_value(value: Any) -> Any:
    volatile_keys = {"analysis_id", "snapshot_id", "observation_id", "result_hash", "created_at"}
    if isinstance(value, dict):
        return {key: stable_value(item) for key, item in value.items() if key not in volatile_keys}
    if isinstance(value, list):
        return [stable_value(item) for item in value]
    return value


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


@dataclass
class MarketSnapshot:
    snapshot_id: str
    symbol: str
    timestamp: str
    timeframe: str
    ohlc: dict[str, float]
    spread: float | None = None
    volume: float | None = None
    tick_volume: float | None = None
    volatility_metrics: dict[str, float] = field(default_factory=dict)
    source: str = ""
    data_hash: str = ""
    created_at: str = field(default_factory=now_iso)


@dataclass
class RegimeState:
    symbol: str
    timeframe: str
    regime: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.INFERRED


@dataclass
class StructureState:
    symbol: str
    timeframe: str
    recent_high: float | None
    recent_low: float | None
    swing_highs: list[dict[str, Any]] = field(default_factory=list)
    swing_lows: list[dict[str, Any]] = field(default_factory=list)
    basic_trend: str = "UNCERTAIN"
    range_high: float | None = None
    range_low: float | None = None
    moving_average_distance: float | None = None
    volatility: float | None = None
    support: float | None = None
    resistance: float | None = None
    previous_high: float | None = None
    previous_low: float | None = None


@dataclass
class MarketObservation:
    observation_id: str
    symbol: str
    timeframe: str
    statement: str
    evidence_level: EvidenceLevel
    data_points: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalContext:
    symbol: str
    timeframe: str
    signal: str
    evidence_level: EvidenceLevel
    reasons: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)


@dataclass
class MultiTimeframeContext:
    symbol: str
    timeframes_used: list[str]
    states_by_timeframe: dict[str, str]
    conflicts: list[str]
    alignment: str
    timestamp: str


@dataclass
class MarketAnalysisResult:
    analysis_id: str
    symbol: str
    source: str
    snapshots: list[MarketSnapshot]
    regimes: list[RegimeState]
    mtf_context: MultiTimeframeContext
    structures: list[StructureState]
    observations: list[MarketObservation]
    signals: list[SignalContext]
    report: dict[str, Any]
    result_hash: str = ""
    created_at: str = field(default_factory=now_iso)

    def compute_hash(self) -> str:
        return deterministic_hash(stable_value(asdict(self)))
