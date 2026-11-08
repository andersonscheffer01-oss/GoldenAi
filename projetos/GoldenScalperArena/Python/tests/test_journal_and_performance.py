from datetime import datetime, timezone

from golden_scalper_arena.journal import ArenaJournal
from golden_scalper_arena.performance import summarize_trades


def test_journal_records_are_append_only_and_metrics_are_net(tmp_path):
    journal = ArenaJournal(tmp_path / "arena.sqlite")
    journal.start_run("run-1", "XAUUSD", "fixture-v1")
    journal.record_signal("run-1", "momentum", 1, {"side": "BUY"})
    journal.record_trade("run-1", {
        "agent": "momentum", "net_pnl": 10.0, "risk_amount": 5.0,
        "exit_reason": "TAKE_PROFIT",
    })
    journal.record_trade("run-1", {
        "agent": "momentum", "net_pnl": -4.0, "risk_amount": 5.0,
        "exit_reason": "STOP_LOSS",
    })

    assert journal.count("signals") == 1
    assert journal.count("trades") == 2
    metrics = summarize_trades(journal.trades("run-1", "momentum"))
    assert metrics["net_pnl"] == 6.0
    assert metrics["win_rate"] == 50.0
    assert metrics["profit_factor"] == 2.5


