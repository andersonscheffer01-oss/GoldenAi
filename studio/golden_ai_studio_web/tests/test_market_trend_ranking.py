from types import SimpleNamespace

from jarvis_core.golden_bridge import GoldenReadBridge
from jarvis_core.tools.market_readonly import (
    _TREND_TIMEFRAMES,
    _TREND_COMPONENT_WEIGHTS,
    _trend_classification,
    _classify_mt5_instrument,
    mt5_search_symbols,
    _technical_context,
    rank_market_trend_frames,
)


def _candles(kind="up", count=100, volume=True):
    rows = []
    for index in range(count):
        if kind == "up":
            close = 100 + index * 0.8
        elif kind == "down":
            close = 180 - index * 0.8
        elif kind == "weak":
            close = 100 + index * 0.001
        elif kind == "alternating":
            close = 120 + (0.15 if index % 2 else -0.15)
        else:
            close = 120
        rows.append({"time_epoch": 1_700_000_000 + index * 60,
                     "open": close - 0.02, "high": close + 0.2,
                     "low": close - 0.2, "close": close,
                     "tick_volume": 12 + index if volume else None})
    return rows


def _snapshot(tf, kind="up", volume=True):
    candles = _candles(kind, volume=volume)
    return {
        "ok": True, "status": "AVAILABLE", "timeframe": tf,
        "snapshot_id": f"snap-{tf}", "freshness": "UNKNOWN",
        "asset": {"provider": "MT5", "asset_id": "mt5:EURUSD",
                  "provider_symbol": "EURUSD", "asset_class": "FOREX"},
        "state": {"freshness": "UNKNOWN", "temporal_authority": "UNKNOWN"},
        "candles": candles,
        "technical_context": _technical_context(candles),
    }


def _frames(kind="up", volume=True, only=None):
    selected = only or _TREND_TIMEFRAMES
    return {tf: _snapshot(tf, kind, volume) for tf in selected}


def test_multitimeframe_classification_has_explicit_score_semantics():
    asset = {"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
             "provider_symbol": "EURUSD", "asset_class": "FOREX"}
    up = rank_market_trend_frames(asset, _frames("up"))
    down = rank_market_trend_frames(asset, _frames("down"))
    flat = rank_market_trend_frames(asset, _frames("flat"))

    assert up["trend"] == "ALTA FORTE"
    assert down["trend"] == "BAIXA FORTE"
    assert flat["trend"] == "LATERAL"
    assert up["directional_score"] > 0 > down["directional_score"]
    assert up["score_semantics"] == "DIRECTIONAL_INTENSITY_NOT_PROBABILITY"
    assert sum(_TREND_COMPONENT_WEIGHTS.values()) == 1.0
    assert {item["trend_classification"] for item in up["evaluated_timeframes"]} == {"ALTA FORTE"}
    assert {item["trend_classification"] for item in down["evaluated_timeframes"]} == {"BAIXA FORTE"}
    assert {item["trend_classification"] for item in flat["evaluated_timeframes"]} == {"LATERAL"}
    assert set(up["evaluated_timeframes"][0]["components"]) == {
        "ma_spread_atr", "price_location_atr", "momentum_10_candles",
        "directional_persistence_20", "observed_breakout_20_candles"}
    assert up["execution_authority"] == "NONE"
    assert up["absolute_utc_verified"] == "UNKNOWN"
    assert up["freshness"] == "UNKNOWN"
    assert up["data_state"] == "AVAILABLE_FRESHNESS_UNKNOWN"
    assert round(sum(up["applied_timeframe_weights"].values()), 6) == 1.0


def test_timeframe_score_uses_existing_inclusive_classification_boundaries():
    assert {_score: _trend_classification(_score) for _score in
            (60, 25, 24, -24, -25, -60)} == {
        60: "ALTA FORTE", 25: "ALTA", 24: "LATERAL",
        -24: "LATERAL", -25: "BAIXA", -60: "BAIXA FORTE",
    }
    asset = {"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
             "provider_symbol": "EURUSD", "asset_class": "FOREX"}
    result = rank_market_trend_frames(asset, _frames("up"))
    assert all(frame["trend_classification"] == _trend_classification(frame["directional_score"])
               for frame in result["evaluated_timeframes"] if frame["status"] == "AVAILABLE")


def test_weak_and_divergent_timeframes_are_reported_without_strategy_inputs():
    asset = {"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
             "provider_symbol": "EURUSD", "asset_class": "FOREX"}
    weak = rank_market_trend_frames(asset, _frames("weak"))
    frames = _frames("up")
    frames["H4"] = _snapshot("H4", "down")
    frames["D1"] = _snapshot("D1", "down")
    divergent = rank_market_trend_frames(asset, frames)

    assert weak["trend"] == "LATERAL"
    assert divergent["timeframe_divergence"] is True
    assert divergent["macro_news_inputs"] == "NOT_USED_UNVERIFIED_TEMPORAL_SOURCES"
    assert all("strategy" not in key.lower() for key in divergent)


def test_insufficient_stale_and_missing_tick_volume_are_conservative():
    asset = {"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
             "provider_symbol": "EURUSD", "asset_class": "FOREX"}
    insufficient = rank_market_trend_frames(asset, _frames(only=("M1", "M5")))
    stale_frames = _frames()
    stale_frames["M1"]["state"]["freshness"] = "STALE"
    stale = rank_market_trend_frames(asset, stale_frames)
    no_volume = rank_market_trend_frames(asset, _frames(volume=False))

    assert insufficient["trend"] == "DADOS INSUFICIENTES"
    assert insufficient["directional_score"] is None
    assert stale["stale_timeframes"] == 1
    assert stale["freshness"] == "UNKNOWN"
    assert no_volume["tick_volume_state"] == "PARTIAL"
    assert no_volume["directional_score"] is not None
    assert no_volume["directional_score"] == rank_market_trend_frames(asset, _frames())["directional_score"]


def test_explicit_batch_is_bounded_uses_existing_snapshots_and_caches(monkeypatch):
    profile = SimpleNamespace(market_data_read_enabled=True,
                              mt5_market_data_read_enabled=True)
    bridge = GoldenReadBridge(runtime_profile=profile)
    calls = []

    def snapshot(provider, asset_id, symbol, asset_class, timeframe, count, correlation_id=""):
        calls.append((symbol, timeframe, count))
        data = _snapshot(timeframe)
        data["asset"].update({"provider_asset_id": asset_id})
        return {"ok": True, "data": data}

    monkeypatch.setattr(bridge, "panel_market_snapshot", snapshot)
    assets = [{"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
               "provider_symbol": "EURUSD", "asset_class": "FOREX"}]
    first_meta = {"scan_id": "scan-first", "universe_hash": "a" * 64,
                  "universe_total": 1, "batch_index": 0, "batch_total": 1,
                  "batch_asset_ids": ["mt5:EURUSD"]}
    first = bridge.panel_trend_ranking(assets, "test-correlation", first_meta)
    assert first["data"]["maximum_market_snapshot_reads"] == 7
    assert first["data"]["maximum_ohlc_bars"] == 700
    assert len(calls) == 7
    assert {item[2] for item in calls} == {100}
    assert first["data"]["audit_summary"]["read_counts"]["snapshot_requests"] == 7

    second_meta = {**first_meta, "scan_id": "scan-second", "universe_hash": "b" * 64}
    second = bridge.panel_trend_ranking(assets, "test-correlation-2", second_meta)
    assert second["data"]["cache"] == "HIT"
    assert len(calls) == 7
    assert second["data"]["audit_summary"]["scan_id"] == "scan-second"
    assert second["data"]["audit_summary"]["correlation_id"] == "test-correlation-2"
    assert second["data"]["audit_summary"]["read_counts"]["snapshot_requests"] == 0


def test_batch_rejects_oversize_and_noncanonical_identity_before_reads():
    profile = SimpleNamespace(market_data_read_enabled=True,
                              mt5_market_data_read_enabled=True)
    bridge = GoldenReadBridge(runtime_profile=profile)
    too_many = [{"provider": "MT5", "provider_asset_id": f"mt5:A{i}",
                 "provider_symbol": f"A{i}", "asset_class": "FOREX"} for i in range(5)]
    invalid = [{"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
                "provider_symbol": "XAUUSD", "asset_class": "FOREX"}]

    assert bridge.panel_trend_ranking(too_many)["data"]["status"] == "INVALID_BATCH_SIZE"
    result = bridge.panel_trend_ranking(invalid)
    assert result["data"]["status"] == "INVALID_ASSET_IDENTITIES"


def test_panel_exposes_manual_rank_table_and_no_automatic_provider_request():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    shell = (root / "jarvis_ui" / "src" / "desktop-shell.js").read_text(encoding="utf-8")
    service = (root / "jarvis_core" / "service.py").read_text(encoding="utf-8")
    server = (root / "server_agent.py").read_text(encoding="utf-8")
    panel = shell[shell.index("panel.innerHTML = `"):shell.index("analysis.innerHTML = `")]
    html = (root / "jarvis_ui" / "jarvis.html").read_text(encoding="utf-8")
    assert "data-trend-ranking" not in panel
    assert "data-panel-trend-up" in panel and "data-panel-trend-down" in panel
    assert "data-panel-trend-progress" in panel
    assert 'data-d2-route="inteligencia-mercado"' in html
    assert html.index('data-d2-route="historico"') < html.index('data-d2-route="inteligencia-mercado"') < html.index("d2NavSecondary")
    assert html.count('data-d2-route="inteligencia-mercado"') == 1
    market_page = html[html.index('data-view="d2-market-intelligence"'):]
    assert all(f">{tf}<" in market_page for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    assert "data-trend-ranking-run" in market_page
    assert "data-market-filter-class" in market_page and "data-market-filter-trend" in market_page
    assert "data-market-filter-state" in market_page
    assert "Nenhuma varredura de mercado consultada." in market_page
    assert '"/api/jarvis/golden/trend-ranking"' in shell
    assert 'trendRanking?.querySelector("[data-trend-ranking-run]")?.addEventListener("click"' in shell
    assert "filterTrendCatalogByClass(discoveredAssets, selectedClass)" in shell
    assert "createTrendScan(selectedUniverse, scanId)" in shell
    assert 'data-trend-class-select' in market_page
    assert 'asset_class_filter: trendScan.asset_class_filter || "ALL"' in shell
    assert "const pageSize = 40" in shell and "filteredRows.slice(" in shell
    scan_start = shell.index("async function startTrendScan")
    scan_end = shell.index('trendRanking?.querySelector("[data-trend-ranking-run]")', scan_start)
    scan_source = shell[scan_start:scan_end]
    assert scan_source.index("window.confirm(") < scan_source.index("trendScan = nextScan")
    class_change = shell.index('trendRankingClassSelect?.addEventListener("change"')
    class_change_end = shell.index("trendRankingPrevious?.addEventListener", class_change)
    assert "httpPost" not in shell[class_change:class_change_end]
    assert "searchPanelAssets" not in shell[class_change:class_change_end]
    assert "executeTrendRankingBatch" not in shell[class_change:class_change_end]
    assert "applyTrendBatch(trendScan, batch, result.ranked_assets, batchIndex)" in shell
    assert "response?.data?.status" in shell and "failure.code" in shell
    assert "nextTrendBatch(trendScan)" in shell
    assert "trendRankingRows" not in shell
    assert "trendRankingOffset" not in shell
    assert "data-trend-ranking-retry" in market_page and "retryFailedTrendBatch" in shell
    assert "window.confirm(" in shell
    assert "createTrendRequestGate" in shell
    batch_function = shell[shell.index("async function executeTrendRankingBatch"):
                           shell.index("async function startTrendScan")]
    batch_body = batch_function[batch_function.index(") {") + 3:]
    assert "executeTrendRankingBatch(" not in batch_body
    assert 'trendRankingNext?.addEventListener("click"' in shell
    assert 'trendRanking?.querySelector("[data-trend-ranking-run]")?.addEventListener("click"' in shell
    assert "assets: batch.map" in batch_function and "MAX_TREND_BATCH_SIZE" not in batch_function
    state_module = (root / "jarvis_ui" / "src" / "trend-ranking-state.js").read_text(encoding="utf-8")
    assert "const MAX_BATCH_SIZE = 4" in state_module
    assert 'const TREND_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]' in state_module
    assert "fetch(" not in state_module and "WebSocket" not in state_module
    nav = shell[shell.index("function selectRoute(route)"):shell.index('root.addEventListener("click"', shell.index("function selectRoute(route)"))]
    assert 'if (route === "inteligencia-mercado")' not in nav
    assert 'if (activeRoute === "painel") ensurePanelCatalog();' in nav
    assert shell.count("let trendScan = null") == 1
    assert "renderTrendPanelSummary" in shell and "renderTrendRanking" in shell
    assert 'data-trend-asset-id' in shell and 'selectPanelAsset(match)' not in shell
    assert '"/api/jarvis/golden/trend-ranking"' in server
    assert 'self._execute_jarvis_read("golden_panel_trend_ranking"' in server
    assert "scan_metadata" in server
    tool = service[service.index('Tool("golden_panel_trend_ranking"'):]
    tool = tool[:tool.index('Tool("golden_panel_market_update"')]
    assert "llm_enabled=False" in tool
    assert "SideEffectClass.READ_ONLY" in tool and "NO_TRADING" in tool


def test_mt5_asset_class_uses_explicit_metadata_and_keeps_unknown_symbols(monkeypatch):
    import jarvis_core.tools.market_readonly as market_readonly

    class FakeMT5:
        SYMBOL_CALC_MODE_FOREX = 0
        SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE = 1
        SYMBOL_CALC_MODE_EXCH_STOCKS = 32
        SYMBOL_CALC_MODE_CFDINDEX = 4

        def __init__(self):
            self.rows = [
                SimpleNamespace(name="AAPL", description="Apple shares USD/USD",
                                path="Stocks\\US", currency_base="USD",
                                currency_profit="USD", trade_calc_mode=7),
                SimpleNamespace(name="SPY", description="S&P tracker",
                                path="ETF\\US", currency_base="USD",
                                currency_profit="USD", trade_calc_mode=7),
                SimpleNamespace(name="EURUSD", description="Euro vs Dollar",
                                path="Symbols\\Majors", currency_base="EUR",
                                currency_profit="USD", trade_calc_mode=0),
                SimpleNamespace(name="MYSTERY", description="Forex mystery USD/USD",
                                path="Symbols\\Unclassified", currency_base="USD",
                                currency_profit="USD", trade_calc_mode=7),
                SimpleNamespace(name="XAUUSD", description="Metal spot",
                                path="Symbols\\Other", currency_base="XAU",
                                currency_profit="USD", trade_calc_mode=7),
                SimpleNamespace(name="BTCUSD", description="Bitcoin",
                                path="Symbols\\Other", currency_base="BTC",
                                currency_profit="USD", trade_calc_mode=7),
                SimpleNamespace(name="OTHER1", description="Unclassified display name",
                                path="Broker\\Other", currency_base="",
                                currency_profit="", trade_calc_mode=7),
            ]

        def symbols_get(self):
            return self.rows

        def symbol_info(self, symbol):
            return next((item for item in self.rows if item.name == symbol), None)

        def symbol_info_tick(self, _symbol):
            return None

    fake = FakeMT5()
    monkeypatch.setattr(market_readonly, "_market_data_connection",
                        lambda: (fake, None, ""))
    result = mt5_search_symbols("", "ALL")
    classes = {item["provider_symbol"]: (item["asset_class"], item["asset_class_source"])
               for item in result["assets"]}
    assert classes == {
        "AAPL": ("STOCKS", "MT5_SYMBOL_PATH_GROUP"),
        "SPY": ("ETF", "MT5_SYMBOL_PATH_GROUP"),
        "EURUSD": ("FOREX", "MT5_TRADE_CALC_MODE"),
        "MYSTERY": ("OTHER_UNKNOWN", "INSUFFICIENT_CANONICAL_METADATA"),
        "XAUUSD": ("METALS", "MT5_CURRENCY_BASE"),
        "BTCUSD": ("CRYPTO", "MT5_CURRENCY_BASE"),
        "OTHER1": ("OTHER", "MT5_SYMBOL_PATH_GROUP"),
    }
    assert result["classification_counts"]["OTHER_UNKNOWN"] == 1
    assert len(result["assets"]) == len(fake.rows)
    stocks = mt5_search_symbols("", "STOCKS")
    assert [item["provider_symbol"] for item in stocks["assets"]] == ["AAPL"]


def test_forex_classification_requires_distinct_canonical_currency_metadata():
    class FakeMT5:
        SYMBOL_CALC_MODE_FOREX = 0
        SYMBOL_CALC_MODE_EXCH_STOCKS = 32
        SYMBOL_CALC_MODE_CFDINDEX = 4

    same_currency = SimpleNamespace(path="Symbols\\Unclassified",
                                    currency_base="USD", currency_profit="USD",
                                    trade_calc_mode=0)
    missing_currency = SimpleNamespace(path="Symbols\\Unclassified",
                                       currency_base="", currency_profit="USD",
                                       trade_calc_mode=0)
    forex_pair = SimpleNamespace(path="Symbols\\Unclassified",
                                 currency_base="EUR", currency_profit="USD",
                                 trade_calc_mode=0)
    explicit_stocks = SimpleNamespace(path="Stocks\\US",
                                      currency_base="USD", currency_profit="USD",
                                      trade_calc_mode=0)
    explicit_metals = SimpleNamespace(path="Metals\\Spot",
                                      currency_base="XAU", currency_profit="USD",
                                      trade_calc_mode=0)
    conflicting = SimpleNamespace(path="Forex\\Retail",
                                  currency_base="EUR", currency_profit="USD",
                                  trade_calc_mode=32)

    assert _classify_mt5_instrument(same_currency, FakeMT5()) == (
        "OTHER_UNKNOWN", "INSUFFICIENT_CANONICAL_METADATA")
    assert _classify_mt5_instrument(missing_currency, FakeMT5()) == (
        "OTHER_UNKNOWN", "INSUFFICIENT_CANONICAL_METADATA")
    assert _classify_mt5_instrument(forex_pair, FakeMT5()) == (
        "FOREX", "MT5_TRADE_CALC_MODE")
    assert _classify_mt5_instrument(explicit_stocks, FakeMT5()) == (
        "STOCKS", "MT5_SYMBOL_PATH_GROUP")
    assert _classify_mt5_instrument(explicit_metals, FakeMT5()) == (
        "METALS", "MT5_SYMBOL_PATH_GROUP")
    assert _classify_mt5_instrument(conflicting, FakeMT5()) == (
        "OTHER_UNKNOWN", "CONFLICTING_MT5_CLASS_METADATA")


def test_ranking_service_audits_compact_per_asset_summary_in_canonical_log():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "jarvis_core" / "service.py").read_text(encoding="utf-8")
    assert 'if name == "golden_panel_trend_ranking":' in source
    assert '"ranking_audit_summary": summary' in source
    assert '"universe_hash_verification": "CLIENT_PROVIDED_NOT_RECOMPUTED_BY_CORE"' in (
        Path(__file__).resolve().parents[1] / "jarvis_core" / "golden_bridge.py"
    ).read_text(encoding="utf-8")


def test_ranking_audit_summary_keeps_per_asset_evidence_without_candle_payloads():
    from jarvis_core.golden_bridge import GoldenReadBridge

    row_data = []
    for symbol in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD"):
        ranked = rank_market_trend_frames(
            {"provider": "MT5", "provider_asset_id": f"mt5:{symbol}",
             "provider_symbol": symbol, "asset_class": "FOREX"}, _frames("up"))
        ranked["terminal_data_root_fingerprints"] = ["a" * 64]
        row_data.append(ranked)
    summary = GoldenReadBridge._trend_ranking_audit_summary(
        row_data, {"scan_id": "scan-test", "universe_hash": "b" * 64,
                   "universe_total": 4, "batch_index": 0, "batch_total": 1,
                   "batch_asset_ids": [f"mt5:{symbol}" for symbol in
                                        ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD")]}, "corr-test",
        snapshot_requests=28, available_snapshots=28, candles_returned=2800, cache="MISS")

    traced = summary["assets"][0]
    assert {item["provider_asset_id"] for item in summary["assets"]} == {
        "mt5:EURUSD", "mt5:GBPUSD", "mt5:USDJPY", "mt5:AUDUSD"}
    assert summary["universe_hash_verification"] == "CLIENT_PROVIDED_NOT_RECOMPUTED_BY_CORE"
    assert summary["correlation_id"] == "corr-test"
    assert traced["state"] == "AVALIADO"
    row_data[0]["asset_class_source"] = "MT5_TRADE_CALC_MODE"
    summary_with_class = GoldenReadBridge._trend_ranking_audit_summary(
        row_data, {"asset_class_filter": "FOREX"}, "corr-class", 0, 0, 0, "HIT")
    assert summary_with_class["assets"][0]["asset_class_source"] == "MT5_TRADE_CALC_MODE"
    assert traced["directional_score"] == row_data[0]["directional_score"]
    assert len(traced["available_timeframes"]) == 7
    assert len(traced["snapshot_ids"]) == 7
    assert traced["freshness"] == "UNKNOWN"
    assert traced["temporal_authority"] == "UNKNOWN"
    assert traced["terminal_identity_state"] == "ROOT_FINGERPRINT_OBSERVED_NOT_RECONCILED"
    assert summary["read_counts"]["snapshot_requests"] == 28
    assert '"open"' not in str(summary).lower()
    assert '"close"' not in str(summary).lower()
    assert "api_key" not in str(summary).lower()


def test_snapshot_exception_is_sanitized_and_remains_a_failed_asset(monkeypatch):
    profile = SimpleNamespace(market_data_read_enabled=True,
                              mt5_market_data_read_enabled=True)
    bridge = GoldenReadBridge(runtime_profile=profile)

    def snapshot(provider, asset_id, symbol, asset_class, timeframe, count, correlation_id=""):
        if timeframe == "H1":
            raise RuntimeError("sensitive details must not be logged")
        data = _snapshot(timeframe)
        data["asset"].update({"provider_asset_id": asset_id})
        return {"ok": True, "data": data}

    monkeypatch.setattr(bridge, "panel_market_snapshot", snapshot)
    assets = [{"provider": "MT5", "provider_asset_id": "mt5:EURUSD",
               "provider_symbol": "EURUSD", "asset_class": "FOREX"}]
    result = bridge.panel_trend_ranking(assets, "corr-failed", {
        "scan_id": "scan-failed", "universe_hash": "c" * 64,
        "universe_total": 1, "batch_index": 0, "batch_total": 1,
        "batch_asset_ids": ["mt5:EURUSD"],
    })
    audit_asset = result["data"]["audit_summary"]["assets"][0]
    assert audit_asset["state"] == "FALHO"
    assert audit_asset["sanitized_errors"] == [{"timeframe": "H1", "error_code": "RuntimeError"}]
    assert "sensitive details" not in str(result)
    assert result["data"]["snapshot_requests"] == 7


def test_trend_ranking_http_contract_validates_identity_batch_and_audit_context():
    from server_agent import GoldenAIHandler

    handler = object.__new__(GoldenAIHandler)
    captured = {}
    handler._execute_jarvis_read = lambda name, args, audit_context=None: captured.update(
        {"name": name, "args": args, "audit_context": audit_context}) or {"ok": True}
    assets = [{"provider": "MT5", "provider_asset_id": f"mt5:FX{i}",
               "provider_symbol": f"FX{i}", "display_symbol": f"FX{i}",
               "display_name": f"FX {i}", "asset_class": "FOREX"} for i in range(4)]
    payload = {"assets": assets, "scan_id": "12345678-1234-1234-1234-123456789abc",
               "universe_hash": "a" * 64, "universe_total": 5, "batch_index": 0,
               "asset_class_filter": "ETF",
               "batch_total": 2, "batch_asset_ids": [row["provider_asset_id"] for row in assets],
               "excluded_count": 1, "excluded_reason_counts": {"DUPLICATE_PROVIDER_ASSET_ID": 1},
               "catalog_source": "AUTHENTICATED_MT5_SYMBOL_DISCOVERY",
               "catalog_observation": {"status": "AVAILABLE", "observed_at": "2026-10-06T00:00:00Z",
                   "enumerated_count": 8, "classification_counts": {
                       "FOREX": 3, "ETF": 2, "STOCKS": 1, "CRYPTO": 2}},
               "correlation_id": "corr-trend-1"}
    response = handler._api_jarvis_golden_trend_ranking(payload)
    assert response["ok"] is True
    assert captured["name"] == "golden_panel_trend_ranking"
    assert captured["args"]["scan_metadata"]["scan_id"] == payload["scan_id"]
    assert captured["args"]["scan_metadata"]["asset_class_filter"] == "ETF"
    assert captured["args"]["scan_metadata"]["batch_asset_ids"] == payload["batch_asset_ids"]
    assert captured["audit_context"]["correlation_id"] == "corr-trend-1"
    assert captured["audit_context"]["metadata"]["universe_hash"] == "a" * 64
    assert captured["args"]["scan_metadata"]["catalog_observation"]["enumerated_count"] == 8

    mismatch = {**payload, "batch_asset_ids": ["mt5:OTHER"]}
    assert handler._api_jarvis_golden_trend_ranking(mismatch)["status"] == "INVALID_SCAN_METADATA"
    invalid_class = {**payload, "asset_class_filter": "SYMBOL_NAME_GUESS"}
    assert handler._api_jarvis_golden_trend_ranking(invalid_class)["status"] == "INVALID_SCAN_METADATA"
    assert len(assets) == 4
