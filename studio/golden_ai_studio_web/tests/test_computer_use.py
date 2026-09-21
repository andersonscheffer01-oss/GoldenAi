import json
from types import SimpleNamespace

from jarvis_core.models import Risk
from jarvis_core.orchestrator import CentralOrchestrator
from jarvis_core.orchestrator.models import Route
from jarvis_core.registry import ToolRegistry
from jarvis_core.service import JarvisService
from jarvis_core.tools import computer_use_tools as tools


class _FakePyAutoGUI:
    def __init__(self):
        self.calls = []

    def position(self):
        return SimpleNamespace(x=11, y=22)

    def screenshot(self, region=None):
        self.calls.append(("screenshot", region))
        return SimpleNamespace(save=lambda path, fmt: open(path, "wb").write(b"png"))

    def moveTo(self, x, y, duration=0):
        self.calls.append(("moveTo", x, y, duration))

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))

    def write(self, text, interval=0):
        self.calls.append(("write", text, interval))

    def press(self, key):
        self.calls.append(("press", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))


def _router_with_computer_tools():
    registry = ToolRegistry()
    for definition in tools.COMPUTER_USE_TOOLS:
        registry.register(definition)
    return CentralOrchestrator(registry, mode="on")


def test_tools_registered():
    assert len(tools.COMPUTER_USE_TOOLS) >= 11
    assert {item.name for item in tools.COMPUTER_USE_TOOLS} >= {
        "mouse_position", "mouse_move", "mouse_click", "screenshot",
        "keyboard_type", "keyboard_press", "keyboard_hotkey",
        "clipboard_get", "clipboard_set", "gpu_status", "gpu_list",
        "vision_analyze_screen",
    }


def test_mouse_and_screenshot_use_mocked_gui(monkeypatch, tmp_path):
    fake = _FakePyAutoGUI()
    monkeypatch.setattr(tools, "_pyautogui", lambda: fake)
    assert tools.mouse_position()["x"] == 11
    assert tools.mouse_position()["y"] == 22
    assert tools.mouse_move(100, 200)["ok"] is True
    path = tools.screenshot([0, 0, 10, 10])
    assert path.endswith(".png")
    assert path
    assert any(call[0] == "screenshot" for call in fake.calls)


def test_clipboard_adapter_is_mockable_without_printing_content(monkeypatch):
    state = {"value": "original"}

    class FakeClipboard:
        def paste(self):
            return state["value"]

        def copy(self, value):
            state["value"] = value

    monkeypatch.setattr(tools, "_pyperclip", lambda: FakeClipboard())
    assert tools.clipboard_get() == "original"
    assert tools.clipboard_set("test_jarvis")["length"] == 11
    assert tools.clipboard_get() == "test_jarvis"


def test_gpu_status_is_vendor_neutral_and_does_not_fabricate_dynamic_metrics(monkeypatch):
    monkeypatch.setattr(tools, "_windows_gpu_records", lambda: [{
        "index": 0,
        "name": "AMD Radeon RX 9060 XT",
        "vendor": "AMD",
        "vram_total": None,
        "usage_percent": None,
        "temperature": None,
        "source": "windows_wmi",
    }])
    result = tools.gpu_status()
    assert result["available"] is True
    assert result["vendor"] == "AMD"
    assert result["vram_total"] is None
    assert result["usage_percent"] is None
    assert result["temperature"] is None
    assert result["source"] == "windows_wmi"
    assert result["status"] == "PARTIAL"
    assert result["reason"] == "dynamic_metrics_unavailable"


def test_hotkey_safety_blocks_high_impact_combination():
    result = tools.keyboard_hotkey("alt", "f4")
    assert result["ok"] is False
    assert "bloqueado" in result["error"]


def test_security_manager_is_canonical_and_high_tools_confirm(tmp_path):
    service = JarvisService(str(tmp_path))
    high_names = {"mouse_click", "keyboard_type", "keyboard_press",
                  "keyboard_hotkey", "clipboard_set"}
    assert all(service.registry.get(name).risk == Risk.HIGH for name in high_names)
    assert all(service.registry.get(name).confirmation for name in high_names)
    assert service.registry.get("mouse_click").risk == Risk.HIGH
    result = service.execute_tool("keyboard_type", {"text": "test", "interval": 0.1})
    assert result["confirmation_required"] is True
    assert not hasattr(tools, "security")


def test_vision_reuses_existing_local_vision_provider(monkeypatch):
    calls = []

    class FakeVision:
        def analyze_screen(self, prompt):
            calls.append(prompt)
            return {"ok": True, "analysis": "janela local"}

    monkeypatch.setattr("jarvis_core.vision.get_vision", lambda: FakeVision())
    assert tools.vision_analyze_screen("Descreva a tela") == "janela local"
    assert calls == ["Descreva a tela"]


def test_computer_use_intent_routes_through_existing_skills_router():
    router = _router_with_computer_tools()
    cases = (
        ("qual a posição do mouse?", "mouse_position"),
        ("mova o mouse para 100, 200", "mouse_move"),
        ("clique no botão esquerdo", "mouse_click"),
        ("digite 'hello world'", "keyboard_type"),
        ("pressione enter", "keyboard_press"),
        ("o que tem na área de transferência?", "clipboard_get"),
        ("copie 'Golden AI' para clipboard", "clipboard_set"),
        ("qual o uso da GPU?", "gpu_status"),
        ("tire um screenshot", "screenshot"),
        ("onde está o botão Salvar na tela?", "vision_find_element"),
    )
    for query, expected_tool in cases:
        decision = router.decide(query)
        assert decision.route == Route.COMPUTER_USE
        assert decision.steps[0].tool == expected_tool
