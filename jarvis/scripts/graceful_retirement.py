"""Local, fail-closed CTRL_C retirement of the legacy Windows Uvicorn service.

Run from a disposable console helper. No public endpoint or force fallback.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time

import psutil


def verify_identity(pid, created, executable, cwd, command, port):
    process = psutil.Process(pid)
    if process.create_time() != created:
        raise RuntimeError("Process creation time changed")
    if Path(process.exe()).resolve() != Path(executable).resolve():
        raise RuntimeError("Executable mismatch")
    if Path(process.cwd()).resolve() != Path(cwd).resolve():
        raise RuntimeError("Project directory mismatch")
    if process.cmdline() != command:
        raise RuntimeError("Command mismatch")
    listeners = [c for c in psutil.net_connections(kind="tcp")
                 if c.status == psutil.CONN_LISTEN and c.laddr.port == port]
    if not listeners or any(c.pid != pid for c in listeners):
        raise RuntimeError("Listener ownership mismatch")
    return process


def require_exclusive_console(members, target, helper):
    if set(members) != {target, helper}:
        raise RuntimeError("Console is shared or target absent; no signal sent")


def signal_and_wait(pid, created, executable, cwd, command, port, timeout=30):
    if os.name != "nt":
        raise RuntimeError("Windows only")
    if not 1 <= timeout <= 60:
        raise ValueError("Timeout must be between 1 and 60 seconds")
    process = verify_identity(pid, created, executable, cwd, command, port)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.AttachConsole.argtypes = [wintypes.DWORD]
    kernel.AttachConsole.restype = wintypes.BOOL
    kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    kernel.GetConsoleProcessList.restype = wintypes.DWORD
    kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    kernel.FreeConsole()
    if not kernel.AttachConsole(pid):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        members = (wintypes.DWORD * 64)()
        count = kernel.GetConsoleProcessList(members, len(members))
        if not 0 < count <= len(members):
            raise RuntimeError("Cannot prove console membership")
        require_exclusive_console(list(members[:count]), pid, os.getpid())
        verify_identity(pid, created, executable, cwd, command, port)
        if not kernel.SetConsoleCtrlHandler(None, True):
            raise ctypes.WinError(ctypes.get_last_error())
        # CTRL_C is delivered only to the verified isolated console. The helper
        # ignores it; Uvicorn handles SIGINT and runs its normal lifespan shutdown.
        if not kernel.GenerateConsoleCtrlEvent(0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        print("GRACEFUL_SHUTDOWN_REQUESTED", flush=True)
        process.wait(timeout=timeout)
        print("PROCESS_EXITED_VOLUNTARILY", flush=True)
    finally:
        kernel.FreeConsole()


def verify_quarantine():
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "$t = Get-ScheduledTask -TaskPath '\\' | Where-Object "
        "TaskName -eq 'Golden Jarvis - Inicializa\u00e7\u00e3o Autom\u00e1tica'; "
        "@($t | Select-Object TaskName,@{n='Enabled';e={$_.Settings.Enabled}},"
        "@{n='Args';e={$_.Actions.Arguments}}) | ConvertTo-Json -Compress"
    ], capture_output=True, text=True, check=True, timeout=15)
    tasks = json.loads(result.stdout)
    tasks = tasks if isinstance(tasks, list) else [tasks]
    launcher = str(Path(__file__).resolve().with_name("start_jarvis.ps1"))
    if len(tasks) != 1 or tasks[0]["Enabled"] is not False or launcher not in tasks[0]["Args"]:
        raise RuntimeError("Verified legacy autostart is not quarantined")
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        if (process.info["name"] or "").lower() in {"powershell.exe", "pwsh.exe"}:
            if any(launcher.lower() in arg.lower() for arg in process.info["cmdline"] or []):
                raise RuntimeError("Legacy supervisor still active; no signal sent")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--created", type=float, required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    verify_quarantine()
    cwd = Path(__file__).resolve().parents[1] / "backend"
    command = [args.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8780"]
    signal_and_wait(args.pid, args.created, args.executable, cwd, command, 8780)
    for _ in range(15):
        if any(c.status == psutil.CONN_LISTEN and c.laddr.port == 8780
               for c in psutil.net_connections(kind="tcp")):
            raise RuntimeError("Port 8780 acquired a listener after shutdown")
        time.sleep(1)
    verify_quarantine()
    print("PORT_8780_FREE_NO_RESTART", flush=True)


if __name__ == "__main__":
    main()
