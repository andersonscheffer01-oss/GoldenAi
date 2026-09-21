"""StatusFooter: Rodapé com CPU/RAM/GPU, Providers, Serviços — para modo CONVERSA."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget, QFrame
from PySide6.QtGui import QFont

from ..theme_v4 import (
    BG_PANEL, BORDER_SUBTLE, CYAN, GOLD, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GOOD, BAD, WARN, MONO_FONT, RADIUS_MD
)
from .hud_panel_v4 import HudPanelV4, TelemetryLabel, TelemetryBar


class StatusFooter(QWidget):
    """Rodapé de status: 3 painéis — Sistema, IA/Providers, Serviços."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(160)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Painel 1: Sistema (CPU, RAM, GPU)
        self.sys_panel = HudPanelV4("SYS·01", "SYSTEM CORE")
        self._setup_system_panel()
        layout.addWidget(self.sys_panel, 1)

        # Painel 2: IA Network + Task Matrix
        self.ai_panel = HudPanelV4("AI·02", "AI NETWORK · TASK MATRIX")
        self._setup_ai_panel()
        layout.addWidget(self.ai_panel, 1)

        # Painel 3: Serviços (Golden, MT5, Radar, Voice, Net)
        self.svc_panel = HudPanelV4("NET·03", "SYSTEM LINKS")
        self._setup_services_panel()
        layout.addWidget(self.svc_panel, 1)

    def _setup_system_panel(self):
        body = self.sys_panel.body
        # CPU
        self.cpu_label = TelemetryLabel("CPU  --%")
        self.cpu_bar = TelemetryBar("░░░░░░░░░░ N/D")
        # RAM
        self.ram_label = TelemetryLabel("RAM  --%")
        self.ram_bar = TelemetryBar("░░░░░░░░░░ N/D")
        # GPU
        self.gpu_label = TelemetryLabel("GPU  N/D")
        self.gpu_bar = TelemetryBar("░░░░░░░░░░ N/D")
        self.vram_label = TelemetryLabel("VRAM N/D")

        for w in (self.cpu_label, self.cpu_bar, self.ram_label, self.ram_bar,
                  self.gpu_label, self.gpu_bar, self.vram_label):
            body.addWidget(w)

    def _setup_ai_panel(self):
        body = self.ai_panel.body
        # Primary provider
        self.primary_tag = TelemetryLabel("PRIMARY CORE")
        self.primary_tag.setStyleSheet(f"color: {GOLD}; font-weight: 700; letter-spacing: 1px;")
        self.primary_value = TelemetryLabel("--")
        self.primary_value.setStyleSheet(f"color: {CYAN}; font-size: 13px;")
        # Readiness
        self.readiness = TelemetryLabel("JARVIS --")
        self.readiness.setProperty("class", "hudTag")
        # Fallback
        self.fallback = TelemetryLabel("")
        self.fallback.setProperty("class", "muted")
        self.fallback.setWordWrap(True)
        # Providers list
        self.provider_labels = {}
        for key in ("GROQ", "OPENROUTER", "GEMINI", "OLLAMA"):
            lbl = TelemetryLabel(f"{key:<10} --")
            self.provider_labels[key] = lbl
            body.addWidget(lbl)
        # Task matrix
        self.t_active = TelemetryLabel("ACTIVE   --")
        self.t_wait = TelemetryLabel("WAITING  --")
        self.t_err = TelemetryLabel("ERROR    --")

        body.addWidget(self.primary_tag)
        body.addWidget(self.primary_value)
        body.addWidget(self.readiness)
        body.addWidget(self.fallback)
        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border: none; border-top: 1px solid {BORDER_SUBTLE}; max-height: 1px;")
        body.addWidget(sep)
        body.addWidget(TelemetryLabel("TASK MATRIX"))
        body.addWidget(self.t_active)
        body.addWidget(self.t_wait)
        body.addWidget(self.t_err)

    def _setup_services_panel(self):
        body = self.svc_panel.body
        self.svc_labels = {}
        for key, label in (("GOLDEN", "GOLDEN BACKEND"), ("MT5", "METATRADER 5"),
                           ("RADAR", "RADAR"), ("VOICE", "VOICE SERVICE"),
                           ("NET", "INTERNET")):
            lbl = TelemetryLabel(f"{label:<18} --")
            self.svc_labels[key] = lbl
            body.addWidget(lbl)

    # ===== Public API =====

    def update_system(self, status: dict):
        """Atualiza CPU/RAM/GPU a partir de /api/status."""
        sys_data = (status or {}).get("system", {}) if isinstance(status, dict) else {}
        gpu_data = (status or {}).get("gpu", {}) if isinstance(status, dict) else {}

        # CPU
        cpu_val = sys_data.get("cpu")
        if cpu_val is not None:
            pct = float(cpu_val)
            self.cpu_label.setText(f"CPU  {pct:.0f}%")
            self.cpu_bar.setText(self._bar_blocks(pct))
            self.cpu_bar.setStyleSheet(f"color: {self._pct_color(pct)};")
        else:
            self.cpu_label.setText("CPU  N/D")
            self.cpu_bar.setText("░░░░░░░░░░ N/D")

        # RAM
        ram_val = sys_data.get("memory")
        if ram_val is not None:
            pct = float(ram_val)
            self.ram_label.setText(f"RAM  {pct:.0f}%")
            self.ram_bar.setText(self._bar_blocks(pct))
            self.ram_bar.setStyleSheet(f"color: {self._pct_color(pct)};")
        else:
            self.ram_label.setText("RAM  N/D")
            self.ram_bar.setText("░░░░░░░░░░ N/D")

        # GPU
        if isinstance(gpu_data, dict) and gpu_data.get("name"):
            name = str(gpu_data["name"])[:26]
            self.gpu_label.setText(f"GPU  {name}")
            util = gpu_data.get("util_percent")
            if util is not None:
                self.gpu_bar.setText(self._bar_blocks(float(util)))
                self.gpu_bar.setStyleSheet(f"color: {self._pct_color(float(util))};")
            else:
                self.gpu_bar.setText("░░░░░░░░░░ N/D")
            vram = gpu_data.get("vram_total_human", "N/D")
            self.vram_label.setText(f"VRAM {vram}")
        else:
            self.gpu_label.setText("GPU  N/D")
            self.gpu_bar.setText("░░░░░░░░░░ N/D")
            self.vram_label.setText("VRAM N/D")

    def update_providers(self, providers_payload: dict, tasks: list):
        """Atualiza providers e tasks a partir dos endpoints reais."""
        if not isinstance(providers_payload, dict) or not providers_payload.get("ok"):
            return

        provs = {p.get("name", "").upper(): p
                 for p in providers_payload.get("providers", [])}

        ready = providers_payload.get("readiness") or {}
        state = str(ready.get("state", "") or "")
        if state:
            extra = str(ready.get("degraded_reason", "") or "")
            self.readiness.setText(f"JARVIS {state}" + (f" · {extra}" if extra else ""))

        for key in ("GROQ", "OPENROUTER", "GEMINI", "OLLAMA"):
            state = str(provs.get(key, {}).get("state", "UNKNOWN"))
            badge = self._provider_badge(state)
            self.provider_labels[key].setText(f"{key:<10} {badge}")

        prim = providers_payload.get("primary") or {}
        if prim.get("actual_provider"):
            self.primary_value.setText(f"{prim['actual_provider'].upper()}\n{prim.get('actual_model', '')}")
            if prim.get("fallback"):
                self.fallback.setText(f"FALLBACK {prim.get('fallback_reason', '')}")
            else:
                self.fallback.setText("")
        else:
            prim_list = providers_payload.get("primary_models", []) or []
            general = next((m for m in prim_list if m.get("profile") == "GENERAL"),
                           prim_list[0] if prim_list else None)
            if general:
                self.primary_value.setText(f"{general['provider'].upper()}\n{general['model']}")
            else:
                self.primary_value.setText("--")
            self.fallback.setText("")

        # Tasks
        counts = self._task_counts(tasks)
        self.t_active.setText(f"ACTIVE   {counts['active']}")
        self.t_wait.setText(f"WAITING  {counts['waiting']}")
        self.t_err.setText(f"ERROR    {counts['errors']}")

    def update_services(self, status: dict, voice: dict, radar: dict):
        """Atualiza status dos serviços."""
        online = bool((status or {}).get("ok"))

        # Golden
        self.svc_labels["GOLDEN"].setText(
            f"GOLDEN BACKEND      {'● ONLINE' if online else '○ OFFLINE'}"
        )
        self.svc_labels["GOLDEN"].setStyleSheet(
            f"color: {GOOD if online else BAD};"
        )

        # MT5
        from ..status_format import mt5_display
        mt5 = mt5_display(status)
        self.svc_labels["MT5"].setText(f"METATRADER 5        {mt5['label']}")
        self.svc_labels["MT5"].setStyleSheet(
            f"color: {GOOD if mt5['connected'] else TEXT_MUTED};"
        )

        # Radar
        from ..status_format import radar_display
        rd = radar_display(radar)
        self.svc_labels["RADAR"].setText(f"RADAR               {rd['label']}")
        self.svc_labels["RADAR"].setStyleSheet(
            f"color: {GOOD if rd['active'] else TEXT_MUTED};"
        )

        # Voice
        from ..status_format import voice_display
        vd = voice_display(voice)
        self.svc_labels["VOICE"].setText(f"VOICE SERVICE       {vd}")
        self.svc_labels["VOICE"].setStyleSheet(f"color: {TEXT_SECONDARY};")

        # Net
        con = (status or {}).get("connections", {}) if isinstance(status, dict) else {}
        net = online or bool(con.get("ollama", {}).get("ok"))
        self.svc_labels["NET"].setText(f"INTERNET            {'● ONLINE' if net else '○ OFFLINE'}")
        self.svc_labels["NET"].setStyleSheet(
            f"color: {GOOD if net else BAD};"
        )

    # ===== Helpers =====

    def _bar_blocks(self, percent):
        try:
            pct = max(0, min(100, float(percent)))
        except (TypeError, ValueError):
            return "░░░░░░░░░░ N/D"
        full = int(round(pct / 10))
        return "█" * full + "░" * (10 - full) + f" {pct:.0f}%"

    def _pct_color(self, pct):
        if pct >= 85: return BAD
        if pct >= 65: return WARN
        return GOOD

    def _provider_badge(self, state):
        return {
            "ONLINE": "● ONLINE", "RATE_LIMITED": "! RATE LIMITED",
            "DEGRADED": "! DEGRADED", "TIMEOUT": "! TIMEOUT",
            "AUTH_ERROR": "! AUTH ERROR", "OFFLINE": "○ OFFLINE"
        }.get(str(state), "? UNKNOWN")

    def _task_counts(self, tasks):
        active_s = {"QUEUED", "RUNNING", "WAITING_CONFIRMATION", "CANCEL_REQUESTED"}
        active = waiting = errors = 0
        for t in tasks or []:
            s = str(t.get("status"))
            if s in active_s:
                active += 1
            if s == "WAITING_CONFIRMATION":
                waiting += 1
            if s in ("FAILED", "INTERRUPTED"):
                errors += 1
        return {"active": active, "waiting": waiting, "errors": errors}