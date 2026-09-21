"""Backdrop V4: Fundo tecnológico — gradiente radial + grid sutil + circuitos decorativos."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import QWidget

from ..theme_v4 import (
    BG_DEEP, CYAN, GRID_LINE, GOLD
)


class BackdropV4(QWidget):
    """Fundo visual V4 — desenho leve em paintEvent."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 1. Gradiente radial principal (centro superior)
        center_x = w * 0.5
        center_y = h * 0.25
        radius = max(w, h) * 0.65

        grad = QRadialGradient(center_x, center_y, radius)
        grad.setColorAt(0.0, QColor("#0a1a35"))      # Centro: navy azulado
        grad.setColorAt(0.35, QColor("#050f1f"))     # Meio
        grad.setColorAt(0.7, QColor("#030814"))      # Transição
        grad.setColorAt(1.0, QColor(BG_DEEP))        # Bordas: quase-preto
        p.fillRect(0, 0, w, h, grad)

        # 2. Glow sutil no centro (pulsação suave via tempo)
        # Nota: animação real virá do widget central; aqui é estático
        glow_grad = QRadialGradient(center_x, center_y, radius * 0.4)
        glow_grad.setColorAt(0.0, QColor(0, 229, 255, 18))
        glow_grad.setColorAt(0.5, QColor(0, 229, 255, 6))
        glow_grad.setColorAt(1.0, QColor(0, 229, 255, 0))
        p.fillRect(0, 0, w, h, glow_grad)

        # 3. Grid sutil (linhas finas)
        grid_pen = QPen(QColor(GRID_LINE))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)

        step = 32
        # Linhas verticais
        for x in range(0, w, step):
            p.drawLine(x, 0, x, h)
        # Linhas horizontais
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)

        # 4. Pontos de interseção esparsos (canto inferior direito mais denso)
        dot_pen = QPen(QColor(0, 229, 255, 30))
        dot_pen.setWidth(1)
        p.setPen(dot_pen)
        dot_step = step * 4
        for x in range(0, w, dot_step):
            for y in range(0, h, dot_step):
                # Mais denso no quadrante inferior direito
                if x > w * 0.6 and y > h * 0.6:
                    p.drawPoint(x, y)
                elif x % (dot_step * 2) == 0 and y % (dot_step * 2) == 0:
                    p.drawPoint(x, y)

        # 5. Circuitos decorativos nos 4 cantos (estilo HUD)
        circuit_pen = QPen(QColor(0, 229, 255, 35))
        circuit_pen.setWidth(1)
        circuit_pen.setCapStyle(Qt.FlatCap)
        p.setPen(circuit_pen)

        margin = 24
        length = 48
        corner_len = 16

        # Canto superior esquerdo
        p.drawLine(margin, margin + 20, margin + length, margin + 20)
        p.drawLine(margin + length, margin + 20, margin + length, margin + 20 + corner_len)
        p.drawLine(margin, margin + 20 + corner_len, margin + corner_len, margin + 20 + corner_len)

        # Canto superior direito
        p.drawLine(w - margin - length, margin + 20, w - margin, margin + 20)
        p.drawLine(w - margin - length, margin + 20, w - margin - length, margin + 20 + corner_len)
        p.drawLine(w - margin - corner_len, margin + 20 + corner_len, w - margin, margin + 20 + corner_len)

        # Canto inferior esquerdo
        p.drawLine(margin, h - margin - 20, margin + length, h - margin - 20)
        p.drawLine(margin + length, h - margin - 20, margin + length, h - margin - 20 - corner_len)
        p.drawLine(margin, h - margin - 20 - corner_len, margin + corner_len, h - margin - 20 - corner_len)

        # Canto inferior direito
        p.drawLine(w - margin - length, h - margin - 20, w - margin, h - margin - 20)
        p.drawLine(w - margin - length, h - margin - 20, w - margin - length, h - margin - 20 - corner_len)
        p.drawLine(w - margin - corner_len, h - margin - 20 - corner_len, w - margin, h - margin - 20 - corner_len)

        # 6. Linha dourada sutil no topo (brand line)
        gold_pen = QPen(QColor(GOLD))
        gold_pen.setWidth(1)
        p.setPen(gold_pen)
        p.drawLine(0, 0, w, 0)

        # 7. Acents dourados nos cantos do grid (muito sutis)
        gold_pen.setWidth(1)
        accent_alpha = 25
        gold_accent = QPen(QColor(255, 215, 0, accent_alpha))
        p.setPen(gold_accent)
        # Dois pontos nos cantos do grid central
        cx, cy = w // 2, h // 2
        p.drawPoint(cx - step * 4, cy - step * 4)
        p.drawPoint(cx + step * 4, cy - step * 4)
        p.drawPoint(cx - step * 4, cy + step * 4)
        p.drawPoint(cx + step * 4, cy + step * 4)