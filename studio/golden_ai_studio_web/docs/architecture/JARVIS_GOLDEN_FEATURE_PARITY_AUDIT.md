# Jarvis / Golden Feature Parity Audit

**Date:** 2026-09-28
**Scope:** read-only inventory of `studio_v7.html`, `dashboard.html`, `market.html` (Radar Macro), canonical `jarvis_ui/jarvis.html`, Jarvis Core and Desktop.
**Decision:** `PASS_WITH_RESTRICTIONS` for the audit only. No feature retirement or migration is authorized by this document.

## Baseline and guardrails

| Field | Observed |
|---|---|
| START_BASELINE | branch `main`, HEAD `3e28f9ab4e2eb232b84d9357b11b30eeaa722bee`, ahead of `origin/main` by 142 |
| CHECKPOINT_REFERENCE | `CHECKPOINT.md` records ancestor `4362c5398d3ef8c2f6585bad8b1d90c0609ff175`; handoff is stale on exact HEAD only |
| PRE_EXISTING_WORKTREE_PRESERVED | YES; tracked changes, runtime DBs, build/dist, backtests and untracked audit files were not reverted |
| STRATEGY_TESTER_EXECUTED | NO |
| PRODUCTION_ROBOT_USED | NO |
| LIVE_TRADING | NO |
| HISTORICAL_BACKTESTS_MODIFIED | NO |
| DEVICE_REGISTRY_MODIFIED | NO |
| PUSH | NO |

`market.html` was audited as a first-class donor and was not modified. This gate performs no provider configuration, compile, tester launch, order, database migration or UI implementation.

## Factual surface scoreboard

These are static surface counts, not quality scores.

| Surface | Static evidence | Major capability families |
|---|---|---|
| `studio_v7.html` | 40 fetch call sites, 6 intervals, 120 buttons, 143 inline handlers | chat/models/modes, market/radar, charts, MQL5/EA builder, files, multimodal, PC/system, security, analytics/backtests/validation |
| `dashboard.html` | 48 fetch call sites, 2 intervals, 83 buttons, 85 inline handlers | robots, backtest/simulation, scanner/radar/risk, strategies, validation, security/status, chat, compare/statistics |
| `market.html` + scripts | 5 first-party scripts; overview/forex/chart/tick/AI/history/ranking routes; chart tick every 0.5s and candle reload every 15s; operational refresh 60s | multi-asset map, gold, news, technical chart, macro, sessions, pipeline, ranking, calendar, performance, AI analysis, replay |
| `jarvis_ui/jarvis.html` | 498 lines, 0 direct fetch calls; behavior in `jarvis_ui/src` | canonical chat, Gateway, voice, command routing, trading read panels, search, telemetry |
| Jarvis Core/Desktop | `JarvisService`, `ToolRegistry`, `SecurityManager`, `AuditLog`, `ModelRouter`; Desktop reuses canonical WebView | canonical execution boundary, approvals, tasks, memory, Computer Use, providers, read-only MT5 |

## Feature trace and parity

Status vocabulary: `REAL`, `WORKING_PARTIAL`, `MOCK_OR_SYNTHETIC`, `UNKNOWN`, `MISSING_PARITY`, `LEGACY_DONOR`.

| Capability | Legacy owner | Jarvis equivalent | Status and finding |
|---|---|---|---|
| Chat and sessions | Studio / server agent | Gateway -> JarvisService / ModelRouter | `WORKING_PARTIAL`; legacy in-memory conversation/provider authority is duplicated |
| Models and providers | Studio selector and server agent | canonical `ModelRouter` and provider adapters | `WORKING_PARTIAL`; direct legacy routing remains |
| User modes | Studio Developer/Trader/Assistant | interaction/profile policy not yet a separate brain | `WORKING_PARTIAL`; mode is mostly UI prompt selection |
| Voice chat | Studio browser SpeechRecognition/SpeechSynthesis; Dashboard status | canonical VoiceService via Gateway/Core | `WORKING_PARTIAL`; legacy browser capture/TTS is frozen, canonical real-speech VAD gate remains open |
| Image/audio/video/document/screen | Studio upload and capture handlers | Core vision, voice and Computer Use | `WORKING_PARTIAL`; legacy temp upload/provenance is weak |
| PC/files | Studio `/api/agent`, `/api/filesystem` | SecurityManager, Computer Use, scoped tools | `LEGACY_FREEZE`; direct legacy mutation is not the canonical authority |
| MT5 read-only | Dashboard, market data, scanner | `market_readonly.py` and registered low-risk tools | `REAL` canonical read path; legacy connector can auto-launch and is unsafe authority |
| MQL5 / EA builder | Studio builder, compile and filesystem endpoints | MQL5 evidence boundary and Core tools | `WORKING_PARTIAL`; rich donor UX lacks full canonical evidence contract |
| Robot inventory | Dashboard top-level external glob | Robot Catalog | `WORKING_PARTIAL`; 9 repo sources vs 29 external MQ5 and 48 EX5 artifacts needs classification |
| Scanner / radar | Dashboard scanner, `golden_scanner.py`, market operational center | canonical command/read tools exist | `WORKING_PARTIAL`; live MT5 reads and hard-coded setup definitions remain legacy-owned |
| Strategy catalog/manager | Dashboard strategy manager and setup definitions | no complete canonical manager UI | `MISSING_PARITY` for rich management UI; active repertoire is not authorization |
| Validation | Dashboard engine and Radar pipeline | command panels and validation tools | `WORKING_PARTIAL`; much of `validation_engine.py` is seeded synthetic simulation |
| Tester evidence | adapter and prior fixture gate | Core StrategyTesterAdapter | `REAL` fail-closed foundation; prior runs remain failed/unverified and no new run was made |
| Security/approvals | Dashboard security panel and legacy gates | SecurityManager + AuditLog | `WORKING_PARTIAL`; canonical authority exists, legacy direct route surface remains broad |
| Radar market map | `market.html`, `market.js`, `market_data.py` | no equivalent full Control Center view | `MISSING_PARITY`; preserve as donor |
| Radar source integrity | Radar source list | no equivalent rich source/integrity view | `MISSING_PARITY` |
| Radar news | Google News RSS query | no equivalent full news panel | `MISSING_PARITY` |
| Radar technical chart | MT5 candles, levels, structure | canonical MT5 candle tools only | `WORKING_PARTIAL`; chart/levels/replay UI absent in Jarvis |
| Radar macro/fundamental | FRED, BCB and computed gold drivers | no equivalent full macro panel | `MISSING_PARITY` |
| Radar sessions/pipeline | `operational_center.js` | no equivalent first-class read model | `MISSING_PARITY`; current sessions are fixed UTC windows |
| Radar AI analysis | `/api/market/ai-context`, `/api/market/analyze` | Jarvis chat/tool flow | `WORKING_PARTIAL`; structured context exists but persistence/provider ownership is legacy |

## Voice parity addition

The Golden legacy voice chat is a browser convenience layer, not a second
voice brain: `studio_v7.html` starts browser-managed `SpeechRecognition` and
sends the final transcript through `/api/chat`; `SpeechSynthesis` reads a
message locally. It has no application VAD, no barge-in, no pinned STT model,
no canonical AuditLog receipt and no Desktop transport. Audio upload through
`/api/audio` is a separate file-analysis path.

The canonical path is `jarvis_ui/src/voice.js` for Web and
`desktop-voice.js -> Gateway -> /api/jarvis/voice-service/*` for Desktop,
owned by `jarvis_core.voice_service.VoiceService`. It keeps one capture owner,
local Silero VAD, local faster-whisper, provider-neutral TTS, session/turn
identity, cancellation and JarvisService/SecurityManager boundaries. The
real microphone/VAD restriction remains open; B0 does not retest or retune it.

`VOICE_REUSE_DECISIONS:` adapt browser permission/error UX and simple level
feedback; keep Core VAD/STT/TTS/session/cancellation; freeze direct legacy
capture/chat; migrate provider routing and audit to the canonical path.

## Radar Macro deep trace

### Market data and source integrity

`market_data.py` defines 15 asset groups with MT5 aliases. MT5 `symbol_info`, `symbol_info_tick` and `copy_rates_from_pos` supply broker prices/candles for the overview, Forex, chart, tick, gold and levels. Symbol normalization is alias-based for the fixed asset list and regex-based for Forex discovery. Missing symbols are skipped; missing history returns an explicit error or an empty panel.

CoinGecko supplies Bitcoin and Ethereum through a public HTTPS market endpoint with a six-second timeout and no durable cache. Radar cache behavior is in-process: news 60 seconds, pair news 120 seconds, macro/strength 900 seconds, economic calendar 60 seconds. MT5 snapshots are refreshed by request and are not durable cached. Stale-data detection is incomplete: timestamps are returned, but no uniform stale policy exists for all providers.

The visible source list reports MT5, CoinGecko, Trading Economics and Twelve Data. Code uses MT5, CoinGecko, Google News RSS, FRED and Banco Central do Brasil; Twelve Data is only checked for configuration and is not used by the overview path. Trading Economics is used only when `TRADING_ECONOMICS_KEY` is configured. This discrepancy is a source-integrity gap, not evidence that Twelve Data is online.

### News, macro and calendar

News is Google News RSS with a fixed Portuguese query and up to 24 items. `topic` is rule-derived from title words (`ouro`, `gold`, `xau`) or defaults to `Macro`; UI impact/positive styling is also title-keyword derived. There is no visible deduplication, durable history or model classification in the ingestion path. Calendar rows use Trading Economics fields `Date`, `Country`, `Event`, `Importance`, `Actual`, `Previous`, `Forecast`, `Currency`, `Source`; absent credentials yield `configure` and no fabricated events.

Macro uses FRED series `DGS10`, `T10YIE`, `DFEDTARU`, `DTWEXBGS`, plus BCB SGS `432` (Selic) and `433` (IPCA). Latest observations and previous values are read, with observation dates. Gold bias is a fixed directional rule; score is the sum of favorable/unfavorable factors, and the reading is `Favoravel ao ouro`, `Contrario ao ouro` or `Misto`. This is contextual interpretation, not validated profit probability.

### Technical, gold and strength engines

The chart accepts `M1`, `M5`, `M15`, `H1`, `H4`, `D1` and loads 260 MT5 bars, displaying the last 100. ATR is a 14-bar true-range mean. Support/resistance candidates are three-bar local pivots clustered within `max(ATR*0.22, 30 points)`, spaced by `max(ATR*0.70, tolerance*2.5)`, scored from touches and recency, then annotated with distance, age, reaction/ATR and false-break counts. BOS/CHoCH uses local swing highs/lows and close breaks; labels are algorithmic, not merely decorative. RSI is a simple 14-period gain/loss calculation.

Gold levels use the previous closed D1 XAUUSD/GOLD candle: `P=(H+L+C)/3`, `R1=2P-L`, `S1=2P-H`, `R2=P+(H-L)`, `S2=P-(H-L)`, `R3=H+2(P-L)`, `S3=L-2(H-P)`, `R4=P+3(H-L)`, `S4=P-3(H-L)`. The gold snapshot uses current MT5 tick, D1 range, prior close, 14-day average range and M15 simple means over 20/50 closes.

Currency strength discovers available broker Forex symbols from a fixed currency universe, averages D1 percentage changes per base/quote occurrence, then normalizes by the largest absolute value to 100. The UI display separately averages pair changes. There is no durable historical strength store, and missing symbols are omitted rather than imputed.

### Sessions, validation and ranking

The operational center uses fixed UTC windows: Tokyo `00-03`, London `07-12`, overlap `12-15`, New York `13-17`. It does not implement local timezone conversion, DST or holidays. The nine-stage pipeline is a UI projection: sources, session, macro, spread, trend, momentum, MTF, risk and validation. Incomplete inputs become `wait`/unknown in some stages, but the macro stage and risk/ranking semantics need a canonical fail-closed read model before reuse.

Ranking delegates to `/api/scanner/radar`, uses `score_total`/`best_readiness`, setup names from scanner definitions, session and validation fields. The score is not a probability. The UI explicitly reports `historico insuficiente` below 30 trades. Radar techniques such as Breakout, FVG, Ichimoku, Fibonacci, Turtle and Darvas are not all proven complete implementations; each requires an implementation-level catalog before adoption.

## Security and authority findings

Critical gaps are duplicated legacy authorities (`server_agent.py`, `mt5_connector.py`, `mt5_trader.py`, direct Studio/Dashboard actions), incomplete canonical UI parity, synthetic validation presented beside real-data labels, weak uniform stale policy, incomplete source truth, and no first-class Jarvis read model for Radar provenance. No unauthenticated bypass was proven by this static audit, but broad direct routes remain an architectural risk. `ACTIVE_IN_REPERTOIRE != AUTHORIZED_TO_TRADE` must remain an explicit invariant.

`ZERO_FEATURE_LOSS_STATUS: GUARANTEED_FOR_AUDIT_ONLY / NOT_YET_FOR_RETIREMENT`. The safe decision is to keep donor surfaces operationally frozen, connect read models behind Jarvis, and retire only after feature-by-feature parity, security, provenance and regression gates pass.

## Next gate

`NEXT_RECOMMENDED_GATE: REVIEW_AND_APPROVE_RECOVERY_B0`. B0 is documentation and read-model contract review only. No Radar UI, robot matching, provider configuration, Strategy Tester run, production compile, live action or batch is authorized by this audit.
