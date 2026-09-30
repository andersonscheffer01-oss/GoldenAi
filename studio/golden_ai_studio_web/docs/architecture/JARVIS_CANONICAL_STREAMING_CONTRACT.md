# JARVIS Canonical Streaming Contract

## Authority

`/stream/chat -> JarvisService.stream_response -> Brain.stream_response -> ModelRouter.stream -> ProviderAdapter`

The HTTP handler owns only authentication, SSE framing, disconnect detection,
and compatibility field names. It does not select a provider, call a provider,
construct a second prompt, execute tools, or write conversation history.

## Internal event contract

| Type | Required fields | Meaning |
|---|---|---|
| `provider_selected` | `provider`, `model`, `fallback_used` | Router selected an adapter; no token content |
| `chunk` | `text`, `provider`, `model` | Normalized user-visible text |
| `done` | `provider`, `model`, `elapsed_ms`, `fallback_used` | Complete stream; service finalizes conversation history |
| `error` | `error`, `before_first_chunk` or `after_first_chunk` | Explicit failure; no fallback after partial output |
| `cancelled` | `cancelled`, `provider` when known | Cooperative cancellation; no partial history finalization |

Request context carries `request_id`, `correlation_id`, `conversation_id`,
`session_id`, `surface`, and runtime profile through the service/audit boundary.
Provider/model telemetry is recorded without prompt or token content.

## SSE compatibility

- Content type: `text/event-stream`.
- Each frame remains `data: <JSON>\n\n`.
- Text frames preserve `{"token": "...", "done": false}`.
- Completion preserves `{"done": true, "full_response": "..."}`.
- Provider selection is an additional non-content `stream_event` frame.
- Errors are explicit `{"error": "...", "done": true}`.
- No heartbeat was added; disconnect is treated as cancellation.

## Fallback and memory

Fallback is allowed only before the first user-visible chunk. A provider error
after partial output is terminal and is not concatenated with a second provider.
The assistant turn is recorded only after `done`; cancelled or failed partial
streams are not committed as conversation history.

## Security and audit

HTTP auth occurs before the stream opens. Streaming is a no-tool response path;
actions must use `JarvisService.execute_tool` and the normal SecurityManager
approval path. Lifecycle events are emitted through canonical `AuditLog`:

`STREAM_REQUEST`, `STREAM_STARTED`, `STREAM_PROVIDER_SELECTED`,
`STREAM_FIRST_CHUNK`, `STREAM_COMPLETED`, `STREAM_CANCELLED`, `STREAM_FAILED`.

No direct provider branch remains in the active handler. No provider policy or
priority order was changed by this contract.
