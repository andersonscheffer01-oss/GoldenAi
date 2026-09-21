"""Phase 6.3A — CORS/Preflight Fix Tests

Tests for:
  - CORS origin validation (SSL on/off)
  - OPTIONS preflight responses
  - CORS headers on POST/GET responses
  - Pairing code localhost-only enforcement
  - Wildcard CORS prohibition
  - Origin validation with SSL
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure we can import from the project
_ROOT = Path(r"C:\GoldenAI")
_STUDIO = _ROOT / "studio" / "golden_ai_studio_web"
if str(_STUDIO) not in sys.path:
    sys.path.insert(0, str(_STUDIO))

from jarvis_core.gateway.cors import (
    is_cors_allowed_origin,
    build_cors_headers,
    cors_preflight_response,
    add_cors_to_response,
    CORSConfig,
)
from jarvis_core.lan_config import LanConfig


# ─── Mock LanConfig ──────────────────────────────────────────

class MockLanConfig:
    """Mock LanConfig for testing."""

    def __init__(self, ssl_enabled=False, enabled=True, bind_address="192.168.1.100"):
        self.ssl_enabled = ssl_enabled
        self.enabled = enabled
        self.bind_address = bind_address


# ─── is_cors_allowed_origin Tests ────────────────────────────

class TestCORSOriginValidation:
    """Test CORS origin validation."""

    def test_no_origin_rejected(self):
        assert is_cors_allowed_origin("", None) is False

    def test_https_localhost_allowed_ssl_on(self):
        lc = MockLanConfig(ssl_enabled=True)
        assert is_cors_allowed_origin("https://localhost:8765", lc) is True

    def test_https_127_allowed_ssl_on(self):
        lc = MockLanConfig(ssl_enabled=True)
        assert is_cors_allowed_origin("https://127.0.0.1:8765", lc) is True

    def test_https_lan_ip_allowed_ssl_on(self):
        lc = MockLanConfig(ssl_enabled=True, bind_address="192.168.1.100")
        assert is_cors_allowed_origin("https://192.168.1.100:8765", lc) is True

    def test_http_lan_ip_rejected_ssl_on(self):
        lc = MockLanConfig(ssl_enabled=True, bind_address="192.168.1.100")
        assert is_cors_allowed_origin("http://192.168.1.100:8765", lc) is False

    def test_http_127_allowed_ssl_on_for_dev(self):
        lc = MockLanConfig(ssl_enabled=True)
        assert is_cors_allowed_origin("http://127.0.0.1:8765", lc) is True

    def test_http_localhost_allowed_ssl_on_for_dev(self):
        lc = MockLanConfig(ssl_enabled=True)
        assert is_cors_allowed_origin("http://localhost:8765", lc) is True

    def test_http_lan_ip_allowed_ssl_off(self):
        lc = MockLanConfig(ssl_enabled=False, bind_address="192.168.1.100")
        assert is_cors_allowed_origin("http://192.168.1.100:8765", lc) is True

    def test_http_127_allowed_ssl_off(self):
        lc = MockLanConfig(ssl_enabled=False)
        assert is_cors_allowed_origin("http://127.0.0.1:8765", lc) is True

    def test_unknown_origin_rejected(self):
        lc = MockLanConfig(ssl_enabled=True)
        assert is_cors_allowed_origin("https://evil.com:8765", lc) is False

    def test_unknown_origin_rejected_ssl_off(self):
        lc = MockLanConfig(ssl_enabled=False)
        assert is_cors_allowed_origin("http://evil.com:8765", lc) is False

    def test_no_lan_config_rejected(self):
        assert is_cors_allowed_origin("https://192.168.1.100:8765", None) is False

    def test_lan_disabled_rejected(self):
        lc = MockLanConfig(ssl_enabled=True, enabled=False)
        assert is_cors_allowed_origin("https://192.168.1.100:8765", lc) is False


# ─── build_cors_headers Tests ─────────────────────────────────

class TestCORSHelpers:
    """Test CORS header building."""

    def test_no_origin_returns_empty(self):
        headers = build_cors_headers("", None)
        assert "Access-Control-Allow-Origin" not in headers

    def test_disallowed_origin_returns_empty(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://evil.com:8765", lc)
        assert "Access-Control-Allow-Origin" not in headers

    def test_allowed_origin_returns_exact_origin(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://192.168.1.100:8765", lc)
        assert headers["Access-Control-Allow-Origin"] == "https://192.168.1.100:8765"

    def test_vary_origin_header_present(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://192.168.1.100:8765", lc)
        assert headers["Vary"] == "Origin"

    def test_wildcard_not_used(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://192.168.1.100:8765", lc)
        assert "*" not in headers.get("Access-Control-Allow-Origin", "")

    def test_allowed_methods_included(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://192.168.1.100:8765", lc,
                                     allowed_methods=["POST", "OPTIONS"])
        assert headers["Access-Control-Allow-Methods"] == "POST, OPTIONS"

    def test_allowed_headers_included(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://192.168.1.100:8765", lc,
                                     allowed_headers=["Content-Type"])
        assert headers["Access-Control-Allow-Headers"] == "Content-Type"


# ─── add_cors_to_response Tests ──────────────────────────────

class TestAddCORS:
    """Test adding CORS headers to aiohttp responses."""

    def test_add_cors_to_response(self):
        from aiohttp.web import Response
        lc = MockLanConfig(ssl_enabled=True)
        resp = Response(status=200, text="ok")
        add_cors_to_response(resp, "https://192.168.1.100:8765", lc)
        assert resp.headers["Access-Control-Allow-Origin"] == "https://192.168.1.100:8765"
        assert resp.headers["Vary"] == "Origin"

    def test_no_cors_for_disallowed_origin(self):
        from aiohttp.web import Response
        lc = MockLanConfig(ssl_enabled=True)
        resp = Response(status=200, text="ok")
        add_cors_to_response(resp, "https://evil.com:8765", lc)
        assert "Access-Control-Allow-Origin" not in resp.headers


# ─── CORSConfig Tests ────────────────────────────────────────

class TestCORSConfig:
    """Test CORSConfig class."""

    def test_cors_config_init(self):
        lc = MockLanConfig(ssl_enabled=True)
        config = CORSConfig(lc)
        assert config.lan_config == lc

    def test_cors_config_preflight(self):
        from aiohttp.web import Request
        from aiohttp.test_utils import make_mocked_request
        lc = MockLanConfig(ssl_enabled=True)
        config = CORSConfig(lc)
        req = make_mocked_request("OPTIONS", "/pairing/confirm",
                                  headers={"Origin": "https://192.168.1.100:8765"})
        resp = config.preflight(req, methods=["POST", "OPTIONS"])
        assert resp.status == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "https://192.168.1.100:8765"


# ─── Wildcard Prohibition Tests ──────────────────────────────

class TestWildcardProhibition:
    """Verify wildcard CORS is never used."""

    def test_no_wildcard_in_headers(self):
        lc = MockLanConfig(ssl_enabled=True)
        headers = build_cors_headers("https://192.168.1.100:8765", lc)
        for key, value in headers.items():
            assert "*" not in str(value), f"Wildcard found in {key}: {value}"

    def test_no_wildcard_in_headers_ssl_off(self):
        lc = MockLanConfig(ssl_enabled=False)
        headers = build_cors_headers("http://192.168.1.100:8765", lc)
        for key, value in headers.items():
            assert "*" not in str(value), f"Wildcard found in {key}: {value}"


# ─── SSL Origin Enforcement Tests ────────────────────────────

class TestSSLOriginEnforcement:
    """Test that SSL mode enforces HTTPS origins."""

    def test_https_origin_required_when_ssl_on(self):
        lc = MockLanConfig(ssl_enabled=True, bind_address="192.168.1.100")
        assert is_cors_allowed_origin("https://192.168.1.100:8765", lc) is True
        assert is_cors_allowed_origin("http://192.168.1.100:8765", lc) is False

    def test_http_origin_preserved_when_ssl_off(self):
        lc = MockLanConfig(ssl_enabled=False, bind_address="192.168.1.100")
        assert is_cors_allowed_origin("http://192.168.1.100:8765", lc) is True
        assert is_cors_allowed_origin("https://192.168.1.100:8765", lc) is False


# ─── Pairing Code Localhost-Only Tests ───────────────────────

class TestPairingCodeLocalhostOnly:
    """Verify pairing code generation stays localhost-only."""

    def test_pairing_code_localhost_only_in_handler(self):
        """The gateway _handle_pairing_code checks source_ip, not origin.
        This test verifies the source_ip check logic exists."""
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        # The handler checks source_ip not in ("127.0.0.1", "::1", "[::1]", "unknown")
        # This is a structural test - the check exists in the code
        import inspect
        source = inspect.getsource(gw._handle_pairing_code)
        assert "127.0.0.1" in source
        assert "Pairing code generation restricted to localhost" in source


# ─── Gateway CORS Integration Tests ──────────────────────────

class TestGatewayCORS:
    """Test Gateway CORS integration."""

    def test_gateway_has_cors_middleware(self):
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        # Verify middleware is set up
        assert hasattr(gw, '_make_cors_middleware')
        mw = gw._make_cors_middleware()
        assert mw is not None

    def test_gateway_cors_config_updated_on_lan_config(self):
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        lc = MockLanConfig(ssl_enabled=True)
        gw.set_lan_config(lc)
        assert gw._cors.lan_config == lc

    def test_gateway_cors_allowed_origin(self):
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        lc = MockLanConfig(ssl_enabled=True, bind_address="192.168.1.100")
        gw.set_lan_config(lc)
        assert is_cors_allowed_origin("https://192.168.1.100:8765", gw._lan_config) is True

    def test_gateway_cors_rejects_unknown_origin(self):
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        lc = MockLanConfig(ssl_enabled=True, bind_address="192.168.1.100")
        gw.set_lan_config(lc)
        assert is_cors_allowed_origin("https://evil.com:8765", gw._lan_config) is False
