from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from golden_scalper_arena.contracts import Bar, MarketSnapshot, SymbolSpec, Tick
from golden_scalper_arena.validation import MarketDataError, validate_ticks


def _spec():
    return SymbolSpec(
        symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
        tick_value=1.0, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )


def _tick(index, bid=2300.0, ask=2300.2):
    return Tick(
        symbol="XAUUSD", event_index=index,
        timestamp=datetime(2026, 1, 2, 12, 0, index, tzinfo=timezone.utc),
        bid=bid, ask=ask,
    )


def test_tick_validation_rejects_non_monotonic_and_invalid_spread():
    with pytest.raises(MarketDataError, match="EVENT_INDEX_NOT_MONOTONIC"):
        validate_ticks([_tick(1), _tick(1)])

    with pytest.raises(MarketDataError, match="ASK_BELOW_BID"):
        validate_ticks([_tick(1, bid=2300.2, ask=2300.1)])


def test_snapshot_rejects_future_bar_and_is_immutable():
    future_bar = Bar(
        symbol="XAUUSD", timeframe="M1", event_index=11,
        close_time=datetime(2026, 1, 2, 12, 1, tzinfo=timezone.utc),
        open=2300, high=2301, low=2299, close=2300.5,
    )
    with pytest.raises(MarketDataError, match="LOOKAHEAD_BARS"):
        MarketSnapshot(
            run_id="run-1", spec=_spec(), tick=_tick(10),
            closed_bars={"M1": (future_bar,)},
        )

    snapshot = MarketSnapshot(run_id="run-1", spec=_spec(), tick=_tick(10))
    with pytest.raises(FrozenInstanceError):
        snapshot.run_id = "changed"


def test_symbol_spec_rejects_missing_cost_data():
    with pytest.raises(ValueError, match="TICK_VALUE_REQUIRED"):
        SymbolSpec(
            symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
            tick_value=0.0, contract_size=100.0,
            volume_min=0.01, volume_max=100.0, volume_step=0.01,
        )


