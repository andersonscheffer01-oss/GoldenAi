from datetime import datetime, timedelta, timezone

from golden_scalper_arena.arena import GoldenScalperArena
from golden_scalper_arena.contracts import MarketSnapshot, Side, StrategySignal, SymbolSpec, Tick
from golden_scalper_arena.journal import ArenaJournal
from golden_scalper_arena.replay import run_replay
from golden_scalper_arena.robustness import run_cost_stress
from golden_scalper_arena.session import run_paper_session
from golden_scalper_arena.virtual_execution import VirtualExecutionConfig
from golden_scalper_arena.walk_forward import build_walk_forward_plan, run_walk_forward


BASE = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)


def _spec():
    return SymbolSpec(
        symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
        tick_value=1.0, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )


def _snapshot(index, bid=100.0, ask=100.1):
    return MarketSnapshot(
        run_id="replay-fixture", spec=_spec(),
        tick=Tick(
            symbol="XAUUSD", event_index=index,
            timestamp=BASE + timedelta(seconds=index), bid=bid, ask=ask,
        ),
    )


def _buy_agent(snapshot, _portfolio):
    if snapshot.event_index != 1:
        return None
    return StrategySignal(
        agent="fixture", side=Side.BUY, stop_price=99.0, take_price=101.0,
        volume=0.2, observed_event_index=snapshot.event_index, reason="fixture",
    )


def test_arena_journals_signals_and_finalizes_open_positions(tmp_path):
    journal = ArenaJournal(tmp_path / "arena.sqlite")
    arena = GoldenScalperArena({"fixture": _buy_agent}, journal=journal)
    arena.run([_snapshot(1), _snapshot(2, 100.4, 100.5)], finalize=True)
    assert journal.count("runs") == 1
    assert journal.count("signals") == 1
    assert journal.count("trades") == 1
    assert journal.trades("replay-fixture", "fixture")[0]["exit_reason"] == "END_OF_RUN"


def test_replay_report_contains_five_agents_and_security_contract():
    result = run_replay([_snapshot(i, 100.0 + i * 0.02, 100.1 + i * 0.02) for i in range(1, 5)])
    report = result.as_dict()
    assert {row["agent"] for row in report["agents"]} == {
        "momentum", "defense", "breakout", "pullback", "liquidity",
    }
    assert report["security"] == {
        "read_only": True, "simulation_only": True,
        "execution_authority": "NONE", "real_orders": False,
    }
    assert report["run"]["status"] == "SIMULATION"


def test_walk_forward_reserves_final_oos_without_overlap():
    rows = list(range(14))
    plan = build_walk_forward_plan(rows, train_size=4, test_size=2, step=2, oos_size=2)
    assert plan.oos == (12, 13)
    assert all(set(window.train).isdisjoint(window.test) for window in plan.windows)
    assert all(max(window.test) < min(plan.oos) for window in plan.windows)
    report = run_walk_forward(plan, lambda train, test, is_oos: {
        "train": len(train), "test": len(test), "is_oos": is_oos,
    })
    assert report["oos"]["is_oos"] is True
    assert len(report["windows"]) == len(plan.windows)


def test_cost_stress_and_paper_session_are_explicitly_simulated():
    snapshots = [_snapshot(1), _snapshot(2, 100.4, 100.5)]
    config = VirtualExecutionConfig(slippage_points=1.0)
    stress = run_cost_stress(snapshots, {"fixture": _buy_agent}, config, multipliers=(1.0, 2.0))
    assert [row["spread_multiplier"] for row in stress["scenarios"]] == [1.0, 2.0]
    assert all(row["execution_authority"] == "NONE" for row in stress["scenarios"])
    paper = run_paper_session(snapshots, {"fixture": _buy_agent}, session_id="paper-1")
    assert paper["status"] == "SIMULATED_PAPER"
    assert paper["execution_authority"] == "NONE"

