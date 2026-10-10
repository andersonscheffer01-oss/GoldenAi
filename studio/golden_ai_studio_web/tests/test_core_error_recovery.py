from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis_core import JarvisService
from jarvis_core.models import AgentState
from jarvis_core.runtime_profile import (
    DEFAULT_PROFILE,
    WEB_AI_SAFE_PROFILE,
    set_active_runtime_profile,
)


@pytest.mark.parametrize("source_status", ["SOURCE_UNAVAILABLE", "SOURCE_DISABLED"])
def test_optional_read_only_discovery_does_not_fail_core_service(
    tmp_path, monkeypatch, source_status
):
    from jarvis_core.tools import market_readonly

    monkeypatch.setattr(market_readonly, "mt5_search_symbols", lambda *_args: {
        "ok": False,
        "status": source_status,
        "provider": "MT5",
        "assets": [],
        "reason": "APPROVED_TERMINAL_NOT_RUNNING",
    })
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        result = service.execute_tool(
            "golden_panel_symbol_discovery",
            {"query": "", "asset_class": "ALL", "correlation_id": "startup"},
        )

        assert result["ok"] is True
        assert result["data"]["ok"] is False
        assert result["data"]["status"] == source_status
        assert result["data"]["sources"]["MT5"]["status"] == source_status
        assert result["availability"] == "UNAVAILABLE"
        assert result["health"] == "DEGRADED"
        assert result["state"] == "IDLE"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_error_transition_records_sanitized_diagnostic_without_changing_state(
    tmp_path,
):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service._set_state(AgentState.ERROR, "HTTP 503 token=redacted")
        event = service._last_state_transition
        assert service.state.value == "ERROR"
        assert event["previous_state"] == "IDLE"
        assert event["new_state"] == "ERROR"
        assert event["component"] == "JarvisService.execute_tool"
        assert "token=redacted" in event["reason"]
        assert "Authorization" not in str(event)
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


@pytest.mark.parametrize("source_status", ["SOURCE_UNAVAILABLE", "SOURCE_DISABLED"])
@pytest.mark.parametrize("tool_name", [
    "golden_panel_market_snapshot", "golden_panel_market_update",
])
def test_optional_market_snapshot_is_degraded_without_failing_core_service(
    tmp_path, monkeypatch, source_status, tool_name
):
    from jarvis_core.tools import market_readonly

    unavailable = lambda *_args: {
        "ok": False,
        "status": source_status,
        "provider": "MT5",
        "provider_symbol": "BTCUSD",
        "asset_class": "CRYPTO",
        "reason": "APPROVED_TERMINAL_NOT_RUNNING",
        "candles": [],
        "read_only": True,
        "execution_authority": "NONE",
    }
    monkeypatch.setattr(market_readonly, "mt5_market_data_snapshot", unavailable)
    monkeypatch.setattr(market_readonly, "mt5_market_data_update", unavailable)
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        assert service.state.value == "IDLE"
        arguments = {
            "provider": "MT5",
            "provider_asset_id": "mt5:BTCUSD",
            "provider_symbol": "BTCUSD",
            "asset_class": "CRYPTO",
            "timeframe": "M15",
            "correlation_id": "market-source-unavailable",
        }
        if tool_name == "golden_panel_market_snapshot":
            arguments["count"] = 120
        result = service.execute_tool(tool_name, arguments)

        assert result["ok"] is True
        assert result["data"]["ok"] is False
        assert result["data"]["status"] == source_status
        assert result["data"]["reason"] == "APPROVED_TERMINAL_NOT_RUNNING"
        assert result["availability"] == "UNAVAILABLE"
        assert result["health"] == "DEGRADED"
        assert result["state"] == "IDLE"
        assert service.state.value == "IDLE"
        audit = service.audit.recent(1)[0]
        assert audit["tool"] == tool_name
        assert audit["status"] == "executado"
        assert audit["audit_envelope"]["status"] == "EXECUTION_SUCCEEDED"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


@pytest.mark.parametrize("tool_name", [
    "golden_panel_market_snapshot", "golden_panel_market_update",
])
def test_real_provider_classification_mismatch_still_fails_closed(
    tmp_path, monkeypatch, tool_name
):
    from jarvis_core.tools import market_readonly

    mismatched = lambda *_args: {
        "ok": True,
        "status": "PARTIAL",
        "provider": "MT5",
        "asset_class": "FOREX",
        "asset": {"provider": "MT5", "provider_symbol": "BTCUSD",
                  "asset_class": "FOREX"},
        "candles": [],
        "read_only": True,
        "execution_authority": "NONE",
    }
    monkeypatch.setattr(market_readonly, "mt5_market_data_snapshot", mismatched)
    monkeypatch.setattr(market_readonly, "mt5_market_data_update", mismatched)
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        arguments = {
            "provider": "MT5",
            "provider_asset_id": "mt5:BTCUSD",
            "provider_symbol": "BTCUSD",
            "asset_class": "CRYPTO",
            "timeframe": "M15",
            "correlation_id": "market-identity-mismatch",
        }
        if tool_name == "golden_panel_market_snapshot":
            arguments["count"] = 120
        result = service.execute_tool(tool_name, arguments)

        assert result["ok"] is False
        assert result["data"]["ok"] is False
        assert result["data"]["status"] == "IDENTITY_MISMATCH"
        assert result["data"]["reason"] == "PROVIDER_CLASSIFICATION_CHANGED"
        assert result["state"] == "ERROR"
        assert service.state.value == "ERROR"
        audit = service.audit.recent(1)[0]
        assert audit["tool"] == tool_name
        assert audit["status"] == "falhou"
        assert audit["audit_envelope"]["status"] == "EXECUTION_FAILED"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


@pytest.mark.parametrize("tool_name", [
    "golden_panel_market_snapshot", "golden_panel_market_update",
])
def test_unknown_provider_classification_is_not_reported_as_mismatch(
    tmp_path, monkeypatch, tool_name
):
    from jarvis_core.tools import market_readonly

    unknown = lambda *_args: {
        "ok": True,
        "status": "PARTIAL",
        "provider": "MT5",
        "provider_symbol": "BTCUSD",
        "candles": [],
        "read_only": True,
        "execution_authority": "NONE",
    }
    monkeypatch.setattr(market_readonly, "mt5_market_data_snapshot", unknown)
    monkeypatch.setattr(market_readonly, "mt5_market_data_update", unknown)
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        arguments = {
            "provider": "MT5",
            "provider_asset_id": "mt5:BTCUSD",
            "provider_symbol": "BTCUSD",
            "asset_class": "CRYPTO",
            "timeframe": "M15",
            "correlation_id": "market-classification-unknown",
        }
        if tool_name == "golden_panel_market_snapshot":
            arguments["count"] = 120
        result = service.execute_tool(tool_name, arguments)

        assert result["ok"] is False
        assert result["data"]["status"] == "IDENTITY_UNVERIFIED"
        assert result["data"]["reason"] == "PROVIDER_CLASSIFICATION_UNAVAILABLE"
        assert result["state"] == "ERROR"
        assert service.state.value == "ERROR"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)
