import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis_desktop.core_launcher import CoreLauncher, HTTPS_HEALTH_URL


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "jarvis_ui"
HTML = UI / "jarvis.html"
SHELL_JS = UI / "src" / "desktop-shell.js"
SHELL_CSS = UI / "src" / "desktop-shell.css"


def test_desktop_shell_is_gated_to_canonical_desktop_runtime():
    source = SHELL_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    assert 'window.__JARVIS_DESKTOP__ === true' in source
    assert 'src="src/desktop-shell.js' in html
    assert 'href="src/desktop-shell.css' in html
    assert 'desktop-shell.js?v=20261108-golden-arena-1' in html
    assert 'desktop-shell.css?v=20261108-golden-arena-1' in html
    assert "desktop-identity" not in source.lower()
    assert "jarvis_device_token" not in source


def test_shell_routes_to_existing_jarvis_views_and_single_workspace():
    source = SHELL_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    required_routes = {
        "jarvis", "painel", "analise", "operacoes", "performance",
        "historico", "robos", "backtests", "tarefas", "memoria", "seguranca",
    }

    for route in required_routes:
        assert f'data-d2-route="{route}"' in html
        assert f"{route}:" in source

    assert 'jarvis.golden.setView(target.view)' in source
    assert 'id="d2JarvisAccess"' in html
    assert "QWebEngineView" not in source
    assert "window.open(" not in source


def test_operational_mode_and_unavailable_states_are_honest():
    source = SHELL_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    assert 'operational_mode: "ANALYSIS"' in source
    assert "LIVE NÃO AUTORIZADO" in html
    assert "MT5_CONNECTED" not in source
    assert "MT5_CONNECTED" not in html
    assert 'class="d2DemoBadge">PAINEL · LEITURA SOMENTE' in html
    assert re.search(r"hydrateDemoViews\(\)", source)
    assert "LIVE NÃO AUTORIZADO" in html


def test_core_agent_state_uses_authenticated_gateway_read_model():
    source = SHELL_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    assert 'window.Gateway?.isAuthenticated' in source
    assert 'window.Gateway.httpGet("/api/desktop/status")' in source
    assert 'status?.state' in source
    assert 'AGENT STATE: ${state}' in source
    assert 'AGENT STATE: UNKNOWN' in source
    assert 'window.Gateway?.on("authenticated", updateCoreState)' in source
    assert 'id="d2CoreState"' in html
    assert 'src="src/desktop-shell.js?v=20261108-golden-arena-1"' in html
    assert source.index('if (!window.Gateway?.isAuthenticated)') < source.index('window.Gateway.httpGet("/api/desktop/status")')
    assert 'gatewayStatus?.dataset.state' not in source
    assert source.count('searchPanelAssets("")') == 1
    assert 'ensureCatalog: () => ensurePanelCatalog()' in source
    assert 'input.addEventListener("focus", () =>' in source
    assert 'if (loadCatalog) options.ensureCatalog?.()' in source


def test_operations_controls_are_disabled_and_have_no_trade_handlers():
    source = SHELL_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    operations = re.search(
        r'<section class="gView d2View d2DonorView d2OperationsView" data-view="d2-operations"(?:(?!<section class="gView).)*',
        html,
        flags=re.DOTALL,
    )

    assert operations
    assert operations.group(0).count(" disabled") >= 3
    assert "submitCommand" not in source
    assert "/api/jarvis/golden/panel-analysis" in source
    assert "/api/market/" not in source
    assert "httpPost" in source
    assert "order_send" not in source.lower()


def test_operations_view_reads_canonical_mt5_snapshot_without_mutation():
    source = SHELL_JS.read_text(encoding="utf-8")
    assert "loadCanonicalOperations" in source
    assert 'window.Gateway.httpPost("/api/jarvis/golden/overview"' in source
    assert "include_live: true" in source
    assert 'execution_authority === "NONE"' in source
    assert "data-operations-positions" in HTML.read_text(encoding="utf-8")
    assert "data-operations-orders" in HTML.read_text(encoding="utf-8")
    assert "order_send" not in source.lower()


def test_five_views_keep_distinct_donor_hierarchies_and_local_controls():
    html = HTML.read_text(encoding="utf-8")
    source = SHELL_JS.read_text(encoding="utf-8")

    assert 'data-view="d2-panel"' in html
    assert 'data-view="d2-analysis"' in html
    assert 'data-view="d2-operations"' in html
    assert 'data-view="d2-performance"' in html
    assert 'data-view="d2-history"' in html
    assert "d2PanelDonorColumns" in html
    assert "d2CriteriaList" in html
    assert "d2OpsLedger" in html
    assert "d2EquityChart" in html
    assert "d2TradeInspector" in html
    assert 'data-d2-period' in html and 'data-d2-history-period' in html
    assert 'data-d2-symbol' in html
    assert 'radar: { view: "controle"' in source
    assert "window.open(" not in source
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source


def test_primary_views_reproduce_donor_copy_as_explicit_demo_data():
    html = HTML.read_text(encoding="utf-8")
    panel = re.search(
        r'<section class="gView d2View d2DonorView d2PanelView"(?:(?!<section class="gView).)*',
        html,
        flags=re.DOTALL,
    ).group(0)
    shell = SHELL_JS.read_text(encoding="utf-8")
    history = re.search(
        r'<section class="gView d2View d2DonorView d2HistoryView"(?:(?!<section class="gView).)*',
        html,
        flags=re.DOTALL,
    ).group(0)

    assert all(f">{label}<" in panel for label in ("OPERAÇÕES", "TAKE", "STOP", "RESULTADO"))
    assert panel.count("<svg") >= 4
    assert 'class="d2HistoryHeaderPanel"' in history
    assert "Tese Neural" in shell
    assert "TESE ALGORÍTMICA NO MOMENTO DA ORDEM" in shell
    assert "CHECKLIST DOS 7 FILTROS" in shell
    panel_runtime = shell[shell.index('panel.innerHTML = `'):shell.index('analysis.innerHTML = `')]
    assert "data-panel-analysis" in panel_runtime
    assert "UNAVAILABLE" in panel_runtime
    assert all(value not in panel_runtime for value in ("+US$ 28,00", "4.139,14", "VIÉS DE BAIXA"))
    assert all(value in shell for value in ("#9842104", "2734.20", "+US$ 1.842,50"))
    assert shell.count("d2DemoNotice") >= 5
    assert "DEMONSTRAÇÃO · POSIÇÕES, ORDENS" in shell


def test_panel_analysis_uses_authenticated_core_read_model_and_prevents_duplicates():
    source = SHELL_JS.read_text(encoding="utf-8")
    panel = source[source.index('panel.innerHTML = `'):source.index('analysis.innerHTML = `')]
    css = SHELL_CSS.read_text(encoding="utf-8")

    assert '"/api/jarvis/golden/panel-analysis"' in source
    assert "panelAnalysisRunning" in source
    assert "analysisButton.disabled = true" in source
    assert "LIVE NÃO AUTORIZADO" in source
    assert "order_send" not in source.lower()
    assert "fetch(" not in panel
    assert "httpPost" in source
    assert '#app[data-desktop-shell="1"] .gView { flex: 0 0 100%;' in css
    assert "overflow-y: auto" in css
    assert "overflow-x: hidden" in css


def test_panel_analysis_allows_unknown_time_for_core_recency_gate_only():
    source = SHELL_JS.read_text(encoding="utf-8")
    start = source.index("function analysisEligibilityReason()")
    end = source.index("function setMarketChartState", start)
    eligibility = source[start:end]

    assert "selectedIdentityValidated" in eligibility
    assert "snapshotAsset?.provider !== selectedPanelAsset.provider" in eligibility
    assert "snapshotAsset?.asset_id !== selectedPanelAsset.provider_asset_id" in eligibility
    assert "snapshotAsset?.provider_asset_id !== selectedPanelAsset.provider_asset_id" not in eligibility
    assert "snapshotAsset?.provider_symbol !== selectedPanelAsset.provider_symbol" in eligibility
    assert "panelMarketSnapshot.timeframe !== selectedTimeframe" in eligibility
    assert "panelMarketSnapshot.state?.market_data_available !== true" in eligibility
    assert "window.Gateway?.isAuthenticated !== true" in eligibility
    assert '["FRESH", "UNKNOWN"]' in eligibility
    assert 'freshness === "STALE"' in eligibility
    assert "TIME STATUS UNKNOWN" in source
    assert "RECÊNCIA A VALIDAR PELO CORE" in source
    assert "TIME STATUS UNKNOWN · ${candles.length} CANDLES REAIS · GOLDENAI BLOQUEADA" not in source


def test_jarvis_shell_assets_are_not_cached_by_the_http_handler(monkeypatch):
    from http.server import SimpleHTTPRequestHandler
    from server_agent import GoldenAIHandler

    monkeypatch.setattr(SimpleHTTPRequestHandler, "end_headers", lambda _self: None)
    for path in ("/jarvis_ui/jarvis.html",
                 "/jarvis_ui/src/desktop-shell.js?v=fixture",
                 "/jarvis_ui/src/desktop-shell.css?v=fixture"):
        handler = object.__new__(GoldenAIHandler)
        handler.path = path
        headers = []
        handler.send_header = lambda name, value: headers.append((name, value))
        handler.end_headers()
        assert ("Cache-Control", "no-store") in headers

    api_handler = object.__new__(GoldenAIHandler)
    api_handler.path = "/api/jarvis/desktop/status"
    api_headers = []
    api_handler.send_header = lambda name, value: api_headers.append((name, value))
    api_handler.end_headers()
    assert not any(name.lower() == "cache-control" for name, _value in api_headers)


def test_panel_f1r_selector_uses_gateway_and_provider_identity_only():
    source = SHELL_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    panel = source[source.index('panel.innerHTML = `'):source.index('analysis.innerHTML = `')]

    assert '"/api/jarvis/golden/symbol-discovery"' in source
    assert '"/api/jarvis/golden/panel-analysis"' in source
    assert "provider_asset_id" in source and "asset_class" in source
    assert "localStorage.setItem(panelAssetStorageKey" in source
    assert "REVALIDAÇÃO NECESSÁRIA" in source
    assert "invalidatePanelAnalysis" in source
    assert "replaceChildren()" in source
    assert "fetch(" not in source and "XMLHttpRequest" not in source
    assert "BTCUSD" not in panel
    assert 'data-panel-asset-select' in source
    assert 'assetSelect?.addEventListener("change"' in source
    assert 'selectPanelAsset(discoveredAssets[index])' in source
    assert 'asset.provider_asset_id === `mt5:${asset.provider_symbol}`' in source
    assert 'ensureCatalog: () => ensurePanelCatalog()' in source
    assert 'input.addEventListener("focus", () =>' in source
    assert 'if (loadCatalog) options.ensureCatalog?.()' in source
    assert 'input.addEventListener("click", () =>' in source
    assert 'open();' in source
    assert 'searchPanelAssets("")' in source
    assert 'selectedIdentityValidated' in source
    assert 'REVALIDAÇÃO FALHOU' in source
    assert 'asset.provider_symbol === restoredIdentity.provider_symbol' in source
    assert 'asset.asset_class === restoredIdentity.asset_class' in source
    assert 'asset.source_available === true' in source
    assert 'asset.display_name' in source and 'option.textContent' in source
    assert 'asset_class: restoredIdentity.asset_class' in source
    assert 'scheduleMarketPoll(0)' in source
    assert 'await refreshLiveMarketUpdate(asset)' in source
    assert 'await refreshSelectedMarketSnapshot(asset)' in source
    assert 'provider: asset.provider' in source
    assert 'timeframe,' in source


def test_desktop_workspace_is_the_single_bounded_scroll_owner():
    css = SHELL_CSS.read_text(encoding="utf-8")
    shell_rules = re.findall(r'#app\[data-desktop-shell="1"\] #golden\.on \{([^}]+)\}', css)
    shell_root = next((rule for rule in shell_rules if "pointer-events: auto" in rule), None)
    view = re.search(r'#app\[data-desktop-shell="1"\] \.gView \{([^}]+)\}', css)

    assert shell_root and "pointer-events: auto" in shell_root
    assert "width: 100%" in shell_root
    assert "max-width: 100%" in shell_root
    assert view and "max-height: 100%" in view.group(1)
    assert "overflow-y: auto" in view.group(1)
    assert "overscroll-behavior-y: contain" in view.group(1)


def test_runtime_shell_contains_no_legacy_persona_label():
    # The screenshot copy names Lia; it is explicitly donor/demo text, not a new runtime persona.
    source = SHELL_JS.read_text(encoding="utf-8")
    assert "LIA NEURAL V2.4" in source
    assert "DEMONSTRAÇÃO" in source
    assert 'window.__JARVIS_DESKTOP__ === true' in source


def test_desktop_owned_core_starts_with_mt5_disabled_profile():
    process = MagicMock()
    process.poll.return_value = None
    popen = MagicMock(return_value=process)
    probes = iter((False, True))
    launcher = CoreLauncher(
        ROOT,
        popen=popen,
        runtime_profile="web-ai-safe",
        probe=lambda _url: next(probes),
        ui_probe=lambda _url: True,
        host_provider=lambda: "127.0.0.1",
    )

    with patch.object(launcher, "_port_in_use", return_value=False), patch(
        "jarvis_desktop.core_launcher.time.sleep"
    ):
        launcher.ensure_online()

    command = popen.call_args.args[0]
    assert command[-2:] == ["--runtime-profile", "web-ai-safe"]


def test_desktop_refuses_to_reuse_a_gateway_with_another_profile():
    response = MagicMock(status=200)
    response.read.return_value = (
        b'{"ok":true,"gateway":"running","runtime_profile":"default"}'
    )
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    launcher = CoreLauncher(ROOT, runtime_profile="web-ai-safe")

    with patch(
        "jarvis_desktop.core_launcher.urllib.request.urlopen",
        return_value=response,
    ):
        assert launcher.probe(HTTPS_HEALTH_URL) is False

