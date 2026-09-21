"""TitleBar V4: Frameless window controls + brand + mode switcher + drag."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget, QSizePolicy
from PySide6.QtGui import QMouseEvent

from ..theme_v4 import (
    GOLD, CYAN, BG_PANEL, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BAD, MONO_FONT
)


class TitleBarV4(QWidget):
    """Barra de título customizada para janela frameless."""

    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()
    retryRequested = Signal()

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setFixedHeight(48)
        self.setObjectName("titleBarV4")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)

        # Brand
        self.gold = QLabel("GOLDEN")
        self.gold.setProperty("class", "brandGold")
        self.cyan = QLabel("JARVIS")
        self.cyan.setProperty("class", "brandCyan")
        layout.addWidget(self.gold)
        layout.addWidget(self.cyan)

        # Separador visual
        sep = QLabel("|")
        sep.setProperty("class", "muted")
        sep.setStyleSheet("font-size: 14px; font-weight: 300;")
        layout.addWidget(sep)

        # Mode Switcher (será injetado depois)
        self.mode_switcher = None
        self.mode_switcher_container = QWidget()
        self.mode_switcher_layout = QHBoxLayout(self.mode_switcher_container)
        self.mode_switcher_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.mode_switcher_container)

        layout.addStretch(1)

        # Status de rede
        self.net = QLabel("● OFFLINE")
        self.net.setProperty("class", "netStatus")
        self.net.setStyleSheet(f"color: {BAD};")
        layout.addWidget(self.net)

        # Modo label (SHADOW MODE etc)
        self.mode_label = QLabel("SHADOW MODE")
        self.mode_label.setProperty("class", "modeTag")
        layout.addWidget(self.mode_label)

        # Botão retry
        self.retry = QPushButton("TENTAR NOVAMENTE")
        self.retry.setProperty("class", "actionBtn")
        self.retry.setVisible(False)
        self.retry.clicked.connect(self.retryRequested.emit)
        layout.addWidget(self.retry)

        # Controles de janela
        self._create_window_controls(layout)

        # Drag
        self._drag_pos = None
        self._drag_active = False

    def _create_window_controls(self, layout):
        """Cria botões minimizar, maximizar, fechar."""
        self.btn_min = QPushButton("—")
        self.btn_min.setProperty("class", "titleBtn")
        self.btn_min.setToolTip("Minimizar (Win+↓)")
        self.btn_min.clicked.connect(self._on_minimize)

        self.btn_max = QPushButton("▢")
        self.btn_max.setProperty("class", "titleBtn")
        self.btn_max.setToolTip("Maximizar/Restaurar (Win+↑)")
        self.btn_max.clicked.connect(self._on_maximize)

        self.btn_close = QPushButton("×")
        self.btn_close.setProperty("class", "titleBtn closeBtn")
        self.btn_close.setToolTip("Fechar (Alt+F4)")
        self.btn_close.clicked.connect(self._on_close)

        for btn in (self.btn_min, self.btn_max, self.btn_close):
            btn.setCursor(Qt.PointingHandCursor)
            layout.addWidget(btn)

    def set_mode_switcher(self, switcher):
        """Conecta o ModeSwitcher."""
        self.mode_switcher = switcher
        self.mode_switcher_layout.addWidget(switcher)

    def _on_minimize(self):
        self._window.showMinimized()
        self.minimizeRequested.emit()

    def _on_maximize(self):
        if self._window.isMaximized():
            self._window.showNormal()
            self.btn_max.setText("▢")
        else:
            self._window.showMaximized()
            self.btn_max.setText("❐")
        self.maximizeRequested.emit()

    def _on_close(self):
        self.closeRequested.emit()

    # --- Drag handling ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # Não drag se clicou em botão
            child = self.childAt(event.position().toPoint())
            if child and child in (self.btn_min, self.btn_max, self.btn_close, self.retry):
                super().mousePressEvent(event)
                return
            if self.mode_switcher and self.mode_switcher.childAt(
                self.mode_switcher.mapFromGlobal(event.globalPosition().toPoint())
            ):
                super().mousePressEvent(event)
                return
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            self._drag_active = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_active and event.buttons() & Qt.LeftButton:
            if not self._window.isMaximized():
                self._window.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_active = False
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double-click na title bar = maximize/restore."""
        if event.button() == Qt.LeftButton:
            self._on_maximize()
        super().mouseDoubleClickEvent(event)

    # --- Public API ---
    def set_online(self, online: bool):
        if online:
            self.net.setText("● ONLINE")
            self.net.setStyleSheet(f"color: #00ff88;")
        else:
            self.net.setText("● OFFLINE")
            self.net.setStyleSheet(f"color: {BAD};")

    def set_retry_visible(self, visible: bool):
        self.retry.setVisible(visible)

    def set_mode_label(self, text: str):
        self.mode_label.setText(text)

    def update_maximize_button(self):
        """Atualiza ícone do botão maximizar baseado no estado."""
        if self._window.isMaximized():
            self.btn_max.setText("❐")
        else:
            self.btn_max.setText("▢")