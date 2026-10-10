"""Read-only device identity verification preserves canonical auth decisions."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis_core.device_pairing import DevicePairingService
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.gateway.gateway import Gateway
from jarvis_core.gateway.protocol import GatewayMessage, MessageType
from jarvis_desktop.identity import DesktopIdentityError, DesktopIdentityManager


def _paired_service(tmp_path):
    service = DevicePairingService(data_dir=str(tmp_path))
    code = service.create_pairing_code("127.0.0.1")
    service.validate_pairing_code(code, "127.0.0.1")
    device = service.complete_pairing("Desktop test", "desktop")
    assert device is not None
    return service, device["token"], device["device_id"]


def _registry_bytes(tmp_path):
    return (tmp_path / "device_registry.json").read_bytes()


@pytest.mark.parametrize("credential", ["", "malformed", "unknown-device-token"])
def test_invalid_device_credentials_have_same_read_only_and_normal_decision(
    tmp_path, credential
):
    service, _, _ = _paired_service(tmp_path)
    before = _registry_bytes(tmp_path)

    assert service.verify_device_token(credential, update_last_seen=False) is None
    assert service.verify_device_token(credential) is None
    assert _registry_bytes(tmp_path) == before


def test_valid_read_only_verification_matches_normal_and_does_not_write(tmp_path):
    service, token, device_id = _paired_service(tmp_path)
    path = tmp_path / "device_registry.json"
    before = path.read_bytes()
    expected_hash = hashlib.sha256(before).digest()
    device_before = service.get_device(device_id)

    readonly = service.verify_device_token(token, update_last_seen=False)
    assert readonly is not None
    assert readonly.device_id == device_id
    assert service.get_device(device_id)["last_seen"] == device_before["last_seen"]
    assert hashlib.sha256(path.read_bytes()).digest() == expected_hash

    normal = service.verify_device_token(token)
    assert normal is not None
    assert normal.device_id == readonly.device_id


def test_normal_verification_keeps_last_seen_persistence(tmp_path, monkeypatch):
    service, token, device_id = _paired_service(tmp_path)
    path = tmp_path / "device_registry.json"
    previous = service.get_device(device_id)["last_seen"]
    monkeypatch.setattr("jarvis_core.device_pairing.time.time", lambda: previous + 10)

    verified = service.verify_device_token(token)

    assert verified is not None
    assert service.get_device(device_id)["last_seen"] == previous + 10
    assert json.loads(path.read_text(encoding="utf-8"))[device_id]["last_seen"] == previous + 10


def test_revoked_device_is_rejected_in_both_modes_without_further_write(tmp_path):
    service, token, device_id = _paired_service(tmp_path)
    assert service.revoke_device(device_id)
    before = _registry_bytes(tmp_path)

    assert service.verify_device_token(token, update_last_seen=False) is None
    assert service.verify_device_token(token) is None
    assert _registry_bytes(tmp_path) == before


def test_read_only_authentication_does_not_change_registry_or_ip(tmp_path):
    service, token, device_id = _paired_service(tmp_path)
    auth = AuthManager(_token="shared-auth-test")
    auth.set_device_pairing_service(service)
    before = _registry_bytes(tmp_path)

    state = auth.authenticate(token, "127.0.0.1", update_device_last_seen=False)

    assert state.authenticated is True
    assert service.get_device(device_id)["ip_address"] == ""
    assert _registry_bytes(tmp_path) == before


def test_authenticate_device_preserves_normal_touch_and_supports_read_only(tmp_path):
    service, token, device_id = _paired_service(tmp_path)
    path = tmp_path / "device_registry.json"
    before = path.read_bytes()

    assert service.authenticate_device(
        token, "192.0.2.10", update_last_seen=False
    ) is True
    assert service.get_device(device_id)["ip_address"] == ""
    assert path.read_bytes() == before

    assert service.authenticate_device(token, "192.0.2.10") is True
    assert service.get_device(device_id)["ip_address"] == "192.0.2.10"
    assert path.read_bytes() != before


def test_registry_writer_audit_is_attributed_and_secret_safe(tmp_path):
    service, token, device_id = _paired_service(tmp_path)
    audit = MagicMock()
    service.set_audit_context(
        audit, lambda: {"runtime_instance_id": "runtime-test",
                        "runtime_profile": "web-ai-safe"})

    assert service.verify_device_token(token) is not None

    audit.add.assert_called_once()
    event = audit.add.call_args.kwargs
    envelope = event["envelope"]
    metadata = envelope["metadata"]
    assert envelope["operation"] == "device.verify_token"
    assert metadata["update_last_seen_requested"] is True
    assert metadata["fields_changed"] == ["last_seen"]
    assert metadata["runtime_instance_id"] == "runtime-test"
    assert metadata["device_fingerprint"] != device_id
    serialized = json.dumps(event)
    assert token not in serialized
    assert device_id not in serialized
    assert "token_hash" not in serialized


def test_registry_audit_records_pair_and_revocation_semantics(tmp_path):
    service = DevicePairingService(data_dir=str(tmp_path))
    audit = MagicMock()
    service.set_audit_context(audit)
    code = service.create_pairing_code("127.0.0.1")
    assert service.validate_pairing_code(code, "127.0.0.1")

    device = service.complete_pairing("Audit test", "desktop")
    assert device is not None
    assert audit.add.call_args.kwargs["envelope"]["operation"] == "device.pair"
    assert audit.add.call_args.kwargs["risk"] == "HIGH"

    assert service.revoke_device(device["device_id"])
    event = audit.add.call_args.kwargs
    assert event["envelope"]["operation"] == "device.revoke"
    assert event["envelope"]["metadata"]["fields_changed"] == [
        "revoked", "revoked_at"]
    assert device["token"] not in json.dumps(event)


@pytest.mark.parametrize(
    ("source_ip", "readonly", "expect_registry_change"),
    [("127.0.0.1", True, False), ("::1", True, False), ("192.0.2.5", True, True),
     ("127.0.0.1", False, True)],
)
def test_gateway_limits_read_only_device_auth_to_loopback_bootstrap(
    tmp_path, source_ip, readonly, expect_registry_change
):
    service, token, _ = _paired_service(tmp_path)
    auth = AuthManager(_token="shared-auth-test")
    gateway = Gateway(MagicMock(), auth_manager=auth)
    gateway.set_device_pairing(service)
    before = _registry_bytes(tmp_path)
    ws = MagicMock()
    message = GatewayMessage(
        type=MessageType.AUTH,
        payload={"token": token, "read_only_verification": readonly},
    )

    _, authenticated = asyncio.run(
        gateway._handle_message(ws, message.to_json(), None, False, source_ip)
    )

    assert authenticated is True
    assert (_registry_bytes(tmp_path) != before) is expect_registry_change


def test_native_desktop_bootstrap_requests_read_only_auth_over_loopback():
    ui_source = (ROOT / "jarvis_ui" / "src" / "gateway-adapter.js").read_text(
        encoding="utf-8"
    )
    identity_source = (ROOT / "jarvis_desktop" / "identity.py").read_text(
        encoding="utf-8"
    )
    assert "read_only_verification" not in ui_source
    assert 'GATEWAY_WS_URL = "wss://127.0.0.1:8766/ws"' in identity_source
    assert '"read_only_verification": True' in identity_source


def test_desktop_read_only_bootstrap_never_clears_or_repairs_identity():
    store = MagicMock()
    store.load_token.return_value = "stored-invalid-token"
    manager = DesktopIdentityManager(
        MagicMock(), store=store, http_post=MagicMock(), validator=lambda _: False
    )

    with pytest.raises(DesktopIdentityError, match="pairing não iniciado"):
        manager.ensure_identity(allow_pairing=False)

    store.clear.assert_not_called()
    store.save.assert_not_called()
    manager._http_post_override.assert_not_called()
