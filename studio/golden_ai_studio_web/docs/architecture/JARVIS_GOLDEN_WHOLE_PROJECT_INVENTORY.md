# JARVIS / GOLDEN — Whole Project Inventory

**Audit mode:** static/read-only, 2026-09-28
**Scope:** `C:\GoldenAI`, excluding generated `build/`, `dist/`, `.venv/`, `node_modules/` from bounded source counts.
**Restrictions:** no server start, MT5, Strategy Tester, order, database write, EA compile, migration, or configuration change.

## Method and baseline

The operational source of truth is the current Git tree (`main`, HEAD `3e28f9a...`). `CHECKPOINT.md` is a partially stale handoff: its recorded HEAD is the ancestor `4362c53...`. Existing user changes and runtime artifacts were preserved. A bounded inventory previously found approximately 2,645 source/document files, including 709 Python, 38 JavaScript, 22 HTML, 33 MQL files, 7 JSONL files and 190 Markdown files; the raw tree also contains backups, generated outputs and test/runtime copies that must not be treated as product authority.

## Repository and application map

| Area | Evidence | Role | Authority classification |
|---|---|---|---|
| Root Git repository | `.git/`, branch `main` | current project history | operational source |
| Jarvis Core | `studio/golden_ai_studio_web/jarvis_core/` | service, registry, security, audit, tasks, memory, models, voice | canonical |
| Golden Studio backend | `studio/golden_ai_studio_web/server_agent.py` | large legacy HTTP/API surface | legacy/frozen until containment |
| Golden Studio UI | `studio_v7.html` | chat, files, PC, AI, voice and builder workflows | legacy UI |
| Golden Dashboard | `dashboard.html` | scanner, MT5, validation, journal, execution controls | legacy UI with broker-side effects |
| Canonical Jarvis Web | `jarvis_ui/` | Jarvis command/control UI | canonical presentation target |
| Jarvis Desktop | `jarvis_desktop/`, launcher scripts | desktop shell and WebView/API client | canonical desktop surface |
| Market/Radar | `market.html`, `market.js`, `ai_radar.js`, `market_data.py` | macro, news, chart and market read views | strong Golden donor |
| Scanner/strategy | `golden_scanner.py`, `strategy_engine.py`, `meta_strategy.py` | opportunities, setups, ranking and regimes | strong Golden donor; no execution authority |
| MT5 legacy path | `mt5_connector.py`, `mt5_trader.py`, `mt5_real_backtest.py` | terminal connection, orders, imports, position control | `LEGACY_FREEZE` |
| Evidence/catalog | `jarvis_core/mql5_evidence.py`, `robot_catalog.py`, `strategy_tester_adapter.py` | source/compile/test provenance and catalog | canonical foundation, not live authority |
| Auxiliary legacy agent | `jarvis/pc_agent/` and older `jarvis/` modules | historical/auxiliary PC and runtime paths | reference/freeze |

## Services and local surfaces

| Surface | Configured location | Static status |
|---|---|---|
| Golden AI Studio/Core HTTP | `https://127.0.0.1:8765` | existing server surface; not started by this audit |
| Gateway/WSS health | `https://127.0.0.1:8766/health` | existing gateway surface |
| Golden Jarvis service | port `8780` in project rules | configured/documented; runtime state not asserted |
| Ollama | `http://127.0.0.1:11434` | local provider endpoint, conditional |
| MT5 | external terminal through `mt5_connector.py` | no runtime connection attempted |

## Capability inventory

| Capability family | Golden evidence | Jarvis evidence | Static conclusion |
|---|---|---|---|
| Chat and model providers | `studio_v7.html`, `/api/chat`, provider modules | `ModelRouter`, `Brain`, `JarvisService` | one canonical route must be Jarvis |
| Computer Use | legacy HTTP/UI helpers and desktop utilities | `ComputerMission*`, UIA, browser, security/audit | Jarvis canonical |
| Tasks/scheduling | legacy task/runtime copies | `TaskManager`, scheduler, canonical task DB | Jarvis canonical |
| Memory | Golden memory routes/stores | memory boundary and v2/ECC stores | Jarvis canonical boundary |
| Voice | browser recognition/TTS and legacy voice routes | `VoiceService`, realtime voice, VAD/STT/TTS | Jarvis canonical |
| Macro/radar | `market.html` and market modules | no equivalent complete read surface | Golden donor to adapt |
| Scanner/opportunities | `GoldenScanner`, dashboard radar | no equivalent complete engine | Golden donor behind read model |
| Risk/validation | `risk_engine`, validation and journal | governance/security only | Golden calculation donor, Jarvis policy boundary |
| Robots/MQL5 | `projetos/`, catalog/evidence | catalog and adapter contracts | Jarvis owns provenance, not strategy logic |
| MT5 read access | legacy connector and canonical read-only tools | `market_readonly.py` | Jarvis read-only authority |
| MT5 order execution | dashboard/server/trader/connector | intentionally absent from canonical ToolRegistry | legacy frozen; future explicit gate |
| Audit/provenance | JSONL/journal and legacy logs | `AuditLog`, evidence contracts | Jarvis canonical receipt model |

## Existing Golden Scanner trade path

The dashboard renders a multi-asset radar from `POST /api/scanner/radar`. `GoldenScanner.scan_all()` iterates `RADAR_SYMBOLS`, each `scan_symbol()` reads MT5 market data, computes regime, multi-timeframe trend, ATR/RSI/ADX/Bollinger/range/session/levels, evaluates setup definitions and ranks the best setup. The backend adds validation status from `StatisticsEngine`, strategy audit status from `audit_all_strategies()`, and an `auto_trade_eligible` flag. The UI then exposes `ENTRAR NO TRADE` and `Análise Profunda (Multi-Layer)`.

`ENTRAR NO TRADE` reads `window._radarData`, calculates an entry from the displayed price and SL/TP from `atr_h1` (`1.5 ATR` stop, `2.5 ATR` target), serializes the analysis and posts `auto_execute:true` to `/api/mt5/auto_trade`. The backend calls `_authorize_api_mutation(..., 'mt5_real_order', permission='EXECUTE')`, then `auto_trade_from_analysis()` and, when enabled, `execute_trade()` -> `mt5.order_send()`. This is a real broker-side path in code, not a simulation claim.

`AUTO-TRADE` is a frontend timer. When toggled on it scans every 30 seconds and requires score/readiness thresholds, opportunity level, non-neutral direction, `VALIDADA` validation and `audit.auto_trade_eligible`; it then posts the same mutation route with `auto_execute:true`. The toggle is not a durable canonical policy or Jarvis approval record.

## Unknowns requiring runtime validation

- The current broker/account, terminal state, actual order result and live/demo mode were not inspected.
- The UI claim of 22 assets/28 setups must be reconciled against current runtime `RADAR_SYMBOLS` and setup definitions.
- Provider health, voice hardware, browser permissions, current route authorization and actual scan metrics remain runtime questions.
- Generated/build/dist copies and historical JSON/backtest files are evidence inputs only, not authorities.

## Inventory verdict

`Jarvis Core` is the architectural owner. Golden contributes valuable domain implementations, especially Radar, Scanner, market calculations, risk, validation and MQL5 evidence inputs. Direct Golden chat, voice, task, security, audit and broker mutation routes must remain frozen until a canonical read/write model is proven. No feature-loss claim is permitted until parity and provenance gates pass.
