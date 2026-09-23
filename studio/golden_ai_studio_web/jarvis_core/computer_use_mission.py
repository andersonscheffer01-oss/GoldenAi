"""Perception-driven missions built on the existing Jarvis tools.

This module is intentionally small.  It does not own input, vision, UIA,
security, or audit infrastructure; it coordinates those existing boundaries
one step at a time and stops when a confirmation or fresh observation is
required.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .windows_known_folders import documents_dir as known_documents_dir


class MissionStatus(str, Enum):
    PENDING = "PENDING"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    CANCELLED = "CANCELLED"


class MissionStepStatus(str, Enum):
    PENDING = "PENDING"
    OBSERVING = "OBSERVING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    CANCELLED = "CANCELLED"


@dataclass
class ComputerMissionStep:
    step_id: str
    description: str
    action_type: str
    target: str = ""
    expected_state: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    status: MissionStepStatus = MissionStepStatus.PENDING
    attempts: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class ComputerMission:
    mission_id: str
    user_request: str
    status: MissionStatus
    created_at: float
    steps: list[ComputerMissionStep]
    current_step: int = 0
    max_steps: int = 30
    timeout_seconds: float = 300.0
    requires_confirmation: bool = True
    risk_level: str = "WRITE"
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    pending_confirmation_token: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "user_request": self.user_request,
            "status": self.status.value,
            "created_at": self.created_at,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "timeout_seconds": self.timeout_seconds,
            "requires_confirmation": self.requires_confirmation,
            "risk_level": self.risk_level,
            "result": dict(self.result),
            "error": self.error,
            "pending_confirmation": bool(self.pending_confirmation_token),
            "steps": [
                {
                    "step_id": step.step_id,
                    "description": step.description,
                    "action_type": step.action_type,
                    "target": step.target,
                    "expected_state": dict(step.expected_state),
                    "status": step.status.value,
                    "attempts": step.attempts,
                    "result": dict(step.result),
                    "error": step.error,
                }
                for step in self.steps
            ],
        }


class ComputerMissionPlanner:
    """Create bounded plans using only tools present in the shared registry."""

    MAX_STEPS = 30
    _NOTEPAD_RE = re.compile(r"\b(bloco\s+de\s+notas|notepad)\b", re.I)
    _SAVE_RE = re.compile(r"\bsalv(?:e|ar|a)\s+(?:como\s+)?([\w.-]+)", re.I)

    def __init__(self, registry, documents_dir: Optional[Path] = None):
        self.registry = registry
        self._documents_dir_override = Path(documents_dir) if documents_dir else None

    def resolve_documents_dir(self) -> Path:
        return (self._documents_dir_override if self._documents_dir_override is not None
                else known_documents_dir())

    def resolve_target_path(self, filename: str) -> Path:
        """Resolve a mission filename against the current Known Folder."""
        return self.resolve_documents_dir() / Path(filename).name

    def can_plan(self, request: str) -> bool:
        text = str(request or "")
        low = text.casefold()
        return bool(self._NOTEPAD_RE.search(text) and
                    re.search(r"\b(escrev|digit|salv|confirme|funcionando)\w*\b", low))

    def plan(self, request: str) -> ComputerMission:
        if not self.can_plan(request):
            raise ValueError("Missão Computer Use não reconhecida.")
        text = str(request).strip()
        match = self._SAVE_RE.search(text)
        filename = match.group(1) if match else "teste.txt"
        filename = Path(filename).name
        if not filename or filename in {".", ".."}:
            raise ValueError("Nome de arquivo inválido para a missão.")
        target_path = self.resolve_target_path(filename)
        content_match = re.search(
            r"\b(?:escrev|digite|digitar)\s+(.+?)(?=\s*,?\s*(?:salv|confirme|e\s+salv)|$)",
            text, re.I)
        content = (content_match.group(1).strip(" \t,\"'")
                   if content_match else "Golden Jarvis funcionando")

        tool_names = {
            "open_program", "ui_active_window", "ui_focus_window", "ui_focus_element",
            "ui_dismiss_path_not_found", "keyboard_type", "keyboard_hotkey", "keyboard_press",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {})

        steps = [
            step("open-notepad", "Abrir o Bloco de Notas", "open_program",
                  target="Bloco de Notas", args={"name": "bloco de notas"}),
            step("focus-notepad", "Focar a janela do Bloco de Notas", "ui_focus_window",
                  target="notepad", expected={"process": "notepad"},
                  args={"window": "notepad"}),
            step("new-notepad-document", "Abrir uma nova aba em branco", "keyboard_hotkey",
                  target="notepad", expected={"process": "notepad"},
                  args={"keys": ["ctrl", "n"]}),
            step("observe-notepad", "Confirmar a janela correta", "observe_window",
                  target="notepad", expected={"process": "notepad"}),
            step("type-content", "Escrever o conteúdo solicitado", "keyboard_type",
                  target="notepad-editor", expected={"process": "notepad"},
                  args={"text": content, "interval": 0.03}),
            step("open-save-dialog", "Abrir o diálogo Salvar como", "keyboard_hotkey",
                  target="save-dialog", expected={"process": "notepad"},
                  args={"keys": ["ctrl", "shift", "s"]}),
            step("observe-save-dialog", "Confirmar o diálogo de salvamento", "observe_window",
                  target="save-dialog", expected={"title": ("save as", "salvar como"),
                                                   "process": "notepad"}),
            step("focus-file-name", "Focar o campo de nome do arquivo", "ui_focus_element",
                  target="file-name", expected={"control_type": "Edit"},
                  args={"target": "", "control_type": "Edit", "window": ""}),
            step("type-file-name", "Informar o nome do arquivo", "keyboard_type",
                  target="file-name", expected={"title": ("save as", "salvar como")},
                  args={"text": str(target_path), "interval": 0.03}),
            step("confirm-save", "Confirmar o salvamento", "keyboard_press",
                  target="save-dialog", expected={"title": ("save as", "salvar como")},
                  args={"key": "enter"}),
            step("observe-saved-window", "Confirmar o retorno ao Bloco de Notas",
                  "observe_window", target="notepad",
                  expected={"process": "notepad"}),
            step("verify-file", "Verificar existência e conteúdo no filesystem",
                  "verify_file", target=str(target_path),
                  expected={"path": str(target_path), "content": content}),
        ]
        return ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                               time.time(), steps, max_steps=self.MAX_STEPS)


class ComputerMissionExecutor:
    """Run one mission step at a time through JarvisService.execute_tool."""

    _WINDOW_TOOLS = {"ui_active_window", "ui_focus_window", "ui_focus_element"}
    _ACTION_TOOLS = {"keyboard_type", "keyboard_hotkey", "keyboard_press"}

    def __init__(self, service, planner: Optional[ComputerMissionPlanner] = None):
        self.service = service
        self.planner = planner or ComputerMissionPlanner(service.registry)
        self._active: Optional[ComputerMission] = None
        self._missions: dict[str, ComputerMission] = {}
        self._lock = threading.RLock()
        self._cancel = threading.Event()

    def run(self, request: str, task_id: str = "desktop") -> dict[str, Any]:
        mission = self.planner.plan(request)
        with self._lock:
            self._active = mission
            self._missions[mission.mission_id] = mission
            self._cancel.clear()
        return self._run_from_current(mission, task_id)

    def resume(self, mission_id: str, token: str, task_id: str = "desktop") -> dict[str, Any]:
        with self._lock:
            mission = self._missions.get(str(mission_id))
            if not mission or mission.pending_confirmation_token != str(token):
                return {"ok": False, "error": "Confirmação de missão inválida ou expirada."}
            mission.pending_confirmation_token = ""
        current = mission.steps[mission.current_step]
        result = self.service.confirm(token, task_id=mission.mission_id)
        if not result.get("ok") or result.get("confirmation_required"):
            mission.status = MissionStatus.FAILED
            mission.error = result.get("error", "Confirmação falhou")
            return self._finish(mission, False)
        return self._run_from_current(mission, task_id, preconfirmed=(current, result))

    def cancel_current_mission(self) -> bool:
        with self._lock:
            mission = self._active
            if mission is None or mission.status in {MissionStatus.COMPLETED,
                                                       MissionStatus.FAILED,
                                                       MissionStatus.CANCELLED}:
                return False
            self._cancel.set()
            mission.status = MissionStatus.CANCELLED
            mission.error = "Cancelamento solicitado pelo operador."
            if mission.current_step < len(mission.steps):
                mission.steps[mission.current_step].status = MissionStepStatus.CANCELLED
            return True

    def current(self) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._active.public() if self._active else None

    def _run_from_current(self, mission, task_id, preconfirmed=None):
        started = time.monotonic()
        action_count = 0
        fingerprints: dict[str, int] = {}
        while mission.current_step < len(mission.steps):
            if self._cancel.is_set() or self.service.cancellation.is_cancelled():
                mission.status = MissionStatus.CANCELLED
                mission.error = "Cancelamento solicitado pelo operador."
                return self._finish(mission, False)
            if time.monotonic() - started > mission.timeout_seconds:
                mission.status = MissionStatus.FAILED
                mission.error = "Timeout da missão excedido."
                return self._finish(mission, False)
            action_count += 1
            if action_count > mission.max_steps:
                mission.status = MissionStatus.BLOCKED
                mission.error = "MAX_STEPS_EXCEEDED"
                return self._finish(mission, False)

            step = mission.steps[mission.current_step]
            step.attempts += 1
            step.status = MissionStepStatus.OBSERVING
            if step.action_type == "verify_file":
                step.status = MissionStepStatus.VERIFYING
                result = self._verify_file(step)
            elif step.action_type == "observe_window":
                result = self._observe_window(step)
            else:
                result = self._execute_tool_step(mission, step, task_id, preconfirmed)
                preconfirmed = None
            if result.get("confirmation_required"):
                mission.status = MissionStatus.WAITING_CONFIRMATION
                mission.pending_confirmation_token = str(result.get("token") or "")
                step.status = MissionStepStatus.WAITING_CONFIRMATION
                step.result = {"confirmation_required": True}
                self._audit_step(mission, step, result, "waiting_confirmation")
                return self._finish(mission, False)
            if not result.get("ok"):
                if self._is_path_not_found(result):
                    self._audit_step(mission, step, result, "path_not_found")
                    if self._recover_path_not_found(mission, step, result):
                        step.status = MissionStepStatus.PENDING
                        mission.status = MissionStatus.OBSERVING
                        continue
                fingerprint = f"{step.step_id}:{result.get('error', '')}:{self._window_fingerprint()}"
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
                step.error = str(result.get("error") or "Etapa falhou")[:500]
                step.result = {"ok": False, "error": step.error}
                self._audit_step(mission, step, result, "failed")
                if fingerprints[fingerprint] >= 2 or step.attempts >= 3:
                    mission.status = MissionStatus.BLOCKED
                    mission.error = "ACTION_LOOP_DETECTED"
                    step.status = MissionStepStatus.BLOCKED
                    return self._finish(mission, False)
                step.status = MissionStepStatus.PENDING
                mission.status = MissionStatus.OBSERVING
                continue
            step.status = MissionStepStatus.VERIFYING
            if not self._validate_step_result(step, result):
                step.status = MissionStepStatus.FAILED
                step.error = "Pós-condição da etapa não confirmada."
                self._audit_step(mission, step, result, "verification_failed")
                mission.status = MissionStatus.FAILED
                mission.error = step.error
                return self._finish(mission, False)
            step.status = MissionStepStatus.COMPLETED
            step.result = self._safe_step_result(result)
            self._audit_step(mission, step, result, "completed")
            mission.current_step += 1
            mission.status = MissionStatus.OBSERVING

        mission.status = MissionStatus.COMPLETED
        mission.result = {"mission_completed": True,
                          "file_exists": bool(mission.steps[-1].result.get("file_exists")),
                          "content_valid": bool(mission.steps[-1].result.get("content_valid"))}
        return self._finish(mission, True)

    def _execute_tool_step(self, mission, step, task_id, preconfirmed):
        if preconfirmed and preconfirmed[0] is step:
            return preconfirmed[1]
        if step.action_type in self._ACTION_TOOLS:
            guard = self._observe_window(step)
            if not guard.get("ok"):
                return guard
        step.status = MissionStepStatus.EXECUTING
        return self.service.execute_tool(step.action_type, step.args,
                                          command=f"computer_mission:{mission.mission_id}",
                                          task_id=mission.mission_id)

    def _observe_window(self, step):
        result = self.service.execute_tool("ui_active_window", {},
                                           command="computer_mission:observe",
                                           task_id="computer-mission")
        if result.get("confirmation_required") or not (result.get("ok") or result.get("found")):
            return result
        data = result.get("result") if isinstance(result.get("result"), dict) else result
        expected = step.expected_state
        title = str(data.get("title") or data.get("message") or "").casefold()
        process = str(data.get("process_name") or "").casefold()
        if expected.get("process") and expected["process"].casefold() not in process:
            return {"ok": False, "error": "CORRECT_WINDOW_NOT_FOCUSED"}
        expected_title = expected.get("title")
        titles = expected_title if isinstance(expected_title, (tuple, list)) else (expected_title,)
        if expected_title and not any(str(item).casefold() in title for item in titles if item):
            if self._is_path_not_found({"error": title}):
                return {"ok": False, "error": "PATH_NOT_FOUND",
                        "path_error_dialog": True, "window": data}
            return {"ok": False, "error": "EXPECTED_WINDOW_NOT_FOUND"}
        return {"ok": True, "window": data, "verified": True,
                "verification": "active_window_match"}

    def _verify_file(self, step):
        path = Path(step.expected_state.get("path") or step.target)
        expected = str(step.expected_state.get("content") or "")
        try:
            exists = path.is_file()
            content_valid = exists and path.read_text(encoding="utf-8") == expected
            return {"ok": exists and content_valid, "verified": exists and content_valid,
                    "verification": "filesystem_exists_and_content",
                    "file_exists": exists, "content_valid": content_valid,
                    "path": str(path)}
        except OSError as exc:
            return {"ok": False, "verified": False, "error": type(exc).__name__,
                    "path_error": "PATH_NOT_FOUND" if getattr(exc, "errno", None) == 2 else "",
                    "file_exists": False, "content_valid": False}

    @staticmethod
    def _is_path_not_found(result: dict[str, Any]) -> bool:
        text = " ".join(str(result.get(key, "")) for key in
                        ("error", "message", "reason", "path_error")).casefold()
        return any(marker in text for marker in
                   ("path_not_found", "path not found", "cannot find the path",
                    "caminho especificado", "sistema não pode encontrar"))

    def _recover_path_not_found(self, mission, step, result) -> bool:
        attempts = int(mission.result.get("path_recovery_attempts", 0)) + 1
        mission.result["path_recovery_attempts"] = attempts
        if attempts > 2:
            mission.status = MissionStatus.BLOCKED
            mission.error = "PATH_NOT_FOUND_UNRECOVERED"
            step.status = MissionStepStatus.BLOCKED
            return False
        if result.get("path_error_dialog"):
            dismissed = self.service.execute_tool(
                "ui_dismiss_path_not_found", {},
                command=f"computer_mission:{mission.mission_id}",
                task_id=mission.mission_id)
            self._audit_step(mission, step, dismissed, "path_not_found_dialog_dismissed")
            if not dismissed.get("ok"):
                return False
        if not self._reresolve_path(mission):
            return False
        entry_index = next((index for index, item in enumerate(mission.steps)
                            if item.target == "file-name" and item.action_type == "keyboard_type"),
                           mission.current_step)
        for item in mission.steps[entry_index:]:
            item.status = MissionStepStatus.PENDING
            item.error = ""
        mission.current_step = entry_index
        return True

    def _reresolve_path(self, mission: ComputerMission) -> bool:
        """Refresh a mission's file target after a recoverable path failure."""
        verify = next((item for item in mission.steps if item.action_type == "verify_file"), None)
        type_name = next((item for item in mission.steps if item.step_id == "type-file-name"), None)
        if verify is None:
            return False
        old_path = str(verify.expected_state.get("path") or verify.target)
        new_path = self.planner.resolve_target_path(Path(old_path).name)
        verify.expected_state["path"] = str(new_path)
        verify.target = str(new_path)
        if type_name is not None:
            type_name.args["text"] = str(new_path)
        mission.result["path_reresolved"] = {"from": old_path, "to": str(new_path)}
        return True

    def _validate_step_result(self, step, result):
        if step.action_type == "verify_file":
            return bool(result.get("verified") and result.get("file_exists")
                        and result.get("content_valid"))
        if step.action_type == "observe_window":
            return bool(result.get("verified"))
        return bool(result.get("ok"))

    def _window_fingerprint(self):
        try:
            result = self.service.execute_tool("ui_active_window", {},
                                               command="computer_mission:fingerprint",
                                               task_id="computer-mission")
            return str((result.get("result") or result).get("title", ""))
        except Exception:
            return "unknown"

    def _audit_step(self, mission, step, result, status):
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool=step.action_type,
            arguments={"mission_id": mission.mission_id, "step_id": step.step_id,
                       "target": step.target},
            risk=mission.risk_level,
            status=status,
            result={"ok": bool(result.get("ok")), "verification": result.get("verification"),
                    "error": result.get("error", "")},
        )

    @staticmethod
    def _safe_step_result(result):
        allowed = {"ok", "verified", "verification", "message", "file_exists",
                    "content_valid", "window", "path", "tool"}
        return {key: value for key, value in result.items() if key in allowed}

    def _finish(self, mission, ok):
        with self._lock:
            if self._active is mission and mission.status in {MissionStatus.COMPLETED,
                                                               MissionStatus.FAILED,
                                                               MissionStatus.BLOCKED,
                                                               MissionStatus.CANCELLED}:
                self._active = None
        return {"ok": bool(ok), "mission": mission.public(),
                "message": ("Missão concluída." if ok else
                            mission.error or mission.status.value)}


__all__ = [
    "ComputerMission", "ComputerMissionExecutor", "ComputerMissionPlanner",
    "ComputerMissionStep", "MissionStatus", "MissionStepStatus",
]
