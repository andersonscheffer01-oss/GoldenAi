"""PyInstaller-friendly entry point for the JARVIS Desktop shell."""
from jarvis_desktop.boot_diagnostics import boot_log, install, prepare_frozen_qt

prepare_frozen_qt()
install()
boot_log("BOOT_00_ENTRY")

from jarvis_desktop.web_app import main
boot_log("BOOT_01_IMPORTS_OK")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException:
        boot_log("TOP_LEVEL_MAIN_EXCEPTION\n" + __import__("traceback").format_exc())
        raise
