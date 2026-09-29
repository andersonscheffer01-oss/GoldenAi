# JARVIS B4.1 Wave 2 - Security Authority Convergence

Status: IMPLEMENTED FOR A SMALL SAFE READ SCOPE / HIGH-RISK FROZEN
Baseline: `05d0d6b9d1ff67eaf6a2e9f482da03faeb98378b`

## Authority decision

`jarvis_core.security.SecurityManager` is the canonical decision authority for
the migrated scope. `core.execution.ExecutionService` is a compatibility
facade there: it delegates one safe read decision and records the compatibility
event, but it does not create a second approval policy or execute a handler.

The adapter boundary is `jarvis_core.security_compatibility.ExecutionSecurityFacade`.
It creates a non-executing, low-risk canonical `Tool` descriptor and calls
`SecurityManager.decision` exactly once. An unavailable or malformed adapter
result blocks the action.

## Migrated scope

The web composition root injects the canonical facade into the legacy
`PermissionManager`/`ExecutionService` pair. The migrated callers are:

- configured/protected-path `PermissionManager.can_read` after its existing
  path policy passes;
- `can_internet_search` and `can_internet_fetch`, which already use the safe
  `READ` authorization path;
- the existing `TaskManager` confirmation paths, now using explicit expected
  tool and argument bindings when consuming canonical tokens.

The legacy path and protected-directory rules remain owned by
`PermissionManager`. They are unique compatibility protections, not a second
generic approval decision.

## Confirmation contract

`SecurityManager.create_confirmation` stores the tool, immutable copied
arguments, command, risk, creation time, expiry, and a canonical signature.
The signature covers action (`tool`), target/arguments, and command. Sensitive
argument keys are redacted only in the signature material; execution arguments
remain available to the existing canonical service and are never copied into
these documents.

`consume(token, expected_tool=..., expected_arguments=..., expected_command=...)`
performs the following checks in order:

1. token exists and is not expired;
2. stored arguments still match the stored signature;
3. supplied action, target, and optional command match the approved request;
4. only then is the token removed and returned.

An action/target mismatch is denied without consuming the original approval.
That preserves the valid approval for its original immutable request while
preventing substitution. A tampered, expired, invalid, or already consumed
token is removed/denied and cannot be retried.

Canonical token scope is `ONCE`: one successful consume, with the existing TTL.
Legacy `TASK` approvals remain in `ExecutionService` for unmigrated write and
high-risk callers; they are not silently converted into unlimited canonical
tokens. `TASK_COMPATIBILITY_REQUIRES_FOLLOWUP` remains the explicit boundary.

## Preserved and frozen areas

Preserved legacy protections include protected paths, configured allowlists,
safe external-read purposes, permission modes, and the persistent root
approval records for unmigrated callers. `PermissionManager` and
`ExecutionService` are not deleted.

Frozen for a later wave: MT5, order sending, auto-trade, close-position,
tester/backtest, MQL5 compilation, destructive desktop actions, credentials,
providers, HTTP authentication, database migration, and voice/hardware.
No executor was added and no provider, broker, account, or device was touched.

If the canonical facade is absent, raises, returns an invalid decision, or is
asked to authorize anything outside the read-only mapping, the request fails
closed. There is no silent fallback for a configured migrated scope.

## Validation

Wave 1 characterization remains green after the deliberate signature-binding
correction. Wave 2 tests cover action/target mismatch, tamper invalidation,
TTL/single-use compatibility, exact single delegation, canonical deny without
legacy fallback, path-policy preservation, TaskManager binding, and the
absence of an executor/trading path. Validation is static/temporary-fixture
only; MT5, Strategy Tester, MQL5, live trading, voice hardware, providers,
and database migrations are out of scope.
