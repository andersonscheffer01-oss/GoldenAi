# Jarvis Gateway V1

Minimal secure WebSocket transport for Jarvis.

## Architecture

```
Client → Gateway → Authentication → Session → JarvisService
```

Gateway is **TRANSPORT ONLY** — never executes tools directly.

```
jarvis_core/gateway/
├── __init__.py      # Package exports
├── protocol.py      # Typed JSON message envelope (V1)
├── auth.py          # Token-based authentication
├── sessions.py      # Session lifecycle management
└── gateway.py       # WebSocket server (aiohttp)
```

## Quick Start

```python
from jarvis_core.gateway import Gateway
from jarvis_core.service import JarvisService
from pathlib import Path

service = JarvisService(Path(r"C:\GoldenAI\studio\golden_ai_studio_web"))
gateway = Gateway(service, host="127.0.0.1", port=8766)

import asyncio
asyncio.run(gateway.start())
```

## Protocol V1

All messages are JSON with this envelope:

```json
{
  "version": 1,
  "id": "<unique_request_id>",
  "type": "<message_type>",
  "timestamp": "<ISO-8601>",
  "session_id": "<optional>",
  "payload": {...}
}
```

### Message Types

| Type | Direction | Auth Required | Description |
|------|-----------|---------------|-------------|
| `hello` | C→S | No | Initial handshake |
| `auth` | C→S | No | Authenticate with token |
| `auth_ok` | S→C | - | Authentication successful |
| `auth_error` | S→C | - | Authentication failed |
| `ping` | C→S | No | Keepalive |
| `pong` | S→C | - | Keepalive response |
| `command` | C→S | Yes | Execute a Jarvis command |
| `command_ack` | S→C | - | Command received |
| `command_result` | S→C | - | Command completed |
| `command_error` | S→C | - | Command failed |
| `confirmation_required` | S→C | - | SecurityManager needs confirmation |
| `confirmation_response` | C→S | Yes | User confirmed action |
| `session_open` | C→S | Yes | Create new session |
| `session_resume` | C→S | Yes | Resume existing session |
| `session_close` | C→S | Yes | Close session |
| `session_info` | S→C | - | Session status |
| `event` | S→C | - | Asynchronous event |
| `status` | S→C | - | Server status |
| `health` | S→C | - | Health information |
| `error` | S→C | - | Structured error |

## Authentication

Token resolution order:
1. Environment variable `GOLDEN_GATEWAY_TOKEN`
2. `config/api_keys.json["gateway_token"]`
3. Auto-generated token (logged at startup)

Rate limiting: 10 failures per source IP per 5-minute window.

## Sessions

- `session_id`: Cryptographically random (24 bytes URL-safe)
- TTL: 1 hour
- Sweep: Every 60 seconds
- Resume requires valid session_id + authentication
- No session fixation

## Security Boundaries

- Gateway binds to `127.0.0.1` only (no LAN/Internet)
- All commands route through `JarvisService.execute_command()`
- SecurityManager remains the authority for all tool execution
- ToolRegistry remains the authority for tool registration
- AuditLog remains the authority for logging
- Gateway has NO direct access to MT5, Golden, filesystem, or Windows tools
- Error messages never leak tracebacks, paths, or secrets

## Confirmation Flow

1. Client sends `command`
2. Gateway sends `command_ack`
3. If SecurityManager requires confirmation:
   - Gateway sends `confirmation_required` with token
   - Client shows confirmation to user
   - Client sends `confirmation_response` with token
   - Gateway routes through `JarvisService.confirm()`
4. Gateway sends `command_result` or `command_error`

## Keepalive

- Server sends heartbeat every 30 seconds
- Client should respond with `ping`/`pong`
- Stale sessions expire after 1 hour

## Dependencies

- `aiohttp` (already installed)
- No new dependencies required

## Default Configuration

- Host: `127.0.0.1`
- Port: `8766`
- Max payload: 1 MB
- Session TTL: 1 hour
- Auth failure limit: 10 per 5 minutes

## Future Phases

- LAN exposure (requires device pairing/auth)
- PWA integration
- iPhone app
- File transfer
- Screen streaming
- Voice
- Push notifications
