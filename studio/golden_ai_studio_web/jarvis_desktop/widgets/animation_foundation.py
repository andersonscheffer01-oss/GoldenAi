"""AnimationFoundation: Avatar humanoide holografico central - Golden Jarvis.

Fase 2: Avatar Jarvis com silhueta humanoide, olhos brilhantes, glow,
particulas e energias fluidas. 6 estados visuais distintos.
QPainter leve, sem QML separado, sem janela branca.
Performance: idle < 2% CPU, ativo 30-45 FPS.
"""
from __future__ import annotations

import math
import time
import random
from typing import List

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QRadialGradient,
    QFont, QPainterPath, QLinearGradient, QConicalGradient,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout

from ..theme_v4 import (
    BG_DEEP, CYAN, CYAN_GLOW, CYAN_DIM, GOLD, GOLD_DIM, BLUE_ELECTRIC,
    TEXT_PRIMARY, TEXT_MUTED,
    anim_color, anim_pulse_speed,
    MONO_FONT
)


_STATE_EYE_BRIGHTNESS = {
    "IDLE": 0.45, "LISTENING": 0.95, "PROCESSING": 0.7,
    "SPEAKING": 0.85, "OFFLINE": 0.05, "ERROR": 0.6,
}
_STATE_SCAN_SPEED = {
    "IDLE": 0.15, "LISTENING": 0.6, "PROCESSING": 0.9,
    "SPEAKING": 0.4, "OFFLINE": 0.0, "ERROR": 0.3,
}
_STATE_RING_COUNT = {
    "IDLE": 2, "LISTENING": 3, "PROCESSING": 4,
    "SPEAKING": 3, "OFFLINE": 0, "ERROR": 1,
}


class Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'life', 'max_life', 'size', 'r', 'g', 'b')

    def __init__(self, cx, cy, r, g, b, spread=80, speed_mul=1.0):
        angle = random.random() * 2 * math.pi
        speed = random.uniform(0.2, 0.8) * speed_mul
        self.x = cx + math.cos(angle) * random.uniform(0, spread * 0.4)
        self.y = cy + math.sin(angle) * random.uniform(0, spread * 0.4)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 1.0
        self.max_life = random.uniform(1.2, 3.5)
        self.size = random.uniform(1.0, 3.0)
        self.r, self.g, self.b = r, g, b


class JarvisAvatarCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self._state = "IDLE"
        self._t = 0.0
        self._voice_level = 0.0
        self._voice_level_target = 0.0
        self._particles: List[Particle] = []
        self._waveform_data = [0.0] * 64
        self._waveform_ptr = 0
        self._scan_y = 0.0
        self._prev_time = time.time()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_state(self, state):
        self._state = str(state).upper()
        self._t = 0.0
        self._scan_y = 0.0
        self._spawn_particles()
        self.update()

    def set_voice_level(self, level):
        self._voice_level_target = max(0.0, min(1.0, level))

    def add_waveform_sample(self, sample):
        self._waveform_data[self._waveform_ptr] = max(-1.0, min(1.0, sample))
        self._waveform_ptr = (self._waveform_ptr + 1) % len(self._waveform_data)

    def _tick(self):
        if not self.isVisible():
            return
        now = time.time()
        dt = min(now - self._prev_time, 0.1)
        self._prev_time = now
        speed = anim_pulse_speed(self._state)
        self._t += dt * speed * 2.0
        self._voice_level += (self._voice_level_target - self._voice_level) * 0.18
        scan_speed = _STATE_SCAN_SPEED.get(self._state, 0.2)
        self._scan_y += dt * scan_speed * 80
        wh = self.height() + 40
        if self._scan_y > wh:
            self._scan_y = -40
        self._update_particles(dt)
        self.update()

    def _spawn_particles(self):
        self._particles.clear()
        cx, cy = self.width() / 2, self.height() * 0.42
        c = QColor(anim_color(self._state))
        count = {"IDLE": 5, "LISTENING": 10, "PROCESSING": 14,
                 "SPEAKING": 10, "OFFLINE": 0, "ERROR": 6}
        for _ in range(count.get(self._state, 5)):
            self._particles.append(
                Particle(cx, cy, c.red(), c.green(), c.blue(), 100, 0.6))

    def _update_particles(self, dt):
        cx, cy = self.width() / 2, self.height() * 0.42
        alive = []
        for p in self._particles:
            if self._state == "PROCESSING":
                dx, dy = cx - p.x, cy - p.y
                dist = math.hypot(dx, dy)
                if dist > 1:
                    pull = 0.5 * dt * 60
                    p.vx += (dx / dist) * pull
                    p.vy += (dy / dist) * pull
            p.x += p.vx * dt * 60
            p.y += p.vy * dt * 60
            p.life -= dt / p.max_life
            if p.life > 0:
                alive.append(p)
            elif self._state != "OFFLINE" and random.random() < 0.015:
                c = QColor(anim_color(self._state))
                alive.append(Particle(cx, cy, c.red(), c.green(), c.blue(), 100, 0.5))
        self._particles = alive

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        cx = w / 2
        head_cy = h * 0.33
        head_rx = min(w * 0.16, h * 0.13)
        head_ry = head_rx * 1.18
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        pulse = (math.sin(self._t * 2.0) + 1) / 2
        voice = self._voice_level
        c_hex = anim_color(self._state)
        base_c = QColor(c_hex)
        base_r, base_g, base_b = base_c.red(), base_c.green(), base_c.blue()
        self._draw_aura(p, cx, head_cy, head_rx, head_ry, base_r, base_g, base_b, pulse)
        self._draw_rings(p, cx, head_cy, head_rx, head_ry, base_r, base_g, base_b, pulse, voice)
        self._draw_scan_line(p, w, h, base_r, base_g, base_b)
        self._draw_holographic_lines(p, w, h, cx, head_cy, base_r, base_g, base_b, pulse)
        self._draw_avatar(p, cx, head_cy, head_rx, head_ry, base_r, base_g, base_b, pulse, voice)
        self._draw_energy_lines(p, cx, head_cy, head_rx, head_ry, base_r, base_g, base_b, pulse, voice)
        self._draw_particles(p)
        self._draw_state_label(p, cx, h, w)

    def _draw_aura(self, p, cx, cy, rx, ry, r, g, b, pulse):
        aura_r = max(rx, ry) * 1.9
        grad = QRadialGradient(cx, cy, aura_r)
        a1 = int(18 + pulse * 12)
        a2 = int(8 + pulse * 6)
        grad.setColorAt(0.0, QColor(r, g, b, a1))
        grad.setColorAt(0.5, QColor(r, g, b, a2))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(cx - aura_r, cy - aura_r, aura_r * 2, aura_r * 2))

    def _draw_rings(self, p, cx, cy, rx, ry, r, g, b, pulse, voice):
        n_rings = _STATE_RING_COUNT.get(self._state, 2)
        if n_rings == 0:
            return
        for i in range(n_rings):
            frac = (i + 1) / (n_rings + 1)
            ring_r = max(rx, ry) * (1.15 + frac * 0.6)
            alpha = int(25 + pulse * 15 + (voice * 20 if i % 2 == 0 else 0))
            alpha = min(alpha, 80)
            pen_c = QColor(r, g, b, alpha)
            pen = QPen(pen_c)
            pen.setWidthF(1.0 + frac * 0.8)
            if self._state == "PROCESSING":
                pen.setStyle(Qt.DashLine)
                pen.setDashOffset(self._t * 30 * (1 if i % 2 == 0 else -1))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            wobble = pulse * 3 * math.sin(self._t * 1.5 + i)
            p.drawEllipse(QRectF(cx - ring_r + wobble, cy - ring_r,
                                  ring_r * 2, ring_r * 2))

    def _draw_scan_line(self, p, w, h, r, g, b):
        scan_alpha = int(40 + abs(math.sin(self._t * 0.5)) * 30)
        scan_c = QColor(r, g, b, scan_alpha)
        p.setPen(QPen(scan_c, 1))
        p.drawLine(int(0), int(self._scan_y), int(w), int(self._scan_y))
        for offset in (-2, 2):
            faint = QColor(r, g, b, scan_alpha // 3)
            p.setPen(QPen(faint, 1))
            p.drawLine(int(0), int(self._scan_y + offset), int(w), int(self._scan_y + offset))

    def _draw_holographic_lines(self, p, w, h, cx, cy, r, g, b, pulse):
        base_alpha = max(8, int(12 + pulse * 8))
        spacing = 6
        offset = int(self._t * 15) % spacing
        for y in range(0, h, spacing):
            y_adj = y + offset
            if abs(y_adj - cy) < max(h * 0.5, 40):
                continue
            a = min(base_alpha, 30)
            p.setPen(QPen(QColor(r, g, b, a), 1))
            p.drawLine(0, y_adj, w, y_adj)

    def _draw_avatar(self, p, cx, cy, rx, ry, r, g, b, pulse, voice):
        body_top = cy + ry * 1.05
        body_bottom = cy + ry * 3.2
        neck_w = rx * 0.35
        shoulder_w = rx * 2.8
        grad = QLinearGradient(cx, cy - ry, cx, body_bottom)
        main_alpha = int(180 + pulse * 40)
        main_alpha = min(main_alpha, 220)
        grad.setColorAt(0.0, QColor(r, g, b, main_alpha))
        grad.setColorAt(0.6, QColor(r, g, b, int(main_alpha * 0.5)))
        grad.setColorAt(1.0, QColor(r, g, b, int(main_alpha * 0.1)))
        outline_pen = QPen(QColor(r, g, b, int(main_alpha * 0.7)), 1.5)
        p.setPen(outline_pen)
        p.setBrush(QBrush(grad))
        path = QPainterPath()
        path.moveTo(cx - neck_w, body_top)
        path.lineTo(cx - neck_w, body_top - ry * 0.15)
        path.cubicTo(
            cx - neck_w, cy + ry * 0.5,
            cx - rx * 0.9, cy + ry * 0.3,
            cx - rx * 1.05, cy + ry * 0.6
        )
        path.lineTo(cx - shoulder_w, body_bottom)
        path.lineTo(cx + shoulder_w, body_bottom)
        path.lineTo(cx + rx * 1.05, cy + ry * 0.6)
        path.cubicTo(
            cx + rx * 0.9, cy + ry * 0.3,
            cx + neck_w, cy + ry * 0.5,
            cx + neck_w, body_top - ry * 0.15
        )
        path.lineTo(cx + neck_w, body_top)
        path.closeSubpath()
        p.drawPath(path)
        head_path = QPainterPath()
        head_path.addEllipse(cx - rx, cy - ry, rx * 2, ry * 2)
        head_grad = QRadialGradient(cx - rx * 0.3, cy - ry * 0.2, ry * 1.3)
        head_grad.setColorAt(0.0, QColor(r, g, b, int(main_alpha * 0.9)))
        head_grad.setColorAt(0.7, QColor(r, g, b, int(main_alpha * 0.5)))
        head_grad.setColorAt(1.0, QColor(r, g, b, int(main_alpha * 0.2)))
        p.setPen(QPen(QColor(r, g, b, int(main_alpha * 0.6)), 1.2))
        p.setBrush(QBrush(head_grad))
        p.drawPath(head_path)
        self._draw_face_details(p, cx, cy, rx, ry, r, g, b, pulse, voice)

    def _draw_face_details(self, p, cx, cy, rx, ry, r, g, b, pulse, voice):
        eye_y = cy - ry * 0.1
        eye_spacing = rx * 0.4
        eye_w = rx * 0.22
        eye_h = ry * 0.1
        brightness = _STATE_EYE_BRIGHTNESS.get(self._state, 0.5)
        eye_alpha = int(60 + brightness * 195 + voice * 40)
        eye_alpha = min(eye_alpha, 255)
        for side in (-1, 1):
            ex = cx + side * eye_spacing
            glow_r = eye_w * 2.2
            glow_grad = QRadialGradient(ex, eye_y, glow_r)
            glow_grad.setColorAt(0.0, QColor(r, g, b, int(eye_alpha * 0.5)))
            glow_grad.setColorAt(0.5, QColor(r, g, b, int(eye_alpha * 0.15)))
            glow_grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(glow_grad))
            p.drawEllipse(QRectF(ex - glow_r, eye_y - glow_r, glow_r * 2, glow_r * 2))
            eye_pen_c = QColor(r, g, b, eye_alpha)
            p.setPen(QPen(eye_pen_c, 1.5))
            p.setBrush(QBrush(QColor(r, g, b, int(eye_alpha * 0.6))))
            eye_rect = QRectF(ex - eye_w, eye_y - eye_h, eye_w * 2, eye_h * 2)
            p.drawEllipse(eye_rect)
            inner_c = QColor(255, 255, 255, int(eye_alpha * 0.8))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(inner_c))
            p.drawEllipse(QRectF(ex - eye_w * 0.3, eye_y - eye_h * 0.3,
                                  eye_w * 0.6, eye_h * 0.6))
        nose_y = cy + ry * 0.15
        nose_pen = QColor(r, g, b, int(40 + pulse * 20))
        p.setPen(QPen(nose_pen, 1))
        p.drawLine(int(cx), int(eye_y + ry * 0.25), int(cx - rx * 0.05), int(nose_y))
        mouth_y = cy + ry * 0.45
        mouth_w = rx * 0.35
        mouth_alpha = int(50 + voice * 150)
        mouth_pen = QColor(r, g, b, min(mouth_alpha, 200))
        p.setPen(QPen(mouth_pen, 1.5))
        mouth_open = voice * 6
        p.drawArc(QRectF(cx - mouth_w, mouth_y - mouth_open, mouth_w * 2, mouth_open * 2 + 4),
                  200 * 16, 140 * 16)

    def _draw_energy_lines(self, p, cx, cy, rx, ry, r, g, b, pulse, voice):
        if self._state == "OFFLINE":
            return
        n_lines = 5 if self._state != "PROCESSING" else 8
        for i in range(n_lines):
            angle = (i / n_lines) * 2 * math.pi + self._t * 0.4
            outer_r = max(rx, ry) * (1.3 + 0.5 * math.sin(self._t + i * 1.7))
            x1 = cx + math.cos(angle) * rx * 0.9
            y1 = cy + math.sin(angle) * ry * 0.9
            x2 = cx + math.cos(angle) * outer_r
            y2 = cy + math.sin(angle) * outer_r
            alpha = int(30 + pulse * 25 + voice * 30)
            alpha = min(alpha, 120)
            line_c = QColor(r, g, b, alpha)
            p.setPen(QPen(line_c, 1.0))
            ctrl_x = cx + math.cos(angle + 0.3) * outer_r * 0.7
            ctrl_y = cy + math.sin(angle + 0.3) * outer_r * 0.7
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.quadTo(ctrl_x, ctrl_y, x2, y2)
            p.drawPath(path)

    def _draw_particles(self, p):
        for pt in self._particles:
            if pt.life <= 0:
                continue
            alpha = int(220 * max(0, pt.life))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(pt.r, pt.g, pt.b, alpha)))
            p.drawEllipse(QRectF(pt.x - pt.size, pt.y - pt.size,
                                  pt.size * 2, pt.size * 2))

    def _draw_state_label(self, p, cx, h, w):
        label = self._state
        c_hex = anim_color(self._state)
        c = QColor(c_hex)
        c.setAlpha(160)
        p.setPen(QPen(c))
        font = QFont(MONO_FONT, 10, QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(cx - 60, h - 32, 120, 24), Qt.AlignCenter, label)


class AnimationFoundation(QWidget):
    """Widget container. API mantida para compatibilidade."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        self.canvas = JarvisAvatarCanvas()
        layout.addWidget(self.canvas, 1, Qt.AlignCenter)
        self._sim_timer = None

    def set_state(self, state):
        self.canvas.set_state(state)

    def set_voice_level(self, level):
        self.canvas.set_voice_level(level)

    def add_waveform_sample(self, sample):
        self.canvas.add_waveform_sample(sample)

    def start_voice_simulation(self):
        if self._sim_timer:
            return
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._simulate_voice)
        self._sim_timer.start(50)

    def stop_voice_simulation(self):
        if self._sim_timer:
            self._sim_timer.stop()
            self._sim_timer = None
        self.set_voice_level(0.0)

    def _simulate_voice(self):
        t = time.time()
        level = 0.3 + 0.4 * abs(math.sin(t * 3)) + random.uniform(-0.1, 0.1)
        level = max(0.0, min(1.0, level))
        self.set_voice_level(level)
        for i in range(3):
            sample = math.sin(t * 10 + i) * level * 0.5 + random.uniform(-0.2, 0.2)
            self.add_waveform_sample(max(-1.0, min(1.0, sample)))
