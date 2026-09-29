# JARVIS B4.1 W1 - Audit Parity

Status: CHARACTERIZATION_ONLY / no audit adapter implemented
Baseline: `c033b61dbbe684ee0943854e650f471bfd87a31b`

## Current schemas

### `core.audit.AuditLogger`

Storage is daily JSONL under `logs/audit_YYYY-MM-DD.jsonl`. `AuditEvent` and
the dictionary recorder expose:

```text
action_type, status, target, action_id, session_id, agent,
input_summary, result, error, duration_ms, files_changed,
commands_executed, timestamp
```

The logger supplies `timestamp` and `action_id` defaults. The observed logger
does not sanitize sensitive values before serialization. W1 tests use only a
harmless fixture marker in temporary storage and do not write the historical
audit directory.

### `jarvis_core.audit.AuditLog`

Storage is SQLite table `jarvis_audit` with:

```text
id, timestamp, task_id, command, tool, arguments, risk,
status, result, elapsed_ms
```

The canonical logger sanitizes sensitive keys and payload-like values before
JSON serialization. `recent(limit)` returns bounded rows ordered by descending
database ID.

## Audit field parity matrix

| Legacy field/event | Canonical field/event | Classification | Wave 3 requirement |
|---|---|---|---|
| `action_type` | `command` plus normalized event type | `MISSING_CANONICAL_MAPPING` | Preserve original action type as sanitized metadata |
| `status` | `status` | `CANONICAL_EQUIVALENT` | Define one status vocabulary |
| `target` | `arguments` or command target metadata | `MISSING_CANONICAL_MAPPING` | Add normalized target field or metadata contract |
| `action_id` | `id` | `SEMANTIC_MISMATCH` | Link IDs; do not equate integer row ID with UUID action ID |
| `session_id` | `task_id` only in current schema | `MISSING_CANONICAL_MAPPING` | Carry session/correlation metadata |
| `agent` | `tool`/`command` metadata | `LEGACY_ONLY` | Preserve source actor as sanitized metadata |
| `input_summary` | `command`/arguments | `MISSING_CANONICAL_MAPPING` | Define summary truncation |
| `result` | `result` | `CANONICAL_EQUIVALENT` | Preserve bounded serialization |
| `error` | status/result | `MISSING_CANONICAL_MAPPING` | Separate error field or structured result |
| `duration_ms` | `elapsed_ms` | `CANONICAL_EQUIVALENT` | Normalize integer units |
| `files_changed` | no dedicated column | `LEGACY_ONLY` | Keep as sanitized metadata if needed |
| `commands_executed` | `command` | `MISSING_CANONICAL_MAPPING` | Do not serialize arbitrary command history as secrets |
| `timestamp` | `timestamp` | `CANONICAL_EQUIVALENT` | Normalize timezone and precision |
| approval requested/granted/denied | status/tool/task metadata | `MISSING_CANONICAL_MAPPING` | Add approval ID, scope, decision and correlation |
| redaction | `_sanitize` | `CANONICAL_STRONGER` | Canonical sanitizer remains authoritative |

## Required Wave 3 event envelope

```text
event_id, correlation_id, request_id, session_id, task_id,
actor, source_authority, operation, action, target, risk,
approval_id, approval_scope, status, result, error,
started_at, completed_at, elapsed_ms, sanitized_metadata
```

This is a design target only. W1 does not add columns, migrate records, or
write a dual log.

## Correlation characterization

| ID | Current creation/owner evidence | Audit presence | Loss point |
|---|---|---|---|
| `request_id` | root approval request; also API/request flows in server | root approval rows; not universal in AuditLog | route-to-audit mapping |
| `response_id` | not proven in canonical AuditLog | absent | response serialization |
| `correlation_id` | not proven in the two logger schemas | absent from both canonical logger schemas | inbound perimeter |
| `session_id` | server/chat and root event model | root logger field; absent canonical column | Jarvis AuditLog adapter |
| `conversation_id` | market/main chat payloads | not a logger field | chat-to-audit propagation |
| `approval_id` | root `request_id` or canonical token-derived compatibility ID | not a dedicated AuditLog column | approval-to-result mapping |
| `task_id` | ExecutionService, Jarvis TaskManager | canonical `task_id` and root approval/event rows | cross-system normalization |
| `mission_id` | Computer Use mission paths | not a dedicated logger column | mission-to-tool event |
| `run_id` | background/test/mission paths | not universal | task/run projection |

The first convergence wave must not introduce a competing ID scheme. It should
only prove where existing IDs are created, propagated, and dropped.
