"""Focused B4.1 Wave 4 HTTP perimeter tests.

These tests use deterministic AuthManager fixtures only. They do not start the
production server, call providers, open MT5, execute trading, or use hardware.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

GOLDEN_ROOT = Path(__file__).resolve().parents[3]
STUDIO_ROOT = GOLDEN_ROOT / "studio" / "golden_ai_studio_web"
for _path in (GOLDEN_ROOT, STUDIO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from jarvis_core.audit import AuditLog
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.gateway.gateway import Gateway
from jarvis_core.http_perimeter import HttpPerimeter
from jarvis_core.models import Risk, Tool
from jarvis_core.security import SecurityManager


def _perimeter(tmp_path, token="wave4-fixture-token"):
    return HttpPerimeter(
        auth_manager=AuthManager(_token=token),
        audit_log=AuditLog(tmp_path / "audit.db"),
    ), token


def _headers(token=None, **extra):
    headers = {"Origin": "http://127.0.0.1:8765"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    headers.update(extra)
    return headers


def test_public_local_health_and_options_do_not_require_identity(tmp_path):
    perimeter, _ = _perimeter(tmp_path)
    health = perimeter.authorize("GET", "/health", _headers())
    options = perimeter.authorize("OPTIONS", "/api/jarvis/chat", _headers())
    assert health.allowed and health.code == "PUBLIC_LOCAL"
    assert options.allowed and options.status_code == 204


def test_public_health_is_not_a_lan_authentication_bypass(tmp_path):
    perimeter, _ = _perimeter(tmp_path)
    result = perimeter.authorize("GET", "/health", _headers(), source_ip="192.168.1.25")
    assert result.allowed is False
    assert result.status_code == 403
    assert result.code == "LOCAL_ONLY"


@pytest.mark.parametrize("headers, code", [
    (_headers(), "AUTH_MISSING"),
    ({"Authorization": "Basic not-bearer"}, "AUTH_MALFORMED"),
    ({"Authorization": "Bearer wrong"}, "AUTH_INVALID"),
    ({"Authorization": "Bearer "}, "AUTH_MALFORMED"),
])
def test_protected_routes_fail_closed_before_dispatch(tmp_path, headers, code):
    perimeter, _ = _perimeter(tmp_path)
    result = perimeter.authorize("POST", "/api/jarvis/chat", headers)
    assert result.allowed is False
    assert result.status_code == 401
    assert result.code == code


def test_valid_auth_preserves_request_and_correlation_identity(tmp_path):
    perimeter, token = _perimeter(tmp_path)
    result = perimeter.authorize(
        "POST", "/api/market/analyze", _headers(
            token, **{"X-Request-ID": "req-wave4", "X-Correlation-ID": "corr-wave4"}))
    assert result.allowed is True
    assert result.code == "AUTH_SUCCESS"
    assert result.context["request_id"] == "req-wave4"
    assert result.context["correlation_id"] == "corr-wave4"
    assert result.context["actor_id"] == "authenticated_client"


def test_expired_or_revoked_credential_is_rejected_without_reclassification(tmp_path):
    perimeter, token = _perimeter(tmp_path)
    # The shared Gateway authority has opaque process/device credentials, so a
    # revoked/expired credential is intentionally indistinguishable from an
    # invalid one at the HTTP boundary and always returns 401.
    result = perimeter.authorize("GET", "/api/status", _headers(token + ":expired"))
    assert result.allowed is False
    assert result.status_code == 401
    assert result.code == "AUTH_INVALID"


def test_route_classes_cover_canonical_legacy_stream_and_high_risk_paths(tmp_path):
    perimeter, _ = _perimeter(tmp_path)
    assert perimeter.route_class("POST", "/api/jarvis/golden/overview") == "AUTHENTICATED"
    assert perimeter.route_class("POST", "/api/market/analyze") == "AUTHENTICATED"
    assert perimeter.route_class("POST", "/api/chat") == "AUTHENTICATED_AND_AUTHORIZED"
    assert perimeter.route_class("POST", "/api/agent") == "AUTHENTICATED_AND_AUTHORIZED"
    assert perimeter.route_class("POST", "/stream/chat") == "AUTHENTICATED_AND_AUTHORIZED"
    assert perimeter.route_class("POST", "/api/mt5/auto_trade") == "AUTHENTICATED_AND_AUTHORIZED"


def test_authentication_does_not_replace_security_manager_approval(tmp_path):
    perimeter, token = _perimeter(tmp_path)
    authenticated = perimeter.authorize("POST", "/api/mt5/auto_trade", _headers(token))
    assert authenticated.allowed is True

    executed = []
    tool = Tool("fixture_trade", "fixture", lambda **_: executed.append(True),
                risk=Risk.HIGH, confirmation=True)
    security = SecurityManager()
    assert security.decision(tool, Risk.HIGH, True) == "confirm"
    assert executed == []


def test_gateway_reuses_the_same_auth_manager(tmp_path):
    auth = AuthManager(_token="shared-wave4-token")
    gateway = Gateway(object(), auth_manager=auth)
    perimeter = HttpPerimeter(auth_manager=auth, audit_log=AuditLog(tmp_path / "audit.db"))
    assert gateway.auth is perimeter.auth_manager
    assert perimeter.authorize("GET", "/api/status", _headers("shared-wave4-token")).allowed


def test_cors_is_origin_bound_and_never_wildcard(tmp_path):
    perimeter, _ = _perimeter(tmp_path)
    allowed = perimeter.cors_headers("http://127.0.0.1:8765")
    denied = perimeter.cors_headers("https://attacker.invalid")
    assert allowed["Access-Control-Allow-Origin"] == "http://127.0.0.1:8765"
    assert allowed["Access-Control-Allow-Origin"] != "*"
    assert denied == {}


def test_static_clients_use_existing_device_identity_without_embedded_secret():
    client = (STUDIO_ROOT / "http-perimeter-client.js").read_text(encoding="utf-8")
    adapter = (STUDIO_ROOT / "jarvis_ui" / "src" / "gateway-adapter.js").read_text(encoding="utf-8")
    for source in (client, adapter):
        assert "GOLDEN_GATEWAY_TOKEN" not in source
        assert "Bearer fixture" not in source
    assert "jarvis_device_token" in client
    assert 'headers.Authorization = \'Bearer \' + token' in adapter


def test_ui_surfaces_install_the_perimeter_client():
    for name in ("dashboard.html", "market.html", "studio_v7.html"):
        source = (STUDIO_ROOT / name).read_text(encoding="utf-8")
        assert "http-perimeter-client.js" in source


def test_stream_and_legacy_routes_are_protected_in_handler_source():
    source = (STUDIO_ROOT / "server_agent.py").read_text(encoding="utf-8")
    assert "decision = self._authorize_http(self.command, self._request_path())" in source
    assert "text/event-stream" in source
    assert '"/api/chat": self.api_chat' in source
    assert '"/api/agent": self.api_agent' in source


def test_canonical_and_legacy_routes_receive_http_context():
    source = (STUDIO_ROOT / "server_agent.py").read_text(encoding="utf-8")
    assert 'data["_http_context"] = decision.context' in source
    assert '"_http_context"] = decision.context' in source
    assert 'HTTP_PERIMETER = HttpPerimeter' in source
