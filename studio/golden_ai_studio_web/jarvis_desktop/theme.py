"""Tema V3: central de comando — quase-preto, cyan, panels HUD, console."""
from __future__ import annotations

ACCENT = "#22d3ee"
ACCENT_DEEP = "#0e7490"
BG = "#030811"
PANEL = "#050d18"
TEXT = "#d9e8f5"
ICE = "#f2f7fd"
MUTED = "#5f7391"
GOOD = "#2dd4bf"
WARN = "#f5b04c"
BAD = "#f46868"
MONO = "Consolas, 'Cascadia Mono', monospace"

STYLE = f"""
* {{ font-family: 'Segoe UI', Arial; }}
QMainWindow, QWidget#root {{ background: {BG}; color: {TEXT}; }}
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel.brandGold {{ color: {ICE}; font-size: 17px; font-weight: 800; letter-spacing: 5px; }}
QLabel.brandCyan {{ color: {ACCENT}; font-size: 17px; font-weight: 800; letter-spacing: 5px; }}
QLabel.mode {{ color: {MUTED}; font-size: 9px; letter-spacing: 3px; }}
QLabel.net {{ font-size: 12px; font-weight: 700; letter-spacing: 1px; }}
QLabel.tag {{ color: {MUTED}; font-size: 9px; letter-spacing: 2px; font-family: {MONO}; }}
QLabel.tele {{ color: {TEXT}; font-size: 12px; font-family: {MONO}; }}
QLabel.teleBar {{ color: {ACCENT}; font-size: 12px; font-family: {MONO}; }}
QLabel.muted {{ color: {MUTED}; }}
QLabel.accent {{ color: {ACCENT}; }}
QLabel.route {{ color: {MUTED}; font-size: 10px; font-family: {MONO}; letter-spacing: 1px; }}
QTextEdit.console {{ background: transparent; border: none; color: {TEXT};
  font-size: 13px; selection-background-color: {ACCENT_DEEP}; }}
QLineEdit.command {{ background: transparent; color: {ICE}; border: none;
  border-bottom: 1px solid #1c3350; padding: 10px 4px; font-size: 13px; letter-spacing: 1px; }}
QLineEdit.command:focus {{ border-bottom: 1px solid {ACCENT}; }}
QPushButton.mic {{ background: transparent; color: {ACCENT}; border: 1px solid #1e3a56;
  border-radius: 17px; font-size: 14px; }}
QPushButton.send {{ background: transparent; color: {ACCENT}; border: 1px solid {ACCENT_DEEP};
  border-radius: 6px; padding: 8px 18px; font-size: 12px; letter-spacing: 2px; }}
QPushButton.send:hover {{ border-color: {ACCENT}; }}
QPushButton.tbtn {{ background: transparent; color: {MUTED}; border: none;
  font-size: 13px; font-weight: 700; }}
QPushButton.tbtn:hover {{ color: {TEXT}; }}
QPushButton.abtn {{ background: #0a1626; color: {TEXT}; border: 1px solid #1e3a56;
  border-radius: 6px; padding: 6px 12px; font-size: 11px; font-family: {MONO}; }}
QPushButton.abtn:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton.danger {{ background: transparent; color: {BAD}; border: 1px solid #5a2323;
  border-radius: 6px; padding: 6px 12px; font-size: 11px; font-family: {MONO}; }}
QTabWidget::pane {{ border: 1px solid #0d1f36; border-radius: 4px;
  background: rgba(5, 13, 25, 220); }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 6px 9px; margin: 0 2px;
  font-size: 10px; letter-spacing: 2px; font-family: {MONO}; border: none;
  border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QListWidget {{ background: transparent; border: none; font-size: 12px; font-family: {MONO}; }}
QListWidget::item {{ border: none; border-left: 2px solid #16283f; padding: 6px 8px; margin: 3px 0; }}
QListWidget::item:selected {{ background: #081426; color: {ACCENT}; border-left: 2px solid {ACCENT}; }}
QCheckBox {{ color: {TEXT}; spacing: 8px; font-size: 12px; }}
QCheckBox::indicator {{ width: 32px; height: 16px; border-radius: 8px;
  background: #101e33; border: 1px solid #2b3f66; }}
QCheckBox::indicator:checked {{ background: {ACCENT_DEEP}; border: 1px solid {ACCENT}; }}
QSizeGrip {{ background: transparent; }}
"""


def apply_theme(app):
    app.setStyleSheet(STYLE)
