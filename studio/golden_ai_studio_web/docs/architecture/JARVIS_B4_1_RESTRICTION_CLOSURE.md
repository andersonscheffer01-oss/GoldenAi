# JARVIS B4.1 Restriction Closure

Status: `CLOSED_WITH_NON_BLOCKING_RESTRICTIONS`
Batch baseline: `8eca3d8f077b3a421f90b8cfd035abd217cd2429`

## Closure result

The active `/stream/chat` route now delegates to the existing
`JarvisService -> Brain -> ModelRouter` path. The route no longer selects or
calls providers. SSE compatibility is preserved for `token`, `done`, and
`full_response` payloads. Native adapter streaming is optional; complete-only
adapters are exposed as one canonical chunk by `ModelRouter`.

High-risk legacy operational families are stopped at the authenticated API
dispatcher with a deterministic `LEGACY_ROUTE_FROZEN` response and a canonical
AuditLog denial. The `web-ai-safe` profile continues to take precedence and
returns its existing `*_DISABLED_BY_PROFILE` result without dispatching a
legacy handler. Catalog/read-only endpoints not in the freeze matrix remain
compatibility surfaces and are still follow-up candidates.

## Restrictions closed

- Active direct-provider streaming authority: closed.
- Streaming fallback after visible partial output: prohibited.
- Streaming cancellation: cooperative and best effort.
- High-risk mutable legacy handler bypass from the dispatcher: closed by freeze.
- Profile containment: preserved.
- SecurityManager and approval authority: preserved.
- Canonical AuditLog correlation: added for stream lifecycle and route denial.
- Parallel Core, Security, Audit, ModelRouter, Streaming, and Trading authority: none added.

## Non-blocking restrictions

- The former provider-specific implementation is preserved only in the prior
  Wave 5 characterization documents; it is no longer an active method in
  `server_agent.py`.
- Complete-only providers do not produce native token granularity; the router
  exposes one canonical chunk until the provider adapter supplies `stream`.
- Legacy read/catalog endpoints still need caller-by-caller migration and
  source freshness characterization.
- The broader regression suite retains pre-existing Windows SQLite teardown
  failures and research fixtures missing `memory_boundary`; these are not
  caused by this batch.

## Safety

No provider request, MT5 initialization/login, order, broker mutation, Strategy
Tester, MQL5 compilation, Voice initialization, microphone access, database
migration, dependency install, credential change, or push was performed.
