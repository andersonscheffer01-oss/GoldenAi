"""Painel estilo HUD: bordas parciais nos cantos + etiqueta superior."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class HudPanel(QFrame):
    """Container com cantos tecnologicos; conteudo adicionado via `body`."""

    def __init__(self, tag="", parent=None):
        super().__init__(parent)
        self._tag = str(tag).upper()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 20, 14, 12)
        if self._tag:
            self._tag_label = QLabel(self._tag)
            self._tag_label.setProperty("class", "tag")
            self._tag_label.move(12, 4)
            self._tag_label.setAttribute(Qt.WA_TransparentForMouseEvents)

    @property
    def body(self):
        return self._layout

    def paintEvent(self, event):  # noqa: N802 - assinatura Qt
        super().paintEvent(event)
        w, h = self.width(), self.height()
        L = 14  # comprimento do canto
        edge = QColor("#1d3a5c")
        edge.setAlpha(200)
        accent = QColor("#22d3ee")
        accent.setAlpha(150)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(edge)
        pen.setWidth(1)
        p.setPen(pen)
        # 4 cantos parciais (topo interrompido p/ etiqueta)
        p.drawLine(70, 1, L + 40, 1)
        p.drawLine(w - L, 1, w - 1, 1)
        p.drawLine(1, 1, 1, L)
        p.drawLine(w - 1, 1, w - 1, L)
        p.drawLine(1, h - L, 1, h - 1)
        p.drawLine(1, h - 1, L, h - 1)
        p.drawLine(w - L, h - 1, w - 1, h - 1)
        p.drawLine(w - 1, h - L, w - 1, h - 1)
        # micro recortes cyan nos cantos inferiores
        pen2 = QPen(accent)
        pen2.setWidth(2)
        p.setPen(pen2)
        p.drawLine(1, h - 6, 1, h - 1)
        p.drawLine(w - 1, h - 6, w - 1, h - 1)
