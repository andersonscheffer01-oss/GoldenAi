"""Minimal persistent diagnostics for frozen Desktop startup."""
from __future__ import annotations

import faulthandler
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path


LOG_DIR = Path(r"C:\GoldenAI\logs")
BOOT_LOG = LOG_DIR / "jarvis_desktop_boot.log"
FAULT_LOG = LOG_DIR / "jarvis_desktop_faulthandler.log"
_QT_DLL_DIRECTORY = None


def prepare_frozen_qt() -> None:
    """Prefer the Qt DLLs extracted beside the frozen PySide6 modules."""
    if not getattr(sys, "frozen", False):
        return
    root = Path(getattr(sys, "_MEIPASS", ""))
    qt_dir = root / "PySide6"
    shiboken_dir = root / "shiboken6"
    if not qt_dir.is_dir():
        return
    global _QT_DLL_DIRECTORY
    if hasattr(os, "add_dll_directory"):
        _QT_DLL_DIRECTORY = os.add_dll_directory(str(qt_dir))
        if shiboken_dir.is_dir():
            os.add_dll_directory(str(shiboken_dir))
    os.environ["PATH"] = (str(qt_dir) + os.pathsep + str(shiboken_dir) +
                           os.pathsep + os.environ.get("PATH", ""))
    boot_log(f"QT_DLL_DIR={qt_dir} SHIBOKEN_DLL_DIR={shiboken_dir}")


def boot_log(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with BOOT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")
    except Exception:
        pass


def _exception_text(exc_type, exc_value, exc_traceback) -> str:
    return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))


def install() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with BOOT_LOG.open("a", encoding="utf-8") as handle:
            handle.write("====================\n")
            handle.write(f"timestamp={datetime.now(timezone.utc).isoformat()}\n")
            handle.write(f"PID={os.getpid()}\n")
            handle.write(f"frozen={getattr(sys, 'frozen', False)}\n")
            handle.write(f"sys.executable={sys.executable}\n")
            handle.write(f"cwd={os.getcwd()}\n")
            handle.write(f"argv={sys.argv!r}\n")
            handle.write("====================\n")
    except Exception:
        pass

    def excepthook(exc_type, exc_value, exc_traceback):
        boot_log("PYTHON_UNHANDLED_EXCEPTION\n" +
                 _exception_text(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        def thread_hook(args):
            boot_log(
                f"THREAD_UNHANDLED_EXCEPTION name={args.thread.name!r}\n" +
                _exception_text(args.exc_type, args.exc_value, args.exc_traceback))
            threading.__excepthook__(args)
        threading.excepthook = thread_hook

    try:
        fault_handle = FAULT_LOG.open("a", encoding="utf-8")
        faulthandler.enable(fault_handle)
    except Exception:
        pass

    try:
        from PySide6.QtCore import qInstallMessageHandler

        def qt_handler(message_type, context, message):
            location = f" {context.file}:{context.line}" if context.file else ""
            boot_log(f"QT_{message_type.name if hasattr(message_type, 'name') else message_type}"
                     f"{location} {message}")
        qInstallMessageHandler(qt_handler)
    except Exception as exc:
        boot_log(f"QT_HANDLER_INSTALL_FAILED {type(exc).__name__}: {exc}")
