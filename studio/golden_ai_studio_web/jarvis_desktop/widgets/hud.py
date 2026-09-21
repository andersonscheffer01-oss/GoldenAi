"""HUD protagonista: 4 aneis + ticks + nucleo + entrada animada (QPainter leve)."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

STATE_COLORS = {
    "ONLINE": "#22d3ee",
    "AGUARDANDO": "#3b82a0",
    "OUVINDO": "#2dd4bf",
    "TRANSCRIBINDO": "#f5b04c",
    "PROCESSANDO": "#f5b04c",
    "FALANDO": "#2dd4bf",
    "PENSANDO": "#f5b04c",
    "PLANEJANDO": "#a78bfa",
    "EXECUTANDO": "#60a5fa",
    "AGUARDANDO CONFIRMAÇÃO": "#fb923c",
    "CONCLUÍDO": "#2dd4bf",
    "ERRO": "#f46868",
    "OFFLINE": "#3b4c66",
}


def state_color(state):
    return STATE_COLORS.get(str(state), "#22d3ee")


def pulse_speed(state):
    return {"ONLINE": 0.8, "AGUARDANDO": 0.6, "OUVINDO": 2.4, "TRANSCRIBINDO": 3.0,
            "PROCESSANDO": 3.0, "FALANDO": 2.0, "PENSANDO": 3.0, "PLANEJANDO": 2.0,
            "EXECUTANDO": 4.2, "AGUARDANDO CONFIRMAÇÃO": 5.0,
            "CONCLUÍDO": 1.2, "ERRO": 6.0, "OFFLINE": 0.0}.get(str(state), 1.0)


class HudCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self._state = "OFFLINE"
        self._t = 0.0
        self._born = time.time()
        self._voice = False
        self._level_rms = 0
        self._level_at = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)  # 25fps

    def set_state(self, value):
        self._state = str(value)
        self.update()

    def set_voice(self, active):
        self._voice = bool(active)

    def set_level(self, rms, at):
        """Nivel real do microfone (RMS + timestamp). Sem dado = sem onda."""
        try:
            self._level_rms = int(rms)
            self._level_at = float(at)
        except (TypeError, ValueError):
            pass

    def _tick(self):
        if self.isVisible():
            self._t += 0.04 * max(0.6, pulse_speed(self._state))
            self.update()

    def _intro(self):
        """0..1 durante ~900ms apos criacao."""
        return min(1.0, (time.time() - self._born) / 0.9)

    def paintEvent(self, event):  # noqa: N802 - assinatura Qt
        side = min(self.width(), self.height())
        cx, cy = self.width() / 2, self.height() / 2 - 6
        intro = self._intro()
        color = QColor(state_color(self._state))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # anel 1: fixo fino
        self._ring(p, cx, cy, (side / 2 - 8) * intro, color, 70, 1)
        # anel 2: segmentado (ticks ao redor)
        self._ticks(p, cx, cy, (side / 2 - 24) * intro, color)
        # anel 3: gira lentamente (pensando/planejando/executando giram + rapido)
        spin = {"PENSANDO": 140, "PLANEJANDO": 90, "EXECUTANDO": 200}.get(self._state, 22)
        self._arc(p, cx, cy, (side / 2 - 40) * intro, color,
                  (-self._t * spin) % 360, 70 if self._state in ("PENSANDO", "PLANEJANDO", "EXECUTANDO") else 40)
        # anel 4: pulsa (respiracao; nivel REAL do mic quando recente)
        speed = pulse_speed(self._state)
        pulse = (math.sin(self._t * 2.4) + 1) / 2 if speed else 0.2
        boost = 0.0
        try:
            if (time.time() - self._level_at) * 1000 < 1500:
                boost = min(max(self._level_rms, 0), 3000) / 3000.0
        except Exception:
            boost = 0.0
        self._ring(p, cx, cy, ((side / 2 - 58) + pulse * 6 + boost * 10) * intro,
                   color, int(60 + pulse * 90 + boost * 60), 2)
        # nucleo luminoso
        glow = QColor(color)
        glow.setAlpha(int((50 + pulse * 60 + boost * 60) * intro))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        core = (30 + pulse * 5) * intro
        p.drawEllipse(int(cx - core - 14), int(cy - core - 14), int((core + 14) * 2), int((core + 14) * 2))
        p.setBrush(color)
        p.drawEllipse(int(cx - 15), int(cy - 15), 30, 30)
        p.setBrush(QColor("#030811"))
        p.drawEllipse(int(cx - 6), int(cy - 6), 12, 12)

    def _ring(self, p, cx, cy, radius, color, alpha, width):
        if radius <= 0:
            return
        c = QColor(color)
        c.setAlpha(alpha)
        pen = QPen(c)
        pen.setWidth(width)
        p.setPen(pen)
        p.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

    def _arc(self, p, cx, cy, radius, color, start_deg, span_deg):
        if radius <= 0:
            return
        pen = QPen(QColor(color))
        pen.setWidth(3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2),
                  int(start_deg * 16), int(span_deg * 16))
        # segundo segmento oposto (padrao quando planejando)
        if self._state == "PLANEJANDO":
            p.drawArc(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2),
                      int((start_deg + 180) * 16), int(span_deg * 16))

    def _ticks(self, p, cx, cy, radius, color):
        if radius <= 0:
            return
        c = QColor(color)
        c.setAlpha(110)
        pen = QPen(c)
        pen.setWidth(2)
        p.setPen(pen)
        for i in range(48):
            ang = math.radians(i * 7.5 + self._t * 4)
            long = (i % 4 == 0)
            r1 = radius - (8 if long else 4)
            x1, y1 = cx + math.cos(ang) * r1, cy + math.sin(ang) * r1
            x2, y2 = cx + math.cos(ang) * radius, cy + math.sin(ang) * radius
            p.drawLine(int(x1), int(y1), int(x2), int(y2))


class HudWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)
        self.canvas = HudCanvas()
        self.name = QLabel("J A R V I S")
        self.name.setStyleSheet("color:#f2f7fd; font-size:17px; font-weight:800; letter-spacing:8px;")
        self.state = QLabel("OFFLINE")
        self.state.setStyleSheet("color:#5f7391; font-size:11px; letter-spacing:4px;")
        self.sub = QLabel("")
        self.sub.setStyleSheet("color:#2dd4bf; font-size:9px; letter-spacing:3px;")
        for w in (self.canvas, self.name, self.state, self.sub):
            layout.addWidget(w, alignment=Qt.AlignCenter)

    def set_state(self, value, voice_active=False, level=None, interim=""):
        self.canvas.set_state(value)
        self.canvas.set_voice(voice_active)
        if level:
            try:
                self.canvas.set_level(level.get("rms", 0),
                                      time.time() - (level.get("age_ms", 9999) / 1000.0))
            except Exception:
                pass
        self.state.setText(str(value))
        self.state.setStyleSheet(f"color:{state_color(value)}; font-size:11px; letter-spacing:4px;")
        if interim:
            shown = str(interim)[:60]
            self.sub.setText(f"♪ “{shown}”")
            self.sub.setStyleSheet("color:#f2f7fd; font-size:10px; letter-spacing:1px;")
        else:
            self.sub.setText("VOICE ACTIVE" if voice_active else "")
            self.sub.setStyleSheet("color:#2dd4bf; font-size:9px; letter-spacing:3px;")
