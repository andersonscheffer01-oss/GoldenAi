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

from .browser import (MAX_SEARCH_PROVIDERS, SEARCH_PROVIDER_ORDER,
                      SEARCH_PROVIDER_URLS, classify_page_barrier)
from .windows_known_folders import documents_dir as known_documents_dir


DEFAULT_SEARCH_HOME = SEARCH_PROVIDER_URLS[SEARCH_PROVIDER_ORDER[0]]


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
    _BROWSER_RE = re.compile(r"\b(navegador|browser|chrome|edge)\b", re.I)
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
        if self._BROWSER_RE.search(text):
            return bool(re.search(r"\b(pesquis|buscar|busque|procure)\w*\b", low))
        return bool(self._NOTEPAD_RE.search(text) and
                    re.search(r"\b(escrev|digit|salv|confirme|funcionando)\w*\b", low))

    def plan(self, request: str) -> ComputerMission:
        if not self.can_plan(request):
            raise ValueError("Missão Computer Use não reconhecida.")
        text = str(request).strip()
        if self._BROWSER_RE.search(text):
            return self._plan_browser_search(text)
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

    def _plan_browser_search(self, text: str) -> ComputerMission:
        match = re.search(
            r"\b(?:pesquis(?:e|ar)?|busque|buscar|procure)\s+(.+?)(?=\s+e\s+me\s+diga|\s+e\s+abra|$)",
            text, re.I)
        query = (match.group(1).strip(" \t,\"'") if match else "")
        if not query:
            raise ValueError("Consulta de navegador vazia.")
        tool_names = {
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "ui_active_window", "ui_focus_window",
            "browser_click", "browser_record_window", "browser_wait_for_results",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {})

        steps = [
            step("open-browser", "Abrir navegador visível controlado", "browser_open",
                 target="browser", args={"visible": True, "provider": "chrome"}),
            step("navigate-search-home", "Abrir página inicial de pesquisa", "browser_navigate",
                 target=DEFAULT_SEARCH_HOME, args={"url": DEFAULT_SEARCH_HOME}),
            step("focus-browser", "Confirmar foco no navegador", "focus_browser",
                 target="browser", expected={"browser_process": True}),
            step("observe-browser", "Confirmar sessão e janela do navegador", "observe_browser",
                 target="browser", expected={"browser_process": True}),
            step("ground-search-field", "Localizar campo de busca por elementos estruturados",
                 "ground_search_field", target="search-field"),
            step("execute-search", "Executar busca textual", "browser_search",
                 target="search-field", args={"query": query, "ref": ""}),
            step("observe-results", "Detectar mudança real de página", "observe_browser",
                 target="results", expected={"page_changed": True}),
            step("read-visible-results", "Ler conteúdo visível estruturado", "browser_get_page_info",
                 target="page"),
            step("verify-three-results", "Validar três títulos de resultados", "verify_browser_results",
                 target="results", expected={"minimum": 3}),
        ]
        mission = ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                                  time.time(), steps, max_steps=self.MAX_STEPS)
        mission.result["browser_mission"] = True
        mission.result["search_query"] = query
        mission.result["search_provider"] = SEARCH_PROVIDER_ORDER[0]
        mission.result["provider_index"] = 0
        mission.result["provider_health"] = []
        return mission


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
            elif step.action_type == "focus_browser":
                result = self._focus_browser()
            elif step.action_type == "observe_browser":
                result = self._observe_browser(mission, step)
            elif step.action_type == "ground_search_field":
                result = self._ground_search_field(mission)
            elif step.action_type == "verify_browser_results":
                step.status = MissionStepStatus.VERIFYING
                result = self._verify_browser_results(mission, step)
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
                if result.get("error") == "USER_CONFIRMATION_REQUIRED":
                    mission.status = MissionStatus.WAITING_CONFIRMATION
                    mission.error = "USER_CONFIRMATION_REQUIRED"
                    step.status = MissionStepStatus.WAITING_CONFIRMATION
                    self._audit_step(mission, step, result, "user_confirmation_required")
                    return self._finish(mission, False)
                if result.get("error") in {
                    "NAVIGATION_TIMEOUT", "SEARCH_EXECUTION_FAILED",
                    "SEARCH_PROVIDERS_EXHAUSTED", "NON_CHROME_BROWSER_DETECTED",
                    "CHROME_FOCUS_GUARD_FAILED", "CHROME_WINDOW_PROCESS_MISMATCH",
                    "CHROME_WINDOW_IDENTITY_UNAVAILABLE", "CHROME_NOT_FOUND",
                    "NON_CHROME_BROWSER_DISABLED",
                }:
                    mission.status = MissionStatus.BLOCKED
                    mission.error = str(result.get("error"))
                    step.status = MissionStepStatus.BLOCKED
                    self._audit_step(mission, step, result, "blocked")
                    return self._finish(mission, False)
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
        if mission.result.get("browser_mission"):
            mission.result.update({"mission_completed": True,
                                   "result_count": len(mission.result.get("titles", []))})
        else:
            mission.result = {"mission_completed": True,
                              "file_exists": bool(mission.steps[-1].result.get("file_exists")),
                              "content_valid": bool(mission.steps[-1].result.get("content_valid"))}
        return self._finish(mission, True)

    def _execute_tool_step(self, mission, step, task_id, preconfirmed):
        if preconfirmed and preconfirmed[0] is step:
            return preconfirmed[1]
        if step.action_type == "browser_search":
            ref = str(mission.result.get("search_ref") or "")
            if not ref:
                return {"ok": False, "error": "SEARCH_FIELD_NOT_GROUNDED"}
            step.args["ref"] = ref
            guard = self._observe_browser(mission, step)
            if not guard.get("ok"):
                return guard
        if step.action_type in self._ACTION_TOOLS:
            guard = self._observe_window(step)
            if not guard.get("ok"):
                return guard
        step.status = MissionStepStatus.EXECUTING
        return self.service.execute_tool(step.action_type, step.args,
                                          command=f"computer_mission:{mission.mission_id}",
                                          task_id=mission.mission_id)

    def _focus_browser(self):
        result = self.service.execute_tool(
            "ui_focus_window", {"window": "chrome"},
            command="computer_mission:focus_browser", task_id="computer-mission")
        if not result.get("ok"):
            return {"ok": False, "error": "CHROME_FOCUS_GUARD_FAILED"}
        active = self.service.execute_tool(
            "ui_active_window", {}, command="computer_mission:focus_browser",
            task_id="computer-mission")
        data = active.get("result") if isinstance(active.get("result"), dict) else active
        process = str(data.get("process_name") or "").casefold()
        if process != "chrome.exe":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED",
                    "window": data}
        return {"ok": True, "focused": True, "browser_process": "chrome.exe",
                "window": data, "verification": "chrome_window_focus_guard"}

    def _observe_browser(self, mission, step):
        health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:observe_browser",
            task_id=mission.mission_id)
        if not health.get("ok") or not health.get("started"):
            return {"ok": False, "error": "BROWSER_SESSION_NOT_STARTED"}
        if str(health.get("browser_provider") or health.get("provider") or "").casefold() != "chrome":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED"}
        active = self.service.execute_tool(
            "ui_active_window", {}, command="computer_mission:observe_browser",
            task_id=mission.mission_id)
        data = active.get("result") if isinstance(active.get("result"), dict) else active
        process = str(data.get("process_name") or "").casefold()
        if process != "chrome.exe":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED",
                    "window": data}
        pid = int(data.get("pid") or 0)
        window_id = int(data.get("handle") or 0)
        session_pid = int(health.get("process_id") or 0)
        if session_pid and pid and session_pid != pid:
            return {"ok": False, "error": "CHROME_WINDOW_PROCESS_MISMATCH",
                    "window": data, "session_process_id": session_pid}
        if self.service.registry.get("browser_record_window") is not None:
            recorded = self.service.execute_tool(
                "browser_record_window", {"pid": pid, "window_id": window_id},
                command="computer_mission:observe_browser", task_id=mission.mission_id)
            if not recorded.get("ok"):
                return {"ok": False, "error": "CHROME_WINDOW_IDENTITY_UNAVAILABLE"}
            health = self.service.execute_tool(
                "browser_health", {}, command="computer_mission:observe_browser",
                task_id=mission.mission_id)
        state_id = health.get("page_state_id")
        previous = mission.result.get("browser_page_state_id")
        if step.expected_state.get("page_changed") and previous is not None and state_id == previous:
            return {"ok": False, "error": "NAVIGATION_STATE_NOT_CHANGED"}
        mission.result["browser_page_state_id"] = state_id
        mission.result["browser_url"] = health.get("current_url", "")
        mission.result["browser_title"] = health.get("page_title", "")
        mission.result["browser_provider"] = "chrome"
        mission.result["chrome_process_id"] = pid
        mission.result["chrome_window_id"] = window_id
        return {"ok": True, "verified": True,
                "verification": "browser_window_and_session_state",
                "window": data, "health": health}

    @staticmethod
    def _search_field(elements):
        candidates = [item for item in elements
                      if item.get("visible", True) and
                      str(item.get("tag")) in {"input", "textarea"}]
        search_terms = ("search", "busca", "query", "pesquisar")
        preferred = [item for item in candidates if any(
            term in " ".join(str(item.get(key) or "").casefold()
                              for key in ("aria_label", "placeholder", "text"))
            for term in search_terms)]
        return (preferred or [item for item in candidates
                              if str(item.get("input_type") or "text").casefold() in
                              {"", "text", "search"} or
                              str(item.get("tag")) == "textarea"])

    @staticmethod
    def _consent_target(elements):
        safe_first = (
            "reject all", "rejeitar tudo", "only necessary", "somente necessários",
            "somente necessarios", "necessary only", "rejeitar", "reject",
        )
        benign_fallback = ("accept", "aceitar", "continue", "continuar", "ok")
        candidates = [item for item in elements if item.get("visible", True) and
                      str(item.get("tag")) in {"a", "button", "input"}]
        for labels in (safe_first, benign_fallback):
            for item in candidates:
                label = " ".join(str(item.get(key) or "") for key in
                                 ("text", "aria_label", "placeholder")).strip().casefold()
                if label and any(label == target or target in label for target in labels):
                    return str(item.get("ref") or ""), label
        return "", ""

    def _provider_health(self, mission, provider, status, block_reason=""):
        entries = list(mission.result.get("provider_health") or [])
        entries.append({"provider": provider, "attempt": len(entries) + 1,
                        "status": status, "block_reason": block_reason})
        mission.result["provider_health"] = entries[-MAX_SEARCH_PROVIDERS:]

    def _advance_provider(self, mission, reason):
        current_index = int(mission.result.get("provider_index", 0))
        current = SEARCH_PROVIDER_ORDER[current_index]
        self._provider_health(mission, current, "BLOCKED", reason)
        next_index = current_index + 1
        if next_index >= MAX_SEARCH_PROVIDERS:
            return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                    "barrier_type": reason}
        provider = SEARCH_PROVIDER_ORDER[next_index]
        mission.result["provider_index"] = next_index
        mission.result["search_provider"] = provider
        navigation = self.service.execute_tool(
            "browser_navigate", {"url": SEARCH_PROVIDER_URLS[provider]},
            command="computer_mission:provider_fallback", task_id=mission.mission_id)
        if not navigation.get("ok"):
            self._provider_health(mission, provider, "ERROR", navigation.get("error", ""))
            return {"ok": False, "error": "SEARCH_PROVIDER_FALLBACK_FAILED"}
        observed = self._observe_browser(
            mission, ComputerMissionStep("provider-observe", "Observar provider de busca",
                                         "observe_browser", expected_state={}))
        if not observed.get("ok"):
            return observed
        self._provider_health(mission, provider, "AVAILABLE", "")
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool="browser_provider_fallback",
            arguments={"from": current, "to": provider},
            risk=mission.risk_level,
            status="fallback",
            result={"reason": reason, "browser": "chrome"},
        )
        return {"ok": True, "provider": provider, "verification": "chrome_provider_fallback"}

    def _handle_cookie_consent(self, mission, page, elements):
        ref, label = self._consent_target(elements)
        if not ref:
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": "unknown_cookie_consent"}
        guard = self._observe_browser(
            mission, ComputerMissionStep("consent-observe", "Validar janela antes do consentimento",
                                         "observe_browser", expected_state={}))
        if not guard.get("ok"):
            return guard
        clicked = self.service.execute_tool(
            "browser_click", {"ref": ref, "selector": "", "text": ""},
            command="computer_mission:cookie_consent", task_id=mission.mission_id)
        if not clicked.get("ok"):
            return {"ok": False, "error": "COOKIE_CONSENT_ACTION_FAILED"}
        page_result = self.service.execute_tool(
            "browser_get_page_info", {}, command="computer_mission:cookie_consent",
            task_id=mission.mission_id)
        elements_result = self.service.execute_tool(
            "browser_get_elements", {}, command="computer_mission:cookie_consent",
            task_id=mission.mission_id)
        barrier = classify_page_barrier(page_result.get("page") or {},
                                        elements_result.get("elements") or [])
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool="browser_cookie_consent",
            arguments={"target": ref, "label": label},
            risk=mission.risk_level,
            status="dismissed" if barrier == "NONE" else "blocked",
            result={"browser": "chrome", "barrier_type": barrier,
                    "decision": "safe_consent_target"},
        )
        if barrier != "NONE":
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": barrier}
        return {"ok": True, "verified": True,
                "verification": "cookie_consent_dismissed"}

    def _prepare_search_provider(self, mission):
        while True:
            page_result = self.service.execute_tool(
                "browser_get_page_info", {}, command="computer_mission:classify_barrier",
                task_id=mission.mission_id)
            elements_result = self.service.execute_tool(
                "browser_get_elements", {}, command="computer_mission:ground_search_field",
                task_id=mission.mission_id)
            page = page_result.get("page") or {}
            elements = list(elements_result.get("elements") or [])
            barrier = classify_page_barrier(page, elements)
            mission.result["barrier_type"] = barrier
            if barrier == "COOKIE_CONSENT":
                consent = self._handle_cookie_consent(mission, page, elements)
                if not consent.get("ok"):
                    return consent
                continue
            if barrier in {"UNKNOWN_BLOCKER", "LOGIN_REQUIRED", "AUTH_REQUIRED",
                           "PRIVACY_CONSENT", "BENIGN_INTERSTITIAL"}:
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": barrier}
            if barrier in {"CAPTCHA", "ANTI_BOT", "BOT_VERIFICATION", "ACCESS_DENIED",
                           "RATE_LIMITED", "NETWORK_ERROR", "PAGE_ERROR"}:
                fallback = self._advance_provider(mission, barrier)
                if not fallback.get("ok"):
                    return fallback
                continue
            selected = self._search_field(elements)
            if selected:
                ref = str(selected[0].get("ref") or "")
                if ref:
                    mission.result["search_ref"] = ref
                    return {"ok": True, "verified": True, "ref": ref,
                            "verification": "structured_search_field_grounding"}
            fallback = self._advance_provider(mission, "SEARCH_FIELD_NOT_FOUND")
            if not fallback.get("ok"):
                return {"ok": False, "error": "SEARCH_FIELD_NOT_FOUND"}

    def _ground_search_field(self, mission):
        return self._prepare_search_provider(mission)

    def _extract_browser_results(self, mission, page, minimum=3):
        page = page or {}
        barrier = classify_page_barrier(page, page.get("interactive"))
        if barrier != "NONE":
            return {"ok": False, "barrier_type": barrier, "titles": [], "source_urls": []}
        links = [link for link in list(page.get("links") or [])
                 if link.get("visible", True) and link.get("result_candidate")]
        page_url = str(page.get("url") or "")
        try:
            page_host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(page_url).netloc
        except Exception:
            page_host = ""
        query = str(mission.result.get("search_query") or "").casefold()
        excluded = {"images", "videos", "maps", "news", "shopping", "sign in", "more",
                    "aceitar", "rejeitar", "privacy policy", "política de privacidade"}
        selected: dict[str, tuple[str, str]] = {}

        def title_score(value):
            lowered = value.casefold()
            return (0 if "›" in value or value.startswith("http") else 100) + min(len(value), 120)

        for link in links:
            title = " ".join(str(link.get("text") or "").split())
            href = str(link.get("href") or "")
            try:
                host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(href).netloc
            except Exception:
                host = ""
            lowered = title.casefold()
            if (len(title) < 3 or lowered in excluded or
                    any(marker in lowered for marker in ("sponsored", "patrocinado", "anúncio", "anuncio")) or
                    not href.startswith(("http://", "https://")) or host == page_host):
                continue
            normalized_href = href.rstrip("/")
            previous = selected.get(normalized_href)
            if previous is None or title_score(title) > title_score(previous[0]):
                selected[normalized_href] = (title, href)
            if len(selected) >= int(minimum):
                break
        titles = [item[0] for item in selected.values()]
        sources = [item[1] for item in selected.values()]
        page_text = " ".join(str(page.get(key) or "") for key in
                             ("url", "title", "text", "headings")).casefold()
        query_present = not query or query in page_text or query.replace(" ", "+") in page_url.casefold()
        ok = query_present and len(titles) >= int(minimum)
        return {"ok": ok, "barrier_type": "NONE", "titles": titles[:minimum],
                "source_urls": sources[:minimum],
                "result_page_confirmed": ok, "visible_results_read": bool(links)}

    def _fallback_search_and_extract(self, mission, step):
        for _ in range(MAX_SEARCH_PROVIDERS):
            prepared = self._prepare_search_provider(mission)
            if not prepared.get("ok"):
                return prepared
            search = self.service.execute_tool(
                "browser_search", {"query": mission.result["search_query"],
                                    "ref": mission.result.get("search_ref", "")},
                command="computer_mission:provider_fallback_search",
                task_id=mission.mission_id)
            if not search.get("ok"):
                fallback = self._advance_provider(mission, search.get("error", "SEARCH_FAILED"))
                if fallback.get("ok"):
                    continue
                return fallback
            observed = self._observe_browser(
                mission, ComputerMissionStep("fallback-observe", "Observar resultados do provider",
                                             "observe_browser", expected_state={"page_changed": True}))
            if not observed.get("ok"):
                return observed
            self.service.execute_tool(
                "browser_wait_for_results", {"timeout_ms": 10000},
                command="computer_mission:wait_fallback_results",
                task_id=mission.mission_id)
            page_result = self.service.execute_tool(
                "browser_get_page_info", {}, command="computer_mission:fallback_results",
                task_id=mission.mission_id)
            extracted = self._extract_browser_results(
                mission, page_result.get("page") or {}, minimum=3)
            if extracted.get("ok"):
                mission.result.update({
                    "titles": extracted["titles"],
                    "source_urls": extracted["source_urls"],
                    "result_page_confirmed": True,
                    "visible_results_read": True,
                    "page_title": (page_result.get("page") or {}).get("title", ""),
                    "page_url": (page_result.get("page") or {}).get("url", ""),
                })
                return {"ok": True, "verified": True,
                        "verification": "fallback_result_page_confirmed"}
            barrier = extracted.get("barrier_type") or "SEARCH_RESULTS_NOT_CONFIRMED"
            fallback = self._advance_provider(mission, barrier)
            if not fallback.get("ok"):
                return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                        "barrier_type": barrier}
        return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED"}

    def _verify_browser_results(self, mission, step):
        self.service.execute_tool(
            "browser_wait_for_results", {"timeout_ms": 10000},
            command="computer_mission:wait_results",
            task_id=mission.mission_id)
        result = self.service.execute_tool(
            "browser_get_page_info", {}, command="computer_mission:verify_results",
            task_id=mission.mission_id)
        page = result.get("page") or {}
        extracted = self._extract_browser_results(
            mission, page, minimum=int(step.expected_state.get("minimum", 3)))
        if extracted.get("ok"):
            titles = extracted["titles"]
            sources = extracted["source_urls"]
            mission.result.update({"titles": titles, "source_urls": sources,
                                   "page_title": page.get("title", ""),
                                   "page_url": page.get("url", ""),
                                   "result_page_confirmed": True,
                                   "visible_results_read": True})
            return {"ok": True, "verified": True, "titles": titles,
                    "source_urls": sources, "verification": "result_page_confirmed"}
        barrier = extracted.get("barrier_type") or "SEARCH_RESULTS_NOT_CONFIRMED"
        if barrier in {"UNKNOWN_BLOCKER", "LOGIN_REQUIRED", "AUTH_REQUIRED",
                       "PRIVACY_CONSENT", "BENIGN_INTERSTITIAL"}:
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": barrier}
        current_provider = SEARCH_PROVIDER_ORDER[int(mission.result.get("provider_index", 0))]
        self._provider_health(mission, current_provider, "BLOCKED", barrier)
        fallback = self._advance_provider(mission, barrier)
        if fallback.get("ok"):
            return self._fallback_search_and_extract(mission, step)
        return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                "barrier_type": barrier}

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
        if step.action_type in {"focus_browser", "observe_browser", "ground_search_field",
                                "verify_browser_results"}:
            return bool(result.get("verified") or result.get("focused"))
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
