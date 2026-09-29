# JARVIS B4.1 W1 - Approval Compatibility Contract

Status: CHARACTERIZATION_ONLY / contract design, no adapter

## Current approval owners

| Owner | Identity | Scope | Lifetime | Persistence | Consumption |
|---|---|---|---|---|---|
| `PermissionManager` | implicit caller plus fixed task ID for delegated writes | path/action through ExecutionService | inherited from ExecutionService | root execution DB | indirect via returned decision |
| `ExecutionService` | `task_id` + operation key | `ONCE` or `TASK`; operation key includes permission/tool/action/target | no expiry field observed | `data/golden_ai.db` under selected root | `ONCE` marks consumed; `TASK` remains reusable |
| `SecurityManager` | opaque token; tool/arguments/command in memory | token and stored signature | `confirmation_ttl`, default 60 seconds | process memory only | `consume` pops before returning |

## Required comparison

### Identity

The root contract identifies a task and operation key. The canonical contract
identifies a tool and opaque token. Neither current approval structure carries a
strong authenticated user identity or mission identity. The compatibility
adapter must not fabricate those fields.

### Scope

Root scope binds the grant to task and operation key. The canonical token binds
the stored request to the tool and arguments, but the current consumer accepts
the token without a caller-supplied target/action to compare.

### Lifetime and single use

Root `ONCE` is persisted and consumed after authorization; `TASK` remains
reusable until its row is changed. No root expiry was observed. Canonical
tokens expire and are removed on consume, including failed/expired consumption.

### Target/action binding

Root operation keys include permission level, tool name, action, and target.
Changing target or task prevents reuse of the same grant. Canonical tokens
store a signature of tool plus arguments, but this signature is not validated
by `consume` in the current implementation. This is a hard
`SEMANTIC_MISMATCH` and blocks direct substitution.

### Revocation and denial

Root `deny(request_id)` marks a request denied and consumed, but a subsequent
equivalent authorization can create a new request. Canonical denial is handled
by consuming/removing the pending token through the service confirmation path.
The two systems do not have identical revocation semantics.

## Compatibility contract for a future adapter

The adapter must normalize, without changing the legacy caller shape:

```text
legacy request
  -> actor/session/task identity
  -> operation/action/target normalization
  -> risk and side-effect class
  -> canonical SecurityManager decision
  -> approval status with stable request_id
  -> canonical AuditLog event
```

Required properties:

1. `request_id` is stable across a pending approval and distinct from the
   opaque token; legacy IDs may be linked as metadata.
2. Target and action are immutable for an approval. Any change creates a new
   decision.
3. Expiry is explicit. A root approval without expiry cannot silently become a
   canonical timed token without a documented compatibility choice.
4. One-time approvals are consumed atomically and cannot be replayed.
5. Task-scoped approvals retain task binding; they must not become global.
6. Missing SecurityManager or unmapped dangerous actions fail closed.
7. Denied and expired approvals remain auditable without exposing token values.
8. No actor/user/mission identity is invented where the current caller does
   not supply it; the result is `UNKNOWN` until the perimeter provides it.

## Characterization-only test coverage

The W1 fixture tests prove:

- root path and protected-root semantics;
- root `ASK`, `ONCE`, `TASK`, target binding, task binding, denial, critical
  block, and missing capability behavior;
- canonical deny precedence, expiry, invalid token, signature storage, and
  single-use removal;
- absence of an execution dispatcher in `ExecutionService` itself.

These tests capture current behavior. They are not authorization to preserve
unsafe semantics permanently.
