# JARVIS B4.1 W1 - Reachability Characterization

Status: STATIC / CHARACTERIZATION_ONLY
Baseline: `c033b61dbbe684ee0943854e650f471bfd87a31b`

No endpoint, provider, Gateway, MT5 component, or browser was invoked. This
map uses source references in Python, HTML, and JavaScript only.

## Current and legacy UI callers

| Route family | Caller evidence | Classification |
|---|---|---|
| `/api/jarvis/chat` | `dashboard.html`, `desktop_center.js`, `server_agent.py` | `ACTIVE_CURRENT_UI` |
| `/api/jarvis/golden/*` | `jarvis_ui/src/app.js` and route map | `ACTIVE_CURRENT_UI` |
| `/api/market/analyze` | `ai_radar.js` and route map | `ACTIVE_CURRENT_UI` |
| `/api/chat` | `studio_v7.html` | `ACTIVE_LEGACY_UI` |
| `/api/agent` | `studio_v7.html` | `ACTIVE_LEGACY_UI` |
| `/stream/chat` | `studio_v7.html`, `server_agent.py` | `ACTIVE_LEGACY_UI` |
| `/api/mt5/*` trading/control routes | `dashboard.html` and route map | `ACTIVE_CURRENT_UI` plus legacy backend behavior |
| `/api/market/*` legacy market pages | `market.js`, `ai_radar.js` | `ACTIVE_CURRENT_UI` |
| `/api/desktop/*` | Desktop/operational source references | `ACTIVE_INTERNAL` or `UNKNOWN` per endpoint |
| unreferenced route-map entries | server route map only | `EXTERNALLY_REACHABLE` or `UNKNOWN`, not dead |

The current UI evidence is sufficient to block removal of the canonical chat,
Golden read, market analysis, and dashboard trading route families.

## HTTP perimeter

`server_agent.py` uses `do_GET`/`do_POST` -> `handle_api` -> `route_api` for
the HTTP API. `do_OPTIONS` allows `GET, POST, OPTIONS` and `Content-Type` and
responds with `Access-Control-Allow-Origin: *`. The inspected HTTP path has no
shared inbound Authorization validation before route execution.

The separate Gateway path is different: the UI adapter derives `ws://` or
`wss://` to `:8766/ws`, sends `hello`, then sends an `auth` message with a
device token. `server_agent.py` starts the Gateway on port 8766. Therefore the
previous B4.1A `WebSocket = UNKNOWN` finding is refined to:

```text
WEBSOCKET_STATUS = DYNAMIC/EXISTS
WEBSOCKET_AUTH = device-token handshake observed in the client protocol
HTTP_8765_AUTH = NOT_OBSERVED in the shared server_agent perimeter
```

This does not prove identical authorization semantics between the Gateway and
HTTP 8765; they remain two perimeter contracts to reconcile.

## SSE characterization

`/stream/chat` is an HTTP streaming path with `text/event-stream`. Its caller
is the legacy `studio_v7.html`; its server handler can select direct provider
branches including Ollama and external provider helpers. No shared inbound
auth gate or canonical AuditLog correlation was proven at stream creation.
Disconnect handling is present in the HTTP handler, but provider cancellation,
partial response audit, and reconnect semantics require a later mock test.

## Trading route reachability

| Route class | Current classification | Evidence |
|---|---|---|
| compile | `UI_REFERENCED` | `studio_v7.html`; handler invokes compile path |
| backtest/real_backtest | `UI_REFERENCED` | `dashboard.html` and legacy dashboard |
| auto_trade | `UI_REFERENCED` | `dashboard.html` buttons and handlers |
| close_position | `UI_REFERENCED` | `dashboard.html` |
| positions | `UI_REFERENCED` | `dashboard.html` |
| import_history | `UI_REFERENCED` | `dashboard.html` |
| position manager controls | `UI_REFERENCED` | `dashboard.html` |
| route-only MT5/EA handlers | `API_ONLY` or `UNKNOWN` | server route map without complete caller proof |

This is reachability only. No endpoint was called and no MT5 interaction
occurred.

## Provider bypass reachability

| Provider/path | Current evidence | Classification | Special behavior |
|---|---|---|---|
| Ollama | legacy stream/chat branches and `ollama_chat` | `ACTIVE_LEGACY_UI` | streaming and local chat history branches |
| Gemini | `call_gemini_model` and stream model selection | `ACTIVE_LEGACY_UI`/external | model selection, image capability, streaming path |
| Groq | `call_groq_model` and fallback branches | `ACTIVE_LEGACY_UI`/external | fallback and health probe paths |
| Claude/OpenRouter | provider adapters and stream/fallback branches | `ACTIVE_LEGACY_UI`/external | transformed messages and streaming |
| Cline | legacy provider branches and tool helpers | `ACTIVE_LEGACY_UI`/external | model mapping and key-dependent branch |
| ModelRouter | Jarvis orchestrator path | `ACTIVE_CURRENT_UI` for canonical flows | canonical target, policy still future scope |

Provider presence in source is not proof that credentials or a network call
occurred.

## Memory and task authority

The current server memory route calls `DESKTOP_CENTER.service._memory_remember`,
which calls `CanonicalMemoryBoundary.remember`. The boundary uses V2 as the
single writer when available and retains legacy as an explicit compatibility
fallback. Internal V2/project/research writers are visible, but complete
runtime reachability of every writer is not proven without running the service.

```text
MEMORY_PARALLEL_ACTIVE = UNKNOWN
```

The current task routes call `service.task_manager`; `TaskManager` owns the
canonical `jarvis/golden_tasks.db` resolution. Static source also contains
test/compatibility path options and multiple historical runtime DB artifacts,
but no current route was proven to write tasks outside TaskManager.

```text
TASK_PARALLEL_ACTIVE = UNKNOWN
```

Unknown is retained deliberately rather than claiming `NO` from incomplete
static reachability.
## Unreferenced and unknown routes

No route is marked dead solely because no current UI caller was found. The
following remain `UNREFERENCED` or `UNKNOWN` until a deployment/caller
inventory resolves them: portions of strategy/risk/validation legacy APIs,
position/monitor controls, EA generation, old dashboard snapshots, and
external clients not represented in the repository.
