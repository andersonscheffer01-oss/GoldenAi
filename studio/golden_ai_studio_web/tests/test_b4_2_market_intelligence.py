from pathlib import Path

from jarvis_core.golden_bridge import GoldenReadBridge
from jarvis_core.market_read_models import (
    SOURCE_DISABLED,
    UNKNOWN,
    build_market_intelligence_snapshot,
    session_observation,
)
from jarvis_core.models import Risk, SideEffectClass
from jarvis_core.service import JarvisService


def _envelope(data, status="AVAILABLE", source="fixture"):
    return {
        "ok": status == "AVAILABLE",
        "availability": status,
        "freshness": "FRESH" if status == "AVAILABLE" else status,
        "observed_at": "2026-09-29T12:00:00+00:00",
        "provenance": {"source_module": source, "provider": source,
                       "freshness_state": "FRESH"},
        "data": data,
    }


def test_market_snapshot_normalizes_provenance_and_preserves_unknowns():
    payload = build_market_intelligence_snapshot(
        overview=_envelope({
            "updated_at": "2026-09-29T12:00:00+00:00",
            "assets": [{"symbol": "XAUUSD", "price": 2300.0, "group": "Metais"}],
            "news": [
                {"title": "Gold", "url": "https://example.test/gold", "source": "A"},
                {"title": "Gold", "url": "https://example.test/gold", "source": "A"},
            ],
            "macro": {"indicators": [{"id": "CPI", "name": "CPI", "value": 3.2, "unit": "%"}]},
            "economic_calendar": [],
            "sources": [{"name": "Fixture", "state": "online"}],
        }),
        chart=_envelope({"price": 2300.0, "candles": [], "levels": [], "structure_events": []}),
        scanner=_envelope({"normalized_results": [{
            "symbol": "XAUUSD", "selected_setup": "BOS", "score": 72,
            "readiness": "SETUP_DETECTED", "market_regime": "TREND",
        }]}),
        risk=_envelope({"risk_state": "UNKNOWN"}),
        validation=_envelope({"history": [{"evidence_class": "BACKTEST"}]}),
        symbol="XAUUSD", timeframe="M15", correlation_id="corr-b42",
    )

    assert payload["read_only"] is True
    assert payload["snapshot_id"].startswith("market_snapshot_")
    assert payload["correlation_id"] == "corr-b42"
    assert len(payload["news"]) == 1
    assert payload["news"][0]["sentiment"] == UNKNOWN
    assert payload["scanner"]["score_semantics"] == "SCORE_NOT_PROBABILITY"
    assert payload["robot_matcher_precursors"]["setup"] == "BOS"
    assert payload["performance"]["evidence_type_counts"] == {"BACKTEST": 1}
    assert "NO_VERIFIED_METRICS_IN_SOURCE" in payload["performance"]["limitations"]
    assert payload["matcher_authority"] == "NOT_IMPLEMENTED_IN_B4_2"


def test_source_disabled_is_explicit_and_never_becomes_zero():
    payload = build_market_intelligence_snapshot(
        overview=_envelope({"assets": [], "news": [], "macro": {}}, SOURCE_DISABLED),
        chart=_envelope({}, SOURCE_DISABLED),
        scanner=_envelope({}, SOURCE_DISABLED),
        risk=_envelope({}, SOURCE_DISABLED),
        validation=_envelope({}, SOURCE_DISABLED),
        symbol="XAUUSD", timeframe="M15", correlation_id="corr-disabled",
    )
    assert payload["status"] == SOURCE_DISABLED
    assert payload["source_availability"]["scanner"]["status"] == SOURCE_DISABLED
    assert payload["market_map"] == []
    assert payload["performance"]["sample_count"] == 0


def test_session_observation_uses_iana_dst_boundaries():
    from datetime import datetime, timezone

    london_before = session_observation(datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc))
    london_after = session_observation(datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc))
    new_york_before = session_observation(datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc))
    new_york_after = session_observation(datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc))

    assert london_before["sessions"]["LONDON"]["utc_offset"] == 0
    assert london_after["sessions"]["LONDON"]["utc_offset"] == 1
    assert new_york_before["sessions"]["NEW_YORK"]["utc_offset"] == -5
    assert new_york_after["sessions"]["NEW_YORK"]["utc_offset"] == -4


def test_bridge_builds_one_correlated_read_snapshot_without_execution():
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {"mt5_enabled": False})())
    bridge._market_overview = lambda: {"ok": True, "assets": [], "macro": {}, "news": []}
    bridge._market_chart = lambda symbol, timeframe: {"ok": False, "status": "SOURCE_DISABLED"}
    bridge.scanner_snapshot = lambda symbol, limit: {"ok": False, "availability": SOURCE_DISABLED, "data": {}}
    bridge.risk_detail = lambda: {"ok": False, "availability": SOURCE_DISABLED, "data": {}}
    bridge.validation_detail = lambda limit: {"ok": True, "data": {"history": []}}

    result = bridge.market_intelligence_snapshot("XAUUSD", "M15", "corr-test")

    assert result["ok"] is True
    assert result["correlation_id"] == "corr-test"
    assert result["data"]["execution_authority"] == "NONE"
    assert result["data"]["source_availability"]["risk"]["status"] == SOURCE_DISABLED


def test_service_exposes_b42_snapshot_as_low_risk_read_only_tool(tmp_path):
    service = JarvisService(str(tmp_path))
    try:
        tool = service.registry.get("golden_market_intelligence_snapshot")
        assert tool is not None
        assert tool.risk == Risk.LOW
        assert tool.side_effect_class == SideEffectClass.READ_ONLY
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(tool.security_requirements)
    finally:
        service.close()


def test_b42_route_and_ui_keep_one_canonical_market_boundary():
    root = Path(__file__).resolve().parents[1]
    server = (root / "server_agent.py").read_text(encoding="utf-8")
    app = (root / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "/api/jarvis/golden/market-intelligence" in server
    assert "golden_market_intelligence_snapshot" in server
    assert "/api/jarvis/golden/market-intelligence" in app
    assert "/api/scanner/" not in app[app.index("const b3State ="):app.index("window.JarvisB3Refresh")]
    assert "order_send" not in app[app.index("const b3State ="):app.index("window.JarvisB3Refresh")]
