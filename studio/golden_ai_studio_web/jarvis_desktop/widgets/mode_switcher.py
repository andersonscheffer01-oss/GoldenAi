"""ModeSwitcher: Toggle CONVERSA / CONTROLE com animação suave."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QRect
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

from ..theme_v4 import (
    CYAN, GOLD, BG_PANEL, BG_ELEVATED, BG_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    RADIUS_MD, MONO_FONT
)


class ModeButton(QPushButton):
    """Botão de modo com indicator animado."""

    def __init__(self, text: str, mode_id: str, parent=None):
        super().__init__(text, parent)
        self.mode_id = mode_id
        self.setCheckable(True)
        self.setProperty("class", "modeBtn")
        self.setCursor(Qt.PointingHandCursor)
        self._indicator_pos = 0.0
        self._target_pos = 0.0
        self._anim = QPropertyAnimation(self, b"_indicator_pos", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_indicator_target(self, value: float):
        self._target_pos = value
        self._anim.stop()
        self._anim.setStartValue(self._indicator_pos)
        self._anim.setEndValue(value)
        self._anim.start()

    def get_indicator_pos(self):
        return self._indicator_pos

    def set_indicator_pos(self, value):
        self._indicator_pos = value
        self.update()

    indicator_pos = property(get_indicator_pos, set_indicator_pos)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._indicator_pos > 0.01:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            h = self.height()
            indicator_h = 3
            y = h - indicator_h - 2
            w = int(self.width() * self._indicator_pos)
            x = (self.width() - w) // 2
            color = QColor(GOLD if self.mode_id == "controle" else CYAN)
            color.setAlpha(int(255 * self._indicator_pos))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(x, y, w, indicator_h, 1.5, 1.5)


class ModeSwitcher(QWidget):
    """Seletor de modo: CONVERSA | CONTROLE."""

    modeChanged = Signal(str)  # "conversa" ou "controle"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        self.btn_conversa = ModeButton("CONVERSA", "conversa")
        self.btn_controle = ModeButton("CONTROLE", "controle")

        self.btn_conversa.setChecked(True)
        self.btn_conversa.set_indicator_target(1.0)
        self.btn_controle.set_indicator_target(0.0)

        for btn in (self.btn_conversa, self.btn_controle):
            btn.clicked.connect(self._on_clicked)
            self.btn_group.addButton(btn)
            layout.addWidget(btn, 1)

    def _on_clicked(self):
        sender = self.sender()
        if not isinstance(sender, ModeButton):
            return
        mode = sender.mode_id
        # Anima indicadores
        if mode == "conversa":
            self.btn_conversa.set_indicator_target(1.0)
            self.btn_controle.set_indicator_target(0.0)
        else:
            self.btn_conversa.set_indicator_target(0.0)
            self.btn_controle.set_indicator_target(1.0)
        self.modeChanged.emit(mode)

    def set_mode(self, mode: str):
        """Define modo programaticamente."""
        if mode == "conversa":
            self.btn_conversa.setChecked(True)
            self.btn_conversa.set_indicator_target(1.0)
            self.btn_controle.set_indicator_target(0.0)
        elif mode == "controle":
            self.btn_controle.setChecked(True)
            self.btn_conversa.set_indicator_target(0.0)
            self.btn_controle.set_indicator_target(1.0)

    def current_mode(self) -> str:
        return "conversa" if self.btn_conversa.isChecked() else "controle"