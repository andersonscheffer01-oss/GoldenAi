"""ManualCommandBar: Barra de comando manual para modo CONTROLE."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget, QLabel

from ..theme_v4 import CYAN, GOLD, TEXT_MUTED, MONO_FONT


class ManualCommandBar(QWidget):
    """Input de comando manual + botão executar + sugestões."""

    commandSubmitted = Signal(str)  # comando texto

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Label
        self.label = QLabel("COMANDO MANUAL")
        self.label.setProperty("class", "hudTag")
        self.label.setFixedWidth(140)
        layout.addWidget(self.label)

        # Input
        self.input = QLineEdit()
        self.input.setProperty("class", "commandBar")
        self.input.setPlaceholderText("Digite um comando para o núcleo (ex: execute mql5_dev scan eurusd)...")
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input, 1)

        # Botão executar
        self.execute_btn = QPushButton("EXECUTAR")
        self.execute_btn.setProperty("class", "actionBtn primary")
        self.execute_btn.setCursor(Qt.PointingHandCursor)
        self.execute_btn.setFixedWidth(130)
        self.execute_btn.clicked.connect(self._submit)
        layout.addWidget(self.execute_btn)

        # Sugestões (botões rápidos)
        self.suggestions = QWidget()
        self.suggestions_layout = QHBoxLayout(self.suggestions)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestions_layout.setSpacing(8)
        layout.addWidget(self.suggestions, 1)

        self._add_default_suggestions()

    def _add_default_suggestions(self):
        """Adiciona botões de sugestão padrão."""
        suggestions = [
            ("scan", "SCAN MERCADO"),
            ("status", "STATUS SISTEMA"),
            ("tasks", "LISTAR TAREFAS"),
            ("agents", "AGENTES ATIVOS"),
        ]
        for cmd, label in suggestions:
            btn = QPushButton(label)
            btn.setProperty("class", "actionBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda checked, c=cmd: self.input.setText(c))
            self.suggestions_layout.addWidget(btn)
        self.suggestions_layout.addStretch(1)

    def _submit(self):
        text = self.input.text().strip()
        if text:
            self.commandSubmitted.emit(text)
            self.input.clear()

    def set_placeholder(self, text: str):
        self.input.setPlaceholderText(text)

    def set_enabled(self, enabled: bool):
        self.input.setEnabled(enabled)
        self.execute_btn.setEnabled(enabled)