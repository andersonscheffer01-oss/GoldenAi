from types import SimpleNamespace

from jarvis_core.cancellation import CancellationToken
from jarvis_core.computer_use_mission import ComputerMissionExecutor, ComputerMissionPlanner
from jarvis_core.models import BROWSER_ACTION, BROWSER_READ, Risk, Tool
from jarvis_core.security import (
    COMPUTER_USE_MISSION_PRE_SAVE,
    READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
    SecurityManager,
)


class Registry:
    def get(self, _name):
        return object()


def _read_tool():
    return Tool(
        "browser_get_page_info", "read", lambda: {"ok": True},
        Risk.LOW, action_class=BROWSER_READ,
        authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
    )


def test_public_browser_observation_scope_allows_same_domain_read():
    manager = SecurityManager()
    assert manager.decision(
        _read_tool(), authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
        target_url="https://www.python.org/", allowed_hosts=("python.org",),
    ) == "allow"


def test_browser_observation_scope_confirms_out_of_scope_or_private_pages():
    manager = SecurityManager()
    for url, hosts, barrier in (
        ("https://example.com/", ("python.org",), "NONE"),
        ("http://127.0.0.1:8000/", ("127.0.0.1",), "NONE"),
        ("https://www.python.org/login", ("python.org",), "LOGIN_REQUIRED"),
    ):
        assert manager.decision(
            _read_tool(), authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
            target_url=url, allowed_hosts=hosts, page_barrier=barrier,
        ) == "confirm"


def test_browser_actions_are_not_classified_as_read_only():
    manager = SecurityManager()
    action = Tool("browser_click", "click", lambda: {"ok": True}, Risk.MEDIUM,
                  action_class=BROWSER_ACTION)
    assert manager.decision(
        action, authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
        target_url="https://www.python.org/", allowed_hosts=("python.org",),
    ) == "allow"


def test_mission_pre_save_scope_allows_only_non_save_input_actions():
    manager = SecurityManager()
    keyboard = Tool("keyboard_type", "type", lambda: {"ok": True}, Risk.HIGH,
                    confirmation=True)
    save = Tool("ui_invoke_element", "save", lambda: {"ok": True}, Risk.HIGH,
                confirmation=True)
    assert manager.decision(
        keyboard, authorization_scope=COMPUTER_USE_MISSION_PRE_SAVE) == "allow"
    assert manager.decision(
        save, authorization_scope=COMPUTER_USE_MISSION_PRE_SAVE) == "confirm"


class HealthFallbackService:
    def __init__(self, page_ok=False, health_ok=True):
        self.registry = Registry()
        self.cancellation = CancellationToken()
        self.audit = SimpleNamespace(add=lambda **_kwargs: None)
        self.page_ok = page_ok
        self.health_ok = health_ok
        self.calls = []

    def execute_tool(self, name, _arguments, **kwargs):
        self.calls.append((name, kwargs))
        if name == "browser_wait_for_results":
            return {"ok": True}
        if name == "browser_get_page_info":
            if self.page_ok:
                return {"ok": True, "page": {
                    "url": "https://www.python.org/",
                    "title": "Welcome to Python.org",
                    "text": "Python official homepage",
                    "links": [], "interactive": [],
                }}
            return {"ok": False, "error": "Failed to extract page: transient DOM error"}
        if name == "browser_health" and self.health_ok:
            return {"ok": True, "current_url": "https://www.python.org/",
                    "page_title": "Welcome to Python.org"}
        return {"ok": False, "error": "browser unavailable"}


def test_public_title_read_recovers_from_dom_failure_without_confirmation():
    service = HealthFallbackService()
    planner = ComputerMissionPlanner(service.registry)
    mission = planner.plan(
        "abra o Google Chrome, acesse a página oficial python.org e obtenha o título principal")
    mission.result.update({
        "browser_url": "https://www.python.org/",
        "source_url": "https://www.python.org/",
        "official_host": "www.python.org",
        "value_key": "python_page_title",
    })
    executor = ComputerMissionExecutor(service, planner)
    service.task_manager = SimpleNamespace(database=SimpleNamespace(
        list_task_runs=lambda _task_id: [{"mission_id": mission.mission_id,
                                          "run_id": "run-1"}]))
    result = executor._extract_mission_value(mission, mission.steps[-1], "task-1")
    assert result["ok"] is True
    assert result["value"] == "Welcome to Python.org"
    assert any(name == "browser_health" for name, _ in service.calls)
    assert all(kwargs.get("authorization_scope") == READ_ONLY_PUBLIC_BROWSER_OBSERVATION
               for _name, kwargs in service.calls)
    provenance = mission.context.source_provenance["python_page_title"]
    assert provenance["observed_value"] == "Welcome to Python.org"
    assert provenance["observation_method"] == "browser_health"
    assert provenance["task_id"] == "task-1"
    assert provenance["run_id"] == "run-1"
    assert provenance["mission_id"] == mission.mission_id


def test_public_title_read_reports_observation_failure_not_confirmation():
    service = HealthFallbackService(health_ok=False)
    planner = ComputerMissionPlanner(service.registry)
    mission = planner.plan(
        "abra o Google Chrome, acesse a página oficial python.org e obtenha o título principal")
    mission.result.update({
        "browser_url": "https://www.python.org/",
        "source_url": "https://www.python.org/",
        "official_host": "www.python.org",
        "value_key": "python_page_title",
    })
    result = ComputerMissionExecutor(service, planner)._extract_mission_value(
        mission, mission.steps[-1])
    assert result["ok"] is False
    assert result["error"] == "BROWSER_READ_FAILURE"
