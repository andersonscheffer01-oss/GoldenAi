"""Read-only Windows UI Automation grounding.

The module deliberately stops at discovery.  It never invokes a UI control;
future action code must validate the short-lived snapshot and use the central
SecurityManager before calling the existing mouse/keyboard tools.
"""
from __future__ import annotations

import ctypes
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..models import Risk, Tool


_UIA_TARGET_TTL_SECONDS = 5
_MAX_TREE_NODES = 500
_MAX_TREE_DEPTH = 6
_RELEVANT_CONTROL_TYPES = {
    "button", "menuitem", "edit", "combobox", "checkbox", "radiobutton",
    "tabitem", "hyperlink", "document",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dependency_error() -> RuntimeError:
    return RuntimeError("Dependência opcional não instalada: pywinauto")


def _desktop():
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise _dependency_error() from exc
    return Desktop(backend="uia")


def _foreground_handle() -> int:
    if os.name != "nt":
        return 0
    try:
        return int(ctypes.windll.user32.GetForegroundWindow())
    except (AttributeError, OSError):
        return 0


def _window_pid(handle: int) -> int:
    if not handle or os.name != "nt":
        return 0
    try:
        pid = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        return int(pid.value)
    except (AttributeError, OSError):
        return 0


def _process_name(pid: int) -> str:
    if not pid:
        return ""
    try:
        import psutil
        return str(psutil.Process(pid).name())
    except Exception:
        return ""


def _safe_call(wrapper: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(wrapper, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _bounds(rect: Any) -> Optional[dict[str, int]]:
    try:
        left, top = int(rect.left), int(rect.top)
        right, bottom = int(rect.right), int(rect.bottom)
    except (AttributeError, TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def _box(bounds: Optional[dict[str, int]]) -> Optional[dict[str, int]]:
    if not bounds:
        return None
    return {"x1": bounds["x"], "y1": bounds["y"],
            "x2": bounds["x"] + bounds["width"],
            "y2": bounds["y"] + bounds["height"]}


def _center(box: dict[str, int]) -> dict[str, int]:
    return {"x": round((box["x1"] + box["x2"]) / 2),
            "y": round((box["y1"] + box["y2"]) / 2)}


def _element_info(wrapper: Any) -> Any:
    return getattr(wrapper, "element_info", None)


def _element_name(wrapper: Any) -> str:
    info = _element_info(wrapper)
    return str(getattr(info, "name", "") or _safe_call(wrapper, "window_text", "") or "")


def _control_type(wrapper: Any) -> str:
    info = _element_info(wrapper)
    value = getattr(info, "control_type", "")
    if value:
        return str(value)
    return str(_safe_call(wrapper, "friendly_class_name", "") or "")


def _automation_id(wrapper: Any) -> str:
    info = _element_info(wrapper)
    return str(getattr(info, "automation_id", "") or "")


def _class_name(wrapper: Any) -> str:
    info = _element_info(wrapper)
    return str(getattr(info, "class_name", "") or "")


def _runtime_id(wrapper: Any) -> Optional[tuple[Any, ...]]:
    value = getattr(_element_info(wrapper), "runtime_id", None)
    try:
        value = value() if callable(value) else value
        return tuple(value) if value else None
    except Exception:
        return None


def _window_wrapper(window: Optional[Any] = None):
    desktop = _desktop()
    if isinstance(window, int):
        return desktop.window(handle=window)
    if isinstance(window, str) and window.strip():
        wanted = window.strip().casefold()
        for candidate in desktop.windows(top_level_only=True):
            title = str(_safe_call(candidate, "window_text", "") or "")
            if wanted in title.casefold():
                return candidate
        return None
    handle = _foreground_handle()
    return desktop.window(handle=handle) if handle else None


def _window_record(wrapper: Any) -> dict[str, Any]:
    handle = int(_safe_call(wrapper, "handle", 0) or 0)
    pid = int(_safe_call(wrapper, "process_id", 0) or 0)
    bounds = _bounds(_safe_call(wrapper, "rectangle", None))
    title = str(_safe_call(wrapper, "window_text", "") or _element_name(wrapper))
    return {
        "title": title,
        "process_name": _process_name(pid),
        "pid": pid,
        "handle": handle,
        "bounds": bounds,
        "backend": "uia",
        "timestamp": _timestamp(),
        "timestamp_epoch": time.time(),
    }


def ui_active_window() -> dict[str, Any]:
    """Return metadata for the foreground window without reading its content."""
    try:
        wrapper = _window_wrapper()
        if wrapper is None:
            return {"found": False, "reason": "active_window_unavailable", "backend": "uia"}
        result = _window_record(wrapper)
        result["found"] = bool(result["handle"] or result["title"])
        return result
    except Exception as exc:
        return {"found": False, "reason": str(exc)[:200], "backend": "uia"}


def _children(wrapper: Any) -> list[Any]:
    try:
        return list(wrapper.children())
    except Exception:
        return []


def _walk(root: Any):
    queue = deque([(root, 0)])
    seen = 0
    while queue and seen < _MAX_TREE_NODES:
        wrapper, depth = queue.popleft()
        seen += 1
        yield wrapper
        if depth >= _MAX_TREE_DEPTH:
            continue
        queue.extend((child, depth + 1) for child in _children(wrapper))


def _matches(wrapper: Any, target: str, control_type: Optional[str]) -> tuple[int, str]:
    wanted = str(target or "").strip().casefold()
    if not wanted:
        return (999, "")
    actual_type = _control_type(wrapper)
    if control_type and actual_type.casefold() != str(control_type).casefold():
        return (999, actual_type)
    values = (_element_name(wrapper), _automation_id(wrapper), _class_name(wrapper))
    ranks = []
    for value in values:
        normalized = str(value or "").strip().casefold()
        if normalized == wanted:
            ranks.append(0)
        elif wanted in normalized:
            ranks.append(1)
    return (min(ranks) if ranks else 999, actual_type)


def _element_record(wrapper: Any, window: dict[str, Any]) -> Optional[dict[str, Any]]:
    bounds = _bounds(_safe_call(wrapper, "rectangle", None))
    box = _box(bounds)
    if box is None:
        return None
    return {
        "found": True,
        "label": _element_name(wrapper),
        "control_type": _control_type(wrapper),
        "automation_id": _automation_id(wrapper),
        "bounds": box,
        "center": _center(box),
        "coordinate_space": "screen_pixels",
        "coordinate_mapping_verified": False,
        "enabled": bool(_safe_call(wrapper, "is_enabled", False)),
        "visible": bool(_safe_call(wrapper, "is_visible", False)),
        "window_title": window["title"],
        "process_name": window["process_name"],
        "pid": window["pid"],
        "handle": window["handle"],
        "identity": _runtime_id(wrapper),
        "source": "windows_uia",
        "backend": "uia",
        "timestamp": _timestamp(),
        "timestamp_epoch": time.time(),
    }


def _find_with_wrapper(target: str, control_type: Optional[str] = None,
                       window: Optional[Any] = None):
    root = _window_wrapper(window)
    if root is None:
        return None, {"found": False, "reason": "window_not_found", "source": "windows_uia"}
    window_info = _window_record(root)
    candidates = []
    for wrapper in _walk(root):
        rank, actual_type = _matches(wrapper, target, control_type)
        if rank < 999:
            record = _element_record(wrapper, window_info)
            if record:
                candidates.append((rank, record, wrapper))
    if not candidates:
        return None, {"found": False, "reason": "element_not_found", "source": "windows_uia",
                      "window_title": window_info["title"]}
    candidates.sort(key=lambda item: item[0])
    _, record, wrapper = candidates[0]
    return wrapper, record


def ui_find_element(target: str, control_type: Optional[str] = None,
                    window: Optional[Any] = None) -> dict[str, Any]:
    """Find one accessible control using bounded UIA tree traversal."""
    try:
        _, result = _find_with_wrapper(target, control_type, window)
        return result
    except Exception as exc:
        return {"found": False, "reason": str(exc)[:200], "source": "windows_uia"}


def ui_list_elements(window: Optional[Any] = None, limit: int = 50) -> dict[str, Any]:
    """List a bounded set of relevant accessible controls."""
    try:
        root = _window_wrapper(window)
        if root is None:
            return {"found": False, "elements": [], "reason": "window_not_found",
                    "source": "windows_uia"}
        window_info = _window_record(root)
        elements = []
        safe_limit = max(1, min(int(limit), 100))
        for wrapper in _walk(root):
            if _control_type(wrapper).casefold() not in _RELEVANT_CONTROL_TYPES:
                continue
            record = _element_record(wrapper, window_info)
            if record:
                elements.append(record)
            if len(elements) >= safe_limit:
                break
        return {"found": True, "window": window_info, "elements": elements,
                "source": "windows_uia", "timestamp": _timestamp()}
    except Exception as exc:
        return {"found": False, "elements": [], "reason": str(exc)[:200],
                "source": "windows_uia"}


def _is_protected(wrapper: Any, record: dict[str, Any]) -> bool:
    try:
        if bool(_safe_call(wrapper, "is_password", False)):
            return True
    except Exception:
        pass
    values = " ".join((record.get("control_type", ""), record.get("automation_id", ""),
                       record.get("label", ""))).casefold()
    return "password" in values or "senha" in values


def ui_get_element_text(target: str, control_type: Optional[str] = None,
                        window: Optional[Any] = None) -> dict[str, Any]:
    """Read text from a non-protected UIA element, never from password fields."""
    try:
        wrapper, result = _find_with_wrapper(target, control_type, window)
        if wrapper is None:
            return result
        if _is_protected(wrapper, result):
            return {**result, "protected": True, "text": None}
        text = str(_safe_call(wrapper, "window_text", "") or result.get("label") or "")
        return {**result, "protected": False, "text": text}
    except Exception as exc:
        return {"found": False, "reason": str(exc)[:200], "source": "windows_uia"}


def validate_ui_target(target: Optional[dict[str, Any]], now: Optional[float] = None,
                       coordinate_mapping_validated: bool = False) -> dict[str, Any]:
    """Validate a UIA snapshot before any future action is considered."""
    if not isinstance(target, dict) or not target.get("found"):
        return {"valid": False, "reason": "target_not_found"}
    now = time.time() if now is None else float(now)
    age = now - float(target.get("timestamp_epoch", 0))
    if age < 0 or age > _UIA_TARGET_TTL_SECONDS:
        return {"valid": False, "reason": "stale_target"}
    if not coordinate_mapping_validated:
        return {"valid": False, "reason": "coordinate_mapping_unverified"}
    handle = int(target.get("handle") or 0)
    if not handle or not _window_exists(handle):
        return {"valid": False, "reason": "window_gone"}
    current_pid = _window_pid(handle)
    if target.get("pid") and current_pid != int(target["pid"]):
        return {"valid": False, "reason": "process_changed"}
    wrapper, current = _find_with_wrapper(
        target.get("label", ""), target.get("control_type"), handle)
    if wrapper is None or not current.get("found"):
        return {"valid": False, "reason": "element_gone"}
    if not current.get("enabled") or not current.get("visible"):
        return {"valid": False, "reason": "element_not_actionable"}
    return {"valid": True, "reason": None, "source": "windows_uia"}


def _window_exists(handle: int) -> bool:
    if os.name != "nt":
        return bool(handle)
    try:
        return bool(ctypes.windll.user32.IsWindow(handle))
    except (AttributeError, OSError):
        return False


def _vision_find(target: str) -> dict[str, Any]:
    try:
        from .computer_use_tools import vision_find_element
        return vision_find_element(target)
    except Exception as exc:
        return {"found": False, "reason": str(exc)[:200], "source": "local_vision"}


def _vision_box(result: dict[str, Any]) -> Optional[dict[str, int]]:
    return result.get("bounding_box") if isinstance(result, dict) else None


def _boxes_agree(uia: dict[str, Any], vision: dict[str, Any]) -> bool:
    uia_box = uia.get("bounds") or {}
    vision_box = _vision_box(vision) or {}
    try:
        ux = (int(uia_box["x1"]) + int(uia_box["x2"])) / 2
        uy = (int(uia_box["y1"]) + int(uia_box["y2"])) / 2
        vx = (int(vision_box["x1"]) + int(vision_box["x2"])) / 2
        vy = (int(vision_box["y1"]) + int(vision_box["y2"])) / 2
    except (KeyError, TypeError, ValueError):
        return False
    return abs(ux - vx) <= 100 and abs(uy - vy) <= 100


def hybrid_find_ui_target(target: str, control_type: Optional[str] = None,
                          window: Optional[Any] = None,
                          vision_result: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Prefer UIA, fall back to local vision, and block source conflicts."""
    uia_result = ui_find_element(target, control_type, window)
    if uia_result.get("found"):
        if vision_result is not None and vision_result.get("found"):
            if not _boxes_agree(uia_result, vision_result):
                return {"found": False, "status": "AMBIGUOUS",
                        "reason": "uia_vision_conflict", "auto_action": "BLOCKED",
                        "uia": uia_result, "vision": vision_result}
            return {**uia_result, "status": "AGREE", "selection_reason": "windows_uia_priority",
                    "vision_source": vision_result.get("source")}
        return {**uia_result, "status": "FOUND", "selection_reason": "windows_uia_priority"}
    vision = vision_result if vision_result is not None else _vision_find(target)
    if vision.get("found"):
        return {**vision, "status": "FOUND", "selection_reason": "vision_fallback",
                "source": "local_vision_fallback"}
    return {"found": False, "status": "NOT_FOUND",
            "reason": vision.get("reason") or uia_result.get("reason") or "not_found",
            "uia": uia_result, "vision": vision}


def _ui_active_window_tool():
    return ui_active_window()


def _ui_find_element_tool(target: str, control_type: Optional[str] = None,
                          window: Optional[Any] = None):
    return ui_find_element(target, control_type, window)


def _ui_list_elements_tool(window: Optional[Any] = None, limit: int = 50):
    return ui_list_elements(window, limit)


def _ui_get_text_tool(target: str, control_type: Optional[str] = None,
                      window: Optional[Any] = None):
    return ui_get_element_text(target, control_type, window)


def _hybrid_find_tool(target: str, control_type: Optional[str] = None,
                      window: Optional[Any] = None):
    return hybrid_find_ui_target(target, control_type, window)


UI_AUTOMATION_TOOLS = (
    Tool("ui_active_window", "Consulta a janela ativa via Windows UIA.",
         _ui_active_window_tool, Risk.LOW, category="computer_use"),
    Tool("ui_find_element", "Localiza um controle acessível via Windows UIA.",
         _ui_find_element_tool, Risk.LOW,
         parameters={"target": str, "control_type": str, "window": str},
         category="computer_use"),
    Tool("ui_list_elements", "Lista controles acessíveis relevantes da janela.",
         _ui_list_elements_tool, Risk.LOW,
         parameters={"window": str, "limit": int}, category="computer_use"),
    Tool("ui_get_element_text", "Lê texto de controle UIA não protegido.",
         _ui_get_text_tool, Risk.MEDIUM,
         parameters={"target": str, "control_type": str, "window": str},
         category="computer_use"),
    Tool("hybrid_find_ui_target", "Busca UIA primeiro e usa visão local como fallback.",
         _hybrid_find_tool, Risk.MEDIUM,
         parameters={"target": str, "control_type": str, "window": str},
         category="computer_use"),
)


__all__ = [
    "UI_AUTOMATION_TOOLS", "ui_active_window", "ui_find_element",
    "ui_list_elements", "ui_get_element_text", "validate_ui_target",
    "hybrid_find_ui_target",
]
