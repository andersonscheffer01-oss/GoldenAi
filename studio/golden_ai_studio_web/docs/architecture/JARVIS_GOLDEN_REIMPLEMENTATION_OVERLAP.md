# JARVIS / GOLDEN — Reimplementation and Overlap Audit

## Summary

The project already has a canonical Jarvis Core and several strong Golden domain implementations. Reimplementation risk is highest where a new UI or service could recreate a second chat brain, voice brain, scheduler, security gate, memory store, model router or trading authority. The safe strategy is to reuse existing implementations behind canonical boundaries and to freeze direct legacy side effects.

| Risk | Existing implementations | Avoided reimplementation |
|---|---|---|
| Second orchestrator | `server_agent` legacy loops; Jarvis `Brain`/`JarvisService` | do not create Golden Brain |
| Second tool registry | server handlers and MCP surfaces; `ToolRegistry` | register canonical tools only |
| Second security gate | UI confirms and route guards; `SecurityManager` | do not make UI confirmation authority |
| Second audit model | journal/JSONL/analytics; `AuditLog` | adapt read receipts; no parallel receipt authority |
| Second task engine | old runtime copies; TaskManager/scheduler | keep canonical task DB/scheduler |
| Second memory system | Golden/runtime copies; Jarvis memory boundary | no database merge without data gate |
| Second voice brain | browser recognition/TTS and old routes; VoiceService | keep one Core VoiceService |
| Second market/radar authority | Golden market/scanner; future Jarvis read model | wrap/adapt calculations, do not fork formulas casually |
| Second strategy catalog | setup/robot globs; RobotCatalog/evidence | one identity/provenance owner |
| Second tester authority | legacy launch paths; StrategyTesterAdapter | one controlled adapter and immutable evidence |
| Second broker authority | dashboard/server/trader; no canonical Jarvis writer | freeze until explicit execution gate |

## Existing Golden Scanner trade path

The Scanner calculation should not be rewritten inside Jarvis. Its output can be adapted to a versioned read model with source bars, indicator inputs, setup identity, score components, readiness, validation and stale/error status. The current dashboard’s `executeTradeFromModal`, timer-based `AUTO-TRADE`, `/api/mt5/auto_trade`, `mt5_trader.execute_trade` and `mt5.order_send` form a separate legacy authority chain. Copying that chain into Jarvis would create the exact parallel trading authority the architecture forbids.

Deep Analysis has the same boundary issue: its deterministic analysis, optional external model calls and journal persistence are useful, but direct provider selection must not be rebuilt beside `ModelRouter`, and its resulting proposal must not implicitly become an execution command.

## Classification vocabulary

- `KEEP_OURS`: canonical Jarvis implementation is the authority.
- `PORT`: Golden domain capability can move behind a Core read model.
- `ADAPT`: reuse behavior/contracts while changing ownership and provenance.
- `MERGE`: combine evidence/data contracts without merging authorities.
- `REIMPLEMENT_PATTERN`: only the pattern is reusable when direct code is unsafe.
- `REFERENCE_ONLY`: consult but do not wire directly.
- `LEGACY_FREEZE`: leave operationally available but block new dependencies.
- `REJECT`: unsafe or contradicts single-authority architecture.

## No-feature-loss rule

Feature parity is not achieved by duplicating screens. A capability is recovered only when its useful behavior, source identity, error/stale states, security boundary, audit receipt and provenance are represented in the canonical surface. Unknowns remain unknown; no synthetic validation is promoted to real evidence.
