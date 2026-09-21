"""QuickActionsGrid: Grid de ações rápidas para modo CONTROLE."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget, QSizePolicy

from ..theme_v4 import QUICK_ACTIONS


class QuickActionsGrid(QWidget):
    """Grid 2x3 (ou 3x2) de botões de ação rápida."""

    actionTriggered = Signal(str)  # action id

    def __init__(self, parent=None, columns: int = 3):
        super().__init__(parent)
        self._columns = columns
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.buttons = {}
        for idx, action in enumerate(QUICK_ACTIONS):
            btn = QPushButton()
            btn.setProperty("class", "quickActionBtn")
            if action.get("primary"):
                btn.setProperty("primary", "true")
                btn.setStyleSheet("""
                    QPushButton[primary="true"] {
                        border-color: #00e5ff;
                        color: #00e5ff;
                    }
                    QPushButton[primary="true"]:hover {
                        background: rgba(0, 229, 255, 0.15);
                    }
                """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.setMinimumHeight(72)

            # Texto com ícone
            btn.setText(f"{action['icon']}\n{action['label']}")
            btn.clicked.connect(lambda checked, a=action['id']: self.actionTriggered.emit(a))

            row = idx // columns
            col = idx % columns
            layout.addWidget(btn, row, col)
            self.buttons[action['id']] = btn

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

    def set_action_enabled(self, action_id: str, enabled: bool):
        if action_id in self.buttons:
            self.buttons[action_id].setEnabled(enabled)

    def set_action_text(self, action_id: str, text: str):
        if action_id in self.buttons:
            self.buttons[action_id].setText(text)