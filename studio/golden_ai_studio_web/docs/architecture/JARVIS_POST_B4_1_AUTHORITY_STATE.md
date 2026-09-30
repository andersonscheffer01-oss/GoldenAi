# JARVIS Post-B4.1 Authority State

Baseline: `8eca3d8f077b3a421f90b8cfd035abd217cd2429`

## Canonical authorities

| Authority | Owner | State |
|---|---|---|
| Core/Brain | `jarvis_core.service.JarvisService` and existing `Brain` | CANONICAL |
| Model routing | existing `ModelRouter` | CANONICAL |
| Tool security | existing `SecurityManager` and ToolRegistry | CANONICAL |
| Approval | existing action/target/TTL/single-use confirmation flow | CANONICAL |
| Audit | existing `AuditLog` | CANONICAL for migrated/frozen scope |
| Tasks | existing TaskManager | CANONICAL with DB-binding follow-up |
| Memory | `CanonicalMemoryBoundary` | CANONICAL direction; scientific semantics pending |
| Streaming | `JarvisService.stream_response` through Brain/ModelRouter | CANONICAL |
| MT5/trading | no Jarvis execution authority | FROZEN / OUT OF SCOPE |

## Observability

HTTP request IDs and correlation IDs are preserved into streaming and route
boundary events. Stream telemetry includes provider/model selection, fallback,
chunk count, elapsed time, cancellation, and failure without token content.
High-risk denials record profile blocks and frozen legacy-route events. Full
cross-surface freshness and deployment observability remains a later gate.

## Final assessment

`B4_1_FINAL_STATUS: CLOSED_WITH_NON_BLOCKING_RESTRICTIONS`

The blocking restrictions are closed: no active direct-provider stream and no
active mutable legacy handler bypass from the dispatcher. Remaining work is
follow-up, not a reason to reopen this batch: native token streaming for
complete-only adapters, migration of safe legacy reads/catalogs, and broader
observability. Do not start Market recovery, Robot Intelligence, or Voice
automatically.

## Next gate

The next implementation batch should be chosen from the Golden Final Coverage
Audit, with Market/Radar read depth and Scanner/Risk/Validation depth ahead of
Robot-to-Market matching. It must have a separate allowlist and baseline.
