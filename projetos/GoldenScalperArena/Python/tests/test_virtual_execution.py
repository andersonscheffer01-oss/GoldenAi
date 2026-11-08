from datetime import datetime, timedelta, timezone

import pytest

from golden_scalper_arena.contracts import MarketSnapshot, Side, StrategySignal, SymbolSpec, Tick
from golden_scalper_arena.virtual_execution import VirtualExecution, VirtualExecutionConfig


def _spec():
    return SymbolSpec(
        symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
        tick_value=1.0, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )


def _snapshot(index, bid, ask, when=None):
    return MarketSnapshot(
        run_id="run-1", spec=_spec(),
        tick=Tick(
            symbol="XAUUSD", event_index=index,
            timestamp=when or datetime(2026, 1, 2, 12, 0, index, tzinfo=timezone.utc),
            bid=bid, ask=ask,
        ),
    )


def _engine():
    return VirtualExecution(
        _spec(),
        VirtualExecutionConfig(
            initial_balance=10_000.0, risk_per_trade=0.0025,
            daily_loss_limit=0.015, max_positions=1,
            slippage_points=2.0, commission_per_volume=0.0,
            max_duration=timedelta(seconds=90),
        ),
    )


def test_buy_uses_ask_and_stop_exit_uses_bid_with_slippage():
    engine = _engine()
    opened = engine.open(
        "momentum", _snapshot(1, 2300.0, 2300.2),
        StrategySignal(
            agent="momentum", side=Side.BUY, stop_price=2299.0,
            take_price=2302.0, volume=0.2, observed_event_index=1,
            reason="fixture",
        ),
    )
    assert opened.accepted is True
    assert opened.position.entry_price == pytest.approx(2300.22)

    closed = engine.on_tick(_snapshot(2, 2298.9, 2299.1))
    assert closed[0].exit_price == pytest.approx(2298.88)
    assert closed[0].exit_reason == "STOP_LOSS"
    assert closed[0].net_pnl < 0


def test_sell_uses_bid_and_take_exit_uses_ask():
    engine = _engine()
    opened = engine.open(
        "defense", _snapshot(1, 2300.0, 2300.2),
        StrategySignal(
            agent="defense", side=Side.SELL, stop_price=2302.0,
            take_price=2298.1, volume=0.1, observed_event_index=1,
            reason="fixture",
        ),
    )
    assert opened.position.entry_price == pytest.approx(2299.98)

    closed = engine.on_tick(_snapshot(2, 2297.9, 2298.1))
    assert closed[0].exit_price == pytest.approx(2298.12)
    assert closed[0].exit_reason == "TAKE_PROFIT"
    assert closed[0].net_pnl > 0


def test_lookahead_and_daily_loss_are_rejected():
    engine = _engine()
    result = engine.open(
        "breakout", _snapshot(1, 2300.0, 2300.2),
        StrategySignal(
            agent="breakout", side=Side.BUY, stop_price=2299.0,
            take_price=2302.0, volume=0.2, observed_event_index=2,
            reason="future",
        ),
    )
    assert result.accepted is False
    assert result.reason == "LOOKAHEAD_SIGNAL"

    opened = engine.open(
        "breakout", _snapshot(3, 2300.0, 2300.2),
        StrategySignal(
            agent="breakout", side=Side.BUY, stop_price=2299.0,
            take_price=2302.0, volume=0.2, observed_event_index=3,
            reason="valid",
        ),
    )
    assert opened.accepted is True
    engine.on_tick(_snapshot(4, 2291.8, 2292.0))
    blocked = engine.open(
        "breakout", _snapshot(5, 2300.0, 2300.2),
        StrategySignal(
            agent="breakout", side=Side.BUY, stop_price=2299.0,
            take_price=2302.0, volume=0.2, observed_event_index=5,
            reason="daily limit",
        ),
    )
    assert blocked.accepted is False
    assert blocked.reason == "DAILY_LOSS_LIMIT"


