from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jarvis_core.computer_use_mission import (
    ComputerMissionExecutor,
    ComputerMissionPlanner,
    MissionContext,
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

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False,
                     authorization_scope=""):
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
    def __init__(self, wrong_window=False, popup=False, anti_bot=False, consent=False,
                 unknown_consent=False):
        self.registry = FakeRegistry({
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "browser_click",
            "browser_record_window", "browser_wait_for_results",
            "ui_active_window", "ui_focus_window",
        })
        self.cancellation = CancellationToken()
        self.audit = SimpleNamespace(add=lambda **_kwargs: None)
        self.calls = []
        self.page_state_id = 1
        self.wrong_window = wrong_window
        self.popup = popup
        self.anti_bot = anti_bot
        self.consent = consent
        self.unknown_consent = unknown_consent
        self.provider = "google"
        self.current_url = "https://www.google.com/"

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        self.calls.append((name, dict(arguments), confirmed))
        if name == "browser_open":
            return {"ok": True, "started": True, "headless": False}
        if name == "browser_navigate":
            self.page_state_id += 1
            self.current_url = arguments["url"]
            self.provider = "bing" if "bing.com" in self.current_url else "duckduckgo" if "duckduckgo" in self.current_url else "google"
            return {"ok": True, "url": self.current_url, "title": self.provider.title()}
        if name == "browser_health":
            return {"ok": True, "started": True, "headless": False,
                    "provider": "chrome", "browser_provider": "CHROME",
                    "current_url": self.current_url,
                    "page_title": "OpenAI - Search",
                    "process_id": 100,
                    "page_state_id": self.page_state_id}
        if name == "ui_active_window":
            if self.wrong_window:
                return {"ok": True, "found": True, "title": "Codex",
                        "process_name": "Codex.exe"}
            return {"ok": True, "found": True, "title": "Google - Google Chrome",
                    "process_name": "chrome.exe", "pid": 100, "handle": 200}
        if name == "ui_focus_window":
            return {"ok": False} if self.wrong_window else {"ok": True, "focused": True}
        if name == "browser_get_elements":
            if self.popup or self.unknown_consent or (self.consent and self.provider == "bing"):
                if self.unknown_consent:
                    return {"ok": True, "elements": [
                        {"ref": "e2", "tag": "button", "text": "Permitir notificações"},
                        {"ref": "e1", "tag": "textarea", "placeholder": "Pesquisar"},
                    ]}
                return {"ok": True, "elements": [
                    {"ref": "e2", "tag": "button", "text": "Aceitar"},
                    {"ref": "e3", "tag": "button", "text": "Rejeitar"},
                    {"ref": "e1", "tag": "textarea", "placeholder": "Pesquisar"},
                ]}
            return {"ok": True, "elements": [
                {"ref": "e1", "tag": "input", "input_type": "text",
                 "aria_label": "Search", "placeholder": "Search"},
            ]}
        if name == "browser_search":
            self.page_state_id += 1
            self.current_url = f"https://{self.provider}.com/search?q=OpenAI"
            return {"ok": True, "navigation_changed": True,
                    "url": self.current_url,
                    "title": "OpenAI - Google Search", "page_state_id": self.page_state_id}
        if name == "browser_click":
            if self.consent:
                self.consent = False
            return {"ok": True, "verified": True, "verification": "consent_target_clicked"}
        if name == "browser_record_window":
            return {"ok": True, "process_id": arguments.get("pid", 0),
                    "window_id": arguments.get("window_id", 0)}
        if name == "browser_wait_for_results":
            return {"ok": True, "result_candidate_count": 3,
                    "barrier_type": "NONE", "result_page_ready": True}
        if name == "browser_get_page_info":
            return {"ok": True, "page": {
                "url": self.current_url,
                "title": "OpenAI - Google Search",
                "text": ("Verify you are human" if self.anti_bot and self.provider == "google"
                          else "Cookies: Permitir notificações" if self.unknown_consent
                          else "Cookies: Aceitar Rejeitar" if self.popup
                          else "OpenAI search results"),
                "links": [
                    {"text": "OpenAI official", "href": "https://openai.com/",
                     "visible": True, "result_candidate": True},
                    {"text": "OpenAI API", "href": "https://platform.openai.com/",
                     "visible": True, "result_candidate": True},
                    {"text": "OpenAI Wikipedia", "href": "https://en.wikipedia.org/wiki/OpenAI",
                     "visible": True, "result_candidate": True},
                ],
            }}
        return {"ok": False, "error": "unexpected_tool"}


class FakeMultiAppService:
    def __init__(self, documents_dir, wrong_window=False, *, editor_empty=False,
                 stale_editor=False, pre_save_mismatch=False, confirm_keyboard=False,
                 confirm_new_document=False):
        self.registry = FakeRegistry({
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "browser_click",
            "browser_record_window", "browser_wait_for_results", "ui_active_window",
            "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
            "ui_type_editor", "ui_invoke_element", "ui_classify_dialog", "ui_list_elements", "open_program", "keyboard_type",
            "keyboard_hotkey", "keyboard_press",
        })
        self.cancellation = CancellationToken()
        self.audit_events = []
        self.audit = SimpleNamespace(add=lambda **kwargs: self.audit_events.append(kwargs))
        self.documents_dir = Path(documents_dir)
        self.calls = []
        self.page_state_id = 1
        self.current_url = "https://www.google.com/"
        self.active_process = "chrome.exe"
        self.active_title = "Google - Google Chrome"
        self.wrong_window = wrong_window
        self.typed = []
        self.editor_text = ""
        self.editor_identity = "document-1"
        self.document_counter = 1
        self.select_all = False
        self.editor_empty = editor_empty
        self.stale_editor = stale_editor
        self.pre_save_mismatch = pre_save_mismatch
        self.confirm_keyboard = confirm_keyboard
        self.confirm_new_document = confirm_new_document
        self.editor_reads = 0

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        self.calls.append((name, dict(arguments), confirmed))
        if name == "browser_open":
            return {"ok": True, "started": True, "headless": False}
        if name == "browser_navigate":
            self.page_state_id += 1
            self.current_url = arguments["url"]
            return {"ok": True, "url": self.current_url}
        if name == "browser_health":
            return {"ok": True, "started": True, "headless": False,
                    "provider": "chrome", "browser_provider": "CHROME",
                    "current_url": self.current_url,
                    "page_title": "Python Search", "process_id": 100,
                    "page_state_id": self.page_state_id}
        if name == "ui_focus_window":
            if arguments.get("window") == "notepad" and not self.wrong_window:
                self.active_process = "notepad.exe"
                self.active_title = "Sem título - Bloco de notas"
            return {"ok": True, "focused": True}
        if name == "ui_active_window":
            process = "chrome.exe" if self.wrong_window else self.active_process
            return {"ok": True, "found": True, "process_name": process,
                    "title": self.active_title, "pid": 100, "handle": 200}
        if name == "open_program":
            return {"ok": True, "verified": True, "verification": "process_lookup"}
        if name == "browser_record_window":
            return {"ok": True, "process_id": arguments.get("pid", 0),
                    "window_id": arguments.get("window_id", 0)}
        if name == "browser_get_elements":
            return {"ok": True, "elements": [{
                "ref": "e1", "tag": "input", "input_type": "text",
                "aria_label": "Search", "placeholder": "Search", "visible": True,
            }]}
        if name == "browser_search":
            self.page_state_id += 1
            self.current_url = "https://duckduckgo.com/?q=Python"
            return {"ok": True, "navigation_changed": True,
                    "url": self.current_url, "page_state_id": self.page_state_id}
        if name == "browser_wait_for_results":
            return {"ok": True, "result_candidate_count": 3,
                    "barrier_type": "NONE", "result_page_ready": True}
        if name == "browser_get_page_info":
            return {"ok": True, "page": {
                "url": self.current_url, "title": "Python Search",
                "text": "Python 3.14.7 official results",
                "links": [
                    {"text": "Welcome to Python.org", "href": "https://www.python.org/",
                     "visible": True, "result_candidate": True},
                    {"text": "Python 3.14.7 Python 3.14.7 release",
                     "href": "https://www.python.org/downloads/release/python-3147/",
                     "visible": True, "result_candidate": True},
                ],
            }}
        if name == "ui_focus_element":
            return {"ok": True, "verified": True, "verification": "focus"}
        if name == "ui_invoke_element":
            if arguments.get("target") == "Salvar":
                path = Path(self.typed[-1])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(self.editor_text, encoding="utf-8")
                self.active_title = path.name + " - Bloco de notas"
            return {"ok": True, "verified": True, "verification": "invoke",
                    "control_type": arguments.get("control_type")}
        if name == "ui_focus_editor":
            if self.wrong_window:
                return {"ok": False, "reason": "process_mismatch"}
            return {"ok": True, "focused": True, "editor": {
                "document_identity": self.editor_identity,
                "content_state_id": "state-before",
            }, "text": self.editor_text}
        if name == "ui_type_editor":
            if self.wrong_window:
                return {"ok": False, "reason": "process_mismatch"}
            if self.confirm_keyboard and not confirmed:
                return {"ok": True, "confirmation_required": True,
                        "token": "multi-app-confirm-token"}
            self.editor_text = str(arguments.get("text") or "")
            self.typed.append(self.editor_text)
            return {"ok": True, "verified": True,
                    "verification": "uia_editor_typed_and_read",
                    "editor": {"document_identity": self.editor_identity,
                                "content_state_id": "state-after"},
                    "text": self.editor_text}
        if name == "ui_read_editor":
            if self.wrong_window:
                return {"ok": False, "found": False, "reason": "process_mismatch"}
            self.editor_reads += 1
            identity = self.editor_identity
            text = self.editor_text
            if self.stale_editor and self.editor_reads > 1:
                identity = "document-unexpected-new-tab"
            if self.pre_save_mismatch and self.editor_reads > 1:
                text = "conteudo divergente"
            return {"ok": True, "found": True, "verified": True,
                    "window": {"handle": 200, "pid": 100,
                                "process_name": "notepad.exe"},
                    "editor": {"document_identity": identity,
                                "content_state_id": "state-after"},
                    "text": "" if self.editor_empty else text,
                    "empty": self.editor_empty or text == ""}
        if name == "ui_list_elements":
            return {"ok": True, "found": True, "elements": [
                {"control_type": "TabItem", "label": self.editor_identity,
                 "identity": ("tab", self.editor_identity)}]}
        if name == "ui_classify_dialog":
            return {"ok": True, "found": False, "dialog_type": "NONE",
                    "visible_controls": []}
        if name == "keyboard_type":
            if self.confirm_keyboard and not confirmed:
                return {"ok": True, "confirmation_required": True,
                        "token": "multi-app-confirm-token"}
            value = str(arguments.get("text") or "")
            if self.active_title == "Salvar como":
                self.typed.append(value)
            else:
                self.editor_text = value if self.select_all else self.editor_text + value
                self.select_all = False
                if value not in self.typed:
                    self.typed.append(value)
            return {"ok": True, "verified": True, "verification": "input_sent"}
        if name == "keyboard_hotkey":
            if (arguments.get("keys") == ["ctrl", "n"] and
                    self.confirm_new_document and not confirmed):
                return {"ok": True, "confirmation_required": True,
                        "token": "new-document-confirm-token"}
            if arguments.get("keys") == ["ctrl", "shift", "s"]:
                self.active_title = "Salvar como"
            elif arguments.get("keys") == ["ctrl", "n"]:
                self.document_counter += 1
                self.editor_identity = f"document-{self.document_counter}"
                self.editor_text = ""
            elif arguments.get("keys") == ["ctrl", "a"]:
                self.select_all = True
            return {"ok": True, "verified": True, "verification": "hotkey_sent"}
        if name == "keyboard_press":
            path = self.documents_dir / ("titulo_python.txt" if any(
                "Welcome to Python.org" in item for item in self.typed) else "pesquisa_python.txt")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.editor_text, encoding="utf-8")
            self.active_title = path.name + " - Bloco de notas"
            return {"ok": True, "verified": True, "verification": "key_sent"}
        return {"ok": False, "error": "unexpected_tool"}

    def confirm(self, token, task_id="desktop"):
        if token == "new-document-confirm-token":
            self.confirm_new_document = False
            return self.execute_tool("keyboard_hotkey", {"keys": ["ctrl", "n"]},
                                     confirmed=True)
        assert token == "multi-app-confirm-token"
        self.confirm_keyboard = False
        return self.execute_tool("ui_type_editor", {
                                  "window": "notepad",
                                  "expected_process": "notepad",
                                  "text": "Versão atual do Python: Python 3.14.7",
                                  "interval": 0.03},
                                 confirmed=True)


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
    assert mission.steps[0].args["provider"] == "chrome"
    assert mission.steps[1].args["url"] == "https://www.google.com"


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
    assert any(name == "browser_wait_for_results" for name, _, _ in service.calls)


def test_browser_extractor_rejects_url_as_result_title():
    service = FakeBrowserService()
    executor = ComputerMissionExecutor(service)
    mission = ComputerMissionPlanner(service.registry).plan(BROWSER_MISSION)
    page = {
        "url": "https://duckduckgo.com/?q=OpenAI",
        "title": "OpenAI at DuckDuckGo",
        "text": "OpenAI search results",
        "links": [
            {"text": "OpenAI official", "href": "https://openai.com/",
             "visible": True, "result_candidate": True},
            {"text": "https://openai.com", "href": "https://openai.com/about/",
             "visible": True, "result_candidate": True},
        ],
    }
    result = executor._extract_browser_results(mission, page, minimum=2)
    assert result["ok"] is False
    assert result["titles"] == ["OpenAI official"]


def test_browser_executor_blocks_when_focus_guard_fails():
    service = FakeBrowserService(wrong_window=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-focus-test")
    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.BLOCKED.value
    assert result["mission"]["error"] == "CHROME_FOCUS_GUARD_FAILED"


def test_browser_executor_stops_for_unexpected_consent_popup():
    service = FakeBrowserService(unknown_consent=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-popup-test")
    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.WAITING_CONFIRMATION.value
    assert result["mission"]["error"] == "USER_CONFIRMATION_REQUIRED"


def test_browser_executor_falls_back_for_anti_bot_verification():
    service = FakeBrowserService(anti_bot=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-anti-bot-test")

    assert result["ok"] is True
    assert result["mission"]["status"] == MissionStatus.COMPLETED.value
    assert result["mission"]["result"]["search_provider"] == "bing"


def test_browser_executor_rejects_cookie_consent_and_keeps_chrome():
    service = FakeBrowserService(anti_bot=True, consent=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-consent-test")

    assert result["ok"] is True
    assert result["mission"]["status"] == MissionStatus.COMPLETED.value
    assert result["mission"]["result"]["search_provider"] == "bing"
    assert result["mission"]["result"]["result_count"] == 3
    assert all(name != "ui_focus_window" or args.get("window") == "chrome"
               for name, args, _ in service.calls)


def test_browser_executor_falls_back_inside_chrome_after_anti_bot():
    service = FakeBrowserService(anti_bot=True)
    executor = ComputerMissionExecutor(service)
    result = executor.run(BROWSER_MISSION, task_id="browser-fallback-test")

    assert result["ok"] is True
    assert result["mission"]["status"] == MissionStatus.COMPLETED.value
    assert result["mission"]["result"]["search_provider"] == "bing"
    assert result["mission"]["result"]["provider_health"]
    assert all(args.get("provider") != "edge" for name, args, _ in service.calls
               if name == "browser_open")


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


MULTI_APP_MISSION = (
    "Jarvis, abra o Google Chrome, pesquise qual é a versão estável atual do Python, "
    "pegue essa informação, abra o Bloco de Notas, escreva Versão atual do Python: "
    "<resultado>, salve como pesquisa_python.txt nos Documentos e confirme que foi salvo."
)


def test_multi_app_planner_creates_one_context_and_handoff_plan(tmp_path):
    service = FakeMultiAppService(tmp_path)
    mission = ComputerMissionPlanner(service.registry, documents_dir=tmp_path).plan(
        MULTI_APP_MISSION)
    assert mission.result["multi_app_mission"] is True
    assert mission.context.mission_id == mission.mission_id
    assert mission.result["value_key"] == "python_version"
    assert [step.action_type for step in mission.steps].count("handoff_to_notepad") == 1
    assert mission.steps[-1].action_type == "verify_cross_app_file"


def test_multi_app_executor_preserves_observed_value_and_provenance(tmp_path):
    service = FakeMultiAppService(tmp_path)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    result = executor.run(MULTI_APP_MISSION, task_id="multi-app-test")
    assert result["ok"] is True
    mission = result["mission"]
    assert mission["status"] == MissionStatus.COMPLETED.value
    assert mission["result"]["python_version"] == "Python 3.14.7"
    assert mission["result"]["cross_app_data_match"] is True
    assert mission["context"]["current_app"] == "notepad"
    assert mission["context"]["variables"]["python_version"]["kind"] == "OBSERVED_VALUE"
    assert mission["context"]["variables"]["python_version"]["source_app"] == "chrome"
    assert Path(tmp_path, "pesquisa_python.txt").read_text(encoding="utf-8") == (
        "Versão atual do Python: Python 3.14.7")
    event_names = [event["tool"] for event in service.audit_events]
    assert "CONTEXT_VALUE_CREATED" in event_names
    assert "CONTEXT_VALUE_CONSUMED" in event_names
    assert "APP_HANDOFF_STARTED" in event_names
    assert "APP_HANDOFF_COMPLETED" in event_names


def test_keyboard_success_but_empty_editor_blocks_save(tmp_path):
    service = FakeMultiAppService(tmp_path, editor_empty=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    result = executor.run(MULTI_APP_MISSION, task_id="empty-editor-test")

    assert result["ok"] is False
    assert result["mission"]["error"] == "EDITOR_CONTENT_EMPTY"
    assert not any(name == "keyboard_hotkey" and args.get("keys") == ["ctrl", "shift", "s"]
                   for name, args, _ in service.calls)
    assert result["mission"]["context"]["artifacts"]["text_input_sent"] is True
    assert result["mission"]["context"]["artifacts"].get("editor_content_verified") is not True


def test_pre_save_mismatch_blocks_save_without_stale_file(tmp_path):
    service = FakeMultiAppService(tmp_path, pre_save_mismatch=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    result = executor.run(MULTI_APP_MISSION, task_id="pre-save-mismatch-test")

    assert result["ok"] is False
    assert result["mission"]["error"] == "EDITOR_CONTENT_MISMATCH"
    assert not Path(tmp_path, "pesquisa_python.txt").exists()


def test_confirmation_resume_still_verifies_custom_editor_step(tmp_path):
    service = FakeMultiAppService(tmp_path, confirm_keyboard=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    waiting = executor.run(MULTI_APP_MISSION, task_id="custom-confirmation-test")

    assert waiting["mission"]["status"] == MissionStatus.WAITING_CONFIRMATION.value
    resumed = executor.resume(waiting["mission"]["mission_id"],
                              "multi-app-confirm-token")

    assert resumed["ok"] is True
    assert resumed["mission"]["result"]["cross_app_data_match"] is True
    assert resumed["mission"]["context"]["artifacts"]["editor_content_verified"] is True


def test_confirmation_resume_revalidates_preexisting_document_before_new_tab(tmp_path):
    service = FakeMultiAppService(tmp_path, confirm_new_document=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    waiting = executor.run(MULTI_APP_MISSION, task_id="new-document-confirmation-test")

    assert waiting["mission"]["status"] == MissionStatus.WAITING_CONFIRMATION.value
    resumed = executor.resume(waiting["mission"]["mission_id"],
                              "new-document-confirm-token")

    assert resumed["ok"] is True
    assert resumed["mission"]["result"]["document_ownership"] == "OWNED_BY_CURRENT_MISSION"
    assert resumed["mission"]["result"]["cross_app_data_match"] is True


def test_unexpected_new_editor_document_is_blocked_before_save(tmp_path):
    service = FakeMultiAppService(tmp_path, stale_editor=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    result = executor.run(MULTI_APP_MISSION, task_id="new-tab-test")

    assert result["ok"] is False
    assert result["mission"]["error"] == "DOCUMENT_IDENTITY_MISMATCH"
    assert not Path(tmp_path, "pesquisa_python.txt").exists()


def test_multi_app_executor_supports_dynamic_title_mission(tmp_path):
    service = FakeMultiAppService(tmp_path)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    request = (
        "Jarvis, pesquise no Chrome o título principal da página oficial do Python, "
        "abra o Bloco de Notas, escreva o título encontrado e salve como titulo_python.txt "
        "nos Documentos."
    )
    result = executor.run(request, task_id="multi-app-title-test")
    assert result["ok"] is True
    assert result["mission"]["result"]["python_page_title"] == "Welcome to Python.org"
    assert Path(tmp_path, "titulo_python.txt").read_text(encoding="utf-8") == (
        "Welcome to Python.org")


def test_title_mission_resolves_url_only_result_to_official_page_title(tmp_path):
    service = FakeMultiAppService(tmp_path)
    original = service.execute_tool

    def execute_tool(name, arguments, *args, **kwargs):
        if name == "browser_get_page_info" and service.current_url.startswith("https://duckduckgo.com/"):
            return {"ok": True, "page": {
                "url": service.current_url,
                "title": "Python Search",
                "text": "Python official results",
                "links": [{
                    "text": "https://www.python.org",
                    "href": "https://www.python.org/",
                    "visible": True, "result_candidate": True,
                }],
            }}
        if name == "browser_get_page_info" and service.current_url == "https://www.python.org/":
            return {"ok": True, "page": {
                "url": service.current_url,
                "title": "Welcome to Python.org",
                "text": "Python official homepage",
                "links": [],
            }}
        return original(name, arguments, *args, **kwargs)

    service.execute_tool = execute_tool
    service.current_url = "https://duckduckgo.com/?q=Python"
    mission = ComputerMissionPlanner(service.registry, documents_dir=tmp_path).plan(
        "Jarvis, pesquise no Chrome o título principal da página oficial do Python, "
        "abra o Bloco de Notas, escreva o título encontrado e salve como "
        "titulo_python.txt nos Documentos.")
    mission.context.store_variable(
        "python_page_title", "https://www.python.org", kind="OBSERVED_VALUE",
        source_app="chrome", source_type="browser_result",
        source_url="https://www.python.org/", confidence="verified")
    mission.result["python_page_title"] = "https://www.python.org"
    step = next(item for item in mission.steps if item.action_type == "extract_mission_value")
    result = ComputerMissionExecutor(service)._extract_mission_value(mission, step)

    assert result["ok"] is True
    assert result["value"] == "Welcome to Python.org"
    assert any(name == "browser_navigate" and args["url"] == "https://www.python.org/"
               for name, args, _ in service.calls)


def test_missing_and_stale_mission_values_fail_closed(tmp_path):
    service = FakeMultiAppService(tmp_path)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    mission = ComputerMissionPlanner(service.registry, documents_dir=tmp_path).plan(
        MULTI_APP_MISSION)
    rendered, error, _ = executor._render_template(mission, "{{missing_value}}")
    assert rendered is None
    assert error == "MISSING_MISSION_VARIABLE"
    mission.context.store_variable("python_version", "Python 3.14.7", kind="OBSERVED_VALUE")
    mission.context.invalidate("python_version", "test invalidation")
    rendered, error, _ = executor._render_template(mission, "{{python_version}}")
    assert rendered is None
    assert error == "STALE_CONTEXT_DETECTED"


def test_wrong_app_write_is_rejected_before_keyboard_input(tmp_path):
    service = FakeMultiAppService(tmp_path, wrong_window=True)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    mission = ComputerMissionPlanner(service.registry, documents_dir=tmp_path).plan(
        MULTI_APP_MISSION)
    mission.context.store_variable("python_version", "Python 3.14.7", kind="OBSERVED_VALUE")
    step = next(item for item in mission.steps if item.action_type == "type_mission_template")
    result = executor._type_mission_template(mission, step, "wrong-app-test")
    assert result["ok"] is False
    assert result["error"] == "CORRECT_WINDOW_NOT_FOCUSED"
    assert not any(name == "keyboard_type" for name, _, _ in service.calls)


def test_app_switch_loop_and_cancel_fail_closed(tmp_path):
    service = FakeMultiAppService(tmp_path)
    executor = ComputerMissionExecutor(
        service, ComputerMissionPlanner(service.registry, documents_dir=tmp_path))
    mission = ComputerMissionPlanner(service.registry, documents_dir=tmp_path).plan(
        MULTI_APP_MISSION)
    mission.context.app_switches = executor.MAX_APP_SWITCHES
    step = next(item for item in mission.steps if item.action_type == "handoff_to_notepad")
    assert executor._handoff_to_notepad(mission, step)["error"] == "APP_SWITCH_LOOP_DETECTED"
    mission.context.app_switches = 0
    service.cancellation.request_cancel()
    assert executor._handoff_to_notepad(mission, step)["error"] == "MISSION_CANCELLED"
    assert not any(name == "open_program" for name, _, _ in service.calls)


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
