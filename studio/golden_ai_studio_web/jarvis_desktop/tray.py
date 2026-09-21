"""System tray controls for the web desktop shell."""
from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .startup import is_enabled, set_enabled


class JarvisTray(QSystemTrayIcon):
    def __init__(self, window, parent=None):
        icon = window.style().standardIcon(QStyle.SP_ComputerIcon)
        super().__init__(icon, parent or window)
        self.window = window
        self.setToolTip("JARVIS")
        menu = QMenu()
        self._add(menu, "Abrir Jarvis", window.restore_window)
        self._add(menu, "Minimizar Jarvis", window.hide)
        self._add(menu, "Reiniciar Jarvis", window.restart_application)
        startup = QAction("Iniciar com Windows", menu)
        startup.setCheckable(True)
        startup.setChecked(is_enabled())
        startup.triggered.connect(self._toggle_startup)
        menu.addAction(startup)
        self.startup_action = startup
        menu.addSeparator()
        self._add(menu, "Encerrar Jarvis", window.exit_application)
        self.setContextMenu(menu)
        self.activated.connect(self._activated)

    @staticmethod
    def _add(menu, label, callback):
        action = QAction(label, menu)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.restore_window()

    def _toggle_startup(self, enabled):
        try:
            set_enabled(bool(enabled))
        except OSError as exc:
            self.startup_action.setChecked(not enabled)
            QMessageBox.warning(self.window, "JARVIS", f"Não foi possível atualizar o startup: {exc}")


    def show_status(self):
        state = "online" if self.window.core_origin else "offline"
        QMessageBox.information(self.window, "JARVIS Status",
                                f"Core: {state}\n{self.window.core_origin or ''}")
