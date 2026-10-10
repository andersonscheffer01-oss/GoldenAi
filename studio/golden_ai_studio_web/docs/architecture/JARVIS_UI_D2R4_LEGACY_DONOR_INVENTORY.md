# UI-D2R4 legacy authority retirement inventory

Baseline: e125bd642b916d3c90bcb0dc2fe27bfd295f451f, main.
Legacy donor: C:\GoldenAI\jarvis. Canonical: studio/golden_ai_studio_web.
Retirement removes runtime authority, not source, capabilities or data.

| Capability | Classification | Future treatment |
|---|---|---|
| Independent auth/session/JWT | DUPLICATED_CANONICAL | Converge only through canonical security; preserve donor data |
| Direct Ollama chat routing | DUPLICATED_CANONICAL | ModelRouter remains the sole provider authority |
| Existing conversations/history | CAPABILITY_RECOVERY_REQUIRED | Separate data-governance gate before any migration |
| Device pairing and PC command queue | DUPLICATED_CANONICAL | Canonical identity, ToolRegistry, SecurityManager and TaskManager own execution |
| Bounded PC-agent command allowlist/confirmation patterns | CAPABILITY_RECOVERY_REQUIRED | Review reusable patterns without a second command authority |
| Independent SQLAlchemy audit | DUPLICATED_CANONICAL | Preserve records; canonical AuditLog owns new orchestration |
| PWA and mobile navigation patterns | REFERENCE_ONLY | Donor reference, not the Desktop acceptance target |
| Financial accounts, cards, receipts, installments, budgets, spending | DEFERRED | Isolated; no integration or data migration in this gate |
| Open Finance, bank connectors and financial alerts | DEFERRED | Isolated; no credentials requested or connectors created |
| Forceful stop fallback | REJECT | Never used by the retirement helper |

## Shutdown contract

`jarvis/scripts/graceful_retirement.py` uses Windows CTRL_C, handled by the
existing Uvicorn SIGINT lifecycle. No HTTP shutdown endpoint is introduced.
It checks process creation time, executable, exact command, working directory,
listener ownership, disabled autostart, absence of supervisor, and exclusive
console membership. A shared/missing console fails closed. Timeout never
escalates to forced termination. It requires a disposable helper process.

The isolated fixture uses the installed FastAPI/Uvicorn stack, no legacy app
imports, production DB, provider or hardware. Its lifecycle marker and Uvicorn
shutdown log establish cooperative exit. A test-only deadline prevents orphans.

The real legacy app cancels/awaits its alert task in lifespan finalization;
request sessions use their existing cleanup. No DB migration/disposal change
is injected into a running interpreter. The real shutdown log must separately
prove application shutdown completion; absence is not a successful proof.

Scheduled task quarantine is reversible (disable, never delete). The existing
manual launcher remains donor source; it must not be invoked to restart the
retired authority. No replacement scheduled task is created.
