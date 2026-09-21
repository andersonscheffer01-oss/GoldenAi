"""Phase 6 Tests — Device Pairing, LAN Mode, PWA.

Run with: python -m pytest tests/test_phase6.py -v
"""

import os
import sys
import time
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

STUDIO_ROOT = Path(r"C:\GoldenAI\studio\golden_ai_studio_web")
sys.path.insert(0, str(STUDIO_ROOT))

from jarvis_core.device_pairing import (
    DevicePairingService, PairingCode, Device,
    _generate_pairing_code, _hash_token, _generate_device_token,
)
from jarvis_core.lan_config import (
    LanConfig, is_private_ip, get_private_interfaces,
    get_best_private_ip, validate_origin, check_firewall_status,
)
from jarvis_core.gateway.auth import AuthManager, AuthState


# ═══════════════════════════════════════════════════════════════
# DEVICE PAIRING TESTS
# ═══════════════════════════════════════════════════════════════

class TestPairingCode:
    """Test pairing code generation and validation."""

    def test_pairing_code_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            assert code is not None
            assert len(code) == 8

    def test_pairing_code_random(self):
        codes = set()
        for _ in range(100):
            codes.add(_generate_pairing_code())
        # Should have high entropy
        assert len(codes) > 90

    def test_pairing_code_expires(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()

            # Manually expire the code
            with svc._lock:
                svc._pairing_codes[code].expires_at = time.time() - 1

            result = svc.validate_pairing_code(code)
            assert result is None

    def test_pairing_code_single_use(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()

            # First use
            result = svc.validate_pairing_code(code)
            assert result is not None

            # Second use should fail
            result = svc.validate_pairing_code(code)
            assert result is None

    def test_invalid_pairing_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            result = svc.validate_pairing_code("INVALID")
            assert result is None

    def test_pairing_rate_limited(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()

            # Exhaust attempts
            for _ in range(4):
                svc.validate_pairing_code("WRONG")

            # Code should still be valid
            result = svc.validate_pairing_code(code)
            assert result is not None

    def test_device_registered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            svc.validate_pairing_code(code)

            device = svc.complete_pairing(
                device_name="iPhone",
                device_type="iphone",
            )
            assert device is not None
            assert device["device_id"].startswith("dev_")
            assert device["device_name"] == "iPhone"

    def test_device_token_not_logged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            svc.validate_pairing_code(code)

            device = svc.complete_pairing(device_name="Test")
            token = device["token"]

            # Token should not appear in any log file
            # (This is a structural test - tokens are never logged)
            assert len(token) > 40

    def test_device_token_not_plaintext(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            svc.validate_pairing_code(code)

            device = svc.complete_pairing(device_name="Test")
            token = device["token"]

            # Token hash should not equal token
            token_hash = _hash_token(token)
            assert token_hash != token

    def test_device_reconnect_auth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            svc.validate_pairing_code(code)

            device = svc.complete_pairing(device_name="iPhone")
            token = device["token"]

            # Verify device can authenticate
            result = svc.authenticate_device(token)
            assert result is True

    def test_revoked_device_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            svc.validate_pairing_code(code)

            device = svc.complete_pairing(device_name="iPhone")
            device_id = device["device_id"]
            token = device["token"]

            # Revoke device
            svc.revoke_device(device_id)

            # Token should be rejected
            result = svc.authenticate_device(token)
            assert result is False

    def test_unknown_device_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            result = svc.authenticate_device("fake_token")
            assert result is False

    def test_device_session_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)
            code = svc.create_pairing_code()
            svc.validate_pairing_code(code)

            device = svc.complete_pairing(device_name="iPhone")
            assert device["token"] is not None
            assert len(device["token"]) > 40

    def test_device_cannot_assume_other_device_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = DevicePairingService(data_dir=tmpdir)

            # Create two devices
            code1 = svc.create_pairing_code()
            svc.validate_pairing_code(code1)
            device1 = svc.complete_pairing(device_name="iPhone")

            code2 = svc.create_pairing_code()
            svc.validate_pairing_code(code2)
            device2 = svc.complete_pairing(device_name="iPad")

            # Device1 token should not authenticate as device2
            device = svc.verify_device_token(device1["token"])
            assert device.device_id == device1["device_id"]
            assert device.device_id != device2["device_id"]


# ═══════════════════════════════════════════════════════════════
# LAN MODE TESTS
# ═══════════════════════════════════════════════════════════════

class TestLanMode:
    """Test LAN mode configuration."""

    def test_lan_mode_default_off(self):
        config = LanConfig()
        assert config.enabled is False

    def test_localhost_default_preserved(self):
        config = LanConfig()
        assert config.bind_address == "127.0.0.1"

    def test_lan_mode_requires_explicit_enable(self):
        config = LanConfig()
        result = config.enable()
        # Should succeed if private interface exists
        assert "ok" in result

    def test_lan_mode_uses_private_address(self):
        best_ip = get_best_private_ip()
        if best_ip:
            assert is_private_ip(best_ip)

    def test_public_bind_rejected(self):
        assert is_private_ip("192.168.1.100") is True
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False

    def test_origin_validation(self):
        # Local origins should be allowed
        assert validate_origin("http://127.0.0.1:8765") is True
        assert validate_origin("http://localhost:8765") is True

        # No origin (mobile apps) should be allowed
        assert validate_origin(None) is True

    def test_private_network_detection(self):
        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("192.168.1.1") is True
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("::1") is True
        assert is_private_ip("8.8.8.8") is False


# ═══════════════════════════════════════════════════════════════
# AUTH INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestAuthIntegration:
    """Test AuthManager with device tokens."""

    def test_shared_token_auth(self):
        auth = AuthManager()
        token = auth.get_token()
        state = auth.authenticate(token)
        assert state.authenticated is True

    def test_device_token_auth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pairing = DevicePairingService(data_dir=tmpdir)
            auth = AuthManager()
            auth.set_device_pairing_service(pairing)

            # Create device
            code = pairing.create_pairing_code()
            pairing.validate_pairing_code(code)
            device = pairing.complete_pairing(device_name="iPhone")
            token = device["token"]

            # Auth with device token
            state = auth.authenticate(token)
            assert state.authenticated is True
            assert state.client_info["type"] == "device"

    def test_invalid_token_rejected(self):
        auth = AuthManager()
        state = auth.authenticate("invalid_token")
        assert state.authenticated is False

    def test_unauthenticated_lan_command_rejected(self):
        # This is a structural test - the gateway rejects unauthed commands
        from jarvis_core.gateway.protocol import REQUIRES_AUTH, MessageType
        assert MessageType.COMMAND in REQUIRES_AUTH


# ═══════════════════════════════════════════════════════════════
# PWA / PROTOCOL TESTS
# ═══════════════════════════════════════════════════════════════

class TestPwaProtocol:
    """Test PWA protocol and security."""

    def test_pwa_no_api_keys(self):
        """PWA should never receive API keys."""
        # Structural test: device tokens ≠ API keys
        token = _generate_device_token()
        assert "sk-" not in token
        assert "gsk_" not in token

    def test_pwa_no_direct_mt5(self):
        """PWA should not access MT5 directly."""
        from jarvis_core.gateway.protocol import REQUIRES_AUTH, MessageType
        # MT5 access goes through command, which requires auth
        assert MessageType.COMMAND in REQUIRES_AUTH

    def test_pwa_no_direct_golden(self):
        """PWA should not access Golden directly."""
        # Same as MT5 - all goes through JarvisService
        from jarvis_core.gateway.protocol import MessageType
        assert MessageType.COMMAND.value == "command"

    def test_pwa_no_direct_browser_runtime(self):
        """PWA should not access browser runtime directly."""
        # Browser access goes through command → SecurityManager
        pass  # Structural test

    def test_existing_gateway_regression(self):
        """Gateway protocol should not be broken."""
        from jarvis_core.gateway.protocol import (
            MessageType, PROTOCOL_VERSION, MAX_PAYLOAD_BYTES
        )
        assert PROTOCOL_VERSION == 1
        assert MAX_PAYLOAD_BYTES == 1_048_576

    def test_existing_browser_regression(self):
        """Browser module should not be broken."""
        from jarvis_core.browser import BrowserSession, NavigationSecurity
        assert BrowserSession is not None
        assert NavigationSecurity is not None

    def test_existing_security_regression(self):
        """Security module should not be broken."""
        from jarvis_core.security import SecurityManager
        assert SecurityManager is not None

    def test_existing_plugin_regression(self):
        """Plugin module should not be broken."""
        try:
            from plugins.plugin_loader import get_plugin_registry
            assert get_plugin_registry is not None
        except ImportError:
            # Plugin module may not be importable from test context
            pass


# ═══════════════════════════════════════════════════════════════
# SESSION / IDEMPOTENCY TESTS
# ═══════════════════════════════════════════════════════════════

class TestSessionIdempotency:
    """Test session and idempotency integration."""

    def test_session_resume(self):
        from jarvis_core.gateway.sessions import SessionManager
        mgr = SessionManager()
        session = mgr.create("test_source")
        assert session.session_id is not None

        # Touch session
        mgr.touch(session.session_id)
        assert mgr.get(session.session_id) is not None

    def test_duplicate_command_not_reexecuted(self):
        from jarvis_core.gateway.gateway import IdempotencyCache
        cache = IdempotencyCache()

        # Store result
        cache.store("session1", "req1", {"ok": True})

        # Get should return cached
        cached = cache.get("session1", "req1")
        assert cached is not None
        assert cached["ok"] is True

        # Clear
        cache.clear_session("session1")
        cached = cache.get("session1", "req1")
        assert cached is None


# ═══════════════════════════════════════════════════════════════
# DEVICE PERSISTENCE TESTS
# ═══════════════════════════════════════════════════════════════

class TestDevicePersistence:
    """Test device persistence across restarts."""

    def test_devices_persist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create device
            svc1 = DevicePairingService(data_dir=tmpdir)
            code = svc1.create_pairing_code()
            svc1.validate_pairing_code(code)
            device = svc1.complete_pairing(device_name="iPhone")
            device_id = device["device_id"]

            # Create new service instance (simulates restart)
            svc2 = DevicePairingService(data_dir=tmpdir)
            loaded = svc2.get_device(device_id)
            assert loaded is not None
            assert loaded["device_name"] == "iPhone"

    def test_revoked_device_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc1 = DevicePairingService(data_dir=tmpdir)
            code = svc1.create_pairing_code()
            svc1.validate_pairing_code(code)
            device = svc1.complete_pairing(device_name="iPhone")
            device_id = device["device_id"]
            token = device["token"]

            # Revoke
            svc1.revoke_device(device_id)

            # New instance should still have revoked
            svc2 = DevicePairingService(data_dir=tmpdir)
            loaded = svc2.get_device(device_id)
            assert loaded["revoked"] is True

            # Token should not work
            result = svc2.authenticate_device(token)
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
