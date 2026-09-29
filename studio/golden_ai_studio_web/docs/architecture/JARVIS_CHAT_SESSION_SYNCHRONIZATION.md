# Jarvis Chat Session Synchronization

## Default boundary

Main Chat and Market Chat have separate conversation ids by default. The
Market browser surface persists one opaque id in local storage and sends it on
each canonical request. The service stores both surfaces in its existing
conversation boundary, keyed by the supplied id; it does not merge histories
implicitly.

The canonical brain, model router, memory boundary, security manager and
AuditLog remain shared service authorities. A caller can explicitly provide
the same `conversation_id` to opt into continuity, which is the contract used
by a future “continue in Jarvis” action.

## Request metadata

Canonical contextual responses carry `surface`, `conversation_id`, provider,
model, routing metadata and a response/request id. Audit entries include the
surface, conversation id, request id, context timestamp and success/failure.
No credentials or provider secrets are persisted.

## History compatibility

Existing in-memory service conversation history is reused. The existing Market
AI JSONL evidence/history writer remains append-only for compatibility; this
gate does not migrate, delete or replace it with another memory store. The
JSONL record is enriched with context freshness/provenance and router identity
when Deep Analysis writes evidence.

## Known limitations

The direct REST handler preserves canonical service/security/audit ownership,
but the global HTTP layer still has a broader legacy perimeter than the
Gateway. This is recorded as a deployment/security follow-up, not hidden by
the Market contract. Timezone/DST session semantics and news deduplication are
also unchanged by this gate.
