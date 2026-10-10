from __future__ import annotations

import asyncio
import io
import json
import os
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis_core.audit import AuditLog
from jarvis_core.device_pairing import Device, DevicePairingService
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.gateway.gateway import Gateway
from jarvis_core.lifecycle import CoreLifecycle
from jarvis_core.security import SecurityManager
from jarvis_desktop.core_launcher import CoreLaunchError, CoreLauncher


def _lifecycle(tmp_path, *, device_type="desktop", profile="web-ai-safe"):
    audit = AuditLog(tmp_path / "audit.db")
    pairing = DevicePairingService(data_dir=str(tmp_path / "unused-store"))
    token = "desktop-test-token"
    token_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
    device = Device(
        device_id="dev_test", device_name="Test Desktop", device_type=device_type,
        created_at=1, paired_at=1, last_seen=1, token_hash=token_hash,
    )
    pairing._devices[device.device_id] = device
    pairing._device_token_map[token_hash] = device.device_id
    auth = AuthManager(_token="shared-test-token")
    auth.set_device_pairing_service(pairing)
    security = SecurityManager(audit_log=audit)
    lifecycle = CoreLifecycle(
        runtime_profile=profile, auth_manager=auth, security_manager=security,
        audit_log=audit, pid=12345, parent_pid=54321,
        runtime_instance_id=str(uuid.uuid4()),
        started_at=datetime.now(timezone.utc).isoformat(),
        market_live_available=True,
    )
    return lifecycle, token, device, pairing, audit, security


def _request(lifecycle, token, **overrides):
    payload = {
        "runtime_instance_id": lifecycle.runtime_instance_id,
        "request_id": str(uuid.uuid4()),
        "issued_at": time.time(),
    }
    payload.update(overrides.pop("payload", {}))
    args = {
        "source_ip": "127.0.0.1",
        "authorization": "Bearer " + token,
        "origin": "",
        "sec_fetch_site": "",
        "content_type": "application/json",
    }
    args.update(overrides)
    return lifecycle.authorize_shutdown(payload, **args), payload


def test_runtime_metadata_is_ephemeral_instance_identity(tmp_path):
    lifecycle, *_ = _lifecycle(tmp_path)
    snapshot = lifecycle.snapshot()
    assert snapshot["runtime_instance_id"] == lifecycle.runtime_instance_id
    assert snapshot["pid"] == 12345
    assert snapshot["runtime_profile"] == "web-ai-safe"
    assert snapshot["lifecycle_state"] == "RUNNING"
    assert snapshot["owner"]["launcher_pid"] == 54321
    assert {"CORE_LIFECYCLE_CONTROL", "golden_market_live"} <= set(
        snapshot["capabilities"])


@pytest.mark.parametrize("overrides, expected", [
    ({"authorization": ""}, "AUTH_REQUIRED"),
    ({"authorization": "Bearer invalid"}, "DESKTOP_IDENTITY_REQUIRED"),
    ({"source_ip": "192.168.1.44"}, "LOOPBACK_REQUIRED"),
    ({"origin": "https://127.0.0.1:8765"}, "BROWSER_CALL_FORBIDDEN"),
    ({"sec_fetch_site": "same-origin"}, "BROWSER_CALL_FORBIDDEN"),
    ({"content_type": "text/plain"}, "JSON_REQUIRED"),
    ({"payload": {"runtime_instance_id": "old-instance"}},
     "RUNTIME_INSTANCE_MISMATCH"),
    ({"payload": {"issued_at": 0}}, "REQUEST_EXPIRED"),
])
def test_shutdown_rejects_unauthorized_requests(tmp_path, overrides, expected):
    lifecycle, token, *_ = _lifecycle(tmp_path)
    result, _ = _request(lifecycle, token, **overrides)
    assert result["ok"] is False
    assert result["error"] == expected
    assert lifecycle.snapshot()["lifecycle_state"] == "RUNNING"


def test_non_desktop_identity_lacks_lifecycle_capability(tmp_path):
    lifecycle, token, *_ = _lifecycle(tmp_path, device_type="iphone")
    result, _ = _request(lifecycle, token)
    assert result["error"] == "LIFECYCLE_CAPABILITY_REQUIRED"
    assert lifecycle.snapshot()["lifecycle_state"] == "RUNNING"


def test_wrong_runtime_profile_and_security_manager_deny(tmp_path):
    lifecycle, token, *_ = _lifecycle(tmp_path, profile="default")
    result, _ = _request(lifecycle, token)
    assert result["error"] == "RUNTIME_PROFILE_FORBIDDEN"

    lifecycle, token, _, _, _, security = _lifecycle(tmp_path / "denied")
    security.rules["core_lifecycle_control"] = "deny"
    result, _ = _request(lifecycle, token)
    assert result["error"] == "SECURITY_MANAGER_DENIED"


def test_shutdown_is_audited_and_request_id_is_single_use(tmp_path):
    lifecycle, token, _, pairing, audit, _ = _lifecycle(tmp_path)
    result, payload = _request(lifecycle, token)
    assert result["ok"] is True
    assert result["_http_status"] == 202
    assert result["runtime_instance_id"] == lifecycle.runtime_instance_id
    assert result["pid"] == 12345
    assert lifecycle.snapshot()["lifecycle_state"] == "SHUTDOWN_REQUESTED"
    replay, _ = _request(lifecycle, token, payload=payload)
    assert replay["error"] == "REQUEST_REPLAYED"
    assert pairing._devices["dev_test"].last_seen == 1
    assert not (tmp_path / "unused-store" / "device_registry.json").exists()
    statuses = {row["status"] for row in audit.recent(10)}
    assert "CORE_SHUTDOWN_ACCEPTED" in statuses
    assert "ALLOW" in statuses


def test_gateway_shutdown_exits_isolated_runtime_and_releases_ports(tmp_path):
    async def exercise():
        lifecycle, token, _, _, _, _ = _lifecycle(tmp_path)

        class QuietHandler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

        core_server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        core_port = core_server.server_address[1]

        def run_core():
            try:
                core_server.serve_forever()
            finally:
                core_server.server_close()

        core_thread = threading.Thread(target=run_core, daemon=True)
        core_thread.start()
        service = SimpleNamespace(
            runtime_profile=SimpleNamespace(name="web-ai-safe"),
            status=lambda: {"state": "IDLE"},
        )
        gateway = Gateway(
            service, host="127.0.0.1", port=0,
            runtime_metadata_provider=lifecycle.snapshot,
            lifecycle_controller=lifecycle, lifecycle_server=core_server,
        )
        await gateway.start()
        site = gateway._sites[0]
        gateway_port = site._server.sockets[0].getsockname()[1]
        try:
            import aiohttp

            async with aiohttp.ClientSession() as client:
                health = await client.get(f"http://127.0.0.1:{gateway_port}/health")
                health_data = await health.json()
                assert health_data["runtime_instance_id"] == lifecycle.runtime_instance_id
                assert health_data["pid"] == 12345
                response = await client.post(
                    f"http://127.0.0.1:{gateway_port}/core/shutdown",
                    json={"runtime_instance_id": lifecycle.runtime_instance_id,
                          "request_id": str(uuid.uuid4()), "issued_at": time.time()},
                    headers={"Authorization": "Bearer " + token},
                )
                reply = await response.json()
                assert response.status == 202
                assert reply["ok"] is True

                browser = await client.post(
                    f"http://127.0.0.1:{gateway_port}/core/shutdown",
                    json={"runtime_instance_id": lifecycle.runtime_instance_id,
                          "request_id": str(uuid.uuid4()), "issued_at": time.time()},
                    headers={"Authorization": "Bearer " + token,
                             "Origin": "http://127.0.0.1"},
                )
                assert browser.status == 403
                await browser.read()

            core_thread.join(timeout=3)
            assert not core_thread.is_alive()
            with socket.socket() as probe:
                probe.settimeout(0.2)
                assert probe.connect_ex(("127.0.0.1", core_port)) != 0
        finally:
            if core_thread.is_alive():
                core_server.shutdown()
                core_thread.join(timeout=2)
            await gateway.stop()
            with socket.socket() as probe:
                probe.settimeout(0.2)
                assert probe.connect_ex(("127.0.0.1", gateway_port)) != 0

    asyncio.run(exercise())


def test_launcher_refuses_legacy_orphan_without_competing_core(tmp_path):
    process = MagicMock()
    launcher = CoreLauncher(
        tmp_path, popen=MagicMock(return_value=process),
        runtime_profile="web-ai-safe",
        required_capabilities=("golden_market_live",),
    )

    def old_core_probe(_url):
        launcher._last_health = {
            "ok": True, "gateway": "running", "runtime_profile": "web-ai-safe",
        }
        return True

    launcher.probe = old_core_probe
    with pytest.raises(CoreLaunchError, match="transição humana única"):
        launcher.ensure_online()
    assert launcher.process is None


def test_launcher_cooperative_replacement_validates_instance_and_releases(tmp_path):
    launcher = CoreLauncher(tmp_path, timeout=1, lifecycle_token="device-token",
                            runtime_profile="web-ai-safe")
    health = {
        "runtime_instance_id": str(uuid.uuid4()), "pid": 654321,
        "runtime_profile": "web-ai-safe",
        "capabilities": ["CORE_LIFECYCLE_CONTROL"],
    }
    response = MagicMock(status=202)
    response.read.return_value = json.dumps({
        "ok": True, "runtime_instance_id": health["runtime_instance_id"],
        "pid": 654321,
    }).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    with patch("jarvis_desktop.core_launcher.urllib.request.urlopen",
               return_value=response) as urlopen, \
            patch.object(launcher, "_port_in_use", return_value=False), \
            patch.object(launcher, "_pid_exists", return_value=False):
        launcher._replace_stale_core(health)
    request = urlopen.call_args.args[0]
    assert request.full_url.endswith("/core/shutdown")
    assert request.get_header("Authorization") == "Bearer device-token"
    assert request.get_header("Origin") is None
    payload = json.loads(request.data)
    assert payload["runtime_instance_id"] == health["runtime_instance_id"]
    uuid.UUID(payload["request_id"])


def test_launcher_exit_shuts_down_adopted_core_without_local_process(tmp_path):
    launcher = CoreLauncher(tmp_path, timeout=1, lifecycle_token="device-token",
                            runtime_profile="web-ai-safe")
    health = {
        "runtime_instance_id": str(uuid.uuid4()), "pid": 654322,
        "runtime_profile": "web-ai-safe",
        "capabilities": ["CORE_LIFECYCLE_CONTROL"],
    }
    response = MagicMock(status=202)
    response.read.return_value = json.dumps({
        "ok": True, "runtime_instance_id": health["runtime_instance_id"],
        "pid": health["pid"],
    }).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    launcher._adopted_health = health
    with patch("jarvis_desktop.core_launcher.urllib.request.urlopen",
               return_value=response) as urlopen, \
            patch.object(launcher, "_port_in_use", return_value=False), \
            patch.object(launcher, "_pid_exists", return_value=False):
        assert launcher.stop_owned_core() is True
    assert urlopen.call_args.args[0].full_url.endswith("/core/shutdown")
    assert launcher._adopted_health is None


def test_launcher_records_spawn_and_unexpected_exit_without_blocking(tmp_path):
    class FakeProcess:
        pid = 4321
        stdout = io.StringIO("normal output\n")
        stderr = io.StringIO("Authorization: Bearer secret\ncrash detail\n")

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 17

    process = FakeProcess()
    (tmp_path / "server_agent.py").write_text("# test runtime", encoding="utf-8")
    launcher = CoreLauncher(
        tmp_path, popen=lambda *args, **kwargs: process,
        runtime_profile="web-ai-safe", probe=lambda _url: next(probes),
        ui_probe=lambda _url: True,
    )
    probes = iter((False, True))
    with patch("jarvis_desktop.core_launcher.boot_log") as boot_log, \
            patch.object(launcher, "_port_in_use", return_value=False), \
            patch("jarvis_desktop.core_launcher.time.sleep"):
        launcher.ensure_online()
    messages = [call.args[0] for call in boot_log.call_args_list]
    assert any(message.startswith("CORE_SPAWN ") for message in messages)
    assert any(message.startswith("CORE_SPAWNED ") for message in messages)
    assert any(message.startswith("CORE_EXIT ") and "unexpected" in message
               for message in messages)
    assert all("secret" not in message for message in messages)
