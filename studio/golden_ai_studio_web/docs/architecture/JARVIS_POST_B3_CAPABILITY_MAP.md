# Jarvis Post-B3 Capability Map

Date: 2026-09-29
Baseline: `013ba7c700a5c62fc97aaab10541ed5a769b5d13`
Scope: read-only architectural reconciliation after B3.

This document uses the current Git tree as operational truth. Historical
audits remain useful evidence, but their older baselines are not treated as
the current runtime state.

## Status vocabulary

- `MATURE`: canonical owner, bounded behavior, and focused evidence are established.
- `FUNCTIONAL`: usable canonical path exists, with meaningful integration or proof gaps.
- `PARTIAL`: important implementation exists, but ownership, coverage, or semantics are incomplete.
- `FOUNDATION_ONLY`: contracts, adapters, or evidence exist without a complete product path.
- `DESIGN_ONLY`: intended behavior is documented but not implemented as a canonical capability.
- `LEGACY_ONLY`: useful donor remains outside the canonical authority path.
- `MISSING`: no validated canonical capability was found.
- `DEFERRED`: intentionally outside the active sequence.
- `BLOCKED`: a known gate prevents safe progression.

## Current architecture

The canonical path is:

```text
Jarvis Web/Desktop -> server_agent.py/Gateway -> JarvisService
  -> Brain -> CentralOrchestrator/ModelRouter
  -> SecurityManager/ToolRegistry -> providers
  -> AuditLog and CanonicalMemoryBoundary
```

B3 added Golden read models and MarketContext through the existing service. It
did not replace Jarvis Core, migrate data, promote legacy writes, or make
legacy execution paths canonical. `server_agent.py` still contains direct
legacy handlers and provider code, so the one-authority invariant is a target,
not yet a complete fact at the perimeter.

## Capability map

| Capability | Status | Current evidence | Main restriction |
|---|---|---|---|
| Core / JarvisService | FUNCTIONAL | Service, ToolRegistry, SecurityManager, AuditLog and orchestrator are wired | legacy root stack and direct handlers coexist |
| ModelRouter | FUNCTIONAL | canonical provider adapters, health, timeout and fallback logic | declarative policy and direct-handler containment are incomplete |
| Memory | PARTIAL | Memory V2, legacy compatibility and CanonicalMemoryBoundary exist | scientific evidence/revision/conflict semantics are not fully exposed |
| Tasks / Scheduler | MATURE | canonical TaskManager, approvals, retries, recovery and 8D closure evidence | multiple historical database roots remain |
| Computer Use | MATURE | canonical missions, UIA, browser, checkpoints, scheduler and security gates | real-world coverage remains scoped by external desktop state |
| Desktop | FUNCTIONAL | DesktopCenter shares JarvisService; B3 market surface integrated | legacy desktop V4 remains present |
| Web | FUNCTIONAL | HTTP/SSE/Web UI and canonical Jarvis routes are active | old route surface remains broad |
| Market Intelligence | FUNCTIONAL | B3 read bridge, MarketContext, provenance/freshness envelope and canonical chat | full Radar parity is not present |
| Scanner | PARTIAL | Golden scanner snapshot and normalized fields are read-only bridged | scoring, readiness and semantic detail are not fully canonicalized |
| Radar | PARTIAL | overview/radar/detail read models exist; `market.html` remains donor | charts, replay, sessions, news and macro detail need governed views |
| Deep Analysis | PARTIAL | canonical MarketContext and deep-analysis context/detail adapters exist | full structure/MTF/statistical explanation needs validation |
| Macro / Fundamental | PARTIAL | market data and macro/news fields are exposed when available | source authority and freshness differ by legacy path |
| Risk | PARTIAL | risk read model and no-authorization boundary exist | full explanation, portfolio context and evidence labels are incomplete |
| Validation | PARTIAL | validation summaries and evidence envelopes exist | synthetic versus real evidence and detailed reports need stronger UI/read contracts |
| Performance | FOUNDATION_ONLY | historical statistics, journals and backtest artifacts exist | no reconciled canonical performance model |
| Robot Catalog | FUNCTIONAL | catalog identity, artifact and evidence read models exist | discovery and mutation remain separately governed |
| Robot Repertoire | DESIGN_ONLY | status vocabulary and protection rules are documented | canonical user mutation workflow is not exposed |
| MQL5 | FOUNDATION_ONLY | evidence and provenance contracts exist | compile path remains operational/legacy and unexecuted here |
| Strategy Tester | FOUNDATION_ONLY | controlled adapter, fixture and evidence contracts exist | no normal UI run action; real execution requires a separate human gate |
| MT5 | PARTIAL | read-only containment and lazy-init profile are implemented | live/read validation and any execution authority remain separate |
| Skills | FUNCTIONAL | ToolRegistry and SkillsRouter path exist | capability coverage and ownership inventory are uneven |
| MCP | FOUNDATION_ONLY | definitions and client scaffolding exist | canonical integrated client/provider proof is incomplete |
| Agents | FOUNDATION_ONLY | specialized contracts and legacy agents exist | no need or authority for a parallel orchestrator was proven |
| Voice | BLOCKED | canonical VoiceService and UI clients exist | `REAL_MIC_SIGNAL_PATH_INCONSISTENCY` / low signal gate remains open |
| Vision | FOUNDATION_ONLY | Jarvis vision tools and local-model path exist | broad real-world semantic validation is absent |
| Mobile | MISSING | PWA/LAN references only | no dedicated validated mobile client |
| Observability | PARTIAL | provider telemetry, provenance, freshness and audit fields exist | ownership and cross-path correlation are incomplete |
| Security | PARTIAL | Jarvis SecurityManager is fail-closed for canonical tools | root PermissionManager and direct APIs remain at the perimeter |
| Audit | PARTIAL | canonical AuditLog and B3 read receipts exist | root audit logger and legacy writes coexist |
| Personal Finance | DEFERRED | explicitly out of scope | no Open Finance, banking, card or credential work |

## Post-B3 conclusions

- Market UI, Market Chat, Deep Analysis routing, MarketContext, runtime profile,
  and MT5 lazy-init containment are not missing; they are functional with
  bounded restrictions.
- Full Radar, scanner semantics, risk/validation detail, scientific memory,
  performance reconciliation, and repertoire workflows remain partial or
  foundation-only.
- Direct orders, auto-trade, Enter Trade, production robot behavior and
  legacy browser voice are not recovery targets for a normal B4 implementation.
- One Jarvis, one Core, one Security model, one Task system, one Audit model,
  one ModelRouter, and one memory authority remain non-negotiable targets.

## Lost capability reconciliation

| Archaeology groups | Post-B3 state |
|---|---|
| Typed scientific evidence, revisions, conflicts, experiment links | STILL_MISSING / PARTIAL; ADAPT behind CanonicalMemoryBoundary |
| Radar detail, deep analysis, meta strategy, risk, validation | PARTIAL; B3 read bridge exists, richer read models remain |
| Statistics, journals, market AI history | LEGACY DATA EXISTS; recovery requires provenance gate |
| Robot catalog and tester provenance | RECOVERED AS READ FOUNDATION; execution and repertoire writes remain separate |
| UI parity and control-center panels | PARTIAL; B3 summary exists, full parity is not claimed |
| Voice hardware lessons | REFERENCE_ONLY; canonical Voice remains blocked |
| Auxiliary conversations and agent/plugin metadata | PARTIAL/DEFERRED; no authority promotion |
| Direct scanner/trade execution and production MQL5 behavior | LEGACY_FREEZE |

## Safety status

This map was produced without provider calls, model downloads, MT5 access,
trading, Strategy Tester execution, MQL5 compilation, Voice hardware access,
database migration, data import, MCP installation, commit, or push.
