# Jarvis Market Functional Audit

Audit date: 2026-09-29
Scope: static/read-only audit of `market.html` and its reachable scripts. The backend was not started for this audit; no MT5, voice, broker, Strategy Tester or trading action was executed.

## Surface

The approved Market Window loads the existing Golden surface at `/market.html`. The document composes `market.js`, `chart_terminal.js`, `operational_center.js`, `ai_radar.js` and `desktop_center.js`. The route is a donor consumer; it does not create a second Jarvis UI authority.

## Feature inventory

| Feature | UI/handler | Endpoint/source | Class | Status | Main limitation |
|---|---|---|---|---|---|
| Market map and ticker | `marketMapTabs`, `renderTicker` | `/api/market/overview`, MT5/CoinGecko | READ_ONLY | FUNCTIONAL by code | Mixed broker/public sources |
| Asset rows and related markets | `renderMarkets` | Overview assets | READ_ONLY | FUNCTIONAL by code | No common snapshot id |
| XAUUSD chart | `GoldenChart`, timeframe buttons | `/api/market/chart` | READ_ONLY | FUNCTIONAL by code | MT5 dependency; no provenance id |
| Live tick refresh | `loadTick` | `/api/market/tick` | READ_ONLY | FUNCTIONAL by code | 500 ms polling; no cancellation token |
| Technical overlays | canvas draw | server ATR/RSI/pivots/BOS/CHoCH plus client SMA/EMA/Bollinger/volume | ALGORITHM | FUNCTIONAL by code | Formulas and source timestamp are not shown together |
| Gold levels | `renderLevels` | `/api/market/overview`, prior D1 candle | ALGORITHM | FUNCTIONAL by code | Static display of reference candle age |
| News | `renderNews`, filter tabs | Google News RSS, 60 s cache | READ_ONLY | PARTIAL | RSS relevance/deduplication is basic |
| Macro/fundamentals | `renderMacro` | FRED, BCB, MT5 asset changes | ALGORITHM | PARTIAL | Failure details remain aggregate |
| Economic calendar | `renderCalendar` | Trading Economics when configured | READ_ONLY | PARTIAL | Hidden when key is absent; timezone is delegated to browser display |
| Forex explorer | `openPair`, `renderPair` | `/api/market/forex`, MT5, macro/news/calendar | HYBRID | FUNCTIONAL by code | Fixed M15/H1/H4/D1 trend windows |
| Currency strength | `_currency_strength` | MT5 D1 pair changes, 900 s cache | ALGORITHM | FUNCTIONAL by code | Normalized relative score, not probability |
| Scanner/radar | `operational_center.js` and `ai_radar.js` | `/api/scanner/radar`, `/api/scanner/scan` | HEURISTIC | FUNCTIONAL by code | Score/readiness are not probabilities |
| Opportunity ranking | `renderPerformance` | `/api/market/opportunity-ranking` | HEURISTIC | FUNCTIONAL by code | 65% readiness + alignment - spread penalty |
| Deep analysis | `deepAnalysis`, `followAnalysis` | `/api/market/ai-context`, history, `/api/market/analyze` | ACTUAL_LLM + ALGORITHM | PARTIAL | Direct fixed Ollama path; not canonical ModelRouter |
| Analysis replay/performance | `renderHistory`, `renderPerformance` | `/api/market/analysis-history`, JSONL | HYBRID | PARTIAL | History endpoint can rewrite pending records |
| Market voice/PC drawer | `desktop_center.js` | `/api/jarvis/chat`, desktop and voice endpoints | JARVIS_VOICE_CLIENT + LOCAL_SAFE | PARTIAL | Browser SpeechRecognition and direct REST path |
| Return to Chat/Robots | anchors in `market.html` | `studio_v7.html`, `dashboard.html` | NAVIGATION | FUNCTIONAL by code | Dashboard remains a separate legacy trading surface |

No market.html control or dependent Market script was found to call `order_send`, a broker order API, `auto_trade`, or an explicit “entrar no trade” action. The `dashboard.html` route does contain dangerous MT5 controls and must remain outside the Market Window.

## Functional boundaries

The chart algorithms are deterministic: ATR from true ranges, pivot clustering, RSI, moving averages, and swing-break events. Scanner fields expose `score_total`, `readiness`, confluence, R:R and validation fields from `golden_scanner`; the UI does not label them as profit probabilities. Macro scoring is a signed count of observed drivers. Opportunity ranking is a bounded heuristic.

The Market surface is therefore a useful read/analysis workstation, not a canonical trading authority. The current Market Chat is a client of Jarvis, but deep analysis is still a legacy Golden analysis endpoint.

## Gaps

1. The direct Market Chat request contains only text and does not carry selected symbol, timeframe, chart state, macro state, news or freshness/provenance.
2. `/api/market/analyze` calls `ollama_chat(model="qwen2.5-coder:14b")` directly and writes `data/market_ai_audit.jsonl`; it bypasses the canonical ModelRouter and canonical audit boundary.
3. `/api/market/analysis-history` may evaluate pending entries, read MT5 and replace the JSONL file. It is not semantically read-only despite being exposed as a history read.
4. Overview source rows expose coarse online/configure/offline states, but individual fields do not carry a source timestamp, snapshot id, transformation and freshness state.
5. Market polling has local guards (`loading`, `tickLoading`, hidden-tab checks) but no request abort or stale-response sequence number.

## Safety conclusion

No implementation change was made. `SECURITY_BLOCKERS=NONE_FOUND_ON_MARKET_SURFACE`, with a P1 authority gap in deep analysis and a P2 direct-chat authorization/session gap documented in the companion reports.
