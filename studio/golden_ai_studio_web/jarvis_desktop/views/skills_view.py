"""Aba Skills V2: cards compactos reais."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget


class SkillsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Skills (reais, sem simulação)"))
        self.list = QListWidget()
        layout.addWidget(self.list, 1)

    def render(self, payload):
        self.list.clear()
        skills = (payload or {}).get("skills", []) if isinstance(payload, dict) else []
        if not skills:
            self.list.addItem("Sem dados — backend offline ou sem skills.")
            return
        for s in skills:
            dot = "●" if s.get("status") == "READY" else ("◐" if s.get("status") == "PARTIAL" else "○")
            tools = ", ".join(s.get("tools", []) or ["-"])
            self.list.addItem(f"{str(s.get('name', '')).upper()}\n{dot} {s.get('status')} · {tools}")
