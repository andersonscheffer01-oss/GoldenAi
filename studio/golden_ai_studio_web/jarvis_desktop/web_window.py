"""Native shell that renders the canonical jarvis_ui in QWebEngineView."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, QUrl, Qt, Signal
from PySide6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QStyle,
                               QSystemTrayIcon)
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                     QWebEngineScript)
from PySide6.QtWebEngineWidgets import QWebEngineView

from .settings import market_url, ui_url
from .boot_diagnostics import boot_log
from .tray import JarvisTray


_UI_DIAGNOSTIC_REVISION = "20261004-panel-mt5-asset-select-3"
_UI_DIAGNOSTIC_SCRIPT = r"""(() => {
  const revisions = (suffix) => [...new Set(
    performance.getEntriesByType("resource").flatMap(({name}) => {
      try {
        const url = new URL(name, location.href);
        return url.pathname.endsWith(suffix) ? [url.searchParams.get("v") || ""] : [];
      } catch (_) { return []; }
    }).filter(Boolean)
  )].slice(-3);
  const normalized = (value) => String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
  const controls = [...document.querySelectorAll("button,[role='button']")];
  const labels = [...document.querySelectorAll("label,[role='combobox']")];
  const inputs = [...document.querySelectorAll("input")];
  return JSON.stringify({
    current_url: location.origin + location.pathname,
    asset_revisions: {
      javascript: revisions("/desktop-shell.js"),
      stylesheet: revisions("/desktop-shell.css")
    },
    old_controls: {
      select_button: controls.some((el) => normalized(el.innerText || el.getAttribute("aria-label")) === "selecionar ativo"),
      class_filter: labels.some((el) => normalized(el.innerText || el.getAttribute("aria-label")) === "classe"),
      search_field: inputs.some((el) => normalized(el.getAttribute("placeholder")) === "filtrar nome ou símbolo")
    },
    new_dropdown_present: document.querySelector(".d2PanelView [data-panel-asset-select]") instanceof HTMLSelectElement
  });
})()"""


def _sanitize_ui_runtime_diagnostic(payload):
    try:
        value = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    revisions = value.get("asset_revisions")
    revisions = revisions if isinstance(revisions, dict) else {}
    old_controls = value.get("old_controls")
    old_controls = old_controls if isinstance(old_controls, dict) else {}

    def revision_list(name):
        entries = revisions.get(name)
        if not isinstance(entries, list):
            return []
        return [item[:80] for item in entries[:3] if isinstance(item, str)]

    return {
        "current_url": value.get("current_url", "")[:512]
        if isinstance(value.get("current_url"), str) else "",
        "asset_revisions": {
            "javascript": revision_list("javascript"),
            "stylesheet": revision_list("stylesheet"),
        },
        "old_controls": {
            "select_button": old_controls.get("select_button") is True,
            "class_filter": old_controls.get("class_filter") is True,
            "search_field": old_controls.get("search_field") is True,
        },
        "new_dropdown_present": value.get("new_dropdown_present") is True,
    }


def _deny_web_media_capture(page):
    if hasattr(page, "permissionRequested"):
        page.permissionRequested.connect(lambda permission: permission.deny())
    if hasattr(page, "featurePermissionRequested"):
        page.featurePermissionRequested.connect(
            lambda origin, feature: page.setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionDeniedByUser))


class JarvisWebPage(QWebEnginePage):
    market_intelligence_requested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.runtime_js_errors = []
        self.runtime_js_messages = []

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        level_name = str(level)
        record = {"level": level_name, "message": str(message),
                  "line": int(line), "source": str(source)}
        self.runtime_js_messages.append(record)
        if "Error" in level_name or "error" in str(message).lower():
            self.runtime_js_errors.append(record)
        print("[JARVIS-DESKTOP] JS_CONSOLE "
              f"level={level_name} line={line} source={source} message={message}",
              flush=True)
        super().javaScriptConsoleMessage(level, message, line, source)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # noqa: N802
        if is_main_frame and url.scheme().lower() == "jarvis":
            if url.host().lower() == "open-market-intelligence" and url.path() in ("", "/"):
                self.market_intelligence_requested.emit()
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class MarketIntelligenceWindow(QMainWindow):
    closed = Signal()
    market_intelligence_requested = Signal()

    def __init__(self, core_origin, profile, device_token=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("JARVIS — Market Intelligence")
        self.setMinimumSize(1100, 700)
        self.core_origin = core_origin
        self._load_error_box = None
        self._load_started_url = ""
        self._size_to_available_screen()
        self.web_view = QWebEngineView(self)
        self.web_page = JarvisWebPage(profile, self.web_view)
        self.web_view.setPage(self.web_page)
        self.web_page.market_intelligence_requested.connect(
            self.market_intelligence_requested.emit)
        _deny_web_media_capture(self.web_page)
        self._install_desktop_identity(device_token)
        self.setCentralWidget(self.web_view)
        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadProgress.connect(
            lambda value: print(f"[JARVIS-DESKTOP] Market UI load progress={value}", flush=True))
        self.web_view.loadFinished.connect(self._on_load_finished)
        target = market_url(core_origin)
        self._load_started_url = target
        self.web_view.load(QUrl(target))

    def _on_load_started(self):
        self._load_started_url = self.web_page.url().toString()
        print(f"[JARVIS-DESKTOP] Market UI load started: {self._load_started_url}", flush=True)

    def _size_to_available_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(1500, 900)
            return
        area = screen.availableGeometry()
        width = max(self.minimumWidth(), min(1800, int(area.width() * 0.9)))
        height = max(self.minimumHeight(), min(1100, int(area.height() * 0.9)))
        self.resize(width, height)
        self.move(area.center() - self.rect().center())

    def _on_load_finished(self, ok):
        if ok:
            if self._load_error_box:
                self._load_error_box.close()
                self._load_error_box = None
            return
        target = market_url(self.core_origin)
        if self.web_page.url().isValid():
            self.web_page.runJavaScript(
                "JSON.stringify({href: location.href, ready: document.readyState, "
                "title: document.title})",
                lambda payload: self._handle_failed_load_probe(target, payload),
            )
            return
        self._show_load_error(target)

    def _handle_failed_load_probe(self, target, payload):
        try:
            state = json.loads(payload or "{}")
        except (TypeError, ValueError):
            state = {}
        if state.get("ready") == "complete" and str(state.get("href", "")).startswith(market_url(self.core_origin)):
            print("[JARVIS-DESKTOP] Market UI ignored non-fatal load failure: "
                  f"url={state.get('href')} ready={state.get('ready')} title={state.get('title')}", flush=True)
            return
        self._show_load_error(target)

    def _show_load_error(self, target):
        print(f"[JARVIS-DESKTOP] Market UI load failed: {target}", flush=True)
        box = QMessageBox(self)
        box.setWindowTitle("JARVIS - servidor Web indisponível")
        box.setIcon(QMessageBox.Warning)
        box.setText("A janela Market Intelligence não conseguiu carregar o Core Web.")
        box.setInformativeText(f"URL canônica tentada:\n{target}\n\nO Core não será encerrado.")
        box.setStandardButtons(QMessageBox.Retry | QMessageBox.Close)
        box.finished.connect(
            lambda result: self.web_view.reload() if result == QMessageBox.Retry else None)
        self._load_error_box = box
        box.open()

    def _install_desktop_identity(self, device_token):
        script = QWebEngineScript()
        script.setName("jarvis-desktop-capability")
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        source = (
            "window.__JARVIS_DESKTOP__ = true;"
            "window.__JARVIS_DESKTOP_OPEN_MARKET__ = function(){"
            "window.location.href='jarvis://open-market-intelligence';};"
        )
        if device_token:
            source += (
                "localStorage.setItem('jarvis_device_token', "
                + json.dumps(device_token) + ");"
                "localStorage.removeItem('jarvis-device-token');")
        script.setSourceCode(source)
        self.web_page.scripts().insert(script)

    def closeEvent(self, event):  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)


class DesktopMainWindow(QMainWindow):
    def __init__(self, core_launcher, single_instance=None, device_token=None,
                 parent=None):
        super().__init__(parent)
        self.core_launcher = core_launcher
        self.single_instance = single_instance
        self.core_origin = core_launcher.origin
        self.device_token = device_token
        self.market_window = None
        self._explicit_exit = False
        self._cleaned = False
        self.settings = QSettings("GoldenAI", "JarvisDesktop")
        self.setWindowTitle("JARVIS")
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.setMinimumSize(900, 620)
        self.web_view = QWebEngineView(self)
        self.web_profile = self._create_web_profile()
        self.web_page = JarvisWebPage(self.web_profile, self.web_view)
        self.web_view.setPage(self.web_page)
        self.web_page.market_intelligence_requested.connect(
            self.open_market_intelligence)
        self._install_desktop_identity(device_token)
        self.web_view.page().renderProcessTerminated.connect(
            self._on_render_process_terminated)
        self._deny_web_media_capture()
        self._renderer_failures = []
        self._load_error_box = None
        self._load_started_url = ""
        self.setCentralWidget(self.web_view)
        self._restore_geometry()
        self.tray = JarvisTray(self)
        self.tray.show()
        self.web_view.loadFinished.connect(self._on_load_finished)
        self._load_ui()

    def _load_ui(self):
        target = ui_url(self.core_origin)
        self._load_started_url = target
        boot_log(f"BOOT_13_UI_URL {target}")
        print(f"[JARVIS-DESKTOP] UI URL: {target}", flush=True)
        self.web_view.load(QUrl(target))

    def _on_load_finished(self, ok):
        if ok:
            if self._load_error_box:
                self._load_error_box.close()
                self._load_error_box = None
            # Temporary bounded probe: remove after the live Qt revision is identified.
            self.web_page.runJavaScript(
                _UI_DIAGNOSTIC_SCRIPT, self._record_ui_runtime_diagnostic)
            return
        target = ui_url(self.core_origin)
        if self.web_page.url().isValid():
            self.web_page.runJavaScript(
                "JSON.stringify({href: location.href, ready: document.readyState, "
                "title: document.title})",
                lambda payload: self._handle_failed_load_probe(target, payload),
            )
            return
        self._show_load_error(target)

    def _record_ui_runtime_diagnostic(self, payload):
        details = _sanitize_ui_runtime_diagnostic(payload)
        if details is None:
            boot_log("UI_RUNTIME_DIAGNOSTIC invalid_payload")
            return
        details["expected_revision"] = _UI_DIAGNOSTIC_REVISION
        boot_log("UI_RUNTIME_DIAGNOSTIC " + json.dumps(details, sort_keys=True))

    def _handle_failed_load_probe(self, target, payload):
        try:
            state = json.loads(payload or "{}")
        except (TypeError, ValueError):
            state = {}
        if state.get("ready") == "complete" and str(state.get("href", "")).startswith(ui_url(self.core_origin)):
            print("[JARVIS-DESKTOP] UI ignored non-fatal load failure: "
                  f"url={state.get('href')} ready={state.get('ready')} title={state.get('title')}", flush=True)
            return
        self._show_load_error(target)

    def _show_load_error(self, target):
        print(f"[JARVIS-DESKTOP] UI load failed: {target}", flush=True)
        box = QMessageBox(self)
        box.setWindowTitle("JARVIS - servidor Web indisponível")
        box.setIcon(QMessageBox.Warning)
        box.setText("Não foi possível carregar a interface do Jarvis.")
        box.setInformativeText(f"URL tentada:\n{target}\n\nO Core não será encerrado.")
        box.setStandardButtons(QMessageBox.Retry | QMessageBox.Close)
        box.finished.connect(
            lambda result: self._load_ui() if result == QMessageBox.Retry else None)
        self._load_error_box = box
        box.open()

    def _create_web_profile(self):
        profile = QWebEngineProfile("GoldenJarvisDesktop", self)
        data_root = Path(QStandardPaths.writableLocation(
            QStandardPaths.AppDataLocation)) / "webengine"
        profile.setPersistentStoragePath(str(data_root / "storage"))
        profile.setCachePath(str(data_root / "cache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.ForcePersistentCookies)
        return profile

    def _install_desktop_identity(self, device_token):
        script = QWebEngineScript()
        script.setName("jarvis-desktop-capability")
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        source = (
            "window.__JARVIS_DESKTOP__ = true;"
            "window.__JARVIS_DESKTOP_OPEN_MARKET__ = function(){"
            "window.location.href='jarvis://open-market-intelligence';};"
        )
        if device_token:
            source += (
                "localStorage.setItem('jarvis_device_token', "
                + json.dumps(device_token) + ");"
                "localStorage.removeItem('jarvis-device-token');")
        script.setSourceCode(source)
        self.web_page.scripts().insert(script)

    def _deny_web_media_capture(self):
        _deny_web_media_capture(self.web_page)

    def open_market_intelligence(self):
        if self.market_window is not None:
            self.market_window.showNormal()
            self.market_window.raise_()
            self.market_window.activateWindow()
            return self.market_window
        market_window = MarketIntelligenceWindow(
            self.core_origin,
            self.web_profile,
            device_token=self.device_token,
            parent=self,
        )
        self.market_window = market_window
        market_window.closed.connect(self._market_window_closed)
        market_window.market_intelligence_requested.connect(
            self.open_market_intelligence)
        market_window.show()
        market_window.raise_()
        market_window.activateWindow()
        return market_window

    def _market_window_closed(self):
        self.market_window = None

    def _on_render_process_terminated(self, status, exit_code):
        now = time.monotonic()
        self._renderer_failures = [stamp for stamp in self._renderer_failures
                                   if now - stamp < 60]
        self._renderer_failures.append(now)
        print("[JARVIS-DESKTOP] Renderer terminated: "
              f"status={status} exit_code={exit_code}", flush=True)
        repeated = len(self._renderer_failures) >= 3
        message = ("A interface Web foi encerrada repetidamente. O Core continua ativo."
                   if repeated else
                   "A interface Web foi encerrada. O Core continua ativo e pode ser recarregado.")
        choice = QMessageBox.warning(
            self, "JARVIS - interface interrompida", message,
            QMessageBox.Retry | QMessageBox.Close, QMessageBox.Retry)
        if choice == QMessageBox.Retry:
            self._load_ui()

    def _restore_geometry(self):
        geometry = self.settings.value("window/geometry")
        if geometry and self.restoreGeometry(geometry):
            return
        self.resize(1280, 820)
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):  # noqa: N802
        if not self._explicit_exit:
            self.settings.setValue("window/geometry", self.saveGeometry())
            event.ignore()
            self.hide()
            self.tray.showMessage("JARVIS", "O Jarvis continua disponível na bandeja.",
                                  QSystemTrayIcon.Information, 1800)
            return
        event.accept()

    def exit_application(self):
        self._explicit_exit = True
        self.cleanup()
        self.close()
        QApplication.instance().quit()

    def restart_application(self):
        """Restart only this Desktop shell and any Core it owns."""
        self._explicit_exit = True
        self.cleanup()
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--hidden"]
        else:
            command = [sys.executable, "-m", "jarvis_desktop.web_app", "--hidden"]
        subprocess.Popen(command, cwd=str(self.core_launcher.root),
                         env=os.environ.copy(),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        QApplication.instance().quit()

    def cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        self.settings.setValue("window/geometry", self.saveGeometry())
        if self.market_window is not None:
            market_window = self.market_window
            self.market_window = None
            market_window.close()
        self.tray.hide()
        if self.single_instance:
            self.single_instance.close()
        self.core_launcher.stop_owned_core()
