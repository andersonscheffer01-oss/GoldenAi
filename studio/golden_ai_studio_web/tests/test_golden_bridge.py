import inspect

from jarvis_core.golden_bridge import GoldenReadBridge, READ_ONLY
from jarvis_core.models import Risk, SideEffectClass
from jarvis_core.service import JarvisService


EXPECTED_CAPABILITIES = {
    "golden.scanner",
    "golden.radar",
    "golden.market_data",
    "golden.market_regime",
    "golden.meta_strategy",
    "golden.risk_engine",
    "golden.validation",
    "golden.strategies",
    "golden.mql5",
    "golden.deep_analysis",
}


def test_registry_is_explicitly_read_only():
    registry = GoldenReadBridge().capability_registry()
    assert {item["capability_id"] for item in registry["capabilities"]} == EXPECTED_CAPABILITIES
    assert registry["count"] == 10
    assert registry["mutation_execution"] == "DISABLED_IN_B1"
    for item in registry["capabilities"]:
        assert item["read_only"] is True
        assert item["side_effect_class"] == READ_ONLY
        assert item["mutation_capabilities"]


def test_scanner_normalization_preserves_score_semantics(monkeypatch):
    from jarvis_core.tools import market_readonly

    monkeypatch.setattr(market_readonly, "golden_scanner_results", lambda symbol, limit: {
        "ok": True,
        "timestamp": "2026-09-28T00:00:00Z",
        "results": [{"symbol": "XAUUSD", "score": 87, "direction": "BUY"}],
    })
    result = GoldenReadBridge().scanner_snapshot("XAUUSD", 1)
    normalized = result["data"]["normalized_results"][0]
    assert normalized["score"] == 87
    assert normalized["score_semantics"] == "SCORE_NOT_PROBABILITY"
    assert "probability" not in normalized


def test_unavailable_provider_is_degraded_read_model(monkeypatch):
    import market_data

    def unavailable(_symbol):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(market_data, "get_market_ai_context", unavailable)
    result = GoldenReadBridge().market_context("XAUUSD")
    assert result["read_only"] is True
    assert result["availability"] == "UNAVAILABLE"
    assert result["data"]["status"] == "UNAVAILABLE"
    assert result["data"]["error_code"] == "RuntimeError"


def test_validation_uses_history_without_running_backtest(monkeypatch):
    import mt5_backtest
    calls = []

    def history(limit):
        calls.append(limit)
        return [{"run_id": "historical-1", "status": "COMPLETED"}]

    monkeypatch.setattr(mt5_backtest, "get_backtest_history", history)
    result = GoldenReadBridge().validation_summary(4)
    assert result["evidence_class"] == "HISTORICAL_EVIDENCE"
    assert result["data"]["count"] == 1
    assert calls == [4]


def test_control_center_default_is_non_live_and_freezes_legacy_paths(monkeypatch):
    bridge = GoldenReadBridge()
    monkeypatch.setattr(bridge, "strategy_summary", lambda: {
        "data": {"matching_coverage": {
            "EXISTING_ROBOT_MARKET_MATCHING_COVERAGE": ["GoldenScanner"]}},
        "read_only": True,
    })
    snapshot = bridge.control_center_snapshot(include_live=False)
    assert snapshot["read_only"] is True
    assert snapshot["mt5"]["status"] == "NOT_REQUESTED"
    assert snapshot["legacy_execution"]["invoked"] is False
    assert snapshot["voice"]["status"] == "OUT_OF_SCOPE_B1"


def test_service_registers_b1_tools_as_read_only(tmp_path):
    service = JarvisService(tmp_path)
    try:
        b1 = [tool for tool in service.registry._tools.values()
              if tool.category == "golden_b1"]
        assert len(b1) == 12
        assert all(tool.risk == Risk.LOW for tool in b1)
        assert all(tool.side_effect_class == SideEffectClass.READ_ONLY for tool in b1)
        assert all(tool.llm_enabled is False for tool in b1)
        assert all("NO_TRADING" in tool.security_requirements for tool in b1)
        assert not any("order_send" in tool.name or "send_order" in tool.name for tool in b1)
    finally:
        service.close()


def test_bridge_source_has_no_execution_or_process_launch_symbols():
    from pathlib import Path

    source = Path(inspect.getfile(GoldenReadBridge)).read_text(encoding="utf-8")
    assert ".order_send(" not in source
    assert "send_order(" not in source
    for forbidden in ("subprocess", "Popen", "os.system", "create_subprocess"):
        assert forbidden not in source
