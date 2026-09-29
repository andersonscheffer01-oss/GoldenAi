# JARVIS B4.1A - Migration Waves

Status: DESIGN ONLY / NOT AUTHORIZED TO EXECUTE
Baseline: `c033b61dbbe684ee0943854e650f471bfd87a31b`

These waves are sequencing guidance, not an implementation plan approved for
execution. Each wave requires its own scope, review, checkpoint, and rollback
decision. No wave was started in B4.1A.

## Wave 1 - Authority contract and characterization

Objective: establish an evidence-backed inventory of owners, callers,
side-effect classes, approval semantics, audit fields, route reachability, and
legacy provider/trading paths.

Current: root `PermissionManager`/`ExecutionService` and `AuditLogger` are
active alongside Jarvis `SecurityManager` and `AuditLog`; HTTP auth coverage is
partial/unknown.

Target: a versioned compatibility contract and route/authority matrix with no
behavioral change.

Scope: source inventory, fixtures, schemas, correlation IDs, mock-only
characterization, and documentation.

Dependencies: complete caller map, Desktop/Web request shapes, deployment
assumptions, and approval-owner decision.

Risks: hidden callers, stale route references, and confusing source presence
with runtime reachability.

Stop: any unknown dangerous caller, unbounded route, or unresolved approval
semantic mismatch.

Checkpoint: review the four B4.1A documents and authorize separately.

## Wave 2 - Security authority compatibility boundary

Objective: make legacy callers address one canonical security decision while
preserving compatibility responses.

Target: `ExecutionService` delegates to Jarvis `SecurityManager`; the adapter
normalizes action, target, risk, actor, session, and approval state.

Scope: authorization contracts and test doubles only at first; no providers,
MT5, trading, voice, or external calls.

Dependencies: Wave 1 contract, approval expiry/replay rules, fail-closed
mapping, Desktop compatibility.

Risks: accidental double approval, changed read behavior, or a legacy caller
that depends on root-only fields.

Stop: any dangerous action that cannot be mapped one-to-one.

Rollback: disable delegation behind a reviewed compatibility switch while
retaining evidence; never silently weaken the root gate.

## Wave 3 - Audit and correlation convergence

Objective: make `AuditLog` the canonical audit authority while preserving a
traceable compatibility record during migration.

Target: one sanitized canonical event for accepted, denied, approved,
executed, failed, and cancelled outcomes, with legacy IDs linked as metadata.

Scope: schema mapping, redaction tests, dual-observation, and event
correlation. Do not rewrite historical records.

Dependencies: Wave 2 decision envelope and stable request/session IDs.

Risks: duplicated events, leaked sensitive fields, broken operational queries,
or false claims of exactly-once behavior.

Stop: sanitizer mismatch or missing correlation for a dangerous action.

## Wave 4 - Inbound HTTP perimeter

Objective: put a reviewed inbound authentication and authorization boundary
before route execution, with Web and Desktop compatibility.

Target: explicit route classes for local health, authenticated read,
authenticated mutation, and dangerous approved operation; narrow CORS and
origin rules; stream auth before SSE creation; one documented relationship
between HTTP 8765 auth and Gateway WebSocket 8766 device auth.

Scope: HTTP request envelope, session/actor propagation, route matrix, CORS,
SSE, and Desktop adapter tests.

Dependencies: Waves 1-3, startup behavior, cached UI assumptions, and local
deployment model.

Risks: dashboard breakage, Desktop startup failure, proxy mismatch, or an
unauthenticated compatibility fallback.

Stop: any mutation route still reachable without a canonical decision.

## Wave 5 - Provider and legacy high-risk containment

Objective: contain direct provider bypasses and move legacy high-risk trading
routes behind the canonical Jarvis path.

Target path:

```text
route -> inbound auth -> JarvisService -> ToolRegistry
  -> SecurityManager -> explicit approval -> provider -> AuditLog
```

Scope: direct chat/agent/stream provider calls, desktop actions, MT5 compile,
backtest, import, auto-trade, close-position, and legacy market writers.

Dependencies: stable security/audit perimeter and verified provider policy.

Risks: provider behavior changes, trading safety regression, lost context,
stream interruption, or duplicate route authority.

Stop: no live trading, MT5 execution, provider call, or Strategy Tester is
allowed as part of design or characterization without a separate explicit
gate.

Rollback: retain frozen legacy route mapping and disable the new delegate at a
reviewed boundary; do not restore unreviewed direct execution.

## Wave decision table

| Surface | First move | Later move |
|---|---|---|
| High-risk MT5 mutation | `FREEZE_FIRST` | `DELEGATE_FIRST`, then canonical execution |
| Legacy direct provider route | `FREEZE_FIRST` | `DELEGATE_FIRST` to ModelRouter policy |
| Low-risk Golden read model | `KEEP_READ_ONLY` | `MIGRATE_DIRECTLY` after auth proof |
| Root ExecutionService | `DELEGATE_FIRST` | Compatibility facade only |
| Root AuditLogger | `DELEGATE_FIRST` | Derived compatibility record or retirement |
| Memory/task stores | `REFERENCE_ONLY` until caller proof | Controlled migration after ownership decision |

## Global gates

No wave may proceed without:

- clean separation from preexisting worktree changes;
- explicit list of files and routes in scope;
- static and mocked tests appropriate to the wave;
- no secrets in artifacts;
- fail-closed behavior for unmapped dangerous actions;
- review of Web/Desktop compatibility;
- a checkpoint recording the exact HEAD, result, and rollback state.

The recommended next gate is review and authorization of Wave 1 design only.
This checkpoint itself changed documentation only and did not begin Wave 1.
