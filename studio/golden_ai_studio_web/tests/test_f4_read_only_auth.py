from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis_core.device_pairing import DevicePairingService
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.http_perimeter import HttpPerimeter
from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE


def _paired(tmp_path, device_type="desktop"):
    pairing = DevicePairingService(data_dir=str(tmp_path))
    code = pairing.create_pairing_code("127.0.0.1")
    assert pairing.validate_pairing_code(code, "127.0.0.1")
    device = pairing.complete_pairing("F4 test device", device_type)
    assert device
    auth = AuthManager(_token="f4-shared-token")
    auth.set_device_pairing_service(pairing)
    perimeter = HttpPerimeter(
        auth_manager=auth,
        runtime_profile_provider=lambda: WEB_AI_SAFE_PROFILE,
    )
    return pairing, perimeter, device["token"], device["device_id"]


def _authorize(perimeter, token, path, *, method="POST", source_ip="127.0.0.1"):
    headers = {"Authorization": "Bearer " + token}
    return perimeter.authorize(method, path, headers, source_ip=source_ip)


@pytest.mark.parametrize("path", [
    "/api/jarvis/golden/symbol-discovery",
    "/api/jarvis/golden/market-data",
    "/api/jarvis/golden/market-live",
])
def test_panel_market_read_auth_preserves_registry_hash(tmp_path, path):
    pairing, perimeter, token, device_id = _paired(tmp_path)
    registry = tmp_path / "device_registry.json"
    before = hashlib.sha256(registry.read_bytes()).digest()
    last_seen = pairing.get_device(device_id)["last_seen"]

    result = _authorize(perimeter, token, path)

    assert result.allowed is True
    assert result.context["actor_id"] == "device:" + device_id
    assert hashlib.sha256(registry.read_bytes()).digest() == before
    assert pairing.get_device(device_id)["last_seen"] == last_seen


@pytest.mark.parametrize("token, headers", [
    (None, {}),
    ("invalid-token", {"Authorization": "Bearer invalid-token"}),
])
def test_read_only_market_auth_rejects_missing_or_invalid_token(
    tmp_path, token, headers
):
    _, perimeter, _, _ = _paired(tmp_path)
    result = perimeter.authorize(
        "POST", "/api/jarvis/golden/market-live", headers
    )
    assert result.allowed is False
    assert result.status_code == 401


def test_read_only_market_auth_rejects_shared_or_non_desktop_identity(tmp_path):
    pairing, perimeter, _, _ = _paired(tmp_path)
    shared = _authorize(perimeter, "f4-shared-token",
                        "/api/jarvis/golden/market-data")
    assert shared.allowed is False
    assert shared.code == "DESKTOP_IDENTITY_REQUIRED"

    _, phone_perimeter, phone_token, _ = _paired(tmp_path / "phone", "iphone")
    phone = _authorize(phone_perimeter, phone_token,
                       "/api/jarvis/golden/market-live")
    assert phone.allowed is False
    assert phone.code == "DESKTOP_IDENTITY_REQUIRED"


def test_read_only_market_auth_rejects_lan_and_profile_disabled(tmp_path):
    pairing, perimeter, token, device_id = _paired(tmp_path)
    registry = tmp_path / "device_registry.json"
    before = hashlib.sha256(registry.read_bytes()).digest()

    lan = _authorize(perimeter, token, "/api/jarvis/golden/market-live",
                     source_ip="192.168.1.100")
    assert lan.allowed is False
    assert lan.code == "LOCAL_DESKTOP_REQUIRED"
    assert hashlib.sha256(registry.read_bytes()).digest() == before

    disabled = HttpPerimeter(
        auth_manager=perimeter.auth_manager,
        runtime_profile_provider=lambda: None,
    )
    result = _authorize(disabled, token, "/api/jarvis/golden/market-live")
    assert result.allowed is False
    assert result.code == "READ_ONLY_DISABLED_BY_PROFILE"
    assert pairing.get_device(device_id)["last_seen"]


def test_read_only_market_auth_accepts_loopback_desktop_without_touch(tmp_path):
    pairing, perimeter, token, device_id = _paired(tmp_path)
    registry = tmp_path / "device_registry.json"
    before = registry.read_bytes()
    last_seen = pairing.get_device(device_id)["last_seen"]

    local = _authorize(perimeter, token, "/api/jarvis/golden/market-live",
                       source_ip="127.0.0.1")

    assert local.allowed is True
    assert local.context["actor_id"] == "device:" + device_id
    assert registry.read_bytes() == before
    assert pairing.get_device(device_id)["last_seen"] == last_seen


def test_normal_auth_still_updates_device_last_seen_and_mutations_stay_high_risk(
    tmp_path, monkeypatch
):
    pairing, perimeter, token, device_id = _paired(tmp_path)
    previous = pairing.get_device(device_id)["last_seen"]
    monkeypatch.setattr("jarvis_core.device_pairing.time.time", lambda: previous + 10)

    result = _authorize(perimeter, token, "/api/mt5/auto_trade")

    assert result.allowed is True
    assert pairing.get_device(device_id)["last_seen"] == previous + 10
    assert result.context["route_class"] == "AUTHENTICATED_AND_AUTHORIZED"
