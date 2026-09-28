from jarvis_core.golden_bridge import GoldenReadBridge


def test_radar_detail_preserves_existing_provider_fields(monkeypatch):
    import market_data

    monkeypatch.setattr(market_data, "get_market_overview", lambda: {
        "ok": True,
        "updated_at": "2026-09-28T12:00:00+00:00",
        "assets": [
            {"group": "Forex", "symbol": "EURUSD"},
            {"group": "Indices", "symbol": "US500"},
            {"group": "Cripto", "symbol": "BTC"},
        ],
        "gold": {"price": 2500}, "gold_levels": [{"price": 2490}],
        "news": [{"title": "macro"}], "macro": {"indicators": [{"id": "DGS10"}]},
        "sources": [{"name": "MT5", "state": "offline"}],
        "configured": {},
    })
    monkeypatch.setattr(market_data, "get_market_chart", lambda symbol, timeframe: {
        "ok": True, "updated_at": "2026-09-28T11:59:00+00:00",
        "levels": [{"kind": "support", "price": 2490}],
    })
    result = GoldenReadBridge().radar_detail("XAUUSD", "M15", "cycle-1")
    assert result["data"]["forex"][0]["symbol"] == "EURUSD"
    assert result["data"]["technical_state"]["levels"][0]["kind"] == "support"
    assert result["provenance"]["observed_at"] == "2026-09-28T12:00:00+00:00"
    assert result["provenance"]["content_fingerprint"]


def test_risk_detail_does_not_authorize_action(monkeypatch):
    from jarvis_core.tools import market_readonly

    monkeypatch.setattr(market_readonly, "golden_risk_status", lambda: {
        "ok": True, "status": "DEGRADED", "timestamp": "2026-09-28T12:00:00+00:00",
        "risk": {"risk_per_trade_pct": 1.0, "correlation_report": {"total": 0}},
    })
    result = GoldenReadBridge().risk_detail()
    assert result["data"]["risk_per_trade"] == 1.0
    assert "SecurityManager" in result["data"]["security_authority"]
    assert result["read_only"] is True


def test_deep_analysis_is_deterministic_without_model_call(monkeypatch):
    import market_data
    import meta_strategy

    monkeypatch.setattr(market_data, "get_market_ai_context", lambda symbol: {
        "ok": True, "updated_at": "2026-09-28T12:00:00+00:00",
        "multitimeframe": {"M15": {"levels": []}},
        "fundamentals": {"events": []},
    })
    monkeypatch.setattr(meta_strategy, "analyze_symbol", lambda symbol: {
        "regime": {"name": "RANGE"}, "market_snapshot": {},
        "best_opportunity": None, "ranked_setups": [], "blocked_setups": [],
        "risk": {},
    })
    result = GoldenReadBridge().deep_analysis_detail("XAUUSD", "cycle-1")
    assert result["data"]["ai_model_context"] == {"model_called": False, "provider": "NONE"}
    assert result["data"]["regime"]["name"] == "RANGE"
