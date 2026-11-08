from datetime import datetime, timezone

from golden_scalper_arena.arena import GoldenScalperArena
from golden_scalper_arena.contracts import MarketSnapshot, Side, StrategySignal, SymbolSpec, Tick
from golden_scalper_arena.virtual_execution import VirtualExecutionConfig


def _snapshot(index):
    spec = SymbolSpec(
        symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
        tick_value=1.0, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )
    return MarketSnapshot(
        run_id="arena-run", spec=spec,
        tick=Tick(
            symbol="XAUUSD", event_index=index,
            timestamp=datetime(2026, 1, 2, 12, 0, index, tzinfo=timezone.utc),
            bid=2300.0, ask=2300.2,
        ),
    )


def test_five_agents_receive_same_snapshot_and_keep_wallets_separate():
    seen = {}

    def make_agent(name):
        def agent(snapshot, _portfolio):
            seen[name] = (id(snapshot), snapshot.tick.event_index)
            return StrategySignal(
                agent=name, side=Side.BUY, stop_price=2299.0,
                take_price=2302.0, volume=0.2,
                observed_event_index=snapshot.event_index, reason="fixture",
            )
        return agent

    names = ("momentum", "defense", "breakout", "pullback", "liquidity")
    arena = GoldenScalperArena(
        agents={name: make_agent(name) for name in names},
        execution_config=VirtualExecutionConfig(
            initial_balance=10_000.0, risk_per_trade=0.0025,
            daily_loss_limit=0.015, max_positions=1,
            slippage_points=0.0, commission_per_volume=0.0,
        ),
    )
    arena.step(_snapshot(1))

    assert {value[0] for value in seen.values()} == {id(arena.last_snapshot)}
    assert {value[1] for value in seen.values()} == {1}
    assert set(arena.portfolios) == set(names)
    assert all(state.open_position is not None for state in arena.portfolios.values())
    assert len({id(state) for state in arena.portfolios.values()}) == 5


