# JARVIS B4.1 W3 - Audit Authority Convergence

Status: IMPLEMENTED / MIGRATED SCOPE ONLY

## Authority

`studio/golden_ai_studio_web/jarvis_core/audit.py::AuditLog` is the canonical
audit owner for the Wave 3 migrated scope:

- SecurityManager allow, deny, and approval decisions;
- approval creation, consumption, mismatch, expiry, stale-target, and invalid
  token outcomes;
- the safe-read compatibility bridge from `core.execution`;
- JarvisService tool result receipts that carry the same correlation context.

`core.audit.AuditLogger` remains present for compatibility and telemetry on
unmigrated paths. It is not authoritative for the migrated scope. No logger,
JSONL file, database, or historical record was deleted or migrated.

## Event envelope

The existing `jarvis_audit` SQLite schema is preserved. Wave 3 stores a
sanitized `_audit_envelope` inside the existing bounded `result` field and
projects it as `audit_envelope` from `AuditLog.recent()`.

The envelope carries:

```text
event_id, timestamp, request_id, correlation_id, session_id,
conversation_id, task_id, mission_id, run_id, approval_id, surface,
operation, action, target, tool, provider, model, risk, security_decision,
status, result, error, elapsed_ms, runtime_profile, metadata
```

The sanitizer is still applied recursively to arguments, result, error,
metadata, and target. Existing legacy fields `agent`, `files_changed`, and
`commands_executed` are retained only as sanitized metadata when provided.

## Emitter ownership

The path is deliberately bounded:

```text
request/task context
  -> SecurityManager decision or approval transition
  -> canonical AuditLog event
  -> compatibility facade / service result receipt
```

The `ExecutionSecurityFacade` owns no policy of its own. It forwards safe-read
decisions to SecurityManager with request/task/surface/target context. When its
canonical audit sink is present, `ExecutionService` does not add the old
authoritative `AuditLogger` decision/event pair.

TaskManager approval callers pass task/run/approval context through the existing
SecurityManager contract. JarvisService carries the command request context
through its existing execution call and binds approval consumption to the
subsequent result receipt.

## Sink classification

| Sink | Classification | Authority |
| --- | --- | --- |
| `jarvis_core.audit.AuditLog` / `jarvis_audit` | canonical audit | migrated Jarvis scope |
| `logs/audit_YYYY-MM-DD.jsonl` | legacy compatibility/telemetry | unmigrated core paths only |
| `data/market_ai_audit.jsonl` | market AI telemetry | not canonical audit |
| `data/trade_journal/*.jsonl` | trading history/telemetry | not canonical audit |
| `data/setup_database/setups.jsonl` | setup/runtime history | not canonical audit |
| `config/backtest_results/*.json` | backtest evidence/history | not canonical audit |
| unknown future JSON/JSONL sinks | unknown until classified | no authority inferred |

These sinks remain untouched in Wave 3.

## Boundary guarantees

Wave 3 does not change HTTP authentication, CORS, gateway authentication,
provider routing, model policy, trading, MT5, Strategy Tester, MQL5, Voice, or
database schema. No provider call or hardware action is part of the validation.
