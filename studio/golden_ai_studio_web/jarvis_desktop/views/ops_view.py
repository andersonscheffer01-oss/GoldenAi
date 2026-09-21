"""Abas RADAR/MT5 V2: dados reais, NO DATA quando ausente, sem trading."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget


class OpsView(QWidget):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("RADAR" if kind == "radar" else "MT5"))
        self.box = QTextEdit()
        self.box.setProperty("class", "console")
        self.box.setReadOnly(True)
        layout.addWidget(self.box, 1)

    def render_radar(self, radar):
        if not isinstance(radar, dict) or not radar.get("ok") or not radar.get("running"):
            self.box.setPlainText("RADAR ○ NO DATA\n\nMonitor não confirmado pelo backend.\nEspaço futuro: mercado, regime, volatilidade, sinais.")
            return
        counts = radar.get("signal_counts", {}) or {}
        last = radar.get("last_run") or {}
        lines = ["RADAR ● ACTIVE", "",
                 f"última varredura: {last.get('finished_at', 'N/D')}",
                 f"ativos: {last.get('assets', 'N/D')}  oportunidades: {last.get('opportunities', 'N/D')}",
                 "", "sinais por status:"]
        lines += [f"- {k}: {v}" for k, v in counts.items()] or ["- NO DATA"]
        self.box.setPlainText("\n".join(lines))

    def render_mt5(self, mt5):
        if not mt5.get("connected"):
            self.box.setPlainText("MT5 ○ DISCONNECTED\n\nAbra o MetaTrader 5 para conectar.")
            return
        lines = ["MT5 ● CONNECTED", "", f"Broker: {mt5.get('broker')}",
                 f"Server: {mt5.get('server')}", f"Account: {mt5.get('account')}"]
        if mt5.get("balance") is not None:
            try:
                lines.append(f"Balance: {float(mt5['balance']):.2f}")
            except (TypeError, ValueError):
                pass
        lines.append("\nTrading não implementado nesta fase (somente leitura).")
        self.box.setPlainText("\n".join(lines))
