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
