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
import re
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Any, Optional

from ..models import Risk, Tool


_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "golden_jarvis_screenshots"
_VISUAL_TARGET_TTL_SECONDS = 5
_LAST_VISUAL_TARGET: Optional[dict[str, Any]] = None
_WMI_LOCK = threading.Lock()
VISION_ACTION_SCOPE = "PRIMARY_MONITOR_ONLY"
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


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_response(value: Any) -> Any:
    text = str(value or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        match = re.search(r"\{.*\}|\[.*\]", text, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None


def _capture_for_grounding(region: Optional[Any] = None) -> dict[str, Any]:
    """Capture through the existing JarvisVision provider boundary."""
    from ..vision import get_vision
    vision = get_vision()
    safe_region = _safe_region(region)
    if safe_region is None:
        capture = vision.capture_screen()
    else:
        path = screenshot(list(safe_region))
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
        with open(path, "rb") as image_file:
            png_bytes = image_file.read()
        capture = {"ok": True, "path": path, "png_bytes": png_bytes,
                   "width": width, "height": height}
    if not capture.get("ok"):
        raise RuntimeError(capture.get("error") or "captura indisponível")
    path = Path(str(capture.get("path") or ""))
    png_bytes = capture.get("png_bytes")
    if not png_bytes and path.is_file():
        png_bytes = path.read_bytes()
    if not png_bytes:
        raise RuntimeError("captura sem dados de imagem")
    return {
        "vision": vision,
        "path": path,
        "image": base64.b64encode(png_bytes).decode("ascii"),
        "width": int(capture.get("width") or 0),
        "height": int(capture.get("height") or 0),
        "origin": (safe_region[0], safe_region[1]) if safe_region else (0, 0),
    }


def _local_vision_json(prompt: str, region: Optional[Any] = None) -> tuple[Any, dict[str, Any]]:
    capture = _capture_for_grounding(region)
    try:
        result = capture["vision"].analyze_image(capture["image"], prompt)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "visão local indisponível")
        payload = _parse_json_response(result.get("analysis"))
        if payload is None:
            raise RuntimeError("resposta visual não é JSON estruturado")
        return payload, capture
    finally:
        path = capture.get("path")
        try:
            if path and path.is_file():
                path.unlink()
        except OSError:
            pass


def _box_from_model(raw: Any, coordinate_space: str, width: int, height: int,
                    origin: tuple[int, int]) -> Optional[dict[str, int]]:
    if isinstance(raw, dict):
        if all(key in raw for key in ("x1", "y1", "x2", "y2")):
            values = (raw["x1"], raw["y1"], raw["x2"], raw["y2"])
        elif all(key in raw for key in ("x", "y", "width", "height")):
            values = (raw["x"], raw["y"], raw["x"] + raw["width"], raw["y"] + raw["height"])
        elif isinstance(raw.get("top_left"), (list, tuple)) and isinstance(
                raw.get("bottom_right"), (list, tuple)):
            top_left, bottom_right = raw["top_left"], raw["bottom_right"]
            if len(top_left) != 2 or len(bottom_right) != 2:
                return None
            values = (top_left[0], top_left[1], bottom_right[0], bottom_right[1])
        else:
            return None
    elif isinstance(raw, (list, tuple)) and len(raw) == 4:
        values = tuple(raw)
    else:
        return None
    try:
        values = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(value == value and abs(value) != float("inf") for value in values):
        return None
    if coordinate_space.casefold() in {"normalized", "relative", "0-1"}:
        values = (values[0] * width, values[1] * height,
                  values[2] * width, values[3] * height)
    values = (values[0] + origin[0], values[1] + origin[1],
              values[2] + origin[0], values[3] + origin[1])
    x1, y1, x2, y2 = (round(value) for value in values)
    if width <= 0 or height <= 0 or not (0 <= x1 < x2 <= width + origin[0]
                                         and 0 <= y1 < y2 <= height + origin[1]):
        return None
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _center(box: dict[str, int]) -> dict[str, int]:
    return {"x": round((box["x1"] + box["x2"]) / 2),
            "y": round((box["y1"] + box["y2"]) / 2)}


def _model_confidence(payload: dict[str, Any]) -> Optional[float]:
    value = payload.get("confidence")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def is_visual_target_fresh(target: Optional[dict[str, Any]], now: Optional[float] = None) -> bool:
    """Return whether a visual target is still within the short safety TTL."""
    if not target:
        return False
    now = time.time() if now is None else float(now)
    age = now - float(target.get("timestamp_epoch", 0))
    return 0 <= age <= _VISUAL_TARGET_TTL_SECONDS


def last_visual_target() -> Optional[dict[str, Any]]:
    target = dict(_LAST_VISUAL_TARGET or {})
    return target if is_visual_target_fresh(target) else None


def visual_coordinate_capability() -> dict[str, Any]:
    """Report the conservative coordinate contract used by visual grounding."""
    return {
        "process_dpi_aware": "PARTIAL",
        "screenshot_coordinate_space": "screen_image_pixels",
        "pyautogui_coordinate_space": "physical_screen_pixels",
        "match": "ONLY_AT_100_PERCENT",
        "dpi_mapping_verified": False,
        "multi_monitor_scope": VISION_ACTION_SCOPE,
    }


def validate_visual_target_for_action(
    target: Optional[dict[str, Any]],
    *,
    current_screen_size: Optional[tuple[int, int]] = None,
    current_active_window: Optional[str] = None,
    dpi_mapping_validated: bool = False,
    monitor: str = "primary",
) -> dict[str, Any]:
    """Validate a target before a future action; this helper never performs one."""
    if not isinstance(target, dict) or not target.get("found"):
        return {"valid": False, "reason": "target_not_found"}
    if not is_visual_target_fresh(target):
        return {"valid": False, "reason": "stale_target"}
    confidence = _model_confidence(target)
    if confidence is None or confidence < 0.8:
        return {"valid": False, "reason": "LOW_CONFIDENCE"}
    if target.get("confidence_source") != "model_reported":
        return {"valid": False, "reason": "confidence_source_unverified"}
    if str(monitor).casefold() != "primary":
        return {"valid": False, "reason": "unsupported_monitor"}
    if str(target.get("monitor_scope") or VISION_ACTION_SCOPE).casefold() != "primary_monitor_only":
        return {"valid": False, "reason": "unsupported_monitor"}
    if not dpi_mapping_validated:
        return {"valid": False, "reason": "dpi_mapping_unverified"}
    width, height = int(target.get("screen_width") or 0), int(target.get("screen_height") or 0)
    if current_screen_size is not None:
        try:
            current_width, current_height = (int(current_screen_size[0]), int(current_screen_size[1]))
        except (TypeError, ValueError, IndexError):
            return {"valid": False, "reason": "screen_dimensions_invalid"}
        if (current_width, current_height) != (width, height):
            return {"valid": False, "reason": "screen_dimensions_changed"}
    if width <= 0 or height <= 0:
        return {"valid": False, "reason": "screen_dimensions_invalid"}
    box = target.get("bounding_box")
    if not isinstance(box, dict):
        return {"valid": False, "reason": "bounding_box_invalid"}
    try:
        x1, y1, x2, y2 = (int(box[key]) for key in ("x1", "y1", "x2", "y2"))
    except (KeyError, TypeError, ValueError):
        return {"valid": False, "reason": "bounding_box_invalid"}
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        return {"valid": False, "reason": "target_out_of_bounds"}
    center = target.get("center") or _center({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    try:
        center_x, center_y = int(center["x"]), int(center["y"])
    except (KeyError, TypeError, ValueError):
        return {"valid": False, "reason": "center_invalid"}
    if not (0 <= center_x < width and 0 <= center_y < height):
        return {"valid": False, "reason": "center_out_of_bounds"}
    if current_active_window is not None and target.get("active_window"):
        if str(target["active_window"]) != str(current_active_window):
            return {"valid": False, "reason": "active_window_changed"}
    return {
        "valid": True,
        "reason": None,
        "monitor_scope": VISION_ACTION_SCOPE,
        "dpi_mapping_validated": True,
        "center": {"x": center_x, "y": center_y},
    }


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
    if not gpus:
        return {
            "ok": True,
            "available": False,
            "vendor": None,
            "name": None,
            "usage_percent": None,
            "vram_used": None,
            "vram_total": None,
            "temperature": None,
            "source": "unavailable",
            "status": "UNAVAILABLE",
            "reason": "wmi_unavailable",
            "gpus": [],
        }
    return {
        "ok": True,
        "available": True,
        "vendor": gpus[0].get("vendor"),
        "name": gpus[0].get("name"),
        "usage_percent": None,
        "vram_used": None,
        "vram_total": gpus[0].get("vram_total"),
        "temperature": None,
        "source": "windows_wmi",
        "status": "PARTIAL",
        "reason": "dynamic_metrics_unavailable",
        "gpus": gpus,
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


def _run_powershell_json(command: str, timeout: float = 5.0) -> Optional[str]:
    """Run a bounded WMI command without subprocess reader threads."""
    args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with _WMI_LOCK:
        with tempfile.TemporaryFile(mode="w+b") as stdout:
            process = subprocess.Popen(
                args,
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


def _windows_gpu_records() -> list[dict[str, Any]]:
    """Read-only WMI/CIM inventory; never invents dynamic GPU metrics."""
    command = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion,PNPDeviceID | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw_text = _run_powershell_json(command)
        if not raw_text or not raw_text.strip():
            return []
        raw = json.loads(raw_text)
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


def vision_describe_screen(prompt: str = "", region: Optional[Any] = None) -> dict[str, Any]:
    """Return a structured description from the local vision provider only."""
    request = (
        "Responda SOMENTE em JSON válido com este formato: "
        '{"description":"texto conciso"}. '
        "Não inclua coordenadas nem instruções de ação. " + str(prompt or "Descreva a tela.")
    )
    payload, capture = _local_vision_json(request, region)
    description = payload.get("description") if isinstance(payload, dict) else None
    if not description and isinstance(payload, dict):
        description = payload.get("text") or payload.get("analysis")
    if not description:
        raise RuntimeError("descrição visual vazia")
    return {"description": str(description),
            "screen_size": {"width": capture["width"], "height": capture["height"]},
            "timestamp": _timestamp(), "source": "local_vision",
            "model": getattr(capture["vision"], "model", "qwen2.5vl:7b")}


def vision_find_element(target: str, region: Optional[Any] = None,
                        context: str = "") -> dict[str, Any]:
    """Locate an element without clicking or returning an unsafe coordinate."""
    request = (
        "Responda SOMENTE em JSON válido. Localize o alvo visual abaixo na imagem. "
        "Use bounding_box com x1,y1,x2,y2, coordinate_space='pixel' ou 'normalized', "
        "found boolean, label e confidence apenas se houver score reportado pelo modelo. "
        "Se não tiver certeza, use found=false. Alvo: " + str(target) +
        (" Contexto: " + str(context) if context else "")
    )
    payload, capture = _local_vision_json(request, region)
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), None)
    if not isinstance(payload, dict):
        return {"found": False, "target": target, "reason": "resposta visual inválida"}
    confidence = _model_confidence(payload)
    confidence_source = "model_reported" if confidence is not None else None
    if not payload.get("found", False):
        return {"found": False, "target": target,
                "reason": str(payload.get("reason") or "elemento não localizado"),
                **({"confidence": confidence, "confidence_source": confidence_source}
                   if confidence is not None else {})}
    if confidence is None:
        return {"found": False, "target": target,
                "reason": "confidence_unavailable", "confidence_source": "unavailable"}
    box = _box_from_model(payload.get("bounding_box"),
                          str(payload.get("coordinate_space") or "pixel"),
                          capture["width"], capture["height"], capture["origin"])
    if box is None:
        return {"found": False, "target": target, "reason": "bounding_box_invalid",
                "confidence": confidence, "confidence_source": confidence_source}
    if confidence < 0.8:
        return {"found": False, "target": target, "reason": "LOW_CONFIDENCE",
                "confidence": confidence, "confidence_source": confidence_source}
    result = {"found": True, "target": target,
              "label": str(payload.get("label") or target), "bounding_box": box,
              "center": _center(box), "confidence": confidence,
              "confidence_source": confidence_source,
              "screen_width": capture["width"], "screen_height": capture["height"],
              "coordinate_space": "screen_image_pixels",
              "monitor_scope": VISION_ACTION_SCOPE,
              "dpi_mapping_validated": False,
              "source": getattr(capture["vision"], "model", "qwen2.5vl:7b"),
              "timestamp": _timestamp()}
    global _LAST_VISUAL_TARGET
    result["timestamp_epoch"] = time.time()
    _LAST_VISUAL_TARGET = dict(result)
    return result


def vision_list_elements(region: Optional[Any] = None, context: str = "") -> dict[str, Any]:
    """List only model-reported, high-confidence visible UI elements."""
    request = (
        "Responda SOMENTE em JSON válido como {\"elements\":[...]}. Liste no máximo "
        "20 elementos UI relevantes (button, input, menu, tab, window ou label). "
        "Cada elemento deve conter type, label, bounding_box, coordinate_space e "
        "confidence reportado pelo modelo. Não invente elementos ou confiança. "
        + ("Contexto: " + str(context) if context else "")
    )
    payload, capture = _local_vision_json(request, region)
    raw_elements = payload.get("elements", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_elements, list):
        return {"elements": [], "reason": "resposta visual inválida",
                "timestamp": _timestamp(), "source": "local_vision"}
    elements = []
    for item in raw_elements[:20]:
        if not isinstance(item, dict):
            continue
        confidence = _model_confidence(item)
        box = _box_from_model(item.get("bounding_box"),
                              str(item.get("coordinate_space") or "pixel"),
                              capture["width"], capture["height"], capture["origin"])
        if confidence is None or box is None or confidence < 0.8:
            continue
        elements.append({"type": str(item.get("type") or "label"),
                         "label": str(item.get("label") or ""),
                         "bounding_box": box, "center": _center(box),
                         "confidence": confidence,
                         "confidence_source": "model_reported"})
    return {"elements": elements, "timestamp": _timestamp(),
            "source": "local_vision",
            "model": getattr(capture["vision"], "model", "qwen2.5vl:7b")}


def _screenshot_tool(region=None):
    return {"ok": True, "path": screenshot(region), "source": "computer_use"}


def _clipboard_get_tool():
    return {"ok": True, "text": clipboard_get()}


def _vision_tool(prompt: str, region=None):
    return {"ok": True, "analysis": vision_analyze_screen(prompt, region)}


def _vision_describe_tool(prompt="", region=None):
    return {"ok": True, **vision_describe_screen(prompt, region)}


def _vision_find_tool(target: str, region=None, context=""):
    return {"ok": True, **vision_find_element(target, region, context)}


def _vision_list_tool(region=None, context=""):
    return {"ok": True, **vision_list_elements(region, context)}


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
    Tool("vision_describe_screen", "Descreve a tela com visão local estruturada.",
         _vision_describe_tool, Risk.MEDIUM, timeout=90,
         parameters={"prompt": str, "region": list}, category="computer_use"),
    Tool("vision_find_element", "Localiza um elemento visual sem clicar.",
         _vision_find_tool, Risk.MEDIUM, timeout=90,
         parameters={"target": str, "region": list, "context": str},
         category="computer_use"),
    Tool("vision_list_elements", "Lista elementos visuais reportados com alta confiança.",
         _vision_list_tool, Risk.MEDIUM, timeout=90,
         parameters={"region": list, "context": str}, category="computer_use"),
)


__all__ = [
    "COMPUTER_USE_TOOLS", "mouse_position", "mouse_move", "mouse_click", "screenshot",
    "keyboard_type", "keyboard_press", "keyboard_hotkey", "clipboard_get", "clipboard_set",
    "gpu_status", "gpu_list", "vision_analyze_screen", "vision_describe_screen",
    "vision_find_element", "vision_list_elements", "is_visual_target_fresh",
    "last_visual_target", "visual_coordinate_capability",
    "validate_visual_target_for_action",
]
