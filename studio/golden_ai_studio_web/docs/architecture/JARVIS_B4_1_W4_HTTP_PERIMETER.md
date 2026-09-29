# JARVIS B4.1 Wave 4 - Authenticated HTTP Perimeter

Status: IMPLEMENTED / FOCUSED-VALIDATED
Baseline: `ad7d04e3bb41a844ebc8680f5ac5d33961f1905f`
Scope: HTTP inbound perimeter on `:8765`; no provider, MT5, trading, tester, MQL5, voice hardware, database migration, or device registry change.

## Authority and Request Order

The HTTP server and the existing Gateway now share the same `AuthManager`
instance. HTTP accepts only an `Authorization: Bearer <device-or-shared-token>`
credential. The token is never written to an audit row, response, frontend
source, or log. `SecurityManager` remains the sole authorization and approval
authority for actions after perimeter authentication.

```text
CLIENT
  -> HTTP perimeter identity (Bearer, shared Gateway AuthManager)
  -> route dispatch
  -> runtime-profile guard
  -> JarvisService / existing route authority
  -> ToolRegistry and SecurityManager where applicable
  -> capability/provider
  -> canonical AuditLog
```

Authentication is not authorization. A valid bearer on a high-risk route does
not execute an action without the existing SecurityManager decision and, when
required, approval token.

## Bind, Identity, and Lifecycle

| Field | Contract |
|---|---|
| HTTP bind | `LanConfig.bind_address`, default `127.0.0.1` |
| HTTP port | `8765` |
| Non-loopback | Opt-in only through existing LAN configuration; no bind change in Wave 4 |
| Auth mechanism | Shared Gateway `AuthManager`, Bearer header |
| Credential sources | `GOLDEN_GATEWAY_TOKEN`, existing config resolver, process-generated token, or device token after pairing |
| HTTP session | Stateless bearer requests; no second HTTP identity/session authority |
| Lifetime | Shared token follows Gateway lifecycle; device credential follows pairing authority |
| Rotation | Existing configured-token rotation or process restart for generated token |
| Revocation | Existing device-pairing revocation or shared-token replacement |
| Failure | Missing, malformed, invalid, expired/revoked credentials return `401` before dispatch |
| Rate limit | Reuses Gateway `AuthManager` failure accounting per source IP |

`localhost` is only a bind/origin boundary. It is not treated as identity.
The `web-ai-safe` runtime profile remains authoritative and is evaluated after
the perimeter; HTTP auth cannot re-enable disabled capabilities.

## Route Inventory

Static extraction from `GoldenAIHandler.route_api` found 139 API routes. The
perimeter classification is deterministic: 65 API routes are
`AUTHENTICATED`, 74 API routes are `AUTHENTICATED_AND_AUTHORIZED`, plus
`/stream/chat` in the latter class. `/health` is the only public local route.
`OPTIONS` is a public preflight operation and never dispatches a route.

Every API route is covered by the same rule. The exact paths are grouped below
only to keep this document readable; no unlisted API path is implicitly public.

### AUTHENTICATED

```text
/api/status
/api/security/status
/api/plugins/list
/api/capabilities
/api/models/catalog
/api/vision
/api/projects
/api/history
/api/quotes
/api/market/overview
/api/market/forex
/api/market/chart
/api/market/tick
/api/market/ai-context
/api/market/analyze
/api/market/analysis-history
/api/market/ai-performance
/api/market/opportunity-ranking
/api/desktop/status
/api/jarvis/voice/transcribe
/api/jarvis/voice/tts
/api/jarvis/voice/status
/api/jarvis/golden/overview
/api/jarvis/golden/radar
/api/jarvis/golden/scanner
/api/jarvis/golden/robots
/api/jarvis/golden/robot
/api/jarvis/golden/evidence
/api/jarvis/golden/risk
/api/jarvis/golden/validation
/api/jarvis/golden/deep-analysis
/api/jarvis/golden/recovery-manifest
/api/jarvis/memory/scientific
/api/jarvis/brain/status
/api/jarvis/vision/analyze
/api/jarvis/vision/status
/api/jarvis/memory/status
/api/jarvis/memory/search
/api/jarvis/memory/recent
/api/jarvis/tasks/list
/api/jarvis/tasks/get
/api/jarvis/orchestrator/status
/api/jarvis/skills/status
/api/jarvis/providers/status
/api/jarvis/readiness
/api/radar/status
/api/search
/api/system/disk
/api/system/stats
/api/chart_audit
/api/chart_data
/api/meta_strategy
/api/monitor/status
/api/monitor/history
/api/journal/stats
/api/journal/calibrate
/api/journal/history
/api/walk_forward
/api/statistics/full
/api/statistics/strategies
/api/statistics/assets
/api/statistics/hourly
/api/statistics/calibration
/api/rag/search
```

### AUTHENTICATED_AND_AUTHORIZED

```text
/api/chat
/api/jarvis/chat
/api/security/mode
/api/security/approve
/api/security/deny
/api/security/lockdown
/api/plugins/toggle
/api/models/key
/api/agent
/api/audio
/api/video
/api/document
/api/clear_history
/api/desktop/action
/api/desktop/confirm
/api/desktop/speech
/api/jarvis/voice/command
/api/jarvis/brain/execute
/api/jarvis/memory/remember
/api/jarvis/voice-service/status
/api/jarvis/voice-service/start
/api/jarvis/voice-service/listen
/api/jarvis/voice-service/stop
/api/jarvis/voice-service/speak
/api/jarvis/tasks/cancel
/api/filesystem
/api/system
/api/ea/generate
/api/mt5/status
/api/mt5/compile
/api/mt5/list_robots
/api/mt5/robot_details
/api/mt5/backtest
/api/strategy_catalog
/api/strategy_audit
/api/chart_strategy_test
/api/monitor/toggle
/api/strategy_matrix
/api/portfolio_backtest
/api/mt5/backtest_history
/api/mt5/compare
/api/mt5/analyze_robot
/api/mt5/real_backtest
/api/mt5/chart_analysis
/api/mt5/full_analysis
/api/scanner/scan
/api/scanner/radar
/api/scanner/performance
/api/scanner/details
/api/risk/status
/api/risk/calculate_lot
/api/risk/config
/api/risk/can_trade
/api/validation/full
/api/validation/monte_carlo
/api/validation/robustness
/api/validation/compare_modes
/api/validation/real
/api/validation/all_real
/api/mt5/import_history
/api/mt5/auto_trade
/api/mt5/positions
/api/mt5/close_position
/api/position/status
/api/position/start
/api/position/stop
/api/position/config
/api/position/log
/api/position/simulate
/api/strategy_manager/list
/api/strategy_manager/toggle
/api/strategy_manager/toggle_mode
/api/strategy_manager/preset
/api/strategy_manager/auto_rank
/api/rag/index
/stream/chat
```

The high-risk class is a required downstream authorization boundary, not an
automatic permission grant. Existing route-specific `_authorize_api_mutation`
and JarvisService/SecurityManager decisions remain in force.

### Public, disabled, and unknown

| Class | Paths | Result |
|---|---|---|
| `PUBLIC_LOCAL` | `GET /health`, `OPTIONS` | Allowlisted; no route action on OPTIONS |
| `DISABLED/FROZEN` | None introduced by the perimeter | Runtime profile still can disable capabilities |
| `UNKNOWN` | None among the 139 extracted API routes | Unknown paths authenticate first, then return `404` |
| Static assets | HTML/JS/CSS/images | Served so the UI can bootstrap; API and stream calls remain protected |

## CORS, Errors, and Correlation

Wildcard CORS was removed from HTTP `8765`. The existing origin allowlist is
reused, with `Vary: Origin`, and accepted request headers are `Content-Type`,
`Authorization`, `X-Request-ID`, and `X-Correlation-ID`. Disallowed origins do
not receive an allow-origin header. `OPTIONS` returns preflight metadata only
and never reads a body or executes an action.

Missing, malformed, invalid, and revoked/expired credentials return `401`.
An authenticated request that fails the existing SecurityManager or approval
boundary remains a denial from that authority; the perimeter does not convert
it into an allow. Unknown authenticated paths return `404`.

The perimeter creates bounded `request_id` and `correlation_id` values, carries
them into the reserved `_http_context` route envelope, and records
`AUTH_SUCCESS`, `AUTH_FAILURE`, `AUTH_MALFORMED`, `AUTH_MISSING`, and public
route observations in the canonical `AuditLog`. Token material is redacted by
existing AuditLog sanitization and is never used as an actor label.

Canonical Market Chat and Deep Analysis pass the envelope into their existing
JarvisService `generate_response` audit context. Main Chat and legacy routes
retain their existing internal request/approval behavior while the perimeter
event provides the inbound correlation receipt.

## Compatibility

- `jarvis_ui` keeps the existing Gateway WebSocket `hello -> auth` handshake.
- Gateway and HTTP use the same `AuthManager`; no second identity system was added.
- `gateway-adapter.js` attaches the existing device token to its HTTP helper.
- Dashboard, Radar Macro, and Studio use a same-origin client that reads only
  the existing paired `localStorage` device token; no static secret exists.
- Main Chat, Market Chat, Deep Analysis, Golden read models, legacy chat, and
  SSE remain on their existing routes and provider/brain paths.
- No `market.html` visual redesign was made.

## Safety Boundary

Wave 4 made no provider call, MT5 connection, order/trading call, Strategy
Tester execution, MQL5 compile, voice initialization, microphone/speaker test,
database migration, device registry edit, or broker mutation.
