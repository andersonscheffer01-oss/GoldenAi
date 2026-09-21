"""
Real Network Integration Test — Gateway V1 on localhost.

Run with: pytest tests/test_gateway_integration.py -v -m integration
Or directly: python tests/test_gateway_integration.py

Tests WebSocket connectivity against a real gateway instance.
Binds to 127.0.0.1:8766 only. No LAN. No firewall changes.

Server runs in a background thread with its own event loop.
Tests connect from the main thread via asyncio.run().
"""

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

GOLDEN_ROOT = Path(r"C:\GoldenAI")
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
sys.path.insert(0, str(GOLDEN_ROOT))
sys.path.insert(0, str(STUDIO_ROOT))

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from jarvis_core.gateway import Gateway
from jarvis_core.service import JarvisService

pytestmark = pytest.mark.integration

HOST = "127.0.0.1"
PORT = 8766


class _GatewayServer:
    """Run the gateway server in a background thread with its own event loop."""

    def __init__(self, service):
        self.gw = Gateway(service, host=HOST, port=PORT)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.gw.start())
        self._loop.run_forever()

    def start(self):
        self._thread.start()
        import time
        time.sleep(0.5)  # wait for server to bind

    def stop(self):
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


def _run_async(coro):
    """Run coroutine in the current thread's event loop (for test client)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an existing loop (shouldn't happen in sync tests)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=30)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@pytest.fixture(scope="module")
def gateway_service():
    """Real JarvisService for integration testing."""
    return JarvisService(STUDIO_ROOT)


@pytest.fixture(scope="module")
def gateway(gateway_service):
    """Real Gateway instance on localhost:8766 in background thread."""
    server = _GatewayServer(gateway_service)
    server.start()
    yield server.gw
    server.stop()


@pytest.fixture(scope="module")
def token(gateway):
    """Real gateway token."""
    return gateway.auth.get_token()


@pytest.mark.integration
@pytest.mark.skipif(not AIOHTTP_AVAILABLE, reason="aiohttp not installed")
class TestGatewayRealNetwork:
    """Real network integration tests on 127.0.0.1:8766."""

    def test_health_endpoint(self, gateway):
        """Health endpoint returns status."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{HOST}:{PORT}/health") as resp:
                    data = await resp.json()
                    assert data["ok"] is True
                    assert data["gateway"] == "running"
                    assert data["service_state"] == "IDLE"
        _run_async(_test())

    def test_websocket_connect_and_hello(self, gateway):
        """WebSocket connects and hello handshake works."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    hello = {"version": 1, "id": "h1", "type": "hello", "payload": {}}
                    await ws.send_str(json.dumps(hello))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "status"
                    assert data["id"] == "h1"
                    assert data["payload"]["auth_required"] is True
        _run_async(_test())

    def test_auth_valid_token(self, gateway, token):
        """Valid token authenticates successfully."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a1", "type": "auth",
                            "payload": {"token": token}}
                    await ws.send_str(json.dumps(auth))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "auth_ok"
                    assert data["payload"]["authenticated"] is True
        _run_async(_test())

    def test_auth_invalid_token_rejected(self, gateway):
        """Invalid token is rejected."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a2", "type": "auth",
                            "payload": {"token": "wrong-token"}}
                    await ws.send_str(json.dumps(auth))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "auth_error"
        _run_async(_test())

    def test_unauthenticated_command_rejected(self, gateway):
        """Command without auth is rejected."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    cmd = {"version": 1, "id": "c1", "type": "command",
                           "payload": {"command": "get_time"}}
                    await ws.send_str(json.dumps(cmd))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "auth_error"
        _run_async(_test())

    def test_ping_pong(self, gateway):
        """Ping returns pong with same ID."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    ping = {"version": 1, "id": "p1", "type": "ping", "payload": {}}
                    await ws.send_str(json.dumps(ping))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "pong"
                    assert data["id"] == "p1"
        _run_async(_test())

    def test_session_open_and_close(self, gateway, token):
        """Session lifecycle: open -> resume -> close."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a1", "type": "auth",
                            "payload": {"token": token}}
                    await ws.send_str(json.dumps(auth))
                    await asyncio.wait_for(ws.receive(), timeout=5)

                    sess = {"version": 1, "id": "s1", "type": "session_open",
                            "payload": {"client_info": {"device": "test"}}}
                    await ws.send_str(json.dumps(sess))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "session_info"
                    assert data["payload"]["action"] == "opened"
                    sid = data["payload"]["session_id"]

                    resume = {"version": 1, "id": "s2", "type": "session_resume",
                              "session_id": sid}
                    await ws.send_str(json.dumps(resume))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "session_info"
                    assert data["payload"]["action"] == "resumed"

                    close = {"version": 1, "id": "s3", "type": "session_close",
                             "session_id": sid}
                    await ws.send_str(json.dumps(close))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "session_info"
                    assert data["payload"]["action"] == "closed"
        _run_async(_test())

    def test_safe_command(self, gateway, token):
        """Authenticated command executes and returns result."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a1", "type": "auth",
                            "payload": {"token": token}}
                    await ws.send_str(json.dumps(auth))
                    await asyncio.wait_for(ws.receive(), timeout=5)

                    cmd = {"version": 1, "id": "c1", "type": "command",
                           "payload": {"command": "get_time"}}
                    await ws.send_str(json.dumps(cmd))

                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    ack = json.loads(msg.data)
                    assert ack["type"] == "command_ack"
                    assert ack["id"] == "c1"

                    msg = await asyncio.wait_for(ws.receive(), timeout=10)
                    result = json.loads(msg.data)
                    assert result["type"] == "command_result"
                    assert result["id"] == "c1"
        _run_async(_test())

    def test_duplicate_request_not_reexecuted(self, gateway, token):
        """Same request_id is not executed twice."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a1", "type": "auth",
                            "payload": {"token": token}}
                    await ws.send_str(json.dumps(auth))
                    await asyncio.wait_for(ws.receive(), timeout=5)

                    sess = {"version": 1, "id": "s1", "type": "session_open",
                            "payload": {}}
                    await ws.send_str(json.dumps(sess))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    sid = json.loads(msg.data)["payload"]["session_id"]

                    cmd = {"version": 1, "id": "dup-test", "type": "command",
                           "session_id": sid,
                           "payload": {"command": "get_time"}}
                    await ws.send_str(json.dumps(cmd))
                    await asyncio.wait_for(ws.receive(), timeout=5)
                    await asyncio.wait_for(ws.receive(), timeout=10)

                    await ws.send_str(json.dumps(cmd))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    ack2 = json.loads(msg.data)
                    assert ack2["payload"]["duplicate"] is True
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    result2 = json.loads(msg.data)
                    assert result2["type"] == "command_result"
        _run_async(_test())

    def test_reconnect_resume(self, gateway, token):
        """Disconnect and reconnect with session resume."""
        async def _test():
            sid = None
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a1", "type": "auth",
                            "payload": {"token": token}}
                    await ws.send_str(json.dumps(auth))
                    await asyncio.wait_for(ws.receive(), timeout=5)

                    sess = {"version": 1, "id": "s1", "type": "session_open",
                            "payload": {}}
                    await ws.send_str(json.dumps(sess))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    sid = json.loads(msg.data)["payload"]["session_id"]
                    await ws.close()

            assert sid is not None

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    auth = {"version": 1, "id": "a2", "type": "auth",
                            "payload": {"token": token}}
                    await ws.send_str(json.dumps(auth))
                    await asyncio.wait_for(ws.receive(), timeout=5)

                    resume = {"version": 1, "id": "s2", "type": "session_resume",
                              "session_id": sid}
                    await ws.send_str(json.dumps(resume))
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "session_info"
                    assert data["payload"]["action"] == "resumed"
                    assert data["payload"]["session_id"] == sid
        _run_async(_test())

    def test_malformed_json_rejected(self, gateway):
        """Malformed JSON returns error."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    await ws.send_str("not json at all")
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    assert data["type"] == "error"
                    assert data["payload"]["code"] == "INVALID_MESSAGE"
        _run_async(_test())

    def test_oversized_payload_rejected(self, gateway):
        """Payload over 1MB is rejected (connection closed by server)."""
        async def _test():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{HOST}:{PORT}/ws") as ws:
                    large = "x" * (1_048_576 + 100)
                    await ws.send_str(large)
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    # Server drops connection due to max_msg_size
                    assert msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                                        aiohttp.WSMsgType.ERROR)
        _run_async(_test())
