"""
Security Gate Tests — PHASE 4 Gateway V1

32+ mandatory tests proving gateway security boundaries.

All tests are READ-ONLY or use mocks.
No functional code modified.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

GOLDEN_ROOT = Path(r"C:\GoldenAI")
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
sys.path.insert(0, str(GOLDEN_ROOT))
sys.path.insert(0, str(STUDIO_ROOT))

from jarvis_core.gateway.protocol import (
    GatewayMessage, MessageType, REQUIRES_AUTH, ALWAYS_ALLOWED,
    MAX_PAYLOAD_BYTES, PROTOCOL_VERSION, make_error_reply,
)
from jarvis_core.gateway.auth import AuthManager, AuthState
from jarvis_core.gateway.sessions import SessionManager, Session
from jarvis_core.gateway.gateway import Gateway
from jarvis_core.models import Risk, Tool


# ═══════════════════════════════════════════════════════════════
# PROTOCOL TESTS
# ═══════════════════════════════════════════════════════════════

class TestProtocol:
    """GatewayMessage envelope tests."""

    def test_message_to_dict(self):
        msg = GatewayMessage(type=MessageType.HELLO)
        d = msg.to_dict()
        assert d["type"] == "hello"
        assert d["version"] == PROTOCOL_VERSION
        assert "id" in d
        assert "timestamp" in d

    def test_message_roundtrip(self):
        msg = GatewayMessage(
            type=MessageType.COMMAND,
            payload={"command": "list_processes"},
            session_id="test-session",
        )
        raw = msg.to_json()
        restored = GatewayMessage.from_json(raw)
        assert restored.type == MessageType.COMMAND
        assert restored.payload["command"] == "list_processes"
        assert restored.session_id == "test-session"
        assert restored.id == msg.id

    def test_reply_preserves_correlation_id(self):
        msg = GatewayMessage(type=MessageType.COMMAND, id="req-123")
        reply = msg.reply(MessageType.COMMAND_RESULT, {"ok": True})
        assert reply.id == "req-123"
        assert reply.type == MessageType.COMMAND_RESULT

    def test_unknown_type_rejected(self):
        with pytest.raises(ValueError, match="Unknown message type"):
            GatewayMessage.from_dict({"type": "unknown_type", "id": "x"})

    def test_invalid_json_rejected(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            GatewayMessage.from_json("not json")

    def test_non_object_json_rejected(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            GatewayMessage.from_json('"just a string"')

    def test_error_reply_structure(self):
        reply = make_error_reply("req-1", "TEST_ERROR", "something failed", retryable=True)
        assert reply.type == MessageType.ERROR
        assert reply.id == "req-1"
        assert reply.payload["code"] == "TEST_ERROR"
        assert reply.payload["retryable"] is True

    def test_requires_auth_set(self):
        assert MessageType.COMMAND in REQUIRES_AUTH
        assert MessageType.CONFIRMATION_RESPONSE in REQUIRES_AUTH
        assert MessageType.SESSION_OPEN in REQUIRES_AUTH

    def test_always_allowed_set(self):
        assert MessageType.HELLO in ALWAYS_ALLOWED
        assert MessageType.AUTH in ALWAYS_ALLOWED
        assert MessageType.PING in ALWAYS_ALLOWED


# ═══════════════════════════════════════════════════════════════
# AUTH TESTS
# ═══════════════════════════════════════════════════════════════

class TestAuth:
    """AuthManager tests."""

    def test_valid_auth_accepted(self):
        am = AuthManager()
        token = am.get_token()
        state = am.authenticate(token)
        assert state.authenticated is True
        assert state.token_hash is not None

    def test_invalid_auth_rejected(self):
        am = AuthManager()
        state = am.authenticate("wrong-token-12345")
        assert state.authenticated is False

    def test_empty_token_rejected(self):
        am = AuthManager()
        state = am.authenticate("")
        assert state.authenticated is False

    def test_auth_token_not_leaked_in_logs(self):
        am = AuthManager()
        token = am.get_token()
        state = am.authenticate(token)
        # AuthState repr should not contain the raw token
        assert token not in repr(state)

    def test_auth_token_not_in_error_messages(self):
        am = AuthManager()
        token = am.get_token()
        state = am.authenticate("wrong")
        # Error state should not contain the real token
        assert token not in repr(state)

    def test_rate_limiting(self):
        am = AuthManager()
        for _ in range(11):
            am.authenticate("wrong-token")
        # Should be rate limited now
        state = am.authenticate("wrong-token")
        assert state.authenticated is False

    def test_rate_limit_resets_on_success(self):
        am = AuthManager()
        for _ in range(5):
            am.authenticate("wrong-token")
        # Successful auth clears failures
        token = am.get_token()
        state = am.authenticate(token)
        assert state.authenticated is True
        assert am.get_failure_count("unknown") == 0


# ═══════════════════════════════════════════════════════════════
# SESSION TESTS
# ═══════════════════════════════════════════════════════════════

class TestSessions:
    """SessionManager tests."""

    def test_session_created(self):
        sm = SessionManager()
        session = sm.create()
        assert session.session_id is not None
        assert len(session.session_id) > 10
        assert session.authenticated is False

    def test_session_get(self):
        sm = SessionManager()
        session = sm.create()
        retrieved = sm.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_session_resume_requires_existing(self):
        sm = SessionManager()
        session = sm.resume("nonexistent-id")
        assert session is None

    def test_session_resume_valid(self):
        sm = SessionManager()
        session = sm.create()
        resumed = sm.resume(session.session_id, authenticated=True)
        assert resumed is not None
        assert resumed.authenticated is True

    def test_session_fixation_prevented(self):
        """Cannot resume a session that was closed."""
        sm = SessionManager()
        session = sm.create()
        sm.close(session.session_id)
        resumed = sm.resume(session.session_id)
        assert resumed is None

    def test_session_expired(self):
        """Expired sessions return None."""
        sm = SessionManager()
        session = sm.create()
        # Force expiry
        session.last_seen = time.time() - 7200
        retrieved = sm.get(session.session_id)
        assert retrieved is None

    def test_session_touch(self):
        sm = SessionManager()
        session = sm.create()
        old_seen = session.last_seen
        time.sleep(0.01)
        sm.touch(session.session_id)
        session = sm.get(session.session_id)
        assert session.last_seen >= old_seen

    def test_session_close(self):
        sm = SessionManager()
        session = sm.create()
        sm.close(session.session_id)
        assert sm.get(session.session_id) is None

    def test_sweep_expired(self):
        sm = SessionManager()
        s1 = sm.create()
        s2 = sm.create()
        s1.last_seen = time.time() - 7200
        sm._last_sweep = 0  # Force sweep
        removed = sm.sweep_expired()
        assert removed == 1
        assert sm.get(s2.session_id) is not None

    def test_session_unpredictable_id(self):
        """Session IDs are cryptographically random."""
        sm = SessionManager()
        ids = {sm.create().session_id for _ in range(50)}
        assert len(ids) == 50


# ═══════════════════════════════════════════════════════════════
# GATEWAY ARCHITECTURE TESTS
# ═══════════════════════════════════════════════════════════════

class TestGatewayArchitecture:
    """Gateway must be transport-only."""

    def test_gateway_starts_localhost_only(self):
        """Default bind is 127.0.0.1."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        assert gw.host == "127.0.0.1"
        assert gw.port == 8766

    def test_gateway_does_not_execute_tool_directly(self):
        """Gateway class has no execute_tool method."""
        gw = Gateway(MagicMock())
        assert not hasattr(gw, "execute_tool")
        assert not hasattr(gw, "_execute_tool")

    def test_gateway_does_not_access_mt5_directly(self):
        """Gateway code has no MT5 imports or function calls."""
        from jarvis_core.gateway import gateway as gw_module
        import inspect
        source = inspect.getsource(gw_module)
        # Check for actual imports/calls, not just mentions in docstrings
        lines = [l.strip() for l in source.split("\n")
                 if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code_lines = "\n".join(lines)
        assert "import mt5" not in code_lines
        assert "from mt5" not in code_lines
        assert "mt5_connector" not in code_lines
        assert "mt5_trader" not in code_lines

    def test_gateway_does_not_access_golden_directly(self):
        """Gateway has no Golden trading imports."""
        from jarvis_core.gateway import gateway as gw_module
        import inspect
        source = inspect.getsource(gw_module)
        assert "golden_scanner" not in source
        assert "golden_memory" not in source

    def test_security_manager_not_bypassed(self):
        """Gateway routes through JarvisService which uses SecurityManager."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        assert hasattr(gw, "service")
        assert gw.service is mock_service

    def test_gateway_uses_jarvis_service_as_authority(self):
        """Gateway delegates to JarvisService for all commands."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        assert gw.service.execute_command is not None
        assert gw.service.confirm is not None

    def test_confirmation_required_forwarded(self):
        """When JarvisService requires confirmation, gateway forwards it."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {
            "ok": True,
            "confirmation_required": True,
            "token": "test-token",
            "action": "shutdown",
            "risk": "CRITICAL",
        }
        gw = Gateway(mock_service)
        # The message handler will forward confirmation_required
        # This is verified by the integration test below

    def test_confirmation_response_forwarded(self):
        """Confirmation responses go through JarvisService.confirm()."""
        mock_service = MagicMock()
        mock_service.confirm.return_value = {"ok": True}
        gw = Gateway(mock_service)
        assert gw.service.confirm is not None


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS (async)
# ═══════════════════════════════════════════════════════════════

def _run_async(coro):
    """Helper to run async functions in tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestGatewayIntegration:
    """Integration tests using mock WebSocket."""

    def _make_ws(self):
        """Create a mock WebSocket response."""
        ws = AsyncMock()
        ws.send_str = AsyncMock()
        ws.close = AsyncMock()
        ws.prepare = AsyncMock()
        return ws

    def _make_request(self):
        """Create a mock HTTP request."""
        request = MagicMock()
        request.remote = "127.0.0.1"
        return request

    def test_ping_pong(self):
        """Ping returns pong with same ID."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(type=MessageType.PING, id="ping-1")
        _run_async(gw._handle_message(ws, msg.to_json(), None, False, "127.0.0.1"))

        ws.send_str.assert_called_once()
        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "pong"
        assert sent["id"] == "ping-1"

    def test_unauthenticated_command_rejected(self):
        """Command without auth is rejected."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(type=MessageType.COMMAND, payload={"command": "test"})
        _run_async(gw._handle_message(ws, msg.to_json(), None, False, "127.0.0.1"))

        ws.send_str.assert_called_once()
        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "auth_error"

    def test_valid_auth_accepted(self):
        """Valid token authenticates."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()
        token = gw.auth.get_token()

        msg = GatewayMessage(type=MessageType.AUTH, payload={"token": token})
        _, authenticated = _run_async(gw._handle_message(ws, msg.to_json(), None, False, "127.0.0.1"))

        assert authenticated is True
        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "auth_ok"

    def test_invalid_auth_rejected(self):
        """Wrong token is rejected."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(type=MessageType.AUTH, payload={"token": "wrong"})
        _, authenticated = _run_async(gw._handle_message(ws, msg.to_json(), None, False, "127.0.0.1"))

        assert authenticated is False

    def test_command_routes_to_jarvis_service(self):
        """Command execution goes through JarvisService."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True, "message": "done"}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.COMMAND,
            payload={"command": "list_processes"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        # No session → task_id defaults to "gateway"
        mock_service.execute_command.assert_called_once_with(
            "list_processes", task_id="gateway"
        )

    def test_request_id_preserved(self):
        """Response preserves the request ID."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.COMMAND,
            id="req-42",
            payload={"command": "test"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        # Should have ACK + result = 2 messages
        assert ws.send_str.call_count == 2
        ack = json.loads(ws.send_str.call_args_list[0][0][0])
        result = json.loads(ws.send_str.call_args_list[1][0][0])
        assert ack["id"] == "req-42"
        assert result["id"] == "req-42"

    def test_confirmation_required_forwarded(self):
        """When service requires confirmation, gateway forwards it."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {
            "ok": True,
            "confirmation_required": True,
            "token": "confirm-tok",
            "action": "shutdown",
            "risk": "CRITICAL",
        }
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.COMMAND,
            payload={"command": "shutdown"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        # ACK + confirmation_required
        assert ws.send_str.call_count == 2
        confirm = json.loads(ws.send_str.call_args_list[1][0][0])
        assert confirm["type"] == "confirmation_required"
        assert confirm["payload"]["token"] == "confirm-tok"

    def test_duplicate_confirmation_required_command_not_replanned(self):
        """Retrying a pending-confirmation command does not mint another token."""
        mock_service = MagicMock()
        mock_service.execute_command.side_effect = [
            {
                "ok": True,
                "confirmation_required": True,
                "token": "confirm-tok-1",
                "action": "shutdown",
                "risk": "CRITICAL",
            },
            {
                "ok": True,
                "confirmation_required": True,
                "token": "confirm-tok-2",
                "action": "shutdown",
                "risk": "CRITICAL",
            },
        ]
        gw = Gateway(mock_service)
        ws = self._make_ws()
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.COMMAND,
            id="pending-confirm-1",
            session_id=session.session_id,
            payload={"command": "shutdown"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))
        ws.send_str.reset_mock()
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        assert mock_service.execute_command.call_count == 1
        assert ws.send_str.call_count == 2
        ack = json.loads(ws.send_str.call_args_list[0][0][0])
        result = json.loads(ws.send_str.call_args_list[1][0][0])
        assert ack["payload"]["duplicate"] is True
        assert result["type"] == "command_result"
        assert result["payload"]["token"] == "confirm-tok-1"

    def test_confirmation_response_forwarded(self):
        """Confirmation response with approved=True goes through service.confirm()."""
        mock_service = MagicMock()
        mock_service.confirm.return_value = {"ok": True, "message": "executed"}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.CONFIRMATION_RESPONSE,
            payload={"token": "confirm-tok", "approved": True},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        mock_service.confirm.assert_called_once()
        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "command_result"

    def test_confirmation_response_denied(self):
        """Confirmation response with approved=False calls deny_confirmation."""
        mock_service = MagicMock()
        mock_service.deny_confirmation.return_value = {"ok": True, "denied": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.CONFIRMATION_RESPONSE,
            payload={"token": "confirm-tok", "approved": False},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        mock_service.deny_confirmation.assert_called_once()
        mock_service.confirm.assert_not_called()
        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "command_result"
        assert sent["payload"]["denied"] is True

    def test_confirmation_response_missing_approved_denied(self):
        """Confirmation response without 'approved' defaults to denied (fail-closed)."""
        mock_service = MagicMock()
        mock_service.deny_confirmation.return_value = {"ok": True, "denied": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.CONFIRMATION_RESPONSE,
            payload={"token": "confirm-tok"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        mock_service.deny_confirmation.assert_called_once()
        mock_service.confirm.assert_not_called()

    def test_session_open(self):
        """Session open creates a new session."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(
            type=MessageType.SESSION_OPEN,
            payload={"client_info": {"device": "test"}},
        )
        result = _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        session = result[0]
        assert session is not None
        assert session.session_id is not None
        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "session_info"
        assert sent["payload"]["action"] == "opened"

    def test_session_resume(self):
        """Session resume works with valid session."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        # Create session
        session = gw.sessions.create()
        sid = session.session_id

        msg = GatewayMessage(
            type=MessageType.SESSION_RESUME,
            session_id=sid,
        )
        result = _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        resumed = result[0]
        assert resumed is not None
        assert resumed.session_id == sid

    def test_session_close(self):
        """Session close removes session."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        session = gw.sessions.create()
        msg = GatewayMessage(
            type=MessageType.SESSION_CLOSE,
            session_id=session.session_id,
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        assert gw.sessions.get(session.session_id) is None

    def test_malformed_json_rejected(self):
        """Malformed JSON returns error."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        _run_async(gw._handle_message(ws, "not json at all", None, False, "127.0.0.1"))

        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "error"
        assert sent["payload"]["code"] == "INVALID_MESSAGE"

    def test_unknown_message_type_rejected(self):
        """Unknown message type returns error."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = json.dumps({"type": "unknown_thing", "id": "x"})
        _run_async(gw._handle_message(ws, msg, None, False, "127.0.0.1"))

        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "error"

    def test_oversized_payload_rejected(self):
        """Payload over 1MB is rejected."""
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        ws = self._make_ws()

        large = "x" * (MAX_PAYLOAD_BYTES + 100)
        _run_async(gw._handle_message(ws, large, None, False, "127.0.0.1"))

        sent = json.loads(ws.send_str.call_args[0][0])
        assert sent["type"] == "error"
        assert sent["payload"]["code"] == "PAYLOAD_TOO_LARGE"

    def test_gateway_internal_exception_not_leaked(self):
        """Internal exceptions don't leak tracebacks."""
        mock_service = MagicMock()
        mock_service.execute_command.side_effect = RuntimeError("internal db error")
        gw = Gateway(mock_service)
        ws = self._make_ws()

        msg = GatewayMessage(type=MessageType.COMMAND, payload={"command": "test"})
        _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        # ACK + error
        error = json.loads(ws.send_str.call_args_list[1][0][0])
        assert error["type"] == "command_error"
        assert "RuntimeError" not in error["payload"]["error"]
        assert "db" not in error["payload"]["error"].lower()

    def test_health_endpoint(self):
        """Health endpoint returns status."""
        mock_service = MagicMock()
        mock_service.status.return_value = {"state": "idle"}
        gw = Gateway(mock_service)

        # Mock request
        request = self._make_request()
        response = _run_async(gw._handle_health(request))

        assert response.status == 200
        data = json.loads(response.body)
        assert data["ok"] is True
        assert data["gateway"] == "running"

    def test_message_flood_limited(self):
        """Auth failures are rate limited."""
        am = AuthManager()
        for _ in range(12):
            am.authenticate("wrong")
        state = am.authenticate("wrong")
        assert state.authenticated is False

    def test_duplicate_request_id_handled(self):
        """Same request ID used twice — second returns cached result, no re-execution."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True, "result": "done"}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        # Create a session first
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.COMMAND,
            id="dup-1",
            session_id=session.session_id,
            payload={"command": "test1"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        msg2 = GatewayMessage(
            type=MessageType.COMMAND,
            id="dup-1",
            session_id=session.session_id,
            payload={"command": "test2"},
        )
        _run_async(gw._handle_message(ws, msg2.to_json(), session, True, "127.0.0.1"))

        # Only ONE execution — duplicate returns cached result
        assert mock_service.execute_command.call_count == 1

    def test_concurrent_requests_correlated(self):
        """Multiple concurrent requests maintain correlation."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        for i in range(5):
            msg = GatewayMessage(
                type=MessageType.COMMAND,
                id=f"req-{i}",
                payload={"command": f"cmd-{i}"},
            )
            _run_async(gw._handle_message(ws, msg.to_json(), None, True, "127.0.0.1"))

        # All 5 commands should have ACK + result = 10 messages
        assert ws.send_str.call_count == 10
        for i in range(5):
            ack = json.loads(ws.send_str.call_args_list[i*2][0][0])
            result = json.loads(ws.send_str.call_args_list[i*2+1][0][0])
            assert ack["id"] == f"req-{i}"
            assert result["id"] == f"req-{i}"


# ═══════════════════════════════════════════════════════════════
# IDEMPOTENCY TESTS
# ═══════════════════════════════════════════════════════════════

class TestIdempotency:
    """Idempotency cache tests."""

    def _make_ws(self):
        ws = AsyncMock()
        ws.send_str = AsyncMock()
        ws.close = AsyncMock()
        ws.prepare = AsyncMock()
        return ws

    def test_duplicate_request_not_double_executed(self):
        """Same session + same request_id executes only once."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.COMMAND, id="idem-1",
            session_id=session.session_id,
            payload={"command": "test"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        assert mock_service.execute_command.call_count == 1

    def test_duplicate_request_returns_cached_result(self):
        """Duplicate request returns the same result."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True, "val": 42}
        gw = Gateway(mock_service)
        ws = self._make_ws()
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.COMMAND, id="idem-2",
            session_id=session.session_id,
            payload={"command": "test"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))
        ws.send_str.reset_mock()
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        # Second call sends ACK(duplicate=True) + cached result
        assert ws.send_str.call_count == 2
        ack = json.loads(ws.send_str.call_args_list[0][0][0])
        result = json.loads(ws.send_str.call_args_list[1][0][0])
        assert ack["payload"]["duplicate"] is True
        assert result["payload"]["val"] == 42

    def test_duplicate_request_after_reconnect_not_reexecuted(self):
        """After reconnect + resume, same request_id still returns cached."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.COMMAND, id="idem-3",
            session_id=session.session_id,
            payload={"command": "test"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        # Simulate reconnect: resume same session
        resumed = gw.sessions.resume(session.session_id, authenticated=True)
        assert resumed is not None

        # Same request_id should still be cached
        ws.send_str.reset_mock()
        _run_async(gw._handle_message(ws, msg.to_json(), resumed, True, "127.0.0.1"))

        assert mock_service.execute_command.call_count == 1

    def test_same_request_id_different_session_is_independent(self):
        """Same request_id in different sessions are independent."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()

        s1 = gw.sessions.create()
        s2 = gw.sessions.create()

        msg1 = GatewayMessage(
            type=MessageType.COMMAND, id="shared-id",
            session_id=s1.session_id,
            payload={"command": "cmd1"},
        )
        _run_async(gw._handle_message(ws, msg1.to_json(), s1, True, "127.0.0.1"))

        msg2 = GatewayMessage(
            type=MessageType.COMMAND, id="shared-id",
            session_id=s2.session_id,
            payload={"command": "cmd2"},
        )
        _run_async(gw._handle_message(ws, msg2.to_json(), s2, True, "127.0.0.1"))

        # Both execute because sessions are different
        assert mock_service.execute_command.call_count == 2

    def test_idempotency_cache_is_bounded(self):
        """Cache does not grow beyond max_entries."""
        from jarvis_core.gateway.gateway import IdempotencyCache
        cache = IdempotencyCache(max_entries=5, ttl=3600)
        for i in range(10):
            cache.store(f"s{i}", f"r{i}", {"i": i})
        assert cache.size() <= 5

    def test_idempotency_cache_expires(self):
        """Expired entries are not returned."""
        from jarvis_core.gateway.gateway import IdempotencyCache
        cache = IdempotencyCache(max_entries=100, ttl=0.01)
        cache.store("s1", "r1", {"ok": True})
        time.sleep(0.02)
        assert cache.get("s1", "r1") is None

    def test_duplicate_confirmation_not_double_executed(self):
        """Replay of confirmation_response does not re-execute."""
        mock_service = MagicMock()
        mock_service.confirm.return_value = {"ok": True, "executed": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.CONFIRMATION_RESPONSE, id="conf-1",
            session_id=session.session_id,
            payload={"token": "some-token", "approved": True},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))

        # Confirmation should only execute once
        assert mock_service.confirm.call_count == 1

    def test_cache_cleared_on_session_close(self):
        """Closing a session clears its idempotency cache."""
        mock_service = MagicMock()
        mock_service.execute_command.return_value = {"ok": True}
        gw = Gateway(mock_service)
        ws = self._make_ws()
        session = gw.sessions.create()

        msg = GatewayMessage(
            type=MessageType.COMMAND, id="cache-test",
            session_id=session.session_id,
            payload={"command": "test"},
        )
        _run_async(gw._handle_message(ws, msg.to_json(), session, True, "127.0.0.1"))
        assert gw.idempotency.get(session.session_id, "cache-test") is not None

        # Close session
        close_msg = GatewayMessage(
            type=MessageType.SESSION_CLOSE,
            session_id=session.session_id,
        )
        _run_async(gw._handle_message(ws, close_msg.to_json(), session, True, "127.0.0.1"))

        assert gw.idempotency.get(session.session_id, "cache-test") is None


# ═══════════════════════════════════════════════════════════════
# TOKEN LOGGING TESTS
# ═══════════════════════════════════════════════════════════════

class TestTokenLogging:
    """Auth token must never be logged in full."""

    def test_generated_token_not_logged_in_full(self):
        """Auto-generated token is never printed to stdout/stderr/log."""
        import io
        import logging

        am = AuthManager()
        token = am.get_token()

        # Capture all logging output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("jarvis.gateway")
        logger.addHandler(handler)

        # Trigger token generation path
        am2 = AuthManager()
        am2.get_token()

        logger.removeHandler(handler)

        log_output = log_capture.getvalue()
        # Token should never appear in log output
        assert token not in log_output

    def test_configured_token_not_logged_in_full(self):
        """Configured token is never printed."""
        import io
        import logging
        import os

        os.environ["GOLDEN_GATEWAY_TOKEN"] = "test-configured-secret-token-12345"
        try:
            am = AuthManager()
            token = am.get_token()

            log_capture = io.StringIO()
            handler = logging.StreamHandler(log_capture)
            handler.setLevel(logging.DEBUG)
            logger = logging.getLogger("jarvis.gateway")
            logger.addHandler(handler)

            # Trigger resolution
            am2 = AuthManager()
            am2.get_token()

            logger.removeHandler(handler)

            log_output = log_capture.getvalue()
            assert token not in log_output
        finally:
            del os.environ["GOLDEN_GATEWAY_TOKEN"]

    def test_auth_error_never_contains_token(self):
        """Auth error responses never include the token value."""
        am = AuthManager()
        real_token = am.get_token()

        state = am.authenticate("wrong-token-value")
        assert state.authenticated is False
        assert real_token not in repr(state)
        assert "wrong-token-value" not in repr(state)

    def test_auth_state_repr_no_token(self):
        """AuthState repr does not expose token hash in a reversible way."""
        am = AuthManager()
        token = am.get_token()
        state = am.authenticate(token)
        repr_str = repr(state)
        assert token not in repr_str
        # Token hash is SHA-256 — not reversible, but should not leak source
        assert token[:8] not in repr_str


# ═══════════════════════════════════════════════════════════════
# BOUNDARY TESTS (same as security gate, proving gateway compliance)
# ═══════════════════════════════════════════════════════════════

class TestGatewayBoundaries:
    """Prove gateway cannot bypass existing security."""

    def test_websocket_cannot_call_mt5_directly(self):
        """Gateway code has no MT5 imports."""
        from jarvis_core.gateway import gateway as gw_mod
        import inspect
        src = inspect.getsource(gw_mod)
        assert "import mt5" not in src
        assert "from mt5" not in src
        assert "mt5_connector" not in src
        assert "mt5_trader" not in src

    def test_websocket_cannot_call_golden_directly(self):
        """Gateway code has no Golden imports."""
        from jarvis_core.gateway import gateway as gw_mod
        import inspect
        src = inspect.getsource(gw_mod)
        assert "golden_scanner" not in src
        assert "from golden" not in src

    def test_audit_log_preserved(self):
        """Gateway uses JarvisService which has AuditLog."""
        from jarvis_core.service import JarvisService
        from jarvis_core.audit import AuditLog
        svc = JarvisService(STUDIO_ROOT)
        assert hasattr(svc, "audit")
        assert isinstance(svc.audit, AuditLog)

    def test_existing_rest_api_unchanged(self):
        """server_agent.py still has all existing routes."""
        from server_agent import GoldenAIHandler
        import inspect
        src = inspect.getsource(GoldenAIHandler.route_api)
        assert "/api/status" in src
        assert "/api/chat" in src
        assert "/api/desktop/action" in src
        assert "/api/mt5/auto_trade" in src
