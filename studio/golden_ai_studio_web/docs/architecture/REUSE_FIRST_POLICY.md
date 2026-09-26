# Jarvis Reuse-First Policy

Status: proposal created by Donor Audit 1A. Runtime behavior unchanged.

## Policy

Golden/JARVIS keeps ownership of the control plane. Donor projects may inform
design, tests, and terminology, but no donor component enters the runtime until
it has a Jarvis-owned contract, security decision, provenance record, license
review, and regression coverage.

## Required Order

1. Reuse an existing Golden boundary when it already provides the behavior.
2. Adapt a donor pattern behind a narrow Golden interface when it removes real
   duplication without changing ownership.
3. Reimplement a pattern when the donor trust model or lifecycle is not safe to
   import.
4. Port code only after file-level license, dependency, and security review.
5. Reject anything that creates a competing core, scheduler, memory store,
   credential resolver, or authorization path.

## Non-Negotiable Owners

- `SecurityManager` owns permission, confirmation, and denial.
- `AuditLog` owns security-relevant runtime records and redaction.
- `ToolRegistry` owns tool registration and model-visible schemas.
- `TaskDatabase` and `BackgroundTaskScheduler` own durable background work.
- `ModelRouter` owns provider selection and classification policy.
- Mission and browser modules own Computer Use and browser provenance.

Skill, MCP, and plugin code must be treated as untrusted extension input until
validated. Manifest permissions are upper bounds, not grants. Tool discovery or
tool-search filtering is never authorization. Remote installation and automatic
updates are disabled unless a later phase explicitly implements provenance,
pinning, approval, rollback, and audit gates.

## Minimum Extension Gate

`discover -> validate manifest -> verify source/revision/license -> resolve
dependencies -> SecurityManager decision -> ToolRegistry registration ->
audited invocation -> isolated teardown`.

An extension must not create a second scheduler, Gateway, WebSocket/control
plane, memory store, provider policy, or secret store. An uncertain write must
fail closed and must not be replayed. Public read-only operations may be
optimized, but their scope and provenance remain explicit.
