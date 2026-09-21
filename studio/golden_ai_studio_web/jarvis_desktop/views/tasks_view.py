"""Aba Tasks V2: cards com progresso real + step atual + cancelar."""
from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

from ..status_format import bar_blocks


class TasksView(QWidget):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self._a = actions
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.itemClicked.connect(lambda *_: self._a["detail"](self.current_id()))
        left.addWidget(QLabel("Tarefas (reais)"))
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Atualizar")
        self.refresh_btn.clicked.connect(lambda: self._a["refresh"]())
        self.cancel_btn = QPushButton("Cancelar selecionada")
        self.cancel_btn.setProperty("class", "danger")
        self.cancel_btn.clicked.connect(lambda: self._a["cancel"](self.current_id()))
        row.addWidget(self.refresh_btn)
        row.addWidget(self.cancel_btn)
        left.addLayout(row)
        layout.addLayout(left, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel("Detalhe (sem pausar/retomar: não suportado pelo TaskManager)"))
        self.detail = QTextEdit()
        self.detail.setProperty("class", "console")
        self.detail.setReadOnly(True)
        right.addWidget(self.detail, 1)
        layout.addLayout(right, 1)
        self._ids = []

    def current_id(self):
        row = self.list.currentRow()
        return self._ids[row] if 0 <= row < len(self._ids) else ""

    def set_tasks(self, tasks):
        self._ids = [t.get("id", "") for t in tasks or []]
        self.list.clear()
        for t in tasks or []:
            title = (t.get("title") or t.get("id") or "?")[:60].upper()
            self.list.addItem(f"{title}\n● {t.get('status')}")

    def set_detail(self, payload):
        if not isinstance(payload, dict) or not payload.get("ok"):
            self.detail.setPlainText(f"Erro: {(payload or {}).get('error', 'falha')}")
            return
        task = payload.get("task", {})
        prog = task.get("progress", {}) or {}
        done, total = prog.get("done", 0), prog.get("total", 0)
        pct = (done / total * 100) if total else 0
        status = str(task.get("status", ""))
        lines = [str(task.get("title", "")).upper(), f"● {status}",
                 bar_blocks(pct) if total else "QUEUED — aguardando início"]
        if status == "WAITING_CONFIRMATION":
            lines.append("CONFIRMAÇÃO NECESSÁRIA")
        cur = task.get("current_step") or {}
        if cur:
            step_no = sum(1 for s in payload.get("steps", [])
                          if s.get("status") == "COMPLETED") + 1
            lines.append(f"STEP {step_no}/{total} — {cur.get('intent') or cur.get('id')} [{cur.get('status')}]")
        if task.get("error"):
            lines.append(f"erro: {task['error']}")
        self.detail.setPlainText("\n".join(lines))
