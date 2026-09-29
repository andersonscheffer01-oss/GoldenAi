"""Gateway WebSocket V1 — Minimal secure WebSocket transport for Jarvis.

ARCHITECTURE:
  Client → WebSocket Gateway → Authentication → Session → JarvisService

Gateway is TRANSPORT ONLY.
Gateway does NOT:
  - Execute tools directly
  - Access MT5 directly
  - Access Golden directly
  - Access filesystem directly
  - Have its own SecurityManager
  - Have its own ToolRegistry
  - Decide permissions
  - Execute commands without authentication
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Set

from aiohttp import web

from .protocol import (
    GatewayMessage, MessageType, REQUIRES_AUTH, ALWAYS_ALLOWED,
    MAX_PAYLOAD_BYTES, PROTOCOL_VERSION, make_error_reply,
)
from .auth import AuthManager, AuthState
from .sessions import SessionManager, Session
from .cors import (
    is_cors_allowed_origin, build_cors_headers, cors_preflight_response,
    add_cors_to_response, CORSConfig,
)

logger = logging.getLogger("jarvis.gateway")

# Connection tracking
_active_connections: Set[web.WebSocketResponse] = set()

# Idempotency constants
_IDEMPOTENCY_MAX_ENTRIES = 1024
_IDEMPOTENCY_TTL = 3600  # 1 hour


class IdempotencyCache:
    """Bounded per-session idempotency cache.

    Tracks (session_id, request_id) → result to prevent duplicate execution.
    Thread-safe. Bounded size. TTL-based expiry.
    """

    def __init__(self, max_entries: int = _IDEMPOTENCY_MAX_ENTRIES,
                 ttl: float = _IDEMPOTENCY_TTL):
        self._max_entries = max_entries
        self._ttl = ttl
        # Key: (session_id, request_id) → (result, timestamp)
        self._cache: collections.OrderedDict = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, session_id: str, request_id: str) -> Optional[Any]:
        """Return cached result if exists and not expired. None = not found."""
        key = (session_id, request_id)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            result, ts = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                return None
            return result

    def store(self, session_id: str, request_id: str, result: Any) -> None:
        """Store result for idempotency protection."""
        key = (session_id, request_id)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (result, time.time())
            # Evict oldest if over limit
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def clear_session(self, session_id: str) -> int:
        """Remove all entries for a session. Returns count removed."""
        prefix = session_id
        removed = 0
        with self._lock:
            keys_to_delete = [k for k in self._cache if k[0] == prefix]
            for k in keys_to_delete:
                del self._cache[k]
                removed += 1
        return removed

    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def sweep_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        removed = 0
        with self._lock:
            expired = [k for k, (_, ts) in self._cache.items()
                       if now - ts > self._ttl]
            for k in expired:
                del self._cache[k]
                removed += 1
        return removed


class Gateway:
    """Minimal WebSocket gateway for Jarvis.

    Binds to 127.0.0.1 only by default.
    LAN mode is OPT-IN via GOLDEN_GATEWAY_LAN=1.
    When LAN enabled, binds to BOTH loopback AND private IP (dual bind).
    SSL mode: GOLDEN_SSL=1 enables WSS via ssl_context.
    All actions route through JarvisService.
    """

    def __init__(self, service, host: str = "127.0.0.1", port: int = 8766,
                 extra_hosts: Optional[list] = None, ssl_context=None,
                 auth_manager: Optional[AuthManager] = None):
        self.service = service
        self.host = host
        self.port = port
        self.extra_hosts = extra_hosts or []  # Additional bind addresses (e.g., LAN IP)
        self.ssl_context = ssl_context  # ssl.SSLContext for WSS
        # HTTP and WebSocket inbound identity share this manager when the
        # canonical server supplies it; standalone Gateway callers retain the
        # historical default.
        self.auth = auth_manager or AuthManager()
        self.sessions = SessionManager()
        self.idempotency = IdempotencyCache()
        self._device_pairing = None
        self._lan_config = None
        self._cors = CORSConfig()  # CORS helper (lan_config set later)
        self._app = web.Application(middlewares=[self._make_cors_middleware()])
        self._app.router.add_get("/ws", self._handle_websocket)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_post("/pairing/code", self._handle_pairing_code)
        self._app.router.add_post("/pairing/confirm", self._handle_pairing_confirm)
        self._app.router.add_get("/devices", self._handle_list_devices)
        self._runner: Optional[web.AppRunner] = None
        self._sites: list = []  # All TCPSite instances
        self._started = False

    def _make_cors_middleware(self):
        """Create CORS middleware bound to this gateway instance."""
        from aiohttp import web

        @web.middleware
        async def cors_middleware(request: web.Request, handler):
            # Handle OPTIONS preflight for all routes
            if request.method == "OPTIONS":
                origin = request.headers.get("Origin", "")
                lc = self._lan_config

                if not origin:
                    return web.Response(status=204)

                if not is_cors_allowed_origin(origin, lc):
                    return web.Response(status=403, text="Origin not allowed")

                allowed_methods = ["GET", "POST", "OPTIONS"]
                allowed_headers = ["Content-Type", "Authorization"]

                headers = build_cors_headers(origin, lc, allowed_methods, allowed_headers)
                return web.Response(status=204, headers=headers)

            # For non-OPTIONS, call handler and add CORS headers
            response = await handler(request)
            origin = request.headers.get("Origin", "")
            if origin:
                add_cors_to_response(response, origin, self._lan_config)
            return response

        return cors_middleware

    async def start(self) -> None:
        """Start the gateway server with dual bind support and optional SSL."""
        if self._started:
            return
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        ws_scheme = "wss" if self.ssl_context else "ws"

        # Primary listener (loopback or configured host)
        primary = web.TCPSite(self._runner, self.host, self.port,
                              ssl_context=self.ssl_context)
        await primary.start()
        self._sites.append(primary)

        # Extra listeners (e.g., LAN IP when dual bind enabled)
        for extra_host in self.extra_hosts:
            if extra_host != self.host:  # Don't duplicate primary
                extra_site = web.TCPSite(self._runner, extra_host, self.port,
                                         ssl_context=self.ssl_context)
                await extra_site.start()
                self._sites.append(extra_site)
                logger.info(f"Gateway extra listener: {extra_host}:{self.port}")

        self._started = True
        hosts = [self.host] + [h for h in self.extra_hosts if h != self.host]
        logger.info(f"Gateway started on {', '.join(f'{ws_scheme}://{h}:{self.port}/ws' for h in hosts)}")

    async def stop(self) -> None:
        """Stop the gateway server and close all connections."""
        if not self._started:
            return
        # Close all active connections
        for ws in list(_active_connections):
            await ws.close()
        _active_connections.clear()
        # Stop all sites
        for site in self._sites:
            try:
                await site.stop()
            except Exception:
                pass
        self._sites.clear()
        if self._runner:
            await self._runner.cleanup()
        self._started = False
        logger.info("Gateway stopped")

    @property
    def is_started(self) -> bool:
        return self._started

    def set_device_pairing(self, service) -> None:
        """Set the device pairing service."""
        self._device_pairing = service
        self.auth.set_device_pairing_service(service)

    def set_lan_config(self, config) -> None:
        """Set the LAN configuration."""
        self._lan_config = config
        self._cors = CORSConfig(config)  # Update CORS config

    # ─── Pairing Endpoints ────────────────────────────────────

    async def _handle_pairing_code(self, request: web.Request) -> web.Response:
        """Generate a pairing code (LOCALHOST ONLY for security)."""
        if not self._device_pairing:
            return web.json_response(
                {"ok": False, "error": "Device pairing not available"},
                status=503,
            )

        source_ip = request.remote or "unknown"

        # SECURITY: Only allow pairing code generation from localhost
        from ..lan_config import is_private_ip
        if source_ip not in ("127.0.0.1", "::1", "[::1]", "unknown"):
            logger.warning(f"Pairing code generation blocked from non-localhost: {source_ip}")
            return web.json_response(
                {"ok": False, "error": "Pairing code generation restricted to localhost"},
                status=403,
            )

        code = self._device_pairing.create_pairing_code(source_ip)
        return web.json_response({
            "ok": True,
            "code": code,
            "ttl": 300,
        })

    async def _handle_pairing_confirm(self, request: web.Request) -> web.Response:
        """Confirm pairing from iPhone (enter code + device info)."""
        if not self._device_pairing:
            return web.json_response(
                {"ok": False, "error": "Device pairing not available"},
                status=503,
            )

        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"ok": False, "error": "Invalid JSON"},
                status=400,
            )

        code = data.get("code", "").strip()
        device_name = data.get("device_name", "iPhone")
        device_type = data.get("device_type", "iphone")
        source_ip = request.remote or "unknown"

        # Validate code
        result = self._device_pairing.validate_pairing_code(code, source_ip)
        if result is None:
            return web.json_response(
                {"ok": False, "error": "Invalid or expired pairing code"},
                status=401,
            )

        # Complete pairing
        device = self._device_pairing.complete_pairing(
            device_name=device_name,
            device_type=device_type,
            source_ip=source_ip,
        )
        if device is None:
            return web.json_response(
                {"ok": False, "error": "Pairing failed"},
                status=500,
            )

        return web.json_response({
            "ok": True,
            "device_id": device["device_id"],
            "device_name": device["device_name"],
            "token": device["token"],
        })

    async def _handle_list_devices(self, request: web.Request) -> web.Response:
        """List registered devices (requires authentication)."""
        if not self._device_pairing:
            return web.json_response(
                {"ok": False, "error": "Device pairing not available"},
                status=503,
            )

        # Check for auth token in header or query
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.query.get("token", "")

        # Verify token
        if not token or not self.auth.verify_token(token):
            # Also check device tokens
            if self._device_pairing:
                device = self._device_pairing.verify_device_token(token)
                if not device:
                    return web.json_response(
                        {"ok": False, "error": "Authentication required"},
                        status=401,
                    )
            else:
                return web.json_response(
                    {"ok": False, "error": "Authentication required"},
                    status=401,
                )

        devices = self._device_pairing.list_devices()
        return web.json_response({
            "ok": True,
            "devices": devices,
        })

    # ─── HTTP Health Endpoint ──────────────────────────────────

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Internal health endpoint (not exposed to external)."""
        try:
            status = self.service.status()
            return web.json_response({
                "ok": True,
                "gateway": "running",
                "connections": len(_active_connections),
                "sessions": self.sessions.count(),
                "service_state": status.get("state", "unknown"),
            })
        except Exception as e:
            return web.json_response(
                {"ok": False, "error": "Health check failed"},
                status=500,
            )

    # ─── WebSocket Handler ─────────────────────────────────────

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        # Origin validation
        origin = request.headers.get("Origin")
        source_ip = request.remote or "unknown"

        # Validate origin against allowed list
        if origin and not self._validate_origin(origin, source_ip):
            logger.warning(f"WebSocket connection rejected: invalid origin {origin} from {source_ip}")
            return web.Response(status=403, text="Origin not allowed")

        ws = web.WebSocketResponse(
            max_msg_size=MAX_PAYLOAD_BYTES,
            heartbeat=30.0,
        )
        await ws.prepare(request)
        _active_connections.add(ws)

        session: Optional[Session] = None
        authenticated = False

        try:
            async for raw_msg in ws:
                if raw_msg.type == web.WSMsgType.TEXT:
                    result = await self._handle_message(
                        ws, raw_msg.data, session, authenticated, source_ip
                    )
                    if result is None:
                        continue
                    new_session, new_auth = result
                    if new_session is not None:
                        session = new_session
                    if new_auth is not None:
                        authenticated = new_auth
                elif raw_msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            _active_connections.discard(ws)
            if session:
                self.sessions.touch(session.session_id)

        return ws

    def _validate_origin(self, origin: str, source_ip: str) -> bool:
        """Validate WebSocket origin."""
        from ..lan_config import validate_origin, is_private_ip

        # Allow if source is private
        if is_private_ip(source_ip):
            return True

        # Check SSL state from lan_config
        ssl_enabled = False
        if self._lan_config:
            ssl_enabled = self._lan_config.ssl_enabled

        # Check against allowed origins (with SSL awareness)
        return validate_origin(origin, self.host, ssl_enabled=ssl_enabled)

    # ─── Message Router ────────────────────────────────────────

    async def _handle_message(
        self,
        ws: web.WebSocketResponse,
        raw: str,
        session: Optional[Session],
        authenticated: bool,
        source_ip: str,
    ) -> Optional[tuple]:
        """Process a single message. Returns (session, authenticated) updates."""

        # Size check
        if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            await self._send(ws, make_error_reply(
                "", "PAYLOAD_TOO_LARGE", "Message exceeds 1MB limit"))
            return None

        # Parse
        try:
            msg = GatewayMessage.from_json(raw)
        except ValueError as e:
            await self._send(ws, make_error_reply(
                "", "INVALID_MESSAGE", str(e)))
            return None

        msg_type = msg.type

        # Auth check
        if msg_type in REQUIRES_AUTH and not authenticated:
            # Allow ping even without auth
            if msg_type == MessageType.PING:
                pass  # handled below
            else:
                await self._send(ws, msg.reply(MessageType.AUTH_ERROR, {
                    "error": "Authentication required"
                }))
                return None

        # Route
        if msg_type == MessageType.HELLO:
            await self._handle_hello(ws, msg)
            return None

        elif msg_type == MessageType.AUTH:
            return await self._handle_auth(ws, msg, source_ip)

        elif msg_type == MessageType.PING:
            await self._send(ws, msg.reply(MessageType.PONG, {}))
            return None

        elif msg_type == MessageType.COMMAND:
            return await self._handle_command(ws, msg, session)

        elif msg_type == MessageType.CONFIRMATION_RESPONSE:
            return await self._handle_confirmation(ws, msg, session)

        elif msg_type == MessageType.SESSION_OPEN:
            return await self._handle_session_open(ws, msg)

        elif msg_type == MessageType.SESSION_RESUME:
            return await self._handle_session_resume(ws, msg)

        elif msg_type == MessageType.SESSION_CLOSE:
            return await self._handle_session_close(ws, msg, session)

        else:
            await self._send(ws, msg.reply(MessageType.ERROR, {
                "code": "UNKNOWN_TYPE",
                "message": f"Unknown message type: {msg_type.value}",
            }))
            return None

    # ─── Hello ─────────────────────────────────────────────────

    async def _handle_hello(self, ws: web.WebSocketResponse, msg: GatewayMessage) -> None:
        await self._send(ws, msg.reply(MessageType.STATUS, {
            "protocol_version": PROTOCOL_VERSION,
            "server": "jarvis-gateway",
            "auth_required": True,
        }))

    # ─── Auth ──────────────────────────────────────────────────

    async def _handle_auth(
        self, ws: web.WebSocketResponse, msg: GatewayMessage, source_ip: str
    ) -> Optional[tuple]:
        token = msg.payload.get("token", "")
        state = self.auth.authenticate(token, source_ip)

        if state.authenticated:
            await self._send(ws, msg.reply(MessageType.AUTH_OK, {
                "authenticated": True,
            }))
            return (None, True)
        else:
            count = self.auth.get_failure_count(source_ip)
            await self._send(ws, msg.reply(MessageType.AUTH_ERROR, {
                "error": "Invalid token",
                "attempts": count,
            }))
            return (None, False)

    # ─── Command ───────────────────────────────────────────────

    async def _handle_command(
        self, ws: web.WebSocketResponse, msg: GatewayMessage,
        session: Optional[Session]
    ) -> Optional[tuple]:
        command = msg.payload.get("command", "")
        if not command:
            await self._send(ws, msg.reply(MessageType.COMMAND_ERROR, {
                "error": "No command provided",
            }))
            return None

        # Idempotency check
        sid = session.session_id if session else ""
        cached = self.idempotency.get(sid, msg.id)
        if cached is not None:
            # Duplicate request — return cached result, do NOT re-execute
            await self._send(ws, msg.reply(MessageType.COMMAND_ACK, {
                "command": command, "duplicate": True,
            }))
            await self._send(ws, msg.reply(MessageType.COMMAND_RESULT, cached))
            return None

        # ACK immediately
        await self._send(ws, msg.reply(MessageType.COMMAND_ACK, {
            "command": command,
        }))

        # Execute via JarvisService (the ONLY authority)
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: self.service.execute_command(
                    command, task_id=sid or "gateway"
                )
            )
        except Exception as e:
            await self._send(ws, msg.reply(MessageType.COMMAND_ERROR, {
                "error": "Execution failed",
            }))
            return None

        # Check if confirmation is required
        if result.get("confirmation_required"):
            # Cache the pending-confirmation reply too. A reconnect/retry with
            # the same request id must not create another pending token.
            self.idempotency.store(sid, msg.id, result)
            await self._send(ws, msg.reply(MessageType.CONFIRMATION_REQUIRED, {
                "token": result.get("token"),
                "action": result.get("action"),
                "risk": result.get("risk"),
                "message": result.get("message"),
            }))
            return None

        # Store in idempotency cache before sending
        self.idempotency.store(sid, msg.id, result)

        # Send result
        await self._send(ws, msg.reply(MessageType.COMMAND_RESULT, result))
        return None

    # ─── Confirmation ──────────────────────────────────────────

    async def _handle_confirmation(
        self, ws: web.WebSocketResponse, msg: GatewayMessage,
        session: Optional[Session]
    ) -> Optional[tuple]:
        token = msg.payload.get("token", "")
        if not token:
            await self._send(ws, msg.reply(MessageType.COMMAND_ERROR, {
                "error": "No confirmation token provided",
            }))
            return None

        # CRITICAL: Check approved field — DENY must be fail-closed
        approved = msg.payload.get("approved", False)
        if not approved:
            # User cancelled — consume token to prevent future replay, do NOT execute
            sid = session.session_id if session else ""
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, lambda: self.service.deny_confirmation(token)
                )
            except Exception:
                pass
            deny_result = {"ok": False, "error": "Ação cancelada pelo operador.",
                           "denied": True}
            self.idempotency.store(sid, msg.id, deny_result)
            await self._send(ws, msg.reply(MessageType.COMMAND_RESULT, deny_result))
            return None

        # Idempotency check — never replay confirmation
        sid = session.session_id if session else ""
        cached = self.idempotency.get(sid, msg.id)
        if cached is not None:
            await self._send(ws, msg.reply(MessageType.COMMAND_RESULT, cached))
            return None

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: self.service.confirm(
                    token, task_id=sid or "gateway"
                )
            )
        except Exception as e:
            await self._send(ws, msg.reply(MessageType.COMMAND_ERROR, {
                "error": "Confirmation failed",
            }))
            return None

        # Store before sending
        self.idempotency.store(sid, msg.id, result)

        await self._send(ws, msg.reply(MessageType.COMMAND_RESULT, result))
        return None

    # ─── Session Management ────────────────────────────────────

    async def _handle_session_open(
        self, ws: web.WebSocketResponse, msg: GatewayMessage
    ) -> Optional[tuple]:
        client_info = msg.payload.get("client_info", {})
        session = self.sessions.create(client_info)
        await self._send(ws, msg.reply(MessageType.SESSION_INFO, {
            "action": "opened",
            **session.to_dict(),
        }, session_id=session.session_id))
        return (session, None)

    async def _handle_session_resume(
        self, ws: web.WebSocketResponse, msg: GatewayMessage
    ) -> Optional[tuple]:
        session_id = msg.session_id or msg.payload.get("session_id", "")
        if not session_id:
            await self._send(ws, msg.reply(MessageType.ERROR, {
                "code": "NO_SESSION_ID",
                "message": "session_id required for resume",
            }))
            return None

        session = self.sessions.resume(session_id, authenticated=True)
        if session is None:
            await self._send(ws, msg.reply(MessageType.ERROR, {
                "code": "SESSION_NOT_FOUND",
                "message": "Session not found or expired",
            }))
            return None

        await self._send(ws, msg.reply(MessageType.SESSION_INFO, {
            "action": "resumed",
            **session.to_dict(),
        }, session_id=session.session_id))
        return (session, None)

    async def _handle_session_close(
        self, ws: web.WebSocketResponse, msg: GatewayMessage,
        session: Optional[Session]
    ) -> Optional[tuple]:
        if session:
            self.idempotency.clear_session(session.session_id)
            self.sessions.close(session.session_id)
            await self._send(ws, msg.reply(MessageType.SESSION_INFO, {
                "action": "closed",
                "session_id": session.session_id,
            }))
        return (None, False)

    # ─── Send Helper ───────────────────────────────────────────

    async def _send(self, ws: web.WebSocketResponse, msg: GatewayMessage) -> None:
        try:
            await ws.send_str(msg.to_json())
        except Exception as e:
            logger.error(f"Failed to send message: {e}")


# ─── Standalone Runner ────────────────────────────────────────

def run_gateway(service, host: str = "127.0.0.1", port: int = 8766) -> None:
    """Run the gateway as a standalone process."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stdout,
    )

    gateway = Gateway(service, host=host, port=port)

    async def _run():
        started = False
        try:
            await gateway.start()
            started = True
            while True:
                await asyncio.sleep(3600)
        finally:
            if started:
                await gateway.stop()

    asyncio.run(_run())
