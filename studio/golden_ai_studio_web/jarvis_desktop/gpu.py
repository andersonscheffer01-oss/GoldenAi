"""Telemetria local da GPU (Windows; honesto: N/D quando indisponivel).

Nao usa nvidia-smi. Tenta CIM Win32_VideoController (nome + VRAM total).
Utilizacao/vram usada: N/D, a menos que fonte confiavel exista.
Cache de 60s; nunca bloqueia a UI (chamado em worker).
"""
from __future__ import annotations

import subprocess
import tempfile
import threading
import time

_CACHE = {"at": 0.0, "data": {"name": None, "vram_total_human": None,
                              "util_percent": None, "vram_used_human": None,
                              "status": "UNAVAILABLE", "reason": "wmi_unavailable"}}
_TTL = 60.0
_WMI_TIMEOUT = 5.0
_WMI_LOCK = threading.Lock()


def _run_wmi_json(timeout=_WMI_TIMEOUT):
    """Run WMI without reader threads so a driver query cannot destabilize Qt."""
    command = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name, AdapterRAM | ConvertTo-Json -Compress",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with _WMI_LOCK:
        with tempfile.TemporaryFile(mode="w+b") as stdout:
            process = subprocess.Popen(
                command,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            try:
                return_code = process.wait(timeout=float(timeout))
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1.0)
                except Exception:
                    pass
                return None
            if return_code != 0:
                return None
            stdout.seek(0)
            return stdout.read().decode("utf-8", errors="replace")


def _cim_video_controllers():
    try:
        raw = _run_wmi_json()
    except Exception:
        return []
    if not raw or not raw.strip():
        return []
    import json
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def get_gpu_info(force=False):
    now = time.time()
    if not force and (now - _CACHE["at"]) < _TTL:
        return dict(_CACHE["data"])
    info = {"name": None, "vram_total_human": None,
            "util_percent": None, "vram_used_human": None,
            "status": "UNAVAILABLE", "reason": "wmi_unavailable"}
    try:
        ctrls = [c for c in _cim_video_controllers()
                 if isinstance(c, dict) and c.get("Name")]
        if ctrls:
            # Prefere GPU dedicada (maior AdapterRAM).
            ctrls.sort(key=lambda c: int(c.get("AdapterRAM") or 0), reverse=True)
            best = ctrls[0]
            info["name"] = str(best["Name"]).strip()
            try:
                total = int(best.get("AdapterRAM") or 0)
                if 0 < total < 0xF0000000:
                    info["vram_total_human"] = f"{total / (1024 ** 3):.1f} GB"
            except (TypeError, ValueError):
                pass
            info["status"] = "PARTIAL"
            info["reason"] = "dynamic_metrics_unavailable"
    except Exception:
        pass
    _CACHE["at"] = now
    _CACHE["data"] = info
    return dict(info)
