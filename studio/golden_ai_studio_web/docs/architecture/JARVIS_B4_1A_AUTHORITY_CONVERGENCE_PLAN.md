# JARVIS B4.1A - Authority Convergence Plan

Status: DESIGN ONLY / READ-ONLY
Baseline: `c033b61dbbe684ee0943854e650f471bfd87a31b`

## Scope and guardrails

This document describes a future convergence path. It does not implement any
delegation, authentication, migration, provider policy, trading behavior, or
database change. No provider, MT5, Strategy Tester, voice hardware, or
external service was invoked while producing this design.

The design preserves the canonical Jarvis direction:

```text
Jarvis Web / Desktop
  -> inbound perimeter
  -> JarvisService / ToolRegistry
  -> SecurityManager
  -> explicit approval where required
  -> ModelRouter or provider adapter
  -> AuditLog
```

The root `core.*` services remain important compatibility surfaces during
migration, but they must not become a second product authority.

## Current authority inventory

### Root core authority

`core.permissions.PermissionManager` is instantiated by `server_agent.py` and
wraps `core.execution.ExecutionService`. It currently combines:

- read, write, execute, path, and internet policy checks;
- permission modes including `READ_ONLY`, `ASK`, `AUTO_SAFE`, and `FULL`;
- approval requests and execution authorization;
- persisted approval and execution state in `data/golden_ai.db`;
- an associated `core.audit.AuditLogger` event path.

`core.execution.ExecutionService` is therefore more than a narrow executor. It
currently acts as policy evaluator, approval manager, execution gate, and
event producer. Multiple root modules instantiate or import these classes,
including vision, video, documents, tools, computer, coding, market, media,
orchestration, and application context modules.

### Canonical Jarvis authority

`jarvis_core.security.SecurityManager` is the intended Jarvis tool
authorization owner. Its current contract is scoped around tool security
requirements, side-effect/risk classification, pending approvals, and
single-use approval consumption.

`jarvis_core.audit.AuditLog` is the intended Jarvis audit owner. It writes the
`jarvis_audit` SQLite record set and sanitizes sensitive fields such as
passwords, tokens, secrets, API keys, authorization values, cookies, and
payload-like data.

`JarvisService`, `ToolRegistry`, and the canonical orchestrator/model router
are the intended composition points. The observed B4.1A state does not yet
prove that every inbound HTTP route is inside this composition.

## PermissionManager versus SecurityManager

| Concern | Root PermissionManager / ExecutionService | Jarvis SecurityManager | Convergence implication |
|---|---|---|---|
| Read access | Permission mode and path policy | Tool/security requirement | Preserve the stricter result while mapping contracts |
| Write access | Path and operation policy, often with persisted approval | Tool risk and scoped approval | One approval vocabulary and correlation ID are needed |
| Execute access | Command/process authorization and critical blocking | Tool side-effect and approval policy | Do not remove root checks until equivalent tool checks are proven |
| Approval state | Root persistence and execution events | In-memory scoped pending approvals/tokens | Define ownership and expiry before delegation |
| Target identity | Paths, commands, action names, context | Tool name, risk class, request/session context | Stable target normalization is required |
| Audit coupling | Root audit event is coupled to execution service | Jarvis audit is coupled to Jarvis flow | Emit one canonical event, retain compatibility metadata during transition |
| Modes | `READ_ONLY`, `ASK`, `AUTO_SAFE`, `FULL` | Security requirements and explicit approval | Use an adapter, not a second policy table |

The overlap is real, but the semantics and persistence are not interchangeable.
The gap is classified as `SEMANTIC_MISMATCH`, not as proof that either system
can be deleted immediately.

## ExecutionService target role

The target role for `ExecutionService` is a compatibility facade and execution
adapter. In a future approved wave it should translate legacy root requests to
canonical Jarvis security requests, receive an allow/deny/approval result,
and report the result through `AuditLog`. It must not retain an independent
final policy decision after delegation is proven.

Required future contract properties:

1. stable `request_id`, `session_id`, actor, tool/action, target, risk, and
   side-effect fields;
2. explicit distinction between denied, needs approval, approved, executed,
   failed, and cancelled;
3. no approval replay across target, user/session, or action changes;
4. compatibility behavior for existing Desktop and root callers;
5. fail-closed behavior for dangerous or unmapped actions;
6. one canonical audit record with links to legacy correlation data.

## Audit convergence

`core.audit.AuditLogger` currently writes daily JSONL records with action,
status, target, action ID, session, agent, input summary, result, error,
duration, files, commands, and timestamp. It is active through the root
execution path.

`jarvis_core.audit.AuditLog` writes SQLite `jarvis_audit` records and applies
the canonical sensitive-field sanitizer. It is the target authority.

Before any removal, a schema mapping and dual-observation period are required.
The root logger may continue producing compatibility records, but those
records must be explicitly marked as legacy/derived and must not be mistaken
for an independent audit authority. No historical records should be rewritten
in this design phase.

## HTTP perimeter target

The current `server_agent.py` API dispatcher routes `/api/*` requests through
`handle_api` and `route_api`. The inspected HTTP path has no proven shared
inbound Authorization validation before route selection, and it advertises
permissive `Access-Control-Allow-Origin: *`. Observed `Authorization` headers
are mainly outbound provider headers, not evidence of inbound client
authentication.

Wave 1 also confirmed a separate Gateway WebSocket perimeter: the UI derives
`:8766/ws`, sends `hello`, then sends device-token `auth`. This is a real
security boundary for Gateway clients, but it is not automatically inherited
by the HTTP 8765 API. The two contracts must converge or be explicitly scoped.

The target perimeter has four explicit classes:

1. local health and static assets: narrowly public as required;
2. authenticated read: overview, radar, scanner, evidence, memory reads;
3. authenticated mutation: writes, task changes, configuration, desktop
   actions;
4. dangerous operation: explicit approval plus canonical security and audit,
   including MT5 compile, backtest, order, close-position, and auto-trade
   routes.

Web and Desktop must receive the same decision contract. Desktop compatibility
is a migration constraint, not permission to bypass the perimeter.

## Direct provider and legacy trading convergence

Direct provider helpers and legacy `/api/chat`, `/api/agent`, and streaming
paths remain reachable in `server_agent.py`. Canonical B3 routes use Jarvis
brain/model-router paths, but that does not establish that all legacy paths
delegate to them. B4.1A records the bypasses; provider policy remains a later
approved concern.

The target trading path is:

```text
route
  -> inbound auth
  -> JarvisService
  -> ToolRegistry
  -> SecurityManager
  -> explicit approval
  -> MT5 provider
  -> AuditLog
```

The currently observed `/api/mt5/positions` read path has no visible mutation
authorization call in the inspected route body. Mutation routes such as
compile, real backtest, auto-trade, and close-position use the root execution
authorization helper, but remain legacy perimeter surfaces. This requires
characterization, freeze rules, and later delegation; no route is changed by
this document.

## Classification and stop conditions

| Classification | Meaning in this design |
|---|---|
| `FREEZE_FIRST` | Keep reachable only under existing safety controls; block expansion while authority is unknown |
| `DELEGATE_FIRST` | Add an explicit adapter boundary before changing behavior |
| `MIGRATE_DIRECTLY` | Only for characterized low-risk reads with a compatible contract |
| `KEEP_READ_ONLY` | Preserve a read path while evidence and ownership are collected |
| `REMOVE_LATER` | Candidate only after reachability and replacement are proven |

Any unknown authority, route ownership, or approval semantics is a stop
condition for implementation. The first future convergence wave must be
independently reviewed and checkpointed before the next wave.
