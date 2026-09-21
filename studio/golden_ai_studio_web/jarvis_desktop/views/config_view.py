"""Aba Config V2: switches reais (voz, dev, tray, minimizar)."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class ConfigView(QWidget):
    def __init__(self, callbacks, parent=None):
        super().__init__(parent)
        self._cb = callbacks
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Config"))
        self.voice = QCheckBox("VOICE — escuta local (VoiceService existente)")
        self.voice.setChecked(True)
        self.voice.toggled.connect(lambda v: self._cb["voice"](bool(v)))
        self.dev = QCheckBox("DEVELOPER MODE — route bar estendida + aba DEV")
        self.dev.toggled.connect(lambda v: self._cb["dev"](bool(v)))
        self.tray = QCheckBox("MINIMIZE TO TRAY — fechar minimiza para a bandeja")
        self.tray.setChecked(True)
        self.tray.toggled.connect(lambda v: self._cb["tray"](bool(v)))
        self.min_start = QCheckBox("START MINIMIZED — abrir já minimizado")
        self.min_start.toggled.connect(lambda v: self._cb["min_start"](bool(v)))
        for w in (self.voice, self.dev, self.tray, self.min_start):
            layout.addWidget(w)
        self.info = QLabel("")
        self.info.setProperty("class", "muted")
        self.info.setWordWrap(True)
        layout.addWidget(self.info, 1)
        layout.addStretch(1)

    def render_info(self, base_url, capabilities):
        caps = (capabilities or {}).get("capabilities", []) if isinstance(capabilities, dict) else []
        lines = [f"backend: {base_url}", "orchestrator: SHADOW (fixo nesta versão)", "",
                 "Anexos (backend):"]
        lines += [f"- {c.get('name')}: {c.get('status')}" for c in caps] or ["- sem dados (backend offline)"]
        lines.append("Arraste arquivos sobre o chat: ingestão ainda não implementada.")
        self.info.setText("\n".join(lines))
