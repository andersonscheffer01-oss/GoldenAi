# JARVIS / GOLDEN Full Integration Audit

Status: `PASS_WITH_RESTRICTIONS`
Audit mode: read-only architecture and integration audit.
Date: 2026-09-28

## Baseline

- Repository: `C:\GoldenAI`
- Branch: `main`
- Actual HEAD: `3e28f9ab4e2eb232b84d9357b11b30eeaa722bee`
- Checkpoint HEAD: `4362c5398d3ef8c2f6585bad8b1d90c0609ff175`
- Reconciliation: checkpoint is stale in exact HEAD, but its commit is an ancestor of the current HEAD; no history divergence was found.
- Current worktree: pre-existing modifications and untracked artifacts are present. They were preserved and not staged, reverted, or deleted.
- Runtime observed: Golden Web on `https://127.0.0.1:8765`; Gateway health on `https://127.0.0.1:8766/health`.

## Scope and verdict

The audit covered the Web surfaces, Desktop shell, Jarvis Core, task and memory systems, skills, MCP, voice, Computer Use, MT5/MQL5, robot catalog, Strategy Tester, audit/provenance, and legacy surfaces. No Strategy Tester run, live order, broker mutation, or production-robot change was performed.

The architecture has a real canonical path:

`UI -> Gateway -> JarvisService -> ToolRegistry -> SecurityManager -> provider -> AuditLog`

That path is reused by the canonical Jarvis UI and Desktop WebView. The result is restricted because the legacy Web REST surface, legacy MT5 modules, compatibility memory path, and legacy native Desktop surfaces remain available beside the canonical path.

## Integration matrix

| Area | Finding | Status |
|---|---|---|
| Golden Web | `server_agent.py` serves legacy dashboard/studio routes and also shares the Core service. | `PARTIAL` |
| Canonical Jarvis Web | `jarvis_ui/jarvis.html` routes commands through Gateway and JarvisService. | `PASS` |
| Desktop | PySide6/QtWebEngine loads the canonical Jarvis Web UI through CoreLauncher. | `PASS_WITH_RESTRICTIONS` |
| Shared Control Center | Web and Desktop share the canonical UI, but legacy surfaces coexist. | `PARTIAL` |
| Jarvis Core | JarvisService owns ToolRegistry, security, providers, tasks, catalog, tester, and audit. | `CANONICAL` |
| Security | Canonical tools are risk/confirmation/audit governed; legacy endpoints need containment. | `PASS_WITH_RESTRICTIONS` |
| Tasks | Canonical TaskManager and scheduler path use `studio/.../jarvis/golden_tasks.db`. | `PASS_WITH_RESTRICTIONS` |
| Memory | V2 is the preferred writer behind CanonicalMemoryBoundary; legacy fallback remains. | `PARTIAL` |
| Strategy Tester | Adapter/evidence backend exists; full Control Center UI is not wired. | `PARTIAL` |
| Robot Catalog | Read model and evidence association exist; full UI is not wired. | `PARTIAL` |
| Voice | Services exist, but real acoustic/VAD/STT gate is incomplete. | `PARTIAL` |

## Web and Desktop

`server_agent.py` is the backend entry point on port `8765`, with a broad legacy route map. `jarvis_ui/src/gateway-adapter.js` and `command-router.js` define the canonical command path and Gateway port `8766`. `dashboard.html` and `studio_v7.html` still call legacy REST endpoints directly, including gated trading, compile, import, and legacy backtest actions.

`jarvis_desktop/web_app.py`, `core_launcher.py`, and `web_window.py` reuse the same Core and load `jarvis_ui/jarvis.html`. Legacy native classes remain compatibility surfaces and are not a second Core authority.

## Core, governance, and provenance

`JarvisService` constructs the shared ToolRegistry, SecurityManager, AuditLog, RobotCatalogReadModel, StrategyTesterAdapter, TaskManager, orchestrator, and runtime coordinator. Gateway execution explicitly delegates to JarvisService. Security confirmation tokens and sanitized AuditLog records are present for canonical high-risk tools.

The fixture/evidence chain is present in `mql5_evidence.py` and `strategy_tester_adapter.py`, with the dedicated fixture archived and prior failed runs preserved. This audit did not start a tester run. The canonical catalog and evidence path must remain the only path for the controlled tester gate.

## Critical restrictions

- Static audit identified legacy direct REST/action surfaces for live trading, compile, import, and legacy real backtest. No unauthenticated bypass was proven by this read-only gate.
- No live order, broker mutation, Strategy Tester execution, or production robot selection occurred during this audit.
- The 177 historical backtest artifacts, nine repository robot sources, `device_registry.json`, and prior fixture runs were not modified.
- No secrets or credential values were read into this report.

## Tests and verification

- Focused integration/security/evidence suite: `188 passed`.
- Full collection: `2022 tests collected`.
- Full suite execution remains outside this gate because the known `tests/live_smoke_test.py::test_streaming` fixture issue is documented and pre-existing.
- `git diff --check`: clean before documentation changes.

## Final architecture statement

Jarvis Core remains the sole canonical execution authority. Web and Desktop can share the canonical Control Center, but the product is not yet a single fully governed surface while legacy REST, MT5, memory, native Desktop, and incomplete tester/catalog UI paths remain exposed. The next work must contain and migrate those surfaces incrementally, without replacing Jarvis Core or creating a parallel architecture.
