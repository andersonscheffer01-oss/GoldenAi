"""Barra superior propria para janela frameless (drag + controles)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class TitleBar(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setFixedHeight(42)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        self.gold = QLabel("GOLDEN")
        self.gold.setProperty("class", "brandGold")
        self.cyan = QLabel("JARVIS")
        self.cyan.setProperty("class", "brandCyan")
        layout.addWidget(self.gold)
        layout.addWidget(self.cyan)
        layout.addStretch(1)
        self.net = QLabel("● OFFLINE")
        self.net.setProperty("class", "net")
        self.mode = QLabel("SHADOW MODE")
        self.mode.setProperty("class", "mode")
        layout.addWidget(self.net)
        layout.addWidget(self.mode)
        self.retry = QPushButton("TENTAR NOVAMENTE")
        self.retry.setProperty("class", "abtn")
        self.retry.setVisible(False)
        layout.addWidget(self.retry)
        self._drag_pos = None
        for label, slot in (("–", self._min), ("▢", self._max), ("×", self._close)):
            btn = QPushButton(label)
            btn.setProperty("class", "tbtn")
            btn.setFixedSize(34, 30)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def _min(self):
        self._window.showMinimized()

    def _max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def _close(self):
        self._window.request_close()

    def mousePressEvent(self, event):  # noqa: N802 - assinatura Qt
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - assinatura Qt
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            if not self._window.isMaximized():
                self._window.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - assinatura Qt
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def set_online(self, online):
        self.net.setText("● ONLINE" if online else "● OFFLINE")
        self.net.setStyleSheet("color:#22d3ee;" if online else "color:#f46868;")
