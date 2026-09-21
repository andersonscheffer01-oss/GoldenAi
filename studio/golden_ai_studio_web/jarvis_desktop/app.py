"""Entry point do Golden Jarvis Desktop."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtWidgets import QApplication

from .api_client import JarvisApiClient
from .main_window import MainWindow
from .theme import apply_theme


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Golden Jarvis")
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    base = os.environ.get("GOLDEN_BACKEND_URL", "http://127.0.0.1:8765")
    window = MainWindow(JarvisApiClient(base))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
