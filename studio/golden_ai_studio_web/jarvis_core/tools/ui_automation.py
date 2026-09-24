"""Read-only Windows UI Automation grounding.

The module deliberately stops at discovery.  It never invokes a UI control;
future action code must validate the short-lived snapshot and use the central
SecurityManager before calling the existing mouse/keyboard tools.
"""
from __future__ import annotations

import ctypes
import hashlib
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
_PATH_NOT_FOUND_MARKERS = (
    "caminho especificado", "path specified", "cannot find the path",
    "sistema não pode encontrar",
)


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
            pid = int(_safe_call(candidate, "process_id", 0) or 0)
            process = _process_name(pid)
            if wanted in title.casefold() or wanted in process.casefold():
                return candidate
        return None
    handle = _foreground_handle()
    return desktop.window(handle=handle) if handle else None


def _window_wrapper_for_process(window: Optional[Any], process_id: int):
    """Resolve a top-level UIA window only within the requested process."""
    desktop = _desktop()
    wanted = str(window or "").strip().casefold()
    for candidate in desktop.windows(top_level_only=True):
        pid = int(_safe_call(candidate, "process_id", 0) or 0)
        if pid != int(process_id):
            continue
        if not wanted:
            return candidate
        title = str(_safe_call(candidate, "window_text", "") or "")
        process = _process_name(pid)
        if wanted in title.casefold() or wanted in process.casefold():
            return candidate
    return None


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


def _activate_window_handle(handle: int) -> bool:
    """Activate one already-grounded window handle through the Win32 focus path."""
    if not handle:
        return False
    try:
        user32 = ctypes.windll.user32
        foreground = int(user32.GetForegroundWindow() or 0)
        current_thread = int(user32.GetCurrentThreadId())
        target_pid = ctypes.c_ulong(0)
        target_thread = int(user32.GetWindowThreadProcessId(
            ctypes.c_void_p(handle), ctypes.byref(target_pid)) or 0)
        foreground_pid = ctypes.c_ulong(0)
        foreground_thread = int(user32.GetWindowThreadProcessId(
            ctypes.c_void_p(foreground), ctypes.byref(foreground_pid)) or 0)
        attached = []
        for thread_id in (foreground_thread, target_thread):
            if thread_id and thread_id != current_thread and thread_id not in attached:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        try:
            user32.ShowWindow(ctypes.c_void_p(handle), 9)  # SW_RESTORE
            user32.BringWindowToTop(ctypes.c_void_p(handle))
            user32.SetForegroundWindow(ctypes.c_void_p(handle))
        finally:
            for thread_id in reversed(attached):
                user32.AttachThreadInput(current_thread, thread_id, False)
        return int(user32.GetForegroundWindow() or 0) == int(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


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


def _control_value(wrapper: Any) -> str:
    """Read an editor value through the UIA value pattern when available."""
    for name in ("get_value", "window_text"):
        value = _safe_call(wrapper, name, None)
        if value is not None and str(value) != "":
            return str(value)
    try:
        pattern = wrapper.get_value_pattern()
        value = getattr(pattern, "value", "")
        return str(value() if callable(value) else value or "")
    except Exception:
        return ""


def _editor_candidates(root: Any, window_info: dict[str, Any]):
    candidates = []
    for wrapper in _walk(root):
        control_type = _control_type(wrapper).casefold()
        if control_type not in {"edit", "document"}:
            continue
        record = _element_record(wrapper, window_info)
        if not record or not record.get("enabled") or not record.get("visible"):
            continue
        if _is_protected(wrapper, record):
            continue
        text = _control_value(wrapper)
        # A document control is preferred to a generic edit control.  Among
        # equal controls, the largest visible editor is the least ambiguous.
        area = (record["bounds"]["x2"] - record["bounds"]["x1"]) * (
            record["bounds"]["y2"] - record["bounds"]["y1"])
        priority = 0 if control_type == "document" else 1
        candidates.append((priority, -area, record, wrapper, text))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates


def _path_not_found_dialog(root: Any) -> tuple[Optional[Any], Optional[Any]]:
    """Find the exact Windows path dialog and its nearby OK control."""
    marker_seen = False
    marker_wrapper = None
    ok_wrapper = None
    for wrapper in _walk(root):
        if not _safe_call(wrapper, "is_visible", False):
            continue
        name = _element_name(wrapper).casefold()
        if any(marker in name for marker in _PATH_NOT_FOUND_MARKERS):
            marker_seen = True
            marker_wrapper = wrapper
            continue
        if marker_seen and name.strip().casefold() == "ok":
            ok_wrapper = wrapper
            # Windows 11 Notepad exposes the clickable Button and a nested
            # TextBlock with the same label.  Prefer the clickable parent.
            if _control_type(wrapper).casefold() == "text":
                try:
                    parent = wrapper.parent()
                    if (_element_name(parent).strip().casefold() == "ok" and
                            _control_type(parent).casefold() == "button"):
                        ok_wrapper = parent
                except Exception:
                    pass
            break
    return marker_wrapper, ok_wrapper


def _editor_record(record: dict[str, Any], text: str) -> dict[str, Any]:
    identity = record.get("identity")
    identity_text = repr(identity)
    content_state_id = hashlib.sha256(
        (f"{record.get('handle')}|{identity_text}|{text}").encode("utf-8")
    ).hexdigest()[:24]
    return {
        **record,
        "text": text,
        "document_identity": identity_text,
        "content_state_id": content_state_id,
    }


def ui_read_editor(window: Optional[Any] = None,
                   expected_process: str = "") -> dict[str, Any]:
    """Resolve and read the active app's visible editor/document control."""
    try:
        root = _window_wrapper(window)
        if root is None:
            return {"found": False, "verified": False, "reason": "window_not_found",
                    "source": "windows_uia"}
        window_info = _window_record(root)
        wanted_process = str(expected_process or "").casefold()
        actual_process = str(window_info.get("process_name") or "").casefold()
        if wanted_process and wanted_process not in actual_process:
            return {"found": False, "verified": False,
                    "reason": "process_mismatch", "window": window_info,
                    "source": "windows_uia"}
        marker, _ = _path_not_found_dialog(root)
        if marker is not None:
            return {"found": False, "verified": False,
                    "reason": "path_not_found_dialog", "path_error_dialog": True,
                    "window": window_info, "source": "windows_uia"}
        candidates = _editor_candidates(root, window_info)
        if not candidates:
            return {"found": False, "verified": False,
                    "reason": "editor_not_found", "window": window_info,
                    "source": "windows_uia"}
        _, _, record, _, text = candidates[0]
        editor = _editor_record(record, text)
        return {"found": True, "verified": True, "window": window_info,
                "editor": editor, "text": text, "empty": text == "",
                "source": "windows_uia", "verification": "editor_content_read"}
    except Exception as exc:
        return {"found": False, "verified": False, "reason": str(exc)[:200],
                "source": "windows_uia"}


def ui_focus_editor(window: Optional[Any] = None,
                    expected_process: str = "") -> dict[str, Any]:
    """Resolve, focus, and reread a visible editor without fixed selectors."""
    try:
        root = _window_wrapper(window)
        if root is None:
            return {"ok": False, "found": False, "reason": "window_not_found",
                    "source": "windows_uia"}
        window_info = _window_record(root)
        wanted_process = str(expected_process or "").casefold()
        actual_process = str(window_info.get("process_name") or "").casefold()
        if wanted_process and wanted_process not in actual_process:
            return {"ok": False, "found": False, "reason": "process_mismatch",
                    "window": window_info, "source": "windows_uia"}
        marker, _ = _path_not_found_dialog(root)
        if marker is not None:
            return {"ok": False, "found": False, "reason": "path_not_found_dialog",
                    "path_error_dialog": True, "window": window_info,
                    "source": "windows_uia"}
        candidates = _editor_candidates(root, window_info)
        if not candidates:
            return {"ok": False, "found": False, "reason": "editor_not_found",
                    "window": window_info, "source": "windows_uia"}
        _, _, record, wrapper, _ = candidates[0]
        focus = getattr(wrapper, "set_focus", None)
        if not callable(focus):
            return {"ok": False, "found": True, "reason": "focus_unavailable",
                    "editor": record, "window": window_info,
                    "source": "windows_uia"}
        focus()
        click_input = getattr(wrapper, "click_input", None)
        if callable(click_input):
            # Modern Notepad exposes the editor as RichEditD2DPT/Document;
            # set_focus can activate the window without placing the caret.
            # Click the freshly grounded control, never a fixed coordinate.
            click_input()
        active = ui_active_window()
        if int(active.get("handle") or 0) != int(window_info.get("handle") or 0):
            return {"ok": False, "found": True, "reason": "focus_not_confirmed",
                    "editor": record, "window": window_info,
                    "source": "windows_uia"}
        refreshed = ui_read_editor(window_info.get("handle"), expected_process)
        if not refreshed.get("found"):
            return {"ok": False, "found": True, "reason": "editor_reread_failed",
                    "editor": record, "window": window_info,
                    "source": "windows_uia"}
        return {"ok": True, "found": True, "focused": True,
                "window": refreshed.get("window", window_info),
                "editor": refreshed.get("editor"), "text": refreshed.get("text", ""),
                "empty": refreshed.get("empty", True),
                "source": "windows_uia", "verification": "editor_focus_and_read"}
    except Exception as exc:
        return {"ok": False, "found": False, "reason": str(exc)[:200],
                "source": "windows_uia"}


def ui_type_editor(window: Optional[Any] = None,
                   expected_process: str = "", text: str = "",
                   interval: float = 0.03) -> dict[str, Any]:
    """Focus and write one mission-owned editor in one confirmed UIA action.

    Keeping grounding and input in the same handler closes the foreground race
    between a separate focus call and the keyboard action.  The value pattern
    is preferred because it writes to the grounded control without depending
    on whichever process wins the foreground immediately afterward.
    """
    try:
        root = _window_wrapper(window)
        if root is None:
            return {"ok": False, "found": False, "reason": "window_not_found",
                    "source": "windows_uia"}
        window_info = _window_record(root)
        wanted_process = str(expected_process or "").casefold()
        actual_process = str(window_info.get("process_name") or "").casefold()
        if wanted_process and wanted_process not in actual_process:
            return {"ok": False, "found": False, "reason": "process_mismatch",
                    "window": window_info, "source": "windows_uia"}
        marker, _ = _path_not_found_dialog(root)
        if marker is not None:
            return {"ok": False, "found": False, "reason": "path_not_found_dialog",
                    "path_error_dialog": True, "window": window_info,
                    "source": "windows_uia"}
        candidates = _editor_candidates(root, window_info)
        if not candidates:
            return {"ok": False, "found": False, "reason": "editor_not_found",
                    "window": window_info, "source": "windows_uia"}
        _, _, record, wrapper, current_text = candidates[0]
        value = str(text or "")
        if current_text and current_text != value:
            return {"ok": False, "found": True, "reason": "editor_not_empty",
                    "editor": _editor_record(record, current_text),
                    "window": window_info, "source": "windows_uia"}

        restore = getattr(root, "restore", None)
        if callable(restore):
            restore()
        root_focus = getattr(root, "set_focus", None)
        if callable(root_focus):
            root_focus()
        focus = getattr(wrapper, "set_focus", None)
        if not callable(focus):
            return {"ok": False, "found": True, "reason": "focus_unavailable",
                    "editor": record, "window": window_info,
                    "source": "windows_uia"}
        focus()
        click_input = getattr(wrapper, "click_input", None)
        if callable(click_input):
            click_input()

        method = ""
        # Modern Notepad exposes a UIA Value pattern on its Document control.
        # Prefer it to foreground keyboard injection; it remains scoped to the
        # freshly resolved editor and replaces the whole value atomically.
        for method_name in ("set_edit_text", "set_value"):
            setter = getattr(wrapper, method_name, None)
            if not callable(setter):
                continue
            try:
                setter(value)
                method = f"uia_{method_name}"
                break
            except Exception:
                continue

        if not method:
            type_keys = getattr(wrapper, "type_keys", None)
            if callable(type_keys):
                try:
                    type_keys(value, with_spaces=True,
                              pause=max(0.0, min(float(interval), 1.0)))
                    method = "uia_type_keys"
                except Exception:
                    method = ""
        if not method:
            # Retain the existing Unicode-aware keyboard boundary as the last
            # option, still inside this single confirmed UIA action.
            from .computer_use_tools import keyboard_type
            fallback = keyboard_type(value, interval=interval)
            if not fallback.get("ok"):
                return {**fallback, "editor": record, "window": window_info,
                        "source": "windows_uia"}
            method = str(fallback.get("input_method") or "keyboard")

        time.sleep(0.05)
        refreshed = ui_read_editor(window_info.get("handle"), expected_process)
        if not refreshed.get("found"):
            return {"ok": False, "found": True, "reason": "editor_reread_failed",
                    "editor": record, "window": window_info,
                    "input_method": method, "source": "windows_uia"}
        actual = str(refreshed.get("text") or "")
        if actual != value:
            return {"ok": False, "found": True, "reason": "editor_content_mismatch",
                    "editor": refreshed.get("editor"), "window": refreshed.get("window", window_info),
                    "input_method": method, "source": "windows_uia"}
        return {"ok": True, "found": True, "focused": True, "typed": True,
                "text": actual, "editor": refreshed.get("editor"),
                "window": refreshed.get("window", window_info),
                "input_method": method, "verification": "uia_editor_typed_and_read"}
    except Exception as exc:
        return {"ok": False, "found": False, "reason": str(exc)[:200],
                "source": "windows_uia"}


def ui_classify_dialog(window: Optional[Any] = None) -> dict[str, Any]:
    """Classify a visible dialog without acting on it."""
    try:
        root = _window_wrapper(window)
        if root is None:
            return {"found": False, "dialog_type": "NONE",
                    "reason": "window_not_found", "source": "windows_uia"}
        window_info = _window_record(root)
        visible = []
        for wrapper in _walk(root):
            if not _safe_call(wrapper, "is_visible", False):
                continue
            name = " ".join(str(_element_name(wrapper) or "").split())
            if name:
                visible.append({"text": name, "control_type": _control_type(wrapper),
                                "identity": _runtime_id(wrapper)})
        texts = [item["text"] for item in visible]
        lowered = " ".join(texts).casefold()
        title = str(window_info.get("title") or "")
        title_low = title.casefold()
        has_cancel = any(text.casefold() in {"cancelar", "cancel"} for text in texts)
        has_dont_save = any("não salvar" in text.casefold() or
                            "nao salvar" in text.casefold() or
                            "don't save" in text.casefold() or
                            "do not save" in text.casefold() for text in texts)
        has_save = any(text.casefold() in {"salvar", "save"} for text in texts)
        has_edit = any(item["control_type"].casefold() in {"edit", "combobox"}
                       for item in visible)
        if has_save and has_dont_save and has_cancel:
            dialog_type = "UNSAVED_DOCUMENT_DIALOG"
        elif any(marker in lowered for marker in
                 ("substituir", "replace", "já existe", "ja existe", "already exists")):
            dialog_type = "FILE_OVERWRITE_DIALOG"
        elif ("salvar como" in title_low or "save as" in title_low) and has_edit:
            dialog_type = "SAVE_AS_DIALOG"
        else:
            dialog_type = "NONE"
        editor = ui_read_editor(window_info.get("handle"), window_info.get("process_name", ""))
        editor_data = editor.get("editor") if editor.get("found") else None
        return {"found": dialog_type != "NONE", "dialog_type": dialog_type,
                "dialog_title": title, "visible_controls": visible[:100],
                "owner_window": window_info,
                "owner_document": editor_data,
                "source": "windows_uia", "verification": "dialog_classified"}
    except Exception as exc:
        return {"found": False, "dialog_type": "UNKNOWN",
                "reason": str(exc)[:200], "source": "windows_uia"}


def _find_first_control(control_type: str, window: Optional[Any] = None):
    root = _window_wrapper(window)
    if root is None:
        return None, {"found": False, "reason": "window_not_found", "source": "windows_uia"}
    window_info = _window_record(root)
    wanted = str(control_type or "").casefold()
    for wrapper in _walk(root):
        if wanted and _control_type(wrapper).casefold() != wanted:
            continue
        record = _element_record(wrapper, window_info)
        if record:
            return wrapper, record
    return None, {"found": False, "reason": "element_not_found",
                  "source": "windows_uia", "window_title": window_info["title"]}


def ui_focus_window(window: Optional[Any] = None, process_id: int = 0) -> dict[str, Any]:
    """Focus a freshly resolved window without clicking by coordinates."""
    try:
        wrapper = (_window_wrapper_for_process(window, process_id)
                   if int(process_id or 0) else _window_wrapper(window))
        if wrapper is None:
            return {"ok": False, "found": False, "reason": "window_not_found",
                    "source": "windows_uia"}
        record = _window_record(wrapper)
        handle = int(record.get("handle") or 0)
        if not handle or not _window_exists(handle):
            return {"ok": False, "found": False, "reason": "window_gone",
                    "source": "windows_uia"}
        restore = getattr(wrapper, "restore", None)
        if callable(restore):
            restore()
        focus = getattr(wrapper, "set_focus", None)
        if not callable(focus):
            return {"ok": False, "found": True, "reason": "focus_unavailable",
                    "source": "windows_uia", "window": record}
        refreshed = {}
        valid = False
        click_input = getattr(wrapper, "click_input", None)
        for attempt in range(2):
            focus()
            refreshed = ui_active_window()
            valid = int(refreshed.get("handle") or 0) == handle
            if valid:
                break
            # Some desktop windows reject a background SetForegroundWindow
            # while another app owns the foreground.  A grounded UIA click on
            # the resolved window is the bounded fallback; no coordinates are
            # invented and identity is still checked afterward.
            if attempt == 0 and callable(click_input):
                try:
                    click_input()
                except Exception:
                    pass
                time.sleep(0.05)
            if not valid:
                valid = _activate_window_handle(handle)
                if valid:
                    refreshed = ui_active_window()
                    break
        return {"ok": valid, "found": True, "focused": valid,
                "window": refreshed if valid else record,
                "source": "windows_uia",
                "reason": None if valid else "focus_not_confirmed"}
    except Exception as exc:
        return {"ok": False, "found": False, "reason": str(exc)[:200],
                "source": "windows_uia"}


def ui_focus_element(target: str = "", control_type: Optional[str] = None,
                     window: Optional[Any] = None) -> dict[str, Any]:
    """Focus a freshly resolved UIA control and confirm its window remains active."""
    try:
        if str(target or "").strip():
            wrapper, record = _find_with_wrapper(target, control_type, window)
        else:
            wrapper, record = _find_first_control(control_type or "", window)
        if wrapper is None or not record.get("found"):
            return {**record, "ok": False}
        if not record.get("enabled") or not record.get("visible"):
            return {**record, "ok": False, "reason": "element_not_actionable"}
        valid = validate_ui_target(record, coordinate_mapping_validated=True)
        if not valid.get("valid"):
            return {**record, "ok": False, "reason": valid.get("reason")}
        focus = getattr(wrapper, "set_focus", None)
        if not callable(focus):
            return {**record, "ok": False, "reason": "focus_unavailable"}
        focus()
        return {**record, "ok": True, "focused": True,
                "verification": "uia_element_focus"}
    except Exception as exc:
        return {"ok": False, "found": False, "reason": str(exc)[:200],
                "source": "windows_uia"}


def ui_invoke_element(target: str = "", control_type: Optional[str] = None,
                      window: Optional[Any] = None) -> dict[str, Any]:
    """Invoke a freshly grounded UIA control without coordinate clicks."""
    try:
        wrapper, record = _find_with_wrapper(target, control_type, window)
        if wrapper is None or not record.get("found"):
            return {**record, "ok": False}
        if not record.get("enabled") or not record.get("visible"):
            return {**record, "ok": False, "reason": "element_not_actionable"}
        valid = validate_ui_target(record, coordinate_mapping_validated=True)
        if not valid.get("valid"):
            return {**record, "ok": False, "reason": valid.get("reason")}
        root = _window_wrapper(window)
        root_focus = getattr(root, "set_focus", None) if root is not None else None
        if callable(root_focus):
            root_focus()
            time.sleep(0.05)
        focus = getattr(wrapper, "set_focus", None)
        if callable(focus):
            focus()
            time.sleep(0.05)
        invoke = getattr(wrapper, "invoke", None)
        if not callable(invoke):
            return {**record, "ok": False, "reason": "invoke_unavailable"}
        invoke()
        return {**record, "ok": True, "invoked": True,
                "verification": "uia_invoke"}
    except Exception as exc:
        return {"ok": False, "found": False, "reason": str(exc)[:200],
                "source": "windows_uia"}


def ui_dismiss_path_not_found(window: Optional[Any] = None) -> dict[str, Any]:
    """Close only a Windows path-not-found dialog after exact title matching."""
    try:
        root = _window_wrapper(window)
        if root is None:
            return {"ok": False, "reason": "path_not_found_dialog_not_confirmed",
                    "source": "windows_uia"}
        window_info = _window_record(root)
        marker, wrapper = _path_not_found_dialog(root)
        if marker is None or wrapper is None:
            return {"ok": False, "reason": "path_not_found_ok_button_not_found",
                    "source": "windows_uia", "window": window_info}
        record = _element_record(wrapper, window_info)
        if record is None:
            return {"ok": False, "reason": "path_not_found_ok_button_not_found",
                    "source": "windows_uia", "window": window_info}
        valid = validate_ui_target(record, coordinate_mapping_validated=True)
        if not valid.get("valid"):
            return {"ok": False, "reason": valid.get("reason"),
                    "source": "windows_uia"}
        root_focus = getattr(root, "set_focus", None)
        if callable(root_focus):
            root_focus()
            time.sleep(0.05)
        set_focus = getattr(wrapper, "set_focus", None)
        if callable(set_focus):
            set_focus()
            time.sleep(0.05)
        invoke = getattr(wrapper, "invoke", None)
        invoked = False
        if callable(invoke):
            try:
                invoke()
                invoked = True
            except Exception:
                invoked = False
        if not invoked:
            return {"ok": False, "reason": "path_not_found_ok_action_unavailable",
                    "source": "windows_uia"}
        time.sleep(0.1)
        refreshed_root = _window_wrapper(window)
        if refreshed_root is not None and _path_not_found_dialog(refreshed_root)[0] is not None:
            return {"ok": False, "reason": "path_not_found_dialog_still_present",
                    "source": "windows_uia"}
        return {"ok": True, "dismissed": True,
                "verification": "exact_path_not_found_dialog", "source": "windows_uia"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:200], "source": "windows_uia"}


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
    return {"ok": True, **ui_active_window()}


def _ui_find_element_tool(target: str, control_type: Optional[str] = None,
                          window: Optional[Any] = None):
    return ui_find_element(target, control_type, window)


def _ui_list_elements_tool(window: Optional[Any] = None, limit: int = 50):
    return ui_list_elements(window, limit)


def _ui_get_text_tool(target: str, control_type: Optional[str] = None,
                      window: Optional[Any] = None):
    return ui_get_element_text(target, control_type, window)


def _ui_read_editor_tool(window: Optional[Any] = None,
                          expected_process: str = ""):
    return ui_read_editor(window, expected_process)


def _ui_focus_editor_tool(window: Optional[Any] = None,
                          expected_process: str = ""):
    return ui_focus_editor(window, expected_process)


def _ui_type_editor_tool(window: Optional[Any] = None,
                         expected_process: str = "", text: str = "",
                         interval: float = 0.03):
    return ui_type_editor(window, expected_process, text, interval)


def _ui_classify_dialog_tool(window: Optional[Any] = None):
    return ui_classify_dialog(window)


def _ui_focus_window_tool(window: Optional[Any] = None, process_id: int = 0):
    return ui_focus_window(window, process_id)


def _ui_focus_element_tool(target: str = "", control_type: Optional[str] = None,
                           window: Optional[Any] = None):
    return ui_focus_element(target, control_type, window)


def _ui_invoke_element_tool(target: str = "", control_type: Optional[str] = None,
                            window: Optional[Any] = None):
    return ui_invoke_element(target, control_type, window)


def _ui_dismiss_path_not_found_tool(window: Optional[Any] = None):
    return ui_dismiss_path_not_found(window)


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
    Tool("ui_read_editor", "Resolve e lê o conteúdo real de um editor UIA.",
         _ui_read_editor_tool, Risk.MEDIUM,
         parameters={"window": str, "expected_process": str},
         category="computer_use"),
    Tool("ui_focus_editor", "Resolve e foca o editor UIA da janela ativa.",
         _ui_focus_editor_tool, Risk.MEDIUM,
         parameters={"window": str, "expected_process": str},
         category="computer_use"),
    Tool("ui_type_editor", "Resolve, foca e escreve em um editor UIA em uma ação atômica.",
         _ui_type_editor_tool, Risk.HIGH, confirmation=True,
         parameters={"window": str, "expected_process": str,
                     "text": str, "interval": float},
         category="computer_use"),
    Tool("ui_classify_dialog", "Classifica diálogos visíveis sem executar ações.",
         _ui_classify_dialog_tool, Risk.LOW,
         parameters={"window": str}, category="computer_use"),
    Tool("ui_focus_window", "Foca uma janela resolvida via Windows UIA.",
         _ui_focus_window_tool, Risk.LOW,
         parameters={"window": str, "process_id": int}, category="computer_use"),
    Tool("ui_focus_element", "Foca um controle resolvido via Windows UIA.",
         _ui_focus_element_tool, Risk.MEDIUM,
         parameters={"target": str, "control_type": str, "window": str},
         category="computer_use"),
    Tool("ui_invoke_element", "Invoca um controle resolvido via Windows UIA.",
         _ui_invoke_element_tool, Risk.HIGH, confirmation=True,
         parameters={"target": str, "control_type": str, "window": str},
         category="computer_use"),
    Tool("ui_dismiss_path_not_found", "Fecha somente o diálogo confirmado de caminho inexistente.",
         _ui_dismiss_path_not_found_tool, Risk.MEDIUM,
         parameters={"window": str}, category="computer_use"),
    Tool("hybrid_find_ui_target", "Busca UIA primeiro e usa visão local como fallback.",
         _hybrid_find_tool, Risk.MEDIUM,
         parameters={"target": str, "control_type": str, "window": str},
         category="computer_use"),
)


__all__ = [
    "UI_AUTOMATION_TOOLS", "ui_active_window", "ui_find_element",
    "ui_list_elements", "ui_get_element_text", "validate_ui_target",
    "ui_read_editor", "ui_focus_editor", "ui_classify_dialog",
    "ui_type_editor",
    "ui_focus_window", "ui_focus_element", "ui_dismiss_path_not_found",
    "ui_invoke_element", "hybrid_find_ui_target",
]
