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
             "ui_get_element_text", "hybrid_find_ui_target"}

    catalog_names = {item["name"] for item in service.registry.public_catalog()}
    assert names <= catalog_names
    assert service.registry.get("ui_active_window").risk == Risk.LOW
    assert service.registry.get("ui_find_element").confirmation is False
    assert service.registry.get("hybrid_find_ui_target").confirmation is False
