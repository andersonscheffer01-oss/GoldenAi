"""Entry point for the JARVIS web desktop shell."""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtWidgets import QApplication, QMessageBox

from .core_launcher import CoreLaunchError, CoreLauncher
from .boot_diagnostics import boot_log
from .identity import DesktopIdentityError, DesktopIdentityManager
from .single_instance import SingleInstance
from .web_window import DesktopMainWindow


def build_parser():
    parser = argparse.ArgumentParser(prog="JARVIS")
    parser.add_argument("--hidden", action="store_true",
                        help="Inicia somente na bandeja do sistema.")
    return parser


def main(argv=None):
    boot_log("BOOT_02_PROJECT_ROOT")
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    app.setOrganizationName("GoldenAI")
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    boot_log("BOOT_03_SINGLE_INSTANCE_START")
    if not instance.acquire():
        boot_log("SINGLE_INSTANCE_ROLE=SECONDARY TARGET_SIGNAL_SENT=YES")
        return 0
    boot_log("BOOT_04_SINGLE_INSTANCE_OK SINGLE_INSTANCE_ROLE=PRIMARY")

    launcher = CoreLauncher()
    boot_log("BOOT_05_QAPPLICATION_START")
    try:
        launcher.ensure_online()
        boot_log("BOOT_06_QAPPLICATION_OK BOOT_10_CORE_HEALTH_OK")
    except CoreLaunchError as exc:
        instance.close()
        QMessageBox.critical(None, "JARVIS", str(exc))
        return 1

    try:
        device_token = DesktopIdentityManager(launcher._ssl_context()).ensure_identity()
    except DesktopIdentityError as exc:
        instance.close()
        launcher.stop_owned_core()
        QMessageBox.critical(None, "JARVIS - autenticação", str(exc))
        return 1

    boot_log("BOOT_11_WINDOW_START")
    window = DesktopMainWindow(launcher, instance, device_token=device_token)
    boot_log("BOOT_12_WINDOW_OK")
    instance.activate_requested.connect(window.restore_window)
    app.aboutToQuit.connect(window.cleanup)
    if not args.hidden:
        boot_log("BOOT_14_SHOW_WINDOW")
        window.show()
    boot_log("BOOT_15_EVENT_LOOP BOOT_READY")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
