from datetime import datetime, timedelta, timezone

from golden_scalper_arena.agents import build_default_agents
from golden_scalper_arena.contracts import Bar, MarketSnapshot, SymbolSpec, Tick


BASE = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)


def _spec():
    return SymbolSpec(
        symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
        tick_value=1.0, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )


def _bar(timeframe, index, open_, high, low, close):
    return Bar(
        symbol="XAUUSD", timeframe=timeframe, event_index=index,
        close_time=BASE + timedelta(minutes=index),
        open=open_, high=high, low=low, close=close,
    )


def _snapshot(bid, ask, bars):
    return MarketSnapshot(
        run_id="agent-fixture", spec=_spec(),
        tick=Tick(
            symbol="XAUUSD", event_index=100,
            timestamp=BASE + timedelta(minutes=100), bid=bid, ask=ask,
        ),
        closed_bars=bars,
    )


def test_each_default_agent_has_one_observable_deterministic_setup():
    agents = build_default_agents()
    fixtures = {
        "momentum": _snapshot(101.25, 101.35, {
            "M1": tuple(_bar("M1", i, close - 0.05, close + 0.12, close - 0.12, close)
                         for i, close in enumerate((100.00, 100.08, 100.16, 100.28, 100.56, 100.88), 1)),
        }),
        "defense": _snapshot(100.55, 100.65, {
            "M1": (
                _bar("M1", 1, 100.1, 100.4, 99.0, 100.3),
                _bar("M1", 2, 100.2, 100.5, 99.05, 100.35),
                _bar("M1", 3, 100.3, 100.7, 99.1, 100.5),
            ),
        }),
        "breakout": _snapshot(101.05, 101.15, {
            "M1": (
                _bar("M1", 1, 100.0, 100.5, 99.5, 100.1),
                _bar("M1", 2, 100.1, 100.45, 99.6, 100.2),
                _bar("M1", 3, 100.2, 100.4, 99.7, 100.15),
                _bar("M1", 4, 100.1, 100.35, 99.65, 100.2),
                _bar("M1", 5, 100.2, 100.45, 99.7, 100.3),
                _bar("M1", 6, 100.3, 101.2, 100.2, 101.0),
            ),
        }),
        "pullback": _snapshot(100.95, 101.05, {
            "H1": (
                _bar("H1", 1, 99.5, 100.1, 99.2, 99.8),
                _bar("H1", 2, 99.8, 100.6, 99.6, 100.4),
                _bar("H1", 3, 100.4, 101.2, 100.1, 101.0),
            ),
            "M1": (
                _bar("M1", 1, 101.0, 101.1, 100.75, 100.8),
                _bar("M1", 2, 100.8, 100.9, 100.65, 100.72),
                _bar("M1", 3, 100.72, 101.0, 100.7, 100.96),
            ),
        }),
        "liquidity": _snapshot(99.45, 99.55, {
            "M1": (
                _bar("M1", 1, 100.0, 100.4, 99.0, 100.1),
                _bar("M1", 2, 100.1, 100.35, 99.15, 100.2),
                _bar("M1", 3, 100.2, 100.3, 98.7, 99.4),
            ),
        }),
    }

    for name, fixture in fixtures.items():
        first = agents[name](fixture, {"agent": name, "balance": 10_000.0})
        second = agents[name](fixture, {"agent": name, "balance": 10_000.0})
        assert first is not None, name
        assert first == second
        assert first.agent == name
        assert first.observed_event_index == fixture.event_index
        if first.side.value == "BUY":
            assert first.stop_price < fixture.tick.ask < first.take_price
        else:
            assert first.take_price < fixture.tick.bid < first.stop_price


def test_agents_fail_closed_without_enough_closed_data():
    snapshot = _snapshot(100.0, 100.1, {"M1": ()})
    assert all(agent(snapshot, {}) is None for agent in build_default_agents().values())

