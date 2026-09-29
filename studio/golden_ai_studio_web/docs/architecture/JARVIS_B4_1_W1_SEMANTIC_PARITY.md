# JARVIS B4.1 W1 - Semantic Parity

Status: HISTORICAL CHARACTERIZATION / Wave 2 convergence applied to safe scope
Baseline: `c033b61dbbe684ee0943854e650f471bfd87a31b`

## Method inventories

### `core.permissions.PermissionManager`

Observed public methods:

| Method | Inputs | Output | Current semantic |
|---|---|---|---|
| `is_read_only` | none | `bool` | `settings.read_only` or disabled writes |
| `is_protected_dir` | path | `bool` | resolved path under configured protected roots |
| `can_read` | path | `PermissionDecision` | allows configured/protected project paths; rejects outside |
| `can_write` | path, explicit flag | `PermissionDecision` | read-only/protected/outside denied; otherwise delegates to ExecutionService unless explicit |
| `can_execute_command` | command, explicit flag | `PermissionDecision` | disabled or missing explicit approval denied/delegated |
| `can_read_external_safe` | purpose, optional path | `PermissionDecision` | fixed purpose allowlist plus safe-root check |
| `can_launch_allowed_app` | app name | `PermissionDecision` | fixed application allowlist |
| `can_open_folder` | path | `PermissionDecision` | fixed folder allowlist |
| `can_write_approved_coding_task` | task mapping | `PermissionDecision` | requires six proof flags and project path |
| `can_internet_search/fetch` | query or URL | `PermissionDecision` | internet setting plus READ authorization |
| `can_internet_download` | URL, destination | `PermissionDecision` | read-only blocks; otherwise WRITE authorization |
| `can_execute_downloaded_file` | path | `PermissionDecision` | path checks plus separate EXECUTE authorization |

`PermissionDecision` has only `allowed` and `reason`. It does not expose an
approval ID, actor, session, scope, expiry, or correlation ID.

### `jarvis_core.security.SecurityManager`

| Method | Inputs | Output | Current semantic |
|---|---|---|---|
| `decision` | tool, risk/confirmation overrides, browser/mission context | string | `allow`, `confirm`, or `deny` |
| `create_confirmation` | tool, arguments, command, optional risk | opaque token | stores tool, arguments, command, risk, signature, timestamps, expiry |
| `consume` | token | stored mapping or `None` | removes token first; rejects missing/expired token |
| `prune` | none | `None` | removes expired pending tokens |

Rules can deny a tool before risk/confirmation handling. High/critical risk,
tool confirmation, and configured confirmation return `confirm`. The browser
and pre-save mission scopes are special allow paths.

## Semantic parity matrix

| Legacy behavior | Canonical equivalent | Parity | Migration action |
|---|---|---|---|
| Allow/deny path reads | Tool authorization/read scope | `SEMANTIC_MISMATCH` | Adapter must preserve path policy and reason |
| Protected project roots | Tool target/path policy | `LEGACY_UNIQUE` | Map explicitly before delegation |
| Permission modes `READ_ONLY`, `ASK`, `AUTO_SAFE`, `FULL` | Security decision plus approval | `SEMANTIC_MISMATCH` | Define mode translation; no direct replacement |
| Persistent task-scoped approval | Pending token and tool contract | `SEMANTIC_MISMATCH` | Contract must choose canonical lifetime/storage |
| One-time approval | Single-use token consumption | `CANONICAL_STRONGER` for token consumption | Keep explicit target/action binding in adapter |
| Critical action block | Risk `CRITICAL` confirmation/deny | `CANONICAL_STRONGER` when tool is registered | Keep root critical block until coverage is proven |
| Fixed app/folder/external-read allowlists | Tool-specific security requirements | `LEGACY_UNIQUE` | Preserve as compatibility policy or port deliberately |
| Unknown capability block | `capability_exists=False` block | `EXACT` | Characterization test is a gate |
| Approval target/action operation key | Token signature is recomputed and optional expected context is compared by `consume` | `ADAPTED` | Canonical binding for migrated scope; mismatch does not consume |
| Root JSONL audit | Canonical SQLite `AuditLog` | `SEMANTIC_MISMATCH` | Wave 3 field/event mapping |

Any remaining `LEGACY_UNIQUE` or `SEMANTIC_MISMATCH` row blocks direct
substitution outside the bounded Wave 2 scope. The characterization tests
remain a baseline for behavior that is not the desired final policy.

## Approval compatibility contract

The minimum future adapter envelope must carry:

```text
request_id, task_id/session_id, actor, operation, action, target,
risk, requested_scope, created_at, expires_at, consumed, decision,
correlation_id
```

Current facts:

- PermissionManager does not expose approval identity or expiry itself.
- ExecutionService persists `request_id`, `task_id`, operation key, action,
  target, status, scope, consumed, and timestamps in the root execution DB.
- ExecutionService has `ONCE` and `TASK` scopes, but no expiry field or expiry
  check in the observed repository.
- SecurityManager tokens have expiry and single-use removal, but no explicit
  user, mission, session, or task binding.
- SecurityManager recomputes its signature and validates changed target/action
  when caller context is supplied; tampered state is invalidated.

## Fail-closed characterization

| Condition | PermissionManager / ExecutionService | SecurityManager | Classification |
|---|---|---|---|
| Missing approval | Denies or returns `WAITING_APPROVAL` by mode | `consume` returns `None`; service confirmation is required | Fail closed |
| Invalid approval | No matching grant; new request or block | `None` | Fail closed |
| Expired approval | No native expiry field observed | `None` | Canonical fail closed; legacy expiry unknown/not applicable |
| Already consumed | One-time grant no longer matches | Token removed; `None` | Fail closed |
| Unknown action | Can create approval if capability exists; no action registry in service | Decision requires a Tool object | Legacy semantic gap |
| Target changed | Operation key changes for root approvals; canonical consume compares expected arguments | Mismatch is denied without consuming the original token | `ADAPTED` |
| Security component unavailable | Root service can still exist independently | Canonical callers should block; bridge has explicit fail-closed behavior | Contract required |
| Executor unavailable | ExecutionService only authorizes/records; dispatch is outside it | Tool service reports execution result | Responsibility boundary |

## Wave 2 gate

Wave 2 records the explicit adapter rule in
`JARVIS_B4_1_W2_APPROVAL_ADAPTER.md`; high-risk mismatches remain frozen for a
later wave.
