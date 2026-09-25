"""Regression coverage for the read-only official-page title mission."""
from types import SimpleNamespace

from jarvis_core.cancellation import CancellationToken
from jarvis_core.computer_use_mission import ComputerMissionExecutor, ComputerMissionPlanner


class Registry:
    def get(self, _name):
        return object()


class ReadOnlyBrowserService:
    def __init__(self):
        self.registry = Registry()
        self.cancellation = CancellationToken()
        self.audit = SimpleNamespace(add=lambda **_kwargs: None)

    def execute_tool(self, name, _arguments, **_kwargs):
        if name == "browser_wait_for_results":
            return {"ok": True}
        if name == "browser_get_page_info":
            return {"ok": True, "page": {
                "url": "https://www.python.org/",
                "title": "Welcome to Python.org",
                "text": "Python official homepage",
                "links": [],
            }}
        return {"ok": True, "process_name": "chrome.exe"}


def test_direct_python_title_request_is_planned_without_write_steps():
    planner = ComputerMissionPlanner(Registry())
    mission = planner.plan(
        "abra o Google Chrome, acesse a página oficial python.org e obtenha o título principal")
    assert [step.action_type for step in mission.steps] == [
        "browser_open", "browser_navigate", "focus_browser", "observe_browser",
        "extract_mission_value"]
    assert not any(step.action_type in {"keyboard_type", "keyboard_press", "verify_file"}
                   for step in mission.steps)


def test_direct_python_title_uses_observed_page_and_provenance():
    service = ReadOnlyBrowserService()
    planner = ComputerMissionPlanner(service.registry)
    mission = planner.plan(
        "abra o Google Chrome, acesse a página oficial python.org e obtenha o título principal")
    executor = ComputerMissionExecutor(service, planner)
    result = executor._extract_mission_value(mission, mission.steps[-1])
    assert result["ok"] is True
    assert result["value"] == "Welcome to Python.org"
    assert result["source_url"] == "https://www.python.org/"
    assert mission.context.source_provenance["python_page_title"]["source_type"] == "browser_page"
