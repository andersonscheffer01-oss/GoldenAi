from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jarvis_core.computer_use_mission import (
    ComputerMissionExecutor,
    ComputerMissionPlanner,
    MissionStatus,
    MissionStepStatus,
)
from jarvis_core.cancellation import CancellationToken


MISSION = (
    "Jarvis, abra o Bloco de Notas, escreva Golden Jarvis funcionando, "
    "salve como teste.txt e confirme que foi salvo."
)

BROWSER_MISSION = (
    "Jarvis, abra o navegador, pesquise OpenAI e me diga o título dos três primeiros resultados."
)


class FakeRegistry:
    def __init__(self, names):
        self.names = set(names)

    def get(self, name):
        return object() if name in self.names else None


class FakeService:
    def __init__(self, documents_dir, *, confirmation=False, wrong_window=False):
        self.registry = FakeRegistry({
            "open_program", "ui_active_window", "ui_focus_window", "ui_focus_element",
            "ui_dismiss_path_not_found", "keyboard_type", "keyboard_hotkey", "keyboard_press",
        })
        self.cancellation = CancellationToken()
        self.audit = SimpleNamespace(add=lambda **_kwargs: None)
        self.documents_dir = Path(documents_dir)
        self.confirmation = confirmation
        self.wrong_window = wrong_window
        self.calls = []
        self.active_title = "Sem título - Bloco de notas"
        self.active_process = "notepad.exe"
        self.typed = []

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        self.calls.append((name, dict(arguments), confirmed))
        if name == "ui_active_window":
            if self.wrong_window:
                return {"ok": True, "found": True, "title": "Terminal",
                        "process_name": "WindowsTerminal.exe"}
            return {"ok": True, "found": True, "title": self.active_title,
                    "process_name": self.active_process}
        if name == "open_program":
            return {"ok": True, "verified": True, "verification": "process_lookup"}
        if name in {"ui_focus_window", "ui_focus_element"}:
            return {"ok": True, "verified": True, "verification": "focus"}
        if name == "keyboard_type":
            if self.confirmation and not confirmed:
                return {"ok": True, "confirmation_required": True,
                        "token": "mission-confirm-token"}
            self.typed.append(arguments["text"])
            return {"ok": True, "verified": True, "verification": "input_sent"}
        if name == "keyboard_hotkey":
            if arguments.get("keys") == ["ctrl", "shift", "s"]:
                self.active_title = "Salvar como"
            else:
                self.active_title = "Sem título - Bloco de notas"
            return {"ok": True, "verified": True, "verification": "hotkey_sent"}
        if name == "keyboard_press":
            content = self.typed[0]
            path = Path(self.typed[1])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self.active_title = "teste.txt - Bloco de notas"
            return {"ok": True, "verified": True, "verification": "key_sent"}
        return {"ok": False, "error": "unexpected_tool"}

    def confirm(self, token, task_id="desktop"):
        assert token == "mission-confirm-token"
        self.confirmation = False
        return self.execute_tool("keyboard_type", {"text": "Golden Jarvis funcionando"},
                                 confirmed=True)


class FakeBrowserService:
    def __init__(self, wrong_window=False, popup=False, anti_bot=False):
        self.registry = FakeRegistry({
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "ui_active_window", "ui_focus_window",
        })
        self.cancellation = CancellationToken()
        self.audit = SimpleNamespace(add=lambda **_kwargs: None)
        self.calls = []
        self.page_state_id = 1
        self.wrong_window = wrong_window
        self.popup = popup
        self.anti_bot = anti_bot

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        self.calls.append((name, dict(arguments), confirmed))
        if name == "browser_open":
            return {"ok": True, "started": True, "headless": False}
        if name == "browser_navigate":
            self.page_state_id += 1
            return {"ok": True, "url": "https://www.google.com/", "title": "Google"}
        if name == "browser_health":
            return {"ok": True, "started": True, "headless": False,
                    "current_url": "https://www.google.com/search?q=OpenAI",
                    "page_title": "OpenAI - Google Search",
                    "page_state_id": self.page_state_id}
        if name == "ui_active_window":
            if self.wrong_window:
                return {"ok": True, "found": True, "title": "Codex",
                        "process_name": "Codex.exe"}
            return {"ok": True, "found": True, "title": "Google - Microsoft Edge",
                    "process_name": "msedge.exe"}
        if name == "ui_focus_window":
            return {"ok": False} if self.wrong_window else {"ok": True, "focused": True}
        if name == "browser_get_elements":
            if self.popup:
                return {"ok": True, "elements": [
                    {"ref": "e2", "tag": "button", "text": "Aceitar"},
                    {"ref": "e3", "tag": "button", "text": "Rejeitar"},
                ]}
            return {"ok": True, "elements": [
                {"ref": "e1", "tag": "input", "input_type": "text",
                 "aria_label": "Search", "placeholder": "Search"},
            ]}
        if name == "browser_search":
            self.page_state_id += 1
            return {"ok": True, "navigation_changed": True,
                    "url": "https://www.google.com/search?q=OpenAI",
                    "title": "OpenAI - Google Search", "page_state_id": self.page_state_id}
        if name == "browser_get_page_info":
            return {"ok": True, "page": {
                "url": "https://www.google.com/search?q=OpenAI",
                "title": "OpenAI - Google Search",
                "text": "Verify you are human" if self.anti_bot else "",
                "links": [
                    {"text": "OpenAI official", "href": "https://openai.com/"},
                    {"text": "OpenAI API", "href": "https://platform.openai.com/"},
                    {"text": "OpenAI Wikipedia", "href": "https://en.wikipedia.org/wiki/OpenAI"},
                ],
            }}
        return {"ok": False, "error": "unexpected_tool"}


def test_planner_creates_bounded_registered_steps(tmp_path):
    service = FakeService(tmp_path)
    mission = ComputerMissionPlanner(service.registry, documents_dir=tmp_path).plan(MISSION)

    assert mission.status is MissionStatus.PENDING
    assert len(mission.steps) == 12
    assert mission.max_steps == 30
    assert mission.risk_level == "WRITE"
    assert [step.action_type for step in mission.steps][-1] == "verify_file"
    assert mission.steps[-1].expected_state["content"] == "Golden Jarvis funcionando"


def test_browser_planner_reuses_registered_browser_capabilities():
    service = FakeBrowserService()
    mission = ComputerMissionPlanner(service.registry).plan(BROWSER_MISSION)
    assert mission.result["browser_mission"] is True
    assert mission.result["search_query"] == "OpenAI"
    assert [step.action_type for step in mission.steps] == [
        "browser_open", "browser_navigate", "focus_browser", "observe_browser",
        "ground_search_field", "browser_search", "observe_browser",
        "browser_get_page_info", "verify_browser_results",
    ]


def test_browser_executor_grounds_search_and_extracts_three_titles():
    service = FakeBrowserService()
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-mission-test")
    assert result["ok"] is True
    assert result["mission"]["status"] == MissionStatus.COMPLETED.value
    assert result["mission"]["result"]["result_count"] == 3
    assert result["mission"]["result"]["titles"] == [
        "OpenAI official", "OpenAI API", "OpenAI Wikipedia"]
    assert any(name == "browser_search" and args["ref"] == "e1"
               for name, args, _ in service.calls)


def test_browser_executor_blocks_when_focus_guard_fails():
    service = FakeBrowserService(wrong_window=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-focus-test")
    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.BLOCKED.value
    assert result["mission"]["error"] == "ACTION_LOOP_DETECTED"


def test_browser_executor_stops_for_unexpected_consent_popup():
    service = FakeBrowserService(popup=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-popup-test")
    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.WAITING_CONFIRMATION.value
    assert result["mission"]["error"] == "USER_CONFIRMATION_REQUIRED"


def test_browser_executor_stops_for_anti_bot_verification():
    service = FakeBrowserService(anti_bot=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-anti-bot-test")

    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.WAITING_CONFIRMATION.value
    assert result["mission"]["error"] == "USER_CONFIRMATION_REQUIRED"


def test_executor_runs_one_step_at_a_time_and_verifies_file(tmp_path):
    service = FakeService(tmp_path)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))

    result = executor.run(MISSION, task_id="mission-test")

    assert result["ok"] is True
    assert result["mission"]["status"] == MissionStatus.COMPLETED.value
    assert result["mission"]["result"] == {
        "mission_completed": True, "file_exists": True, "content_valid": True}
    assert sum(name == "keyboard_type" for name, _, _ in service.calls) == 2
    assert Path(tmp_path, "teste.txt").read_text(encoding="utf-8") == "Golden Jarvis funcionando"


def test_executor_stops_at_security_confirmation_without_bypass(tmp_path):
    service = FakeService(tmp_path, confirmation=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))

    result = executor.run(MISSION)

    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.WAITING_CONFIRMATION.value
    assert result["mission"]["pending_confirmation"] is True
    assert not Path(tmp_path, "teste.txt").exists()
    assert service.calls[-1][0] == "keyboard_type"
    assert service.calls[-1][2] is False


def test_executor_can_resume_after_confirmation(tmp_path):
    service = FakeService(tmp_path, confirmation=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    waiting = executor.run(MISSION)

    resumed = executor.resume(waiting["mission"]["mission_id"], "mission-confirm-token")

    assert resumed["ok"] is True
    assert resumed["mission"]["status"] == MissionStatus.COMPLETED.value


def test_cancel_fails_safe_between_steps(tmp_path):
    service = FakeService(tmp_path)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    service.cancellation.request_cancel()

    result = executor.run(MISSION)

    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.CANCELLED.value
    assert service.calls == []


def test_repeated_same_window_failure_blocks_as_action_loop(tmp_path):
    service = FakeService(tmp_path, wrong_window=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))

    result = executor.run(MISSION)

    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.BLOCKED.value
    assert result["mission"]["error"] == "ACTION_LOOP_DETECTED"
    assert result["mission"]["steps"][0]["status"] == MissionStepStatus.COMPLETED.value
    assert result["mission"]["steps"][2]["status"] == MissionStepStatus.BLOCKED.value


def test_known_folder_documents_resolution_is_not_userprofile_hardcoded(monkeypatch, tmp_path):
    monkeypatch.setattr("jarvis_core.computer_use_mission.known_documents_dir", lambda: tmp_path)
    service = FakeService(tmp_path)
    mission = ComputerMissionPlanner(service.registry).plan(MISSION)
    assert mission.steps[-1].target == str(tmp_path / "teste.txt")
    assert mission.steps[-1].expected_state["path"] == str(tmp_path / "teste.txt")


def test_redirected_documents_resolution_can_be_mocked(tmp_path):
    service = FakeService(tmp_path / "OneDrive" / "Documents")
    planner = ComputerMissionPlanner(service.registry, documents_dir=service.documents_dir)
    mission = planner.plan(MISSION)
    assert Path(mission.steps[-1].target).parent == tmp_path / "OneDrive" / "Documents"


def test_path_not_found_is_audited_and_reresolved(monkeypatch, tmp_path):
    service = FakeService(tmp_path / "resolved")
    folders = iter((tmp_path / "old", tmp_path / "resolved"))
    monkeypatch.setattr(
        "jarvis_core.computer_use_mission.known_documents_dir", lambda: next(folders))
    planner = ComputerMissionPlanner(service.registry)
    executor = ComputerMissionExecutor(service, planner)
    mission = planner.plan(MISSION)
    failure = {"ok": False, "error": "PATH_NOT_FOUND"}
    assert executor._is_path_not_found(failure)
    assert executor._reresolve_path(mission)
    assert mission.steps[-1].target == str(tmp_path / "resolved" / "teste.txt")


def test_path_not_found_recovery_rechecks_step_and_records_audit(tmp_path):
    service = FakeService(tmp_path)
    planner = ComputerMissionPlanner(service.registry, documents_dir=tmp_path)
    executor = ComputerMissionExecutor(service, planner)
    mission = planner.plan(MISSION)
    audit_rows = []
    service.audit = SimpleNamespace(add=lambda **row: audit_rows.append(row))
    step = mission.steps[-1]
    failure = {"ok": False, "error": "PATH_NOT_FOUND"}
    executor._audit_step(mission, step, failure, "path_not_found")
    assert audit_rows[-1]["status"] == "path_not_found"
    assert executor._recover_path_not_found(mission, step, failure)
    assert mission.current_step == 8
