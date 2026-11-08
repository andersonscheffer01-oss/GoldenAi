"""Immutable data contracts shared by the simulation-only arena."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class MarketDataError(ValueError):
    """Raised when market data cannot be used safely by the simulator."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MarketDataError("UTC_TIMESTAMP_REQUIRED")
    return value.astimezone(timezone.utc)


def _finite(value: float, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(code)
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(code)
    return value


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    currency_base: str = ""
    currency_quote: str = ""

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("SYMBOL_REQUIRED")
        object.__setattr__(self, "symbol", symbol)
        if isinstance(self.digits, bool) or not isinstance(self.digits, int) or self.digits < 0:
            raise ValueError("DIGITS_INVALID")
        for name in ("point", "tick_size", "tick_value", "contract_size",
                     "volume_min", "volume_max", "volume_step"):
            value = _finite(getattr(self, name), f"{name.upper()}_INVALID")
            if value <= 0:
                raise ValueError(f"{name.upper()}_REQUIRED")
            object.__setattr__(self, name, value)
        if self.volume_min > self.volume_max:
            raise ValueError("VOLUME_RANGE_INVALID")
        if self.volume_step > self.volume_max:
            raise ValueError("VOLUME_STEP_INVALID")

    def normalize_volume(self, value: float) -> float:
        value = _finite(value, "VOLUME_INVALID")
        if value < self.volume_min:
            return 0.0
        bounded = min(value, self.volume_max)
        steps = math.floor((bounded - self.volume_min) / self.volume_step + 1e-9)
        return round(self.volume_min + steps * self.volume_step, self.digits + 4)


@dataclass(frozen=True, slots=True)
class Tick:
    symbol: str
    event_index: int
    timestamp: datetime
    bid: float
    ask: float

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("SYMBOL_REQUIRED")
        object.__setattr__(self, "symbol", symbol)
        if isinstance(self.event_index, bool) or not isinstance(self.event_index, int) or self.event_index < 0:
            raise ValueError("EVENT_INDEX_INVALID")
        object.__setattr__(self, "timestamp", _utc(self.timestamp))
        bid = _finite(self.bid, "BID_INVALID")
        ask = _finite(self.ask, "ASK_INVALID")
        if ask < bid:
            raise MarketDataError("ASK_BELOW_BID")
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    timeframe: str
    event_index: int
    close_time: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        timeframe = str(self.timeframe or "").strip().upper()
        if not symbol:
            raise ValueError("SYMBOL_REQUIRED")
        if not timeframe:
            raise ValueError("TIMEFRAME_REQUIRED")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)
        if isinstance(self.event_index, bool) or not isinstance(self.event_index, int) or self.event_index < 0:
            raise ValueError("EVENT_INDEX_INVALID")
        object.__setattr__(self, "close_time", _utc(self.close_time))
        values = {
            name: _finite(getattr(self, name), f"{name.upper()}_INVALID")
            for name in ("open", "high", "low", "close")
        }
        if values["high"] < max(values["open"], values["close"]):
            raise MarketDataError("BAR_HIGH_INVALID")
        if values["low"] > min(values["open"], values["close"]):
            raise MarketDataError("BAR_LOW_INVALID")
        for name, value in values.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    run_id: str
    spec: SymbolSpec
    tick: Tick
    closed_bars: Mapping[str, tuple[Bar, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        run_id = str(self.run_id or "").strip()
        if not run_id:
            raise ValueError("RUN_ID_REQUIRED")
        if self.tick.symbol != self.spec.symbol:
            raise MarketDataError("TICK_SYMBOL_MISMATCH")
        normalized: dict[str, tuple[Bar, ...]] = {}
        for timeframe, rows in dict(self.closed_bars or {}).items():
            key = str(timeframe or "").strip().upper()
            ordered = tuple(rows or ())
            for bar in ordered:
                if bar.symbol != self.spec.symbol or bar.timeframe != key:
                    raise MarketDataError("BAR_SYMBOL_OR_TIMEFRAME_MISMATCH")
                if bar.event_index > self.tick.event_index:
                    raise MarketDataError("LOOKAHEAD_BARS")
            if any(left.event_index >= right.event_index for left, right in zip(ordered, ordered[1:])):
                raise MarketDataError("BAR_INDEX_NOT_MONOTONIC")
            normalized[key] = ordered
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "closed_bars", MappingProxyType(normalized))

    @property
    def event_index(self) -> int:
        return self.tick.event_index

    @property
    def timestamp(self) -> datetime:
        return self.tick.timestamp


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class StrategySignal:
    agent: str
    side: Side
    stop_price: float | None
    take_price: float | None
    observed_event_index: int
    reason: str
    volume: float | None = None
    confidence: float | None = None
    data_valid: bool = True

    def __post_init__(self) -> None:
        agent = str(self.agent or "").strip().lower()
        if not agent:
            raise ValueError("AGENT_REQUIRED")
        object.__setattr__(self, "agent", agent)
        side = self.side if isinstance(self.side, Side) else Side(str(self.side).upper())
        object.__setattr__(self, "side", side)
        if isinstance(self.observed_event_index, bool) or not isinstance(self.observed_event_index, int):
            raise ValueError("OBSERVED_EVENT_INDEX_INVALID")
        if self.stop_price is not None:
            _finite(self.stop_price, "STOP_PRICE_INVALID")
        if self.take_price is not None:
            _finite(self.take_price, "TAKE_PRICE_INVALID")
        if self.volume is not None:
            _finite(self.volume, "VOLUME_INVALID")
        if self.confidence is not None:
            confidence = _finite(self.confidence, "CONFIDENCE_INVALID")
            if not 0 <= confidence <= 100:
                raise ValueError("CONFIDENCE_INVALID")
            object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "reason", str(self.reason or "").strip()[:500])

    def as_dict(self) -> dict:
        return {
            "agent": self.agent,
            "side": self.side.value,
            "stop_price": self.stop_price,
            "take_price": self.take_price,
            "observed_event_index": self.observed_event_index,
            "reason": self.reason,
            "volume": self.volume,
            "confidence": self.confidence,
            "data_valid": self.data_valid,
        }


@dataclass(frozen=True, slots=True)
class VirtualPosition:
    agent: str
    side: Side
    volume: float
    entry_price: float
    stop_price: float
    take_price: float
    opened_event_index: int
    opened_at: datetime
    risk_amount: float
    entry_spread: float = 0.0
    slippage_points: float = 0.0


@dataclass(frozen=True, slots=True)
class TradeRecord:
    run_id: str
    agent: str
    side: Side
    volume: float
    entry_price: float
    exit_price: float
    opened_event_index: int
    closed_event_index: int
    opened_at: datetime
    closed_at: datetime
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    signal_reason: str
    risk_amount: float = 0.0
    entry_spread: float = 0.0
    slippage_points: float = 0.0

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id, "agent": self.agent, "side": self.side.value,
            "volume": self.volume, "entry_price": self.entry_price,
            "exit_price": self.exit_price, "opened_event_index": self.opened_event_index,
            "closed_event_index": self.closed_event_index,
            "opened_at": self.opened_at.isoformat(), "closed_at": self.closed_at.isoformat(),
            "gross_pnl": self.gross_pnl, "costs": self.costs, "net_pnl": self.net_pnl,
            "exit_reason": self.exit_reason, "signal_reason": self.signal_reason,
            "risk_amount": self.risk_amount, "entry_spread": self.entry_spread,
            "slippage_points": self.slippage_points,
        }


@dataclass
class PortfolioState:
    agent: str
    balance: float
    initial_balance: float
    daily_realized_pnl: float = 0.0
    current_day: str = ""
    open_position: VirtualPosition | None = None
    closed_trades: list[TradeRecord] = field(default_factory=list)


