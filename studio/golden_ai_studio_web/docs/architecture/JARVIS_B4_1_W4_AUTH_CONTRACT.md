# JARVIS B4.1 Wave 4 - HTTP Authentication Contract

## Credential Contract

HTTP callers use:

```http
Authorization: Bearer <existing Gateway shared or device token>
X-Request-ID: <bounded optional caller id>
X-Correlation-ID: <bounded optional caller correlation>
```

Only the existing Gateway `AuthManager` validates the credential. It compares
the shared token in constant time and, when the existing pairing service is
connected, accepts the existing device token. HTTP does not create a second
secret, token namespace, user store, or permission model.

The browser client reads `jarvis_device_token` (with the existing legacy key
migration already supported by GatewayAdapter) from its same-origin storage.
Desktop identity injection remains the existing source of that device token.
No token is embedded in HTML/JS, placed in a URL, copied into a response, or
written to logs/audit payloads.

## Lifecycle

| Event | Behavior |
|---|---|
| Creation | Existing Gateway config/env token or process-generated shared token; device token from existing pairing |
| Storage | Existing Gateway resolver/device-pairing storage; browser only retains the already-issued device token |
| HTTP lifetime | Stateless per-request Bearer validation; no parallel cookie/session authority |
| Rotation | Existing configured Gateway token replacement or process restart for generated token |
| Revocation | Existing device-pairing revocation or shared-token replacement |
| Expiration | Opaque expired/revoked credentials fail the same closed `401` path as invalid credentials |
| Rate limit | Existing AuthManager source-IP failure window |
| Logging | Status and bounded actor label only; token and token hash are excluded |

## Decision Order

```text
minimum parse
  -> OPTIONS/origin handling
  -> bearer authentication
  -> route dispatch
  -> RuntimeProfile.api_disabled_reason
  -> existing SecurityManager / approval boundary
  -> existing capability/provider
  -> canonical AuditLog
```

`401` means no valid inbound identity. `403` is reserved for origin policy or
an authenticated operation denied by the existing authorization boundary.
Successful HTTP identity never implies SecurityManager approval.

## Failure and Streaming Rules

- Missing `Authorization` -> `401 AUTH_MISSING`.
- Non-Bearer, empty, or whitespace-padded Bearer value -> `401 AUTH_MALFORMED`.
- Invalid, expired, or revoked opaque credential -> `401 AUTH_INVALID`.
- Valid identity plus dangerous operation without approval -> no executor call;
  the existing SecurityManager returns denial/approval-required.
- `OPTIONS` returns preflight metadata and never dispatches or executes.
- `/stream/chat` authenticates before reading the body or opening SSE.
- The stream keeps `text/event-stream`, no-cache, and close semantics.

## CORS Contract

The existing Gateway CORS allowlist is reused for HTTP `8765`. Origin-bound
headers replace the former wildcard. Allowed request headers are
`Content-Type`, `Authorization`, `X-Request-ID`, and `X-Correlation-ID`.
Disallowed origins receive no wildcard fallback. No Windows firewall, bind,
SSL, or LAN setting is changed by this contract.

## Audit and Provenance

The canonical `AuditLog` receives perimeter events with route, method, class,
request/correlation ids, runtime-independent actor label, result status, and
bounded source IP metadata. Sensitive field sanitization remains the canonical
implementation. Canonical Market Chat and Deep Analysis also pass the inbound
context to their existing JarvisService audit envelope.

## Non-Goals

This contract does not change ModelRouter/provider selection, canonical Brain,
JarvisService, ToolRegistry, SecurityManager policy, MT5 behavior, trading,
Strategy Tester, MQL5, voice hardware, databases, or device registry.
