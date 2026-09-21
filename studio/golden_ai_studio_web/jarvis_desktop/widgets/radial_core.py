"""RadialCore: Núcleo central + 12 nós radiais para modo CONTROLE.

Desenho leve em QPainter: núcleo central, linhas de conexão, nós orbitais.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QRadialGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout

from ..theme_v4 import (
    BG_DEEP, CYAN, CYAN_GLOW, GOLD, GOLD_DIM, BLUE_ELECTRIC,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    RADIAL_NODES, MONO_FONT
)


class RadialNode:
    """Nó radial individual."""
    __slots__ = ('id', 'label', 'icon', 'angle', 'is_core', 'active', 'hover', 'x', 'y', 'radius')

    def __init__(self, id: str, label: str, icon: str, angle: float, is_core: bool = False):
        self.id = id
        self.label = label
        self.icon = icon
        self.angle = angle  # graus
        self.is_core = is_core
        self.active = False
        self.hover = False
        self.x = 0.0
        self.y = 0.0
        self.radius = 0.0


class RadialCoreCanvas(QWidget):
    """Canvas do núcleo radial."""

    nodeClicked = Signal(str)  # node id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)

        self._nodes = [RadialNode(**n) for n in RADIAL_NODES]
        self._core_node = next(n for n in self._nodes if n.is_core)
        self._orbit_radius = 0.0
        self._t = 0.0
        self._hovered_node = None
        self._connection_alpha = 0.0
        self._target_connection_alpha = 1.0

        # Timer para animação suave
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 FPS

        # Inicializar posições
        self._update_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_layout()

    def _update_layout(self):
        """Atualiza posições dos nós baseado no tamanho do widget."""
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        side = min(w, h)
        self._orbit_radius = side * 0.38

        for node in self._nodes:
            if node.is_core:
                node.x = cx
                node.y = cy
                node.radius = side * 0.08
            else:
                ang = math.radians(node.angle - 90)  # -90 = topo
                node.x = cx + math.cos(ang) * self._orbit_radius
                node.y = cy + math.sin(ang) * self._orbit_radius
                node.radius = side * 0.045

        self._core_node.x = cx
        self._core_node.y = cy

    def _tick(self):
        if not self.isVisible():
            return
        now = time.time()
        dt = now - getattr(self, '_last_tick', now)
        self._last_tick = now

        self._t += dt * 0.5

        # Anima conexões aparecendo
        self._connection_alpha += (self._target_connection_alpha - self._connection_alpha) * 0.08

        # Pulso do núcleo
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        hovered = None
        for node in self._nodes:
            if not node.is_core:
                dx = pos.x() - node.x
                dy = pos.y() - node.y
                if dx * dx + dy * dy <= (node.radius + 8) ** 2:
                    hovered = node
                    break
        if hovered != self._hovered_node:
            if self._hovered_node:
                self._hovered_node.hover = False
            self._hovered_node = hovered
            if hovered:
                hovered.hover = True
            self.update()

    def leaveEvent(self, event):
        if self._hovered_node:
            self._hovered_node.hover = False
            self._hovered_node = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._hovered_node:
            self.nodeClicked.emit(self._hovered_node.id)
        super().mousePressEvent(event)

    def set_node_active(self, node_id: str, active: bool):
        for node in self._nodes:
            if node.id == node_id:
                node.active = active
                self.update()
                break

    def set_connections_visible(self, visible: bool):
        self._target_connection_alpha = 1.0 if visible else 0.0

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        cx, cy = w / 2, h / 2
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        # 1. Desenhar conexões (linhas do núcleo para nós)
        if self._connection_alpha > 0.01:
            self._draw_connections(p, cx, cy)

        # 2. Desenhar órbitas/anéis de referência
        self._draw_orbits(p, cx, cy)

        # 3. Desenhar nós orbitais
        for node in self._nodes:
            if not node.is_core:
                self._draw_node(p, node)

        # 4. Desenhar núcleo central (por cima)
        self._draw_core(p, self._core_node)

        # 5. Label do nó hover
        if self._hovered_node and not self._hovered_node.is_core:
            self._draw_node_label(p, self._hovered_node)

    def _draw_connections(self, p, cx, cy):
        """Desenha linhas do núcleo para cada nó."""
        alpha = int(60 * self._connection_alpha)
        # Linhas principais
        line_color = QColor(CYAN)
        line_color.setAlpha(alpha)
        pen = QPen(line_color)
        pen.setWidth(1)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

        for node in self._nodes:
            if node.is_core:
                continue
            # Linha tracejada sutil
            dash_pen = QPen(line_color)
            dash_pen.setWidth(1)
            dash_pen.setStyle(Qt.DashLine)
            dash_pen.setDashPattern([4, 6])
            p.setPen(dash_pen)
            p.drawLine(QPointF(cx, cy), QPointF(node.x, node.y))

            # Ponto de conexão no nó
            dot_color = QColor(CYAN)
            dot_color.setAlpha(int(120 * self._connection_alpha))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(dot_color))
            p.drawEllipse(QRectF(node.x - 3, node.y - 3, 6, 6))

    def _draw_orbits(self, p, cx, cy):
        """Desenha anéis de órbita de referência."""
        # Anel principal
        orbit_color = QColor(CYAN)
        orbit_color.setAlpha(25)
        pen = QPen(orbit_color)
        pen.setWidth(1)
        pen.setStyle(Qt.DotLine)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), self._orbit_radius, self._orbit_radius)

        # Anel interno
        inner_r = self._orbit_radius * 0.5
        orbit_color.setAlpha(15)
        pen = QPen(orbit_color)
        pen.setWidth(1)
        pen.setStyle(Qt.SolidLine)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Cruzes cardinais (N/S/E/W)
        cross_color = QColor(CYAN)
        cross_color.setAlpha(20)
        pen = QPen(cross_color)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawLine(int(cx - self._orbit_radius), int(cy), int(cx + self._orbit_radius), int(cy))
        p.drawLine(int(cx), int(cy - self._orbit_radius), int(cx), int(cy + self._orbit_radius))

    def _draw_node(self, p, node: RadialNode):
        """Desenha um nó orbital."""
        # Cores baseadas no estado
        if node.active:
            base_color = QColor(GOLD)
            glow_color = QColor(GOLD)
            text_color = QColor(GOLD)
            ring_alpha = 200
        elif node.hover:
            base_color = QColor(CYAN_GLOW)
            glow_color = QColor(CYAN)
            text_color = QColor(CYAN)
            ring_alpha = 220
        else:
            base_color = QColor(CYAN)
            glow_color = QColor(CYAN)
            text_color = QColor(TEXT_SECONDARY)
            ring_alpha = 100

        # Anel externo (glow)
        if node.active or node.hover:
            glow = QColor(glow_color)
            glow.setAlpha(int(40 * self._connection_alpha))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QRectF(node.x - node.radius - 8, node.y - node.radius - 8,
                                 (node.radius + 8) * 2, (node.radius + 8) * 2))

        # Anel do nó
        ring_color = QColor(base_color)
        ring_color.setAlpha(ring_alpha)
        pen = QPen(ring_color)
        pen.setWidth(2 if node.active or node.hover else 1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(node.x - node.radius, node.y - node.radius,
                             node.radius * 2, node.radius * 2))

        # Ícone/texto no centro do nó
        p.setPen(QPen(text_color))
        font = QFont(MONO_FONT, 9 if node.active or node.hover else 8, QFont.Bold if node.active else QFont.Normal)
        p.setFont(font)
        text_rect = QRectF(node.x - node.radius * 2.5, node.y - node.radius * 2.5,
                           node.radius * 5, node.radius * 5)
        # Desenha label curto
        short_label = node.label[:4] if not node.active else node.label
        p.drawText(text_rect, Qt.AlignCenter, short_label)

    def _draw_core(self, p, node: RadialNode):
        """Desenha o núcleo central (Golden Jarvis)."""
        cx, cy = node.x, node.y
        r = node.radius

        # Pulso do núcleo
        pulse = (math.sin(self._t * 2.0) + 1) / 2
        core_r = r * (0.9 + pulse * 0.15)

        # Glow externo
        glow = QColor(GOLD)
        glow.setAlpha(int(60 + pulse * 40))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(cx - core_r - 14, cy - core_r - 14,
                             (core_r + 14) * 2, (core_r + 14) * 2))

        # Anel dourado
        ring_c = QColor(GOLD)
        ring_c.setAlpha(180)
        pen = QPen(ring_c)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # Núcleo preenchido
        p.setBrush(QBrush(GOLD))
        p.drawEllipse(QRectF(cx - core_r * 0.7, cy - core_r * 0.7,
                             core_r * 1.4, core_r * 1.4))

        # Centro escuro
        p.setBrush(QBrush(QColor(BG_DEEP)))
        p.drawEllipse(QRectF(cx - core_r * 0.25, cy - core_r * 0.25,
                             core_r * 0.5, core_r * 0.5))

        # Label "NÚCLEO" abaixo
        label_c = QColor(GOLD)
        label_c.setAlpha(200)
        p.setPen(QPen(label_c))
        font = QFont(MONO_FONT, 10, QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(cx - 60, cy + r + 18, 120, 20), Qt.AlignCenter, "NÚCLEO")

    def _draw_node_label(self, p, node: RadialNode):
        """Desenha label expandido do nó hover."""
        label = node.label
        icon = node.icon

        # Background do tooltip
        tooltip_w = 160
        tooltip_h = 56
        tx = node.x - tooltip_w / 2
        ty = node.y - node.radius - tooltip_h - 8

        # Ajustar para não sair da tela
        if tx < 8: tx = 8
        if tx + tooltip_w > self.width() - 8: tx = self.width() - tooltip_w - 8
        if ty < 8: ty = node.y + node.radius + 8

        # Fundo
        bg = QColor(2, 6, 16, 230)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(tx, ty, tooltip_w, tooltip_h), 8, 8)

        # Borda accent
        border_c = QColor(GOLD if node.active else CYAN)
        border_c.setAlpha(180)
        pen = QPen(border_c)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(tx, ty, tooltip_w, tooltip_h), 8, 8)

        # Texto
        p.setPen(QPen(TEXT_PRIMARY))
        font = QFont(MONO_FONT, 10, QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(tx + 12, ty + 4, tooltip_w - 24, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{icon}  {label}")

        # Status
        status = "ATIVO" if node.active else "DISPONÍVEL"
        status_c = QColor(GOLD if node.active else TEXT_SECONDARY)
        p.setPen(QPen(status_c))
        font = QFont(MONO_FONT, 8)
        p.setFont(font)
        p.drawText(QRectF(tx + 12, ty + 28, tooltip_w - 24, 20), Qt.AlignLeft | Qt.AlignVCenter, status)


class RadialCore(QWidget):
    """Widget container para o núcleo radial."""

    nodeActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.canvas = RadialCoreCanvas()
        self.canvas.nodeClicked.connect(self._on_node_clicked)
        layout.addWidget(self.canvas, 1, Qt.AlignCenter)

    def _on_node_clicked(self, node_id: str):
        # Toggle active state
        node = next((n for n in self.canvas._nodes if n.id == node_id), None)
        if node and not node.is_core:
            node.active = not node.active
            self.canvas.update()
            self.nodeActivated.emit(node_id)

    def set_node_active(self, node_id: str, active: bool):
        self.canvas.set_node_active(node_id, active)

    def set_connections_visible(self, visible: bool):
        self.canvas.set_connections_visible(visible)