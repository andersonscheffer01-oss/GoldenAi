# JARVIS / GOLDEN Gap Register

Severity reflects integration and governance risk found by static/read-only audit. Entries are not permission to implement changes.

| ID | Severity | Gap | Evidence | Recommended disposition |
|---|---|---|---|---|
| CRIT-001 | Critical | Legacy Web REST routes still expose direct action paths for trading, compile, import, and legacy real backtest. | `dashboard.html`; `server_agent.py` action handlers; `_authorize_api_mutation` is present but this is a parallel surface. | Contain and route through canonical Jarvis commands; prove parity before retirement. |
| CRIT-002 | Critical | Legacy UI mixes analysis, simulation/backtest, and live-action controls without one visible mode contract. | `dashboard.html` direct MT5 actions and `/api/mt5/real_backtest`. | Make mode and authorization state explicit in the shared Control Center. |
| HIGH-001 | High | Robot Catalog and Strategy Tester evidence backend is not represented as a complete Control Center UI. | `RobotCatalogReadModel`, `mql5_evidence.py`, `strategy_tester_adapter.py` exist without full catalog/evidence views. | Add read-only views before controlled-run UX. |
| HIGH-002 | High | Legacy MQL5/EA Builder flow writes to external MT5 paths and instructs manual F7 compilation outside the evidence chain. | `studio_v7.html` builder/compile flow. | Bind source and compiled artifacts to canonical compile evidence. |
| HIGH-003 | High | Memory retains a legacy compatibility fallback beside V2. | `CanonicalMemoryBoundary` and `GoldenMemoryManager`/V2 initialization. | Keep one boundary; migrate and measure before removing fallback. |
| HIGH-004 | High | `server_agent.py` remains a large monolithic route and compatibility authority, including direct MT5/provider probes. | Legacy route map and `api_status`; shared Core is available but not every read is through its model. | Classify routes and migrate read models incrementally. |
| MED-001 | Medium | Legacy native Desktop compatibility classes coexist with the canonical WebView shell. | `main_window.py`, `main_window_v4.py`, `web_window.py`. | Keep compatibility until WebView feature parity is proven; label ownership. |
| MED-002 | Medium | Real voice VAD/STT gate remains incomplete and faster-whisper is unavailable in the current environment. | Voice service modules, known issues, checkpoint Gate 3A. | Finish the acoustic gate or expose explicit unavailable state. |
| MED-003 | Medium | Historical backtests do not all have verified robot association/provenance. | 177 `config/backtest_results` artifacts and catalog unresolved handling. | Classify unresolved artifacts; never rewrite historical results silently. |
| LOW-001 | Low | Context docs and checkpoint exact HEAD are stale relative to current descendant commit. | `CHECKPOINT.md`, `CURRENT_WORK.md`, `HANDOFF.md`. | Refresh documentation in a dedicated handoff/documentation pass. |

## Confirmed non-findings

- No unauthenticated live-order bypass was proven by this read-only audit.
- No live order, broker mutation, Strategy Tester run, or production robot was used.
- No replacement Core or parallel execution architecture was introduced.
- No device registry, production robot source, or historical backtest was modified by this audit.
