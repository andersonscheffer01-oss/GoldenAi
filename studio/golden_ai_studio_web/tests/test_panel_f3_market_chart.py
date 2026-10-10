from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "jarvis_ui"
HTML = (UI / "jarvis.html").read_text(encoding="utf-8")
SHELL = (UI / "src" / "desktop-shell.js").read_text(encoding="utf-8")
MARKET_READ = (ROOT / "jarvis_core" / "tools" / "market_readonly.py").read_text(encoding="utf-8")


def test_panel_replaces_demo_performance_region_with_read_only_market_chart():
    panel = SHELL[SHELL.index("panel.innerHTML = `"):SHELL.index("analysis.innerHTML = `")]

    assert "Desempenho no Dia" not in panel
    assert "data-market-chart-title" in panel
    assert "data-market-chart-quote" in panel
    assert "data-market-chart" in panel and "<canvas" in panel
    assert "d2PanelHistory" in panel
    assert "data-market-timeframe=\"M15\" aria-pressed=\"true\"" in panel


def test_chart_uses_only_timeframes_supported_by_canonical_mt5_reader():
    supported = set(re.findall(r'"(M\d+|H\d+|D\d+)"\s*:', MARKET_READ.split("_TIMEFRAMES =", 1)[1].split("}", 1)[0]))
    visible = set(re.findall(r'data-market-timeframe="([A-Z0-9]+)"', SHELL))

    assert supported == {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
    assert visible == supported - {"M30"}
    assert "M30" not in visible


def test_market_chart_and_analysis_share_selected_identity_and_timeframe():
    assert '"/api/jarvis/golden/market-data"' in SHELL
    assert '"/api/jarvis/golden/panel-analysis"' in SHELL
    assert "provider_asset_id: asset.provider_asset_id" in SHELL
    assert "timeframe,\n        count: 200" in SHELL
    assert "timeframe: submittedTimeframe" in SHELL
    assert "selectedPanelAsset?.provider_asset_id !== asset.provider_asset_id" in SHELL
    assert "selectedTimeframe !== timeframe" in SHELL
    assert "selectedTimeframe !== submittedTimeframe" in SHELL
    assert '"/api/jarvis/golden/market-live"' in SHELL


def test_unknown_time_can_reach_core_gate_but_stale_evidence_stays_blocked():
    assert 'quote.last' in SHELL and 'quote.bid' in SHELL and 'quote.ask' in SHELL
    assert '"TIME STATUS UNKNOWN"' in SHELL
    assert 'panelMarketSnapshot?.state?.market_data_available === true' in SHELL
    assert '["FRESH", "UNKNOWN"]' in SHELL
    assert 'panelMarketSnapshot?.asset?.provider_symbol === selectedPanelAsset?.provider_symbol' in SHELL
    assert 'panelMarketSnapshot?.asset?.asset_id === selectedPanelAsset?.provider_asset_id' in SHELL
    assert 'panelMarketSnapshot?.asset?.asset_class === selectedPanelAsset?.asset_class' in SHELL
    assert 'panelMarketSnapshot?.timeframe === selectedTimeframe' in SHELL
    assert 'window.Gateway?.isAuthenticated === true' in SHELL
    assert 'if (!selectedPanelAsset || !analysisEligible())' in SHELL
    assert "GOLDENAI BLOQUEADA" in SHELL


def test_polling_is_bounded_serial_and_cleaned_up_without_trade_authority():
    assert "const marketPollIntervalMs = 1200" in SHELL
    assert "const marketHistoryRefreshMs = 300000" in SHELL
    assert "marketPollRunning" in SHELL and "marketPollRequested" in SHELL
    assert 'addEventListener("visibilitychange", syncMarketPolling)' in SHELL
    assert 'addEventListener("pagehide", stopMarketPolling' in SHELL
    assert "await refreshLiveMarketUpdate(asset)" in SHELL
    assert "marketPollRunning" in SHELL
    assert "order_send" not in SHELL.lower()
    assert "fetch(" not in SHELL and "XMLHttpRequest" not in SHELL
    assert "coingecko" not in SHELL.lower() and "binance" not in SHELL.lower()


def test_live_view_reads_current_quote_and_one_forming_candle_only():
    assert "def mt5_market_data_update(" in MARKET_READ
    live_reader = MARKET_READ.split("def mt5_market_data_update(", 1)[1]
    assert 'copy_rates_from_pos(symbol, getattr(mt5, _TIMEFRAMES[timeframe]), 0, 1)' in live_reader
    assert 'symbol_info_tick(symbol)' in live_reader
    assert "account_info" not in live_reader
    assert "orders_get" not in live_reader
    assert "positions_get" not in live_reader
    assert "order_send" not in live_reader


def test_asset_dropdown_uses_only_authenticated_dynamic_mt5_catalog():
    assert '"/api/jarvis/golden/symbol-discovery"' in SHELL
    assert 'query: "", asset_class: "ALL"' in SHELL
    assert "data-panel-asset-select" in SHELL
    assert '<select data-panel-asset-select' in SHELL
    assert 'asset.provider === "MT5"' in SHELL
    assert 'asset.provider_asset_id === `mt5:${asset.provider_symbol}`' in SHELL
    assert 'METALS: "METAIS"' in SHELL and 'CRYPTO: "CRIPTO"' in SHELL
    assert 'assetSelect?.addEventListener("change"' in SHELL
    assert 'assetSelect?.addEventListener("focus", ensurePanelCatalog)' in SHELL
    assert 'assetSelect?.addEventListener("pointerdown", ensurePanelCatalog)' in SHELL
    route_handler = SHELL[SHELL.index("function selectRoute(route)"):SHELL.index('root.addEventListener("click"')]
    assert 'if (activeRoute === "painel") ensurePanelCatalog();' in route_handler
    assert 'if (activeRoute === "painel") ensurePanelCatalog();' in SHELL
    assert "BTCUSD" not in SHELL[SHELL.index('data-panel-asset-select'):SHELL.index('data-panel-analysis disabled')]
    panel_markup = SHELL[SHELL.index('panel.innerHTML = `'):SHELL.index('analysis.innerHTML = `')]
    assert 'data-panel-picker-toggle' not in panel_markup
    assert 'data-panel-asset-query' not in panel_markup
    assert 'data-panel-asset-class' not in panel_markup
    assert 'type="search"' not in panel_markup
    assert "AUTENTICAÇÃO NECESSÁRIA" in SHELL
    assert "Nenhum ativo MT5 disponível" in SHELL
    assert 'window.Gateway?.isAuthenticated' in SHELL


def test_restored_asset_revalidates_before_read_only_chart_poll():
    discovery = SHELL.index('post.call(gateway, "/api/jarvis/golden/symbol-discovery"')
    catalog_render = SHELL.index('renderAssetChoices(refreshed ? discovery.assets', discovery)
    revalidate = SHELL.index('if (refreshed && restoredPanelAsset) revalidateRestoredPanelAsset()', catalog_render)
    identity_match = SHELL.index('asset.provider_asset_id === restoredIdentity.provider_asset_id', revalidate)
    validated = SHELL.index('selectedIdentityValidated = true;', identity_match)
    polling = SHELL.index('syncMarketPolling();', validated)
    assert discovery < catalog_render < revalidate < identity_match < validated < polling
    assert 'source_available === true' in SHELL[identity_match:validated]
    assert 'scheduleMarketPoll(0)' in SHELL[SHELL.index('function selectPanelAsset'):SHELL.index('assetSelect?.addEventListener("change"')]
    assert 'drawMarketCandles(snapshot)' in SHELL


def test_live_chart_merge_and_lifecycle_reject_stale_asset_timeframe_and_hidden_responses():
    assert 'Number(last.time_epoch) === Number(update.candle.time_epoch)' in SHELL
    assert 'Number(update.candle.time_epoch) > Number(last.time_epoch)' in SHELL
    assert "candles.splice(0, candles.length - 200)" in SHELL
    assert "marketHistoryRefreshedAt = 0" in SHELL
    assert "RECONCILIANDO HISTÓRICO MT5" in SHELL
    assert 'selectedPanelAsset?.provider_asset_id !== asset.provider_asset_id' in SHELL
    assert 'selectedTimeframe !== timeframe' in SHELL
    assert 'activeRoute !== "painel" || document.hidden' in SHELL
    assert 'addEventListener("visibilitychange", syncMarketPolling)' in SHELL
    assert 'addEventListener("pagehide", stopMarketPolling' in SHELL
    assert 'stopMarketPolling();' in SHELL
    assert "TIME STATUS UNKNOWN" in SHELL and '["FRESH", "UNKNOWN"]' in SHELL


def test_candles_are_provider_ohlc_ordered_and_temporal_anomaly_is_not_shifted():
    assert "candle.open, candle.high, candle.low, candle.close" in SHELL
    assert "candle.high >= Math.max(candle.open, candle.close)" in SHELL
    assert "candle.low <= Math.min(candle.open, candle.close)" in SHELL
    assert "Number(candle.time_epoch) > Number(candles[index - 1].time_epoch)" in SHELL
    assert "new Date(Number(candles[index].time_epoch) * 1000)" in SHELL
    assert "getTimezoneOffset" not in SHELL
    assert "setHours(" not in SHELL
    assert "data-market-chart-source" in HTML
