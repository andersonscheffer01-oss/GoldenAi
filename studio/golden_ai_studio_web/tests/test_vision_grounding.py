import json

from PIL import Image

from jarvis_core.orchestrator import CentralOrchestrator
from jarvis_core.orchestrator.models import Route
from jarvis_core.registry import ToolRegistry
from jarvis_core.tools import computer_use_tools as tools


class _FakeVision:
    model = "qwen2.5vl:7b"

    def __init__(self, tmp_path, payload):
        self.tmp_path = tmp_path
        self.payload = payload
        self.capture_count = 0

    def capture_screen(self):
        self.capture_count += 1
        path = self.tmp_path / f"screen-{self.capture_count}.png"
        path.write_bytes(b"png")
        return {
            "ok": True,
            "path": str(path),
            "png_bytes": b"png",
            "width": 1920,
            "height": 1080,
        }

    def analyze_image(self, _image_b64, _prompt):
        return {"ok": True, "analysis": json.dumps(self.payload)}


def _patch_vision(monkeypatch, tmp_path, payload):
    fake = _FakeVision(tmp_path, payload)
    monkeypatch.setattr("jarvis_core.vision.get_vision", lambda: fake)
    return fake


def test_describe_screen_is_structured_local_and_cleans_capture(monkeypatch, tmp_path):
    _patch_vision(monkeypatch, tmp_path, {"description": "Janela do Bloco de Notas"})

    result = tools.vision_describe_screen("Descreva a tela")

    assert result["description"] == "Janela do Bloco de Notas"
    assert result["screen_size"] == {"width": 1920, "height": 1080}
    assert result["source"] == "local_vision"
    assert result["model"] == "qwen2.5vl:7b"
    assert list(tmp_path.iterdir()) == []


def test_find_element_converts_normalized_box_and_reports_center(monkeypatch, tmp_path):
    _patch_vision(monkeypatch, tmp_path, {
        "found": True,
        "label": "Salvar",
        "confidence": 0.92,
        "coordinate_space": "normalized",
        "bounding_box": {"x1": 0.25, "y1": 0.2, "x2": 0.5, "y2": 0.4},
    })

    result = tools.vision_find_element("botão Salvar")

    assert result["found"] is True
    assert result["bounding_box"] == {"x1": 480, "y1": 216, "x2": 960, "y2": 432}
    assert result["center"] == {"x": 720, "y": 324}
    assert result["confidence_source"] == "model_reported"
    assert tools.last_visual_target()["target"] == "botão Salvar"


def test_find_element_rejects_low_confidence_and_invalid_boxes(monkeypatch, tmp_path):
    _patch_vision(monkeypatch, tmp_path, {
        "found": True,
        "confidence": 0.79,
        "coordinate_space": "pixel",
        "bounding_box": [10, 10, 100, 100],
    })
    low_confidence = tools.vision_find_element("alvo")
    assert low_confidence["found"] is False
    assert low_confidence["reason"] == "LOW_CONFIDENCE"

    _patch_vision(monkeypatch, tmp_path, {
        "found": True,
        "confidence": 0.95,
        "coordinate_space": "pixel",
        "bounding_box": [-1, 10, 100, 100],
    })
    invalid_box = tools.vision_find_element("alvo")
    assert invalid_box["found"] is False
    assert invalid_box["reason"] == "bounding_box_invalid"


def test_find_element_accepts_model_list_and_corner_box_format(monkeypatch, tmp_path):
    _patch_vision(monkeypatch, tmp_path, [{
        "found": True,
        "label": "Notepad",
        "confidence": 0.95,
        "coordinate_space": "screen",
        "bounding_box": {"top_left": [25, 25], "bottom_right": [620, 510]},
    }])

    result = tools.vision_find_element("janela do Bloco de Notas")

    assert result["found"] is True
    assert result["bounding_box"] == {"x1": 25, "y1": 25, "x2": 620, "y2": 510}


def test_find_element_maps_normalized_region_to_screen_coordinates(monkeypatch, tmp_path):
    region_path = tmp_path / "region.png"
    Image.new("RGB", (400, 200), "white").save(region_path)
    _patch_vision(monkeypatch, tmp_path, {
        "found": True,
        "confidence": 0.9,
        "coordinate_space": "normalized",
        "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5},
    })
    monkeypatch.setattr(tools, "screenshot", lambda _region: str(region_path))

    result = tools.vision_find_element("Salvar", region=[100, 50, 400, 200])

    assert result["found"] is True
    assert result["bounding_box"] == {"x1": 140, "y1": 70, "x2": 300, "y2": 150}


def test_find_element_never_clicks_and_stale_targets_expire(monkeypatch, tmp_path):
    _patch_vision(monkeypatch, tmp_path, {
        "found": True,
        "confidence": 0.9,
        "coordinate_space": "pixel",
        "bounding_box": [10, 10, 100, 100],
    })
    click_calls = []

    class _NoClick:
        def click(self, **kwargs):
            click_calls.append(kwargs)

    monkeypatch.setattr(tools, "_pyautogui", lambda: _NoClick())
    result = tools.vision_find_element("Salvar")
    timestamp = result["timestamp_epoch"]

    assert result["found"] is True
    assert click_calls == []
    assert tools.is_visual_target_fresh(result, now=timestamp + 4.9) is True
    assert tools.is_visual_target_fresh(result, now=timestamp + 5.1) is False


def test_visual_coordinate_capability_is_conservative():
    capability = tools.visual_coordinate_capability()

    assert capability["process_dpi_aware"] == "PARTIAL"
    assert capability["screenshot_coordinate_space"] == "screen_image_pixels"
    assert capability["pyautogui_coordinate_space"] == "physical_screen_pixels"
    assert capability["match"] == "ONLY_AT_100_PERCENT"
    assert capability["dpi_mapping_verified"] is False
    assert capability["multi_monitor_scope"] == "PRIMARY_MONITOR_ONLY"


def _valid_target():
    return {
        "found": True,
        "confidence": 0.95,
        "confidence_source": "model_reported",
        "timestamp_epoch": __import__("time").time(),
        "screen_width": 1920,
        "screen_height": 1080,
        "bounding_box": {"x1": 10, "y1": 20, "x2": 110, "y2": 80},
        "center": {"x": 60, "y": 50},
        "monitor_scope": "PRIMARY_MONITOR_ONLY",
    }


def test_visual_target_validation_requires_dpi_and_primary_monitor():
    target = _valid_target()

    blocked_dpi = tools.validate_visual_target_for_action(
        target, current_screen_size=(1920, 1080))
    blocked_monitor = tools.validate_visual_target_for_action(
        target, current_screen_size=(1920, 1080),
        dpi_mapping_validated=True, monitor="secondary")
    valid = tools.validate_visual_target_for_action(
        target, current_screen_size=(1920, 1080), dpi_mapping_validated=True)

    assert blocked_dpi == {"valid": False, "reason": "dpi_mapping_unverified"}
    assert blocked_monitor == {"valid": False, "reason": "unsupported_monitor"}
    assert valid["valid"] is True
    assert valid["monitor_scope"] == "PRIMARY_MONITOR_ONLY"


def test_visual_target_validation_blocks_changed_dimensions_and_stale_target():
    target = _valid_target()

    changed = tools.validate_visual_target_for_action(
        target, current_screen_size=(1280, 720), dpi_mapping_validated=True)
    target["timestamp_epoch"] -= 10
    stale = tools.validate_visual_target_for_action(
        target, current_screen_size=(1920, 1080), dpi_mapping_validated=True)

    assert changed["reason"] == "screen_dimensions_changed"
    assert stale["reason"] == "stale_target"


def test_visual_target_validation_blocks_invalid_coordinates_and_confidence_source():
    target = _valid_target()
    target["bounding_box"] = {"x1": -1, "y1": 20, "x2": 110, "y2": 80}
    invalid = tools.validate_visual_target_for_action(
        target, current_screen_size=(1920, 1080), dpi_mapping_validated=True)
    target = _valid_target()
    target["confidence_source"] = "heuristic"
    untrusted = tools.validate_visual_target_for_action(
        target, current_screen_size=(1920, 1080), dpi_mapping_validated=True)

    assert invalid["reason"] == "target_out_of_bounds"
    assert untrusted["reason"] == "confidence_source_unverified"


def test_list_elements_keeps_only_valid_high_confidence_elements(monkeypatch, tmp_path):
    _patch_vision(monkeypatch, tmp_path, {
        "elements": [
            {"type": "button", "label": "Salvar", "confidence": 0.91,
             "coordinate_space": "pixel", "bounding_box": [10, 20, 100, 60]},
            {"type": "button", "label": "Cancelar", "confidence": 0.4,
             "coordinate_space": "pixel", "bounding_box": [110, 20, 200, 60]},
            {"type": "input", "label": "Nome", "coordinate_space": "pixel",
             "bounding_box": [10, 80, 200, 120]},
        ]
    })

    result = tools.vision_list_elements()

    assert len(result["elements"]) == 1
    assert result["elements"][0]["label"] == "Salvar"
    assert result["source"] == "local_vision"


def test_vision_grounding_routes_are_explicit_and_use_computer_use():
    registry = ToolRegistry()
    for definition in tools.COMPUTER_USE_TOOLS:
        registry.register(definition)
    router = CentralOrchestrator(registry, mode="on")

    find = router.decide("onde está o botão Salvar?")
    describe = router.decide("descreva o que está na tela")

    assert find.route == Route.COMPUTER_USE
    assert find.steps[0].tool == "hybrid_find_ui_target"
    assert describe.route == Route.COMPUTER_USE
    assert describe.steps[0].tool == "vision_describe_screen"
