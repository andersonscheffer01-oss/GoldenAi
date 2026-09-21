"""Fundo tecnologico discreto: gradiente + grid sutil + circuitos (estatico)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class Backdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)

    def paintEvent(self, event):  # noqa: N802 - assinatura Qt
        w, h = self.width(), self.height()
        p = QPainter(self)
        # base vertical
        grad = QRadialGradient(w / 2, h * 0.30, max(w, h) * 0.55)
        grad.setColorAt(0.0, QColor("#0a1a30"))
        grad.setColorAt(0.5, QColor("#050f1f"))
        grad.setColorAt(1.0, QColor("#030811"))
        p.fillRect(0, 0, w, h, grad)
        # grid sutil
        grid = QPen(QColor(34, 211, 238, 10))
        grid.setWidth(1)
        p.setPen(grid)
        step = 30
        for x in range(0, w, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)
        # pontos de intersecao esparsos
        dot = QPen(QColor(34, 211, 238, 26))
        p.setPen(dot)
        for x in range(0, w, step * 4):
            for y in range(0, h, step * 4):
                p.drawPoint(x, y)
        # circuitos decorativos nos cantos
        cir = QPen(QColor(34, 211, 238, 30))
        cir.setWidth(1)
        p.setPen(cir)
        p.drawLine(20, 60, 90, 60)
        p.drawLine(90, 60, 90, 110)
        p.drawLine(w - 90, 60, w - 20, 60)
        p.drawLine(w - 90, 60, w - 90, 110)
        p.drawLine(20, h - 60, 90, h - 60)
        p.drawLine(w - 90, h - 60, w - 20, h - 60)
