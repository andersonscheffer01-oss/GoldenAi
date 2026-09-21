"""Tema V4: Golden Jarvis Desktop — Dark Navy, Cyan Elétrico, Dourado."""
from __future__ import annotations

from PySide6.QtGui import QColor

# ============================================================
# PALETA V4
# ============================================================

BG_DEEP = "#020610"           # Fundo principal (quase-preto navy)
BG_PANEL = "#040c1a"          # Painéis/cards
BG_ELEVATED = "#061224"       # Elementos elevados (hover, active)
BG_HOVER = "#081830"          # Hover sutil

CYAN = "#00e5ff"              # Accent principal (elétrico)
CYAN_DIM = "#007a8a"          # Accent secundário/bordas
CYAN_GLOW = "#00ffff"         # Glow/brilho intenso
CYAN_SOFT = "#00e5ff33"       # 20% alpha para backgrounds

BLUE_ELECTRIC = "#1e90ff"     # Azul elétrico (estados ativos)
BLUE_ELECTRIC_DIM = "#1568c0" # Azul elétrico dim

GOLD = "#ffd700"              # Detalhes dourados (brand, highlights)
GOLD_DIM = "#b8860b"          # Dourado suave
GOLD_SOFT = "#ffd70033"       # 20% alpha

TEXT_PRIMARY = "#e8f4fd"      # Texto principal
TEXT_SECONDARY = "#8ab4d8"    # Texto secundário/labels
TEXT_MUTED = "#4a6b8a"        # Texto muted/desabilitado
TEXT_ON_ACCENT = "#020610"    # Texto sobre accent (contraste)

GOOD = "#00ff88"              # Sucesso/online
WARN = "#ffaa00"              # Atenção/processando
BAD = "#ff4444"               # Erro/offline

GRID_LINE = "#003344"         # Grid sutil backdrop
BORDER_SUBTLE = "#0d1f36"     # Bordas sutis
BORDER_ACCENT = "#007a8a"     # Bordas accent

# Fontes
MONO_FONT = "Consolas, 'Cascadia Mono', 'JetBrains Mono', monospace"
UI_FONT = "Segoe UI, Inter, Arial, sans-serif"
DISPLAY_FONT = "Segoe UI, Inter, sans-serif"

# Espaçamento (base 4px)
SP_4 = 4
SP_8 = 8
SP_12 = 12
SP_16 = 16
SP_24 = 24
SP_32 = 32
SP_48 = 48
SP_64 = 64

# Raio de borda
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_XL = 16
RADIUS_FULL = 9999

# Sombras/Glow (para QSS box-shadow onde suportado)
GLOW_CYAN = "0 0 24px rgba(0, 229, 255, 0.35), 0 0 48px rgba(0, 229, 255, 0.15)"
GLOW_GOLD = "0 0 20px rgba(255, 215, 0, 0.3), 0 0 40px rgba(255, 215, 0, 0.1)"
SHADOW_DEEP = "0 8px 32px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.4)"

# ============================================================
# HELPERS DE COR
# ============================================================

def qcolor(hex_str: str) -> QColor:
    """Converte hex (#RRGGBB ou #RRGGBBAA) para QColor."""
    return QColor(hex_str)

def alpha(hex_str: str, a: int) -> str:
    """Retorna hex com alpha (0-255)."""
    c = QColor(hex_str)
    c.setAlpha(a)
    return c.name(QColor.HexArgb)

def rgba(hex_str: str, a: float) -> str:
    """Retorna rgba string para QSS."""
    c = QColor(hex_str)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"

# ============================================================
# STYLESHEET GLOBAL V4
# ============================================================

STYLE_V4 = f"""
/* ===== BASE ===== */
* {{
    font-family: {UI_FONT};
}}
QMainWindow, QWidget#rootV4 {{
    background: {BG_DEEP};
    color: {TEXT_PRIMARY};
}}
QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

/* ===== TIPOGRAFIA ===== */
QLabel.brandGold {{
    color: {GOLD};
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 6px;
    font-family: {DISPLAY_FONT};
}}
QLabel.brandCyan {{
    color: {CYAN};
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 6px;
    font-family: {DISPLAY_FONT};
}}
QLabel.modeTag {{
    color: {TEXT_MUTED};
    font-size: 9px;
    letter-spacing: 3px;
    font-family: {MONO_FONT};
}}
QLabel.netStatus {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    font-family: {MONO_FONT};
}}
QLabel.hudTag {{
    color: {TEXT_MUTED};
    font-size: 9px;
    letter-spacing: 2px;
    font-family: {MONO_FONT};
}}
QLabel.telemetry {{
    color: {TEXT_PRIMARY};
    font-size: 12px;
    font-family: {MONO_FONT};
}}
QLabel.telemetryBar {{
    color: {CYAN};
    font-size: 12px;
    font-family: {MONO_FONT};
}}
QLabel.muted {{
    color: {TEXT_MUTED};
}}
QLabel.accent {{
    color: {CYAN};
}}
QLabel.gold {{
    color: {GOLD};
}}
QLabel.routeInfo {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-family: {MONO_FONT};
    letter-spacing: 1px;
}}

/* ===== INPUTS ===== */
QTextEdit.console {{
    background: transparent;
    border: none;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    selection-background-color: {CYAN_DIM};
    font-family: {UI_FONT};
}}
QLineEdit.command {{
    background: transparent;
    color: #f2f7fd;
    border: none;
    border-bottom: 1px solid #1c3350;
    padding: 10px 4px;
    font-size: 13px;
    letter-spacing: 1px;
    font-family: {UI_FONT};
}}
QLineEdit.command:focus {{
    border-bottom: 1px solid {CYAN};
}}
QLineEdit.commandBar {{
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_MD}px;
    padding: 10px 14px;
    font-size: 13px;
    font-family: {UI_FONT};
    selection-background-color: {CYAN_DIM};
}}
QLineEdit.commandBar:focus {{
    border: 1px solid {CYAN};
}}

/* ===== BOTÕES ===== */
QPushButton.micBtn {{
    background: transparent;
    color: {CYAN};
    border: 1px solid #1e3a56;
    border-radius: 17px;
    font-size: 14px;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
}}
QPushButton.micBtn:hover {{
    border-color: {CYAN_DIM};
    background: {CYAN_SOFT};
}}
QPushButton.micBtn:pressed {{
    background: {CYAN};
    color: {TEXT_ON_ACCENT};
}}
QPushButton.micBtn.active {{
    background: {CYAN};
    color: {TEXT_ON_ACCENT};
    border-color: {CYAN};
}}

QPushButton.sendBtn {{
    background: transparent;
    color: {CYAN};
    border: 1px solid {CYAN_DIM};
    border-radius: {RADIUS_MD}px;
    padding: 8px 18px;
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: 600;
}}
QPushButton.sendBtn:hover {{
    border-color: {CYAN};
    background: {CYAN_SOFT};
}}
QPushButton.sendBtn:pressed {{
    background: {CYAN};
    color: {TEXT_ON_ACCENT};
}}

QPushButton.modeBtn {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: {RADIUS_MD}px;
    padding: 8px 16px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    font-family: {MONO_FONT};
    min-width: 100px;
}}
QPushButton.modeBtn:hover {{
    color: {TEXT_PRIMARY};
    border-color: {BORDER_SUBTLE};
    background: {BG_HOVER};
}}
QPushButton.modeBtn:checked {{
    color: {GOLD};
    border-color: {GOLD_DIM};
    background: {GOLD_SOFT};
}}
QPushButton.modeBtn:checked:hover {{
    color: {GOLD};
    border-color: {GOLD};
    background: {GOLD_SOFT};
}}

QPushButton.titleBtn {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    font-size: 13px;
    font-weight: 700;
    min-width: 34px;
    max-width: 34px;
    min-height: 30px;
    max-height: 30px;
}}
QPushButton.titleBtn:hover {{
    color: {TEXT_PRIMARY};
    background: {BG_HOVER};
}}
QPushButton.titleBtn.closeBtn:hover {{
    color: {BAD};
    background: rgba(255, 68, 68, 0.15);
}}

QPushButton.actionBtn {{
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_MD}px;
    padding: 10px 16px;
    font-size: 11px;
    font-family: {MONO_FONT};
    font-weight: 600;
    min-height: 40px;
}}
QPushButton.actionBtn:hover {{
    border-color: {CYAN_DIM};
    background: {BG_ELEVATED};
    color: {CYAN};
}}
QPushButton.actionBtn:pressed {{
    border-color: {CYAN};
    background: {CYAN_SOFT};
    color: {CYAN};
}}
QPushButton.actionBtn.primary {{
    border-color: {CYAN};
    color: {CYAN};
}}
QPushButton.actionBtn.primary:hover {{
    background: {CYAN_SOFT};
}}
QPushButton.actionBtn.gold {{
    border-color: {GOLD_DIM};
    color: {GOLD};
}}
QPushButton.actionBtn.gold:hover {{
    background: {GOLD_SOFT};
    color: {GOLD};
}}
QPushButton.actionBtn.danger {{
    border-color: #5a2323;
    color: {BAD};
}}
QPushButton.actionBtn.danger:hover {{
    background: rgba(255, 68, 68, 0.1);
    border-color: {BAD};
}}

QPushButton.quickActionBtn {{
    background: {BG_PANEL};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_MD}px;
    padding: 12px 16px;
    font-size: 11px;
    font-family: {MONO_FONT};
    font-weight: 600;
    text-align: center;
    min-height: 56px;
}}
QPushButton.quickActionBtn:hover {{
    border-color: {CYAN_DIM};
    background: {BG_ELEVATED};
    color: {CYAN};
}}
QPushButton.quickActionBtn:pressed {{
    border-color: {CYAN};
    background: {CYAN_SOFT};
}}

/* ===== TABS ===== */
QTabWidget::pane {{
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_MD}px;
    background: rgba(4, 12, 26, 220);
    margin-top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 12px;
    margin: 0 2px;
    font-size: 10px;
    letter-spacing: 2px;
    font-family: {MONO_FONT};
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {CYAN};
    border-bottom: 2px solid {CYAN};
}}
QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}

/* ===== LISTAS ===== */
QListWidget {{
    background: transparent;
    border: none;
    font-size: 12px;
    font-family: {MONO_FONT};
    outline: none;
}}
QListWidget::item {{
    border: none;
    border-left: 2px solid #16283f;
    padding: 8px 10px;
    margin: 3px 0;
}}
QListWidget::item:selected {{
    background: {BG_ELEVATED};
    color: {CYAN};
    border-left: 2px solid {CYAN};
}}
QListWidget::item:hover {{
    background: {BG_HOVER};
}}

/* ===== CHECKBOX ===== */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 36px;
    height: 18px;
    border-radius: 9px;
    background: #101e33;
    border: 1px solid #2b3f66;
}}
QCheckBox::indicator:checked {{
    background: {CYAN_DIM};
    border: 1px solid {CYAN};
}}
QCheckBox::indicator:hover {{
    border-color: {CYAN_DIM};
}}

/* ===== SCROLLBAR ===== */
QScrollBar:vertical {{
    background: {BG_DEEP};
    width: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #1a3048;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {CYAN_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_DEEP};
    height: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #1a3048;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {CYAN_DIM};
}}

/* ===== SIZE GRIP ===== */
QSizeGrip {{
    background: transparent;
    width: 16px;
    height: 16px;
    image: url(:/grip.png); /* opcional */
}}

/* ===== TOOLTIP ===== */
QToolTip {{
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
    font-size: 11px;
    font-family: {UI_FONT};
}}

/* ===== SEPARATOR ===== */
QFrame.hLine {{
    border: none;
    border-top: 1px solid {BORDER_SUBTLE};
    max-height: 1px;
}}
QFrame.vLine {{
    border: none;
    border-left: 1px solid {BORDER_SUBTLE};
    max-width: 1px;
}}
"""

# ============================================================
# APLICAÇÃO DO TEMA
# ============================================================

def apply_theme_v4(app):
    """Aplica o tema V4 globalmente."""
    app.setStyleSheet(STYLE_V4)

# ============================================================
# ESTADOS DE ANIMAÇÃO → CORES
# ============================================================

ANIMATION_STATE_COLORS = {
    "IDLE": CYAN,
    "LISTENING": CYAN,
    "PROCESSING": GOLD,
    "SPEAKING": BLUE_ELECTRIC,
    "OFFLINE": "#3b4c66",
    "ERROR": BAD,
}

ANIMATION_PULSE_SPEED = {
    "IDLE": 0.8,
    "LISTENING": 2.4,
    "PROCESSING": 3.0,
    "SPEAKING": 2.0,
    "OFFLINE": 0.0,
    "ERROR": 6.0,
}

def anim_color(state: str) -> str:
    return ANIMATION_STATE_COLORS.get(str(state).upper(), CYAN)

def anim_pulse_speed(state: str) -> float:
    return ANIMATION_PULSE_SPEED.get(str(state).upper(), 1.0)

# ============================================================
# NÓS RADIAIS (CONTROLE MODE)
# ============================================================

RADIAL_NODES = [
    {"id": "pesquisa", "label": "PESQUISA", "icon": "🔍", "angle": 0},
    {"id": "memoria", "label": "MEMÓRIA", "icon": "🧠", "angle": 30},
    {"id": "projetos", "label": "PROJETOS", "icon": "📁", "angle": 60},
    {"id": "automacao", "label": "AUTOMAÇÃO", "icon": "⚙️", "angle": 90},
    {"id": "analise", "label": "ANÁLISE", "icon": "📊", "angle": 120},
    {"id": "documentos", "label": "DOCUMENTOS", "icon": "📄", "angle": 150},
    {"id": "agenda", "label": "AGENDA", "icon": "📅", "angle": 180},
    {"id": "internet", "label": "INTERNET", "icon": "🌐", "angle": 210},
    {"id": "ferramentas", "label": "FERRAMENTAS", "icon": "🔧", "angle": 240},
    {"id": "trading", "label": "TRADING", "icon": "📈", "angle": 270},
    {"id": "design", "label": "DESIGN", "icon": "🎨", "angle": 300},
    {"id": "nucleo", "label": "NÚCLEO", "icon": "⬟", "angle": 330, "is_core": True},
]

# ============================================================
# AÇÕES RÁPIDAS (CONTROLE MODE) — REAIS
# ============================================================

QUICK_ACTIONS = [
    {"id": "nova_tarefa", "label": "NOVA TAREFA", "icon": "➕", "primary": True},
    {"id": "executar_agente", "label": "EXECUTAR AGENTE", "icon": "▶️", "primary": False},
    {"id": "abrir_projeto", "label": "ABRIR PROJETO", "icon": "📂", "primary": False},
    {"id": "ver_logs", "label": "VER LOGS", "icon": "📋", "primary": False},
    {"id": "configurar", "label": "CONFIGURAR", "icon": "⚙️", "primary": False},
    {"id": "atualizar", "label": "ATUALIZAR", "icon": "🔄", "primary": False},
]

# ============================================================
# AGENTES ATIVOS — DADOS REAIS (via CONTROLE view)
# ============================================================

MOCK_ACTIVE_AGENTS = []

# ============================================================
# PROJETOS RECENTES — DADOS REAIS (via CONTROLE view)
# ============================================================

MOCK_RECENT_PROJECTS = []