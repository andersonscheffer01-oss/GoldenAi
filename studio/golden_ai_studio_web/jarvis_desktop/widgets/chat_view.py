"""Console V3: conversa integrada, sem bubbles — linhas finas + glow discreto."""
from __future__ import annotations

import html

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

ACCENT = "#22d3ee"

CSS = """<style>
body { font-family:'Segoe UI',Arial; font-size:13px; color:#d9e8f5; }
.j { margin:6px 0 6px 0; padding:2px 0 6px 12px; border-left:2px solid #22d3ee; }
.u { margin:6px 0 6px 40px; padding:2px 0 6px 12px; border-left:1px solid #33507a; text-align:left; }
.who { color:#22d3ee; font-size:10px; font-weight:bold; letter-spacing:2px; }
.who-u { color:#8ba3c4; font-size:10px; font-weight:bold; letter-spacing:2px; }
hr { border:none; border-top:1px solid #0e1d33; }
</style>"""


class ChatWidget(QWidget):
    def __init__(self, on_send, on_voice_toggle, parent=None):
        super().__init__(parent)
        self._on_send = on_send
        self._on_voice = on_voice_toggle
        self._dev = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.history = QTextEdit()
        self.history.setProperty("class", "console")
        self.history.setReadOnly(True)
        self.history.setHtml(f"{CSS}<div class='j'><span class='who'>◉ JARVIS</span><br>Como posso ajudar?</div>"
                                 "<div class='u'><span class='who-u'>CONSOLE</span><br>link com o backend Golden ativo — digite ou fale.</div>")
        layout.addWidget(self.history, 1)
        self.meta = QLabel("ROUTE -- · BRAIN -- · CONF --")
        self.meta.setProperty("class", "route")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)
        # barra de comando sci-fi
        row = QHBoxLayout()
        self.mic = QPushButton("◉")
        self.mic.setProperty("class", "mic")
        self.mic.setFixedSize(34, 34)
        self.mic.setToolTip("Ativar/Desativar voz")
        self.mic.clicked.connect(self._on_voice)
        self.input = QLineEdit()
        self.input.setProperty("class", "command")
        self.input.setPlaceholderText("DIGITE OU FALE COM JARVIS...")
        self.input.returnPressed.connect(self._send)
        self.send = QPushButton("➤ SEND")
        self.send.setProperty("class", "send")
        self.send.clicked.connect(self._send)
        row.addWidget(self.mic)
        row.addWidget(self.input, 1)
        row.addWidget(self.send)
        layout.addLayout(row)
        self.setAcceptDrops(True)

    def set_dev(self, enabled):
        self._dev = bool(enabled)

    def set_mic_state(self, listening):
        self.mic.setText("◉" if not listening else "◎")
        self.mic.setStyleSheet("color:#2dd4bf; box-shadow:none;" if listening else "")

    def _send(self):
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self._on_send(text)

    def add_user(self, text):
        safe = html.escape(text).replace("\n", "<br>")
        self.history.append(f"<div class='u'><span class='who-u'>YOU</span><br>{safe}</div><hr>")
        self._reveal()

    def add_jarvis(self, text):
        safe = html.escape(str(text)).replace("\n", "<br>")
        self.history.append(f"<div class='j'><span class='who'>◉ JARVIS</span><br>{safe}</div><hr>")
        self._reveal()

    def _reveal(self):
        """Garante que a mensagem nova fique visivel (cursor no fim)."""
        try:
            self.history.moveCursor(self.history.textCursor().End)
            self.history.ensureCursorVisible()
        except Exception:
            pass

    def set_meta(self, route="", brain="", conf="", skill="", provider="", dev_extra="", llm=None):
        if str(brain).startswith("deterministic"):
            brain = "NONE"
        base = f"ROUTE {route or '--'} · BRAIN {brain or '--'} · CONF {conf or '--'}"
        prov = provider or ((llm or {}).get("provider", "") if isinstance(llm, dict) else "")
        extra = f"SKILL {skill or '--'} · PROVIDER {prov.upper() if prov else '--'}"
        if isinstance(llm, dict) and llm:
            fb = llm.get("fallback")
            fb_txt = "NONE"
            if fb:
                fb_txt = str(llm.get("fallback_reason") or "FALLBACK")
            extra += (f" · PROFILE {llm.get('profile', '--')} · MODEL {llm.get('model', '--')} "
                      f"· FB {fb_txt} · {llm.get('latency_ms', '--')}ms")
            if (llm.get("provider") or "") == "ollama" and not fb:
                extra += " · LOCAL"
        if self._dev and dev_extra:
            extra += f" · {dev_extra}"
        self.meta.setText(base + "\n" + extra)
