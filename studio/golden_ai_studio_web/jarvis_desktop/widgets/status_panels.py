"""Paineis HUD V3: SYSTEM CORE + SYSTEM LINKS | AI NETWORK + TASK MATRIX."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..status_format import (bar_blocks, gpu_text, mt5_display, provider_badge,
                             radar_display, task_counts, voice_display)
from .hud_panel import HudPanel


def _tele(text):
    lbl = QLabel(text)
    lbl.setProperty("class", "tele")
    return lbl


def _bar(text):
    lbl = QLabel(text)
    lbl.setProperty("class", "teleBar")
    return lbl


class SystemPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.core = HudPanel("SYS·01 — SYSTEM CORE")
        self.cpu = _tele("CPU")
        self.cpu_bar = _bar("")
        self.ram = _tele("RAM")
        self.ram_bar = _bar("")
        self.gpu = _tele("GPU")
        self.gpu_bar = _bar("")
        self.vram = _tele("VRAM N/D")
        for w in (self.cpu, self.cpu_bar, self.ram, self.ram_bar,
                  self.gpu, self.gpu_bar, self.vram):
            self.core.body.addWidget(w)
        self.links = HudPanel("NET·02 — SYSTEM LINKS")
        self.lines = {}
        for key in ("GOLDEN", "MT5", "RADAR", "VOICE", "INTERNET"):
            lbl = _tele(f"{key} --")
            self.links.body.addWidget(lbl)
            self.lines[key] = lbl
        layout.addWidget(self.core)
        layout.addWidget(self.links, 1)

    def update_system(self, status):
        sys = (status or {}).get("system", {}) if isinstance(status, dict) else {}
        for attr, key in (("cpu", "cpu"), ("ram", "memory")):
            val = sys.get(key)
            label = "N/D" if val is None else f"{float(val):.0f}%"
            getattr(self, attr).setText(f"{attr.upper():<4} {label}")
        self.cpu_bar.setText(bar_blocks(sys.get("cpu")))
        self.ram_bar.setText(bar_blocks(sys.get("memory")))

    def update_gpu(self, gpu):
        g = gpu_text(gpu)
        self.gpu.setText(f"GPU  {g['name'][:26]}")
        self.gpu_bar.setText(bar_blocks(g["util"]))
        self.vram.setText(f"VRAM {g['vram']}")

    def update_services(self, status, voice, radar):
        online = bool((status or {}).get("ok"))
        self.lines["GOLDEN"].setText(f"GOLDEN  {'● ONLINE' if online else '○ OFFLINE'}")
        self.lines["MT5"].setText(f"MT5  {mt5_display(status)['label']}")
        self.lines["RADAR"].setText(f"RADAR  {radar_display(radar)['label']}")
        self.lines["VOICE"].setText(f"VOICE  {voice_display(voice)}")
        con = (status or {}).get("connections", {}) if isinstance(status, dict) else {}
        net = online or bool(con.get("ollama", {}).get("ok"))
        self.lines["INTERNET"].setText(f"NET  {'● ONLINE' if net else '○ OFFLINE'}")


class ProvidersPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.ai = HudPanel("AI·03 — AI NETWORK")
        self.primary_tag = QLabel("PRIMARY CORE")
        self.primary_tag.setProperty("class", "tag")
        self.primary = QLabel("--")
        self.primary.setProperty("class", "accent")
        self.readiness = QLabel("JARVIS --")
        self.readiness.setProperty("class", "tag")
        self.readiness.setWordWrap(True)
        self.fallback = QLabel("")
        self.fallback.setProperty("class", "tag")
        self.fallback.setWordWrap(True)
        self.ai.body.addWidget(self.primary_tag)
        self.ai.body.addWidget(self.primary)
        self.ai.body.addWidget(self.readiness)
        self.ai.body.addWidget(self.fallback)
        self.lines = {}
        for key in ("GROQ", "OPENROUTER", "GEMINI", "OLLAMA"):
            lbl = _tele(f"{key} --")
            self.ai.body.addWidget(lbl)
            self.lines[key] = lbl
        self.tm = HudPanel("TSK·04 — TASK MATRIX")
        self.t_active = _tele("ACTIVE --")
        self.t_wait = _tele("WAITING --")
        self.t_err = _tele("ERROR --")
        for w in (self.t_active, self.t_wait, self.t_err):
            self.tm.body.addWidget(w)
        layout.addWidget(self.ai)
        layout.addWidget(self.tm, 1)

    def update(self, providers_payload, tasks):
        provs = {(p.get("name", "").upper()): p
                 for p in (providers_payload or {}).get("providers", [])}
        ready = ((providers_payload or {}).get("readiness") or {}) if isinstance(providers_payload, dict) else {}
        state = str(ready.get("state", "") or "")
        if state:
            extra = str(ready.get("degraded_reason", "") or "")
            self.readiness.setText(f"JARVIS {state}" + (f" · {extra}" if extra else ""))
        for key in ("GROQ", "OPENROUTER", "GEMINI", "OLLAMA"):
            state = str(provs.get(key, {}).get("state", "UNKNOWN"))
            self.lines[key].setText(f"{key:<10} {provider_badge(state)}")
        prim = (providers_payload or {}).get("primary") or {}
        if prim.get("actual_provider"):
            self.primary.setText(f"{prim['actual_provider'].upper()}\n{prim.get('actual_model', '')}")
            self.fallback.setText("FALLBACK " + str(prim.get("fallback_reason", "")) if prim.get("fallback") else "")
        else:
            prim_list = (providers_payload or {}).get("primary_models", []) or []
            general = next((m for m in prim_list if m.get("profile") == "GENERAL"),
                           prim_list[0] if prim_list else None)
            self.primary.setText(f"{general['provider'].upper()}\n{general['model']}" if general else "--")
            self.fallback.setText("")
        counts = task_counts(tasks)
        self.t_active.setText(f"ACTIVE   {counts['active']}")
        self.t_wait.setText(f"WAITING  {counts['waiting']}")
        self.t_err.setText(f"ERROR    {counts['errors']}")
