"""ControleView: View do modo CONTROLE — núcleo radial + painéis laterais + comando manual + ações rápidas.

Fase 3: Dados reais do backend (providers, skills, projects, tasks, radar).
"""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget, QLabel,
                                QListWidget, QListWidgetItem, QPushButton,
                                QFrame, QSizeGrip, QSizePolicy)

from ..widgets.backdrop_v4 import BackdropV4
from ..widgets.radial_core import RadialCore
from ..widgets.quick_actions import QuickActionsGrid
from ..widgets.manual_command import ManualCommandBar
from ..widgets.hud_panel_v4 import HudPanelV4
from ..theme_v4 import (
    BG_PANEL, BORDER_SUBTLE, CYAN, GOLD, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GOOD, WARN, BAD, MONO_FONT, RADIUS_MD
)


NODE_ACTION_MAP = {
    "pesquisa": "pesquisar na web",
    "memoria": "ver memória recente",
    "projetos": "listar projetos",
    "automacao": "ver automações ativas",
    "analise": "analisar mercado",
    "documentos": "listar documentos",
    "agenda": "ver agenda",
    "internet": "ver status internet",
    "ferramentas": "listar ferramentas",
    "trading": "ver status trading",
    "design": "ver projetos design",
    "nucleo": "status do núcleo",
}


class AgentListItem(QWidget):
    """Item de agente/serviço ativo para lista."""
    def __init__(self, agent_data: dict, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(16)
        layout.addWidget(self.status_dot)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        self.name_label = QLabel(agent_data.get("name", ""))
        self.name_label.setProperty("class", "telemetry")
        self.name_label.setStyleSheet("font-weight: 700; font-size: 11px;")
        info_layout.addWidget(self.name_label)

        self.task_label = QLabel(f"{agent_data.get('task', '—')}")
        self.task_label.setProperty("class", "muted")
        self.task_label.setStyleSheet("font-size: 9px;")
        info_layout.addWidget(self.task_label)
        layout.addLayout(info_layout, 1)

        self.update_status(agent_data.get("status", "IDLE"))

    def update_status(self, status: str):
        color_map = {
            "IDLE": TEXT_MUTED,
            "READY": GOOD,
            "RUNNING": CYAN,
            "ONLINE": GOOD,
            "OFFLINE": BAD,
            "WARN": WARN,
            "ERROR": "#ff4444",
            "WAITING": WARN,
            "SHADOW": TEXT_SECONDARY,
        }
        color = color_map.get(status, TEXT_MUTED)
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 12px;")


class ProjectListItem(QWidget):
    """Item de projeto recente para lista."""
    def __init__(self, project_data: dict, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        ext = project_data.get("ext", "")
        type_map = {
            ".mq5": "MQL5",
            ".mq4": "MQL4",
            ".py": "PYTHON",
            ".js": "JS",
            ".html": "HTML",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
        }
        type_label = type_map.get(str(ext).lower(), str(ext).upper().lstrip(".") or "FILE")

        self.type_label = QLabel(type_label)
        self.type_label.setProperty("class", "muted")
        self.type_label.setFixedWidth(60)
        self.type_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.type_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        self.name_label = QLabel(project_data.get("name", ""))
        self.name_label.setProperty("class", "telemetry")
        self.name_label.setStyleSheet("font-weight: 700; font-size: 11px;")
        info_layout.addWidget(self.name_label)

        path = project_data.get("path", "")
        size = project_data.get("size", 0)
        size_str = f"{size / 1024:.1f} KB" if isinstance(size, (int, float)) and size > 0 else ""
        self.path_label = QLabel(size_str or path[-40:] if len(path) > 40 else path)
        self.path_label.setProperty("class", "muted")
        self.path_label.setStyleSheet("font-size: 9px;")
        info_layout.addWidget(self.path_label)
        layout.addLayout(info_layout, 1)

        self.open_btn = QPushButton("ABRIR")
        self.open_btn.setProperty("class", "actionBtn")
        self.open_btn.setFixedSize(60, 28)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(lambda: self._open_file(path))
        layout.addWidget(self.open_btn)

    def _open_file(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception:
                subprocess.Popen(["explorer", os.path.dirname(path) or path])


class ControleView(QWidget):
    """
    View principal do modo CONTROLE.
    Fase 3: Dados reais do backend.

    Layout:
    - BackdropV4 (fundo)
    - Esquerda: RadialCore (núcleo + 12 nós)
    - Direita superior: ActiveAgentsPanel + RecentProjectsPanel
    - Direita inferior: QuickActionsGrid
    - Bottom: ManualCommandBar
    """

    nodeActionTriggered = Signal(str)

    def __init__(self, on_manual_command, parent=None):
        super().__init__(parent)
        self._on_manual_command = on_manual_command

        self.backdrop = BackdropV4()
        self.setAttribute(Qt.WA_StyledBackground, True)

        root_layout = QHBoxLayout(self.backdrop)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(16)

        # ===== ESQUERDA: RADIAL CORE =====
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        title = QLabel("NÚCLEO GOLDEN JARVIS")
        title.setProperty("class", "brandGold")
        title.setStyleSheet("font-size: 14px; letter-spacing: 4px;")
        title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title)

        self.radial_core = RadialCore()
        self.radial_core.setMinimumSize(420, 420)
        self.radial_core.canvas.nodeClicked.connect(self._on_node_clicked)
        left_layout.addWidget(self.radial_core, 1)

        self.conn_toggle = QPushButton("MOSTRAR CONEXÕES")
        self.conn_toggle.setProperty("class", "actionBtn")
        self.conn_toggle.setCheckable(True)
        self.conn_toggle.setChecked(True)
        self.conn_toggle.setCursor(Qt.PointingHandCursor)
        self.conn_toggle.toggled.connect(self.radial_core.set_connections_visible)
        left_layout.addWidget(self.conn_toggle, 0, Qt.AlignCenter)

        root_layout.addWidget(left_widget, 2)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setStyleSheet(f"border: none; border-left: 1px solid {BORDER_SUBTLE}; max-width: 1px;")
        root_layout.addWidget(vsep)

        # ===== DIREITA: PAINÉIS =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.agents_panel = HudPanelV4("AGT·01", "SERVIÇOS  ●  LIVE")
        self.agents_list = QListWidget()
        self.agents_list.setFrameShape(QListWidget.NoFrame)
        self.agents_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.agents_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; }
            QListWidget::item { border: none; padding: 2px 0; }
        """)
        self.agents_panel.body.addWidget(self.agents_list, 1)
        right_layout.addWidget(self.agents_panel, 1)

        self.projects_panel = HudPanelV4("PRJ·02", "PROJETOS  ●  LIVE")
        self.projects_list = QListWidget()
        self.projects_list.setFrameShape(QListWidget.NoFrame)
        self.projects_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.projects_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; }
            QListWidget::item { border: none; padding: 2px 0; }
        """)
        self.projects_panel.body.addWidget(self.projects_list, 1)
        right_layout.addWidget(self.projects_panel, 1)

        self.quick_actions = QuickActionsGrid()
        self.quick_actions.actionTriggered.connect(self._on_quick_action)
        right_layout.addWidget(self.quick_actions, 0)

        self.command_bar = ManualCommandBar()
        self.command_bar.commandSubmitted.connect(self._on_manual_command)
        right_layout.addWidget(self.command_bar, 0)

        root_layout.addWidget(right_widget, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.backdrop)

    def _on_node_clicked(self, node_id: str):
        cmd = NODE_ACTION_MAP.get(node_id, node_id)
        self._on_manual_command(cmd)

    def _on_quick_action(self, action_id: str):
        cmd_map = {
            "nova_tarefa": "criar uma nova tarefa",
            "executar_agente": "executar agente agora",
            "abrir_projeto": "listar projetos disponíveis",
            "ver_logs": "mostrar logs recentes",
            "configurar": "abrir configurações",
            "atualizar": "atualizar status do sistema",
        }
        cmd = cmd_map.get(action_id, action_id)
        self._on_manual_command(cmd)

    # ===== API pública para dados reais =====

    def set_agents(self, agents: list[dict]):
        """Atualiza lista de agentes/serviços com dados reais."""
        self.agents_list.clear()
        if not agents:
            item = QListWidgetItem()
            widget = AgentListItem({"name": "AGUARDANDO...", "status": "IDLE", "task": "Backend offline"})
            item.setSizeHint(widget.sizeHint())
            self.agents_list.addItem(item)
            self.agents_list.setItemWidget(item, widget)
            return
        for agent in agents:
            item = QListWidgetItem()
            widget = AgentListItem(agent)
            item.setSizeHint(widget.sizeHint())
            self.agents_list.addItem(item)
            self.agents_list.setItemWidget(item, widget)

    def set_projects(self, projects: list[dict]):
        """Atualiza lista de projetos com dados reais."""
        self.projects_list.clear()
        if not projects:
            item = QListWidgetItem()
            widget = ProjectListItem({"name": "NENHUM PROJETO ENCONTRADO", "ext": "", "path": ""})
            item.setSizeHint(widget.sizeHint())
            self.projects_list.addItem(item)
            self.projects_list.setItemWidget(item, widget)
            return
        for proj in projects[:8]:
            item = QListWidgetItem()
            widget = ProjectListItem(proj)
            item.setSizeHint(widget.sizeHint())
            self.projects_list.addItem(item)
            self.projects_list.setItemWidget(item, widget)

    def set_agents_from_providers(self, providers_data: dict, skills_data: list, orchestrator_data: dict, radar_data: dict):
        """Constrói lista de agentes a partir dos dados reais do backend."""
        agents = []

        orch = orchestrator_data if isinstance(orchestrator_data, dict) else {}
        last_dec = orch.get("last_decision") or {}
        orch_mode = orch.get("mode", "shadow").upper()
        agents.append({
            "name": f"ORCHESTRATOR [{orch_mode}]",
            "status": "RUNNING" if orch.get("ok") else "OFFLINE",
            "task": f"Rota: {last_dec.get('route', '—')} · Skill: {last_dec.get('skill', '—')}",
        })

        p_data = providers_data if isinstance(providers_data, dict) else {}
        providers = p_data.get("providers", [])
        primary = p_data.get("primary") or {}
        for prov in providers:
            state = str(prov.get("state", "")).upper()
            name = prov.get("name", "unknown").upper()
            configured = prov.get("configured", False)
            if not configured:
                status = "IDLE"
                task = "Não configurado"
            elif state == "READY" or state == "ONLINE":
                status = "READY"
                is_primary = name.lower() in str(primary.get("actual_provider", "")).lower()
                task = f"{'PRIMÁRIO' if is_primary else 'Disponível'}"
            elif state == "SHADOW":
                status = "SHADOW"
                task = "Modo shadow"
            elif state == "OFFLINE" or state == "ERROR":
                status = "OFFLINE"
                task = "Indisponível"
            else:
                status = state
                task = prov.get("state", "—")
            agents.append({"name": name, "status": status, "task": task})

        skills = skills_data if isinstance(skills_data, list) else []
        ready_count = sum(1 for s in skills if s.get("status") == "READY")
        agents.append({
            "name": f"SKILLS [{ready_count}/{len(skills)}]",
            "status": "READY" if ready_count > 0 else "IDLE",
            "task": f"{ready_count} prontas" if ready_count else "Nenhuma skill",
        })

        rad = radar_data if isinstance(radar_data, dict) else {}
        rad_running = rad.get("running", False)
        agents.append({
            "name": "RADAR",
            "status": "RUNNING" if rad_running else "IDLE",
            "task": f"Sinais: {rad.get('signal_counts', {})}" if rad_running else "Parado",
        })

        self.set_agents(agents)

    def set_radial_node_active(self, node_id: str, active: bool):
        self.radial_core.set_node_active(node_id, active)

    def get_radial_core(self) -> RadialCore:
        return self.radial_core

    def get_quick_actions(self) -> QuickActionsGrid:
        return self.quick_actions

    def get_command_bar(self) -> ManualCommandBar:
        return self.command_bar
