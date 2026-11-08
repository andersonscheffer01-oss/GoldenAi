from golden_scalper_arena.dashboard_data import build_dashboard_model, render_dashboard_html


def test_dashboard_model_exposes_rankings_validation_and_read_only_state():
    report = {
        "run": {"run_id": "demo", "symbol": "XAUUSD", "status": "SIMULATION"},
        "security": {
            "read_only": True, "simulation_only": True,
            "execution_authority": "NONE", "real_orders": False,
        },
        "agents": [
            {"agent": name, "metrics": {"net_pnl": index, "profit_factor": 1.1, "max_drawdown": 2.0}}
            for index, name in enumerate(("momentum", "defense", "breakout", "pullback", "liquidity"), 1)
        ],
        "validation": {"status": "NOT_VALIDATED", "winner": None},
    }
    model = build_dashboard_model(report)
    assert len(model["agents"]) == 5
    assert model["security"]["execution_authority"] == "NONE"
    assert model["validation"]["winner"] is None
    html = render_dashboard_html(model)
    assert "Golden Scalper Arena" in html
    assert "execution_authority" in html

