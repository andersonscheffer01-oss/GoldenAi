"""Entry point do Golden Jarvis Desktop V4."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtWidgets import QApplication

from .api_client import JarvisApiClient
from .main_window_v4 import MainWindowV4
from .theme_v4 import apply_theme_v4


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Golden Jarvis V4")
    app.setQuitOnLastWindowClosed(False)
    apply_theme_v4(app)
    base = os.environ.get("GOLDEN_BACKEND_URL", "http://127.0.0.1:8765")
    window = MainWindowV4(JarvisApiClient(base))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())