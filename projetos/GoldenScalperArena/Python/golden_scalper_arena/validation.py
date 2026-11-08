"""Fail-closed validation for historical and live-read snapshots."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .contracts import MarketDataError, Tick


def validate_ticks(ticks: Iterable[Tick], expected_symbol: str | None = None) -> tuple[Tick, ...]:
    rows = tuple(ticks or ())
    previous = None
    symbol = str(expected_symbol or "").strip().upper()
    for tick in rows:
        if not isinstance(tick, Tick):
            raise MarketDataError("TICK_CONTRACT_REQUIRED")
        if symbol and tick.symbol != symbol:
            raise MarketDataError("TICK_SYMBOL_MISMATCH")
        if previous is not None:
            if tick.event_index <= previous.event_index:
                raise MarketDataError("EVENT_INDEX_NOT_MONOTONIC")
            if tick.timestamp < previous.timestamp:
                raise MarketDataError("TIMESTAMP_NOT_MONOTONIC")
        if not all(math.isfinite(value) for value in (tick.bid, tick.ask, tick.spread)):
            raise MarketDataError("TICK_NUMBER_INVALID")
        if tick.ask < tick.bid:
            raise MarketDataError("ASK_BELOW_BID")
        previous = tick
    return rows


__all__ = ["MarketDataError", "validate_ticks"]


