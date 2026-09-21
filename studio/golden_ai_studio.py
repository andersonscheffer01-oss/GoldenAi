import os
import sys
import json
import subprocess
import difflib
import re
import unicodedata
import sqlite3
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QSize, QTimer, QProcessEnvironment, QSettings
from PySide6.QtGui import QAction, QFont, QKeySequence, QTextCursor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QTreeView, QFileSystemModel, QTabWidget, QPlainTextEdit, QTextEdit,
    QLineEdit, QPushButton, QLabel, QToolBar, QStatusBar, QFileDialog,
    QMessageBox, QDockWidget, QListWidget, QListWidgetItem, QFrame, QSizePolicy,
    QToolButton, QMenu, QScrollArea, QStackedWidget
)

APP_ROOT_FOR_IMPORT = Path(r"C:\GoldenAI")
if str(APP_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT_FOR_IMPORT))

from core.activity import ActivityService
from core.config import load_settings
from core.attachments import AttachmentService
from core.coding import CodingProjectService, CodingService
from core.execution import ExecutionService, PermissionMode
from core.intent import IntentRouter
from core.permissions.external_access import ExternalAccessService
from core.permissions.v2 import PermissionManagerV2, Operation as PermOp
from core.project_intelligence import ProjectIntelligenceService
from core.vision import VisionService

APP_ROOT = Path(r"C:\GoldenAI")
APP_DIR = APP_ROOT / "app"
PROJECTS_DIR = APP_ROOT / "projetos"
ENGINE = APP_DIR / "golden_ai.py"
BRIDGE = APP_ROOT / "studio" / "golden_ai_pty_bridge.py"
PYTHON_EXE = APP_ROOT / ".venv" / "Scripts" / "python.exe"
HISTORY_FILE = APP_ROOT / "studio" / "historico_v2.json"

THEME = """
/* Golden AI Studio - Tema Ouro & Black v2 */
QMainWindow, QWidget { 
    background: #1a1a2e; 
    color: #F5F5F5; 
    font-family: "Segoe UI", "Helvetica", sans-serif; 
    font-size: 10pt; 
}
QToolBar { 
    background: #0f0f1a; 
    border: none; 
    border-bottom: 1px solid #2d2d4a; 
    spacing: 6px; 
    padding: 6px; 
}
QFrame#sidebar { 
    background: #0f0f1a; 
    border: 1px solid #2d2d4a; 
    border-radius: 12px; 
}
QFrame#surface, QFrame#chatPanel, QFrame#modulePanel, QFrame#terminalPanel { 
    background: #16213e; 
    border: 1px solid #2d2d4a; 
    border-radius: 12px; 
}
QFrame#composer { 
    background: #252540; 
    border: 1px solid #3d3d5c; 
    border-radius: 12px; 
}
QFrame#card { 
    background: #1f2a44; 
    border: 1px solid #2d3a5c; 
    border-radius: 10px; 
}
QTreeView, QPlainTextEdit, QTextEdit, QLineEdit, QListWidget, QTabWidget::pane {
    background: #16213e; 
    color: #F5F5F5; 
    border: 1px solid #2d2d4a; 
    border-radius: 10px;
    selection-background-color: #f0c040; 
    selection-color: #0d0d0d;
}
QTextEdit { 
    padding: 10px; 
    border-radius: 10px; 
}
QLineEdit { 
    padding: 0 16px; 
    min-height: 44px; 
    border-radius: 10px; 
}
QTreeView { 
    border-radius: 10px; 
    show-decoration-selected: 1; 
}
QTreeView::item, QListWidget::item { 
    padding: 8px 8px; 
    border-radius: 8px; 
    margin: 2px 4px; 
}
QTreeView::item:selected, QListWidget::item:selected { 
    background: #f0c040; 
    color: #0d0d0d; 
    border-radius: 8px; 
}
QPushButton, QToolButton {
    background: #252540; 
    color: #F5F5F5; 
    border: 1px solid #3d3d5c;
    padding: 10px 14px; 
    border-radius: 10px; 
    text-align: left;
    font-weight: 500;
}
QPushButton:hover, QToolButton:hover { 
    background: #3d3d5c; 
    border-color: #f0c040; 
}
QPushButton[navMinimized="true"], QToolButton[navMinimized="true"] {
    text-align: center;
    padding: 10px 0;
    font-size: 14px;
    border-radius: 10px;
}
QPushButton[navMinimized="false"], QToolButton[navMinimized="false"] {
    text-align: left;
}
QPushButton:checked, QPushButton#activeNav { 
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d4a017, stop:1 #f0c040); 
    color: #0d0d0d; 
    border-color: #f0c040; 
}
QPushButton#primary { 
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d4a017, stop:1 #f0c040); 
    color: #0d0d0d; 
    border: 1px solid #f0c040; 
    border-radius: 12px; 
    padding: 10px 20px; 
    font-weight:700; 
    text-align:center; 
}
QPushButton#primary:hover {
    background: #ffd700;
}
QPushButton#ghost { 
    background: transparent; 
    border: 1px solid transparent; 
    color: #999999; 
}
QPushButton#ghost:hover { 
    color: #f0c040; 
    border-color: #3d3d5c; 
    border-radius: 8px;
}
QLabel#title { 
    font-size: 16px; 
    font-weight: 800; 
    color: #f0c040; 
}
QLabel#panelTitle { 
    font-size: 16px; 
    font-weight: 700; 
    color: #F5F5F5; 
    margin-bottom: 4px;
}
QLabel#hero { 
    font-size: 24px; 
    font-weight: 700; 
    color: #F5F5F5; 
}
QLabel#muted { 
    color: #999999; 
    font-size: 12px;
}
QLabel#badgeReadOnly { 
    background: #1a2e1a; 
    color: #4caf50; 
    border: 1px solid #2d4a2d; 
    padding: 5px 10px; 
    border-radius: 12px; 
    font-weight: 600; 
    font-size: 11px;
}
QLabel#pill { 
    background: #252540; 
    color: #f0c040; 
    border: 1px solid #3d3d5c; 
    padding: 6px 12px; 
    border-radius: 12px; 
    font-size: 11px;
}
QTabBar::tab { 
    background: #16213e; 
    color: #999999; 
    padding: 10px 16px; 
    border: 1px solid #2d2d4a; 
    border-radius: 12px 12px 0 0;
    margin-right: 4px;
}
QTabBar::tab:selected { 
    background: #252540; 
    color: #f0c040; 
    border-bottom: 1px solid #252540;
}
QStatusBar { 
    background: #0f0f1a; 
    color: #CCCCCC; 
    border-top: 1px solid #3A3A3A; 
    padding: 4px 12px;
    font-size: 11px;
}
QScrollBar:vertical { 
    background: #1E1E1E; 
    width: 10px; 
    margin: 0; 
    border: none; 
    border-radius: 5px;
}
QScrollBar::handle:vertical { 
    background: #4A4A4A; 
    min-height: 32px; 
    border-radius: 5px; 
    margin: 2px;
}
QScrollBar::handle:vertical:hover { 
    background: #FFD700; 
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
    height: 0; 
    border: none; 
    background: transparent; 
}
QScrollBar:horizontal { 
    background: #1E1E1E; 
    height: 10px; 
    margin: 0; 
    border: none; 
    border-radius: 5px;
}
QScrollBar::handle:horizontal { 
    background: #4A4A4A; 
    min-width: 32px; 
    border-radius: 5px; 
    margin: 2px;
}
QScrollBar::handle:horizontal:hover { 
    background: #FFD700; 
    border-radius: 5px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
    width: 0; 
    border: none; 
    background: transparent; 
}
QDockWidget { 
    color: #FFFFFF; 
    titlebar-close-icon: none; 
}
QDockWidget::title { 
    background: #232323; 
    padding: 6px 10px; 
    border: 1px solid #3A3A3A; 
    border-top-left-radius: 10px; 
    border-top-right-radius: 10px; 
    font-weight: 700; 
    color: #FFFFFF; 
}
QDockWidget > QWidget { 
    background: #1E1E1E; 
    border: 1px solid #3A3A3A; 
    border-top: none; 
}
QPushButton#dockBtn { 
    background: #3A3A3A; 
    color: #FFFFFF; 
    border: 1px solid #4A4A4A; 
    border-radius: 6px; 
    padding: 0; 
    font-weight: 700; 
    text-align: center; 
}
QPushButton#dockBtn:hover { 
    background: #FFD700; 
    color: #161616; 
    border-color: #FFD700; 
}
QFrame#userBox { 
    background: #2A2A2A; 
    border: 1px solid #4A4A4A; 
    border-radius: 10px; 
}
QLabel#userName { 
    color: #FFFFFF; 
    font-weight: 600; 
    font-size: 12px; 
}
QLabel#onlineStatus { 
    color: #6FE07A; 
    font-size: 11px; 
}
"""

TEXT_EXTENSIONS = {
    ".mq5", ".mqh", ".py", ".json", ".txt", ".md", ".csv",
    ".ini", ".cfg", ".yaml", ".yml", ".bat", ".ps1", ".log"
}


class AttachmentLineEdit(QLineEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setAcceptDrops(True)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste) and self.owner._clipboard_has_image():
            self.owner._attach_clipboard_image()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.owner._attach_paths(paths, "drop")
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

class GoldenAIStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Golden AI Studio V2.1.0")
        self.resize(1500, 900)
        self.setMinimumSize(1100, 700)

        icon_path = APP_ROOT / "assets" / "golden_ai.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.engine_process = None
        self.engine_ready = False
        self.engine_waiting_input = False
        self.engine_buffer = ""
        self.engine_chat_buffer = ""
        self.engine_prompt_queue = []
        self.engine_start_ms = None
        self.engine_last_output_ms = None
        self.engine_diag_timer = QTimer(self)
        self.engine_diag_timer.setInterval(1500)
        self.engine_diag_timer.timeout.connect(self._engine_diagnostic_tick)
        self.last_user_prompt = ""
        self.open_files = {}
        self.selected_context_path = None
        self.context_source = "nenhum"
        self.current_conversation = []
        self.current_conversation_id = None
        self.history = []
        self.activity_service = ActivityService(APP_ROOT)
        self.activity_session_id = self.activity_service.new_session_id()
        self.activity_service.start_session(self.activity_session_id)
        self.attachment_service = AttachmentService(APP_ROOT)
        self.vision_service = VisionService(APP_ROOT)
        self.pending_attachments = []
        self.activity_view_active = False
        self.coding_service = CodingService(APP_ROOT)
        self.coding_project_service = CodingProjectService(APP_ROOT)
        self.project_tools = ProjectIntelligenceService(APP_ROOT)
        self.execution_service = ExecutionService(APP_ROOT)
        self.intent_router = IntentRouter()
        self.external_access_service = ExternalAccessService(APP_ROOT)
        self.permission_manager_v2 = PermissionManagerV2(APP_ROOT)
        self.pending_external_prompts = {}
        self.external_context_ready = set()
        self.external_access_chat_status = "IDLE"
        self.active_coding_task_id = None
        self.active_coding_project_task_id = None
        self.file_context_active = False
        self.last_context_path_used = None
        self.settings = QSettings("GoldenAI", "GoldenAIStudio")
        self.focus_mode = self.settings.value("layout/focus_mode", False, type=bool)
        self.last_module = self.settings.value("layout/last_module", "Chat")

        self._build_toolbar()
        self._build_central()
        self._build_docks()
        self._build_status()
        self._load_projects_root()
        self._load_history()
        self._install_layout_shortcuts()
        if self.focus_mode:
            self._set_focus_mode(True)

    def _build_toolbar(self):
        tb = QToolBar("Principal")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        title = QLabel("  GOLDEN AI  ")
        title.setObjectName("title")
        tb.addWidget(title)

        self.badge_mode = QLabel("SOMENTE LEITURA")
        self.badge_mode.setObjectName("badgeReadOnly")
        tb.addWidget(self.badge_mode)

        self.agent_indicator = QLabel("Especialista: Auto")
        self.agent_indicator.setObjectName("muted")
        tb.addWidget(self.agent_indicator)

        self.model_indicator = QLabel(f"Modelo local principal: {load_settings().model_profiles.get('EXPERT', 'nao configurado')}")
        self.model_indicator.setObjectName("muted")
        tb.addWidget(self.model_indicator)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.tools_button = QToolButton()
        self.tools_button.setText("Ferramentas")
        self.tools_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.tools_button)

        actions = [
            ("Analisar arquivo atual", self._analisar_arquivo_atual),
            ("Corrigir", self._corrigir_arquivo_atual),
            ("Rollback", self._rollback_arquivo_atual),
            ("Compilar", self._compilar_arquivo_atual),
            ("Testar", self._mostrar_mensagem_teste),
        ]
        for text, handler in actions:
            act = QAction(text, self)
            act.triggered.connect(handler)
            menu.addAction(act)

        menu.addSeparator()

        file_actions = [
            ("Comparar arquivos", self._comparar_placeholder),
        ]
        for text, handler in file_actions:
            act = QAction(text, self)
            act.triggered.connect(handler)
            menu.addAction(act)

        self.tools_button.setMenu(menu)
        tb.addWidget(self.tools_button)

    def _build_central(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(14)

        self.sidebar_minimized = self.settings.value("layout/sidebar_minimized", True, type=bool)
        self.left_panel = self._build_sidebar()
        root_layout.addWidget(self.left_panel)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        self.page_stack = QStackedWidget()
        self.chat_page = self._build_chat_page()
        self.page_stack.addWidget(self.chat_page)
        self.module_panel = self.page_stack
        main_layout.addWidget(self.page_stack, 1)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._tab_context_changed)
        self.tabs.hide()

        self.terminal_panel = QFrame()
        self.terminal_panel.setObjectName("terminalPanel")
        terminal_layout = QVBoxLayout(self.terminal_panel)
        terminal_layout.setContentsMargins(14, 12, 14, 14)
        terminal_layout.setSpacing(10)
        terminal_header = QHBoxLayout()
        ttitle = QLabel("Terminal ConPTY")
        ttitle.setObjectName("panelTitle")
        terminal_header.addWidget(ttitle, 1)
        self.btn_clear_terminal = QPushButton("Limpar")
        self.btn_clear_terminal.setObjectName("ghost")
        self.btn_clear_terminal.clicked.connect(lambda: self.terminal.clear())
        self.btn_terminal_max = QPushButton("Maximizar")
        self.btn_terminal_max.setObjectName("ghost")
        self.btn_terminal_max.clicked.connect(self._maximize_terminal_panel)
        self.btn_terminal_close = QPushButton("Fechar")
        self.btn_terminal_close.setObjectName("ghost")
        self.btn_terminal_close.clicked.connect(self._close_terminal_panel)
        terminal_header.addWidget(self.btn_clear_terminal)
        terminal_header.addWidget(self.btn_terminal_max)
        terminal_header.addWidget(self.btn_terminal_close)
        terminal_layout.addLayout(terminal_header)
        terminal_layout.addWidget(self.tabs)
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Consolas", 10))
        self.terminal.setMinimumHeight(170)
        terminal_layout.addWidget(self.terminal)
        self.terminal_panel.hide()
        main_layout.addWidget(self.terminal_panel)

        root_layout.addWidget(main, 1)
        self.setCentralWidget(root)
        self._build_module_docks()
        self._apply_sidebar_state()
        self._refresh_permission_button()
        self._open_module(self.last_module if self.last_module else "Chat")
        if self.settings.value("layout/terminal_open", False, type=bool):
            self._show_terminal_panel()

    def _build_module_docks(self):
        self.docks = {}
        specs = [
            ("Dashboard", "Dashboard", lambda: self._build_module_page("Dashboard")),
            ("Projetos", "Projetos", self._build_projects_page),
            ("Recentes", "Recentes", self._build_recent_page),
            ("Agentes", "Agentes", lambda: self._build_module_page("Agentes")),
            ("Monitoramento", "Monitoramento", lambda: self._build_module_page("Monitoramento")),
            ("Codigo", "Codigo", self._build_coding_panel),
            ("Quant", "Laboratorio Quant", lambda: self._build_module_page("Laboratorio Quant")),
            ("Market", "Market Analyzer", lambda: self._build_module_page("Market Analyzer")),
            ("Memoria", "Memoria Cientifica", lambda: self._build_module_page("Memoria Cientifica")),
            ("Media Study", "Media Study", lambda: self._build_module_page("Media Study")),
            ("Ferramentas", "Ferramentas", lambda: self._build_module_page("Ferramentas")),
            ("Perfil", "Atividade", self._build_activity_panel),
            ("Configuracoes", "Configuracoes", lambda: self._build_module_page("Configuracoes")),
        ]
        for key, title, builder in specs:
            content = builder()
            dock = self._make_dock(title, content)
            dock.setObjectName(f"dock_{key}")
            self.addDockWidget(Qt.RightDockWidgetArea, dock)
            dock.hide()
            self.docks[key] = dock
        self.projects_page = self.docks["Projetos"].widget()
        self.recent_page = self.docks["Recentes"].widget()
        self.coding_panel = self.docks["Codigo"].widget()
        self.quant_page = self.docks["Quant"].widget()
        self.market_page = self.docks["Market"].widget()
        self.memory_page = self.docks["Memoria"].widget()
        self.media_page = self.docks["Media Study"].widget()
        self.tools_page = self.docks["Ferramentas"].widget()
        self.activity_panel = self.docks["Perfil"].widget()
        self.settings_page = self.docks["Configuracoes"].widget()
        for key, dock in self.docks.items():
            dock.visibilityChanged.connect(
                lambda visible, k=key: self._on_dock_visibility(k, visible)
            )

    def _make_dock(self, title, content):
        dock = QDockWidget(str(title), self)
        dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        titlebar = QWidget()
        tb = QHBoxLayout(titlebar)
        tb.setContentsMargins(8, 4, 4, 4)
        tb.setSpacing(2)
        label = QLabel(str(title))
        label.setObjectName("panelTitle")
        tb.addWidget(label, 1)
        btn_min = QPushButton("\u2013")
        btn_min.setObjectName("dockBtn")
        btn_min.setToolTip("Minimizar")
        btn_min.setFixedSize(22, 22)
        btn_min.clicked.connect(lambda: dock.hide())
        btn_max = QPushButton("\u25A1")
        btn_max.setObjectName("dockBtn")
        btn_max.setToolTip("Maximizar / restaurar")
        btn_max.setFixedSize(22, 22)
        btn_max.clicked.connect(lambda: self._toggle_dock_float(dock))
        btn_close = QPushButton("\u2715")
        btn_close.setObjectName("dockBtn")
        btn_close.setToolTip("Fechar")
        btn_close.setFixedSize(22, 22)
        btn_close.clicked.connect(lambda: dock.hide())
        tb.addWidget(btn_min)
        tb.addWidget(btn_max)
        tb.addWidget(btn_close)
        dock.setTitleBarWidget(titlebar)
        dock.setWidget(content)
        return dock

    def _toggle_dock_float(self, dock):
        if dock.isFloating():
            dock.setFloating(False)
        else:
            dock.setFloating(True)
            dock.raise_()

    def _on_dock_visibility(self, key, visible):
        if hasattr(self, "module_buttons"):
            btn = self.module_buttons.get(key)
            if btn:
                btn.setObjectName("activeNav" if visible else "")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def _open_dock(self, key):
        dock = self.docks.get(key)
        if not dock:
            return
        dock.setFloating(False)
        dock.show()
        dock.raise_()
        self._mark_active_module(key)
        self.settings.setValue("layout/last_module", key)
        return dock

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.sidebar_brand = QLabel("GOLDEN AI")
        self.sidebar_brand.setObjectName("title")
        header.addWidget(self.sidebar_brand, 1)
        self.btn_sidebar_toggle = QPushButton("<")
        self.btn_sidebar_toggle.setObjectName("ghost")
        self.btn_sidebar_toggle.setFixedWidth(36)
        self.btn_sidebar_toggle.clicked.connect(self._toggle_sidebar)
        header.addWidget(self.btn_sidebar_toggle)
        layout.addLayout(header)

        self.btn_new_chat = QPushButton("+  Novo chat")
        self.btn_new_chat.clicked.connect(self._new_chat)
        layout.addWidget(self.btn_new_chat)

        self.module_buttons = {}
        items = [
            ("Chat", "\U0001F4AC", "Chat"),
            ("Dashboard", "\U0001F4CA", "Dashboard"),
            ("Projetos", "\U0001F4C1", "Projetos"),
            ("Agentes", "\U0001F465", "Agentes"),
            ("Monitoramento", "\U0001F493", "Monitoramento"),
            ("Quant", "\U0001F9EE", "Laboratorio Quant"),
            ("Market", "\U0001F4C8", "Market Analyzer"),
            ("Memoria", "\U0001F9E0", "Memoria Cientifica"),
            ("Media Study", "\U0001F3AC", "Media Study"),
            ("Ferramentas", "\U0001F527", "Ferramentas"),
            ("Perfil", "\U0001F4CB", "Atividade"),
            ("Configuracoes", "\u2699\uFE0F", "Configuracoes"),
        ]
        for module, icon, label in items:
            btn = QPushButton(label)
            btn.setToolTip(label)
            btn.setProperty("full_text", label)
            btn.setProperty("mini_text", icon)
            btn.clicked.connect(lambda checked=False, name=module: self._open_module(name))
            self.module_buttons[module] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

        user_box = QFrame()
        user_box.setObjectName("userBox")
        self.user_box = user_box
        user_layout = QHBoxLayout(user_box)
        user_layout.setContentsMargins(8, 8, 8, 8)
        user_layout.setSpacing(8)
        self.avatar_label = QLabel("\U0001F464")
        self.avatar_label.setObjectName("avatar")
        self.avatar_label.setStyleSheet(
            "font-size:20px; background:#FFD700; border-radius:16px; color:#161616;"
        )
        self.avatar_label.setFixedSize(32, 32)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        user_layout.addWidget(self.avatar_label)
        user_text = QVBoxLayout()
        user_text.setSpacing(0)
        self.user_name_label = QLabel(self._current_user_name())
        self.user_name_label.setObjectName("userName")
        self.user_status_label = QLabel("\u25CF  online")
        self.user_status_label.setObjectName("onlineStatus")
        user_text.addWidget(self.user_name_label)
        user_text.addWidget(self.user_status_label)
        user_layout.addLayout(user_text, 1)
        layout.addWidget(user_box)

        self.sidebar_footer = QLabel("V2.1.0")
        self.sidebar_footer.setObjectName("muted")
        layout.addWidget(self.sidebar_footer)
        return sidebar

    def _current_user_name(self):
        try:
            return os.environ.get("USERNAME", "usuario")
        except Exception:
            return "usuario"

    def _build_chat_page(self):
        frame = QFrame()
        frame.setObjectName("chatPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Conversa com Golden AI")
        title.setObjectName("panelTitle")
        subtitle = QLabel("Chat principal")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.btn_recent_panel = QPushButton("Recentes")
        self.btn_recent_panel.setObjectName("ghost")
        self.btn_recent_panel.clicked.connect(lambda: self._open_module("Recentes"))
        self.btn_chat_terminal = QPushButton("Terminal")
        self.btn_chat_terminal.setObjectName("ghost")
        self.btn_chat_terminal.clicked.connect(self._show_terminal_panel)
        self.btn_chat_max = QPushButton("Foco")
        self.btn_chat_max.setObjectName("ghost")
        self.btn_chat_max.clicked.connect(self._toggle_focus_mode)
        header.addWidget(self.btn_recent_panel)
        header.addWidget(self.btn_chat_terminal)
        header.addWidget(self.btn_chat_max)
        layout.addLayout(header)

        self.chat_output = QTextEdit()
        self.chat_output.setReadOnly(True)
        self.chat_output.setAcceptRichText(True)
        self.chat_output.setFrameShape(QFrame.NoFrame)
        self.chat_output.setMinimumHeight(420)
        self.chat_output.setHtml(self._empty_chat_html())
        layout.addWidget(self.chat_output, 1)

        self.execution_feed = QTextEdit()
        self.execution_feed.setReadOnly(True)
        self.execution_feed.setMaximumHeight(130)
        self.execution_feed.setHtml(self._execution_feed_html(collapsed=True))
        self.execution_feed_collapsed = True
        self.execution_feed.hide()
        layout.addWidget(self.execution_feed)

        self.chat_status = QFrame()
        self.chat_status.setObjectName("composer")
        status_layout = QHBoxLayout(self.chat_status)
        status_layout.setContentsMargins(14, 8, 14, 8)
        status_layout.setSpacing(10)
        self.chat_status_label = QLabel("")
        self.chat_status_label.setObjectName("muted")
        self.chat_status_label.setStyleSheet("color:#FFD700; font-weight:600; font-size:11px;")
        status_layout.addWidget(self.chat_status_label)
        status_layout.addStretch(1)
        self.chat_status.hide()
        layout.addWidget(self.chat_status)

        self.composer = QFrame()
        self.composer.setObjectName("composer")
        composer_layout = QVBoxLayout(self.composer)
        composer_layout.setContentsMargins(12, 10, 12, 10)
        composer_layout.setSpacing(8)
        top = QHBoxLayout()
        self.context_chip = QPushButton("Escolher projeto ou arquivo")
        self.context_chip.setObjectName("ghost")
        self.context_chip.clicked.connect(self._choose_context_file)
        top.addWidget(self.context_chip, 1)
        self.permission_button = QPushButton("")
        self.permission_button.setObjectName("ghost")
        self.permission_button.clicked.connect(self._open_permission_menu)
        top.addWidget(self.permission_button)
        self.approval_button = QPushButton("Aprovacoes")
        self.approval_button.setObjectName("ghost")
        self.approval_button.clicked.connect(self._show_latest_approval_request)
        top.addWidget(self.approval_button)
        self.feed_button = QPushButton("Execucao")
        self.feed_button.setObjectName("ghost")
        self.feed_button.clicked.connect(self._toggle_execution_feed)
        top.addWidget(self.feed_button)
        hint = QLabel("Enter para enviar")
        hint.setObjectName("muted")
        top.addWidget(hint)
        composer_layout.addLayout(top)
        self.attachments_preview = QFrame()
        self.attachments_preview.setObjectName("card")
        self.attachments_preview_layout = QHBoxLayout(self.attachments_preview)
        self.attachments_preview_layout.setContentsMargins(8, 6, 8, 6)
        self.attachments_preview_layout.setSpacing(8)
        self.attachments_preview.hide()
        composer_layout.addWidget(self.attachments_preview)
        row = QHBoxLayout()
        self.btn_attach = QPushButton("+")
        self.btn_attach.setToolTip("Anexar arquivos")
        self.btn_attach.clicked.connect(self._choose_attachments)
        self.chat_input = AttachmentLineEdit(self)
        self.chat_input.setPlaceholderText("Digite sua mensagem...")
        self.chat_input.returnPressed.connect(self._send_chat)
        self.btn_send = QPushButton("Enviar")
        self.btn_send.setObjectName("primary")
        self.btn_send.clicked.connect(self._send_chat)
        row.addWidget(self.btn_attach)
        row.addWidget(self.chat_input, 1)
        row.addWidget(self.btn_send)
        composer_layout.addLayout(row)
        layout.addWidget(self.composer)

        self.model_footer = QLabel("")
        self.model_footer.setObjectName("muted")
        self.model_footer.setStyleSheet("color:#9AA4B2; font-size:12px; padding:6px 4px 2px 4px;")
        self.model_footer.setWordWrap(True)
        self.model_footer.setMinimumHeight(20)
        layout.addWidget(self.model_footer)
        self._refresh_model_footer()
        return frame

    def _model_label(self, model):
        short = str(model or "").replace("opencode/", "").replace("-free", "").strip()
        return short or model or "nao configurado"

    def _refresh_model_footer(self):
        if not hasattr(self, "model_footer"):
            return
        settings = load_settings()
        coder = self._model_label(settings.model_profiles.get("CODER", ""))
        chain = settings.opencode_models
        chain_text = " -> ".join(self._model_label(m) for m in chain) if chain else "sem cadeia"
        active = getattr(self, "active_model_name", "")
        if active:
            self.model_footer.setText(
                f"Modelo ativo: <span style='color:#FFD700; font-weight:700;'>{self._model_label(active)}</span>"
                f"  |  Local: {coder}  |  Cadeia OpenCode: {chain_text}"
            )
        else:
            self.model_footer.setText(f"Modelo local: {coder}  |  Cadeia OpenCode: {chain_text}")

    def _set_active_model(self, model):
        model = str(model or "").strip()
        if not model:
            return
        self.active_model_name = model
        self._refresh_model_footer()

    def _set_chat_status(self, text):
        if not hasattr(self, "chat_status"):
            return
        if text:
            self.chat_status_label.setText(text)
            self.chat_status.show()
        else:
            self.chat_status.hide()

    def _build_projects_page(self):
        frame = QFrame()
        frame.setObjectName("modulePanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Projetos")
        title.setObjectName("panelTitle")
        header.addWidget(title, 1)
        choose = QPushButton("Escolher arquivo")
        choose.setObjectName("primary")
        choose.clicked.connect(self._choose_context_file)
        header.addWidget(choose)
        layout.addLayout(header)

        self.fs_model = QFileSystemModel()
        self.fs_model.setReadOnly(True)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.clicked.connect(self._select_tree_item)
        self.tree.doubleClicked.connect(self._open_tree_item)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        for c in (1, 2, 3):
            self.tree.setColumnHidden(c, True)
        layout.addWidget(self.tree, 1)
        self.project_context_label = QLabel("Arquivo em contexto: nenhum")
        self.project_context_label.setObjectName("pill")
        layout.addWidget(self.project_context_label)
        return frame

    def _build_recent_page(self):
        frame = QFrame()
        frame.setObjectName("modulePanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Recentes")
        title.setObjectName("panelTitle")
        header.addWidget(title, 1)
        close_btn = QPushButton("Voltar ao chat")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(self._show_chat_mode)
        header.addWidget(close_btn)
        layout.addLayout(header)
        if not hasattr(self, "recent_list"):
            self.recent_list = QListWidget()
            self.recent_list.itemClicked.connect(self._open_recent_conversation)
        layout.addWidget(self.recent_list, 1)
        hint = QLabel("Selecione uma conversa para restaurar pergunta e resposta.")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        return frame

    def _build_module_page(self, title):
        frame = QFrame()
        frame.setObjectName("modulePanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("panelTitle")
        header.addWidget(label, 1)
        close_btn = QPushButton("Voltar ao chat")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(self._show_chat_mode)
        header.addWidget(close_btn)
        layout.addLayout(header)
        body = QTextEdit()
        body.setReadOnly(True)
        body.setProperty("module_body", True)
        layout.addWidget(body, 1)
        frame.body = body
        return frame

    def _legacy_build_central_disabled(self):
        root = QSplitter(Qt.Horizontal)
        self.root_splitter = root

        left = QWidget()
        self.left_panel = left
        left.setMaximumWidth(310)
        left.setMinimumWidth(225)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)

        self.btn_new_chat = QPushButton("＋  Novo chat")
        self.btn_new_chat.clicked.connect(self._new_chat)
        ll.addWidget(self.btn_new_chat)

        self.btn_focus = QPushButton("Modo foco")
        self.btn_focus.clicked.connect(self._toggle_focus_mode)
        ll.addWidget(self.btn_focus)

        self.btn_activity = QPushButton("Perfil / Atividade")
        self.btn_activity.clicked.connect(self._show_activity_panel)
        ll.addWidget(self.btn_activity)

        conv = QLabel("CONVERSAS"); conv.setObjectName("muted"); ll.addWidget(conv)

        p = QLabel("PROJETOS"); p.setObjectName("muted"); ll.addWidget(p)

        self.fs_model = QFileSystemModel()
        self.fs_model.setReadOnly(True)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.clicked.connect(self._select_tree_item)
        self.tree.doubleClicked.connect(self._open_tree_item)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(14)
        self.tree.setMaximumHeight(300)
        for c in (1, 2, 3):
            self.tree.setColumnHidden(c, True)
        ll.addWidget(self.tree)

        r = QLabel("RECENTES"); r.setObjectName("muted"); ll.addWidget(r)
        self.recent_list = QListWidget()
        self.recent_list.itemClicked.connect(self._open_recent_conversation)
        ll.addWidget(self.recent_list, 1)

        modules = QLabel("MODULOS"); modules.setObjectName("muted"); ll.addWidget(modules)
        self.module_buttons = {}
        for name in ("Chat", "Codigo", "Quant", "Market", "Memoria", "Media Study", "Ferramentas", "Terminal"):
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked=False, module=name: self._open_module(module))
            self.module_buttons[name] = btn
            ll.addWidget(btn)

        footer = QLabel("Golden AI Studio • V2.1.0"); footer.setObjectName("muted"); ll.addWidget(footer)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(50, 24, 50, 22)
        ml.setSpacing(10)

        self.hero = QLabel("O que devemos criar?")
        self.hero.setObjectName("hero")
        self.hero.setAlignment(Qt.AlignCenter)
        ml.addStretch(1)
        ml.addWidget(self.hero)

        self.hero_sub = QLabel("Converse naturalmente com a Golden AI. Escolha um projeto quando quiser dar contexto.")
        self.hero_sub.setObjectName("muted")
        self.hero_sub.setAlignment(Qt.AlignCenter)
        self.hero_sub.setWordWrap(True)
        ml.addWidget(self.hero_sub)

        self.chat_output = QTextEdit()
        self.chat_output.setReadOnly(True)
        self.chat_output.setMinimumHeight(320)
        self.chat_output.setFrameShape(QFrame.NoFrame)
        self.chat_output.hide()
        ml.addWidget(self.chat_output, 8)

        self.activity_panel = self._build_activity_panel()
        self.activity_panel.hide()
        ml.addWidget(self.activity_panel, 8)

        self.coding_panel = self._build_coding_panel()
        self.coding_panel.hide()
        ml.addWidget(self.coding_panel, 8)

        self.module_panel = self._build_module_panel()
        self.module_panel.hide()
        ml.addWidget(self.module_panel, 8)
        ml.addStretch(1)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._tab_context_changed)
        welcome = QTextEdit()
        welcome.setReadOnly(True)
        welcome.setHtml("<h2>Golden AI Studio V2.1.0</h2><p>Base técnica preservada da V1.15.0.</p>")
        self.tabs.addTab(welcome, "Início")
        self.tabs.hide()

        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Consolas", 10))
        self.terminal.hide()
        ml.addWidget(self.tabs)
        ml.addWidget(self.terminal)

        self.composer = QFrame()
        self.composer.setMaximumWidth(980)
        cl = QVBoxLayout(self.composer)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(7)

        self.context_chip = QPushButton("📁  Escolher projeto ou arquivo")
        self.context_chip.clicked.connect(self._choose_context_file)
        cl.addWidget(self.context_chip)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Peça qualquer coisa")
        self.chat_input.setMinimumHeight(50)
        self.chat_input.returnPressed.connect(self._send_chat)
        self.btn_send = QPushButton("Enviar")
        self.btn_send.setObjectName("primary")
        self.btn_send.clicked.connect(self._send_chat)
        row.addWidget(self.chat_input, 1)
        row.addWidget(self.btn_send)
        cl.addLayout(row)

        tools = QHBoxLayout()
        self.btn_details = QPushButton("Código / terminal")
        self.btn_details.clicked.connect(self._toggle_technical_view)
        tools.addWidget(self.btn_details)
        for label in ("Chat", "Quant", "Market", "Media", "Atividade", "Terminal"):
            btn = QPushButton(label)
            target = "Media Study" if label == "Media" else ("Perfil" if label == "Atividade" else label)
            btn.clicked.connect(lambda checked=False, module=target: self._open_module(module))
            tools.addWidget(btn)
        tools.addStretch()
        hint = QLabel("Enter para enviar"); hint.setObjectName("muted"); tools.addWidget(hint)
        cl.addLayout(tools)

        cr = QHBoxLayout()
        cr.addStretch(1); cr.addWidget(self.composer, 1); cr.addStretch(1)
        ml.addLayout(cr)

        root.addWidget(left)
        root.addWidget(main)
        root.setSizes([255, 1245])
        self.setCentralWidget(root)
        splitter_state = self.settings.value("layout/root_splitter")
        if splitter_state:
            root.restoreState(splitter_state)
        if self.settings.value("layout/terminal_open", False, type=bool):
            self.terminal.show()

    def _build_docks(self):
        # Mantém os objetos de contexto usados pelo motor, sem poluir a interface principal.
        dock_context = QDockWidget("Contexto do Projeto", self)
        self.context_list = QListWidget()
        for txt in ("Motor: golden_ai.py","Modo: somente leitura","MT5 real: protegido","Autocorreção: experimental / congelada","Chat bidirecional: disponível","I/O do motor: unbuffered (-u)","Transporte do motor: ConPTY / pywinpty","Arquivo em contexto: nenhum"):
            self.context_list.addItem(txt)
        dock_context.setWidget(self.context_list); self.addDockWidget(Qt.RightDockWidgetArea, dock_context); dock_context.hide()
        self.dock_context = dock_context
        self.recent_list = QListWidget()
        self.recent_list.itemClicked.connect(self._open_recent_conversation)

    def _build_activity_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        self.activity_title = QLabel("Golden AI")
        self.activity_title.setObjectName("hero")
        title_box.addWidget(self.activity_title)
        subtitle = QLabel("Atividade do sistema")
        subtitle.setObjectName("muted")
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)
        self.activity_refresh = QPushButton("Atualizar")
        self.activity_refresh.clicked.connect(self._render_activity_panel)
        top.addWidget(self.activity_refresh)
        layout.addLayout(top)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("Periodo"))
        for label in ("Diario", "Semanal", "Mensal", "Acumulado"):
            btn = QPushButton(label)
            btn.setEnabled(label == "Acumulado")
            period_row.addWidget(btn)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        self.activity_cards = QGridLayout()
        self.activity_cards.setSpacing(10)
        layout.addLayout(self.activity_cards)

        self.tokens_box = self._activity_block("Tokens")
        layout.addWidget(self.tokens_box)

        self.heatmap_box = self._activity_block("Calendario de atividade")
        layout.addWidget(self.heatmap_box)

        lower = QHBoxLayout()
        self.tools_box = self._activity_block("Ferramentas mais usadas")
        self.security_box = self._activity_block("Seguranca")
        lower.addWidget(self.tools_box, 1)
        lower.addWidget(self.security_box, 1)
        layout.addLayout(lower)

        lower2 = QHBoxLayout()
        self.projects_box = self._activity_block("Projetos mais usados")
        self.categories_box = self._activity_block("Categorias")
        lower2.addWidget(self.projects_box, 1)
        lower2.addWidget(self.categories_box, 1)
        layout.addLayout(lower2)

        self.models_box = self._activity_block("Modelos")
        layout.addWidget(self.models_box)

        scroll.setWidget(body)
        return scroll

    def _activity_block(self, title):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        label = QLabel(title)
        label.setObjectName("panelTitle")
        layout.addWidget(label)
        return frame

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)

    def _replace_block_lines(self, frame, lines):
        layout = frame.layout()
        while layout.count() > 1:
            item = layout.takeAt(1)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not lines:
            empty = QLabel("Ainda sem dados")
            empty.setObjectName("muted")
            layout.addWidget(empty)
            return
        for line in lines:
            label = QLabel(str(line))
            label.setWordWrap(True)
            label.setStyleSheet("border:none; background:transparent; color:#D9DEE7;")
            layout.addWidget(label)

    def _metric_text(self, value):
        if value is None:
            return "Ainda sem dados"
        try:
            if int(value) == 0:
                return "Ainda sem dados"
        except Exception:
            pass
        return str(value)

    def _add_metric_card(self, row, column, title, value):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        name = QLabel(title)
        value_label = QLabel(self._metric_text(value))
        name.setStyleSheet("border:none; background:transparent; color:#9AA4B2;")
        value_label.setStyleSheet("font-size:20px; font-weight:700; border:none; background:transparent; color:#F2C94C;")
        layout.addWidget(name)
        layout.addWidget(value_label)
        self.activity_cards.addWidget(card, row, column)

    def _format_seconds(self, seconds):
        try:
            seconds = int(seconds)
        except Exception:
            return "Ainda sem dados"
        hours, rest = divmod(seconds, 3600)
        minutes, _ = divmod(rest, 60)
        if hours:
            return f"{hours}h {minutes}min"
        return f"{minutes}min"

    def _render_activity_panel(self):
        data = self.activity_service.dashboard(current_model="orcarouter/Qwen3.8-27B-Uncensored:iq4_xs")
        summary = data.get("summary", {})
        self._clear_layout(self.activity_cards)
        cards = [
            ("Total de chats", summary.get("total_chats")),
            ("Total de mensagens", summary.get("total_messages")),
            ("Mensagens do usuario", summary.get("user_messages")),
            ("Respostas da Golden AI", summary.get("assistant_messages")),
            ("Total de sessoes", summary.get("total_sessions")),
            ("Dias ativos", summary.get("active_days")),
            ("Sequencia atual", summary.get("current_streak_days")),
            ("Maior sequencia", summary.get("longest_streak_days")),
        ]
        for index, (title, value) in enumerate(cards):
            self._add_metric_card(index // 4, index % 4, title, value)

        tokens = data.get("tokens", {})
        token_lines = [tokens.get("message", "Tokens exatos: indisponiveis para o modelo atual")]
        if tokens.get("records"):
            token_lines.append(f"Registros reais: {tokens.get('records')}")
        self._replace_block_lines(self.tokens_box, token_lines)

        self._render_heatmap(data.get("heatmap", []))

        tool_lines = [
            f"{row.get('tool')}: {row.get('calls')} chamadas | permitidas {row.get('allowed')} | bloqueadas {row.get('denied')} | falhas {row.get('failed')}"
            for row in data.get("tools", [])
        ]
        self._replace_block_lines(self.tools_box, tool_lines)

        security = data.get("security", {})
        security_lines = [
            f"Acoes permitidas: {security.get('allowed', 0)}",
            f"Acoes bloqueadas: {security.get('denied', 0)}",
            f"Acoes falhas: {security.get('failed', 0)}",
            f"WRITE bloqueadas: {security.get('write_denied', 0)}",
            f"CRITICAL bloqueadas: {security.get('critical_denied', 0)}",
        ]
        self._replace_block_lines(self.security_box, security_lines)

        project_lines = [
            f"{row.get('project_name')}: {row.get('conversations')} conversas | {row.get('messages')} mensagens | {row.get('tool_events')} eventos de ferramenta"
            for row in data.get("projects", [])
        ]
        self._replace_block_lines(self.projects_box, project_lines)

        category_lines = []
        for row in data.get("categories", []):
            if row.get("count") is None:
                category_lines.append(f"{row.get('name')}: {row.get('status')}")
            else:
                category_lines.append(f"{row.get('name')}: {row.get('count')}")
        self._replace_block_lines(self.categories_box, category_lines)

        session_time = data.get("session_time", {})
        model_lines = [
            f"{row.get('model')}: {row.get('messages')} mensagens"
            for row in data.get("models", [])
        ]
        if session_time.get("known"):
            model_lines.extend([
                f"Tempo total aproximado: {self._format_seconds(session_time.get('total_seconds'))}",
                f"Media por sessao: {self._format_seconds(session_time.get('average_seconds'))}",
                f"Sessao mais longa: {self._format_seconds(session_time.get('longest_seconds'))}",
            ])
        else:
            model_lines.append(session_time.get("message", "Ainda sem sessoes finalizadas"))
        if data.get("last_error"):
            model_lines.append(data.get("last_error"))
        self._replace_block_lines(self.models_box, model_lines)

    def _render_heatmap(self, days):
        layout = self.heatmap_box.layout()
        while layout.count() > 1:
            item = layout.takeAt(1)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        grid_widget = QWidget()
        grid_widget.setStyleSheet("border:none; background:transparent;")
        grid = QGridLayout(grid_widget)
        grid.setSpacing(3)
        colors = ["#151B23", "#25351F", "#476B2B", "#78A63C", "#D4AF37"]
        for index, day in enumerate(days[-140:]):
            square = QLabel("")
            square.setFixedSize(12, 12)
            square.setStyleSheet(
                f"background:{colors[int(day.get('intensity', 0))]}; border:1px solid #222A34; border-radius:2px;"
            )
            square.setToolTip(
                f"{day.get('day')}\n"
                f"{day.get('messages')} mensagens\n"
                f"{day.get('tools')} ferramentas\n"
                f"{day.get('projects')} projetos"
            )
            grid.addWidget(square, index % 7, index // 7)
        layout.addWidget(grid_widget)

    def _show_activity_panel(self):
        self.activity_view_active = True
        self._persist_current_conversation()
        self._open_dock("Perfil")
        self._render_activity_panel()

    def _build_coding_panel(self):
        frame = QFrame()
        frame.setObjectName("modulePanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Alteracao proposta")
        title.setObjectName("hero")
        header.addWidget(title, 1)
        self.btn_coding_approve = QPushButton("Aprovar")
        self.btn_coding_reject = QPushButton("Rejeitar")
        self.btn_coding_tests = QPushButton("Ver testes")
        self.btn_coding_checkpoints = QPushButton("Ver checkpoints")
        self.btn_coding_approve.clicked.connect(self._approve_coding_task)
        self.btn_coding_reject.clicked.connect(self._reject_coding_task)
        self.btn_coding_tests.clicked.connect(self._show_coding_tests)
        self.btn_coding_checkpoints.clicked.connect(self._show_coding_checkpoints)
        header.addWidget(self.btn_coding_approve)
        header.addWidget(self.btn_coding_reject)
        header.addWidget(self.btn_coding_tests)
        header.addWidget(self.btn_coding_checkpoints)
        layout.addLayout(header)

        self.coding_status = QLabel("Aguardando proposta")
        self.coding_status.setObjectName("muted")
        self.coding_status.setWordWrap(True)
        layout.addWidget(self.coding_status)

        split = QSplitter(Qt.Horizontal)
        self.coding_file_list = QListWidget()
        self.coding_file_list.setMinimumWidth(240)
        self.coding_file_list.currentTextChanged.connect(self._show_selected_project_diff)
        split.addWidget(self.coding_file_list)
        self.coding_details = QTextEdit()
        self.coding_details.setReadOnly(True)
        self.coding_details.setMinimumHeight(360)
        split.addWidget(self.coding_details)
        split.setSizes([280, 820])
        layout.addWidget(split, 1)
        return frame

    def _build_module_panel(self):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 10)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.module_title = QLabel("Modulo")
        self.module_title.setObjectName("hero")
        header.addWidget(self.module_title, 1)
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self._show_chat_mode)
        header.addWidget(close_btn)
        layout.addLayout(header)
        self.module_body = QTextEdit()
        self.module_body.setReadOnly(True)
        self.module_body.setMinimumHeight(360)
        layout.addWidget(self.module_body, 1)
        return frame

    def _open_module(self, module):
        if module == "Terminal":
            self._show_terminal_panel()
            return
        if module == "Chat":
            self._show_chat_mode()
            return
        if module == "Recentes":
            self._show_recent_history()
            return
        if module in ("Quant", "Market", "Memoria", "Media Study", "Ferramentas", "Configuracoes"):
            dock = self._open_dock(module)
            if dock and hasattr(dock.widget(), "body"):
                dock.widget().body.setHtml(self._module_html(module))
            return
        if module in self.docks:
            self._open_dock(module)
            return
        self._show_chat_mode()

    def _hide_main_panels(self):
        if hasattr(self, "page_stack") and hasattr(self, "chat_page"):
            self.page_stack.setCurrentWidget(self.chat_page)

    def _module_html(self, module):
        if module == "Quant":
            return self._quant_panel_html()
        if module == "Market":
            return self._market_panel_html()
        if module == "Memoria":
            return self._memory_panel_html()
        if module == "Media Study":
            return self._media_panel_html()
        if module == "Ferramentas":
            return self._tools_panel_html()
        if module == "Configuracoes":
            return self._settings_panel_html()
        return "<p>Modulo em desenvolvimento.</p>"

    def _tools_panel_html(self):
        tools = [
            "Editor de Codigo",
            "Terminal ConPTY",
            "Gerenciador de Arquivos",
            "Backups",
            "Auditoria",
            "Permissoes",
            "Calculadora",
            "Computer Tools",
        ]
        cards = "".join(
            "<td style='padding:10px; border:1px solid #2A323E; background:#111820;'>"
            f"<b>{name}</b><br><span style='color:#9AA4B2'>Conectado ao fluxo existente quando disponivel.</span></td>"
            for name in tools
        )
        return (
            "<h2>Ferramentas</h2>"
            "<p>Modo somente leitura ativo. Nenhuma ferramenta nova foi implementada nesta etapa.</p>"
            f"<table width='100%' cellspacing='10'><tr>{cards}</tr></table>"
        )

    def _settings_panel_html(self):
        items = ["Aparencia", "Modelo de IA", "Seguranca", "Notificacoes", "Conexoes", "Sobre"]
        rows = "".join(
            f"<li><b>{item}</b><br><span style='color:#9AA4B2'>Estrutura visual inicial; item funcional nao alterado.</span></li>"
            for item in items
        )
        return (
            "<h2>Configuracoes</h2>"
            "<p>Golden AI Studio V2.1.0. Base tecnica preservada.</p>"
            f"<ul>{rows}</ul>"
        )

    def _show_recent_history(self):
        self._refresh_recent_list()
        self._open_dock("Recentes")

    def _recent_history_html(self):
        if not self.history:
            return "<h2>Recentes</h2><p>Sem conversas recentes.</p>"
        rows = []
        for conv in reversed(self.history[-20:]):
            title = str(conv.get("title", "Conversa"))[:80]
            count = len(conv.get("messages", []))
            rows.append(f"<li><b>{title}</b><br><span style='color:#9AA4B2'>{count} mensagens</span></li>")
        return "<h2>Recentes</h2><p>Use a lista interna preservada para reabrir pelo painel de historico.</p><ul>" + "".join(rows) + "</ul>"

    def _empty_chat_html(self):
        return (
            "<div style='margin-top:120px; text-align:center; color:#BBBBBB;'>"
            "<h2 style='color:#FFFFFF;'>Golden AI</h2>"
            "<p>Conversa em foco. Escolha um arquivo somente quando precisar de contexto.</p>"
            "</div>"
        )

    def _mark_active_module(self, module):
        if not hasattr(self, "module_buttons"):
            return
        for name, btn in self.module_buttons.items():
            btn.setObjectName("activeNav" if name == module else "")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_sidebar(self):
        self.sidebar_minimized = not bool(getattr(self, "sidebar_minimized", False))
        self.settings.setValue("layout/sidebar_minimized", self.sidebar_minimized)
        self._apply_sidebar_state()

    def _apply_sidebar_state(self):
        if not hasattr(self, "left_panel"):
            return
        minimized = bool(getattr(self, "sidebar_minimized", False))
        width = 58 if minimized else 205
        self.left_panel.setMinimumWidth(width)
        self.left_panel.setMaximumWidth(width)
        self.btn_sidebar_toggle.setText(">" if minimized else "<")
        self.sidebar_brand.setText("G" if minimized else "GOLDEN AI")
        self.sidebar_footer.setVisible(not minimized)
        if hasattr(self, "user_box"):
            self.user_box.setVisible(not minimized)
        self.btn_new_chat.setText("+" if minimized else "+  Novo chat")
        for btn in self.module_buttons.values():
            btn.setText(btn.property("mini_text") if minimized else btn.property("full_text"))
            btn.setProperty("navMinimized", minimized)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.left_panel.setProperty("sidebarMinimized", minimized)
        self.left_panel.style().unpolish(self.left_panel)
        self.left_panel.style().polish(self.left_panel)

    def _show_terminal_panel(self):
        self.terminal_panel.show()
        self.tabs.setVisible(self.tabs.count() > 0)
        self.settings.setValue("layout/terminal_open", True)

    def _close_terminal_panel(self):
        self.terminal_panel.hide()
        self.settings.setValue("layout/terminal_open", False)

    def _maximize_terminal_panel(self):
        if self.terminal.minimumHeight() < 360:
            self.terminal.setMinimumHeight(420)
            self.btn_terminal_max.setText("Restaurar")
        else:
            self.terminal.setMinimumHeight(170)
            self.btn_terminal_max.setText("Maximizar")

    def _permission_mode_label(self, mode=None):
        mode = mode or self.execution_service.get_mode()
        labels = {
            PermissionMode.READ_ONLY: "Somente leitura",
            PermissionMode.ASK: "Solicitar aprovacao",
            PermissionMode.AUTO_SAFE: "Aprovar por mim",
            PermissionMode.FULL: "Acesso completo",
        }
        return labels.get(mode, str(mode))

    def _refresh_permission_button(self):
        if not hasattr(self, "permission_button"):
            return
        mode = self.execution_service.get_mode()
        self.permission_button.setText("Permissao: " + self._permission_mode_label(mode))
        descriptions = {
            PermissionMode.READ_ONLY: "Pode analisar, mas nao modificar arquivos.",
            PermissionMode.ASK: "Pede aprovacao antes de acoes protegidas.",
            PermissionMode.AUTO_SAFE: "Executa LOW automaticamente e pede aprovacao acima disso.",
            PermissionMode.FULL: "Usa o maximo das capacidades realmente habilitadas; CRITICAL segue bloqueado.",
        }
        self.permission_button.setToolTip(descriptions.get(mode, ""))

    def _open_permission_menu(self):
        menu = QMenu(self)
        modes = [
            (PermissionMode.READ_ONLY, "Somente leitura", "Nao alterar arquivos."),
            (PermissionMode.ASK, "Solicitar aprovacao", "Pedir aprovacao antes de acoes protegidas."),
            (PermissionMode.AUTO_SAFE, "Aprovar por mim", "Aprovar automaticamente apenas acoes LOW."),
            (PermissionMode.FULL, "Acesso completo", "Acesso ampliado somente ao que ja existe."),
        ]
        current = self.execution_service.get_mode()
        for mode, title, description in modes:
            action = QAction(("✓ " if mode == current else "") + title, self)
            action.setToolTip(description)
            action.triggered.connect(lambda checked=False, selected=mode: self._set_permission_mode(selected))
            menu.addAction(action)
        menu.exec(self.permission_button.mapToGlobal(self.permission_button.rect().bottomLeft()))

    def _set_permission_mode(self, mode):
        self.execution_service.set_mode(mode)
        self._refresh_permission_button()
        self._refresh_execution_feed()

    def _execution_feed_html(self, collapsed=False):
        events = self.execution_service.latest_events(limit=10)
        if not events:
            return "<b>Execucao</b><br><span style='color:#9AA4B2'>Sem eventos recentes.</span>"
        if collapsed:
            latest = events[0]
            return (
                "<b>Execucao</b><br>"
                f"<span style='color:#9AA4B2'>{latest.get('status')} - {latest.get('summary')}</span>"
            )
        rows = []
        for event in reversed(events):
            status = str(event.get("status", ""))
            marker = "✓" if status in {"COMPLETED", "PASSED", "ALLOWED"} else ("!" if status in {"FAILED", "BLOCKED"} else "•")
            rows.append(
                f"<div><b>{marker}</b> {event.get('category')} / {event.get('action')} - "
                f"{event.get('summary')}</div>"
            )
        return "<b>Execucao</b><br>" + "".join(rows)

    def _refresh_execution_feed(self):
        if not hasattr(self, "execution_feed"):
            return
        self.execution_feed.setHtml(self._execution_feed_html(self.execution_feed_collapsed))
        if self.execution_service.latest_events(limit=1):
            self.execution_feed.show()

    def _toggle_execution_feed(self):
        self.execution_feed_collapsed = not bool(getattr(self, "execution_feed_collapsed", True))
        self.execution_feed.setMaximumHeight(130 if self.execution_feed_collapsed else 260)
        self.execution_feed.setHtml(self._execution_feed_html(self.execution_feed_collapsed))
        self.execution_feed.show()

    def _show_latest_approval_request(self):
        requests = [req for req in self.execution_service.latest_requests(limit=20) if req.get("status") == "PENDING"]
        if not requests:
            QMessageBox.information(self, "Golden solicita aprovacao", "Nenhuma aprovacao pendente.")
            return
        req = requests[0]
        box = QMessageBox(self)
        box.setWindowTitle("GOLDEN AI SOLICITA ACESSO")
        if req.get("permission_level") == "READ_EXTERNAL":
            target = Path(req.get("target") or "")
            box.setText(
                "Arquivo:\n"
                f"{target.name}\n\n"
                "Caminho:\n"
                f"{target}\n\n"
                "Operacao:\n"
                "SOMENTE LEITURA\n\n"
                "Motivo:\n"
                f"{req.get('reason') or 'Analisar o arquivo selecionado e responder a pergunta atual.'}"
            )
        else:
            box.setText(
                "Acao:\n"
                f"{req.get('action')}\n\n"
                "Motivo:\n"
                f"{req.get('reason')}\n\n"
                "Arquivos/Alvo:\n"
                f"{req.get('target') or 'Nao informado'}\n\n"
                "Risco:\n"
                f"{req.get('risk_level')}"
            )
        once = box.addButton("Permitir uma vez", QMessageBox.AcceptRole)
        task = box.addButton("Permitir nesta tarefa", QMessageBox.ActionRole)
        deny = box.addButton("Negar", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == once:
            if req.get("permission_level") == "READ_EXTERNAL":
                self.external_access_service.grant_once(req.get("request_id"))
                self._continue_pending_external_prompt(req.get("request_id"))
            else:
                self.execution_service.grant_once(req.get("request_id"))
        elif clicked == task:
            if req.get("permission_level") == "READ_EXTERNAL":
                self.external_access_service.grant_for_task(req.get("request_id"))
                self._continue_pending_external_prompt(req.get("request_id"))
            else:
                self.execution_service.grant_for_task(req.get("request_id"))
        elif clicked == deny:
            self.execution_service.deny(req.get("request_id"))
            if req.get("permission_level") == "READ_EXTERNAL":
                self.pending_external_prompts.pop(req.get("request_id"), None)
                self._append_assistant_message("Acesso externo negado. Nao li o arquivo selecionado.")
        self._refresh_execution_feed()

    def _db_rows(self, sql, params=()):
        db = APP_ROOT / "data" / "golden_ai.db"
        if not db.exists():
            return []
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in con.execute(sql, params).fetchall()]
        except Exception:
            return []
        finally:
            con.close()

    def _quant_panel_html(self):
        rows = self._db_rows("SELECT experiment_id, metrics_json, status, created_at FROM quant_backtests ORDER BY created_at DESC LIMIT 5")
        if not rows:
            return "<h2>Quant</h2><p>Sem experimentos.</p>"
        first = rows[0]
        try:
            metrics = json.loads(first.get("metrics_json") or "{}")
        except Exception:
            metrics = {}
        cards = [
            ("Experimentos", len(rows)),
            ("Trades", metrics.get("total_trades", "Sem dados")),
            ("Net Profit", metrics.get("net_profit", "Sem dados")),
            ("Win Rate", metrics.get("win_rate", "Sem dados")),
            ("Profit Factor", metrics.get("profit_factor", "Sem dados")),
            ("Drawdown", metrics.get("max_drawdown_abs", "Sem dados")),
        ]
        html = "<h2>Quant</h2><table width='100%'><tr>" + "".join(f"<td><b>{k}</b><br>{v}</td>" for k, v in cards) + "</tr></table>"
        html += "<h3>Experimentos recentes</h3><ul>" + "".join(f"<li>{r.get('experiment_id')} - {r.get('status')}</li>" for r in rows) + "</ul>"
        return html

    def _market_panel_html(self):
        rows = self._db_rows("SELECT analysis_id, symbol, created_at FROM market_analyses ORDER BY created_at DESC LIMIT 5")
        if not rows:
            return "<h2>Market</h2><p>Sem analises Market.</p>"
        return "<h2>Market</h2><p>Regime, estrutura, multi-timeframe, observacoes e hipoteses permanecem como evidencia OBSERVED/INFERRED/HYPOTHESIS.</p><ul>" + "".join(f"<li>{r.get('analysis_id')} - {r.get('symbol')}</li>" for r in rows) + "</ul>"

    def _memory_panel_html(self):
        rows = self._db_rows("SELECT topic, evidence_level, source_type, created_at FROM knowledge_items ORDER BY created_at DESC LIMIT 20")
        if not rows:
            return "<h2>Memoria Cientifica</h2><p>Sem conhecimentos persistidos.</p>"
        return "<h2>Memoria Cientifica</h2><ul>" + "".join(f"<li><b>{r.get('evidence_level')}</b> | {r.get('source_type')} | {r.get('topic')}</li>" for r in rows) + "</ul>"

    def _media_panel_html(self):
        rows = self._db_rows("SELECT source_id, title, source_type, language, created_at FROM media_sources ORDER BY created_at DESC LIMIT 20")
        if not rows:
            return "<h2>Media Study</h2><p>Sem fontes estudadas.</p>"
        html = "<h2>Media Study</h2><ul>"
        for row in rows:
            counts = self._db_rows("SELECT COUNT(*) AS n FROM media_segments WHERE source_id = ?", (row.get("source_id"),))
            claims = self._db_rows("SELECT COUNT(*) AS n FROM media_claims WHERE source_id = ?", (row.get("source_id"),))
            html += f"<li>{row.get('title')} | {row.get('source_type')} | segmentos={counts[0].get('n') if counts else 0} | claims={claims[0].get('n') if claims else 0}</li>"
        return html + "</ul>"

    def _toggle_focus_mode(self):
        self._set_focus_mode(not self.focus_mode)

    def _set_focus_mode(self, enabled):
        self.focus_mode = bool(enabled)
        if hasattr(self, "left_panel"):
            self.left_panel.setVisible(not self.focus_mode)
        self.btn_focus.setText("Sair do foco" if self.focus_mode else "Modo foco")
        self.settings.setValue("layout/focus_mode", self.focus_mode)

    def _set_focus_mode(self, enabled):
        self.focus_mode = bool(enabled)
        if hasattr(self, "left_panel"):
            self.left_panel.setVisible(not self.focus_mode)
        if hasattr(self, "terminal_panel") and self.focus_mode:
            self.terminal_panel.hide()
        if hasattr(self, "btn_focus"):
            self.btn_focus.setText("Sair do foco" if self.focus_mode else "Modo foco")
        if hasattr(self, "btn_chat_max"):
            self.btn_chat_max.setText("Sair do foco" if self.focus_mode else "Foco")
        self.settings.setValue("layout/focus_mode", self.focus_mode)
        if hasattr(self, "sidebar_minimized"):
            self._apply_sidebar_state()

    def _install_layout_shortcuts(self):
        shortcuts = {
            "Ctrl+N": self._new_chat,
            "Ctrl+1": lambda: self._open_module("Chat"),
            "Ctrl+2": lambda: self._open_module("Codigo"),
            "Ctrl+3": lambda: self._open_module("Quant"),
            "Ctrl+4": lambda: self._open_module("Market"),
            "Ctrl+5": lambda: self._open_module("Media Study"),
            "Ctrl+`": lambda: self._open_module("Terminal"),
            "F11": self._toggle_focus_mode,
        }
        for sequence, handler in shortcuts.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(handler)
            self.addAction(action)

    def _is_coding_change_request(self, prompt):
        texto = str(prompt or "").lower()
        if re.search(r"\bn.{0,3}o\s+(?:altere|modifique|mexa)\b", texto):
            return False
        if any(term in texto for term in ("nao altere", "não altere", "nao modifique", "não modifique", "sem alterar", "somente leitura")):
            return False
        if any(term in texto for term in ("o que e", "o que é", "explique", "qual a diferenca", "qual a diferença")):
            return False
        verbs = (
            "altere", "alterar", "modifique", "modificar", "corrija", "corrigir",
            "implemente", "implementar", "refatore", "refatorar", "prepare uma correcao",
            "prepare uma correção", "melhore esse modulo", "melhore este modulo",
        )
        return any(verb in texto for verb in verbs)

    def _is_coding_change_request(self, prompt):
        return self._classify_coding_intent(prompt).execution_requested

    def _classify_coding_intent(self, prompt):
        active = bool(getattr(self, "active_coding_task_id", None) or getattr(self, "active_coding_project_task_id", None))
        return self.intent_router.classify_coding_change(prompt, active_coding_task=active)

    def _is_project_coding_request(self, prompt):
        text = self._normalized_prompt(prompt)
        if any(term in text for term in ("nao altere", "sem alterar", "somente revisao", "somente leitura")):
            return False
        project_terms = ("projeto", "testes", "falhando", "falhas", "multi-arquivo", "todas as correcoes")
        change_terms = ("prepare", "corrija", "correcoes", "descubra por que", "teste novamente")
        return any(term in text for term in project_terms) and any(term in text for term in change_terms)

    def _is_project_tool_request(self, prompt):
        text = self._normalized_prompt(prompt)
        if any(term in text for term in ("quanto e", "quanto é", "o que e uma funcao", "o que é uma funcao", "vamos conversar")):
            return False
        terms = (
            "liste os arquivos", "procure", "onde", "referencias", "referencias de",
            "referencias do", "leia as linhas", "linhas", "quem depende", "dependem de",
            "importa", "importam", "cadeia entre", "arquivos envolvidos", "grafo",
        )
        project_hint = ("arquivo", "projeto", ".py", ".mq5", "funcao", "classe", "modulo", "pricing", "inventory")
        has_symbol_shape = bool(re.search(r"\b[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]*\b", prompt))
        return any(term in text for term in terms) and (any(hint in text for hint in project_hint) or has_symbol_shape)

    def _answer_project_tool_request(self, prompt):
        project = self._project_root_for_context()
        if not project:
            self._append_assistant_message("Selecione um arquivo ou projeto antes de usar busca/leitura de projeto.")
            return True
        text = self._normalized_prompt(prompt)
        try:
            if "liste os arquivos" in text:
                items = self.project_tools.project_list(project)
                files = [item for item in items if item.kind == "file"]
                preview = "\n".join(f"- {item.path} ({item.language}, {item.size_bytes} bytes)" for item in files[:40])
                self._append_assistant_message(f"Encontrei {len(files)} arquivos em {project}.\n\n{preview}")
            elif "leia as linhas" in text or re.search(r"\blinhas?\s+\d+", text):
                numbers = [int(n) for n in re.findall(r"\d+", text)]
                path = self._path_from_prompt(prompt, project)
                if len(numbers) < 2 or not path:
                    self._append_assistant_message("Informe arquivo e intervalo, por exemplo: leia as linhas 1 a 20 de audit_app/pricing.py.")
                    return True
                read = self.project_tools.project_read_range(project, path, numbers[0], numbers[1])
                self._append_assistant_message(f"{read.path} linhas {read.start_line}-{read.end_line} de {read.total_lines}:\n\n{read.text}")
            elif "quem depende" in text or "dependem de" in text or "importam" in text:
                path = self._path_from_prompt(prompt, project)
                if not path:
                    self._append_assistant_message("Informe o arquivo para consultar dependencias reversas.")
                    return True
                edges = self.project_tools.project_reverse_dependencies(project, path)
                body = "\n".join(f"- {edge.source}:{edge.line} importa {edge.symbol}" for edge in edges) or "Nenhuma dependencia reversa local encontrada."
                self._append_assistant_message(body)
            elif "grafo" in text or "cadeia entre" in text or "depende" in text:
                graph = self.project_tools.project_dependency_graph(project)
                body = "\n".join(f"- {edge.source} -> {edge.target} ({edge.import_type}, linha {edge.line})" for edge in graph.edges[:40])
                self._append_assistant_message(f"Grafo Python local: {len(graph.nodes)} modulos / {len(graph.edges)} dependencias.\n\n{body}")
            elif "arquivos envolvidos" in text or "relacionados" in text:
                path = self._path_from_prompt(prompt, project) or ""
                symbol = self._symbol_from_prompt(prompt)
                rows = self.project_tools.project_related_files(project, seed_path=path, symbol=symbol)
                body = "\n".join(f"- {row['path']} | score {row['score']} | {', '.join(row['reasons'])}" for row in rows[:20])
                self._append_assistant_message(body or "Nao encontrei relacionamento com evidencia local.")
            else:
                symbol = self._symbol_from_prompt(prompt)
                if not symbol:
                    self._append_assistant_message("Informe o termo ou simbolo que devo procurar no projeto.")
                    return True
                refs = self.project_tools.project_find_references(project, symbol)
                matches = refs["references"]
                self.last_project_tool_results = matches
                body = "\n".join(f"{i+1}. {m.path}:{m.line} - {m.snippet}" for i, m in enumerate(matches[:30]))
                self._append_assistant_message(f'Referencias de "{symbol}": {refs["total"]}\n\n{body}')
            self._refresh_execution_feed()
            return True
        except Exception as exc:
            self._append_assistant_message(f"Nao consegui executar a investigacao de projeto: {exc}")
            return True

    def _symbol_from_prompt(self, prompt):
        quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', prompt)
        if quoted:
            return next(part for group in quoted for part in group if part).strip()
        candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", prompt)
        stop = {
            "Procure", "procure", "onde", "usado", "usada", "referencias", "referências",
            "arquivo", "arquivos", "projeto", "linhas", "Leia", "leia", "Quem", "quem",
        }
        for candidate in reversed(candidates):
            if candidate not in stop and len(candidate) > 2:
                return candidate
        return ""

    def _path_from_prompt(self, prompt, project):
        path_match = re.findall(r"[\w./\\-]+\.(?:py|mq5|mqh|txt|md|json|csv|log)", prompt, flags=re.IGNORECASE)
        if path_match:
            raw = path_match[-1].replace("\\", "/")
            if (Path(project) / raw).exists():
                return raw
            name = Path(raw).name
            for item in self.project_tools.project_list(project):
                if Path(item.path).name == name:
                    return item.path
        current = self._context_path()
        if current:
            try:
                return current.resolve().relative_to(Path(project).resolve()).as_posix()
            except ValueError:
                return ""
        return ""

    def _project_root_for_context(self):
        path = self._context_path()
        if not path:
            return None
        current = path if path.is_dir() else path.parent
        projects = PROJECTS_DIR.resolve()
        try:
            current.resolve().relative_to(projects)
        except ValueError:
            return None
        while current.parent != projects and current != projects:
            if (current / "tests").exists() or (current / "pyproject.toml").exists():
                return current
            current = current.parent
        return path.parent if path.is_file() else path

    def _prepare_project_coding_task_from_prompt(self, prompt):
        project = self._project_root_for_context()
        if not project:
            self._append_assistant_message("Selecione primeiro um arquivo dentro do projeto que deve ser corrigido.")
            return True
        try:
            task = self.coding_project_service.create_task(prompt, project)
            task = self.coding_project_service.prepare_full_fix(task.task_id)
            self.active_coding_project_task_id = task.task_id
            self._append_assistant_message(
                "Preparei uma correcao multi-arquivo em sandbox. O projeto original permanece intacto. "
                f"Status: {task.status}. Arquivos afetados: {len(task.affected_files)}. "
                f"Testes da sandbox: {task.test_status}. Aguardando aprovacao atomica."
            )
            self._show_project_coding_panel(task)
            return True
        except Exception as exc:
            self._append_assistant_message(f"Nao consegui preparar a tarefa multi-arquivo: {exc}")
            return True

    def _show_project_coding_panel(self, task):
        self._open_dock("Codigo")
        self.active_coding_project_task_id = task.task_id
        self.active_coding_task_id = None
        self.coding_status.setText(
            f"Status: {task.status} | Projeto: {task.project_root} | Iteracoes: {task.iteration_count}"
        )
        self.coding_file_list.clear()
        for rel in task.affected_files:
            self.coding_file_list.addItem(rel)
        self._refresh_coding_buttons(task)
        self.coding_details.setHtml(self._project_coding_summary_html(task))
        if task.affected_files:
            self.coding_file_list.setCurrentRow(0)

    def _project_coding_summary_html(self, task):
        added = removed = 0
        for rel in task.affected_files:
            diff_path = Path(task.workspace_path) / "diffs" / (rel.replace("/", "__") + ".diff")
            if diff_path.exists():
                for line in diff_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        added += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        removed += 1
        mode = self.execution_service.get_mode()
        risk = "MEDIUM" if task.test_status != "PASSED" or len(task.affected_files) > 1 else "LOW"
        return (
            "<h2 style='color:#F2C94C'>ALTERACAO PROPOSTA</h2>"
            f"<p><b>Task:</b> {task.task_id}<br>"
            f"<b>Status:</b> {task.status}<br>"
            f"<b>Risco:</b> {risk}<br>"
            f"<b>Testes:</b> Sandbox {task.test_status or 'sem dados'}<br>"
            f"<b>Arquivos afetados:</b> {len(task.affected_files)}<br>"
            f"<b>Diff:</b> +{added} / -{removed}<br>"
            f"<b>Modo:</b> {mode.value}</p>"
            f"<p><b>Resumo:</b> {task.result}</p>"
            f"<p><b>Approval manifest real:</b><br><code>{task.approval_manifest_hash}</code></p>"
            "<p style='color:#9AA4B2'>Clique em um arquivo na lista para ver o diff daquele arquivo.</p>"
        )

    def _show_selected_project_diff(self, rel):
        if not rel or not self.active_coding_project_task_id:
            return
        try:
            task = self.coding_project_service.require_task(self.active_coding_project_task_id)
            diff_path = Path(task.workspace_path) / "diffs" / (rel.replace("/", "__") + ".diff")
            diff = diff_path.read_text(encoding="utf-8", errors="replace") if diff_path.exists() else ""
            self.coding_details.setHtml(self._diff_html(rel, diff, task))
        except Exception as exc:
            self.coding_details.setPlainText(f"Falha ao abrir diff: {exc}")

    def _diff_html(self, rel, diff, task):
        rows = [f"<h2 style='color:#F2C94C'>{rel}</h2>", f"<p>Manifest: <code>{task.approval_manifest_hash}</code></p>"]
        if not diff.strip():
            rows.append("<p style='color:#9AA4B2'>Arquivo sem mudancas.</p>")
            return "".join(rows)
        rows.append("<pre style='font-family:Consolas; font-size:12px; white-space:pre-wrap'>")
        for line in diff.splitlines():
            escaped = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            if line.startswith("+") and not line.startswith("+++"):
                rows.append(f"<span style='color:#7BE495;background:#102417'>{escaped}</span>\n")
            elif line.startswith("-") and not line.startswith("---"):
                rows.append(f"<span style='color:#FF8A8A;background:#2A1212'>{escaped}</span>\n")
            elif line.startswith("@@"):
                rows.append(f"<span style='color:#F2C94C'>{escaped}</span>\n")
            else:
                rows.append(f"<span style='color:#D9DEE7'>{escaped}</span>\n")
        rows.append("</pre>")
        return "".join(rows)

    def _refresh_coding_buttons(self, task=None):
        can_apply = self._can_apply_coding_task()
        self.btn_coding_approve.setEnabled(can_apply)
        self.btn_coding_approve.setText("Aprovar alteracao" if can_apply else "Aplicar indisponivel")
        self.btn_coding_reject.setEnabled(bool(task))
        self.btn_coding_tests.setEnabled(bool(task and getattr(task, "workspace_path", "")))
        self.btn_coding_checkpoints.setEnabled(bool(task))

    def _can_apply_coding_task(self):
        return self.execution_service.get_mode() != PermissionMode.READ_ONLY

    def _approval_required_for_coding_task(self):
        return self.execution_service.get_mode() == PermissionMode.ASK

    def _prepare_coding_task_from_prompt(self, prompt):
        source = self._context_path()
        if not source:
            self._append_assistant_message(
                "Para preparar uma alteracao controlada, selecione primeiro um arquivo em C:\\GoldenAI\\projetos."
            )
            return True
        try:
            task = self.coding_service.create_task(prompt, source)
            task = self.coding_service.analyze_and_plan(task.task_id)
            if task.language == "python":
                task = self.coding_service.apply_controlled_python_change(task.task_id)
            else:
                self._append_assistant_message(
                    "Criei a sandbox e o plano, mas esta V1 ainda nao gera alteracao automatica segura para esse pedido/linguagem."
                )
                self.active_coding_task_id = task.task_id
                self._show_coding_panel(task)
                return True
            self.active_coding_task_id = task.task_id
            self._append_assistant_message(
                "Preparei uma alteracao em copia isolada. O original permanece intacto. Revise o painel 'Alteracao proposta' e aprove pelo botao Aprovar se quiser aplicar."
            )
            self._show_coding_panel(task)
            return True
        except Exception as exc:
            self._append_assistant_message(f"Nao consegui preparar a alteracao controlada: {exc}")
            return True

    def _show_coding_panel(self, task):
        self.hero.hide()
        self.hero_sub.hide()
        self.chat_output.hide()
        self.active_coding_project_task_id = None
        if hasattr(self, "activity_panel"):
            self.activity_panel.hide()
        if hasattr(self, "composer"):
            self.composer.show()
        self.coding_panel.show()
        self.coding_status.setText(f"Status: {task.status} | Arquivo: {task.source_path}")
        if hasattr(self, "coding_file_list"):
            self.coding_file_list.clear()
            self.coding_file_list.addItem(Path(task.source_path).name)
        details = (
            f"Pedido:\n{task.user_request}\n\n"
            f"Analise:\n{task.analysis}\n\n"
            f"Plano:\n{task.plan}\n\n"
            f"Validacao pre-aplicacao: {task.validation_status or 'Ainda sem dados'}\n"
            f"Aprovacao: {task.approval_status}\n\n"
            f"Diff:\n{task.diff or 'Ainda sem diff'}"
        )
        self.coding_details.setPlainText(details)

    def _approve_coding_task(self):
        if self.active_coding_project_task_id:
            try:
                if self.execution_service.get_mode() == PermissionMode.READ_ONLY:
                    self._append_assistant_message("Modo SOMENTE LEITURA: aplicacao indisponivel. A proposta permanece em sandbox.")
                    return
                task = self.coding_project_service.approve(self.active_coding_project_task_id)
                task = self.coding_project_service.apply_approved(task.task_id)
                if task.status == "COMPLETED":
                    self._append_assistant_message("Alteracao multi-arquivo aprovada, aplicada e validada com sucesso.")
                elif task.status == "ROLLED_BACK":
                    self._append_assistant_message("A aplicacao multi-arquivo falhou na validacao e o rollback completo foi executado.")
                else:
                    self._append_assistant_message(f"A aplicacao multi-arquivo nao foi concluida: {task.result}")
                self._show_project_coding_panel(task)
            except Exception as exc:
                self._append_assistant_message(f"Falha ao aplicar alteracao multi-arquivo aprovada: {exc}")
            return
        if not self.active_coding_task_id:
            QMessageBox.information(self, "Aprovar", "Nenhuma alteracao aguardando aprovacao.")
            return
        try:
            task = self.coding_service.approve(self.active_coding_task_id)
            task = self.coding_service.apply_approved(task.task_id)
            if task.status == "COMPLETED":
                self._append_assistant_message("Alteracao aprovada aplicada e validada com sucesso.")
            elif task.status == "ROLLED_BACK":
                self._append_assistant_message("A alteracao falhou na validacao e a versao anterior foi restaurada.")
            else:
                self._append_assistant_message(f"A aplicacao nao foi concluida: {task.result}")
            self._show_coding_panel(task)
        except Exception as exc:
            self._append_assistant_message(f"Falha ao aplicar alteracao aprovada: {exc}")

    def _reject_coding_task(self):
        if self.active_coding_project_task_id:
            self._append_assistant_message("Alteracao multi-arquivo rejeitada. Nenhum arquivo original foi modificado.")
            self.active_coding_project_task_id = None
            if hasattr(self, "coding_file_list"):
                self.coding_file_list.clear()
            self.coding_status.setText("Proposta rejeitada")
            self.coding_details.setPlainText("Nenhum arquivo original foi modificado.")
            return
        if not self.active_coding_task_id:
            QMessageBox.information(self, "Rejeitar", "Nenhuma alteracao aguardando aprovacao.")
            return
        try:
            task = self.coding_service.reject(self.active_coding_task_id)
            self._append_assistant_message("Alteracao rejeitada. Nenhum arquivo original foi modificado.")
            self._show_coding_panel(task)
        except Exception as exc:
            self._append_assistant_message(f"Falha ao rejeitar alteracao: {exc}")

    def _show_coding_tests(self):
        task = None
        if self.active_coding_project_task_id:
            task = self.coding_project_service.require_task(self.active_coding_project_task_id)
            reports = sorted((Path(task.workspace_path) / "reports").glob("*_test_output.txt")) if task.workspace_path else []
            body = []
            for report in reports[-4:]:
                body.append(f"===== {report.name} =====\n{report.read_text(encoding='utf-8', errors='replace')[-5000:]}")
            self.coding_details.setPlainText("\n\n".join(body) or "Nenhum relatorio de teste encontrado.")
            return
        self.coding_details.setPlainText("Relatorios de teste disponiveis para tarefas multi-arquivo nesta visualizacao.")

    def _show_coding_checkpoints(self):
        if self.active_coding_project_task_id:
            task = self.coding_project_service.require_task(self.active_coding_project_task_id)
            if not task.checkpoint_ids:
                self.coding_details.setPlainText("Checkpoints serao criados no momento da aplicacao aprovada.")
                return
            self.coding_details.setPlainText(json.dumps(task.checkpoint_ids, ensure_ascii=False, indent=2))
            return
        self.coding_details.setPlainText("Nenhum checkpoint ativo nesta proposta.")

    def _toggle_technical_view(self):
        visible = not self.tabs.isVisible()
        self.tabs.setVisible(visible)
        self.terminal.setVisible(visible)
        self.btn_details.setText("Ocultar código / terminal" if visible else "Código / terminal")
        if visible:
            self._show_chat_mode()
        elif not self.current_conversation:
            self.chat_output.hide()
            self.hero.show()
            self.hero_sub.show()

    def _toggle_technical_view(self):
        if hasattr(self, "terminal_panel") and self.terminal_panel.isVisible():
            self._close_terminal_panel()
        else:
            self._show_terminal_panel()

    def _show_coding_panel(self, task):
        self._open_dock("Codigo")
        self.active_coding_project_task_id = None
        self.coding_status.setText(f"Status: {task.status} | Arquivo: {task.source_path}")
        if hasattr(self, "coding_file_list"):
            self.coding_file_list.clear()
            self.coding_file_list.addItem(Path(task.source_path).name)
        self._refresh_coding_buttons(task)
        details = (
            f"Pedido:\n{task.user_request}\n\n"
            f"Analise:\n{task.analysis}\n\n"
            f"Plano:\n{task.plan}\n\n"
            f"Validacao pre-aplicacao: {task.validation_status or 'Ainda sem dados'}\n"
            f"Aprovacao: {task.approval_status}\n\n"
            f"Diff:\n{task.diff or 'Ainda sem diff'}"
        )
        self.coding_details.setPlainText(details)

    def _build_status(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_engine = QLabel("Motor: verificando...")
        self.status_file = QLabel("Nenhum arquivo selecionado")
        sb.addWidget(self.status_engine)
        sb.addPermanentWidget(self.status_file)
        self._refresh_engine_status()

        # Atalhos principais
        QAction_analisar = QAction(self)
        QAction_analisar.setShortcut(QKeySequence("Ctrl+Enter"))
        QAction_analisar.triggered.connect(self._analisar_arquivo_atual)
        self.addAction(QAction_analisar)

        QAction_compilar = QAction(self)
        QAction_compilar.setShortcut(QKeySequence("F7"))
        QAction_compilar.triggered.connect(self._compilar_arquivo_atual)
        self.addAction(QAction_compilar)

    def _refresh_engine_status(self):
        if ENGINE.exists() and PYTHON_EXE.exists():
            self.status_engine.setText("Motor Golden AI: disponível")
        else:
            self.status_engine.setText("Motor Golden AI: não localizado")

    def _load_history(self):
        try:
            if HISTORY_FILE.exists():
                raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self.history = raw[-30:]
        except Exception as exc:
            self.history = []
            self.terminal.appendPlainText(f"[Histórico] Falha ao carregar: {exc}")
        self._refresh_recent_list()

    def _save_history_file(self):
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self.history[-30:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            self.terminal.appendPlainText(f"[Histórico] Falha ao salvar: {exc}")

    def _refresh_recent_list(self):
        if not hasattr(self, "recent_list"):
            return
        self.recent_list.clear()
        for conv in reversed(self.history[-20:]):
            item = QListWidgetItem(str(conv.get("title", "Conversa"))[:48])
            item.setData(Qt.UserRole, conv.get("id"))
            self.recent_list.addItem(item)

    def _conversation_title(self):
        for msg in self.current_conversation:
            if msg.get("role") == "user":
                t = str(msg.get("text", "")).strip().replace("\n", " ")
                if t:
                    return t[:55]
        return "Nova conversa"

    def _persist_current_conversation(self):
        if not self.current_conversation:
            return
        import time
        if not self.current_conversation_id:
            self.current_conversation_id = str(int(time.time() * 1000))
        record = {
            "id": self.current_conversation_id,
            "title": self._conversation_title(),
            "context": str(self._context_path() or ""),
            "messages": self.current_conversation[-100:],
        }
        for i, old in enumerate(self.history):
            if old.get("id") == self.current_conversation_id:
                self.history[i] = record
                break
        else:
            self.history.append(record)
        self.history = self.history[-30:]
        self._save_history_file()
        self._refresh_recent_list()

    def _new_chat(self):
        self._persist_current_conversation()
        self.current_conversation = []
        self.current_conversation_id = None
        self.activity_view_active = False
        if hasattr(self, "activity_panel"):
            self.activity_panel.hide()
        if hasattr(self, "coding_panel"):
            self.coding_panel.hide()
        if hasattr(self, "module_panel"):
            self.module_panel.hide()
        if hasattr(self, "composer"):
            self.composer.show()
        self.chat_output.clear()
        self.chat_output.hide()
        self.hero.show()
        self.hero_sub.show()
        self.chat_input.clear()
        self.chat_input.setFocus()

    def _open_recent_conversation(self, item):
        conv_id = item.data(Qt.UserRole)
        conv = next((c for c in self.history if c.get("id") == conv_id), None)
        if not conv:
            return
        self._persist_current_conversation()
        self.current_conversation_id = conv.get("id")
        self.current_conversation = list(conv.get("messages", []))
        ctx = str(conv.get("context", "")).strip()
        if ctx and Path(ctx).exists():
            self._set_context_path(Path(ctx), "histórico")
        self.chat_output.clear()
        self._show_chat_mode()
        for msg in self.current_conversation:
            if msg.get("role") == "user":
                self._render_user_message(msg.get("text", ""), msg.get("attachments", []))
            elif msg.get("role") == "assistant":
                self._render_assistant_message(msg.get("text", ""))

    def _choose_context_file(self):
        start = str(PROJECTS_DIR if PROJECTS_DIR.exists() else APP_ROOT)
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Escolher projeto ou arquivo", start,
            "Código e dados (*.mq5 *.mqh *.py *.json *.txt *.md *.csv);;Todos os arquivos (*.*)"
        )
        if chosen:
            self._set_context_path(Path(chosen), "seletor")

    def _show_chat_mode(self):
        self.activity_view_active = False
        if hasattr(self, "module_panel"):
            self.module_panel.show()
        if hasattr(self, "composer"):
            self.composer.show()
        self.hero.hide()
        self.hero_sub.hide()
        self.chat_output.show()
        self._mark_active_module("Chat")
        self.settings.setValue("layout/last_module", "Chat")

    def _render_user_message(self, message):
        safe = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat_output.append(
            "<div style='margin:14px 0 10px 20%; padding:11px 14px; background:#f0f0ed; border-radius:12px;'>"
            f"<span style='color:#232323'>{safe}</span></div>"
        )

    def _render_assistant_message(self, message):
        safe = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat_output.append(
            "<div style='margin:14px 20% 12px 0; padding:5px 2px;'>"
            "<b style='color:#202123'>Golden AI</b><br>"
            f"<span style='color:#343434'>{safe}</span></div>"
        )

    def _new_chat(self):
        self._persist_current_conversation()
        self.current_conversation = []
        self.current_conversation_id = None
        self.activity_view_active = False
        self.chat_output.setHtml(self._empty_chat_html())
        self._show_chat_mode()
        self.chat_input.clear()
        self.chat_input.setFocus()

    def _open_recent_conversation(self, item):
        conv_id = item.data(Qt.UserRole)
        conv = next((c for c in self.history if c.get("id") == conv_id), None)
        if not conv:
            return
        self._persist_current_conversation()
        self.current_conversation_id = conv.get("id")
        self.current_conversation = list(conv.get("messages", []))
        ctx = str(conv.get("context", "")).strip()
        if ctx and Path(ctx).exists():
            self._set_context_path(Path(ctx), "historico")
        self.chat_output.setHtml("")
        self._show_chat_mode()
        for msg in self.current_conversation:
            if msg.get("role") == "user":
                self._render_user_message(msg.get("text", ""), msg.get("attachments", []))
            elif msg.get("role") == "assistant":
                self._render_assistant_message(msg.get("text", ""))

    def _show_chat_mode(self):
        self.activity_view_active = False
        if hasattr(self, "page_stack"):
            self.chat_output.show()
            self.page_stack.setCurrentWidget(self.chat_page)
            self._mark_active_module("Chat")
            self.settings.setValue("layout/last_module", "Chat")
        for key, dock in getattr(self, "docks", {}).items():
            dock.hide()

    def _render_user_message(self, message, attachments=None):
        safe = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        attachments_html = self._attachments_html(attachments or [])
        self.chat_output.append(
            "<div style='margin:14px 0 6px 20%;'>"
            "<div style='color:#9AA4B2; font-size:11px; text-align:right;'>Voce</div>"
            f"<div style='color:#FFFFFF;'>{safe}{attachments_html}</div></div>"
        )

    def _attachments_html(self, attachments):
        if not attachments:
            return ""
        cards = ["<div style='margin-top:10px'>"]
        for item in attachments:
            name = str(item.get("original_name", "anexo")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            ext = str(item.get("extension", "")).upper().replace(".", "") or "FILE"
            size = self._format_bytes(item.get("size_bytes", 0))
            status = str(item.get("processing_status", ""))
            cards.append(
                "<span style='display:inline-block; margin:4px 6px 0 0; padding:7px 9px; "
                "background:#2A2A2A; border:1px solid #FFD700; border-radius:8px;'>"
                f"<b style='color:#FFD700'>[{ext}]</b> {name}<br>"
                f"<span style='color:#BBBBBB'>{size} | {status}</span></span>"
            )
        cards.append("</div>")
        return "".join(cards)

    def _format_bytes(self, value):
        try:
            size = float(value)
        except Exception:
            return "0 B"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size} B"

    def _session_id_for_attachments(self):
        if not self.current_conversation_id:
            import time
            self.current_conversation_id = str(int(time.time() * 1000))
        return self.current_conversation_id

    def _choose_attachments(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Anexar arquivos",
            str(PROJECTS_DIR if PROJECTS_DIR.exists() else APP_ROOT),
            "Suportados (*.png *.jpg *.jpeg *.webp *.txt *.md *.py *.mq5 *.json *.csv *.log *.srt *.vtt *.pdf);;Todos (*.*)",
        )
        if files:
            self._attach_paths(files, "file")

    def _attach_paths(self, paths, source_type="file"):
        for raw in paths:
            try:
                attachment = self.attachment_service.attach_file(raw, self._session_id_for_attachments(), source_type=source_type)
                self.pending_attachments.append(attachment)
            except Exception as exc:
                QMessageBox.warning(self, "Anexo", f"Nao foi possivel anexar:\n{raw}\n\n{exc}")
        self._refresh_attachments_preview()
        self._refresh_execution_feed()

    def _clipboard_has_image(self):
        return QApplication.clipboard().mimeData().hasImage()

    def _attach_clipboard_image(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            return
        temp = Path(tempfile.gettempdir()) / f"golden_clipboard_{self._session_id_for_attachments()}.png"
        image.save(str(temp), "PNG")
        try:
            self._attach_paths([str(temp)], "clipboard")
        finally:
            try:
                temp.unlink()
            except OSError:
                pass

    def _refresh_attachments_preview(self):
        if not hasattr(self, "attachments_preview_layout"):
            return
        self._clear_layout(self.attachments_preview_layout)
        if not self.pending_attachments:
            self.attachments_preview.hide()
            return
        for attachment in self.pending_attachments:
            card = QFrame()
            card.setObjectName("card")
            layout = QHBoxLayout(card)
            layout.setContentsMargins(8, 6, 8, 6)
            label_text = f"{attachment.original_name}\n{self._format_bytes(attachment.size_bytes)}"
            if attachment.extension in {".png", ".jpg", ".jpeg", ".webp"} and attachment.storage_path:
                pix = QPixmap(attachment.storage_path)
                if not pix.isNull():
                    thumb = QLabel()
                    thumb.setPixmap(pix.scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    layout.addWidget(thumb)
            label = QLabel(label_text)
            label.setObjectName("muted")
            layout.addWidget(label)
            remove = QPushButton("X")
            remove.setMaximumWidth(34)
            remove.clicked.connect(lambda checked=False, aid=attachment.attachment_id: self._remove_pending_attachment(aid))
            layout.addWidget(remove)
            self.attachments_preview_layout.addWidget(card)
        self.attachments_preview_layout.addStretch(1)
        self.attachments_preview.show()

    def _remove_pending_attachment(self, attachment_id):
        self.pending_attachments = [item for item in self.pending_attachments if item.attachment_id != attachment_id]
        self._refresh_attachments_preview()

    def _render_assistant_message(self, message):
        safe = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat_output.append(
            "<div style='margin:14px 20% 6px 0;'>"
            "<div style='color:#FFD700; font-size:11px; font-weight:600;'>Golden AI</div>"
            f"<div style='color:#FFFFFF;'>{safe}</div></div>"
        )

    def _load_projects_root(self):
        root = PROJECTS_DIR if PROJECTS_DIR.exists() else APP_ROOT
        self.fs_model.setRootPath(str(root))
        self.tree.setRootIndex(self.fs_model.index(str(root)))
        self.terminal.appendPlainText(f"[Studio] Raiz de projetos: {root}")

    def _set_context_path(self, path, source="seleção"):
        """
        Define o arquivo que expressões como 'este arquivo', 'este robô'
        e 'o arquivo atual' devem representar no chat.
        """
        if not path:
            self.selected_context_path = None
            self.context_source = "nenhum"
            self.status_file.setText("Nenhum arquivo selecionado")
            self._refresh_context_panel()
            return

        p = Path(path)
        if not p.is_file():
            return

        self.selected_context_path = p
        self.context_source = source
        self.status_file.setText(str(p))
        if hasattr(self, "project_context_label"):
            self.project_context_label.setText(f"Arquivo em contexto: {p.name}")
        if hasattr(self, "context_chip"):
            self.context_chip.setText(f"📎  {p.name}")
            self.context_chip.setToolTip(str(p))
        self._refresh_context_panel()

    def _select_tree_item(self, index):
        path = Path(self.fs_model.filePath(index))
        if path.is_file():
            self._set_context_path(path, "árvore")

    def _tab_context_changed(self, index):
        if index < 0:
            return
        widget = self.tabs.widget(index)
        if widget is None:
            return
        path = widget.property("file_path")
        if path:
            self._set_context_path(Path(path), "aba")

    def _context_path(self):
        """
        Prioridade:
        1. aba atualmente aberta;
        2. seleção explícita na árvore.
        """
        current = self._current_path()
        if current and current.exists():
            return current
        if self.selected_context_path and self.selected_context_path.exists():
            return self.selected_context_path
        return None

    def _refresh_context_panel(self):
        path = self._context_path()

        self.context_list.clear()
        self.context_list.addItem("Motor: golden_ai.py")
        self.context_list.addItem("Modo: somente leitura")
        self.context_list.addItem("MT5 real: protegido")
        self.context_list.addItem("Autocorreção: experimental / congelada")
        self.context_list.addItem("Chat bidirecional: disponível")
        self.context_list.addItem("Transporte do motor: ConPTY / pywinpty")

        if not path:
            self.context_list.addItem("Arquivo em contexto: nenhum")
            return

        self.context_list.addItem(f"Arquivo: {path.name}")
        self.context_list.addItem(f"Caminho: {path}")
        self.context_list.addItem(f"Origem do contexto: {self.context_source}")
        self.context_list.addItem(f"Extensão: {path.suffix or '(sem extensão)'}")

        try:
            tamanho = path.stat().st_size
            self.context_list.addItem(f"Tamanho: {tamanho:,} bytes".replace(",", "."))
        except Exception:
            pass

        ext = path.suffix.lower()
        if ext == ".mq5":
            self.context_list.addItem("Tipo: Expert Advisor / MQL5")
        elif ext == ".mqh":
            self.context_list.addItem("Tipo: Include / MQL5")
        elif ext == ".py":
            self.context_list.addItem("Tipo: Python")
        elif ext == ".json":
            self.context_list.addItem("Tipo: JSON")

        self.context_list.addItem("Contexto automático no chat: ATIVO")

    def _context_instruction(self, user_prompt=""):
        """
        Adds a deterministic file reference only when the user intent is
        clearly about the selected project/file. Normal conversation must not
        be pulled into MQL5, robots, MetaTrader, or programming just because a
        file is selected.
        """
        path = self._context_path()
        if not path:
            return ""

        if not self._should_attach_project_context(user_prompt):
            return ""

        is_external_context = self.external_access_service.is_external(path)
        if self.external_access_service.is_external(path):
            task_id = self.current_conversation_id or "chat"
            key = (task_id, str(path.resolve()))
            if key in self.external_context_ready:
                self.external_context_ready.discard(key)
            else:
                decision = self.external_access_service.check_read(task_id, path)
                if not decision.allowed:
                    raise PermissionError("EXTERNAL_ACCESS_APPROVAL_REQUIRED")

        self.file_context_active = True
        self.last_context_path_used = path
        intent = self._classify_user_intent(user_prompt)
        language = self._preferred_response_language(user_prompt)

        content_block = ""
        try:
            if intent != "FILE_METADATA" and path.is_file():
                if is_external_context:
                    content = self.external_access_service.read_text_after_approval(
                        self.current_conversation_id or "chat",
                        path,
                        max_bytes=200_000,
                    )
                elif path.stat().st_size <= 80000:
                    content = path.read_text(encoding="utf-8", errors="replace")
                else:
                    content = ""
                if content:
                    self.execution_service.record_event(
                        task_id=self.current_conversation_id or "chat",
                        category="READ",
                        action="EXTERNAL_CONTEXT_INJECTED" if is_external_context else "CONTEXT_INJECTED",
                        status="COMPLETED",
                        summary="Context injected",
                        target=str(path),
                        tool_name="studio_context",
                        permission_level="READ_EXTERNAL" if is_external_context else "READ",
                        risk_level="LOW",
                    )
                content_block = (
                    "\n[SELECTED_FILE_CONTENT]\n"
                    + content
                    + "\n[/SELECTED_FILE_CONTENT]\n"
                ) if content else ""
        except Exception as exc:
            content_block = f"\n[SELECTED_FILE_READ_ERROR]{exc}[/SELECTED_FILE_READ_ERROR]\n"

        return (
            "\n\n[STUDIO_CONTEXT]\n"
            "The user is asking about the project/file currently selected in Golden AI Studio. "
            "The Studio state below is the source of truth. Do not infer a filename from words "
            "like 'esse', 'este', 'ele', 'isso', 'robo', 'codigo' or 'arquivo'. "
            "Use CURRENT_CONTEXT_PATH exactly and answer in read-only mode. "
            "The selected context defines WHICH file; the original user message defines WHAT to do.\n"
            f"CURRENT_CONTEXT_PATH={path}\n"
            f"CURRENT_CONTEXT_NAME={path.name}\n"
            f"USER_INTENT={intent}\n"
            f"RESPONSE_LANGUAGE={language}\n"
            "READ_ONLY=true\n"
            f"{content_block}"
            "[/STUDIO_CONTEXT]"
        )

    def _ensure_external_context_read_approved(self, prompt):
        path = self._context_path()
        if not path or not self._should_attach_project_context(prompt):
            return True
        if not self.external_access_service.is_external(path):
            return True
        task_id = self.current_conversation_id or self._session_id_for_attachments()
        decision = self.external_access_service.check_read(task_id, path)
        if decision.allowed:
            self.external_context_ready.add((task_id, str(path.resolve())))
            return True
        self.pending_external_prompts[decision.request_id] = prompt
        self.external_access_chat_status = "AWAITING_APPROVAL"
        self.execution_service.record_event(
            task_id=task_id,
            category="PERMISSION",
            action="EXTERNAL_ACCESS_REQUESTED",
            status="WAITING_APPROVAL",
            summary="Arquivo externo detectado; aguardando autorizacao READ",
            target=str(path),
            tool_name="external_access",
            permission_level="READ_EXTERNAL",
            risk_level="LOW",
        )
        self._append_assistant_message(
            "Golden AI solicita acesso somente leitura ao arquivo externo selecionado. "
            "Use o botao Aprovacoes para permitir uma vez, permitir nesta tarefa ou negar."
        )
        self._refresh_execution_feed()
        return False

    def _continue_pending_external_prompt(self, request_id):
        prompt = self.pending_external_prompts.pop(request_id, "")
        if not prompt:
            return
        self.external_access_chat_status = "RUNNING"
        self.chat_input.setText(prompt)
        self._send_chat()

    def _is_permission_help_question(self, prompt):
        text = self._normalized_prompt(prompt)
        return "permiss" in text and any(term in text for term in ("como", "dar", "autorizar", "liberar", "voce", "acesso"))

    def _answer_permission_help_question(self, prompt):
        path = self._context_path()
        if path and self.external_access_service.is_external(path):
            task_id = self.current_conversation_id or self._session_id_for_attachments()
            decision = self.external_access_service.check_read(task_id, path)
            if not decision.allowed:
                self.pending_external_prompts[decision.request_id] = "Analise o arquivo selecionado em modo somente leitura."
                self.external_access_chat_status = "AWAITING_APPROVAL"
            self._append_assistant_message(
                "Posso solicitar autorizacao de leitura para esse arquivo externo. "
                "Quando a solicitacao aparecer em Aprovacoes, escolha Permitir uma vez, "
                "Permitir nesta tarefa ou Negar. Isso autoriza somente leitura do arquivo exato; nao autoriza edicao."
            )
            self._refresh_execution_feed()
            return True
        self._append_assistant_message(
            "As permissoes reais aparecem pelo botao Aprovacoes quando uma acao precisa de autorizacao. "
            "Nao existe um menu de Permitted Paths nesta versao do Studio."
        )
        return True

    def _is_access_now_statement(self, prompt):
        text = self._normalized_prompt(prompt)
        return any(term in text for term in ("pode acessar", "pode ler", "acessar agr", "acessar agora", "liberei", "autorizei"))

    def _answer_access_now_statement(self, prompt):
        path = self._context_path()
        if not path or not self.external_access_service.is_external(path):
            self._append_assistant_message("Nao ha arquivo externo selecionado aguardando acesso agora.")
            return True
        if self.pending_external_prompts:
            request_id = next(iter(self.pending_external_prompts))
            decision = self.external_access_service.check_read(self.current_conversation_id or "chat", path)
            if decision.allowed:
                self._append_assistant_message(f"Sim. O acesso de leitura a {path.name} esta autorizado; vou retomar a pergunta original.")
                self._continue_pending_external_prompt(request_id)
                return True
        decision = self.external_access_service.check_read(self.current_conversation_id or self._session_id_for_attachments(), path)
        if decision.allowed:
            self._append_assistant_message(f"Sim. O acesso de leitura a {path.name} esta autorizado nesta tarefa.")
            return True
        self.pending_external_prompts[decision.request_id] = "me fala qual estrutura e o que esse robo faz"
        self.external_access_chat_status = "AWAITING_APPROVAL"
        self._append_assistant_message(
            f"Esse arquivo ainda precisa de autorizacao de leitura. Abra Aprovacoes e escolha Permitir uma vez, Permitir nesta tarefa ou Negar para {path.name}."
        )
        self._refresh_execution_feed()
        return True

    def _normalized_prompt(self, prompt):
        text = str(prompt or "").lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        replacements = {
            "??": "a", "?": "a", "?": "a", "?": "a", "?": "a",
            "??": "e", "?": "e", "?": "e",
            "??": "i", "?": "i",
            "??": "o", "?": "o", "?": "o", "?": "o",
            "??": "u", "?": "u",
            "??": "c", "?": "c",
        }
        for old, new_value in replacements.items():
            text = text.replace(old, new_value)
        return text

    def _is_subject_change_away_from_project(self, prompt):
        text = self._normalized_prompt(prompt)
        change_markers = (
            "nao quero falar", "nao vamos falar", "nao quero mais falar",
            "esqueca o robo",
            "esqueca robos", "mudar de assunto", "vamos falar sobre",
            "quero falar sobre", "quero conversar sobre",
            "conversar sobre carros", "falar de carros", "falar sobre carros",
        )
        return any(marker in text for marker in change_markers)

    def _is_returning_to_project_context(self, prompt):
        text = self._normalized_prompt(prompt)
        return any(marker in text for marker in (
            "voltando ao robo", "voltar ao robo", "voltando para o robo",
            "voltando ao arquivo", "voltar ao arquivo", "sobre o arquivo",
            "sobre o robo",
        ))

    def _explicit_file_mentions(self, prompt):
        text = str(prompt or "")
        return re.findall(
            r"[\w .\\/:_-]+\.(?:mq5|mqh|py|json|ya?ml|md|txt|csv|ini|cfg|log)",
            text,
            flags=re.IGNORECASE,
        )

    def _has_read_or_analysis_intent(self, prompt):
        text = self._normalized_prompt(prompt)
        if self._classify_user_intent(text) in {"FILE_METADATA", "FILE_READ", "FILE_ANALYSIS", "FILE_EXPLANATION", "MARKET_ANALYSIS", "QUANT_ANALYSIS", "QUANT_EXECUTION"}:
            return True
        intent_terms = (
            "o que", "qual", "quando", "como", "onde", "analise", "analisar",
            "explique", "explicar", "veja", "verifique", "audite", "revise",
            "encontre", "mostre", "tem algum erro", "problema", "bug",
            "funciona", "faz", "usa", "compra", "vende", "stop", "entrada",
            "saida", "break even", "break-even", "breakeven", "logica",
        )
        return any(term in text for term in intent_terms)

    def _classify_user_intent(self, prompt):
        text = self._normalized_prompt(prompt)
        if any(term in text for term in ("corrija", "corrigir", "conserte", "modifique", "altere", "implemente", "fix this code")):
            if any(term in text for term in ("nao altere", "nao modifique", "sem alterar", "do not change")):
                return "FILE_ANALYSIS"
            return "CODING_CHANGE"
        if any(term in text for term in (
            "teste essa strategyspec", "teste essa strategy", "rode o backtest",
            "faca um backtest", "execute essa strategyspec", "valide estatisticamente",
        )):
            return "QUANT_EXECUTION"
        if any(term in text for term in (
            "ultimo experimento", "resultado do ultimo experimento", "quantas operacoes",
            "drawdown", "piores trades", "profit factor", "compare com",
        )):
            return "QUANT_ANALYSIS"
        if any(term in text for term in (
            "analise este dataset", "analise esse dataset", "dataset de mercado",
            "qual o regime desse periodo", "regime desse periodo",
            "timeframes estao alinhados", "estruturas foram detectadas",
            "observacoes foram encontradas", "sinal de compra", "sinal potencial",
        )):
            return "MARKET_ANALYSIS"
        if any(term in text for term in (
            "quantas linhas", "numero de linhas", "contar linhas", "linhas tem",
            "tamanho desse arquivo", "tamanho do arquivo", "qual o tamanho",
            "extensao", "extension", "file size", "how many lines",
        )):
            return "FILE_METADATA"
        if any(term in text for term in ("analise", "analisar", "audite", "revise", "possiveis problemas", "bug", "problema")):
            return "FILE_ANALYSIS"
        if any(term in text for term in ("o que esse", "o que este", "what does this", "explique", "faz", "funciona")):
            return "FILE_EXPLANATION"
        if any(term in text for term in ("leia", "ler", "mostre o conteudo", "show content")):
            return "FILE_READ"
        return "GENERAL_CONVERSATION"

    def _preferred_response_language(self, prompt):
        text = self._normalized_prompt(prompt)
        if any(term in text for term in ("responda em ingles", "answer in english", "in english")):
            return "en"
        if any(term in text for term in ("responda em portugues", "in portuguese")):
            return "pt"
        english_terms = ("what", "does", "this", "code", "file", "how many", "lines", "size", "extension")
        portuguese_terms = ("quantas", "linhas", "codigo", "robo", "arquivo", "qual", "tamanho", "extensao", "nao")
        en_score = sum(1 for term in english_terms if term in text)
        pt_score = sum(1 for term in portuguese_terms if term in text)
        return "en" if en_score > pt_score else "pt"

    def _has_natural_current_file_reference(self, prompt):
        text = self._normalized_prompt(prompt)
        current_refs = (
            "esse robo", "este robo", "o robo", "desse robo", "deste robo",
            "robo selecionado", "esse codigo", "este codigo", "desse codigo",
            "deste codigo", "codigo selecionado", "esse arquivo", "este arquivo",
            "desse arquivo", "deste arquivo", "o arquivo", "arquivo atual",
            "arquivo selecionado", "projeto atual", "projeto selecionado",
            "arquivo que selecionei", "que selecionei", "this code",
            "this file", "selected file", "current file", "esse dataset",
            "este dataset", "dataset selecionado", "dataset atual",
            "esse periodo", "este periodo", "esses dados", "estes dados",
        )
        if any(ref in text for ref in current_refs):
            return self._has_read_or_analysis_intent(text) or self._is_coding_change_request(text)

        pronoun_refs = (" ele ", " dele ", " nele ", " isso ", " esse ")
        padded = f" {text} "
        technical_terms = (
            "robo", "codigo", "arquivo", "stop", "entrada", "saida", "compra",
            "vende", "break even", "break-even", "breakeven", "logica", "erro",
            "problema", "funciona", "faz", "usa", "dataset", "mercado",
            "periodo", "timeframes", "regime", "estrutura", "observacoes",
        )
        return (
            any(ref in padded for ref in pronoun_refs)
            and any(term in text for term in technical_terms)
            and self._has_read_or_analysis_intent(text)
        )

    def _should_attach_project_context(self, prompt):
        text = self._normalized_prompt(prompt)
        if self._is_subject_change_away_from_project(text):
            self.file_context_active = False
            return False

        explicit_mentions = self._explicit_file_mentions(prompt)
        if explicit_mentions and not self._has_natural_current_file_reference(text):
            return False

        if self._classify_user_intent(text) in {"MARKET_ANALYSIS", "QUANT_ANALYSIS", "QUANT_EXECUTION"}:
            return True

        if self._has_natural_current_file_reference(text):
            return True

        if self.file_context_active and self._has_read_or_analysis_intent(text):
            return True

        if self._is_returning_to_project_context(text):
            return True

        project_refs = (
            "arquivo selecionado", "arquivo atual", "este arquivo", "desse arquivo",
            "do arquivo", "projeto selecionado", "meu projeto", "este projeto",
            "codigo selecionado", "este codigo", "desse codigo", "robo selecionado",
            "este robo", "desse robo", "meu robo", "ea selecionado", "break-even",
            "breakeven", "breakevenpreco", "break even", ".mq5", ".mqh",
            "voltando ao robo", "voltar ao robo", "voltando ao arquivo",
        )
        technical_actions = (
            "analise", "analisar", "explique", "explicar", "veja", "verifique",
            "audite", "revise", "compile", "compilar", "corrija", "corrigir",
            "erro", "bug", "funcao", "fun??o", "codigo", "mql5",
        )
        has_project_ref = any(ref in text for ref in project_refs)
        has_action = any(action in text for action in technical_actions)
        return has_project_ref and (has_action or "qual" in text or "o que" in text)

    def _is_mt5_general_inspection(self, prompt):
        """
        Detecta comandos gerais de inspeção do MT5 que NÃO exigem
        arquivo selecionado. Exemplos:
        - "Verifique o MetaTrader 5 instalado neste computador"
        - "O MT5 está aberto?"
        - "Quantos robôs tenho instalados no MT5?"
        - "Localize meu MetaEditor"
        - "Liste os EAs do meu MetaTrader"
        - "Quais instalações do MT5 existem?"
        - "Mostre os EAs instalados"
        - "Status do MT5"
        - "Onde está instalado o MT5"
        - "Qual é a pasta Experts?"
        """
        text = self._normalized_prompt(prompt)

        mt5_terms = ("metatrader", "meta trader", "mt5", "metaeditor")
        has_mt5 = any(term in text for term in mt5_terms)
        if not has_mt5:
            return False

        specific_refs = (
            "este robo", "esse robo", "este arquivo", "esse arquivo",
            "este codigo", "esse codigo", "leia este", "leia esse",
            "analise este", "analise esse", "corrija este", "corrija esse",
            "compile este", "compile esse", "altere este", "altere esse",
            "modifique este", "modifique esse", "abrir este", "abrir esse",
        )
        has_specific_ref = any(ref in text for ref in specific_refs)
        if has_specific_ref:
            return False

        if re.search(r'[\w\\/:.-]+\.(?:mq5|mqh)', text):
            return False

        return True

    def _needs_selected_file_but_missing(self, prompt):
        if self._context_path():
            return False
        text = self._normalized_prompt(prompt)
        if self._is_subject_change_away_from_project(text):
            return False
        if self._is_mt5_general_inspection(prompt):
            return False
        return self._has_natural_current_file_reference(text)

    def _answer_missing_selected_file(self):
        self._append_assistant_message(
            "Preciso que voce selecione ou indique o arquivo/robo primeiro. "
            "Nao vou escolher um projeto automaticamente."
        )

    def _is_context_status_question(self, prompt):
        text = self._normalized_prompt(prompt)
        return (
            ("arquivo" in text or "projeto" in text or "contexto" in text)
            and any(token in text for token in ("qual", "caminho", "nome"))
            and not self._is_subject_change_away_from_project(text)
        )

    def _answer_context_status_question(self):
        path = self._context_path()
        if path:
            answer = f"Arquivo atualmente no contexto: {path.name}\nCaminho: {path}"
        else:
            answer = "Nenhum arquivo ou projeto está atualmente no contexto."
        self._append_assistant_message(answer)

    def _is_chat_diagnostic_question(self, prompt):
        text = str(prompt or "").strip().lower()
        return "teste chat ok" in text and "responda" in text and "somente" in text

    def _open_tree_item(self, index):
        path = Path(self.fs_model.filePath(index))
        if path.is_file():
            self.open_file(path)

    def open_file(self, path: Path):
        path = Path(path)
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            QMessageBox.information(self, "Arquivo", "Este tipo de arquivo ainda não é aberto no editor da V1.15.0.")
            return

        key = str(path).lower()
        if key in self.open_files:
            self.tabs.setCurrentWidget(self.open_files[key])
            return

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir:\n{path}\n\n{e}")
            return

        editor = QPlainTextEdit()
        editor.setReadOnly(True)  # primeira versão: segurança
        editor.setFont(QFont("Consolas", 10))
        editor.setPlainText(text)
        editor.setProperty("file_path", str(path))

        self.open_files[key] = editor
        idx = self.tabs.addTab(editor, path.name)
        self.tabs.setCurrentIndex(idx)
        self._set_context_path(path, "aba")

    def _close_tab(self, idx):
        widget = self.tabs.widget(idx)
        if widget is None:
            return
        path = widget.property("file_path")
        if path:
            self.open_files.pop(str(path).lower(), None)
        self.tabs.removeTab(idx)
        widget.deleteLater()

        # Atualiza o painel para a nova aba ativa ou mantém a seleção da árvore.
        current = self._current_path()
        if current:
            self._set_context_path(current, "aba")
        else:
            self._refresh_context_panel()

    def _current_path(self):
        widget = self.tabs.currentWidget()
        if widget is None:
            return None
        path = widget.property("file_path")
        return Path(path) if path else None

    def _update_context(self, path):
        # Compatibilidade com chamadas antigas.
        self._set_context_path(path, "arquivo")

    def _ensure_engine_process(self):
        if self.engine_process and self.engine_process.state() != QProcess.NotRunning:
            return True

        if not ENGINE.exists() or not PYTHON_EXE.exists() or not BRIDGE.exists():
            self.chat_output.append("<b>Erro:</b> motor/bridge da Golden AI não localizado.")
            self.terminal.appendPlainText(
                f"[Motor] ENGINE={ENGINE.exists()} PYTHON={PYTHON_EXE.exists()} BRIDGE={BRIDGE.exists()}"
            )
            return False

        self._diag_silencio_reportado = False
        self._diag_timeout_reportado = False

        self.engine_process = QProcess(self)
        self.engine_process.setProgram(str(PYTHON_EXE))
        self.engine_process.setArguments(["-u", str(BRIDGE)])
        self.engine_process.setWorkingDirectory(str(APP_DIR))

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.engine_process.setProcessEnvironment(env)

        self.engine_process.setProcessChannelMode(QProcess.SeparateChannels)
        self.engine_process.readyReadStandardOutput.connect(self._read_engine_output)
        self.engine_process.readyReadStandardError.connect(self._read_engine_error_output)
        self.engine_process.started.connect(self._engine_started)
        self.engine_process.finished.connect(self._engine_finished)
        self.engine_process.errorOccurred.connect(self._engine_error)

        self.terminal.appendPlainText("[Motor] Iniciando bridge ConPTY da Golden AI...")
        self.engine_process.start()

        if not self.engine_process.waitForStarted(5000):
            self.terminal.appendPlainText("[Motor] Falha ao iniciar o bridge.")
            return False

        return True

    def _engine_started(self):
        import time
        self.engine_ready = True
        self.engine_waiting_input = False
        self.engine_start_ms = int(time.time() * 1000)
        self.engine_last_output_ms = self.engine_start_ms
        self.status_engine.setText("Motor Golden AI: iniciando ConPTY...")
        self.terminal.appendPlainText("[Motor] Bridge iniciado; criando pseudo-terminal real.")
        self.terminal.appendPlainText(f"[Diag] Bridge PID: {int(self.engine_process.processId()) if self.engine_process else 0}")
        self.terminal.appendPlainText(f"[Diag] Bridge: {BRIDGE}")
        self.terminal.appendPlainText(f"[Diag] Engine: {ENGINE}")
        self.engine_diag_timer.start()

    def _engine_finished(self, exit_code, exit_status):
        self.engine_diag_timer.stop()
        self.engine_ready = False
        self.engine_waiting_input = False
        self.status_engine.setText("Motor Golden AI: encerrado")
        self.terminal.appendPlainText(
            f"[Motor] Processo encerrado. exit={exit_code} status={getattr(exit_status, 'name', str(exit_status))}"
        )

    def _engine_error(self, error):
        self.terminal.appendPlainText(f"[Motor] Erro de processo: {error}")

    def _read_engine_error_output(self):
        import time
        if not self.engine_process:
            return

        data = bytes(self.engine_process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )
        if not data:
            return

        self.engine_last_output_ms = int(time.time() * 1000)
        self.terminal.appendPlainText("\n[STDERR DO MOTOR]")
        self.terminal.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal.insertPlainText(data)
        self.terminal.appendPlainText("\n[FIM STDERR]")
        scroll = self.terminal.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def _engine_diagnostic_tick(self):
        """
        Watchdog de handshake.
        Não envia comandos escondidos e não altera arquivos.
        Apenas mostra onde o processo está parado.
        """
        import time

        if not self.engine_process:
            return

        state = self.engine_process.state()
        now = int(time.time() * 1000)

        if state == QProcess.NotRunning:
            self.engine_diag_timer.stop()
            return

        elapsed = 0
        silent = 0
        if self.engine_start_ms:
            elapsed = (now - self.engine_start_ms) / 1000.0
        if self.engine_last_output_ms:
            silent = (now - self.engine_last_output_ms) / 1000.0

        # Só imprime checkpoints úteis para não poluir o terminal.
        sec = int(elapsed)
        if sec in (3, 6, 10, 15, 20, 30) and abs(elapsed - sec) < 1.6:
            self.terminal.appendPlainText(
                f"[Handshake] estado={state.name} tempo={elapsed:.1f}s "
                f"sem_saida={silent:.1f}s fila={len(self.engine_prompt_queue)}"
            )

        # Se o prompt estiver visível no buffer, conclui o handshake mesmo que
        # tenha chegado entre ticks/chunks.
        if self.engine_waiting_input or self._main_prompt_visible():
            if not self.engine_waiting_input:
                self.engine_waiting_input = True
                self.engine_ready = True
                self.status_engine.setText("Motor Golden AI: pronto")
                self.terminal.appendPlainText(
                    "[Handshake] OK: prompt principal reconhecido pelo watchdog."
                )
                self._flush_prompt_queue()
            self.engine_diag_timer.stop()
            return

        # Diagnóstico forte depois de 12s sem qualquer saída.
        if elapsed >= 12 and silent >= 12:
            self.status_engine.setText("Motor Golden AI: sem saída / diagnosticando")
            if not getattr(self, "_diag_silencio_reportado", False):
                self._diag_silencio_reportado = True
                self.terminal.appendPlainText(
                    "[Handshake] ALERTA: processo está ativo, mas não produziu stdout/stderr."
                )
                self.terminal.appendPlainText(
                    "[Handshake] ConPTY ativo; aguardando saída real do console da Golden AI."
                )

        # Depois de 25s, mantém sessão viva mas deixa claro que o handshake falhou.
        if elapsed >= 25 and not self.engine_waiting_input:
            if not getattr(self, "_diag_timeout_reportado", False):
                self._diag_timeout_reportado = True
                self.status_engine.setText("Motor Golden AI: handshake não concluído")
                self.terminal.appendPlainText(
                    "[Handshake] TIMEOUT DIAGNÓSTICO: processo continua aberto, "
                    "mas o prompt principal não apareceu."
                )
                self.terminal.appendPlainText(
                    "[Handshake] Nenhuma mensagem foi enviada automaticamente ao motor."
                )

    def _normalize_terminal_text(self, value):
        """
        Normaliza texto vindo do ConPTY:
        - remove sequências ANSI/VT100;
        - converte CRLF/CR para LF;
        - remove NUL;
        - preserva conteúdo textual real.
        """
        s = str(value or "")
        s = s.replace("\x00", "")
        s = s.replace("\r\n", "\n").replace("\r", "\n")

        # CSI: ESC [ ... comando
        s = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", s)

        # OSC: ESC ] ... BEL ou ESC \
        s = re.sub(r"\x1B\].*?(?:\x07|\x1B\\\\)", "", s, flags=re.DOTALL)

        # Outros ESC simples.
        s = re.sub(r"\x1B[@-_]", "", s)
        return s

    def _main_prompt_visible(self):
        """
        Detecta o prompt principal mesmo se ele chegar:
        - dividido em vários chunks;
        - com ANSI;
        - com espaços;
        - como 'Voce:' ou 'Você:'.
        """
        tail = self._clean_terminal_display(self.engine_buffer[-6000:])

        # O prompt principal precisa estar no final lógico do stream.
        return bool(
            re.search(
                r"(?:^|\n)\s*(?:Voce|Voc[^\s:]{1,2})\s*:\s*$",
                tail,
                flags=re.IGNORECASE
            )
        )

    def _append_assistant_message(self, message):
        msg = str(message or "").strip()
        if not msg or msg in {"Você:", "VocÃª:", "Voce:", "Golden AI:"}:
            return
        self._show_chat_mode()
        if hasattr(self, "agent_indicator"):
            match = re.search(r"Especialista(?:s)?\s*:\s*([^\n]+)", msg)
            if match:
                self.agent_indicator.setText("Especialista: " + match.group(1)[:48])
        self._render_assistant_message(msg)
        self.current_conversation.append({"role": "assistant", "text": msg})
        if getattr(self, "external_access_chat_status", "") == "RUNNING":
            self.external_access_chat_status = "COMPLETED"
        self._persist_current_conversation()
        self._refresh_execution_feed()
        self._set_chat_status("")
        self._refresh_model_footer()
        sb = self.chat_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _extract_chat_messages(self):
        """
        Extrai respostas completas no formato:

            Golden AI:
            <resposta>
            Voce:

        Funciona com ANSI e chunks fragmentados do ConPTY.
        """
        buf = self._clean_terminal_display(self.engine_chat_buffer)

        while True:
            m_start = re.search(
                r"(?:^|\n)\s*Golden AI\s*:\s*",
                buf,
                flags=re.IGNORECASE
            )
            if not m_start:
                if len(buf) > 20000:
                    buf = buf[-4000:]
                break

            after_start = buf[m_start.end():]

            m_end = re.search(
                r"(?:\n+)\s*(?:Voce|Voc[^\s:]{1,2})\s*:\s*",
                after_start,
                flags=re.IGNORECASE
            )

            if not m_end:
                # resposta ainda incompleta
                buf = buf[m_start.start():]
                break

            answer = after_start[:m_end.start()].strip()
            self._append_assistant_message(answer)

            buf = after_start[m_end.end():]

        self.engine_chat_buffer = buf

    def _detect_main_prompt(self, data):
        """
        Compatibilidade: usa o buffer acumulado do ConPTY e não depende
        de o prompt chegar inteiro no mesmo readyRead.
        """
        return self._main_prompt_visible()

    def _flush_prompt_queue(self):
        if not self.engine_process:
            return
        if self.engine_process.state() == QProcess.NotRunning:
            return
        if not self.engine_waiting_input:
            return
        if not self.engine_prompt_queue:
            return

        prompt = self.engine_prompt_queue.pop(0)
        payload = (prompt + "\\n").encode("utf-8", errors="replace")

        written = self.engine_process.write(payload)
        if written < 0:
            self.chat_output.append(
                "<b>Erro:</b> não foi possível enviar a mensagem ao motor."
            )
            return

        self.engine_process.waitForBytesWritten(2000)
        self.engine_waiting_input = False
        self.status_engine.setText("Motor Golden AI: processando...")
        self.terminal.appendPlainText(f"\\n[Studio -> Motor] {prompt}")

    def _clean_terminal_display(self, value):
        """
        Limpeza SOMENTE VISUAL. O buffer bruto continua intacto para o handshake.
        Remove ANSI e também códigos de cursor que chegam sem ESC, como:
        [14;7H  [14;16H  [2J  [1K
        """
        s = self._normalize_terminal_text(value)

        # Cursor position / horizontal-vertical position.
        s = re.sub(r"\[\d+(?:;\d+)*[Hf]", "", s)

        # Erase/display/cursor move comuns sem ESC.
        s = re.sub(r"\[\d*(?:;\d+)*[ABCDJKG]", "", s)

        # DEC private modes residuais.
        s = re.sub(r"\[\?\d+(?:;\d+)*[hl]", "", s)

        # Modos simples como [1t, [2t, etc.
        s = re.sub(r"\[\d+(?:;\d+)*[t]", "", s)
        return s

    def _track_engine_status(self, data):
        try:
            text = str(data or "")
            tool_match = re.search(r"GoldenAI usando ferramenta:\s*([A-Za-z0-9_]+)", text)
            if tool_match:
                self._set_chat_status(f"Executando: {tool_match.group(1)}")
            model_match = re.search(r"\(modelo:\s*([^)]+)\)", text)
            if model_match:
                self._set_active_model(str(model_match.group(1)).strip())
            if "usando o motor local Qwen do Golden" in text:
                self._set_chat_status("Executando: motor local Golden (Qwen)")
            fallback_match = re.search(r"\[GoldenAI usando ferramenta: ([^\]]+)\]", text)
            if fallback_match and not tool_match:
                self._set_chat_status(f"Executando: {fallback_match.group(1).strip()}")
        except Exception:
            pass

    def _process_engine_text(self, data):
        """
        Recebe texto bruto vindo do golden_ai.py dentro do ConPTY.
        Terminal recebe tudo; chat recebe somente respostas completas.
        """
        import time
        if not data:
            return

        self.engine_last_output_ms = int(time.time() * 1000)

        display_data = self._clean_terminal_display(data)
        self.terminal.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal.insertPlainText(display_data)
        tscroll = self.terminal.verticalScrollBar()
        tscroll.setValue(tscroll.maximum())

        self._track_engine_status(data)

        self.engine_buffer = (self.engine_buffer + data)[-48000:]
        self.engine_chat_buffer += data
        self._extract_chat_messages()

        # Prompt pode vir fragmentado e com ANSI.
        if self._main_prompt_visible():
            if not self.engine_waiting_input:
                self.terminal.appendPlainText(
                    "\n[Handshake] OK: prompt principal detectado via ConPTY."
                )
            self.engine_waiting_input = True
            self.engine_ready = True
            self.status_engine.setText("Motor Golden AI: pronto")
            self.engine_diag_timer.stop()
            self._flush_prompt_queue()

    def _read_engine_output(self):
        """
        stdout do bridge é JSON Lines; cada evento output contém texto real
        do console da Golden AI.
        """
        import time
        if not self.engine_process:
            return

        data = bytes(self.engine_process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if not data:
            return

        # Acumulador exclusivo do protocolo JSON do bridge.
        proto = getattr(self, "_bridge_protocol_buffer", "") + data
        lines = proto.split("\n")
        self._bridge_protocol_buffer = lines.pop()

        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue

            try:
                evt = json.loads(raw)
            except Exception:
                self.terminal.appendPlainText("[Bridge RAW] " + raw)
                continue

            kind = evt.get("type")

            if kind == "output":
                self._process_engine_text(str(evt.get("text", "")))

            elif kind == "status":
                status = str(evt.get("status", ""))
                if status == "pty_started":
                    self.terminal.appendPlainText("[Bridge] ConPTY iniciado com sucesso.")
                    self.terminal.appendPlainText(f"[Bridge] Python: {evt.get('python')}")
                    self.terminal.appendPlainText(f"[Bridge] Engine: {evt.get('engine')}")
                    self.status_engine.setText("Motor Golden AI: aguardando prompt ConPTY...")
                elif status == "sent":
                    self.status_engine.setText("Motor Golden AI: processando...")
                elif status == "engine_exited":
                    self.terminal.appendPlainText("[Bridge] golden_ai.py encerrou.")
                    self.status_engine.setText("Motor Golden AI: encerrado")

            elif kind == "fatal":
                msg = str(evt.get("message", "Falha fatal no bridge."))
                detail = str(evt.get("detail", ""))
                self.terminal.appendPlainText("[Bridge FATAL] " + msg)
                if detail:
                    self.terminal.appendPlainText(detail)
                self.chat_output.append(f"<b>Erro do bridge:</b> {msg}")
                self.status_engine.setText("Motor Golden AI: falha no ConPTY")

            elif kind == "bridge_error":
                self.terminal.appendPlainText(
                    "[Bridge ERRO] " + str(evt.get("message", ""))
                )

            elif kind == "pong":
                self.terminal.appendPlainText(
                    f"[Bridge] healthcheck alive={evt.get('alive')}"
                )

    def _send_bridge_json(self, obj):
        if not self.engine_process:
            return False
        if self.engine_process.state() == QProcess.NotRunning:
            return False

        payload = (json.dumps(obj, ensure_ascii=False) + "\n").encode(
            "utf-8", errors="replace"
        )
        written = self.engine_process.write(payload)
        if written < 0:
            return False
        self.engine_process.waitForBytesWritten(1500)
        return True

    def _flush_prompt_queue(self):
        if not self.engine_process:
            return
        if self.engine_process.state() == QProcess.NotRunning:
            return
        if not self.engine_waiting_input:
            return
        if not self.engine_prompt_queue:
            return

        prompt = self.engine_prompt_queue.pop(0)

        if not self._send_bridge_json({"type": "send", "text": prompt}):
            self.chat_output.append(
                "<b>Erro:</b> não foi possível enviar a mensagem ao bridge."
            )
            return

        self.engine_waiting_input = False
        self.status_engine.setText("Motor Golden AI: processando...")
        self.terminal.appendPlainText(f"\n[Studio -> ConPTY] {prompt}")

    def _send_chat(self):
        prompt = self.chat_input.text().strip()
        attachments = list(getattr(self, "pending_attachments", []))
        if not prompt and attachments:
            prompt = "Analise os anexos enviados."
        if not prompt:
            return

        self.chat_input.clear()
        self.pending_attachments = []
        self._refresh_attachments_preview()
        self.last_user_prompt = prompt
        self._show_chat_mode()
        self._set_chat_status("Pensando...")
        coding_change_requested = self._is_coding_change_request(prompt)
        attachment_dicts = [item.to_dict() for item in attachments]
        self._render_user_message(prompt, attachment_dicts)
        self.current_conversation.append({"role": "user", "text": prompt, "attachments": attachment_dicts})
        self.execution_service.record_event(
            task_id=self.current_conversation_id or "chat",
            category="TASK",
            action="CHAT_MESSAGE_SENT",
            status="RUNNING",
            summary="Mensagem enviada ao motor",
            details="Evento de alto nivel; conteudo privado do prompt nao e exposto no feed.",
            target="chat",
            agent="studio",
            permission_level=self.execution_service.get_mode().value,
            risk_level="LOW",
        )
        self._refresh_execution_feed()
        if self._needs_selected_file_but_missing(prompt):
            self._persist_current_conversation()
            self._answer_missing_selected_file()
            return
        if self._is_permission_help_question(prompt):
            self._persist_current_conversation()
            if self._answer_permission_help_question(prompt):
                return
        if self._is_access_now_statement(prompt):
            self._persist_current_conversation()
            if self._answer_access_now_statement(prompt):
                return
        if not self._ensure_external_context_read_approved(prompt):
            self._persist_current_conversation()
            return
        if self._is_mt5_general_inspection(prompt):
            pass  # MT5 general inspection does not need project tools
        elif self._is_project_tool_request(prompt):
            self._persist_current_conversation()
            if self._answer_project_tool_request(prompt):
                return
        if self._is_project_coding_request(prompt):
            self._persist_current_conversation()
            if self._prepare_project_coding_task_from_prompt(prompt):
                return
        if coding_change_requested:
            self._persist_current_conversation()
            if self._prepare_coding_task_from_prompt(prompt):
                return
        self._persist_current_conversation()

        # Enfileira a versão enviada ao motor já com o contexto determinístico.
        if self._is_context_status_question(prompt):
            self._answer_context_status_question()
            return

        if self._is_chat_diagnostic_question(prompt):
            self._append_assistant_message("TESTE CHAT OK")
            return

        if attachments and any(item.extension in {".png", ".jpg", ".jpeg", ".webp"} for item in attachments):
            image_paths = [item.storage_path for item in attachments if item.extension in {".png", ".jpg", ".jpeg", ".webp"} and item.storage_path]
            vision = self.vision_service.analyze_images(image_paths, prompt, self.current_conversation_id or "chat")
            if vision.status == "COMPLETED":
                self.agent_indicator.setText("Especialista: Vision")
                self._append_assistant_message(vision.text)
                self._refresh_execution_feed()
                return
            self._append_assistant_message("Imagem recebida e associada a mensagem, mas nenhum modelo multimodal local funcional esta habilitado agora.")
            self._refresh_execution_feed()
            return

        if attachments and all(item.processing_status not in {"STORED"} for item in attachments):
            self._append_assistant_message("Anexos recebidos, mas nenhum deles possui processamento textual disponivel nesta fase.")
            return

        prompt_for_engine = self.attachment_service.summarize_for_engine(prompt, attachments) + self._context_instruction(prompt)
        self.engine_prompt_queue.append(prompt_for_engine)

        if not self._ensure_engine_process():
            # Remove apenas a mensagem recém-enfileirada caso o motor nem inicie.
            if self.engine_prompt_queue and self.engine_prompt_queue[-1] == prompt_for_engine:
                self.engine_prompt_queue.pop()
            return

        # Se o prompt principal já foi detectado, envia imediatamente.
        if self.engine_waiting_input:
            self._flush_prompt_queue()
        else:
            self.status_engine.setText("Motor Golden AI: aguardando prompt ConPTY...")
            self.terminal.appendPlainText(
                "[Studio] Mensagem enfileirada; aguardando o prompt principal via ConPTY."
            )

    def _stop_engine(self):
        self.engine_prompt_queue.clear()
        self.engine_waiting_input = False
        self.engine_diag_timer.stop()
        if self.engine_process and self.engine_process.state() != QProcess.NotRunning:
            self.terminal.appendPlainText("[Motor] Encerrando sessão ConPTY...")
            self._send_bridge_json({"type": "stop"})
            if not self.engine_process.waitForFinished(3000):
                self.engine_process.kill()
                self.engine_process.waitForFinished(1500)

    def _analisar_arquivo_atual(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "Analisar", "Abra um arquivo primeiro.")
            return
        prompt = (
            f"Analise SOMENTE o arquivo atual em modo somente leitura. "
            "Explique estrutura, funções principais, riscos e dependências. "
            "Não altere nenhum arquivo."
        )
        self.chat_input.setText(prompt)
        self._send_chat()

    def _compilar_arquivo_atual(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "Compilar", "Abra um arquivo primeiro.")
            return
        if path.suffix.lower() != ".mq5":
            QMessageBox.information(self, "Compilar", "A compilação direta desta versão está focada em .mq5.")
            return

        # Busca MetaEditor no terminal usado pela GoldenAI.
        self.terminal.appendPlainText(f"[Compilar] Solicitado: {path}")

        # Tenta descobrir MetaEditor em locais comuns.
        candidates = []
        terminal_root = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
        if terminal_root.exists():
            for p in terminal_root.glob("**/metaeditor64.exe"):
                candidates.append(p)
        for p in [
            Path(r"C:\Program Files\MetaTrader 5\metaeditor64.exe"),
            Path(r"C:\Program Files\MetaTrader 5\MetaEditor64.exe"),
        ]:
            if p.exists():
                candidates.append(p)

        if not candidates:
            self.terminal.appendPlainText("[Compilar] MetaEditor não localizado automaticamente.")
            self.terminal.appendPlainText("[Compilar] O motor Golden AI continua disponível para compilar pelo fluxo atual.")
            return

        metaeditor = candidates[0]
        log_file = APP_DIR / "studio_metaeditor_compile.log"

        proc = QProcess(self)
        proc.setProgram(str(metaeditor))
        proc.setArguments([
            f"/compile:{path}",
            f"/log:{log_file}"
        ])
        proc.finished.connect(lambda code, status: self._compile_finished(path, log_file, code))
        proc.start()
        self.terminal.appendPlainText(f"[Compilar] MetaEditor: {metaeditor}")

    def _compile_finished(self, path, log_file, code):
        self.terminal.appendPlainText(f"[Compilar] Processo finalizado. Exit code: {code}")
        if log_file.exists():
            txt = log_file.read_text(encoding="utf-16", errors="replace")
            if not txt.strip():
                txt = log_file.read_text(encoding="utf-8", errors="replace")
            self.terminal.appendPlainText(txt[-12000:])
        else:
            self.terminal.appendPlainText("[Compilar] Log não encontrado.")

    def _mostrar_mensagem_teste(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "Testar", "Abra um arquivo primeiro.")
            return

        if path.suffix.lower() == ".py":
            self.terminal.appendPlainText(f"[Testar] py_compile: {path}")
            proc = QProcess(self)
            proc.setProgram(str(PYTHON_EXE))
            proc.setArguments(["-m", "py_compile", str(path)])
            proc.setProcessChannelMode(QProcess.MergedChannels)

            def done(code, status):
                out = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
                if out:
                    self.terminal.appendPlainText(out)
                if code == 0:
                    self.terminal.appendPlainText("[Testar] Python: OK")
                else:
                    self.terminal.appendPlainText(f"[Testar] Python: FALHOU (exit {code})")

            proc.finished.connect(done)
            proc.start()
            return

        if path.suffix.lower() == ".mq5":
            self.terminal.appendPlainText("[Testar] Para .mq5, executando compilação MetaEditor.")
            self._compilar_arquivo_atual()
            return

        QMessageBox.information(
            self,
            "Testar",
            "Nesta versão, Testar suporta diretamente .py e .mq5."
        )

    def _corrigir_arquivo_atual(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "Corrigir", "Abra um arquivo primeiro.")
            return
        prompt = (
            f"Corrija erros e melhore a qualidade do codigo do arquivo atual: {path.name}. "
            f"Mostre as correcoes propostas linha a linha, explique cada mudanca e aplique apenas "
            "as correcao que nao alterem o comportamento esperado. Use o motor Golden AI."
        )
        self.chat_input.setText(prompt)
        self._send_chat()

    def _rollback_arquivo_atual(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "Rollback", "Abra um arquivo primeiro.")
            return
        base = path.name
        candidates = []
        backups_dir = APP_ROOT / "backups"
        if backups_dir.exists():
            for p in backups_dir.rglob(base):
                candidates.append(p)
        for folder in (APP_ROOT / "studio",):
            if folder.exists():
                for p in folder.glob(f"*_{base}*"):
                    candidates.append(p)
                for p in folder.glob(base):
                    candidates.append(p)
        candidates = [c for c in candidates if c.resolve() != path.resolve()]
        if not candidates:
            QMessageBox.information(
                self,
                "Rollback",
                f"Nenhum backup anterior encontrado para {base}. Nada a restaurar.",
            )
            return
        candidates.sort(key=lambda c: c.stat().st_mtime, reverse=True)
        latest = candidates[0]
        if not QMessageBox.question(
            self,
            "Rollback",
            f"Restaurar {base} a partir de:\n{latest}\n\nIsso substitui o arquivo atual por este backup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            return
        try:
            shutil_copy = __import__("shutil").copy2(latest, path)
            self.terminal.appendPlainText(f"[Rollback] Arquivo restaurado de: {latest}")
            if path.suffix.lower() == ".py":
                self.terminal.appendPlainText("[Rollback] Reexecutando verificacao de sintaxe...")
                proc = QProcess(self)
                proc.setProgram(str(PYTHON_EXE))
                proc.setArguments(["-m", "py_compile", str(path)])
                proc.finished.connect(lambda *_: self.terminal.appendPlainText(f"[Rollback] py_compile exit {proc.exitCode()}"))
                proc.start()
        except Exception as e:
            QMessageBox.critical(self, "Rollback", str(e))

    def _comparar_placeholder(self):
        atual = self._current_path()
        if not atual:
            QMessageBox.information(self, "Comparar", "Abra um arquivo primeiro.")
            return

        outro, _ = QFileDialog.getOpenFileName(
            self,
            "Escolha o arquivo para comparar",
            str(atual.parent),
            "Arquivos de texto (*.mq5 *.mqh *.py *.txt *.json *.md *.csv);;Todos (*.*)"
        )
        if not outro:
            return

        try:
            a = atual.read_text(encoding="utf-8", errors="replace").splitlines()
            b_path = Path(outro)
            b = b_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            QMessageBox.critical(self, "Comparar", str(e))
            return

        diff = "\n".join(difflib.unified_diff(
            a, b,
            fromfile=str(atual),
            tofile=str(b_path),
            lineterm=""
        ))

        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setFont(QFont("Consolas", 10))
        editor.setPlainText(diff or "Nenhuma diferença encontrada.")
        self.tabs.addTab(editor, f"DIFF: {atual.name}")
        self.tabs.setCurrentWidget(editor)

    def closeEvent(self, event):
        self._persist_current_conversation()
        try:
            self.settings.setValue("layout/focus_mode", self.focus_mode)
            self.settings.setValue("layout/terminal_open", self.terminal.isVisible())
            if hasattr(self, "root_splitter"):
                self.settings.setValue("layout/root_splitter", self.root_splitter.saveState())
        except Exception:
            pass
        try:
            self.activity_service.end_session(self.activity_session_id)
        except Exception:
            pass
        self._stop_engine()
        event.accept()


def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Golden AI Studio")
    app.setStyleSheet(THEME)

    win = GoldenAIStudio()
    win.show()
    
    # Tentativa de executar para verificar erros
    try:
        exit_code = app.exec()
        sys.exit(exit_code)
    except Exception as e:
        print(f"Erro na execução: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
