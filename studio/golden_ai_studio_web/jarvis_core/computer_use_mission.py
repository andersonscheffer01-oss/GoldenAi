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
from urllib.parse import urlparse

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
class MissionValue:
    """A short-lived observed/user/derived value owned by one mission."""

    value: str
    mission_id: str
    kind: str
    source_app: str = ""
    source_type: str = ""
    source_title: str = ""
    source_url: str = ""
    observed_at: float = field(default_factory=time.time)
    confidence: str = "verified"
    context_version: int = 0
    source_state_id: str = ""
    valid_until_step: Optional[int] = None
    invalidated: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind,
            "source_app": self.source_app,
            "source_type": self.source_type,
            "source_title": self.source_title,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "context_version": self.context_version,
            "source_state_id": self.source_state_id,
            "valid_until_step": self.valid_until_step,
            "invalidated": self.invalidated,
        }


@dataclass
class MissionContext:
    """Transient cross-application state; never the Jarvis long-term memory."""

    mission_id: str
    user_request: str
    current_app: str = ""
    previous_app: str = ""
    variables: dict[str, MissionValue] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    context_version: int = 0
    app_switches: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def store_variable(self, name: str, value: str, *, kind: str,
                       source_app: str = "", source_type: str = "",
                       source_title: str = "", source_url: str = "",
                       confidence: str = "verified", source_state_id: str = "",
                       valid_until_step: Optional[int] = None) -> MissionValue:
        self.context_version += 1
        stored = MissionValue(
            value=str(value), mission_id=self.mission_id, kind=kind,
            source_app=source_app, source_type=source_type,
            source_title=source_title, source_url=source_url,
            confidence=confidence, context_version=self.context_version,
            source_state_id=source_state_id, valid_until_step=valid_until_step,
        )
        self.variables[str(name)] = stored
        self.source_provenance[str(name)] = stored.public()
        self.updated_at = time.time()
        return stored

    def resolve(self, name: str, *, mission_id: str,
                current_step: int) -> tuple[Optional[MissionValue], str]:
        stored = self.variables.get(str(name))
        if stored is None:
            return None, "MISSING_MISSION_VARIABLE"
        if stored.mission_id != mission_id or stored.invalidated:
            return None, "STALE_CONTEXT_DETECTED"
        if (stored.valid_until_step is not None and
                current_step > stored.valid_until_step):
            return None, "STALE_CONTEXT_DETECTED"
        return stored, ""

    def invalidate(self, name: str, reason: str = "") -> bool:
        stored = self.variables.get(str(name))
        if stored is None:
            return False
        stored.invalidated = True
        self.context_version += 1
        self.updated_at = time.time()
        self.artifacts.setdefault("invalidations", {})[str(name)] = {
            "reason": reason, "context_version": self.context_version,
        }
        return True

    def public(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "user_request": self.user_request,
            "current_app": self.current_app,
            "previous_app": self.previous_app,
            "variables": {key: value.public() for key, value in self.variables.items()},
            "artifacts": dict(self.artifacts),
            "step_outputs": dict(self.step_outputs),
            "source_provenance": dict(self.source_provenance),
            "context_version": self.context_version,
            "app_switches": self.app_switches,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ComputerMissionStep:
    step_id: str
    description: str
    action_type: str
    target: str = ""
    expected_state: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    app: str = ""
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
    context: Optional[MissionContext] = None

    def __post_init__(self):
        if self.context is None:
            self.context = MissionContext(self.mission_id, self.user_request)

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
            "context": self.context.public() if self.context else {},
            "steps": [
                {
                    "step_id": step.step_id,
                    "description": step.description,
                    "action_type": step.action_type,
                    "target": step.target,
                    "expected_state": dict(step.expected_state),
                    "app": step.app,
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
    _MULTI_APP_RE = re.compile(
        r"(?:chrome|navegador).*(?:bloco\s+de\s+notas|notepad).*"
        r"(?:salv|escrev|digit)", re.I | re.S)

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
        if self._is_multi_app_request(text):
            return True
        if self._BROWSER_RE.search(text):
            return bool(re.search(r"\b(pesquis|buscar|busque|procure)\w*\b", low))
        return bool(self._NOTEPAD_RE.search(text) and
                    re.search(r"\b(escrev|digit|salv|confirme|funcionando)\w*\b", low))

    def plan(self, request: str) -> ComputerMission:
        if not self.can_plan(request):
            raise ValueError("Missão Computer Use não reconhecida.")
        text = str(request).strip()
        if self._is_multi_app_request(text):
            return self._plan_multi_app(text)
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

        def step(step_id, description, action_type, target="", expected=None, args=None,
                 app=""):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {}, app=app)

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

    def _is_multi_app_request(self, text: str) -> bool:
        low = str(text or "").casefold()
        return bool(self._MULTI_APP_RE.search(text) and "document" in low)

    def _plan_multi_app(self, text: str) -> ComputerMission:
        low = text.casefold()
        title_mode = bool(re.search(r"t[ií]tulo", low))
        value_key = "python_page_title" if title_mode else "python_version"
        query = ("Python official homepage Python.org" if title_mode else
                 "current stable Python version official Python")
        template = ("{{python_page_title}}" if title_mode else
                    "Versão atual do Python: {{python_version}}")
        match = re.search(r"\bsalv(?:e|ar|a)\s+(?:como\s+)?([\w.-]+)", text, re.I)
        filename = Path(match.group(1)).name if match else (
            "titulo_python.txt" if title_mode else "pesquisa_python.txt")
        if not filename or filename in {".", ".."}:
            raise ValueError("Nome de arquivo inválido para a missão multiaplicativo.")
        target_path = self.resolve_target_path(filename)
        tool_names = {
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "browser_click",
            "browser_record_window", "browser_wait_for_results", "ui_active_window",
            "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
            "ui_invoke_element", "ui_classify_dialog", "ui_list_elements",
            "open_program", "keyboard_type",
            "keyboard_hotkey", "keyboard_press",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None,
                 app=""):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {}, app=app)

        steps = [
            step("open-browser", "Abrir Google Chrome", "browser_open", "browser",
                  args={"visible": True, "provider": "chrome"}, app="chrome"),
            step("navigate-search-home", "Abrir a página de pesquisa", "browser_navigate",
                  DEFAULT_SEARCH_HOME, args={"url": DEFAULT_SEARCH_HOME}, app="chrome"),
            step("focus-browser", "Validar foco do Chrome", "focus_browser", "browser",
                  expected={"browser_process": True}, app="chrome"),
            step("observe-browser", "Validar identidade do Chrome", "observe_browser", "browser",
                  expected={"browser_process": True}, app="chrome"),
            step("ground-search-field", "Localizar campo de pesquisa", "ground_search_field",
                  "search-field", app="chrome"),
            step("execute-search", "Pesquisar o dado solicitado", "browser_search",
                  "search-field", args={"query": query, "ref": ""}, app="chrome"),
            step("observe-results", "Confirmar página de resultados", "observe_browser", "results",
                  expected={"page_changed": True}, app="chrome"),
            step("extract-mission-value", "Extrair e validar o valor observado",
                  "extract_mission_value", "browser-result", app="chrome"),
            step("handoff-to-notepad", "Transferir a missão para o Bloco de Notas",
                  "handoff_to_notepad", "notepad", args={"name": "bloco de notas"},
                  app="notepad"),
            step("focus-notepad", "Validar foco do Bloco de Notas", "ui_focus_window",
                  "notepad", expected={"process": "notepad"},
                  args={"window": "notepad"}, app="notepad"),
            step("observe-notepad", "Validar identidade do Bloco de Notas", "observe_window",
                  "notepad", expected={"process": "notepad"}, app="notepad"),
            step("capture-preexisting-document", "Registrar documento pré-existente",
                  "capture_document_state", "notepad", app="notepad"),
            step("new-notepad-document", "Abrir uma nova aba em branco",
                  "keyboard_hotkey", "notepad", expected={"process": "notepad"},
                  args={"keys": ["ctrl", "n"]}, app="notepad"),
            step("capture-mission-document", "Registrar documento criado pela missão",
                  "capture_document_state", "notepad", app="notepad"),
            step("check-overwrite", "Verificar política de sobrescrita", "check_overwrite_policy",
                  str(target_path), app="notepad"),
            step("type-mission-template", "Resolver o valor e escrever o texto",
                  "type_mission_template", "notepad-editor",
                  expected={"process": "notepad"},
                  args={"template": template, "source_variable": value_key}, app="notepad"),
            step("verify-editor-pre-save", "Validar editor antes do salvamento",
                  "verify_editor_pre_save", "notepad-editor",
                  expected={"process": "notepad"}, app="notepad"),
            step("open-save-dialog", "Abrir Salvar como", "keyboard_hotkey", "save-dialog",
                  expected={"process": "notepad"},
                  args={"keys": ["ctrl", "shift", "s"]}, app="notepad"),
            step("observe-save-dialog", "Validar Salvar como", "observe_window", "save-dialog",
                  expected={"title": ("save as", "salvar como"), "process": "notepad"},
                  app="notepad"),
            step("focus-file-name", "Focar nome do arquivo", "ui_focus_element", "file-name",
                  expected={"control_type": "Edit"},
                  args={"target": "", "control_type": "Edit", "window": ""}, app="notepad"),
            step("type-file-name", "Informar o caminho autorizado", "keyboard_type", "file-name",
                  expected={"title": ("save as", "salvar como")},
                  args={"text": str(target_path), "interval": 0.03}, app="notepad"),
            step("focus-save-button", "Groundar o botão Salvar", "ui_focus_element", "save-button",
                  expected={"control_type": "Button"},
                  args={"target": "Salvar", "control_type": "Button", "window": ""},
                  app="notepad"),
            step("confirm-save", "Confirmar salvamento", "ui_invoke_element", "save-button",
                  expected={"control_type": "Button"},
                  args={"target": "Salvar", "control_type": "Button", "window": ""},
                  app="notepad"),
            step("handle-overwrite-confirmation", "Confirmar sobrescrita somente do alvo autorizado",
                  "handle_overwrite_confirmation", "overwrite-dialog", app="notepad"),
            step("observe-saved-window", "Confirmar retorno ao Notepad", "observe_window",
                  "notepad", expected={"process": "notepad"}, app="notepad"),
            step("verify-cross-app-file", "Validar arquivo e valor transferido",
                  "verify_cross_app_file", str(target_path), app="notepad"),
        ]
        mission = ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                                  time.time(), steps, max_steps=self.MAX_STEPS)
        mission.result.update({
            "multi_app_mission": True,
            "search_query": query,
            "value_key": value_key,
            "filename": filename,
            "target_path": str(target_path),
            "original_user_request": text,
            "browser_mission": True,
            "search_provider": SEARCH_PROVIDER_ORDER[0],
            "provider_index": 0,
            "provider_health": [],
            "document_ownership": "PENDING",
        })
        mission.context.artifacts["search_query"] = {
            "value": query, "kind": "USER_VALUE",
        }
        return mission

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
    MAX_APP_SWITCHES = 4

    def __init__(self, service, planner: Optional[ComputerMissionPlanner] = None):
        self.service = service
        self.planner = planner or ComputerMissionPlanner(service.registry)
        self._active: Optional[ComputerMission] = None
        self._missions: dict[str, ComputerMission] = {}
        self._lock = threading.RLock()
        self._cancel = threading.Event()

    def run(self, request: str, task_id: str = "desktop",
            authorized_overwrite_paths: Optional[list[str]] = None) -> dict[str, Any]:
        mission = self.planner.plan(request)
        if authorized_overwrite_paths:
            mission.result["authorized_overwrite_paths"] = [
                str(Path(path).resolve()) for path in authorized_overwrite_paths
            ]
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
        revalidated = self._resume_revalidate(mission, current, task_id)
        if not revalidated.get("ok"):
            mission.status = MissionStatus.BLOCKED
            mission.error = str(revalidated.get("error") or "RESUME_REVALIDATION_FAILED")
            current.status = MissionStepStatus.BLOCKED
            current.error = mission.error
            self._audit_step(mission, current, revalidated, "resume_revalidation_failed")
            return self._finish(mission, False)
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
            elif step.action_type == "extract_mission_value":
                step.status = MissionStepStatus.VERIFYING
                result = self._extract_mission_value(mission, step)
            elif step.action_type == "handoff_to_notepad":
                result = self._handoff_to_notepad(mission, step)
            elif step.action_type == "capture_document_state":
                result = self._capture_document_state(mission, step, task_id)
            elif step.action_type == "check_overwrite_policy":
                result = self._check_overwrite_policy(mission, step)
            elif step.action_type == "type_mission_template":
                result = self._type_mission_template(mission, step, task_id,
                                                     preconfirmed=preconfirmed)
                preconfirmed = None
            elif step.action_type == "verify_editor_pre_save":
                result = self._verify_editor_content(mission, step, task_id,
                                                     pre_save=True)
            elif step.action_type == "handle_overwrite_confirmation":
                result = self._handle_overwrite_confirmation(
                    mission, step, task_id, preconfirmed=preconfirmed)
                preconfirmed = None
            elif step.action_type == "verify_cross_app_file":
                step.status = MissionStepStatus.VERIFYING
                result = self._verify_cross_app_file(mission, step)
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
                    "MISSING_MISSION_VARIABLE", "UNRESOLVED_TEMPLATE_VARIABLE",
                    "STALE_CONTEXT_DETECTED", "SOURCE_VERIFICATION_FAILED",
                    "APP_IDENTITY_MISMATCH", "CROSS_APP_DATA_MISMATCH",
                    "APP_SWITCH_LOOP_DETECTED", "EDITOR_CONTENT_EMPTY",
                    "EDITOR_CONTENT_MISMATCH", "STALE_EDITOR_TARGET",
                    "EDITOR_NOT_FOUND", "EDITOR_PROCESS_MISMATCH",
                    "OVERWRITE_CONFIRMATION_NOT_DISMISSED", "DOCUMENT_NOT_FOUND",
                    "DOCUMENT_IDENTITY_UNAVAILABLE", "DOCUMENT_IDENTITY_MISMATCH",
                    "DOCUMENT_WINDOW_MISMATCH", "MISSION_DOCUMENT_NOT_REGISTERED",
                    "DIALOG_OWNERSHIP_MISMATCH",
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
            self._record_step_output(mission, step)
            self._audit_step(mission, step, result, "completed")
            mission.current_step += 1
            mission.status = MissionStatus.OBSERVING

        mission.status = MissionStatus.COMPLETED
        if mission.result.get("multi_app_mission"):
            final = mission.steps[-1].result
            mission.result.update({
                "mission_completed": True,
                "file_exists": bool(final.get("file_exists")),
                "content_valid": bool(final.get("content_valid")),
                "cross_app_data_match": bool(final.get("cross_app_data_match")),
                "variable_stored": bool(mission.context and mission.context.variables),
                "provenance_stored": bool(mission.context and mission.context.source_provenance),
                "context_version": mission.context.context_version if mission.context else 0,
                "current_app": mission.context.current_app if mission.context else "",
                "document_ownership": mission.result.get("document_ownership", ""),
                "mission_document_id": mission.result.get("mission_document_id", ""),
            })
        elif mission.result.get("browser_mission"):
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
        if (mission.result.get("multi_app_mission") and step.app == "notepad" and
                step.step_id not in {"focus-notepad", "observe-notepad",
                                     "capture-preexisting-document",
                                     "new-notepad-document", "capture-mission-document"}):
            ownership = self._assert_mission_document(mission, task_id)
            if not ownership.get("ok"):
                return ownership
        step.status = MissionStepStatus.EXECUTING
        return self.service.execute_tool(step.action_type, step.args,
                                          command=f"computer_mission:{mission.mission_id}",
                                          task_id=mission.mission_id)

    def _resume_revalidate(self, mission, step, task_id):
        """Re-observe mission-owned state before consuming a confirmation."""
        if not mission.result.get("multi_app_mission") or step.app != "notepad":
            return {"ok": True, "verification": "resume_revalidation_not_required"}
        if step.step_id == "new-notepad-document":
            return self._assert_preexisting_document(mission, task_id)
        if step.action_type == "handle_overwrite_confirmation":
            dialog = self.service.execute_tool(
                "ui_classify_dialog", {},
                command=f"computer_mission:{mission.mission_id}:resume_dialog",
                task_id=task_id)
            if dialog.get("dialog_type") != "FILE_OVERWRITE_DIALOG":
                return {"ok": False, "error": "DIALOG_OWNERSHIP_MISMATCH"}
        return self._assert_mission_document(mission, task_id)

    def _assert_preexisting_document(self, mission, task_id):
        """Ensure a confirmed tab action still targets the protected document."""
        artifacts = mission.context.artifacts if mission.context else {}
        pre_existing = set(artifacts.get("pre_existing_document_ids") or [])
        if not pre_existing:
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        observed = self.service.execute_tool(
            "ui_read_editor", {"window": "notepad", "expected_process": "notepad"},
            command=f"computer_mission:{mission.mission_id}:preexisting_guard",
            task_id=task_id)
        if observed.get("path_error_dialog"):
            return {"ok": False, "error": "PATH_NOT_FOUND", "path_error_dialog": True}
        if not observed.get("found") or not observed.get("verified"):
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        editor = observed.get("editor") or {}
        current_id = str(editor.get("document_identity") or "")
        if current_id not in pre_existing:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "current_document_id": current_id,
                    "pre_existing_document_ids": sorted(pre_existing)}
        expected_window = int((artifacts.get("pre_existing_documents") or [{}])[0].get("window_id") or 0)
        current_window = int((observed.get("window") or {}).get("handle") or 0)
        if expected_window and current_window != expected_window:
            return {"ok": False, "error": "DOCUMENT_WINDOW_MISMATCH",
                    "pre_existing_window_id": expected_window,
                    "current_window_id": current_window}
        return {"ok": True, "verified": True,
                "verification": "pre_existing_document_revalidated",
                "document_identity": current_id}

    def _cancelled_result(self):
        return {"ok": False, "error": "MISSION_CANCELLED"}

    def _record_step_output(self, mission, step):
        if not mission.context:
            return
        mission.context.step_outputs[step.step_id] = dict(step.result)
        if step.app and not mission.context.current_app:
            mission.context.current_app = step.app
        mission.context.updated_at = time.time()

    def _audit_context_event(self, mission, tool, status, result, *, app="",
                             previous_app="", source_variable="", destination=""):
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool=tool,
            arguments={
                "mission_id": mission.mission_id,
                "app": app,
                "previous_app": previous_app,
                "source_variable": source_variable,
                "destination": destination,
            },
            risk=mission.risk_level,
            status=status,
            result={"ok": bool(result.get("ok")), "error": result.get("error", "")},
        )

    def _extract_mission_value(self, mission, step):
        key = str(mission.result.get("value_key") or "python_version")
        mode = "title" if key == "python_page_title" else "version"
        version_re = re.compile(
            r"\bPython\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b", re.I)

        for attempt in range(MAX_SEARCH_PROVIDERS):
            if self._cancel.is_set() or self.service.cancellation.is_cancelled():
                return self._cancelled_result()
            self.service.execute_tool(
                "browser_wait_for_results", {"timeout_ms": 10000},
                command="computer_mission:extract_value_wait",
                task_id=mission.mission_id)
            page_result = self.service.execute_tool(
                "browser_get_page_info", {}, command="computer_mission:extract_value",
                task_id=mission.mission_id)
            page = page_result.get("page") or {}
            barrier = classify_page_barrier(page, page.get("interactive"))
            if barrier in {"UNKNOWN_BLOCKER", "LOGIN_REQUIRED", "AUTH_REQUIRED",
                           "PRIVACY_CONSENT", "BENIGN_INTERSTITIAL"}:
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": barrier}
            candidates = [item for item in list(page.get("links") or [])
                          if item.get("visible", True) and item.get("result_candidate")]
            official = [item for item in candidates if (
                urlparse(str(item.get("href") or "")).netloc.casefold() == "python.org" or
                urlparse(str(item.get("href") or "")).netloc.casefold().endswith(".python.org"))]
            selected = None
            version_match = None
            if official and barrier == "NONE":
                if mode == "version":
                    for item in official:
                        haystack = " ".join(
                            str(item.get(field) or "")
                            for field in ("text", "aria_label", "title"))
                        version_match = version_re.search(haystack)
                        if version_match:
                            selected = item
                            break
                else:
                    selected = official[0]
            if selected is not None:
                source_title = " ".join(
                    " ".join(str(selected.get(field) or "").split())
                    for field in ("text", "title") if selected.get(field)
                ).strip()
                source_url = str(selected.get("href") or "")
                if mode == "title" and re.fullmatch(
                        r"(?:https?://|www\.)\S+", source_title, re.I):
                    navigated = self.service.execute_tool(
                        "browser_navigate", {"url": source_url},
                        command="computer_mission:official_source_title",
                        task_id=mission.mission_id)
                    if not navigated.get("ok"):
                        selected = None
                    else:
                        observed = self._observe_browser(
                            mission,
                            ComputerMissionStep(
                                "official-source-observe",
                                "Observar título da fonte oficial",
                                "observe_browser", expected_state={}, app="chrome"))
                        if not observed.get("ok"):
                            return observed
                        official_page = self.service.execute_tool(
                            "browser_get_page_info", {},
                            command="computer_mission:official_source_title",
                            task_id=mission.mission_id)
                        page_title = " ".join(str(
                            (official_page.get("page") or {}).get("title") or ""
                        ).split())
                        if page_title and not re.fullmatch(
                                r"(?:https?://|www\.)\S+", page_title, re.I):
                            source_title = page_title
                        else:
                            selected = None
                value = (f"Python {version_match.group(1)}"
                         if mode == "version" and version_match else source_title)
                if selected is not None and value:
                    state_id = str(mission.result.get("browser_page_state_id") or
                                   page.get("url") or "")
                    stored = mission.context.store_variable(
                        key, value, kind="OBSERVED_VALUE", source_app="chrome",
                        source_type="browser_result", source_title=source_title,
                        source_url=source_url, confidence="verified",
                        source_state_id=state_id,
                        valid_until_step=mission.current_step + mission.max_steps)
                    mission.result.update({
                        key: value, "value_extracted": True, "source_found": True,
                        "source_verified": True, "source_provenance": stored.public(),
                    })
                    self._audit_context_event(
                        mission, "CONTEXT_VALUE_CREATED", "stored", {"ok": True},
                        app="chrome", source_variable=key, destination="mission_context")
                    return {"ok": True, "verified": True,
                            "verification": "observed_official_value", "value": value,
                            "source_variable": key, "source_url": source_url,
                            "source_title": source_title}
            if attempt >= MAX_SEARCH_PROVIDERS - 1:
                break
            fallback = self._advance_provider(mission, "SOURCE_VERIFICATION_FAILED")
            if not fallback.get("ok"):
                break
            prepared = self._prepare_search_provider(mission)
            if not prepared.get("ok"):
                if prepared.get("error") == "USER_CONFIRMATION_REQUIRED":
                    return prepared
                continue
            search = self.service.execute_tool(
                "browser_search", {"query": mission.result.get("search_query", ""),
                                    "ref": mission.result.get("search_ref", "")},
                command="computer_mission:value_provider_search",
                task_id=mission.mission_id)
            if not search.get("ok"):
                continue
            observed = self._observe_browser(
                mission, ComputerMissionStep("value-provider-observe",
                                             "Observar provider de valor", "observe_browser",
                                             expected_state={"page_changed": True}, app="chrome"))
            if not observed.get("ok"):
                continue
        return {"ok": False, "error": "SOURCE_VERIFICATION_FAILED"}

    def _handoff_to_notepad(self, mission, step):
        context = mission.context
        if not context:
            return {"ok": False, "error": "MISSING_MISSION_CONTEXT"}
        if self._cancel.is_set() or self.service.cancellation.is_cancelled():
            return self._cancelled_result()
        if context.app_switches >= self.MAX_APP_SWITCHES:
            return {"ok": False, "error": "APP_SWITCH_LOOP_DETECTED"}
        previous = context.current_app
        self._audit_context_event(
            mission, "APP_HANDOFF_STARTED", "switching", {"ok": True},
            app="notepad", previous_app=previous, destination="notepad")
        opened = self.service.execute_tool(
            "open_program", {"name": step.args.get("name", "bloco de notas")},
            command=f"computer_mission:{mission.mission_id}", task_id=mission.mission_id)
        if not opened.get("ok"):
            return {"ok": False, "error": "APP_HANDOFF_FAILED"}
        if self._cancel.is_set() or self.service.cancellation.is_cancelled():
            return self._cancelled_result()
        focused = self.service.execute_tool(
            "ui_focus_window", {"window": "notepad"},
            command=f"computer_mission:{mission.mission_id}", task_id=mission.mission_id)
        if not focused.get("ok"):
            return {"ok": False, "error": "APP_HANDOFF_FAILED"}
        active = self.service.execute_tool(
            "ui_active_window", {}, command=f"computer_mission:{mission.mission_id}",
            task_id=mission.mission_id)
        data = active.get("result") if isinstance(active.get("result"), dict) else active
        process = str(data.get("process_name") or "").casefold()
        if process != "notepad.exe":
            return {"ok": False, "error": "APP_IDENTITY_MISMATCH", "window": data}
        context.previous_app = previous
        context.current_app = "notepad"
        context.app_switches += 1
        context.context_version += 1
        context.updated_at = time.time()
        result = {"ok": True, "verified": True, "verification": "app_handoff_completed",
                  "window": data, "previous_app": previous, "app": "notepad"}
        self._audit_context_event(
            mission, "APP_HANDOFF_COMPLETED", "completed", result,
            app="notepad", previous_app=previous, destination="notepad")
        return result

    def _capture_document_state(self, mission, step, task_id):
        observed = self.service.execute_tool(
            "ui_read_editor", {"window": "notepad", "expected_process": "notepad"},
            command=f"computer_mission:{mission.mission_id}:document_state",
            task_id=task_id)
        if observed.get("path_error_dialog"):
            return {"ok": False, "error": "PATH_NOT_FOUND", "path_error_dialog": True}
        if not observed.get("found") or not observed.get("verified"):
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        editor = observed.get("editor") or {}
        document_id = str(editor.get("document_identity") or "")
        window = observed.get("window") or {}
        if not document_id or not window.get("handle"):
            return {"ok": False, "error": "DOCUMENT_IDENTITY_UNAVAILABLE"}
        tabs = self.service.execute_tool(
            "ui_list_elements", {"window": "notepad", "limit": 100},
            command=f"computer_mission:{mission.mission_id}:document_tabs",
            task_id=task_id)
        tab_records = [item for item in (tabs.get("elements") or [])
                       if str(item.get("control_type") or "").casefold() == "tabitem"]
        owned = step.step_id == "capture-mission-document"
        artifacts = mission.context.artifacts
        if not owned:
            existing = set(artifacts.get("pre_existing_document_ids") or [])
            existing.add(document_id)
            artifacts["pre_existing_document_ids"] = sorted(existing)
            artifacts["pre_existing_documents"] = [{
                "document_id": document_id, "window_id": window.get("handle"),
                "process_id": window.get("pid"), "content_state_id": editor.get("content_state_id"),
            }]
            artifacts["pre_existing_tabs"] = tab_records
            mission.result["document_ownership"] = "PRE_EXISTING_DOCUMENT_PROTECTED"
            return {"ok": True, "verified": True,
                    "verification": "pre_existing_document_recorded",
                    "document_identity": document_id,
                    "pre_existing_document": True}
        if document_id in set(artifacts.get("pre_existing_document_ids") or []):
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "document_identity": document_id}
        artifacts.update({
            "mission_document_id": document_id,
            "mission_window_id": int(window.get("handle") or 0),
            "mission_document_content_state_id": editor.get("content_state_id", ""),
            "mission_document_created_by_mission": True,
            "mission_document_app": "notepad",
            "mission_document_tabs": tab_records,
        })
        mission.result.update({
            "mission_document_id": document_id,
            "mission_window_id": int(window.get("handle") or 0),
            "document_ownership": "OWNED_BY_CURRENT_MISSION",
        })
        return {"ok": True, "verified": True,
                "verification": "mission_document_registered",
                "document_identity": document_id,
                "mission_document_id": document_id,
                "created_by_mission": True}

    def _assert_mission_document(self, mission, task_id, *, expected_text=None):
        artifacts = mission.context.artifacts if mission.context else {}
        mission_document_id = str(artifacts.get("mission_document_id") or "")
        if not mission_document_id:
            return {"ok": False, "error": "MISSION_DOCUMENT_NOT_REGISTERED"}
        observed = self.service.execute_tool(
            "ui_read_editor", {"window": "notepad", "expected_process": "notepad"},
            command=f"computer_mission:{mission.mission_id}:document_guard",
            task_id=task_id)
        if observed.get("path_error_dialog"):
            return {"ok": False, "error": "PATH_NOT_FOUND", "path_error_dialog": True}
        if not observed.get("found") or not observed.get("verified"):
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        editor = observed.get("editor") or {}
        current_id = str(editor.get("document_identity") or "")
        if current_id != mission_document_id:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "mission_document_id": mission_document_id,
                    "current_document_id": current_id}
        expected_window = int(artifacts.get("mission_window_id") or 0)
        current_window = int((observed.get("window") or {}).get("handle") or 0)
        if expected_window and current_window != expected_window:
            return {"ok": False, "error": "DOCUMENT_WINDOW_MISMATCH",
                    "mission_window_id": expected_window,
                    "current_window_id": current_window}
        actual = str(observed.get("text") or "")
        if expected_text is not None and actual == "":
            return {"ok": False, "error": "EDITOR_CONTENT_EMPTY",
                    "editor_text": actual}
        if expected_text is not None and actual != str(expected_text):
            return {"ok": False, "error": "EDITOR_CONTENT_MISMATCH",
                    "editor_text": actual}
        return {"ok": True, "verified": True,
                "verification": "mission_document_identity_match",
                "mission_document_id": mission_document_id,
                "editor_text": actual,
                "content_state_id": editor.get("content_state_id", "")}

    def _check_overwrite_policy(self, mission, step):
        path = Path(step.target)
        authorized = {
            str(Path(item).resolve())
            for item in mission.result.get("authorized_overwrite_paths", [])
        }
        created = {
            str(Path(item).resolve())
            for item in (mission.context.artifacts.get("created_paths", [])
                         if mission.context else [])
        }
        if path.exists() and str(path.resolve()) not in authorized | created:
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": "overwrite_existing_file", "path": str(path)}
        verification = ("authorized_overwrite_target" if path.exists()
                        else "overwrite_policy_clear")
        return {"ok": True, "verified": True, "verification": verification,
                "path": str(path)}

    def _render_template(self, mission, template):
        context = mission.context
        if not context:
            return None, "MISSING_MISSION_CONTEXT", []
        names = re.findall(r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}", template)
        rendered = str(template)
        consumed = []
        for name in names:
            stored, error = context.resolve(
                name, mission_id=mission.mission_id, current_step=mission.current_step)
            if error:
                return None, error, consumed
            rendered = re.sub(r"\{\{\s*" + re.escape(name) + r"\s*\}\}",
                              stored.value, rendered, count=1)
            consumed.append(name)
            self._audit_context_event(
                mission, "CONTEXT_VALUE_CONSUMED", "consumed", {"ok": True},
                app="notepad", source_variable=name, destination="keyboard_type")
        if "{{" in rendered or "}}" in rendered:
            return None, "UNRESOLVED_TEMPLATE_VARIABLE", consumed
        return rendered, "", consumed

    def _type_mission_template(self, mission, step, task_id, preconfirmed=None):
        rendered, error, consumed = self._render_template(
            mission, str(step.args.get("template") or ""))
        if error:
            return {"ok": False, "error": error}
        guard = self._observe_window(step)
        if not guard.get("ok"):
            return guard
        ownership = self._assert_mission_document(mission, task_id)
        if not ownership.get("ok"):
            return ownership
        if self._cancel.is_set() or self.service.cancellation.is_cancelled():
            return self._cancelled_result()
        focused = self.service.execute_tool(
            "ui_focus_editor", {"window": "notepad", "expected_process": "notepad"},
            command=f"computer_mission:{mission.mission_id}", task_id=task_id)
        if not focused.get("ok"):
            if focused.get("path_error_dialog"):
                return {"ok": False, "error": "PATH_NOT_FOUND",
                        "path_error_dialog": True}
            reason = str(focused.get("reason") or "")
            error = ("EDITOR_PROCESS_MISMATCH" if reason == "process_mismatch"
                     else "EDITOR_NOT_FOUND")
            return {"ok": False, "error": error, "editor": focused.get("editor")}
        focused_id = str((focused.get("editor") or {}).get("document_identity") or "")
        mission_id = str(mission.context.artifacts.get("mission_document_id") or "")
        if focused_id != mission_id:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "mission_document_id": mission_id,
                    "current_document_id": focused_id}
        if preconfirmed and preconfirmed[0] is step:
            typed = preconfirmed[1]
        else:
            typed = self.service.execute_tool(
                "keyboard_type", {"text": rendered, "interval": step.args.get("interval", 0.03)},
                command=f"computer_mission:{mission.mission_id}", task_id=task_id)
        if typed.get("confirmation_required"):
            return typed
        if not typed.get("ok"):
            return typed
        mission.context.artifacts["text_input_sent"] = True
        verified = self._verify_editor_content(mission, step, task_id)
        if not verified.get("ok"):
            # One bounded recovery is allowed: refocus the freshly resolved
            # editor and resend only after the observed content failed exact
            # comparison.  Save As is never reached on a failed verification.
            if verified.get("error") in {"EDITOR_CONTENT_EMPTY", "EDITOR_CONTENT_MISMATCH"}:
                refocused = self.service.execute_tool(
                    "ui_focus_editor",
                    {"window": "notepad", "expected_process": "notepad"},
                    command=f"computer_mission:{mission.mission_id}:editor_recovery",
                    task_id=task_id)
                if refocused.get("ok"):
                    self.service.execute_tool(
                        "keyboard_hotkey", {"keys": ["ctrl", "a"]},
                        command=f"computer_mission:{mission.mission_id}:editor_recovery",
                        task_id=task_id)
                    retried = self.service.execute_tool(
                        "keyboard_type", {"text": rendered, "interval": step.args.get("interval", 0.03)},
                        command=f"computer_mission:{mission.mission_id}:editor_recovery",
                        task_id=task_id)
                    if retried.get("ok"):
                        verified = self._verify_editor_content(mission, step, task_id)
        if not verified.get("ok"):
            return verified
        mission.context.artifacts["rendered_text"] = {
            "value": rendered, "kind": "DERIVED_VALUE",
            "source_variables": consumed, "context_version": mission.context.context_version,
        }
        return {"ok": True, "verified": True,
                "verification": "template_resolved_typed_and_editor_verified",
                "text": rendered, "source_variable": consumed,
                "text_input_sent": True, "editor_content_verified": True,
                "mission_to_editor_match": True,
                "editor_identity": verified.get("editor_identity"),
                "content_state_id": verified.get("content_state_id")}

    def _verify_editor_content(self, mission, step, task_id, pre_save=False):
        rendered = str((mission.context.artifacts.get("rendered_text") or {}).get("value") or "")
        if not rendered:
            # During the first verification the rendered text is still carried
            # by the current template step.
            rendered, error, _ = self._render_template(
                mission, str(step.args.get("template") or ""))
            if error:
                return {"ok": False, "error": error}
        guard = self._observe_window(step)
        if not guard.get("ok"):
            return guard
        ownership = self._assert_mission_document(
            mission, task_id, expected_text=rendered)
        if not ownership.get("ok"):
            return ownership
        observed = self.service.execute_tool(
            "ui_read_editor", {"window": "notepad", "expected_process": "notepad"},
            command=f"computer_mission:{mission.mission_id}:read_editor",
            task_id=task_id)
        if not observed.get("found") or not observed.get("verified"):
            if observed.get("path_error_dialog"):
                return {"ok": False, "error": "PATH_NOT_FOUND",
                        "path_error_dialog": True}
            reason = str(observed.get("reason") or "")
            return {"ok": False,
                    "error": ("EDITOR_PROCESS_MISMATCH" if reason == "process_mismatch"
                               else "EDITOR_NOT_FOUND"),
                    "editor_content_verified": False}
        editor = observed.get("editor") or {}
        actual = str(observed.get("text") or "")
        mission_document_id = str(mission.context.artifacts.get("mission_document_id") or "")
        if str(editor.get("document_identity") or "") != mission_document_id:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "editor_content_verified": False}
        if actual == "":
            return {"ok": False, "error": "EDITOR_CONTENT_EMPTY",
                    "editor_content_verified": False, "editor_identity": editor.get("document_identity")}
        if actual != rendered:
            return {"ok": False, "error": "EDITOR_CONTENT_MISMATCH",
                    "editor_content_verified": False, "editor_text": actual,
                    "editor_identity": editor.get("document_identity")}
        identity = str(editor.get("document_identity") or "")
        previous_identity = str(mission.context.artifacts.get("editor_identity") or "")
        if pre_save and previous_identity and identity != previous_identity:
            return {"ok": False, "error": "STALE_EDITOR_TARGET",
                    "editor_content_verified": False,
                    "editor_identity": identity, "previous_editor_identity": previous_identity}
        mission.context.artifacts["editor_identity"] = identity
        mission.context.artifacts["editor_content_state_id"] = editor.get("content_state_id", "")
        mission.context.artifacts["editor_text"] = {
            "value": actual, "kind": "OBSERVED_VALUE",
            "document_identity": identity,
            "content_state_id": editor.get("content_state_id", ""),
        }
        mission.context.artifacts["editor_content_verified"] = True
        mission.context.artifacts["mission_to_editor_match"] = actual == rendered
        return {"ok": True, "verified": True,
                "verification": "editor_content_exact_match",
                "editor_content_verified": True,
                "mission_to_editor_match": actual == rendered,
                "editor_identity": identity,
                "content_state_id": editor.get("content_state_id", ""),
                "editor_text": actual}

    def _verify_cross_app_file(self, mission, step):
        rendered = str((mission.context.artifacts.get("rendered_text") or {}).get("value") or "")
        path = Path(step.target)
        try:
            exists = path.is_file()
            content = path.read_text(encoding="utf-8") if exists else ""
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__,
                    "file_exists": False, "content_valid": False,
                    "path_error": "PATH_NOT_FOUND" if getattr(exc, "errno", None) == 2 else ""}
        stored, error = mission.context.resolve(
            str(mission.result.get("value_key") or "python_version"),
            mission_id=mission.mission_id, current_step=mission.current_step)
        value_match = bool(stored and stored.value in content)
        content_valid = bool(exists and content == rendered)
        cross_match = bool(content_valid and value_match and rendered)
        if exists and cross_match:
            mission.context.artifacts.setdefault("created_paths", []).append(str(path))
        return {"ok": cross_match and not error, "verified": cross_match and not error,
                "verification": "filesystem_and_context_match",
                "file_exists": exists, "content_valid": content_valid,
                "cross_app_data_match": cross_match, "path": str(path),
                "context_error": error}

    def _handle_overwrite_confirmation(self, mission, step, task_id,
                                        preconfirmed=None):
        target = str(mission.result.get("target_path") or "")
        if preconfirmed and preconfirmed[0] is step:
            result = preconfirmed[1]
            if not result.get("ok"):
                return result
        else:
            dialog = self.service.execute_tool(
                "ui_classify_dialog", {},
                command=f"computer_mission:{mission.mission_id}:overwrite_guard",
                task_id=task_id)
            dialog_type = str(dialog.get("dialog_type") or "UNKNOWN")
            if dialog_type == "UNSAVED_DOCUMENT_DIALOG":
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": dialog_type, "dialog_ownership": "unknown"}
            if dialog_type == "NONE":
                return {"ok": True, "verified": True,
                        "verification": "overwrite_confirmation_not_required"}
            if dialog_type != "FILE_OVERWRITE_DIALOG":
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": dialog_type}
            authorized = {str(Path(item).resolve()) for item in
                          mission.result.get("authorized_overwrite_paths", [])}
            if not target or str(Path(target).resolve()) not in authorized:
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": "overwrite_target_not_authorized"}
            visible = " ".join(str(item.get("text") or "")
                               for item in dialog.get("visible_controls", []))
            if Path(target).name.casefold() not in visible.casefold():
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": "overwrite_target_mismatch",
                        "target": target}
            affirmative_order = ("substituir", "replace", "sim", "yes",
                                 "confirmar", "confirm")
            buttons = {str(item.get("text") or "").casefold(): str(item.get("text") or "")
                       for item in dialog.get("visible_controls", [])
                       if str(item.get("control_type") or "").casefold() == "button"}
            button = next((buttons[label] for label in affirmative_order if label in buttons), "")
            if not button:
                return {"ok": False, "error": "OVERWRITE_CONFIRMATION_BUTTON_NOT_FOUND"}
            confirmed = self.service.execute_tool(
                "ui_invoke_element", {"target": button, "control_type": "Button", "window": ""},
                command=f"computer_mission:{mission.mission_id}:overwrite_confirm",
                task_id=task_id)
            if confirmed.get("confirmation_required"):
                return confirmed
            if not confirmed.get("ok"):
                return confirmed
        time.sleep(0.1)
        dialog = self.service.execute_tool(
            "ui_classify_dialog", {},
            command=f"computer_mission:{mission.mission_id}:overwrite_verify",
            task_id=task_id)
        if dialog.get("dialog_type") != "NONE":
            return {"ok": False, "error": "OVERWRITE_CONFIRMATION_NOT_DISMISSED"}
        mission.context.artifacts["overwrite_confirmed"] = True
        return {"ok": True, "verified": True,
                "verification": "authorized_overwrite_confirmed",
                "overwrite_confirmed": True}

    def _focus_browser(self):
        health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:focus_browser",
            task_id="computer-mission")
        if not health.get("ok") or not health.get("started"):
            return {"ok": False, "error": "BROWSER_SESSION_NOT_STARTED"}
        if str(health.get("browser_provider") or health.get("provider") or "").casefold() != "chrome":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED"}
        session_pid = int(health.get("process_id") or 0)
        if not session_pid:
            return {"ok": False, "error": "CHROME_SESSION_PROCESS_UNAVAILABLE"}
        result = self.service.execute_tool(
            "ui_focus_window", {"window": "chrome", "process_id": session_pid},
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
        if int(data.get("pid") or 0) != session_pid:
            return {"ok": False, "error": "CHROME_WINDOW_PROCESS_MISMATCH",
                    "window": data, "session_process_id": session_pid}
        return {"ok": True, "focused": True, "browser_process": "chrome.exe",
                "window": data, "session_process_id": session_pid,
                "verification": "chrome_window_focus_guard"}

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
                    re.fullmatch(r"(?:https?://|www\.)\S+", title, re.I) or
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
                "ui_dismiss_path_not_found", {"window": "notepad"},
                command=f"computer_mission:{mission.mission_id}",
                task_id=mission.mission_id)
            self._audit_step(mission, step, dismissed, "path_not_found_dialog_dismissed")
            if not dismissed.get("ok"):
                return False
            if step.action_type in {"type_mission_template", "verify_editor_pre_save"}:
                # The dialog may be a stale child of the target app.  Retry
                # the current perception step after the exact dialog is gone;
                # do not jump into Save As or rewrite a file path blindly.
                mission.result["path_reresolved"] = {"dialog": "dismissed",
                                                       "step": step.step_id}
                if step.action_type == "type_mission_template":
                    restart_index = next((index for index, item in enumerate(mission.steps)
                                          if item.step_id == "new-notepad-document"),
                                         mission.current_step)
                    for item in mission.steps[restart_index:]:
                        item.status = MissionStepStatus.PENDING
                        item.error = ""
                    mission.current_step = restart_index
                return True
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
        verify = next((item for item in mission.steps
                       if item.action_type in {"verify_file", "verify_cross_app_file"}), None)
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
                   "content_valid", "cross_app_data_match", "window", "path", "tool",
                   "text", "value", "source_variable", "source_url", "source_title",
                   "previous_app", "app", "text_input_sent",
                   "editor_content_verified", "mission_to_editor_match",
                   "editor_identity", "content_state_id", "overwrite_confirmed",
                   "document_identity", "mission_document_id", "created_by_mission",
                   "pre_existing_document"}
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
