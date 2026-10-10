# JARVIS / GOLDEN — Duplication Matrix

**Mode:** static/read-only. This matrix identifies overlapping capability and authority; it does not authorize migration.

| Capability | Golden surface | Jarvis surface | Overlap | Decision |
|---|---|---|---|---|
| Chat/LLM | `studio_v7.html`, `/api/chat`, legacy provider selection | `Brain`, `ModelRouter`, `JarvisService` | high | `MIGRATE_AUTHORITY` |
| Tool execution | server handlers and direct helpers | `ToolRegistry` -> `JarvisService.execute_tool` | high | `KEEP_OURS` |
| Security/confirmation | legacy route gates and UI confirmations | `SecurityManager`, scoped approvals | high | `MIGRATE_AUTHORITY` |
| Audit/history | analytics, JSONL, journal | `AuditLog`, receipts and telemetry | high | `MERGE` read models; Jarvis receipt authority |
| Tasks/scheduler | older runtime/task copies | `TaskManager`, scheduler, task DB | medium/high | `KEEP_OURS` |
| Memory | Golden stores and HTTP routes | canonical memory boundary/v2 | high | `KEEP_OURS` Jarvis boundary; adapt data |
| Voice capture | browser `SpeechRecognition` | Core `AudioInputProvider`/`VoiceService` | high | `LEGACY_FREEZE` capture; `ADAPT` UX |
| Voice STT/TTS | browser-managed recognition/synthesis and old server routes | local faster-whisper, provider-neutral TTS/SAPI | high | `KEEP_OURS` |
| Voice session/turns | ephemeral browser result and server chat session | `VoiceSession`, turn/epoch/generation | medium/high | `KEEP_OURS` |
| Radar macro | `market.html` and market scripts | no complete equivalent | low | `PORT` |
| Technical analysis | `market_data.py`, scanner indicators | canonical read model not complete | medium | `PORT` |
| Opportunities | `GoldenScanner`, dashboard radar | no complete equivalent | medium | `ADAPT` behind Jarvis read model |
| Setup definitions | `golden_scanner.py`, strategy manager | catalog/evidence contracts | medium | `MERGE` metadata, preserve strategy source |
| Risk engine | `risk_engine.py` | SecurityManager policy, no broker risk engine equivalent | medium | `ADAPT` as calculation/policy input; do not duplicate authority |
| Validation/backtest | validation engine, journal, JSON artifacts | evidence/catalog and tester adapter | high | `MERGE` provenance, preserve old artifacts |
| Robot catalog | globs/strategy catalog | `RobotCatalog`, provenance DB | high | `KEEP_OURS` canonical catalog |
| MQL5 compile/test evidence | legacy compile/test paths | `mql5_evidence`, `StrategyTesterAdapter` | high | `KEEP_OURS` adapter and evidence contracts |
| MT5 reads | legacy connector | `market_readonly.py` | medium | `KEEP_OURS` Jarvis read-only boundary |
| MT5 orders | dashboard -> server -> `mt5_trader` | no canonical order tool | high | `LEGACY_FREEZE`; separate future gate |
| Position management | legacy position manager | no canonical equivalent | medium | `REFERENCE_ONLY` until approved |
| Desktop shell | Golden launchers and utilities | Jarvis Desktop/WebView | medium | `KEEP_OURS` Jarvis shell; reuse UI assets |

## Existing Golden Scanner trade path

The strongest duplication is not the Scanner calculation itself but the scanner-to-broker bridge. Golden owns radar collection and setup scoring, then its dashboard can directly POST `/api/mt5/auto_trade`; the backend authorizes a mutation and invokes `mt5_trader.execute_trade`, which can call `mt5.order_send`. Jarvis has no equivalent canonical broker order tool, so this path cannot be silently reclassified as a Jarvis capability. It remains a legacy external-side-effect authority and must be wrapped or frozen before any future integration.

The Deep Analysis button is a second overlap: it calls `/api/mt5/full_analysis`, which invokes `FullAnalyzer`, `MasterAnalyzer`, optional Cline/OpenRouter providers and journals the result. It is useful intelligence, but its direct server/provider route is not the canonical `ModelRouter` or `AuditLog` boundary.

## Authority rule

Domain computation may be reused; execution authority may not be duplicated. A Golden implementation is reusable only when it can return a bounded, provenance-bearing read model or calculation. Any path that can mutate broker, account, credentials, tasks, filesystem, provider configuration or desktop state remains behind Jarvis security and audit.
