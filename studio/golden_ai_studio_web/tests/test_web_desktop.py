"""Architecture and lifecycle tests for the QWebEngine Desktop client."""
from __future__ import annotations

import os
import json
import subprocess
import sys
import uuid
import ssl
import urllib.error
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QCloseEvent
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWidgets import QApplication, QMessageBox

from jarvis_desktop.core_launcher import (CoreLaunchError, CoreLauncher,
                                          HTTPS_HEALTH_URL, HTTPS_UI_ORIGIN)
from jarvis_desktop.identity import (DesktopIdentityManager,
                                     PAIRING_CODE_URL, PAIRING_CONFIRM_URL)
from jarvis_desktop.settings import candidate_origins, market_url, ui_url
from jarvis_desktop.single_instance import SingleInstance
from jarvis_desktop.web_window import (DesktopMainWindow,
                                       _UI_DIAGNOSTIC_REVISION,
                                       _UI_DIAGNOSTIC_SCRIPT)


ROOT = Path(__file__).resolve().parent.parent


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = 0
        self.killed = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed += 1
        self.returncode = -9


def test_online_core_is_reused_without_starting_server():
    popen = MagicMock()
    launcher = CoreLauncher(ROOT, popen=popen,
                            probe=lambda origin: origin.startswith("https://"),
                            ui_probe=lambda url: True)
    assert launcher.ensure_online() == "https://127.0.0.1:8765"
    assert launcher.owns_core is False
    popen.assert_not_called()


def test_gateway_idle_payload_is_healthy():
    payload = b'{"ok":true,"gateway":"running","connections":0,' \
              b'"sessions":0,"service_state":"IDLE",' \
              b'"runtime_profile":"web-ai-safe"}'
    response = MagicMock(status=200)
    response.read.return_value = payload
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    launcher = CoreLauncher(ROOT)
    with patch("jarvis_desktop.core_launcher.urllib.request.urlopen",
               return_value=response) as urlopen:
        assert launcher.probe(HTTPS_HEALTH_URL) is True
    assert urlopen.call_args.args[0].full_url == HTTPS_HEALTH_URL


def test_tls_context_reuses_local_ca_without_disabling_verification():
    launcher = CoreLauncher(ROOT)
    context = launcher._ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_invalid_certificate_fails_closed():
    launcher = CoreLauncher(ROOT)
    certificate_error = ssl.SSLCertVerificationError(
        1, "certificate verify failed")
    with patch("jarvis_desktop.core_launcher.urllib.request.urlopen",
               side_effect=urllib.error.URLError(certificate_error)):
        assert launcher.probe(HTTPS_HEALTH_URL) is False


def test_offline_core_starts_exactly_one_existing_runtime():
    process = FakeProcess()
    probes = iter([False, False, True])
    popen = MagicMock(return_value=process)
    launcher = CoreLauncher(ROOT, popen=popen, timeout=2,
                            probe=lambda origin: next(probes, True),
                            ui_probe=lambda url: True)
    with patch.object(launcher, "_port_in_use", return_value=False), \
            patch("jarvis_desktop.core_launcher.time.sleep", return_value=None):
        assert launcher.ensure_online().endswith(":8765")
    assert popen.call_count == 1
    command = popen.call_args.args[0]
    assert command[1] == str(ROOT / "server_agent.py")
    assert launcher.owns_core is True


def test_frozen_desktop_uses_external_python_for_core(monkeypatch):
    python_path = ROOT.parents[1] / ".venv" / "Scripts" / "python.exe"
    monkeypatch.setattr("jarvis_desktop.core_launcher.sys.frozen", True,
                        raising=False)
    launcher = CoreLauncher(ROOT, popen=MagicMock())
    assert launcher.python_executable == str(python_path)


def test_owned_core_is_stopped_but_reused_core_is_not():
    owned = CoreLauncher(ROOT, probe=lambda origin: False)
    process = FakeProcess()
    owned.process = process
    assert owned.stop_owned_core() is False
    assert process.terminated == 0
    assert process.killed == 0
    assert owned.process is process

    reused = CoreLauncher(ROOT, probe=lambda origin: True,
                          ui_probe=lambda url: True)
    reused.ensure_online()
    reused.stop_owned_core()
    assert reused.owns_core is False


def test_second_instance_signals_first_instead_of_listening_twice():
    app = QApplication.instance() or QApplication([])
    name = "JarvisDesktopTest_" + uuid.uuid4().hex
    first = SingleInstance(name)
    second = SingleInstance(name)
    activated = []
    first.activate_requested.connect(lambda: activated.append(True))
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        for _ in range(10):
            app.processEvents()
        assert activated
    finally:
        second.close()
        first.close()


def test_close_hides_to_tray_and_does_not_stop_core():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    window = DesktopMainWindow(launcher)
    window.tray.showMessage = MagicMock()
    window.show()
    app.processEvents()
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() is False
    assert window.isHidden()
    launcher.stop_owned_core.assert_not_called()
    window._explicit_exit = True
    window.cleanup()


def test_explicit_exit_cleans_desktop_and_owned_core_once():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    instance = MagicMock()
    window = DesktopMainWindow(launcher, instance)
    with patch.object(app, "quit"):
        window.exit_application()
        window.cleanup()
    launcher.stop_owned_core.assert_called_once()
    instance.close.assert_called_once()


def test_desktop_marker_is_injected_before_page_scripts():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    window = DesktopMainWindow(launcher)
    try:
        scripts = window.web_view.page().scripts().toList()
        marker = next(script for script in scripts
                      if script.name() == "jarvis-desktop-capability")
        assert marker.injectionPoint() == QWebEngineScript.DocumentCreation
        assert "__JARVIS_DESKTOP__ = true" in marker.sourceCode()
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_desktop_identity_is_injected_at_document_creation():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    window = DesktopMainWindow(launcher, device_token="test-device-token")
    try:
        scripts = window.web_view.page().scripts().toList()
        marker = next(script for script in scripts
                      if script.name() == "jarvis-desktop-capability")
        assert marker.injectionPoint() == QWebEngineScript.DocumentCreation
        assert "jarvis_device_token" in marker.sourceCode()
        assert "jarvis-device-token" in marker.sourceCode()
        assert window.web_profile.isOffTheRecord() is False
        assert window.web_profile.persistentStoragePath()
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_market_intelligence_is_single_instance_and_closes_independently():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    window = DesktopMainWindow(launcher)
    try:
        window.show()
        market = window.open_market_intelligence()
        assert market.windowTitle() == "JARVIS — Market Intelligence"
        assert market.web_page.profile() is window.web_profile
        assert window.open_market_intelligence() is market
        assert window.market_window is market

        market.close()
        app.processEvents()
        assert window.market_window is None
        assert not window.isHidden()
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_market_window_loads_existing_golden_web_market_surface():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "https://192.0.2.10:8765"
    window = DesktopMainWindow(launcher)
    try:
        market = window.open_market_intelligence()
        assert market_url(launcher.origin) == "https://192.0.2.10:8765/market.html"
        assert (ROOT / "market.html").is_file()
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_market_page_captures_javascript_console_diagnostics():
    source = (ROOT / "jarvis_desktop" / "web_window.py").read_text(encoding="utf-8")
    assert "def javaScriptConsoleMessage" in source
    assert "runtime_js_errors" in source
    assert "_handle_failed_load_probe" in source
    assert "document.readyState" in source


def test_desktop_load_records_bounded_qt_asset_diagnostic():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    window = DesktopMainWindow(launcher)
    try:
        run_javascript = MagicMock()
        window.web_page.runJavaScript = run_javascript
        with patch("jarvis_desktop.web_window.boot_log") as boot_log:
            window._on_load_finished(True)

            script, callback = run_javascript.call_args.args
            assert script == _UI_DIAGNOSTIC_SCRIPT
            assert "performance.getEntriesByType(\"resource\")" in script
            assert "localStorage" not in script
            assert "document.cookie" not in script
            assert "innerText" in script
            assert "JSON.stringify" in script

            callback(json.dumps({
                "current_url": "https://127.0.0.1:8765/jarvis_ui/jarvis.html",
                "asset_revisions": {
                    "javascript": [_UI_DIAGNOSTIC_REVISION],
                    "stylesheet": [_UI_DIAGNOSTIC_REVISION],
                },
                "old_controls": {
                    "select_button": False,
                    "class_filter": False,
                    "search_field": True,
                },
                "new_dropdown_present": True,
                "private_content": "must not reach log",
            }))

        record = boot_log.call_args.args[0]
        assert record.startswith("UI_RUNTIME_DIAGNOSTIC ")
        assert _UI_DIAGNOSTIC_REVISION in record
        assert '"search_field": true' in record
        assert '"new_dropdown_present": true' in record
        assert "must not reach log" not in record
        assert "private_content" not in record
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


class _MemoryCredentialStore:
    def __init__(self, token=None):
        self.token = token
        self.device_id = None
        self.cleared = 0

    def load_token(self):
        return self.token

    def save(self, token, device_id):
        self.token = token
        self.device_id = device_id

    def clear(self):
        self.token = None
        self.cleared += 1


def test_desktop_identity_pairs_once_then_reuses_canonical_token():
    store = _MemoryCredentialStore()
    posts = []

    def post(url, payload):
        posts.append((url, payload))
        if url == PAIRING_CODE_URL:
            return {"ok": True, "code": "PAIRCODE"}
        return {"ok": True, "token": "gateway-token", "device_id": "dev-1"}

    manager = DesktopIdentityManager(
        MagicMock(), store=store, http_post=post,
        validator=lambda token: token == "gateway-token")
    assert manager.ensure_identity() == "gateway-token"
    assert store.device_id == "dev-1"
    assert [url for url, _ in posts] == [PAIRING_CODE_URL, PAIRING_CONFIRM_URL]

    posts.clear()
    assert manager.ensure_identity() == "gateway-token"
    assert posts == []


def test_rejected_desktop_identity_is_cleared_and_repaired():
    store = _MemoryCredentialStore("expired-token")
    replies = iter([
        {"ok": True, "code": "PAIRCODE"},
        {"ok": True, "token": "fresh-token", "device_id": "dev-2"},
    ])
    manager = DesktopIdentityManager(
        MagicMock(), store=store,
        http_post=lambda url, payload: next(replies),
        validator=lambda token: token == "fresh-token")
    assert manager.ensure_identity() == "fresh-token"
    assert store.cleared == 1


def test_renderer_crash_can_reload_without_stopping_core():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "http://127.0.0.1:9"
    window = DesktopMainWindow(launcher)
    window.web_view.load = MagicMock()
    try:
        with patch("jarvis_desktop.web_window.QMessageBox.warning",
                   return_value=QMessageBox.Retry):
            window._on_render_process_terminated("Crashed", 9)
        window.web_view.load.assert_called_once()
        launcher.stop_owned_core.assert_not_called()
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_desktop_voice_never_constructs_browser_speech_recognition():
    voice_uri = (ROOT / "jarvis_ui" / "src" / "voice.js").as_uri()
    script = (
        "globalThis.window={__JARVIS_DESKTOP__:true," 
        "SpeechRecognition:class{constructor(){globalThis.calls++}}," 
        "speechSynthesis:{getVoices:()=>[]}};globalThis.calls=0;"
        f"const m=await import('{voice_uri}');"
        "const v=m.createVoice({onError:()=>{}});v.start(false);"
        "console.log(globalThis.calls);"
    )
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            capture_output=True, text=True, timeout=10, check=True)
    assert result.stdout.strip() == "0"


def test_normal_web_voice_behavior_still_uses_supported_recognizer():
    voice_uri = (ROOT / "jarvis_ui" / "src" / "voice.js").as_uri()
    script = (
        "globalThis.window={SpeechRecognition:class{constructor(){globalThis.calls++;}" 
        "start(){}},speechSynthesis:{getVoices:()=>[]}};globalThis.calls=0;"
        f"const m=await import('{voice_uri}');"
        "const v=m.createVoice({});v.start(false);console.log(globalThis.calls);"
    )
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            capture_output=True, text=True, timeout=10, check=True)
    assert result.stdout.strip() == "1"


def test_desktop_voice_adapter_calls_existing_voice_service():
    adapter_uri = (ROOT / "jarvis_ui" / "src" / "desktop-voice.js").as_uri()
    script = (
        "const calls=[];const gateway={httpPost:async(p)=>{calls.push(p);"
        "if(p.endsWith('/status'))return {ok:true,state:'WAITING_WAKE',last_event:{id:0}};"
        "return {ok:true};}};"
        f"const m=await import('{adapter_uri}');"
        "const v=m.createDesktopVoiceClient({gateway});await v.start();v.dispose();"
        "console.log(JSON.stringify(calls));"
    )
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            capture_output=True, text=True, timeout=10, check=True)
    calls = json.loads(result.stdout)
    assert calls == ["/api/jarvis/voice-service/status",
                     "/api/jarvis/voice-service/start",
                     "/api/jarvis/voice-service/listen"]


def test_desktop_mic_reuses_running_voice_service_and_requests_capture():
    adapter_uri = (ROOT / "jarvis_ui" / "src" / "desktop-voice.js").as_uri()
    script = (
        "const calls=[];const states=[];const gateway={httpPost:async(p)=>{calls.push(p);"
        "if(p.endsWith('/status'))return {ok:true,running:true,state:'WAITING_WAKE',last_event:{id:0}};"
        "if(p.endsWith('/listen'))return {ok:true,running:true,capture_requested:true};"
        "throw new Error('unexpected start');}};"
        f"const m=await import('{adapter_uri}');"
        "const v=m.createDesktopVoiceClient({gateway,onState:s=>states.push(s)});"
        "console.log(JSON.stringify({ok:await v.start(),calls,states}));v.dispose();"
    )
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            capture_output=True, text=True, timeout=10, check=True)
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["calls"] == ["/api/jarvis/voice-service/status",
                                "/api/jarvis/voice-service/listen"]
    assert "LISTENING" in payload["states"]


def test_desktop_continuous_voice_observes_without_requesting_capture():
    adapter_uri = (ROOT / "jarvis_ui" / "src" / "desktop-voice.js").as_uri()
    script = (
        "const calls=[];const gateway={httpPost:async(p)=>{calls.push(p);"
        "return {ok:true,running:true,state:'WAITING_WAKE',last_event:{id:0}};}};"
        f"const m=await import('{adapter_uri}');"
        "const v=m.createDesktopVoiceClient({gateway});"
        "await v.start({capture:false});console.log(JSON.stringify(calls));v.dispose();"
    )
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(result.stdout) == ["/api/jarvis/voice-service/status"]


def test_desktop_always_connects_gateway_without_changing_web_preference():
    source = (ROOT / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "settings.autoConnect || isJarvisDesktop" in source


def test_ui_url_is_canonical_and_no_desktop_copy_exists():
    assert HTTPS_HEALTH_URL == "https://127.0.0.1:8766/health"
    assert HTTPS_UI_ORIGIN == "https://127.0.0.1:8765"
    assert ui_url(HTTPS_UI_ORIGIN) == (
        "https://127.0.0.1:8765/jarvis_ui/jarvis.html")
    assert (ROOT / "jarvis_ui" / "jarvis.html").is_file()
    assert not (ROOT / "jarvis_desktop" / "jarvis_ui").exists()


def test_market_url_points_to_existing_golden_web_surface():
    assert market_url(HTTPS_UI_ORIGIN) == "https://127.0.0.1:8765/market.html"
    assert (ROOT / "market.html").is_file()


def test_desktop_never_falls_back_to_lan_ui_origin():
    attempted = []

    def ui_probe(url):
        attempted.append(url)
        return "192.168.1.100" in url

    launcher = CoreLauncher(
        ROOT, probe=lambda url: True, ui_probe=ui_probe,
        host_provider=lambda: "192.168.1.100")
    with pytest.raises(CoreLaunchError, match="jarvis_ui não respondeu"):
        launcher.ensure_online()
    assert attempted == ["https://127.0.0.1:8765/jarvis_ui/jarvis.html"]
    assert launcher.owns_core is False


def test_lan_enabled_http_listener_addresses_include_loopback(monkeypatch):
    from jarvis_core.lan_config import LanConfig

    lan = object.__new__(LanConfig)
    lan._enabled = True
    lan._bind_address = "192.0.2.15"

    assert lan.http_bind_addresses() == ("127.0.0.1", "192.0.2.15")


def test_local_http_listener_address_is_loopback_when_lan_is_disabled():
    from jarvis_core.lan_config import LanConfig

    lan = object.__new__(LanConfig)
    lan._enabled = False
    lan._bind_address = "127.0.0.1"
    assert lan.http_bind_addresses() == ("127.0.0.1",)


def test_desktop_launcher_does_not_discover_or_use_lan_ui_fallback():
    source = (ROOT / "jarvis_desktop" / "core_launcher.py").read_text(encoding="utf-8")
    assert "192.168.1.100" not in source
    assert "get_best_private_ip" not in source
    assert 'return ("127.0.0.1",)' in source


def test_ui_load_failure_offers_retry_without_stopping_core():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "https://192.0.2.10:8765"
    window = DesktopMainWindow(launcher)
    try:
        window._on_load_finished(False)
        assert window._load_error_box is not None
        assert "192.0.2.10" in window._load_error_box.informativeText()
        launcher.stop_owned_core.assert_not_called()
        window._load_error_box.close()
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_tls_mode_never_offers_http(monkeypatch):
    monkeypatch.setenv("GOLDEN_SSL", "1")
    monkeypatch.delenv("GOLDEN_DESKTOP_ORIGIN", raising=False)
    assert candidate_origins() == ("https://127.0.0.1:8765",)


def test_desktop_has_no_direct_core_or_tool_bypass():
    sources = "\n".join(
        (ROOT / "jarvis_desktop" / name).read_text(encoding="utf-8")
        for name in ("web_app.py", "web_window.py", "tray.py", "core_launcher.py")
    )
    forbidden = ("JarvisService", "ToolRegistry", "SecurityManager", "get_brain",
                 "execute_tool(", "MetaTrader5", "ollama", "VoiceService")
    assert all(term not in sources for term in forbidden)


def test_start_hidden_argument_is_supported():
    from jarvis_desktop.web_app import build_parser
    assert build_parser().parse_args(["--hidden"]).hidden is True


def test_tray_exposes_required_lifecycle_actions():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "https://127.0.0.1:8765"
    window = DesktopMainWindow(launcher)
    try:
        labels = [action.text() for action in window.tray.contextMenu().actions()]
        assert "Abrir Jarvis" in labels
        assert "Minimizar Jarvis" in labels
        assert "Reiniciar Jarvis" in labels
        assert "Iniciar com Windows" in labels
        assert "Encerrar Jarvis" in labels
    finally:
        window._explicit_exit = True
        window.cleanup()
        window.close()


def test_restart_spawns_same_desktop_entrypoint_without_touching_reused_core():
    app = QApplication.instance() or QApplication([])
    launcher = MagicMock()
    launcher.origin = "https://127.0.0.1:8765"
    launcher.root = ROOT
    window = DesktopMainWindow(launcher)
    try:
        with patch("jarvis_desktop.web_window.subprocess.Popen") as popen, \
                patch.object(app, "quit"):
            window.restart_application()
        popen.assert_called_once()
        assert popen.call_args.args[0][-3:] == ["-m", "jarvis_desktop.web_app", "--hidden"]
        launcher.stop_owned_core.assert_called_once()
    finally:
        window.close()
