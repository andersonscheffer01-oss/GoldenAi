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
    assert mission.risk_level == "LOW"
    assert mission.requires_confirmation is False
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


def test_ollama_title_to_notepad_request_uses_multi_app_plan(tmp_path):
    request = (
        "Daqui a 2 minutos, quando eu estiver ocioso, acesse a página oficial do Ollama, "
        "obtenha o título principal, abra o Bloco de Notas, escreva o título encontrado e "
        "prepare para salvar como tarefa_7d.txt nos Documentos."
    )
    mission = ComputerMissionPlanner(Registry(), documents_dir=tmp_path).plan(request)
    assert mission.result["multi_app_mission"] is True
    assert mission.result["value_key"] == "ollama_page_title"
    assert mission.result["search_query"] == "Ollama official homepage"
    assert mission.result["target_path"] == str(tmp_path / "tarefa_7d.txt")
    assert [step.step_id for step in mission.steps[:2]] == [
        "open-browser", "navigate-ollama-official"]
    assert mission.result["official_host"] == "ollama.com"
    assert mission.steps[-4].step_id == "confirm-save"


def test_ollama_only_recovery_validates_only_its_context_value():
    request = (
        "Daqui a 2 minutos, quando eu estiver ocioso, acesse a página oficial do Ollama, "
        "obtenha o título principal, abra o Bloco de Notas, escreva o título encontrado e "
        "prepare para salvar como tarefa_7d.txt nos Documentos."
    )
    planner = ComputerMissionPlanner(Registry())
    mission = planner.plan(request)
    mission.current_step = 12
    mission.context.store_variable(
        "ollama_page_title", "Ollama", kind="OBSERVED_VALUE",
        source_app="chrome", source_type="browser_page",
        source_title="Ollama", source_url="https://ollama.com/",
        confidence="verified")

    executor = ComputerMissionExecutor(SimpleNamespace(registry=Registry()), planner)

    result = executor._recovery_context_validation(mission)

    assert result == {
        "ok": True,
        "verification": "MISSION_CONTEXT_AND_PROVENANCE_VALID",
    }
