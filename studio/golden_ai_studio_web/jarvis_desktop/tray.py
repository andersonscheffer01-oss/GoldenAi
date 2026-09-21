"""System tray controls for the web desktop shell."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QStyle, QSystemTrayIcon


class JarvisTray(QSystemTrayIcon):
    def __init__(self, window, parent=None):
        icon = window.style().standardIcon(QStyle.SP_ComputerIcon)
        super().__init__(icon, parent or window)
        self.window = window
        self.setToolTip("JARVIS")
        menu = QMenu()
        self._add(menu, "Abrir Jarvis", window.restore_window)
        self._add(menu, "Ocultar Jarvis", window.hide)
        self._add(menu, "Restaurar", window.restore_window)
        self._add(menu, "Status", self.show_status)
        menu.addSeparator()
        self._add(menu, "Sair", window.exit_application)
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

    def show_status(self):
        state = "online" if self.window.core_origin else "offline"
        QMessageBox.information(self.window, "JARVIS Status",
                                f"Core: {state}\n{self.window.core_origin or ''}")

