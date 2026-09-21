"""Telemetria local da GPU (Windows; honesto: N/D quando indisponivel).

Nao usa nvidia-smi. Tenta CIM Win32_VideoController (nome + VRAM total).
Utilizacao/vram usada: N/D, a menos que fonte confiavel exista.
Cache de 60s; nunca bloqueia a UI (chamado em worker).
"""
from __future__ import annotations

import subprocess
import time

_CACHE = {"at": 0.0, "data": {"name": None, "vram_total_human": None,
                              "util_percent": None, "vram_used_human": None}}
_TTL = 60.0


def _cim_video_controllers():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object Name, AdapterRAM | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15)
    except Exception:
        return []
    if out.returncode != 0 or not out.stdout.strip():
        return []
    import json
    try:
        data = json.loads(out.stdout)
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def get_gpu_info(force=False):
    now = time.time()
    if not force and (now - _CACHE["at"]) < _TTL:
        return dict(_CACHE["data"])
    info = {"name": None, "vram_total_human": None,
            "util_percent": None, "vram_used_human": None}
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
                if total > 0:
                    info["vram_total_human"] = f"{total / (1024 ** 3):.1f} GB"
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    _CACHE["at"] = now
    _CACHE["data"] = info
    return dict(info)
