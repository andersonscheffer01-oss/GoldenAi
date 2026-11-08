from golden_scalper_arena.performance import summarize_trades


def test_metrics_include_costs_points_drawdown_recovery_and_streaks():
    rows = [
        {
            "agent": "momentum", "side": "BUY", "entry_price": 100.0,
            "exit_price": 100.2, "net_pnl": 10.0, "gross_pnl": 11.0,
            "costs": 1.0, "opened_at": "2026-01-01T00:00:00+00:00",
            "closed_at": "2026-01-01T00:00:01+00:00",
        },
        {
            "agent": "momentum", "side": "BUY", "entry_price": 100.0,
            "exit_price": 99.9, "net_pnl": -4.0, "gross_pnl": -3.0,
            "costs": 1.0, "opened_at": "2026-01-01T00:00:02+00:00",
            "closed_at": "2026-01-01T00:00:03+00:00",
        },
        {
            "agent": "momentum", "side": "BUY", "entry_price": 100.0,
            "exit_price": 100.1, "net_pnl": 6.0, "gross_pnl": 7.0,
            "costs": 1.0, "opened_at": "2026-01-01T00:00:04+00:00",
            "closed_at": "2026-01-01T00:00:05+00:00",
        },
    ]
    metrics = summarize_trades(rows, tick_size=0.01)
    assert metrics["net_pnl"] == 12.0
    assert metrics["costs"] == 3.0
    assert metrics["net_points"] == 20.0
    assert metrics["gross_points"] == 30.0
    assert metrics["losing_points"] == 10.0
    assert metrics["max_drawdown"] == 4.0
    assert metrics["max_win_streak"] == 1
    assert metrics["max_loss_streak"] == 1
    assert metrics["avg_holding_seconds"] == 1.0

