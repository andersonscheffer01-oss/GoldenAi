import time
from types import SimpleNamespace

from jarvis_core.models import Risk
from jarvis_core.service import JarvisService
from jarvis_core.tools import ui_automation as uia


class _FakeWrapper:
    def __init__(self, name, control_type, rect, *, handle=100, pid=55,
                 children=None, enabled=True, visible=True, password=False,
                 automation_id="", class_name=""):
        self.element_info = SimpleNamespace(
            name=name,
            control_type=control_type,
            automation_id=automation_id,
            class_name=class_name,
            runtime_id=(handle, name),
        )
        self._rect = SimpleNamespace(*())
        self._rect.left, self._rect.top, self._rect.right, self._rect.bottom = rect
        self._handle = handle
        self._pid = pid
        self._children = children or []
        self._enabled = enabled
        self._visible = visible
        self._password = password

    @property
    def handle(self):
        return self._handle

    def process_id(self):
        return self._pid

    def window_text(self):
        return self.element_info.name

    def rectangle(self):
        return self._rect

    def children(self):
        return self._children

    def is_enabled(self):
        return self._enabled

    def is_visible(self):
        return self._visible

    def is_password(self):
        return self._password


def _fake_tree(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), children=[])
    children = [
        _FakeWrapper("Arquivo", "MenuItem", (10, 40, 90, 70),
                      automation_id="file-menu"),
        _FakeWrapper("Salvar", "Button", (100, 40, 180, 70)),
        _FakeWrapper("Nome", "Edit", (100, 100, 400, 140)),
        _FakeWrapper("Senha", "Edit", (100, 150, 400, 190), password=True),
    ]
    root._children = children
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_window_pid", lambda _handle: 55)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")
    return root


def test_active_window_schema(monkeypatch):
    _fake_tree(monkeypatch)

    result = uia.ui_active_window()

    assert result["found"] is True
    assert result["title"] == "Sem título - Bloco de notas"
    assert result["pid"] == 55
    assert result["handle"] == 100
    assert result["bounds"] == {"x": 0, "y": 0, "width": 800, "height": 600}
    assert result["backend"] == "uia"


def test_focus_window_selects_requested_process_when_chrome_is_ambiguous(monkeypatch):
    unrelated = _FakeWrapper("MEGA - Google Chrome", "Window",
                             (0, 0, 800, 600), handle=201, pid=101)
    session = _FakeWrapper("Google - Google Chrome", "Window",
                           (0, 0, 800, 600), handle=202, pid=202)
    class _Desktop:
        def windows(self, top_level_only=True):
            return [unrelated, session]

        def window(self, handle):
            return next(item for item in (unrelated, session)
                        if item.handle == handle)

    focused = []
    session.set_focus = lambda: focused.append(session.handle)
    unrelated.set_focus = lambda: focused.append(unrelated.handle)
    monkeypatch.setattr(uia, "_desktop", lambda: _Desktop())
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_foreground_handle", lambda: 202)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "chrome.exe")

    result = uia.ui_focus_window("chrome", process_id=202)

    assert result["ok"] is True
    assert result["window"]["pid"] == 202
    assert focused == [202]


def test_focus_window_restores_minimized_target_before_focus(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (-32000, -32000, -31900, -31900), handle=303, pid=303)
    restored = []
    focused = []
    root.restore = lambda: restored.append(True)
    root.set_focus = lambda: focused.append(True)
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_foreground_handle", lambda: 303)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")

    result = uia.ui_focus_window("notepad")

    assert result["ok"] is True
    assert restored == [True]
    assert focused == [True]


def test_focus_window_uses_grounded_click_when_set_focus_loses_foreground(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), handle=304, pid=304)
    focused = []
    clicked = []
    root.set_focus = lambda: focused.append(True)
    root.click_input = lambda: clicked.append(True)
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")
    active = iter([{"handle": 999}, {"handle": 304}])
    monkeypatch.setattr(uia, "ui_active_window", lambda: next(active))

    result = uia.ui_focus_window("notepad")

    assert result["ok"] is True
    assert focused == [True, True]
    assert clicked == [True]


def test_user_activity_reports_idle_age_without_content(monkeypatch):
    monkeypatch.setattr(uia, "_last_user_input_age_ms", lambda: 120)

    result = uia.ui_user_activity(threshold_ms=500)

    assert result["ok"] is True
    assert result["user_active"] is True
    assert result["last_user_input_age_ms"] == 120
    assert "keys" not in result
    assert "mouse" not in result


def test_foreground_state_distinguishes_background_target_and_user_owner(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), handle=401, pid=55)
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_process_present", lambda _name: True)
    monkeypatch.setattr(uia, "_window_minimized", lambda _handle: False)
    monkeypatch.setattr(uia, "_window_visible", lambda _handle: True)
    monkeypatch.setattr(uia, "ui_active_window", lambda: {
        "found": True, "handle": 402, "process_name": "TslGame.exe",
    })
    monkeypatch.setattr(uia, "ui_user_activity", lambda _threshold: {
        "ok": True, "user_active": True, "last_user_input_age_ms": 80,
        "threshold_ms": 2000,
    })

    result = uia.ui_foreground_state("notepad", "notepad")

    assert result["process_present"] is True
    assert result["window_present"] is True
    assert result["window_focused"] is False
    assert result["window_state"] == "WINDOW_EXISTS_BACKGROUND"
    assert result["foreground_owner"] == "USER_EXTERNAL_APP"
    assert result["user_active"] is True


def test_foreground_state_distinguishes_minimized_target_when_user_idle(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), handle=403, pid=55)
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_process_present", lambda _name: True)
    monkeypatch.setattr(uia, "_window_minimized", lambda _handle: True)
    monkeypatch.setattr(uia, "_window_visible", lambda _handle: True)
    monkeypatch.setattr(uia, "ui_active_window", lambda: {
        "found": True, "handle": 404, "process_name": "explorer.exe",
    })
    monkeypatch.setattr(uia, "ui_user_activity", lambda _threshold: {
        "ok": True, "user_active": False, "last_user_input_age_ms": 5000,
        "threshold_ms": 2000,
    })

    result = uia.ui_foreground_state("notepad", "notepad")

    assert result["window_state"] == "WINDOW_MINIMIZED"
    assert result["foreground_owner"] == "UNKNOWN"
    assert result["automatic_foreground_change"] is True


def test_type_editor_aborts_before_input_when_external_user_owns_foreground(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), handle=405, pid=55)
    editor = _FakeWrapper("", "Document", (20, 80, 780, 560), handle=406, pid=55)
    writes = []
    editor.set_edit_text = lambda value: writes.append(value)
    root._children = [editor]
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")
    monkeypatch.setattr(uia, "ui_foreground_state", lambda *_args: {
        "ok": True, "foreground_owner": "USER_EXTERNAL_APP",
        "window_focused": False, "last_user_input_age_ms": 40,
    })

    result = uia.ui_type_editor("notepad", "notepad", "Golden Jarvis funcionando")

    assert result["ok"] is False
    assert result["reason"] == "USER_ACTIVITY_DETECTED"
    assert writes == []


def test_type_editor_aborts_on_foreground_epoch_change_before_input(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), handle=407, pid=55)
    editor = _FakeWrapper("", "Document", (20, 80, 780, 560), handle=408, pid=55)
    writes = []
    editor.set_focus = lambda: None
    editor.click_input = lambda: None
    editor.set_edit_text = lambda value: writes.append(value)
    root._children = [editor]
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")
    monkeypatch.setattr(uia, "ui_foreground_state", lambda *_args: {
        "ok": True, "foreground_owner": "JARVIS_TARGET", "window_focused": True,
    })
    snapshots = iter([(407, 11), (999, 12)])
    monkeypatch.setattr(uia, "_foreground_snapshot", lambda: next(snapshots))

    result = uia.ui_type_editor("notepad", "notepad", "Golden Jarvis funcionando")

    assert result["ok"] is False
    assert result["reason"] == "FOREGROUND_CHANGED_DURING_ATOMIC_ACTION"
    assert writes == []


def test_ui_find_element_and_bounds_validation(monkeypatch):
    _fake_tree(monkeypatch)

    found = uia.ui_find_element("Arquivo", control_type="MenuItem")
    missing = uia.ui_find_element("Inexistente")

    assert found["found"] is True
    assert found["control_type"] == "MenuItem"
    assert found["bounds"] == {"x1": 10, "y1": 40, "x2": 90, "y2": 70}
    assert found["center"] == {"x": 50, "y": 55}
    assert found["source"] == "windows_uia"
    assert missing["found"] is False
    assert missing["reason"] == "element_not_found"


def test_ui_list_is_limited_and_text_protects_password(monkeypatch):
    _fake_tree(monkeypatch)

    listed = uia.ui_list_elements(limit=2)
    protected = uia.ui_get_element_text("Senha")
    plain = uia.ui_get_element_text("Nome")

    assert len(listed["elements"]) == 2
    assert protected["protected"] is True
    assert protected["text"] is None
    assert plain["protected"] is False
    assert plain["text"] == "Nome"


def test_editor_read_returns_content_and_document_identity(monkeypatch):
    root = _FakeWrapper("Sem título - Bloco de notas", "Window",
                        (0, 0, 800, 600), children=[])
    editor = _FakeWrapper("Golden Jarvis funcionando", "Document",
                          (20, 80, 780, 560), handle=101, pid=55)
    root._children = [editor]
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_window_exists", lambda _handle: True)
    monkeypatch.setattr(uia, "_window_pid", lambda _handle: 55)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")

    result = uia.ui_read_editor(expected_process="notepad")

    assert result["verified"] is True
    assert result["text"] == "Golden Jarvis funcionando"
    assert result["editor"]["document_identity"]
    assert result["editor"]["content_state_id"]


def test_editor_read_rejects_wrong_process(monkeypatch):
    _fake_tree(monkeypatch)
    result = uia.ui_read_editor(expected_process="chrome")
    assert result["found"] is False
    assert result["reason"] == "process_mismatch"


def test_dialog_classifier_distinguishes_unsaved_document(monkeypatch):
    root = _FakeWrapper("criar_features.py - Bloco de notas", "Window",
                        (0, 0, 800, 600), children=[])
    root._children = [
        _FakeWrapper("Salvar", "Button", (10, 10, 100, 40)),
        _FakeWrapper("Não salvar", "Button", (110, 10, 220, 40)),
        _FakeWrapper("Cancelar", "Button", (230, 10, 340, 40)),
    ]
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    monkeypatch.setattr(uia, "_process_name", lambda _pid: "notepad.exe")

    result = uia.ui_classify_dialog("notepad")

    assert result["dialog_type"] == "UNSAVED_DOCUMENT_DIALOG"
    assert {item["text"] for item in result["visible_controls"]} >= {
        "Salvar", "Não salvar", "Cancelar"}


def test_dialog_classifier_distinguishes_save_as_and_overwrite(monkeypatch):
    root = _FakeWrapper("Salvar como", "Window", (0, 0, 800, 600), children=[])
    root._children = [_FakeWrapper("Nome", "Edit", (10, 10, 300, 40))]
    monkeypatch.setattr(uia, "_window_wrapper", lambda _window=None: root)
    assert uia.ui_classify_dialog("notepad")["dialog_type"] == "SAVE_AS_DIALOG"

    root.element_info.name = "Confirmar Salvar como"
    root._children = [
        _FakeWrapper("pesquisa_python.txt já existe. Substituir?", "Text",
                     (10, 10, 400, 40)),
        _FakeWrapper("Cancelar", "Button", (10, 50, 120, 80)),
    ]
    assert uia.ui_classify_dialog("notepad")["dialog_type"] == "FILE_OVERWRITE_DIALOG"


def test_ui_target_stale_and_window_changed(monkeypatch):
    _fake_tree(monkeypatch)
    target = uia.ui_find_element("Arquivo")

    stale = uia.validate_ui_target(
        target, now=target["timestamp_epoch"] + 6,
        coordinate_mapping_validated=True)
    monkeypatch.setattr(uia, "_window_pid", lambda _handle: 99)
    changed = uia.validate_ui_target(target, coordinate_mapping_validated=True)

    assert stale["valid"] is False
    assert stale["reason"] == "stale_target"
    assert changed["valid"] is False
    assert changed["reason"] == "process_changed"


def test_ui_target_requires_coordinate_mapping_before_action(monkeypatch):
    _fake_tree(monkeypatch)
    target = uia.ui_find_element("Arquivo")

    blocked = uia.validate_ui_target(target)
    valid = uia.validate_ui_target(target, coordinate_mapping_validated=True)

    assert blocked == {"valid": False, "reason": "coordinate_mapping_unverified"}
    assert valid["valid"] is True


def test_hybrid_uses_vision_fallback_when_uia_misses(monkeypatch):
    _fake_tree(monkeypatch)
    monkeypatch.setattr(uia, "ui_find_element", lambda *args, **kwargs: {
        "found": False, "reason": "element_not_found", "source": "windows_uia"})
    monkeypatch.setattr(uia, "_vision_find", lambda _target: {
        "found": True, "bounding_box": {"x1": 10, "y1": 10, "x2": 100, "y2": 60},
        "center": {"x": 55, "y": 35}, "confidence": 0.9,
        "confidence_source": "model_reported", "source": "local_vision"})

    result = uia.hybrid_find_ui_target("canvas")

    assert result["found"] is True
    assert result["status"] == "FOUND"
    assert result["selection_reason"] == "vision_fallback"
    assert result["source"] == "local_vision_fallback"


def test_hybrid_prioritizes_uia_and_blocks_disagreement(monkeypatch):
    _fake_tree(monkeypatch)
    uia_result = uia.ui_find_element("Arquivo")
    near_vision = {"found": True, "bounding_box": {"x1": 12, "y1": 42, "x2": 92, "y2": 72}}
    far_vision = {"found": True, "bounding_box": {"x1": 500, "y1": 400, "x2": 700, "y2": 500}}

    agreed = uia.hybrid_find_ui_target("Arquivo", vision_result=near_vision)
    conflict = uia.hybrid_find_ui_target("Arquivo", vision_result=far_vision)

    assert agreed["status"] == "AGREE"
    assert agreed["source"] == "windows_uia"
    assert agreed["selection_reason"] == "windows_uia_priority"
    assert conflict["status"] == "AMBIGUOUS"
    assert conflict["auto_action"] == "BLOCKED"


def test_ui_tools_are_read_only_and_use_canonical_security_manager(tmp_path):
    service = JarvisService(str(tmp_path))
    names = {"ui_active_window", "ui_find_element", "ui_list_elements",
             "ui_get_element_text", "ui_read_editor", "ui_focus_editor",
             "ui_type_editor", "ui_classify_dialog",
             "hybrid_find_ui_target", "ui_user_activity", "ui_foreground_state"}

    catalog_names = {item["name"] for item in service.registry.public_catalog()}
    assert names <= catalog_names
    assert service.registry.get("ui_active_window").risk == Risk.LOW
    assert service.registry.get("ui_user_activity").risk == Risk.LOW
    assert service.registry.get("ui_foreground_state").risk == Risk.LOW
    assert service.registry.get("ui_user_activity").confirmation is False
    assert service.registry.get("ui_foreground_state").confirmation is False
    assert service.registry.get("ui_find_element").confirmation is False
    assert service.registry.get("ui_type_editor").risk == Risk.HIGH
    assert service.registry.get("ui_type_editor").confirmation is True
    assert service.registry.get("hybrid_find_ui_target").confirmation is False
