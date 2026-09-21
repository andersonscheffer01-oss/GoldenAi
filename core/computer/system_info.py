from __future__ import annotations

import getpass
import os
import platform
import subprocess
import sys
from dataclasses import asdict

from .models import SystemInfo


def _memory_status() -> tuple[int, int]:
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys), int(stat.ullAvailPhys)
    except Exception:
        return 0, 0


def _cpu_model() -> str:
    try:
        out = subprocess.check_output(
            ["wmic", "cpu", "get", "name"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        lines = [line.strip() for line in out.splitlines() if line.strip() and line.strip().lower() != "name"]
        return lines[0] if lines else platform.processor()
    except Exception:
        return platform.processor()


def get_system_info() -> dict:
    total, available = _memory_status()
    info = SystemInfo(
        hostname=platform.node(),
        windows_version=platform.platform(),
        architecture=platform.machine(),
        cpu_model=_cpu_model(),
        logical_cpus=os.cpu_count() or 0,
        ram_total_bytes=total,
        ram_available_bytes=available,
        user=getpass.getuser(),
        python=sys.version.split()[0],
        goldenai_root=r"C:\GoldenAI",
    )
    return asdict(info)
