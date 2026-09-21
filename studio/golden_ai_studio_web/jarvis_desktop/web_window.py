"""Native shell that renders the canonical jarvis_ui in QWebEngineView."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QStyle,
                               QSystemTrayIcon)
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                     QWebEngineScript)
from PySide6.QtWebEngineWidgets import QWebEngineView

from .settings import ui_url
from .boot_diagnostics import boot_log
from .tray import JarvisTray


class DesktopMainWindow(QMainWindow):
    def __init__(self, core_launcher, single_instance=None, device_token=None,
                 parent=None):
        super().__init__(parent)
        self.core_launcher = core_launcher
        self.single_instance = single_instance
        self.core_origin = core_launcher.origin
        self._explicit_exit = False
        self._cleaned = False
        self.settings = QSettings("GoldenAI", "JarvisDesktop")
        self.setWindowTitle("JARVIS")
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.setMinimumSize(900, 620)
        self.web_view = QWebEngineView(self)
        self.web_profile = self._create_web_profile()
        self.web_view.setPage(QWebEnginePage(self.web_profile, self.web_view))
        self._install_desktop_identity(device_token)
        self.web_view.page().renderProcessTerminated.connect(
            self._on_render_process_terminated)
        self._deny_web_media_capture()
        self._renderer_failures = []
        self._load_error_box = None
        self.setCentralWidget(self.web_view)
        self._restore_geometry()
        self.tray = JarvisTray(self)
        self.tray.show()
        self.web_view.loadFinished.connect(self._on_load_finished)
        self._load_ui()

    def _load_ui(self):
        target = ui_url(self.core_origin)
        boot_log(f"BOOT_13_UI_URL {target}")
        print(f"[JARVIS-DESKTOP] UI URL: {target}", flush=True)
        self.web_view.load(QUrl(target))

    def _on_load_finished(self, ok):
        if ok:
            if self._load_error_box:
                self._load_error_box.close()
                self._load_error_box = None
            return
        target = ui_url(self.core_origin)
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
        source = "window.__JARVIS_DESKTOP__ = true;"
        if device_token:
            source += (
                "localStorage.setItem('jarvis_device_token', "
                + json.dumps(device_token) + ");"
                "localStorage.removeItem('jarvis-device-token');")
        script.setSourceCode(source)
        self.web_view.page().scripts().insert(script)

    def _deny_web_media_capture(self):
        page = self.web_view.page()
        if hasattr(page, "permissionRequested"):
            page.permissionRequested.connect(lambda permission: permission.deny())
        if hasattr(page, "featurePermissionRequested"):
            page.featurePermissionRequested.connect(
                lambda origin, feature: page.setFeaturePermission(
                    origin, feature, QWebEnginePage.PermissionDeniedByUser))

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
        self.tray.hide()
        if self.single_instance:
            self.single_instance.close()
        self.core_launcher.stop_owned_core()
