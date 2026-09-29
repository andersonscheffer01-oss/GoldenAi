from pathlib import Path

from jarvis_core.models import Risk, SideEffectClass
from jarvis_core.service import JarvisService


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "jarvis_ui"


def test_robot_catalog_snapshot_is_canonical_read_only(tmp_path):
    service = JarvisService(tmp_path)
    try:
        tool = service.registry._tools["robot_catalog_snapshot"]
        assert tool.risk == Risk.LOW
        assert tool.side_effect_class == SideEffectClass.READ_ONLY
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(tool.security_requirements)
        assert tool.confirmation is False
    finally:
        service.close()


def test_b3_backend_routes_use_jarvis_read_boundary():
    source = (ROOT / "server_agent.py").read_text(encoding="utf-8")
    for route in (
        "/api/jarvis/golden/radar",
        "/api/jarvis/golden/scanner",
        "/api/jarvis/golden/robots",
        "/api/jarvis/golden/robot",
        "/api/jarvis/golden/evidence",
    ):
        assert route in source
    assert "return self._execute_jarvis_read(\"golden_scanner_snapshot\"" in source
    assert "return self._execute_jarvis_read(\"robot_catalog_snapshot\")" in source
    assert "side_effect_class\": \"READ_ONLY\"" in source


def test_b3_ui_uses_only_canonical_read_endpoints():
    source = (UI / "src" / "app.js").read_text(encoding="utf-8")
    start = source.index("const b3State =")
    end = source.index("window.JarvisB3Refresh", start)
    b3 = source[start:end]
    for route in (
        "/api/jarvis/golden/overview",
        "/api/jarvis/golden/radar",
        "/api/jarvis/golden/scanner",
        "/api/jarvis/golden/robots",
        "/api/jarvis/golden/evidence",
        "/api/jarvis/memory/scientific",
    ):
        assert route in b3
    assert "/api/mt5" not in b3
    assert "/api/scanner" not in b3
    assert "order_send" not in b3
    assert "strategy_tester" not in b3


def test_b3_ui_exposes_zero_execution_and_provenance_states():
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    css = (UI / "src" / "styles.css").read_text(encoding="utf-8")
    for element_id in (
        "gB3Overview", "gB3MarketAssets", "gB3Scanner", "gB3OpportunityDetail",
        "gB3Robots", "gB3Unresolved", "gB3Evidence", "gB3MemoryRelations", "gB3Provenance",
        "gB3MarketKpis", "gB3MarketChart", "gB3MarketHeatmap", "gB3MarketFlow", "gB3MarketTop", "gB3MarketNews",
    ):
        assert f'id="{element_id}"' in html
    assert "READ-ONLY · NO TRADING" in html
    assert ".gB3State" in css
    assert ".gB3MetricGrid" in css
    assert ".gB3MarketDashboard" in css
    assert "@media (max-width: 880px)" in css


def test_market_actions_open_b3_market_intelligence_instead_of_chat_command():
    source = (UI / "src" / "golden.js").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    assert 'label: "Analisar mercado", cmd: "analisar mercado"' not in source
    assert 'label: "Analisar mercado", action: "open_market_intelligence"' in source
    assert 'id="gB3MarketSection"' in html
    assert 'data-b3-target="gB3MarketSection"' in html
    assert "function openB3(target)" in source
    assert "api.submitCommand(p.cmd)" in source

    start = source.index("function openMarketIntelligence()")
    end = source.index("function expandedAtBottom", start)
    market_action = source[start:end]
    assert "api.submitCommand" not in market_action
    assert "window.open" in market_action
    assert 'target.hash = "market-intelligence"' in market_action


def test_market_window_reuses_b3_read_models_and_desktop_bridge():
    source = (UI / "src" / "golden.js").read_text(encoding="utf-8")
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    desktop = (ROOT / "jarvis_desktop" / "web_window.py").read_text(encoding="utf-8")
    css = (UI / "src" / "styles.css").read_text(encoding="utf-8")
    assert 'window.location.hash === "#market-intelligence"' in source
    assert 'const MARKET_WINDOW_MODE' in app
    assert "MarketIntelligenceWindow" in desktop
    assert "open_market_intelligence" in desktop
    assert 'url.host().lower() == "open-market-intelligence"' in desktop
    assert '#golden[data-market-window="1"]' in css
    assert "self.web_profile" in desktop


def test_market_window_reuses_existing_golden_web_market_surface():
    desktop = (ROOT / "jarvis_desktop" / "web_window.py").read_text(encoding="utf-8")
    settings = (ROOT / "jarvis_desktop" / "settings.py").read_text(encoding="utf-8")
    market = (ROOT / "market.html").read_text(encoding="utf-8")
    assert "def market_url(origin: str)" in settings
    assert "market_url(core_origin)" in desktop
    assert "#market-intelligence" not in desktop
    for script in ("market.js", "chart_terminal.js", "operational_center.js", "ai_radar.js"):
        assert f'src="{script}' in market


def test_b3_surfaces_and_scientific_memory_path_are_explicit():
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    for section_id in (
        "gB3OverviewSection", "gB3MarketSection", "gB3ScannerSection",
        "gB3RobotsSection", "gB3EvidenceSection", "gB3MemorySection",
        "gB3ProvenanceSection",
    ):
        assert f'id="{section_id}"' in html
    assert 'id="gB3Navigation"' in html
    assert 'data-b3-target="gB3MemorySection"' in html
    assert "ABRIR SCIENTIFIC MEMORY" in html


def test_b3_navigation_wiring_has_no_operational_backend_path():
    source = (UI / "src" / "golden.js").read_text(encoding="utf-8")
    start = source.index("function openB3(target)")
    end = source.index("function expandedAtBottom", start)
    navigation = source[start:end]
    assert "order_send" not in navigation
    assert "/api/mt5" not in navigation
    assert "strategy_tester" not in navigation
    assert "api.submitCommand" not in navigation


def test_b3_market_surface_is_read_model_only_and_filterable():
    source = (UI / "src" / "app.js").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    market_start = source.index("function b3RenderMarket(response)")
    market_end = source.index("function b3RenderScanner(response)", market_start)
    market = source[market_start:market_end]
    assert "data.technical_state" in market
    assert "gB3MarketGroup" in market
    assert "gB3MarketHeatmap" in market
    assert "data.capital_flow" in market
    assert "api.submitCommand" not in market
    assert "/api/market/" not in market
    for element_id in ("gB3MarketGroup", "gB3MarketChartState", "gB3MarketFlow", "gB3MarketTop", "gB3MarketNews"):
        assert f'id="{element_id}"' in html


def test_b3_market_states_do_not_replace_missing_data_with_reference_values():
    source = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "Fluxo de capitais não fornecido pelo read model" in source
    assert "DATA UNAVAILABLE" in source
    assert "Nenhuma notícia verificável disponível" in source


def test_b3_market_runtime_surface_switch_is_explicit_and_hnum_free():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    golden = (UI / "src" / "golden.js").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    css = (UI / "src" / "styles.css").read_text(encoding="utf-8")
    assert "hNum" not in app
    assert "hNum" not in golden
    assert "function setMarketSurface(target)" in golden
    assert 'root.dataset.marketSurfaceVersion = "b3-market-v2"' in golden
    assert "node.hidden = !active" in golden
    assert 'id="gAiCoreSection"' in html
    assert "#gAiCoreSection" in css


def test_b3_market_runtime_surface_has_single_active_tab_contract():
    source = (UI / "src" / "golden.js").read_text(encoding="utf-8")
    for section_id in (
        "gB3OverviewSection", "gB3MarketSection", "gB3ScannerSection",
        "gB3RobotsSection", "gB3EvidenceSection", "gB3MemorySection",
        "gB3ProvenanceSection",
    ):
        assert f'"{section_id}"' in source
    assert "data-b3-surface-active" in source
    assert 'setMarketSurface("gB3MarketSection")' in source
