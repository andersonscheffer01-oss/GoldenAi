"""HudPanel V4: Painel estilo HUD com cantos tecnológicos, tag superior, body flexível."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget

from ..theme_v4 import (
    BG_PANEL, BORDER_SUBTLE, CYAN, GOLD, TEXT_MUTED,
    MONO_FONT, RADIUS_MD
)


class HudPanelV4(QFrame):
    """
    Container visual estilo HUD:
    - Fundo semi-transparente navy
    - Bordas parciais nos 4 cantos (estilo bracketed corners)
    - Tag/label no canto superior esquerdo
    - Body layout para adicionar widgets filhos
    """

    def __init__(self, tag: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self._tag = str(tag).upper()
        self._subtitle = str(subtitle)
        self.setObjectName("hudPanelV4")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QFrame#hudPanelV4 {{
                background: {BG_PANEL};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: {RADIUS_MD}px;
            }}
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 28, 16, 14)
        self._layout.setSpacing(8)

        # Tag label (posicionada via paintEvent no canto)
        if self._tag:
            self._tag_label = QLabel(self._tag)
            self._tag_label.setProperty("class", "hudTag")
            self._tag_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            # Não adicionamos ao layout — posicionamos manualmente no paintEvent
            self._tag_label.setParent(self)

        if self._subtitle:
            self._sub_label = QLabel(self._subtitle)
            self._sub_label.setProperty("class", "muted")
            self._sub_label.setStyleSheet("font-size: 10px; letter-spacing: 1px;")
            self._sub_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._sub_label.setParent(self)

    @property
    def body(self) -> QVBoxLayout:
        """Retorna o layout interno para adicionar widgets."""
        return self._layout

    def addWidget(self, widget: QWidget):
        self._layout.addWidget(widget)

    def addLayout(self, layout):
        self._layout.addLayout(layout)

    def addStretch(self, stretch=1):
        self._layout.addStretch(stretch)

    def paintEvent(self, event):
        super().paintEvent(event)

        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Cantos tecnológicos (bracketed corners)
        corner_len = 18
        corner_thickness = 1

        # Cores
        edge_color = QColor(BORDER_SUBTLE)
        edge_color.setAlpha(200)
        accent_color = QColor(CYAN)
        accent_color.setAlpha(180)
        gold_color = QColor(GOLD)
        gold_color.setAlpha(120)

        pen_edge = QPen(edge_color)
        pen_edge.setWidth(corner_thickness)
        pen_accent = QPen(accent_color)
        pen_accent.setWidth(2)
        pen_accent.setCapStyle(Qt.RoundCap)
        pen_gold = QPen(gold_color)
        pen_gold.setWidth(1)

        # Offset para não sobrepor a tag
        tag_offset = 60 if self._tag else 0

        # --- Cantos superiores ---
        # Topo-esquerdo (início após tag)
        p.setPen(pen_edge)
        p.drawLine(tag_offset, 1, corner_len + tag_offset, 1)
        p.drawLine(1, 1, 1, corner_len)

        # Topo-direito
        p.drawLine(w - corner_len, 1, w - 1, 1)
        p.drawLine(w - 1, 1, w - 1, corner_len)

        # --- Cantos inferiores ---
        # Base-esquerdo
        p.drawLine(1, h - corner_len, 1, h - 1)
        p.drawLine(1, h - 1, corner_len, h - 1)

        # Base-direito
        p.drawLine(w - corner_len, h - 1, w - 1, h - 1)
        p.drawLine(w - 1, h - corner_len, w - 1, h - 1)

        # --- Micro recortes cyan nos cantos inferiores (estilo HUD) ---
        p.setPen(pen_accent)
        p.drawLine(1, h - 6, 1, h - 1)
        p.drawLine(w - 1, h - 6, w - 1, h - 1)

        # --- Detalhes dourados nos cantos superiores (muito sutis) ---
        p.setPen(pen_gold)
        p.drawPoint(tag_offset + 2, 2)
        p.drawPoint(w - 3, 2)

        # --- Posicionar tag label ---
        if self._tag and hasattr(self, '_tag_label'):
            self._tag_label.move(12 + tag_offset, 4)
            self._tag_label.adjustSize()

        if self._subtitle and hasattr(self, '_sub_label'):
            self._sub_label.move(12 + tag_offset, 22)
            self._sub_label.adjustSize()


class TelemetryLabel(QLabel):
    """Label monoespaçado para telemetria."""
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("class", "telemetry")
        self.setFont(self.font())


class TelemetryBar(QLabel):
    """Label monoespaçado para barras (CPU/RAM/GPU)."""
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("class", "telemetryBar")
        self.setFont(self.font())