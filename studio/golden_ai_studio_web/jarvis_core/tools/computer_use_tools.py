"""Computer Use tools for controlled Windows interaction.

The public functions are small, lazy-imported adapters so the Core can still
start on machines without GUI, clipboard, NVIDIA or Ollama support.  Risk and
confirmation are enforced by the central JarvisService SecurityManager when
these functions are registered as Tools.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from ..models import Risk, Tool


_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "golden_jarvis_screenshots"
_DANGEROUS_HOTKEYS = {
    frozenset(("alt", "f4")),
    frozenset(("ctrl", "alt", "delete")),
    frozenset(("win", "l")),
    frozenset(("win", "r")),
    frozenset(("win", "x")),
    frozenset(("ctrl", "shift", "esc")),
    frozenset(("shift", "delete")),
}


def _dependency_error(name: str) -> RuntimeError:
    return RuntimeError(f"Dependência opcional não instalada: {name}")


def _pyautogui():
    try:
        import pyautogui
    except ImportError as exc:
        raise _dependency_error("pyautogui") from exc
    return pyautogui


def _pyperclip():
    try:
        import pyperclip
    except ImportError as exc:
        raise _dependency_error("pyperclip") from exc
    return pyperclip


def _safe_region(region: Optional[Any]) -> Optional[tuple[int, int, int, int]]:
    if region is None:
        return None
    if not isinstance(region, (list, tuple)) or len(region) != 4:
        raise ValueError("region deve conter x, y, largura e altura")
    values = tuple(int(value) for value in region)
    if values[2] <= 0 or values[3] <= 0:
        raise ValueError("largura e altura da região devem ser positivas")
    return values


def mouse_position() -> dict[str, Any]:
    """Retorna a posição atual do mouse sem alterar a interface."""
    try:
        point = _pyautogui().position()
        return {"ok": True, "x": int(point.x), "y": int(point.y)}
    except Exception as exc:
        return {"ok": False, "x": 0, "y": 0, "error": str(exc)}


def mouse_move(x: int, y: int, duration: float = 0.5) -> dict[str, Any]:
    """Move o mouse; a confirmação MEDIUM/HIGH fica no serviço central."""
    try:
        x, y = int(x), int(y)
        duration = max(0.0, min(float(duration), 10.0))
        _pyautogui().moveTo(x, y, duration=duration)
        return {"ok": True, "x": x, "y": y, "duration": duration}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def mouse_click(button: str = "left", clicks: int = 1) -> dict[str, Any]:
    """Clica o mouse; a Tool é HIGH e exige confirmação no serviço central."""
    button = str(button or "left").lower()
    if button not in {"left", "middle", "right"}:
        return {"ok": False, "error": "button inválido"}
    try:
        clicks = max(1, min(int(clicks), 3))
        _pyautogui().click(button=button, clicks=clicks)
        return {"ok": True, "button": button, "clicks": clicks}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def screenshot(region: Optional[Any] = None) -> str:
    """Captura a tela e retorna o caminho PNG gerado."""
    safe_region = _safe_region(region)
    if safe_region is None:
        from ..vision import get_vision
        capture = get_vision().capture_screen()
        if not capture.get("ok"):
            raise RuntimeError(capture.get("error") or "captura indisponível")
        return str(capture["path"])
    image = _pyautogui().screenshot(region=safe_region)
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _SCREENSHOT_DIR / f"jarvis_{time.time_ns()}.png"
    image.save(path, "PNG")
    return str(path)


def keyboard_type(text: str, interval: float = 0.1) -> dict[str, Any]:
    """Digita texto; o serviço classifica como MEDIUM."""
    try:
        value = str(text)
        interval = max(0.0, min(float(interval), 1.0))
        _pyautogui().write(value, interval=interval)
        return {"ok": True, "length": len(value), "interval": interval}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def keyboard_press(key: str) -> dict[str, Any]:
    """Pressiona uma tecla; a Tool é HIGH e exige confirmação."""
    value = str(key or "").strip().lower()
    if not value or len(value) > 30:
        return {"ok": False, "error": "key inválida"}
    try:
        _pyautogui().press(value)
        return {"ok": True, "key": value}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def keyboard_hotkey(*keys: str) -> dict[str, Any]:
    """Pressiona combinação permitida; atalhos destrutivos são bloqueados."""
    values = tuple(str(key or "").strip().lower() for key in keys)
    if not values or any(not key or len(key) > 30 for key in values):
        return {"ok": False, "error": "keys inválidas"}
    if frozenset(values) in _DANGEROUS_HOTKEYS:
        return {"ok": False, "error": "atalho perigoso bloqueado"}
    try:
        _pyautogui().hotkey(*values)
        return {"ok": True, "keys": list(values)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def clipboard_get() -> str:
    """Lê o conteúdo atual da área de transferência."""
    return str(_pyperclip().paste())


def clipboard_set(text: str) -> dict[str, Any]:
    """Escreve na área de transferência; a Tool é HIGH e exige confirmação."""
    value = str(text)
    _pyperclip().copy(value)
    return {"ok": True, "length": len(value)}


def gpu_list() -> list[dict[str, Any]]:
    """Lista GPUs via o provider Windows vendor-neutral."""
    return _windows_gpu_records()


def gpu_status() -> dict[str, Any]:
    """Retorna métricas confiáveis; uso e temperatura desconhecidos ficam nulos."""
    gpus = _windows_gpu_records()
    return {
        "ok": True,
        "available": bool(gpus),
        "vendor": gpus[0].get("vendor") if gpus else None,
        "name": gpus[0].get("name") if gpus else None,
        "usage_percent": None,
        "vram_used": None,
        "vram_total": gpus[0].get("vram_total") if gpus else None,
        "temperature": None,
        "source": "windows_wmi" if gpus else "unavailable",
        "gpus": gpus,
        "reason": None if gpus else "GPU não detectada ou métricas não disponíveis.",
    }


def _gpu_vendor(name: str, vendor: str = "") -> str:
    value = f"{name} {vendor}".casefold()
    if "advanced micro devices" in value or "amd" in value or "radeon" in value:
        return "AMD"
    if "nvidia" in value or "geforce" in value or "quadro" in value:
        return "NVIDIA"
    if "intel" in value or "arc" in value or "uhd graphics" in value:
        return "INTEL"
    return "UNKNOWN"


def _reliable_wmi_vram(value: Any) -> Optional[int]:
    try:
        total = int(value)
    except (TypeError, ValueError):
        return None
    # Win32_VideoController.AdapterRAM is a 32-bit field and commonly caps
    # larger AMD cards near 4 GiB. Do not expose that truncated value.
    if total <= 0 or total >= 0xF0000000:
        return None
    return total


def _windows_gpu_records() -> list[dict[str, Any]]:
    """Read-only WMI/CIM inventory; never invents dynamic GPU metrics."""
    command = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion,PNPDeviceID | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return []
        raw = json.loads(completed.stdout)
        rows = raw if isinstance(raw, list) else [raw]
        records = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not row.get("Name"):
                continue
            total = _reliable_wmi_vram(row.get("AdapterRAM"))
            records.append({
                "index": index,
                "name": str(row.get("Name")),
                "vendor": _gpu_vendor(str(row.get("Name")), str(row.get("PNPDeviceID") or "")),
                "driver": row.get("DriverVersion"),
                "vram_total": total,
                "usage_percent": None,
                "temperature": None,
                "source": "windows_wmi",
            })
        return records
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError):
        return []


def vision_analyze_screen(prompt: str, region: Optional[Any] = None) -> str:
    """Reutiliza o provider local canônico JarvisVision/Ollama."""
    from ..vision import get_vision
    vision = get_vision()
    if region is None:
        result = vision.analyze_screen(str(prompt or "Descreva a tela."))
    else:
        path = screenshot(region)
        with open(path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("ascii")
        result = vision.analyze_image(image_data, str(prompt or "Descreva a tela."))
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "visão indisponível")
    return str(result.get("analysis") or "").strip()


def _screenshot_tool(region=None):
    return {"ok": True, "path": screenshot(region), "source": "computer_use"}


def _clipboard_get_tool():
    return {"ok": True, "text": clipboard_get()}


def _vision_tool(prompt: str, region=None):
    return {"ok": True, "analysis": vision_analyze_screen(prompt, region)}


def _hotkey_tool(keys):
    return keyboard_hotkey(*(keys or []))


COMPUTER_USE_TOOLS = (
    Tool("mouse_position", "Consulta a posição atual do mouse.", mouse_position,
         Risk.LOW, category="computer_use"),
    Tool("mouse_move", "Move o mouse para coordenadas informadas.", mouse_move,
         Risk.MEDIUM, parameters={"x": int, "y": int, "duration": float},
         category="computer_use"),
    Tool("mouse_click", "Clica com o mouse após confirmação.", mouse_click,
         Risk.HIGH, confirmation=True,
         parameters={"button": str, "clicks": int}, category="computer_use"),
    Tool("screenshot", "Captura a tela em PNG.", _screenshot_tool,
         Risk.MEDIUM, parameters={"region": list}, category="computer_use"),
    Tool("keyboard_type", "Digita texto na janela ativa após confirmação.", keyboard_type,
         Risk.HIGH, confirmation=True,
         parameters={"text": str, "interval": float}, category="computer_use"),
    Tool("keyboard_press", "Pressiona uma tecla após confirmação.", keyboard_press,
         Risk.HIGH, confirmation=True, parameters={"key": str}, category="computer_use"),
    Tool("keyboard_hotkey", "Pressiona um atalho após confirmação.", _hotkey_tool,
         Risk.HIGH, confirmation=True, parameters={"keys": list}, category="computer_use"),
    Tool("clipboard_get", "Lê a área de transferência sem registrar seu conteúdo.", _clipboard_get_tool,
         Risk.MEDIUM, category="computer_use"),
    Tool("clipboard_set", "Escreve na área de transferência após confirmação.", clipboard_set,
         Risk.HIGH, confirmation=True, parameters={"text": str}, category="computer_use"),
    Tool("gpu_status", "Consulta uso, memória e temperatura da GPU.", gpu_status,
         Risk.LOW, category="computer_use"),
    Tool("gpu_list", "Lista GPUs NVIDIA disponíveis.", gpu_list,
         Risk.LOW, category="computer_use"),
    Tool("vision_analyze_screen", "Analisa a tela com qwen2.5vl via Ollama.", _vision_tool,
         Risk.MEDIUM, timeout=90, parameters={"prompt": str, "region": list},
         category="computer_use"),
)


__all__ = [
    "COMPUTER_USE_TOOLS", "mouse_position", "mouse_move", "mouse_click", "screenshot",
    "keyboard_type", "keyboard_press", "keyboard_hotkey", "clipboard_get", "clipboard_set",
    "gpu_status", "gpu_list", "vision_analyze_screen",
]
