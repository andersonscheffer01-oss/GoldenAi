from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from jarvis_core.cancellation import CancellationToken
from jarvis_core.computer_use_mission import (
    ActionState,
    CheckpointState,
    ComputerMission,
    ComputerMissionExecutor,
    ComputerMissionPlanner,
    ComputerMissionStep,
    MissionCheckpointStore,
    MissionContext,
    MissionStatus,
    MissionStepStatus,
    WorldStateChangeType,
)
from jarvis_core.computer_use_mission import _resolved_result_url
from jarvis_core.task_manager.database import TaskDatabase


LONG_MISSION = (
    "Jarvis, abra o Google Chrome, descubra na fonte oficial qual é a versão "
    "estável atual do Python, depois pesquise a página oficial do Ollama e "
    "pegue o título principal. Em seguida abra o Bloco de Notas, escreva um "
    "pequeno resumo com as duas informações, salve como resumo_pesquisa.txt "
    "nos Documentos e confirme que foi salvo."
)


class Registry:
    def __init__(self, *names):
        self.names = set(names)

    def get(self, name):
        return object() if name in self.names else None


class ProbeService:
    def __init__(self, database, *, process="notepad.exe"):
        self.registry = Registry(
            "ui_active_window", "keyboard_hotkey", "browser_health",
            "ui_focus_window", "browser_record_window",
        )
        self.cancellation = CancellationToken()
        self.task_manager = SimpleNamespace(database=database)
        self.audit_events = []
        self.audit = SimpleNamespace(add=lambda **kwargs: self.audit_events.append(kwargs))
        self.calls = []
        self.side_effects = 0
        self.page_state_id = 1
        self.process = process

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        self.calls.append((name, dict(arguments), confirmed))
        if name == "ui_active_window":
            title = "Google Chrome" if self.process == "chrome.exe" else "Sem título - Bloco de notas"
            return {"ok": True, "found": True, "process_name": self.process,
                    "title": title, "pid": 10, "handle": 20}
        if name == "keyboard_hotkey":
            self.side_effects += 1
            return {"ok": True, "verified": True, "verification": "hotkey_sent"}
        if name == "browser_health":
            return {"ok": True, "started": True, "provider": "chrome",
                    "browser_provider": "CHROME", "process_id": 10,
                    "page_state_id": self.page_state_id,
                    "current_url": "https://www.google.com/"}
        if name == "ui_focus_window":
            return {"ok": True, "focused": True}
        if name == "browser_record_window":
            return {"ok": True, "process_id": 10, "window_id": 20}
        return {"ok": True, "verified": True}


class FixedPlanner:
    def __init__(self, factory):
        self.factory = factory

    def plan(self, request):
        return self.factory(request)

    def resolve_target_path(self, filename):
        return Path(filename)


def make_pause_mission(request):
    steps = [
        ComputerMissionStep("python-search", "Pesquisar Python", "logical_action"),
        ComputerMissionStep(
            "python-checkpoint", "Checkpoint Python", "checkpoint",
            args={"name": "CHECKPOINT_PYTHON_DONE"},
            requires=("python-search",),
        ),
        ComputerMissionStep(
            "ollama-search", "Pesquisar Ollama", "logical_action",
            requires=("python-checkpoint",),
        ),
    ]
    mission = ComputerMission(
        "mission-6d-test", request, MissionStatus.PENDING, time.time(), steps,
        max_steps=10,
    )
    mission.context.current_app = "chrome"
    mission.result["browser_page_state_id"] = 1
    return mission


def test_checkpoint_store_persists_integrity_and_excludes_runtime_fields(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    store = MissionCheckpointStore(database)
    context = MissionContext("mission-1", "request")
    context.store_variable("python_version", "Python 3.14.7", kind="OBSERVED_VALUE")
    snapshot = {
        "context": context.checkpoint_snapshot(),
        "window_id": 123,
        "screenshot": "runtime-data",
        "logical": "preserved",
    }

    record = store.save_checkpoint(
        mission_id="mission-1", mission_version=1, name="CHECKPOINT_PYTHON_DONE",
        current_step=3, next_step=4, context_revision=context.context_version,
        snapshot=snapshot,
    )

    loaded, error = store.load_resume_token(record["resume_token"])
    assert error == ""
    assert loaded["state"] == CheckpointState.VALID.value
    assert loaded["snapshot"]["logical"] == "preserved"
    assert "window_id" not in loaded["snapshot"]
    assert "screenshot" not in loaded["snapshot"]

    with database.connect() as db:
        db.execute(
            "UPDATE mission_checkpoints SET snapshot=? WHERE checkpoint_id=?",
            ('{"context": {"context_version": 1}, "logical": "tampered"}',
             record["checkpoint_id"]),
        )
    invalid, error = store.load(record["checkpoint_id"], "mission-1")
    assert invalid is None
    assert error == "CHECKPOINT_INVALID"


def test_checkpoint_context_revision_mismatch_fails_closed(tmp_path):
    store = MissionCheckpointStore(TaskDatabase(tmp_path / "golden_tasks.db"))
    context = MissionContext("mission-2", "request")
    context.store_variable("value", "observed", kind="OBSERVED_VALUE")
    record = store.save_checkpoint(
        mission_id="mission-2", mission_version=1, name="CHECKPOINT_CONTEXT",
        current_step=1, next_step=1, context_revision=context.context_version,
        snapshot={"context": context.checkpoint_snapshot()},
    )
    with store.database.connect() as db:
        db.execute(
            "UPDATE mission_checkpoints SET context_revision=? WHERE checkpoint_id=?",
            (context.context_version + 1, record["checkpoint_id"]),
        )
    loaded, error = store.load(record["checkpoint_id"], "mission-2")
    assert loaded is None
    assert error == "CHECKPOINT_INVALID"


def test_dependency_contract_blocks_without_running_action(tmp_path):
    service = ProbeService(TaskDatabase(tmp_path / "golden_tasks.db"))

    def factory(request):
        return ComputerMission(
            "dependency-mission", request, MissionStatus.PENDING, time.time(),
            [ComputerMissionStep(
                "write", "Write", "logical_action", requires=("missing",),
            )],
        )

    result = ComputerMissionExecutor(service, FixedPlanner(factory)).run("request")
    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.BLOCKED.value
    assert result["mission"]["error"] == "DEPENDENCY_NOT_SATISFIED"
    assert service.calls == []


def test_pause_and_durable_resume_do_not_repeat_completed_python_step(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    service = ProbeService(database, process="chrome.exe")
    planner = FixedPlanner(make_pause_mission)
    executor = ComputerMissionExecutor(service, planner)

    paused = executor.run(
        LONG_MISSION, task_id="mission-6d-test",
        pause_after_checkpoint="CHECKPOINT_PYTHON_DONE",
    )
    assert paused["ok"] is False
    assert paused["mission"]["status"] == MissionStatus.PAUSED.value
    assert paused["mission"]["current_step"] == 2
    token = paused["mission"]["resume_token"]
    assert token.startswith("mission-6d-test:")

    resumed = ComputerMissionExecutor(service, planner).resume(
        "mission-6d-test", token, task_id="mission-6d-test",
    )
    assert resumed["ok"] is True
    assert resumed["mission"]["status"] == MissionStatus.COMPLETED.value
    assert resumed["mission"]["result"]["recovered_from_checkpoint"] is True
    assert [name for name, _, _ in service.calls].count("logical_action") == 2


def test_verified_action_receipt_skips_duplicate_side_effect(tmp_path):
    service = ProbeService(TaskDatabase(tmp_path / "golden_tasks.db"))
    executor = ComputerMissionExecutor(service)
    mission = ComputerMission(
        "receipt-mission", "request", MissionStatus.PENDING, time.time(), [],
    )
    step = ComputerMissionStep(
        "open-document", "Open document", "keyboard_hotkey",
        expected_state={"process": "notepad"}, args={"keys": ["ctrl", "n"]},
    )

    first = executor._execute_tool_step(mission, step, "receipt-mission", None)
    executor._receipt_verified(mission, step, first)
    second = executor._execute_tool_step(mission, step, "receipt-mission", None)
    assert first["ok"] is True
    assert second["skipped"] is True
    assert second["verification"] == "STEP_SKIPPED_ALREADY_VERIFIED"
    assert service.side_effects == 1
    assert executor.persistence.receipt(mission.mission_id, step.step_id)[
        "result_state"] == ActionState.VERIFIED.value


def test_inflight_save_receipt_recovers_from_filesystem_without_repeating_save(tmp_path):
    target = tmp_path / "resumo_pesquisa.txt"
    target.write_text("Versão estável do Python: Python 3.14.7", encoding="utf-8")
    service = ProbeService(TaskDatabase(tmp_path / "golden_tasks.db"))
    executor = ComputerMissionExecutor(service)
    mission = ComputerMission(
        "recovery-mission", "request", MissionStatus.PENDING, time.time(), [],
    )
    mission.result.update({"target_path": str(target), "value_key": "python_version"})
    mission.context.store_variable("python_version", "Python 3.14.7", kind="OBSERVED_VALUE")
    mission.context.artifacts["rendered_text"] = {
        "value": target.read_text(encoding="utf-8"), "kind": "DERIVED_VALUE",
    }
    step = ComputerMissionStep(
        "confirm-save", "Confirm save", "ui_invoke_element", "save-button",
        args={"target": "Salvar", "control_type": "Button", "window": ""},
    )
    executor.persistence.save_receipt(
        mission_id=mission.mission_id, step_id=step.step_id,
        action_type=step.action_type, target=step.target,
        result_state=ActionState.IN_FLIGHT_UNKNOWN,
    )

    recovered = executor._execute_tool_step(mission, step, "recovery-mission", None)
    assert recovered["skipped"] is True
    assert recovered["verification"] == "ACTION_IN_FLIGHT_RECOVERED"
    assert service.side_effects == 0
    assert executor.persistence.receipt(mission.mission_id, step.step_id)[
        "result_state"] == ActionState.VERIFIED.value


def test_resume_rejects_stale_browser_state(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    service = ProbeService(database, process="chrome.exe")
    planner = FixedPlanner(make_pause_mission)
    executor = ComputerMissionExecutor(service, planner)
    paused = executor.run(
        LONG_MISSION, pause_after_checkpoint="CHECKPOINT_PYTHON_DONE",
    )
    token = paused["mission"]["resume_token"]
    service.page_state_id += 1
    result = ComputerMissionExecutor(service, planner).resume(
        "mission-6d-test", token,
    )
    assert result["ok"] is False
    assert result["mission"]["error"] == "STALE_BROWSER_STATE"


def test_long_plan_has_bounded_replan_and_step_contracts(tmp_path):
    names = {
        "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
        "browser_search", "browser_get_page_info", "browser_click",
        "browser_record_window", "browser_wait_for_results", "ui_active_window",
        "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
        "ui_invoke_element", "ui_classify_dialog", "ui_list_elements", "open_program",
        "keyboard_type", "keyboard_hotkey", "keyboard_press",
    }
    mission = ComputerMissionPlanner(Registry(*names), documents_dir=tmp_path).plan(LONG_MISSION)
    assert mission.result["long_workflow"] is True
    assert mission.result["max_replans"] == 2
    assert mission.max_steps == 60
    assert all(step.max_attempts <= 3 for step in mission.steps)
    assert any(step.step_id == "checkpoint-python" and
               "extract-python-value" in step.requires for step in mission.steps)
    assert any("python_version" in step.produces for step in mission.steps)


def test_documents_resolution_uses_known_folder_provider(monkeypatch, tmp_path):
    redirected = tmp_path / "OneDrive" / "Documents"
    redirected.mkdir(parents=True)
    monkeypatch.setattr(
        "jarvis_core.computer_use_mission.known_documents_dir",
        lambda: redirected,
    )
    planner = ComputerMissionPlanner(Registry(
        "open_program", "ui_active_window", "ui_focus_window", "ui_focus_element",
        "ui_dismiss_path_not_found", "keyboard_type", "keyboard_hotkey", "keyboard_press",
    ))
    mission = planner.plan(
        "Jarvis, abra o Bloco de Notas, escreva Golden Jarvis funcionando, "
        "salve como teste.txt e confirme que foi salvo."
    )
    assert planner.resolve_target_path("teste.txt") == redirected / "teste.txt"


def test_official_source_selection_resolves_search_provider_redirect():
    redirected = (
        "https://www.bing.com/ck/a?!&&u="
        "a1aHR0cHM6Ly93d3cucHl0aG9uLm9yZy9kb3dubG9hZHMv&ntb=1"
    )
    assert _resolved_result_url(redirected) == "https://www.python.org/downloads/"


def _recovery_mission(tmp_path):
    names = {
        "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
        "browser_search", "browser_get_page_info", "browser_click",
        "browser_record_window", "browser_wait_for_results", "ui_active_window",
        "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
        "ui_invoke_element", "ui_classify_dialog", "ui_list_elements", "open_program",
        "keyboard_type", "keyboard_hotkey", "keyboard_press",
    }
    planner = ComputerMissionPlanner(Registry(*names), documents_dir=tmp_path)
    mission = planner.plan(LONG_MISSION)
    mission.context.current_app = "notepad"
    mission.context.app_switches = 1
    mission.context.store_variable(
        "python_version", "Python 3.14.7", kind="OBSERVED_VALUE",
        source_app="chrome", source_type="browser_result",
        source_title="Python Release Python 3.14.7 | Python.org",
        source_url="https://www.python.org/downloads/latest/",
        source_state_id="python-state", valid_until_step=75,
    )
    mission.context.store_variable(
        "ollama_page_title", "Ollama", kind="OBSERVED_VALUE",
        source_app="chrome", source_type="browser_result",
        source_title="Ollama", source_url="https://ollama.com/",
        source_state_id="ollama-state", valid_until_step=75,
    )
    mission.context.artifacts.update({
        "mission_document_id": "old-document",
        "mission_window_id": 123,
        "mission_document_content_state_id": "old-content",
        "mission_document_created_by_mission": True,
        "pre_existing_document_ids": ["old-preexisting"],
        "rendered_text": {"value": "old text"},
    })
    mission.result["document_ownership"] = "OWNED_BY_CURRENT_MISSION"
    mission.current_step = next(
        index for index, step in enumerate(mission.steps)
        if step.step_id == "open-save-dialog"
    )
    return mission, planner


class ClosedNotepadProbe(ProbeService):
    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        if name == "ui_read_editor":
            self.calls.append((name, dict(arguments), confirmed))
            return {"found": False, "verified": False, "reason": "window_not_found"}
        return super().execute_tool(name, arguments, command, task_id, confirmed)


class ForegroundProbe(ProbeService):
    def __init__(self, database, *, user_active, owner, focused=False,
                 focus_ok=True):
        super().__init__(database)
        self.registry.names.add("ui_foreground_state")
        self.user_active = user_active
        self.owner = owner
        self.focused = focused
        self.focus_ok = focus_ok
        self.focus_calls = 0

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        if name == "ui_foreground_state":
            self.calls.append((name, dict(arguments), confirmed))
            return {
                "ok": True,
                "process_present": True,
                "window_present": True,
                "window_focused": self.focused,
                "window_state": ("WINDOW_EXISTS_FOREGROUND" if self.focused
                                  else "WINDOW_EXISTS_BACKGROUND"),
                "foreground_owner": self.owner,
                "foreground_epoch": 7,
                "user_active": self.user_active,
                "last_user_input_age_ms": 50 if self.user_active else 5000,
            }
        if name == "ui_focus_window":
            self.focus_calls += 1
            self.calls.append((name, dict(arguments), confirmed))
            return {"ok": self.focus_ok, "focused": self.focus_ok,
                    **({} if self.focus_ok else {"error": "FOCUS_ACQUIRE_FAILED"})}
        return super().execute_tool(name, arguments, command, task_id, confirmed)


class QuietForegroundProbe(ForegroundProbe):
    def __init__(self, database, *, ages, **kwargs):
        super().__init__(database, **kwargs)
        self.registry.names.add("ui_user_activity")
        self.ages = list(ages)

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        if name == "ui_user_activity":
            self.calls.append((name, dict(arguments), confirmed))
            age = self.ages.pop(0) if self.ages else 5000
            return {"ok": True, "user_active": age < 1500,
                    "last_user_input_age_ms": age,
                    "threshold_ms": arguments.get("threshold_ms")}
        return super().execute_tool(name, arguments, command, task_id, confirmed)


class BackgroundRecoveryProbe(ForegroundProbe):
    def __init__(self, database, *, ages=None, focus_ok=True,
                 editor_identity="(42, 329544)", **kwargs):
        super().__init__(database, focus_ok=focus_ok, **kwargs)
        self.registry.names.update({
            "ui_user_activity", "ui_read_editor", "ui_list_elements",
        })
        self.ages = list(ages or [])
        self.target_handle = 123
        self.target_pid = 10
        self.editor_identity = editor_identity
        self.editor_text = (
            "Versão estável do Python: Python 3.14.7\n"
            "Título principal do Ollama: Ollama"
        )
        self.editor_reads = 0
        self.security = SimpleNamespace(decision=lambda _tool: "allow")

    def _activity(self):
        age = self.ages.pop(0) if self.ages else 5000
        return {"ok": True, "user_active": age < 1500,
                "last_user_input_age_ms": age, "threshold_ms": 1500}

    def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
        if name == "ui_user_activity":
            self.calls.append((name, dict(arguments), confirmed))
            return self._activity()
        if name == "ui_foreground_state":
            self.calls.append((name, dict(arguments), confirmed))
            activity = self._activity()
            return {
                "ok": True, "process_present": True, "window_present": True,
                "window_focused": self.focused,
                "window_state": ("WINDOW_EXISTS_FOREGROUND" if self.focused
                                  else "WINDOW_EXISTS_BACKGROUND"),
                "foreground_owner": "JARVIS_TARGET" if self.focused else self.owner,
                "foreground_epoch": 7 if self.focused else 6,
                "user_active": activity["user_active"],
                "last_user_input_age_ms": activity["last_user_input_age_ms"],
                "target_window": {"handle": self.target_handle, "pid": self.target_pid},
            }
        if name == "ui_active_window":
            self.calls.append((name, dict(arguments), confirmed))
            return {
                "ok": True, "found": True,
                "process_name": "notepad.exe" if self.focused else "explorer.exe",
                "title": "* pesquisa_python.txt - Bloco de notas" if self.focused else "Explorer",
                "pid": self.target_pid if self.focused else 20,
                "handle": self.target_handle if self.focused else 999,
            }
        if name == "ui_focus_window":
            self.focus_calls += 1
            self.calls.append((name, dict(arguments), confirmed))
            if self.focus_ok:
                self.focused = True
            return {"ok": self.focus_ok, "focused": self.focus_ok,
                    **({} if self.focus_ok else {"error": "FOCUS_ACQUIRE_FAILED"})}
        if name == "ui_read_editor":
            self.editor_reads += 1
            self.calls.append((name, dict(arguments), confirmed))
            return {
                "ok": True, "found": True, "verified": True,
                "text": self.editor_text,
                "window": {"handle": self.target_handle, "pid": self.target_pid},
                "editor": {"document_identity": self.editor_identity,
                            "content_state_id": "content-1"},
            }
        if name == "ui_list_elements":
            self.calls.append((name, dict(arguments), confirmed))
            return {"ok": True, "elements": []}
        return super().execute_tool(name, arguments, command, task_id, confirmed)


def _owned_background_mission():
    template = (
        "Versão estável do Python: {{python_version}}\n"
        "Título principal do Ollama: {{ollama_page_title}}"
    )
    mission = ComputerMission(
        "background-recovery-mission", "request", MissionStatus.PENDING,
        time.time(), [
            ComputerMissionStep(
                "verify-editor-pre-save", "Verify editor", "verify_editor_pre_save",
                app="notepad", args={"template": template},
            ),
            ComputerMissionStep(
                "open-save-dialog", "Open Save As", "keyboard_hotkey",
                app="notepad", args={"keys": ["ctrl", "shift", "s"]},
            ),
        ], current_step=1, max_steps=10,
    )
    mission.context.current_app = "notepad"
    mission.context.store_variable(
        "python_version", "Python 3.14.7", kind="OBSERVED_VALUE",
        source_app="chrome", source_type="browser_result",
        source_url="https://www.python.org/downloads/latest/",
    )
    mission.context.store_variable(
        "ollama_page_title", "Ollama", kind="OBSERVED_VALUE",
        source_app="chrome", source_type="browser_result",
        source_url="https://ollama.com/",
    )
    mission.context.artifacts.update({
        "mission_document_id": "(42, 329544)",
        "mission_window_id": 123,
        "mission_document_created_by_mission": True,
        "rendered_text": {"value": "Versão estável do Python: Python 3.14.7\n"
                                  "Título principal do Ollama: Ollama"},
    })
    mission.result["document_ownership"] = "OWNED_BY_CURRENT_MISSION"
    mission.result["target_path"] = "C:\\temp\\resumo_pesquisa.txt"
    mission.result["filename"] = "resumo_pesquisa.txt"
    return mission


def test_long_research_template_uses_real_line_breaks():
    registry = Registry(
        "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
        "browser_search", "browser_get_page_info", "browser_click",
        "browser_record_window", "browser_wait_for_results", "ui_active_window",
        "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
        "ui_invoke_element", "ui_classify_dialog", "ui_list_elements", "open_program",
        "keyboard_type", "keyboard_hotkey", "keyboard_press",
    )
    mission = ComputerMissionPlanner(registry).plan(LONG_MISSION)
    step = next(item for item in mission.steps if item.step_id == "type-summary")
    template = str(step.args["template"])

    assert "\n" in template
    assert "\\n" not in template


class DurableMissionPlanner:
    def __init__(self, *, seed_context):
        self.seed_context = seed_context

    def plan(self, request):
        mission = ComputerMission(
            "durable-real-mission", request, MissionStatus.PENDING, time.time(),
            [
                ComputerMissionStep("python-search", "Python", "logical_action"),
                ComputerMissionStep(
                    "checkpoint-python", "Checkpoint Python", "checkpoint",
                    args={"name": "CHECKPOINT_PYTHON_DONE"},
                    requires=("python-search",),
                ),
                ComputerMissionStep(
                    "ollama-search", "Ollama", "logical_action",
                    requires=("checkpoint-python",),
                ),
            ],
            max_steps=10,
        )
        if self.seed_context:
            mission.context.store_variable(
                "python_version", "Python 3.14.7", kind="OBSERVED_VALUE",
                source_app="chrome", source_type="browser_result",
                source_url="https://www.python.org/downloads/latest/",
            )
            mission.context.store_variable(
                "ollama_page_title", "Ollama", kind="OBSERVED_VALUE",
                source_app="chrome", source_type="browser_result",
                source_url="https://ollama.com/",
            )
        return mission


def _foreground_pause_mission(request="request"):
    mission = ComputerMission(
        "foreground-pause-mission", request, MissionStatus.PENDING, time.time(),
        [ComputerMissionStep(
            "focus-notepad", "Focus Notepad", "ui_focus_window", app="notepad",
            expected_state={"process": "notepad"}, args={"window": "notepad"},
        )],
        max_steps=10,
    )
    mission.context.current_app = "notepad"
    return mission


def test_user_activity_pauses_before_focus_or_keyboard_input(tmp_path):
    service = ForegroundProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        user_active=True, owner="USER_EXTERNAL_APP", focused=False,
    )
    executor = ComputerMissionExecutor(
        service, FixedPlanner(lambda request: _foreground_pause_mission(request)))

    result = executor.run("request")

    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.PAUSED.value
    assert result["mission"]["error"] == "MISSION_PAUSED_FOR_USER_ACTIVITY"
    assert result["mission"]["result"]["pause_reason"] == "USER_ACTIVITY"
    assert service.focus_calls == 0
    assert any(event["status"] == "USER_ACTIVITY_DETECTED"
               for event in service.audit_events)


def test_focus_failure_pauses_as_foreground_contention_without_retry_loop(tmp_path):
    service = ForegroundProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        user_active=False, owner="UNKNOWN", focused=False, focus_ok=False,
    )
    executor = ComputerMissionExecutor(
        service, FixedPlanner(lambda request: _foreground_pause_mission(request)))

    result = executor.run("request")

    assert result["ok"] is False
    assert result["mission"]["status"] == MissionStatus.PAUSED.value
    assert result["mission"]["error"] == "MISSION_PAUSED_FOR_FOREGROUND_CONTENTION"
    assert service.focus_calls == 1
    assert result["mission"]["result"]["pause_reason"] == "FOREGROUND_CONTENTION"


def test_background_target_is_contention_not_app_closed(tmp_path):
    service = ForegroundProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        user_active=False, owner="UNKNOWN", focused=False,
    )
    mission = _foreground_pause_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda request: mission))

    change = executor._classify_world_state_change(
        mission, {"ok": False, "error": "CORRECT_WINDOW_NOT_FOCUSED"},
        mission.mission_id,
    )

    assert change is WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_UNKNOWN
    assert change is not WorldStateChangeType.APP_CLOSED


def test_idle_owned_background_window_is_recoverable_and_revalidates_editor(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        ages=[5000, 5000, 5000, 5000, 5000],
        user_active=False, owner="UNKNOWN", focused=False,
    )
    mission = _owned_background_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-recovery-mission")

    assert result["ok"] is True
    assert result["world_state_change_type"] == (
        WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_RECOVERABLE.value)
    assert result["focus_recovery_attempts"] == 1
    assert service.focus_calls == 1
    assert service.editor_reads >= 2
    assert any(event["status"] == "BACKGROUND_WINDOW_RECOVERED"
               for event in service.audit_events)


def test_background_window_with_recent_activity_never_focuses(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        ages=[0, 0, 0], user_active=True,
        owner="USER_EXTERNAL_APP", focused=False,
    )
    mission = _owned_background_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-user-active")

    assert result["ok"] is False
    assert result["error"] == "USER_ACTIVITY_DETECTED"
    assert service.focus_calls == 0


def test_unowned_background_window_is_not_recoverable(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        user_active=False, owner="UNKNOWN", focused=False,
    )
    mission = _owned_background_mission()
    mission.result["document_ownership"] = "PRE_EXISTING_DOCUMENT_PROTECTED"
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-unowned")

    assert result["ok"] is False
    assert result["error"] == "WORLD_STATE_CHANGED"
    assert result["world_state_change_type"] == (
        WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_UNKNOWN.value)
    assert service.focus_calls == 0


def test_background_focus_recovery_is_bounded_and_blocks_on_failure(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        user_active=False, owner="UNKNOWN", focused=False, focus_ok=False,
    )
    mission = _owned_background_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-focus-failure")

    assert result["ok"] is False
    assert result["error"] == "FOCUS_RECOVERY_FAILED"
    assert result["focus_recovery_attempts"] == 2
    assert service.focus_calls == 2
    assert service.editor_reads == 0


def test_new_activity_before_focus_aborts_recovery(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        ages=[5000, 5000, 0], user_active=False,
        owner="UNKNOWN", focused=False,
    )
    mission = _owned_background_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-activity-before-focus")

    assert result["ok"] is False
    assert result["error"] == "USER_ACTIVITY_DETECTED"
    assert service.focus_calls == 0


def test_new_activity_after_focus_aborts_before_editor_or_save(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        ages=[5000, 5000, 5000, 5000, 0], user_active=False,
        owner="UNKNOWN", focused=False,
    )
    mission = _owned_background_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-activity-after-focus")

    assert result["ok"] is False
    assert result["error"] == "USER_ACTIVITY_DETECTED"
    assert service.focus_calls == 1
    assert service.editor_reads == 0


def test_background_recovery_rejects_changed_document_identity(tmp_path):
    service = BackgroundRecoveryProbe(
        TaskDatabase(tmp_path / "golden_tasks.db"),
        user_active=False, owner="UNKNOWN", focused=False,
        editor_identity="(42, 999999)",
    )
    mission = _owned_background_mission()
    executor = ComputerMissionExecutor(service, FixedPlanner(lambda _request: mission))

    result = executor._revalidate_world(mission, "background-stale-document")

    assert result["ok"] is False
    assert result["error"] == "STALE_DOCUMENT"
    assert service.focus_calls == 1


def test_explicit_resume_after_user_pause_rechecks_foreground(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    service = ForegroundProbe(
        database, user_active=True, owner="USER_EXTERNAL_APP", focused=False,
    )
    executor = ComputerMissionExecutor(
        service, FixedPlanner(lambda request: _foreground_pause_mission(request)))
    paused = executor.run("request")
    token = paused["mission"]["resume_token"]

    service.user_active = False
    service.owner = "JARVIS_TARGET"
    service.focused = True
    service.focus_ok = True
    resumed = executor.resume("foreground-pause-mission", token)

    assert resumed["ok"] is True
    assert resumed["mission"]["status"] == MissionStatus.COMPLETED.value
    assert resumed["mission"]["current_step"] == 1


def test_missions_have_scoped_tokens_even_when_latest_checkpoint_changes(tmp_path):
    store_a = MissionCheckpointStore(TaskDatabase(tmp_path / "golden_tasks.db"))
    context_a = MissionContext("mission-a", "request-a")
    context_b = MissionContext("mission-b", "request-b")
    checkpoint_a = store_a.save_checkpoint(
        mission_id="mission-a", mission_version=0, name="A",
        current_step=1, next_step=1, context_revision=0,
        snapshot={"mission_id": "mission-a", "user_request": "request-a",
                  "context": context_a.checkpoint_snapshot()},
    )
    checkpoint_b = store_a.save_checkpoint(
        mission_id="mission-b", mission_version=0, name="B",
        current_step=2, next_step=2, context_revision=0,
        snapshot={"mission_id": "mission-b", "user_request": "request-b",
                  "context": context_b.checkpoint_snapshot()},
    )

    loaded_a, error_a = store_a.load_resume_token(checkpoint_a["resume_token"])
    loaded_b, error_b = store_a.load_resume_token(checkpoint_b["resume_token"])

    assert error_a == ""
    assert error_b == ""
    assert loaded_a["mission_id"] == "mission-a"
    assert loaded_b["mission_id"] == "mission-b"
    assert loaded_a["checkpoint_id"] != loaded_b["checkpoint_id"]
    assert store_a.load_resume_token("mission-a:missing-checkpoint")[1] == (
        "RESUME_TOKEN_NOT_FOUND")


def test_mission_context_provenance_and_receipts_survive_new_executor_instance(tmp_path):
    database_path = tmp_path / "golden_tasks.db"
    service_a = ProbeService(TaskDatabase(database_path), process="chrome.exe")
    planner_a = DurableMissionPlanner(seed_context=True)
    executor_a = ComputerMissionExecutor(service_a, planner_a)
    paused = executor_a.run(
        "durable request", pause_after_checkpoint="CHECKPOINT_PYTHON_DONE",
    )
    assert paused["mission"]["status"] == MissionStatus.PAUSED.value
    token = paused["mission"]["resume_token"]
    assert token

    service_b = ProbeService(TaskDatabase(database_path), process="chrome.exe")
    executor_b = ComputerMissionExecutor(
        service_b, DurableMissionPlanner(seed_context=False))
    resumed = executor_b.resume("durable-real-mission", token)

    assert resumed["ok"] is True
    assert resumed["mission"]["status"] == MissionStatus.COMPLETED.value
    context = resumed["mission"]["context"]
    assert context["variables"]["python_version"]["value"] == "Python 3.14.7"
    assert context["variables"]["ollama_page_title"]["value"] == "Ollama"
    assert context["source_provenance"]["python_version"]["source_url"] == (
        "https://www.python.org/downloads/latest/")
    assert context["source_provenance"]["ollama_page_title"]["source_url"] == (
        "https://ollama.com/")
    assert [name for name, _, _ in service_a.calls].count("logical_action") == 1
    assert [name for name, _, _ in service_b.calls].count("logical_action") == 1
    assert executor_b.persistence.receipts_for_mission(
        "durable-real-mission") == []


def test_action_receipts_survive_store_reconstruction(tmp_path):
    database_path = tmp_path / "golden_tasks.db"
    store_a = MissionCheckpointStore(TaskDatabase(database_path))
    store_a.save_receipt(
        mission_id="mission-a", step_id="write", action_type="ui_type_editor",
        target="notepad-editor", result_state=ActionState.VERIFIED,
        result={"verified": True},
    )
    store_b = MissionCheckpointStore(TaskDatabase(database_path))

    receipt = store_b.receipt("mission-a", "write")

    assert receipt["mission_id"] == "mission-a"
    assert receipt["result_state"] == ActionState.VERIFIED.value
    assert receipt["result"]["verified"] is True


def test_mission_record_tampering_invalidates_resume_token(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    store = MissionCheckpointStore(database)
    context = MissionContext("mission-integrity", "request")
    record = store.save_checkpoint(
        mission_id="mission-integrity", mission_version=0, name="pause",
        current_step=0, next_step=0, context_revision=0,
        snapshot={"mission_id": "mission-integrity", "user_request": "request",
                  "context": context.checkpoint_snapshot()},
    )

    with database.connect() as db:
        db.execute(
            "UPDATE mission_records SET snapshot=? WHERE mission_id=?",
            ('{"mission_id":"mission-integrity","tampered":true}',
             "mission-integrity"),
        )

    mission, mission_error = store.load_mission("mission-integrity")
    resumed, resume_error = store.load_resume_token(record["resume_token"])

    assert mission is None
    assert mission_error == "MISSION_RECORD_INVALID"
    assert resumed is None
    assert resume_error == "RESUME_TOKEN_NOT_FOUND"


def test_resume_waits_for_quiet_window_and_resets_on_new_input(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    service = QuietForegroundProbe(
        database, ages=[0, 100, 0, 2000], user_active=True,
        owner="USER_EXTERNAL_APP", focused=False,
    )
    executor = ComputerMissionExecutor(
        service, FixedPlanner(lambda request: _foreground_pause_mission(request)))
    paused = executor.run("request")
    token = paused["mission"]["resume_token"]

    service.user_active = False
    service.owner = "JARVIS_TARGET"
    service.focused = True
    resumed = executor.resume("foreground-pause-mission", token)

    assert resumed["ok"] is True
    assert resumed["mission"]["status"] == MissionStatus.COMPLETED.value
    activity_calls = [item for item in service.calls if item[0] == "ui_user_activity"]
    assert len(activity_calls) == 4
    assert any(event["status"] == "WAITING_FOR_USER_IDLE"
               for event in service.audit_events)
    assert any(event["status"] == "QUIET_WINDOW_RESET"
               for event in service.audit_events)


def test_cancel_during_resume_quiet_window_fails_closed_without_actions(tmp_path):
    class CancelDuringQuietProbe(QuietForegroundProbe):
        def execute_tool(self, name, arguments, command="", task_id="desktop", confirmed=False):
            result = super().execute_tool(name, arguments, command, task_id, confirmed)
            if name == "ui_user_activity":
                self.cancellation.request_cancel()
            return result

    database = TaskDatabase(tmp_path / "golden_tasks.db")
    service = CancelDuringQuietProbe(
        database, ages=[0], user_active=True,
        owner="USER_EXTERNAL_APP", focused=False,
    )
    executor = ComputerMissionExecutor(
        service, FixedPlanner(lambda request: _foreground_pause_mission(request)))
    paused = executor.run("request")
    token = paused["mission"]["resume_token"]

    service.user_active = False
    service.owner = "JARVIS_TARGET"
    service.focused = True
    resumed = executor.resume("foreground-pause-mission", token)

    assert resumed["ok"] is False
    assert resumed["mission"]["status"] == MissionStatus.CANCELLED.value
    assert [name for name, _, _ in service.calls].count("logical_action") == 0
    assert any(event["status"] == "MISSION_CANCELLED"
               for event in service.audit_events)


def test_explicit_cancel_persists_terminal_mission_state(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    service = ProbeService(database)
    planner = FixedPlanner(lambda request: _foreground_pause_mission(request))
    executor = ComputerMissionExecutor(service, planner)
    mission = planner.plan("request")
    executor._active = mission
    executor._missions[mission.mission_id] = mission
    executor._persist_mission(mission, audit=False)

    assert executor.cancel_current_mission() is True

    stored, error = executor.persistence.load_mission(mission.mission_id)
    assert error == ""
    assert stored["status"] == MissionStatus.CANCELLED.value
    assert stored["pause_reason"] == "OPERATOR_CANCELLED"


def test_app_closed_is_classified_as_recoverable_without_research_rerun(tmp_path):
    service = ClosedNotepadProbe(TaskDatabase(tmp_path / "golden_tasks.db"))
    mission, planner = _recovery_mission(tmp_path)
    executor = ComputerMissionExecutor(service, planner)
    executor.persistence.save_receipt(
        mission_id=mission.mission_id, step_id="new-notepad-document",
        action_type="keyboard_hotkey", target="notepad",
        result_state=ActionState.VERIFIED,
    )

    change = executor._classify_world_state_change(
        mission, {"ok": False, "error": "CORRECT_WINDOW_NOT_FOCUSED"},
        mission.mission_id,
    )
    assert change is WorldStateChangeType.APP_CLOSED

    recovered = executor._prepare_notepad_recovery(
        mission, change, {"error": "CORRECT_WINDOW_NOT_FOCUSED"},
    )
    assert recovered["ok"] is True
    assert recovered["world_state_change_classification"] == "RECOVERABLE"
    assert mission.steps[mission.current_step].step_id == "handoff-to-notepad"
    assert mission.result["old_window_target_invalidated"] is True
    assert mission.result["old_document_target_invalidated"] is True
    assert "mission_document_id" not in mission.context.artifacts
    assert "python_version" in mission.context.variables
    assert "ollama_page_title" in mission.context.variables
    assert executor.persistence.receipt(
        mission.mission_id, "new-notepad-document")["result_state"] == ActionState.NOT_STARTED.value
    new_document = next(step for step in mission.steps
                        if step.step_id == "new-notepad-document")
    assert new_document.action_type == "ui_invoke_element"
    assert new_document.args["target"] == "Adicionar Nova Guia"


def test_recovery_rejects_existing_target_before_reopening_app(tmp_path):
    service = ClosedNotepadProbe(TaskDatabase(tmp_path / "golden_tasks.db"))
    mission, planner = _recovery_mission(tmp_path)
    target = Path(mission.result["target_path"])
    target.write_text("unexpected", encoding="utf-8")
    executor = ComputerMissionExecutor(service, planner)

    result = executor._prepare_notepad_recovery(
        mission, WorldStateChangeType.APP_CLOSED, {"error": "window_not_found"},
    )
    assert result["ok"] is False
    assert result["error"] == "USER_CONFIRMATION_REQUIRED"
    assert service.calls == []


def test_recovery_rejects_unknown_side_effect_receipt(tmp_path):
    service = ClosedNotepadProbe(TaskDatabase(tmp_path / "golden_tasks.db"))
    mission, planner = _recovery_mission(tmp_path)
    executor = ComputerMissionExecutor(service, planner)
    executor.persistence.save_receipt(
        mission_id=mission.mission_id, step_id="confirm-save",
        action_type="ui_invoke_element", target="save-button",
        result_state=ActionState.IN_FLIGHT_UNKNOWN,
    )

    result = executor._prepare_notepad_recovery(
        mission, WorldStateChangeType.APP_CLOSED, {"error": "window_not_found"},
    )
    assert result["ok"] is False
    assert result["error"] == "ACTION_IN_FLIGHT_UNKNOWN"


def test_recovery_rejects_invalid_provenance_without_research(tmp_path):
    service = ClosedNotepadProbe(TaskDatabase(tmp_path / "golden_tasks.db"))
    mission, planner = _recovery_mission(tmp_path)
    mission.context.source_provenance["ollama_page_title"]["invalidated"] = True
    executor = ComputerMissionExecutor(service, planner)

    result = executor._prepare_notepad_recovery(
        mission, WorldStateChangeType.APP_CLOSED, {"error": "window_not_found"},
    )
    assert result["ok"] is False
    assert result["error"] == "SOURCE_PROVENANCE_INVALID"
