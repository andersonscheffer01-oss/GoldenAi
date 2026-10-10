from pathlib import Path

from jarvis_core.golden_bridge import GoldenReadBridge
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.http_perimeter import HttpPerimeter
from jarvis_core.models import Risk, SideEffectClass
from jarvis_core.runtime_profile import (
    WEB_AI_SAFE_PROFILE,
    active_runtime_profile,
    set_active_runtime_profile,
)
from jarvis_core.service import JarvisService


ROOT = Path(__file__).resolve().parents[1]


def test_statistics_projection_uses_existing_engine_without_cache_write(monkeypatch):
    import statistics_engine

    class ReadOnlyEngine:
        def get_strategy_performance(self):
            return {"SCALP_TEST": {"total": 4}}

        def get_asset_performance(self):
            return {}

        def get_hourly_performance(self):
            return {}

        def get_regime_performance(self):
            return {}

        def get_mode_performance(self):
            return {}

        def get_score_calibration(self):
            return {"calibrated": False}

        def get_walk_forward(self):
            return {"sufficient_data": False}

        def get_confidence_status(self):
            return {"total_strategies": 1}

        def get_full_dashboard(self):
            raise AssertionError("legacy dashboard method persists cached_stats")

    monkeypatch.setattr(statistics_engine, "get_engine", ReadOnlyEngine)
    result = GoldenReadBridge().statistics_snapshot()

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["data"]["cache_written"] is False
    assert result["data"]["strategy_performance"]["SCALP_TEST"]["total"] == 4


def test_statistics_tool_is_canonical_read_only(tmp_path):
    previous_profile = active_runtime_profile()
    service = JarvisService(tmp_path, runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        tool = service.registry.get("golden_statistics_snapshot")
        assert tool is not None
        assert tool.risk == Risk.LOW
        assert tool.side_effect_class == SideEffectClass.READ_ONLY
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(tool.security_requirements)
        assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/jarvis/golden/statistics") == ""
        assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/statistics/full") == "MT5_DISABLED_BY_PROFILE"
        assert WEB_AI_SAFE_PROFILE.api_disabled_reason("/api/scanner/radar") == "MT5_DISABLED_BY_PROFILE"
    finally:
        service.close()
        set_active_runtime_profile(previous_profile)


def test_dashboard_canonical_read_routes_require_bearer_auth():
    perimeter = HttpPerimeter(auth_manager=AuthManager(_token="ui1-test-token"))
    path = "/api/jarvis/golden/statistics"
    assert perimeter.route_class("POST", path) == "AUTHENTICATED"
    denied = perimeter.authorize("POST", path, {}, source_ip="127.0.0.1")
    allowed = perimeter.authorize(
        "POST", path,
        {"Authorization": "Bearer ui1-test-token", "Origin": "http://127.0.0.1:8765"},
        source_ip="127.0.0.1",
    )
    assert denied.status_code == 401
    assert allowed.allowed is True


def test_dashboard_read_controls_use_jarvis_and_trading_paths_stay_inert():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    server = (ROOT / "server_agent.py").read_text(encoding="utf-8")
    radar = html[html.index("async function scannerRadar()"):html.index("function openAssetDetail(")]
    stats = html[html.index("async function scannerStatistics()"):html.index("async function runValidation(")]
    trade = html[html.index("function toggleAutoTrade()"):html.index("async function scannerRadar()")]

    assert "/api/jarvis/golden/radar" in radar
    assert "/api/scanner/radar" not in radar
    assert "/api/jarvis/golden/statistics" in stats
    assert "/api/statistics/full" not in stats
    assert "golden_statistics_snapshot" in server
    assert "disabled title=\"Execução legada permanece bloqueada\"" in html
    assert "/api/mt5/auto_trade" not in trade


def test_dashboard_scanner_catalog_and_order_callbacks_are_safe():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    scan_all = html[html.index("async function scannerScanAll()"):html.index("// ═══ RISK ENGINE STATUS")]
    auto_trade = html[html.index("async function executeAutoTrade()"):html.index("async function showTradePositions()")]
    modal_trade = html[html.index("async function executeTradeFromModal("):html.index("async function runDeepAnalysis(")]
    auto_start = html[html.index("function toggleAutoTrade()"):html.index("async function scannerRadar()")]

    assert "/api/jarvis/golden/scanner" in scan_all
    assert "model.scans" in scan_all and "model.scan" in scan_all
    assert "return;" in auto_trade.split("\n", 2)[1]
    assert "return;" in modal_trade.split("\n", 2)[1]
    assert "autoTradeEnabled = false" in auto_start
    assert "/api/mt5/auto_trade" not in auto_start


def test_strategy_catalog_does_not_invent_activation_state():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    loader = html[html.index("async function loadStrategies()"):html.index("function renderStrategyStats(")]

    assert "enabled:false" not in loader
    assert "Estado de ativação" in html
    assert "SOMENTE LEITURA" in html
