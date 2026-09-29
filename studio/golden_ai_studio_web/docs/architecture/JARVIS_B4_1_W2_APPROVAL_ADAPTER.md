# JARVIS B4.1 Wave 2 - Approval Adapter Contract

## Canonical envelope

The canonical approval identity is an opaque in-memory token linked to:

`tool`, `arguments/target`, `command`, `risk`, `created_at`, `expires`, and
`signature`.

The caller may supply expected `tool`, expected `arguments`, and expected
`command` at consumption time. These values are compared to the approved
request before the one-time removal. No actor, user, mission, or session
identity is fabricated by this wave.

## Mapping table

| Legacy concept | Wave 2 mapping | Decision |
|---|---|---|
| `READ` safe path | canonical low-risk read descriptor | `ADAPT` |
| protected/allowed path rules | `PermissionManager` compatibility policy | `KEEP` |
| `can_internet_search/fetch` | canonical low-risk read descriptor | `ADAPT` |
| `ONCE` | canonical expiring single-use token | `MERGE` |
| `TASK` | legacy persistent task grant for unmigrated scope | `LEGACY_FREEZE` |
| action/target operation key | canonical tool/argument signature plus expected comparison | `MERGE` |
| high-risk/trading approval | existing root path remains frozen | `LEGACY_FREEZE` |

## Mismatch and lifetime policy

The chosen policy is **mismatch does not consume**. A wrong action or target is
denied, while the original token remains available for the exact approved
request. This prevents a bad caller from burning a valid approval and makes
the compatibility behavior explicit. If the stored approval itself is
tampered with, the token is invalidated immediately.

`ONCE` is the only canonical scope admitted here. TTL remains explicit and is
enforced before consumption. `TASK` is not represented as a reusable
canonical token; `TASK_COMPATIBILITY_REQUIRES_FOLLOWUP` is required before any
future migration of that scope.

## Facade contract

`ExecutionSecurityFacade.authorize(...)` accepts only the safe mapped reads:

- `read` / `read_file` -> `legacy_read`;
- `internet_search` -> `legacy_internet_search`;
- `internet_fetch` -> `legacy_internet_fetch`.

It calls the canonical `SecurityManager` once, never invokes a handler, and
returns `COMPLETED`, `WAITING_APPROVAL`, or `BLOCKED`. The root
`ExecutionService` converts that result into its existing
`AuthorizationResult` shape and emits compatibility audit/event records.
Those records do not become a second security authority.

Anything outside this mapping, any non-LOW read risk, an unavailable manager,
or an invalid adapter result fails closed. MT5, trading, tester, MQL5,
destructive desktop, credentials, providers, HTTP auth, and voice remain
unmigrated.

## Ownership after Wave 2

- `SecurityManager`: canonical decisions, signatures, TTL, single-use consume.
- `ExecutionSecurityFacade`: bounded read compatibility translation only.
- `PermissionManager`: legacy path/app/folder/safe-purpose protections.
- `ExecutionService`: compatibility result shape, root persistence, and frozen
  legacy approvals outside the migrated read scope; no executor.
- `AuditLog`: existing Jarvis service audit remains unchanged; no new audit
  authority is introduced by this wave.
