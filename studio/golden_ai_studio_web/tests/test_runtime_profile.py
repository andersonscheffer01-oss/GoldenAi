from pathlib import Path

import pytest

import mt5_connector
from jarvis_core.runtime_profile import (
    DEFAULT_PROFILE,
    WEB_AI_SAFE_PROFILE,
    active_runtime_profile,
    resolve_runtime_profile,
    set_active_runtime_profile,
)
from jarvis_core.service import JarvisService
from jarvis_core.tools import market_readonly as market
import market_data


def test_safe_profile_is_explicit_and_invalid_profiles_fail_closed():
    assert resolve_runtime_profile("web-ai-safe") is WEB_AI_SAFE_PROFILE
    assert WEB_AI_SAFE_PROFILE.status()["mt5"] == "DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.status()["voice"] == "DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/jarvis/voice/status") == "VOICE_DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/mt5/status") == "MT5_DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.status()["market_data_read"] == "ENABLED"
    assert WEB_AI_SAFE_PROFILE.status()["mt5_market_data_read"] == "ENABLED"
    assert WEB_AI_SAFE_PROFILE.status()["trading"] == "DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.tool_disabled_reason("golden_panel_market_snapshot") == ""
    assert WEB_AI_SAFE_PROFILE.tool_disabled_reason("golden_panel_market_update") == ""
    for mutation in ("order_send", "position_close", "position_modify",
                     "pending_order_cancel", "autotrading_change", "broker_mutation"):
        assert WEB_AI_SAFE_PROFILE.tool_disabled_reason(mutation) == "TRADING_DISABLED_BY_PROFILE"
    with pytest.raises(ValueError, match="Perfil de runtime invalido"):
        resolve_runtime_profile("unknown-profile")


def test_safe_service_keeps_canonical_core_and_blocks_disabled_tools(tmp_path):
    service = JarvisService(Path(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        assert service.runtime_profile_status()["service"] == "ENABLED"
        assert service.orchestrator is not None
        assert service.memory_boundary is not None
        assert service.security is not None
        assert service.audit is not None

        mt5_result = service.execute_tool("mt5_status", {})
        tester_result = service.execute_tool("strategy_tester_environment", {})
        market_result = service.execute_tool("golden_panel_market_snapshot", {})
        assert mt5_result["disabled_by_profile"] is True
        assert mt5_result["error"] == "MT5_DISABLED_BY_PROFILE"
        assert tester_result["disabled_by_profile"] is True
        assert tester_result["error"] == "STRATEGY_TESTER_DISABLED_BY_PROFILE"
        assert market_result.get("error") != "MARKET_DATA_READ_DISABLED_BY_PROFILE"
        market_tool = service.registry.get("golden_panel_market_snapshot")
        assert market_tool.side_effect_class.value == "READ_ONLY"
        live_market_tool = service.registry.get("golden_panel_market_update")
        assert live_market_tool.side_effect_class.value == "READ_ONLY"
        assert service.registry.get("order_send") is None
        assert service.registry.get("position_close") is None
        assert service.registry.get("autotrading_change") is None
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_safe_read_models_never_open_mt5(monkeypatch):
    set_active_runtime_profile(WEB_AI_SAFE_PROFILE)
    try:
        def fail_if_called():
            raise AssertionError("ensure_connection must not run in web-ai-safe")

        monkeypatch.setattr(market, "_terminal_available", lambda: False)
        result = market.mt5_status()
        assert result["status"] == "DISABLED_BY_PROFILE"
        assert result["availability"] == "SOURCE_DISABLED"

        monkeypatch.setattr(market_data, "_mt5_enabled", lambda override=None: False)
        monkeypatch.setattr(market_data, "ensure_connection", fail_if_called, raising=False)
        chart = market_data.get_market_chart()
        assert chart["error"] == "SOURCE_DISABLED: MT5_DISABLED_BY_PROFILE"
    finally:
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_safe_bridge_read_paths_never_reach_connector(monkeypatch, tmp_path):
    calls = []

    def fail_if_called():
        calls.append("ensure_connection")
        raise AssertionError("ensure_connection must not run in web-ai-safe")

    monkeypatch.setattr(mt5_connector, "ensure_connection", fail_if_called)
    monkeypatch.setattr(market_data, "_market_news", lambda: ([], "SOURCE_DISABLED"))
    monkeypatch.setattr(market_data, "_economic_calendar", lambda: ([], "SOURCE_DISABLED"))
    monkeypatch.setattr(market_data, "_macro_snapshot", lambda assets: {
        "indicators": [], "drivers": [], "reading": "UNAVAILABLE"})
    service = JarvisService(Path(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        context = service.market_context_snapshot({"symbol": "EURUSD", "timeframe": "H1"})
        bridge_context = service.golden_bridge.market_context("EURUSD", "H1")
        radar = service.golden_bridge.radar_snapshot("EURUSD", 3)
        scanner = service.golden_bridge.scanner_snapshot("EURUSD", 1)
        deep = service.golden_bridge.deep_analysis_context("EURUSD")
        readonly = service.golden_bridge.mt5_read_snapshot()

        assert context["context"]["symbol"] == "EURUSD"
        assert context["context"]["timeframe"] == "H1"
        assert context["context"]["availability"] == "UNAVAILABLE"
        assert bridge_context["data"]["status"] == "SOURCE_DISABLED"
        assert radar["data"]["sources"][0]["state"] == "offline"
        assert scanner["data"]["status"] == "SOURCE_DISABLED"
        assert deep["data"]["context"]["ok"] is False
        assert readonly["data"]["status"] == "SOURCE_DISABLED"
        assert calls == []
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_safe_server_profile_blocks_legacy_mt5_routes():
    assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/meta_strategy") == "MT5_DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/scanner/scan") == "MT5_DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/chart_data") == "MT5_DISABLED_BY_PROFILE"
    assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/market/chart") == ""


def test_connector_boundary_fails_closed_without_initialize(monkeypatch):
    set_active_runtime_profile(WEB_AI_SAFE_PROFILE)
    initialize_calls = []
    monkeypatch.setattr(mt5_connector.mt5, "initialize",
                        lambda *args, **kwargs: initialize_calls.append(True))
    try:
        assert mt5_connector.ensure_connection() is False
        assert initialize_calls == []
    finally:
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_default_profile_keeps_mt5_path_available_under_mock(monkeypatch):
    set_active_runtime_profile(DEFAULT_PROFILE)
    calls = []
    monkeypatch.setattr(mt5_connector, "ensure_connection",
                        lambda: calls.append(True) or False)
    try:
        result = market_data.get_market_chart("EURUSD", "H1", mt5_enabled=True)
        assert calls == [True]
        assert result["error"] == "MetaTrader 5 desconectado"
    finally:
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_default_profile_preserves_operational_capabilities():
    status = DEFAULT_PROFILE.status()
    assert status["mt5"] == "ENABLED"
    assert status["voice"] == "ENABLED"
    assert status["trading"] == "ENABLED"
    assert active_runtime_profile() is DEFAULT_PROFILE
