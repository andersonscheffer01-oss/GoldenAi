# JARVIS B4.1A - HTTP Perimeter Matrix

Status: WAVE 4 IMPLEMENTED / FOCUSED-VALIDATED
Baseline: `ad7d04e3bb41a844ebc8680f5ac5d33961f1905f`

## Evidence boundary

This matrix records source-visible routes and call paths. Wave 4 adds an
explicit inbound perimeter before route execution; it does not claim a route
is safe merely because it is authenticated. No HTTP server, provider, MT5, or
browser action was executed for this focused validation.

## Current perimeter observations

`server_agent.py` dispatches `do_GET` and `do_POST` requests through the
shared `HttpPerimeter` before `handle_api`, `handle_stream`, and `route_api`.
`do_OPTIONS` is preflight-only and advertises `GET, POST, OPTIONS` plus the
bounded identity/correlation headers. CORS is origin-bound through the
existing Gateway allowlist; wildcard CORS is no longer emitted.

The Wave 4 path now validates `Authorization: Bearer` with the same
`AuthManager` used by Gateway `:8766/ws`. Provider authorization headers are
not used as inbound identity. Therefore:

```text
HTTP_AUTH_CURRENT_STATE = EXPLICIT_SHARED_GATE
HTTP_AUTH_TARGET_STATE = explicit inbound auth before route execution
```

The target is implemented for the extracted API and SSE routes.

## Wave 4 measured state

| Metric | Result |
|---|---|
| Extracted API routes | 139 |
| `AUTHENTICATED` API routes | 65 |
| `AUTHENTICATED_AND_AUTHORIZED` API routes | 74 |
| Additional protected stream | `/stream/chat` |
| Public local route | `GET /health` |
| Public preflight | `OPTIONS` only; no dispatch |
| Unknown API route | Authenticated first, then `404` |
| Bind | Existing `LanConfig.bind_address`, default `127.0.0.1:8765` |
| Identity authority | Shared Gateway `AuthManager` |

## Route classes

| Route family | Current reachability evidence | Current authority observation | Target class |
|---|---|---|---|
| `/api/jarvis/golden/*` overview, radar, scanner, robots, evidence, risk, validation, deep analysis, recovery | Route map and B3 UI/API integration | Canonical read-model path, perimeter still not proven | Authenticated read |
| `/api/jarvis/chat`, `/api/market/analyze` | Route map and current UI usage | Canonical-ish Jarvis path; verify context and audit at runtime later | Authenticated read / model action |
| `/api/jarvis/memory/*`, `/api/jarvis/tasks/*` | Route map and Jarvis modules | Canonical service boundary appears present; complete HTTP auth coverage unknown | Authenticated read or mutation |
| `/api/chat`, `/api/agent` | Legacy route map and legacy callers | Direct/legacy path; provider and security authority vary | Freeze then delegate |
| `/stream/chat` and `text/event-stream` paths | Source streaming handler and legacy chat flow | Direct legacy provider/stream path observed | Freeze then delegate |
| `/api/audio`, `/api/video`, `/api/document` | Legacy route map | Root tool path; inbound auth coverage not proven | Authenticated mutation/tool action |
| `/api/desktop/action`, `/confirm`, `/speech` | Desktop route map | High side-effect surface; root authorization varies by action | Explicit approval |
| `/api/mt5/status`, `/positions` | MT5 route map | Read calls exist; shared perimeter not proven | Authenticated read |
| `/api/mt5/compile`, `/backtest`, `/real_backtest` | MT5 route map and handler bodies | `_authorize_api_mutation` uses root ExecutionService | Explicit approval |
| `/api/mt5/auto_trade`, `/close_position` | MT5 route map and handler bodies | Dangerous legacy trading routes remain reachable | Explicit approval and freeze |
| `/api/mt5/import_history` | Route map | Data mutation/import risk requires characterization | Explicit approval |
| `/api/strategy_*`, `/api/scanner/*`, `/api/risk/*`, `/api/validation/*` | Route map | Mixed legacy and read-model ownership | Classify per endpoint before migration |
| `/api/position/*`, `/api/monitor/*`, `/api/ea/generate` | Route map | Reachability and caller ownership not fully proven | Unknown until characterized |
| Health/static endpoints | Server/static route behavior | Candidate local public surface only | Narrow public allowlist |

`ACTIVE_CURRENT_UI` means a current B3 UI caller or canonical integration was
seen. `ACTIVE_LEGACY_UI` means a legacy frontend or server route is present.
`ACTIVE_EXTERNAL_API` means source route exposure exists without a current UI
caller. `UNKNOWN` means reachability or caller evidence is incomplete. A route
is not classified as dead from absence of a current UI reference.

## WebSocket and SSE

Wave 1 static characterization refined the earlier WebSocket unknown. The
canonical UI Gateway adapter derives `ws://` or `wss://` to `:8766/ws`, sends a
`hello` message, and then sends an `auth` message with a device token. The
server startup path also starts the Gateway on port 8766. Therefore:

```text
WEBSOCKET_STATUS = DYNAMIC/EXISTS
WEBSOCKET_AUTH = device-token handshake observed
```

This is a separate Gateway perimeter, not proof that the HTTP 8765 API has the
same auth coverage. SSE-like behavior is present in `/stream/chat` and
`text/event-stream` handling. Its current direct-provider and legacy chat
ownership must be delegated or frozen before perimeter relaxation.

## Authentication and compatibility matrix

| Surface | Current inbound auth proof | Target requirement | Compatibility risk |
|---|---|---|---|
| Local health | Narrow route-specific behavior only | Public only if explicitly allowlisted | Low if isolated |
| Jarvis Web read | No universal gate proven | Session/client identity plus read scope | Existing UI fetches may need headers |
| Jarvis Web mutation | Root execution helper only on some routes | Inbound auth plus SecurityManager and approval | Medium/high |
| Jarvis Desktop | Mixed route and root execution behavior | Same decision contract with Desktop adapter | Existing startup and cached UI assumptions |
| Legacy browser/UI | Mixed or absent | Freeze, redirect, or compatibility token boundary | High |
| Streaming | No shared HTTP inbound gate proven; Gateway WS uses device-token handshake | Auth before stream creation and per-stream correlation | High |

## Target request envelope

The future perimeter should normalize, before route execution:

```text
request_id
session_id
actor_id
client_surface
route
operation
target
requested_side_effect
correlation_id
```

The envelope is a design requirement only. It must be mapped to existing
Desktop and Web contracts before implementation. Missing or invalid identity
must fail closed for mutations and dangerous reads.

## Required future checks

- characterize every route family with source caller and side-effect class;
- distinguish local-only from network-exposed deployment assumptions;
- define CORS and origin policy before changing frontend behavior;
- preserve health/static availability only through an explicit allowlist;
- require canonical audit correlation for accepted, denied, and failed calls;
- test legacy Desktop startup and Web dashboard compatibility in a separate
  authorized gate;
- stop if an endpoint's authority or reachability remains unknown.
