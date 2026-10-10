# JARVIS Web / Desktop Integration Plan

This plan is intentionally documentation-only. It describes incremental batches for the existing architecture and does not authorize live trading, Strategy Tester execution, or replacement of Jarvis Core.

## Batch 0 - Baseline and containment

Owner: Jarvis Core and Web/Desktop maintainers.

- Freeze the current canonical boundary: `Gateway -> JarvisService -> ToolRegistry -> SecurityManager`.
- Inventory every legacy `server_agent.py` action route and label read-only, simulated, compile, backtest, or live-trading behavior.
- Keep `dashboard.html`, `studio_v7.html`, old native Desktop classes, old DBs, 177 historical backtests, nine robot sources, and prior fixture runs intact.
- Add regression tests that prove legacy actions cannot bypass the same authorization and audit requirements.

Success: no unclassified action route and no second execution authority introduced.

## Batch 1 - Shared Control Center read models

- Add read-only Gateway views for robot catalog, evidence, Strategy Tester environment, task state, and audit/provenance state.
- Use existing `RobotCatalogReadModel`, `StrategyTesterAdapter`, `AuditLog`, and TaskManager; do not duplicate their storage or logic.
- Render the views in canonical `jarvis_ui`, then verify Desktop WebView receives the same data.

Dependencies: Batch 0 route inventory and focused contract tests.

Success: Web and Desktop show the same read-only state from the same Core instance.

## Batch 2 - Controlled tester UX

- Present fixture identity, source hash, compile result/hash, parameter fingerprint, manifest, tester configuration, and run lineage.
- Require explicit authorization for a new controlled run and preserve failed/unverified/retry relationships.
- Keep `Optimization=0`, `UseRemote=0`, `UseCloud=0`, and `AllowLiveTrading=0` for the fixture gate.

Dependencies: verified compile evidence and Batch 1 read models.

Success: a user can review a complete preflight and provenance chain before any tester process starts.

## Batch 3 - Legacy action containment and migration

- Route legacy dashboard actions through canonical commands or make them read-only with a clear migration state.
- Remove duplicated business decisions from UI JavaScript only after equivalent canonical commands and tests exist.
- Preserve compatibility endpoints and artifacts until a separately approved migration gate confirms parity.

Dependencies: route inventory, authorization tests, rollback plan, and explicit approval for each action family.

Success: no direct legacy UI action can become a second authority for live trading, compile, or backtest.

## Batch 4 - Memory, voice, and capability closure

- Keep V2 behind `CanonicalMemoryBoundary`; retire compatibility fallback only after migration evidence.
- Complete the real voice acoustic/VAD/STT gate and retain typed fallback.
- Fill only the missing Skills/MCP mappings that have an explicit provider, risk classification, and audit path.

Success: each exposed capability has one owner, one security path, one audit path, and a tested user-facing state.

## Verification and rollback

Every batch requires focused tests, `git diff --check`, service health verification, and a read-only UI smoke test. Rollback means disabling the new UI route or feature flag and returning to the already existing canonical tool path; it does not mean deleting databases, backtests, or legacy source files.
