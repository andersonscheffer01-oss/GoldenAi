from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - exercised when psutil is absent locally
    psutil = None


def _http_json(url: str, timeout: float = 3.0) -> tuple[str, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read(2_000_000).decode("utf-8", errors="replace")
        try:
            return "ativo", json.loads(raw)
        except json.JSONDecodeError:
            return "ativo", None
    except urllib.error.URLError:
        return "inativo", None
    except Exception:
        return "erro", None


def check_ollama(base_url: str = "http://127.0.0.1:11434") -> dict:
    status, data = _http_json(base_url.rstrip("/") + "/api/tags")
    models = []
    if isinstance(data, dict):
        for item in data.get("models", []):
            if isinstance(item, dict) and item.get("name"):
                models.append(str(item["name"]))
    return {
        "status": status,
        "qwen2_5vl_disponivel": any(name.startswith("qwen2.5vl:7b") for name in models),
        "modelos": models,
    }


def check_jarvis(server_url: str = "http://127.0.0.1:8780") -> str:
    status, data = _http_json(server_url.rstrip("/") + "/api/health")
    if status == "ativo" and isinstance(data, dict) and data.get("status") == "ok":
        return "ativo"
    return status


def check_mt5() -> str:
    if psutil is None:
        return "verificar"
    names = {"terminal64.exe", "terminal.exe", "metatrader.exe", "metatrader 5.exe"}
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
        except Exception:
            continue
        if name in names:
            return "ativo"
    return "inativo"


def system_status(server_url: str = "http://127.0.0.1:8780", agent_version: str = "0.1.0") -> dict:
    disk = shutil.disk_usage(Path(os.getenv("SystemDrive", "C:") + "\\"))
    if psutil is not None:
        cpu = float(psutil.cpu_percent(interval=0.1))
        mem = psutil.virtual_memory()
        uptime = int(time.time() - psutil.boot_time())
        memory_total_gb = round(mem.total / (1024 ** 3), 2)
        memory_percent = float(mem.percent)
    else:
        cpu = 0.0
        uptime = 0
        memory_total_gb = 0.0
        memory_percent = 0.0
    ollama = check_ollama()
    return {
        "nome_computador": socket.gethostname(),
        "sistema_operacional": platform.system() or "Windows",
        "cpu_percentual": cpu,
        "memoria_total_gb": memory_total_gb,
        "memoria_percentual": memory_percent,
        "disco_livre_gb": round(disk.free / (1024 ** 3), 2),
        "tempo_ligado_segundos": uptime,
        "versao_agente": agent_version,
        "ollama": ollama["status"],
        "qwen2_5vl_disponivel": ollama["qwen2_5vl_disponivel"],
        "jarvis": check_jarvis(server_url),
        "mt5": check_mt5(),
    }
