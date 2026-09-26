import os
import re
import ctypes
import shutil
import subprocess
import time
import inspect
import json
import threading
import uuid
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

from .audit import AuditLog
from .models import AgentState, BROWSER_READ, ResponsePolicy, Risk, Tool
from .registry import ToolRegistry
from .security import READ_ONLY_PUBLIC_BROWSER_OBSERVATION, SecurityManager
from .cancellation import CancellationToken
from .memory import GoldenMemoryManager
from .memory.models import MemoryCategory, MemorySource
from .orchestrator import CentralOrchestrator, JarvisRuntimeCoordinator
from .task_manager import TaskManager


class JarvisService:
    MAX_PLAN_STEPS = 5
    MARKET_PLAN_MAX_STEPS = 10
    MARKET_PLAN_TOOLS = frozenset({
        "mt5_status", "mt5_account_info", "mt5_positions", "mt5_orders",
        "mt5_symbol_tick", "mt5_symbol_info", "mt5_recent_candles",
        "golden_status", "golden_scanner_status", "golden_scanner_results",
        "golden_risk_status", "web_research", "web_research_learn",
    })
    MARKET_OPTIONAL_TOOLS = frozenset({
        "golden_scanner_results", "web_research", "web_research_learn",
    })
    FINAL_TOOLS = {
        "open_program", "close_program", "open_folder", "open_file", "open_path",
        "is_running", "system_status", "get_time", "get_date", "get_ip", "open_url",
        "volume_up", "volume_down", "volume_mute", "volume_set", "lock_windows",
        "minimize_all", "show_desktop", "open_control_center", "copy_file", "move_file",
        "rename_file", "delete_file", "create_folder", "get_username", "get_active_window",
        "get_battery", "get_network", "close_active_window", "maximize_window",
        "minimize_window", "switch_window", "get_exchange_rate",
        "browser_open", "browser_navigate", "browser_get_page_info", "browser_read_page",
        "browser_get_elements", "browser_click", "browser_type", "browser_scroll",
        "browser_back", "browser_forward", "browser_screenshot", "browser_close",
        "browser_health",
    }
    BACKGROUND_TOOLS = {"analyze_screen"}
    # ═══════════════════════════════════════════════════════════════
    # PROGRAMAS CADASTRADOS (nome → executável Windows)
    # ═══════════════════════════════════════════════════════════════
    PROGRAMS = {
        # Produtividade (nomes simples que o Windows encontra no PATH)
        "bloco de notas": "notepad.exe",
        "notepad": "notepad.exe",
        "calculadora": "calc.exe",
        "calculador": "calc.exe",
        "paint": "mspaint.exe",
        "wordpad": "write.exe",
        # Explorador e sistema
        "explorador": "explorer.exe",
        "explorer": "explorer.exe",
        "explorador de arquivos": "explorer.exe",
        "gerenciador de tarefas": "taskmgr.exe",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "painel de controle": "control.exe",
        "painel": "control.exe",
        "control": "control.exe",
        "configuracoes": "ms-settings:",
        "configurações": "ms-settings:",
        "settings": "ms-settings:",
        "propriedades do sistema": "SystemPropertiesAdvanced.exe",
        # Navegadores (caminho completo)
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "microsoft edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "opera": r"C:\Program Files\Opera\launcher.exe",
        # Desenvolvimento
        "vs code": "code.cmd",
        "vscode": "code.cmd",
        "visual studio code": "code.cmd",
        "git bash": r"C:\Program Files\Git\bin\bash.exe",
        "terminal": "WindowsTerminal.exe",
        "windows terminal": "WindowsTerminal.exe",
        # Trading (caminho completo)
        "meta trader": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        "metatrader": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        "mt5": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        "metatrader 5": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        # Utilitários e apps comuns
        "vlc": "vlc.exe",
        "spotify": "Spotify.exe",
        "7zip": "7zFM.exe",
        "7-zip": "7zFM.exe",
        "notepad++": "notepad++.exe",
        "winrar": "WinRAR.exe",
        "obs": "obs64.exe",
        "obs studio": "obs64.exe",
        "discord": "Discord.exe",
        "telegram": "Telegram.exe",
        "zoom": "Zoom.exe",
        "teams": "ms-teams.exe",
        "onedrive": "OneDrive.exe",
    }

    # ═══════════════════════════════════════════════════════════════
    # PASTAS ESPECIAIS DO WINDOWS
    # ═══════════════════════════════════════════════════════════════
    SPECIAL_FOLDERS = {
        "downloads": "Downloads",
        "download": "Downloads",
        "documentos": "Documents",
        "documentos": "Documents",
        "document": "Documents",
        "desktop": "Desktop",
        "area de trabalho": "Desktop",
        "área de trabalho": "Desktop",
        "imagens": "Pictures",
        "images": "Pictures",
        "fotos": "Pictures",
        "pictures": "Pictures",
        "videos": "Videos",
        "vídeos": "Videos",
        "musicas": "Music",
        "músicas": "Music",
        "music": "Music",
        "appdata": "AppData",
        "programs": "AppData/Local/Programs",
        "programas": "AppData/Local/Programs",
        "golden": r"C:\GoldenAI",
        "goldenai": r"C:\GoldenAI",
        "golden ai": r"C:\GoldenAI",
    }

    def __init__(self, base_dir):
        self.started_at = time.time()
        self.state = AgentState.IDLE
        self.dry_run = os.getenv("GOLDEN_JARVIS_DRY_RUN", "0") == "1"
        self.registry = ToolRegistry()
        self.cancellation = CancellationToken()
        self.security = SecurityManager({
            "shutdown": "confirm",
            "restart": "confirm",
            "lock_windows": "confirm",
            "kill_process": "confirm",
        })
        self.audit = AuditLog(Path(base_dir) / "golden_runtime.db")
        self.legacy_memory = GoldenMemoryManager(base_dir)
        self.memory = self.legacy_memory  # compatibilidade da API existente
        self.legacy_memory.start_session({"component": "jarvis_service"})
        # M1.0: engine V2 sobre o mesmo DB (migrations aditivas; legado intacto).
        # M1.1: projeção Markdown/Obsidian pós-commit (degradada; SQLite canônico).
        try:
            from .memory.v2 import (GoldenMemoryEngine, LearningEngine,
                                    ResearchEngine,
                                    build_research_provider_from_env)
            from .memory.v2.vault import default_vault_root
            self.memory_v2 = GoldenMemoryEngine(
                self.legacy_memory.db.path,
                vault_root=default_vault_root(),
                embed=self.legacy_memory.embedding.embed_sync,
                embedding_model=self.legacy_memory.embedding.MODEL_PRIMARY)
            self.research_provider = build_research_provider_from_env()
            self.learning_engine = LearningEngine(
                self.memory_v2, ResearchEngine(self.research_provider))
            from .memory.v2.project_memory import ProjectMemoryManager
            self.project_memory = ProjectMemoryManager(self.memory_v2)
        except Exception:
            self.memory_v2 = None
            self.research_provider = None
            self.learning_engine = None
            self.project_memory = None
        self._register_tools()
        self.task_manager = TaskManager(base_dir)
        from .computer_use_mission import ComputerMissionExecutor
        self.computer_missions = ComputerMissionExecutor(self)
        self.task_manager.start_scheduler(self._launch_background_task,
                                          idle_provider=self._background_idle_seconds)
        self.orchestrator = CentralOrchestrator(self.registry, audit=self.audit)
        self.runtime = JarvisRuntimeCoordinator(self.orchestrator, self,
                                                task_manager=self.task_manager)
        self._closed = False
        self._conversation_lock = threading.RLock()
        self._ai_status_lock = threading.RLock()
        self._last_request_telemetry = {}
        self._conversation_histories = {}

    def ai_core_status(self):
        """Return the canonical, secret-free status consumed by the UI."""
        from .orchestrator.models import ModelProfile
        from .orchestrator.policies import DEFAULT_MODELS, PROVIDER_ORDER, PROVIDER_MODELS

        def state_name(value):
            return str(getattr(value, "value", value or "OFFLINE")).upper()

        def display_state(value, configured=True):
            state = state_name(value)
            if not configured:
                return "NOT_CONFIGURED"
            return {
                "AVAILABLE": "ONLINE", "RATE_LIMITED": "COOLDOWN",
                "AUTH_ERROR": "AUTH_ERROR", "TIMEOUT": "TIMEOUT",
                "DEGRADED": "DEGRADED", "OFFLINE": "OFFLINE",
            }.get(state, state)

        models = self.orchestrator.models
        registered = dict(getattr(models, "providers", {}) or {})
        health = dict(getattr(models, "last_health", {}) or {})
        model_status = models.status() if hasattr(models, "status") else {}
        providers = []
        for name in PROVIDER_ORDER:
            adapter = registered.get(name)
            configured = adapter is not None
            item = dict(model_status.get(name, {}))
            item.update({"name": name, "configured": configured,
                         "registered": configured,
                         "status": display_state(health.get(name, getattr(adapter, "state", None)), configured)})
            if not item.get("model"):
                item["model"] = ""
            providers.append(item)

        preferred_provider, preferred_model = DEFAULT_MODELS[ModelProfile.GENERAL]
        active = next((item for item in providers if item["status"] == "ONLINE"), None)
        research_status = {"provider": "", "status": "NOT_CONFIGURED", "configured": False,
                           "last_success": 0.0, "last_error": "", "latency_ms": None,
                           "cooldown_active": False, "sources": 0, "providers": {}}
        research = self.research_provider
        if research is not None:
            configured = True
            raw = research.status() if hasattr(research, "status") else {}
            selected = raw.get("selected", "")
            child = (raw.get("providers", {}).get(selected, {})
                     if selected else {})
            status = str(child.get("status") or raw.get("final_status") or "NOT_CHECKED").upper()
            if status in {"AVAILABLE", "ONLINE"}:
                status = "ONLINE"
            elif status in {"RATE_LIMIT", "RATE_LIMITED"}:
                status = "COOLDOWN"
            elif status == "CONFIGURED":
                status = "NOT_CHECKED"
            research_status.update({"provider": selected, "status": status,
                                    "configured": configured,
                                    "last_success": child.get("last_success", 0.0),
                                    "last_error": child.get("last_error", ""),
                                    "cooldown_active": bool(child.get("cooldown_active")),
                                    "fallback_count": int(raw.get("fallback_count") or 0)})
            for name, item in (raw.get("providers") or {}).items():
                child_state = str(item.get("status") or "NOT_CHECKED").upper()
                if child_state in {"AVAILABLE", "ONLINE"}:
                    child_state = "ONLINE"
                elif child_state in {"RATE_LIMIT", "RATE_LIMITED"}:
                    child_state = "COOLDOWN"
                research_status["providers"][name] = {
                    "status": child_state,
                    "configured": bool(item.get("configured")),
                    "last_success": item.get("last_success", 0.0),
                    "last_error": item.get("last_error", ""),
                    "cooldown_active": bool(item.get("cooldown_active")),
                }
        with self._ai_status_lock:
            last_request = dict(self._last_request_telemetry)

        states = [item["status"] for item in providers]
        online = sum(state == "ONLINE" for state in states)
        configured_states = [state for state in states if state != "NOT_CONFIGURED"]
        if research_status["status"] == "COOLDOWN":
            overall = "DEGRADED" if online else "COOLDOWN"
        elif online == 0:
            overall = "NOT_CONFIGURED" if not configured_states else "OFFLINE"
        elif any(state not in {"ONLINE", "NOT_CONFIGURED"} for state in states):
            overall = "DEGRADED"
        else:
            overall = "ONLINE"
        return {
            "overall_status": overall,
            "llm": {"active_provider": active["name"] if active else "",
                    "active_model": (active.get("model") or
                                     PROVIDER_MODELS.get(active["name"], {}).get(ModelProfile.GENERAL, "")) if active else "",
                    "preferred_provider": str(preferred_provider),
                    "preferred_model": preferred_model},
            "local_ai": next((item for item in providers if item["name"] == "ollama"),
                              {"name": "ollama", "status": "NOT_CONFIGURED"}),
            "research": research_status,
            "providers": providers,
            "last_request": last_request or None,
        }

    def close(self):
        """Release background resources owned by this JarvisService instance."""
        if self._closed:
            return
        self._closed = True
        try:
            self.task_manager.shutdown(wait=False)
        except Exception:
            pass
        try:
            from .brain import _brain
            if _brain is not None and getattr(_brain, "registry", None) is self.registry:
                _brain.close()
        except Exception:
            pass
        try:
            from .browser import _browser_thread
            if _browser_thread is not None:
                _browser_thread.stop()
        except Exception:
            pass

    def _launch_background_task(self, task, run):
        """Route scheduled missions through the canonical mission/security path."""
        if run.get("mission_id"):
            checkpoint, error = self.computer_missions.persistence.latest(
                str(run["mission_id"]))
            if error or not checkpoint:
                return {"ok": False, "error": error or "MISSION_CHECKPOINT_NOT_FOUND",
                        "mission_id": run["mission_id"]}
            return self.resume_current_mission(
                run["mission_id"], checkpoint["resume_token"], task_id=task.task_id)
        return self.run_computer_mission(task.user_request, task_id=task.task_id)

    def _background_idle_seconds(self):
        """Read Windows idle age without touching foreground state."""
        from .tools.ui_automation import ui_user_activity
        result = ui_user_activity(1500)
        age_ms = result.get("last_user_input_age_ms")
        return max(0.0, float(age_ms or 0) / 1000.0)

    # ═══════════════════════════════════════════════════════════════
    # REGISTRO DE FERRAMENTAS
    # ═══════════════════════════════════════════════════════════════
    def _register_tools(self):
        from .tools.computer_use_tools import COMPUTER_USE_TOOLS
        from .tools.ui_automation import UI_AUTOMATION_TOOLS
        from .tools.market_readonly import (
            golden_risk_status, golden_scanner_results, golden_scanner_status,
            golden_status, mt5_account_info, mt5_orders, mt5_positions,
            mt5_recent_candles, mt5_status, mt5_symbol_info, mt5_symbol_tick,
        )

        for tool in (
            # --- PROGRAMAS ---
            Tool("open_program", "Abre um programa autorizado", self._open_program,
                 parameters={"name": str}),
            Tool("close_program", "Fecha um programa autorizado", self._close_program,
                 Risk.MEDIUM, parameters={"name": str}),
            Tool("open_any_exe", "Abre qualquer executável por caminho completo",
                 self._open_any_exe, Risk.HIGH, parameters={"path": str},
                 llm_enabled=False, dynamic_risk=True),

            # --- PASTAS E ARQUIVOS ---
            Tool("open_folder", "Abre uma pasta (pasta especial ou caminho)", self._open_folder,
                 parameters={"name": str}),
            Tool("open_file", "Abre um arquivo existente", self._open_file,
                 parameters={"path": str}),
            Tool("open_path", "Abre qualquer caminho (pasta ou arquivo)", self._open_path,
                 parameters={"path": str}),
            Tool("search_files", "Busca arquivos no PC por nome", self._search_files,
                 Risk.MEDIUM, parameters={"query": str, "folder": str}),

            # --- PROCESSOS ---
            Tool("list_processes", "Lista processos em execução", self._list_processes),
            Tool("kill_process", "Encerra um processo por nome", self._kill_process,
                 Risk.HIGH, confirmation=True, parameters={"name": str}),
            Tool("is_running", "Verifica se um programa está aberto", self._is_running,
                 parameters={"name": str}),

            # --- SISTEMA ---
            Tool("system_status", "Consulta CPU, memória e disco", self._system_status),
            Tool("get_time", "Mostra a hora atual", self._get_time),
            Tool("get_date", "Mostra a data atual", self._get_date),
            Tool("get_ip", "Mostra endereço IP", self._get_ip),
            Tool("open_url", "Abre um site no navegador padrão", self._open_url,
                 parameters={"url": str}),
            Tool("take_screenshot", "Captura a tela inteira", self._take_screenshot),
            Tool("take_screenshot_window", "Captura janela específica", self._take_screenshot_window,
                 parameters={"window": str}),
            Tool("analyze_screen", "Analisa a tela com IA visual (veja minha tela)", self._analyze_screen,
                 parameters={"question": str}, timeout=90),

            # --- VOLUME ---
            Tool("volume_up", "Aumenta o volume", self._volume_up),
            Tool("volume_down", "Diminui o volume", self._volume_down),
            Tool("volume_mute", "Silencia o áudio", self._volume_mute),
            Tool("volume_set", "Define o volume (0-100)", self._volume_set,
                 parameters={"level": int}),

            # --- WINDOWS ---
            Tool("lock_windows", "Bloqueia a sessão do Windows", self._lock,
                 Risk.MEDIUM, confirmation=True),
            Tool("shutdown", "Desliga o computador", self._shutdown,
                 Risk.CRITICAL, confirmation=True),
            Tool("restart", "Reinicia o computador", self._restart,
                 Risk.CRITICAL, confirmation=True),
            Tool("minimize_all", "Minimiza todas as janelas", self._minimize_all),
            Tool("show_desktop", "Mostra a área de trabalho", self._show_desktop),
            Tool("open_control_center", "Abre o Centro de Ações do Windows", self._open_action_center),

            # --- ARQUIVOS ---
            Tool("copy_file", "Copia um arquivo para outro destino", self._copy_file,
                 Risk.MEDIUM, parameters={"source": str, "dest": str}),
            Tool("move_file", "Move um arquivo para outro destino", self._move_file,
                 Risk.MEDIUM, parameters={"source": str, "dest": str}),
            Tool("rename_file", "Renomeia um arquivo", self._rename_file,
                 Risk.MEDIUM, parameters={"source": str, "new_name": str}),
            Tool("delete_file", "Exclui um arquivo", self._delete_file,
                 Risk.HIGH, confirmation=True, parameters={"path": str}),
            Tool("create_folder", "Cria uma pasta", self._create_folder,
                 parameters={"path": str}),
            Tool("list_folder", "Lista arquivos de uma pasta", self._list_folder,
                 parameters={"path": str}),

            # --- LIXEIRA ---
            Tool("recycle_bin_status", "Consulta status da lixeira (itens, tamanho)",
                 self._recycle_bin_status),
            Tool("empty_recycle_bin", "Esvazia a lixeira do Windows (IRREVERSÍVEL)",
                 self._empty_recycle_bin,
                 Risk.CRITICAL, confirmation=True),

            # --- INFO DO SISTEMA ---
            Tool("get_username", "Mostra o usuário do Windows", self._get_username),
            Tool("get_active_window", "Mostra a janela ativa atual", self._get_active_window),
            Tool("get_battery", "Mostra status da bateria", self._get_battery),
            Tool("get_network", "Mostra informações de rede", self._get_network),
            Tool("get_recent_files", "Mostra arquivos recentes", self._get_recent_files),

            # --- CONTROLE DE JANELAS ---
            Tool("close_active_window", "Fecha a janela ativa", self._close_active_window,
                 Risk.MEDIUM),
            Tool("maximize_window", "Maximiza a janela ativa", self._maximize_window),
            Tool("minimize_window", "Minimiza a janela ativa", self._minimize_window),
            Tool("switch_window", "Alterna para próxima janela (Alt+Tab)", self._switch_window),
            Tool("memory_search", "Busca memórias relevantes do usuário", self._memory_search,
                 parameters={"query": str, "namespace": str}),
            Tool("memory_remember", "Guarda informação explicitamente solicitada pelo usuário",
                 self._memory_remember, Risk.MEDIUM,
                 parameters={"content": str, "namespace": str}),
            Tool("memory_recent", "Lista memórias recentes", self._memory_recent,
                 parameters={"limit": int, "namespace": str}),
            Tool("get_exchange_rate", "Consulta cotação atual de par de moedas (ex.: USD/BRL). "
                 "NUNCA invente valor: sempre chame esta ferramenta para cotações.",
                 self._get_exchange_rate, Risk.LOW,
                 parameters={"base": str, "quote": str},
                 parameter_descriptions={"base": "Moeda base (ex.: USD)",
                                         "quote": "Moeda de cotação (ex.: BRL)"},
                 category="data"),
            # --- MARKET INTELLIGENCE (SOMENTE LEITURA) ---
            Tool("mt5_status", "Consulta o estado da conexão MT5 sem executar operações.",
                 mt5_status, Risk.LOW, timeout=20, category="market"),
            Tool("mt5_account_info", "Consulta saldo e estado da conta MT5 sem executar operações.",
                 mt5_account_info, Risk.LOW, timeout=20, category="market"),
            Tool("mt5_positions", "Lista posições abertas do MT5 sem alterar ordens.",
                 mt5_positions, Risk.LOW, timeout=20, category="market"),
            Tool("mt5_orders", "Lista ordens pendentes do MT5 sem alterá-las.",
                 mt5_orders, Risk.LOW, timeout=20, category="market"),
            Tool("mt5_symbol_tick", "Consulta bid/ask/last de um símbolo no MT5.",
                 mt5_symbol_tick, Risk.LOW, timeout=20,
                 parameters={"symbol": str},
                 parameter_descriptions={"symbol": "Símbolo exato do broker, como XAUUSD ou EURUSD."},
                 category="market"),
            Tool("mt5_symbol_info", "Consulta metadados de um símbolo no MT5.",
                 mt5_symbol_info, Risk.LOW, timeout=20,
                 parameters={"symbol": str},
                 parameter_descriptions={"symbol": "Símbolo exato do broker, como XAUUSD ou EURUSD."},
                 category="market"),
            Tool("mt5_recent_candles", "Consulta candles recentes do MT5 sem executar operações.",
                 mt5_recent_candles, Risk.LOW, timeout=25,
                 parameters={"symbol": str, "timeframe": str, "count": int},
                 parameter_descriptions={
                     "symbol": "Símbolo exato do broker.",
                     "timeframe": "M1, M5, M15, H1, H4 ou D1.",
                     "count": "Quantidade de candles, limitada pelo adapter.",
                 }, category="market"),
            Tool("golden_status", "Consulta a disponibilidade dos módulos Golden.",
                 golden_status, Risk.LOW, timeout=20, category="market"),
            Tool("golden_scanner_status", "Consulta o estado do scanner Golden sem iniciar scan.",
                 golden_scanner_status, Risk.LOW, timeout=20, category="market"),
            Tool("golden_scanner_results", "Consulta setups do scanner Golden em modo leitura.",
                 golden_scanner_results, Risk.LOW, timeout=35,
                 parameters={"symbol": str, "limit": int},
                 parameter_descriptions={
                     "symbol": "Símbolo a consultar; vazio apenas inspeciona cache.",
                     "limit": "Máximo de setups retornados.",
                 }, category="market"),
            Tool("golden_risk_status", "Consulta o estado de risco Golden sem enviar ordens.",
                 golden_risk_status, Risk.LOW, timeout=25, category="market"),
            Tool("web_research", "Pesquisa real na web e retorna fontes sem memorizar.",
                 self._web_research, Risk.LOW, timeout=45,
                 parameters={"query": str, "limit": int, "privacy": str},
                 parameter_descriptions={
                     "query": "Consulta de pesquisa sem segredos.",
                     "limit": "Máximo de resultados, de 1 a 10.",
                     "privacy": "PUBLIC, INTERNAL, SENSITIVE ou SECRET."},
                 category="research"),
            Tool("web_research_learn", "Pesquisa real na web e promove candidatos confiáveis para Memory V2.",
                 self._web_research_learn, Risk.MEDIUM, timeout=60,
                 parameters={"query": str, "limit": int, "privacy": str},
                 parameter_descriptions={
                     "query": "Consulta de pesquisa sem segredos.",
                     "limit": "Máximo de resultados, de 1 a 10.",
                     "privacy": "PUBLIC, INTERNAL, SENSITIVE ou SECRET."},
                 category="research"),
            # --- COMPUTER USE ---
            *COMPUTER_USE_TOOLS,
            *UI_AUTOMATION_TOOLS,

            # --- BROWSER (Playwright V1) ---
            Tool("browser_open", "Inicia o navegador Playwright controlado", self._browser_open,
                 Risk.LOW, timeout=15,
                 parameters={"visible": bool, "provider": str}, category="browser"),
            Tool("browser_navigate", "Navega para uma URL no navegador", self._browser_navigate,
                 Risk.MEDIUM, timeout=30, parameters={"url": str}, category="browser"),
            Tool("browser_get_page_info", "Extrai informações estruturadas da página (DOM/ARIA)",
                 self._browser_get_page_info, Risk.LOW, timeout=15, category="browser",
                 action_class=BROWSER_READ,
                 authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION),
            Tool("browser_read_page", "Lê o conteúdo de texto da página (marcado como untrusted)",
                 self._browser_read_page, Risk.LOW, timeout=15, category="browser",
                 action_class=BROWSER_READ,
                 authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION),
            Tool("browser_get_elements", "Lista elementos interativos com refs (e1, e2, ...)",
                 self._browser_get_elements, Risk.LOW, timeout=15, category="browser",
                 action_class=BROWSER_READ,
                 authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION),
            Tool("browser_click", "Clica em elemento por ref, seletor ou texto",
                 self._browser_click, Risk.MEDIUM, timeout=15,
                 parameters={"ref": str, "selector": str, "text": str}, category="browser"),
            Tool("browser_type", "Digita texto em campo por ref ou seletor",
                 self._browser_type, Risk.LOW, timeout=15,
                 parameters={"ref": str, "selector": str, "text": str, "clear": bool},
                 category="browser"),
            Tool("browser_search", "Pesquisa texto em campo identificado e aguarda navegação.",
                 self._browser_search, Risk.LOW, timeout=30,
                 parameters={"query": str, "ref": str}, category="browser"),
            Tool("browser_wait_for_navigation", "Aguarda mudança observável de navegação.",
                 self._browser_wait_for_navigation, Risk.LOW, timeout=20,
                 parameters={"timeout_ms": int}, category="browser"),
            Tool("browser_wait_for_results", "Aguarda resultados visíveis e estruturados da página.",
                 self._browser_wait_for_results, Risk.LOW, timeout=25,
                 parameters={"timeout_ms": int}, category="browser",
                 llm_enabled=False, action_class=BROWSER_READ,
                 authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION),
            Tool("browser_scroll", "Rola a página (down/up/top/bottom)",
                 self._browser_scroll, Risk.LOW, timeout=10,
                 parameters={"direction": str, "amount": int}, category="browser"),
            Tool("browser_back", "Navega para a página anterior", self._browser_back,
                 Risk.LOW, timeout=15, category="browser"),
            Tool("browser_forward", "Navega para a próxima página", self._browser_forward,
                 Risk.LOW, timeout=15, category="browser"),
            Tool("browser_screenshot", "Captura screenshot da página atual",
                 self._browser_screenshot, Risk.LOW, timeout=15,
                 parameters={"full_page": bool}, category="browser"),
            Tool("browser_close", "Fecha o navegador e limpa recursos", self._browser_close,
                 Risk.LOW, timeout=10, category="browser"),
            Tool("browser_health", "Verifica status do navegador", self._browser_health,
                 Risk.LOW, timeout=5, category="browser", action_class=BROWSER_READ,
                 authorization_scope=READ_ONLY_PUBLIC_BROWSER_OBSERVATION),
            Tool("browser_record_window", "Registra a identidade UIA da janela Chrome",
                 self._browser_record_window, Risk.LOW, timeout=5,
                 parameters={"pid": int, "window_id": int}, category="browser",
                 llm_enabled=False),
        ):
            if tool.name in self.FINAL_TOOLS:
                tool = replace(tool, response_policy=ResponsePolicy.FINAL)
            elif tool.name in self.BACKGROUND_TOOLS:
                tool = replace(tool, response_policy=ResponsePolicy.BACKGROUND,
                               expected_latency_ms=5000)
            self.registry.register(tool)

    # ═══════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════
    def status(self):
        self.security.prune()
        return {
            "ok": True, "online": True, "state": self.state.value,
            "dry_run": self.dry_run,
            "uptime_seconds": int(time.time() - self.started_at),
            "pending": len(self.security.pending),
            "programs": sorted(set(self.PROGRAMS)),
            "tools": self.registry.public_catalog(),
            "history": self.audit.recent(20),
            "memory": self._memory_status(),
            "orchestrator": self.orchestrator.status(),
            "tasks": {"active_task_id": self.runtime.active_task_id,
                      "recent": len(self.task_manager.list(limit=20))},
        }

    @staticmethod
    def _memory_record_dict(record):
        return {"id": record.id, "type": record.memory_type.value,
                "category": record.category.value, "content": record.content,
                "importance": record.importance, "confidence": record.confidence,
                "source": record.source.value, "source_id": record.source_id,
                "session_id": record.session_id, "namespace": record.namespace,
                "created_at": record.created_at, "updated_at": record.updated_at,
                "last_accessed_at": record.last_accessed_at,
                "access_count": record.access_count, "active": record.active,
                "metadata": record.metadata}

    def _memory_status(self):
        from dataclasses import asdict
        payload = {"ok": True, **asdict(self.memory.status())}
        try:
            payload["engine_v2"] = self.memory_v2.status() if self.memory_v2 else {
                "engine": "V2 DEGRADED", "error": "não inicializado"}
            if self.memory_v2:
                try:
                    counts = self.memory_v2.graph_stats()
                    payload["engine_v2"]["graph"] = {
                        "entities": counts.get("entities_total", 0),
                        "relations": counts.get("relations_total", 0),
                        "integrity": ("OK" if self.memory_v2.store.validate_graph().get(
                            "ok") else "DEGRADED")}
                except Exception:
                    pass
        except Exception as exc:
            payload["engine_v2"] = {"engine": "V2 DEGRADED", "error": str(exc)[:120]}
        return payload

    def _memory_search(self, query, namespace="jarvis"):
        items = self.memory.search(query, top_k=8, namespace=namespace)
        return {"ok": True, "items": [self._memory_record_dict(item) for item in items],
                "count": len(items), "fallback": self.memory.embedding.status().get("fallback")}

    def _memory_remember(self, content, namespace="jarvis"):
        if self.memory._unsafe_content_reason(content):
            return {"ok": False, "error": "Conteúdo sensível, binário ou excessivo não foi armazenado."}
        rid = self.memory.remember(content, source=MemorySource.USER,
                                   category=MemoryCategory.GENERAL,
                                   importance=75, confidence=0.95, namespace=namespace)
        return {"ok": bool(rid), "id": rid,
                "message": "Memória registrada." if rid else "Memória não registrada."}

    def _memory_recent(self, limit=10, namespace="jarvis"):
        limit = max(1, min(int(limit), 50))
        items = self.memory.get_recent(limit=limit, namespace=namespace)
        return {"ok": True, "items": [self._memory_record_dict(item) for item in items],
                "count": len(items)}

    def _web_research(self, query, limit=5, privacy="PUBLIC"):
        return self._run_web_research(query, limit, privacy, learn=False)

    def _web_research_learn(self, query, limit=5, privacy="PUBLIC"):
        return self._run_web_research(query, limit, privacy, learn=True)

    def _run_web_research(self, query, limit=5, privacy="PUBLIC", learn=False):
        from .orchestrator.models import DataClassification
        from .memory.v2 import MemorySecurityError, sanitize_research_query
        try:
            level = DataClassification(str(privacy or "PUBLIC").upper())
        except Exception:
            level = DataClassification.PUBLIC
        if level == DataClassification.SECRET:
            return {"ok": False, "error": "Pesquisa web bloqueada para SECRET.",
                    "telemetry": {"failed": 1}}
        if self.learning_engine is None or self.research_provider is None:
            return {"ok": False, "error": "Provider de pesquisa real indisponível. Configure BRAVE_SEARCH_API_KEY.",
                    "telemetry": {"provider": "", "failed": 1}}
        sanitized = sanitize_research_query(query)
        if not sanitized:
            return {"ok": False, "error": "Consulta vazia após sanitização de egress.",
                    "telemetry": {"failed": 1}}
        try:
            limit = max(1, min(int(limit), 10))
            if learn:
                report = self.learning_engine.research_and_learn(
                    sanitized, limit=limit, privacy=level, project="jarvis")
            else:
                report = self.learning_engine.research_candidates(
                    sanitized, limit=limit, privacy=level, project="jarvis")
        except MemorySecurityError as exc:
            return {"ok": False, "error": str(exc), "telemetry": {"failed": 1}}
        telemetry = {
            "provider": report.provider, "provider_selected": report.provider_selected,
            "fallback_used": report.fallback_used,
            "failure_reason": report.failure_reason,
            "provider_failures": report.provider_failures,
            "search_ms": report.search_ms,
            "fetch_ms": report.fetch_ms, "results_count": report.results_count,
            "pages_fetched": report.pages_fetched,
            "candidates_created": report.candidates_created,
            "promoted": report.promoted, "disputed": report.disputed,
            "failed": report.failed,
            "official_source_count": sum(
                1 for candidate in report.candidates if candidate.trust.value == "A"),
            "community_source_count": sum(
                1 for candidate in report.candidates if candidate.trust.value in ("D", "E")),
            "source_conflict": bool(report.disputed),
        }
        provider_status = (self.research_provider.status()
                           if hasattr(self.research_provider, "status") else {})
        telemetry.update({
            "provider_status": provider_status.get("providers", {}),
            "fallback_count": provider_status.get("fallback_count", 0),
            "cooldown_active": any(
                item.get("cooldown_active", False)
                for item in provider_status.get("providers", {}).values()),
            "final_status": report.final_status,
        })
        print("[JARVIS-SEARCH] SEARCH_REQUEST=YES SEARCH_PROVIDER=%s "
              "RAW_RESPONSE_TYPE=research_report PARSE_RESULT=%s "
              "VALIDATION_ERROR=%s FALLBACK_ATTEMPTED=%s FINAL_ERROR=%s" % (
                  report.provider_selected or report.provider or "unavailable",
                  "ok" if report.results_count else "empty",
                  report.failure_reason or "none",
                  bool(report.fallback_used or report.provider_failures),
                  bool(report.errors and not report.pages_fetched)), flush=True)
        if report.errors and not report.evidences:
            reason = report.failure_reason or "provider_down"
            friendly = {
                "missing_key": "A pesquisa externa não está configurada neste ambiente.",
                "rate_limit": "O provedor de pesquisa atingiu o limite temporário.",
                "timeout": "A pesquisa externa excedeu o tempo limite.",
                "auth_error": "A autenticação do provedor de pesquisa falhou.",
                "oversized_page": "As fontes encontradas excederam o limite seguro de conteúdo.",
            }.get(reason, "Não consegui consultar fontes externas agora.")
            return {"ok": False,
                    "error": friendly + " Posso usar apenas os dados locais disponíveis.",
                    "telemetry": telemetry}
        temporal_query = bool(re.search(
            r"\b(atual|atualmente|current|latest|stable|estável|vers[aã]o)\b",
            report.query, re.I))
        trust_rank = {"A": 4, "B": 3, "C": 2, "D": 1, "E": 0}
        candidates = sorted(
            report.candidates,
            key=lambda candidate: (
                trust_rank.get(candidate.trust.value, 0),
                max((e.timestamp for e in candidate.evidences), default=0)
                if temporal_query else 0,
                candidate.confidence),
            reverse=True)
        lines = []
        for candidate in candidates[:6]:
            source = candidate.evidences[0] if candidate.evidences else None
            label = "oficial" if candidate.trust.value == "A" else (
                "benchmark/técnica" if candidate.trust.value == "B" else
                "comunidade/hipótese" if candidate.trust.value in ("D", "E")
                else "fontes independentes")
            url = source.url if source else ""
            lines.append("- %s [%s, trust %s]%s" % (
                candidate.claim[:800], label, candidate.trust.value,
                (" — " + url) if url else ""))
        action = "Pesquisei e aprendi" if learn and report.promoted else (
            "Pesquisei, mas não promovi memória" if learn else "Pesquisei")
        message = ("%s. Fontes lidas: %d. Candidatos: %d. Promovidos: %d."
                   % (action, report.pages_fetched, report.candidates_created,
                      report.promoted))
        if lines:
            message += "\n" + "\n".join(lines)
        if report.errors:
            message += "\nAvisos: " + "; ".join(report.errors[:3])
        # A page may yield many chunks. Keep the strongest, freshest claims
        # per URL so secondary pages cannot outvote a recent official source.
        grouped = {}
        for candidate in candidates:
            for evidence in candidate.evidences:
                key = evidence.to_metadata().get("url") or evidence.url
                grouped.setdefault(key, []).append((candidate, evidence))
        evidence_records = []
        for url, items in grouped.items():
            items.sort(key=lambda pair: (
                trust_rank.get(pair[1].trust.value, 0),
                pair[1].timestamp if temporal_query else 0,
                pair[1].confidence), reverse=True)
            for candidate, evidence in items[:2]:
                evidence_records.append({
                    "claim": candidate.claim[:800],
                    "quote": evidence.quote[:800],
                    "source": evidence.to_metadata(),
                })
        evidence_records.sort(key=lambda item: (
            trust_rank.get(item["source"].get("trust", "E"), 0),
            item["source"].get("timestamp", 0) if temporal_query else 0,
            item["source"].get("confidence", 0)), reverse=True)
        evidence_records = evidence_records[:24]
        return {"ok": True, "message": message, "query": report.query,
                "learn": bool(learn), "telemetry": telemetry,
                "sources": [e.to_metadata() for e in report.evidences[:12]],
                "evidence_records": evidence_records}

    # ═══════════════════════════════════════════════════════════════
    # DADOS ONLINE (Fase 8.1) — cotações
    # ═══════════════════════════════════════════════════════════════

    # Aliases naturais PT-BR → símbolos de moeda.
    CURRENCY_ALIASES = {
        "dolar": "USD", "dólar": "USD", "dolares": "USD", "dólares": "USD",
        "usd": "USD", "dollar": "USD",
        "real": "BRL", "reais": "BRL", "brl": "BRL", "r$": "BRL",
        "euro": "EUR", "eur": "EUR", "euros": "EUR",
        "libra": "GBP", "libras": "GBP", "gbp": "GBP", "libra esterlina": "GBP",
        "iene": "JPY", "ienes": "JPY", "jpy": "JPY", "yen": "JPY",
        "franco suico": "CHF", "chf": "CHF",
        "dolar canadense": "CAD", "cad": "CAD",
        "dolar australiano": "AUD", "aud": "AUD",
        "yuan": "CNY", "cny": "CNY",
        "peso argentino": "ARS", "ars": "ARS",
        "bitcoin": "BTC", "btc": "BTC",
        "ethereum": "ETH", "eth": "ETH",
        "ouro": "XAU", "gold": "XAU", "xau": "XAU",
        "prata": "XAG", "xag": "XAG",
    }

    @classmethod
    def resolve_currency(cls, value: str) -> str:
        """Resolve alias natural ("dólar") para símbolo ("USD")."""
        raw = str(value or "").strip().lower().replace("/", " ").strip()
        return cls.CURRENCY_ALIASES.get(raw, raw.upper())

    def _get_exchange_rate(self, base="USD", quote="BRL"):
        """Tool get_exchange_rate — cotação atual via MarketDataService.

        Aceita aliases naturais (dólar, euro, real...). Sem credenciais.
        Nunca inventa valor: falha reporta falha (com cache recente, se houver).
        """
        from .data.market_data import get_market_data_service
        b = self.resolve_currency(base)
        q = self.resolve_currency(quote)
        result = get_market_data_service().get_exchange_rate(b, q)
        if not result.get("ok"):
            # Falha honesta — sem número inventado.
            return {"ok": False, "message": "Não consegui consultar a cotação agora.",
                    "error": result.get("error"), "detail": result.get("detail")}

        when = str(result.get("display_timestamp") or "").strip()
        timezone_source = str(result.get("timezone_source") or "unknown")
        provider = result.get("provider", "?")
        price = result.get("price")
        if price is None:
            return {"ok": False, "message": "A fonte não retornou valor para este par.",
                    "raw": result}

        # Resposta formatada para o Brain falar.
        stale_note = " (ultima cotacao disponivel)" if result.get("stale") else ""
        message = (
            f"{b}/{q}: {price:.4f}" if q not in ("BRL",)
            else f"{b}: R$ {price:.2f}"
        )
        if when and timezone_source != "source_unspecified":
            message += f". Fonte: {provider}{stale_note}. Atualizado às {when} no horário local."
        elif when:
            message += f". Fonte: {provider}{stale_note}. Horário informado pela fonte: {when}."
        else:
            message += f". Fonte: {provider}{stale_note}. Horário da atualização não informado."
        if result.get("warning"):
            message += f" Atencao: {result['warning']}"

        return {"ok": True, "message": message,
                "base": b, "quote": q, "price": price,
                "bid": result.get("bid"), "ask": result.get("ask"),
                "timestamp": result.get("timestamp"),
                "timestamp_raw": result.get("timestamp_raw"),
                "normalized_timestamp": result.get("normalized_timestamp", ""),
                "display_timestamp": result.get("display_timestamp", ""),
                "timezone_source": timezone_source, "provider": provider,
                "from_cache": result.get("from_cache", False),
                "stale": result.get("stale", False)}

    # ═══════════════════════════════════════════════════════════════
    # EXECUÇÃO CENTRAL
    # ═══════════════════════════════════════════════════════════════
    def execute_command(self, command, task_id="desktop"):
        request_started = time.perf_counter()
        request_id = uuid.uuid4().hex
        command = str(command or "").strip()
        history = self._conversation_snapshot(task_id)
        self.orchestrator.last_decision = None
        result = self._execute_command_once(command, task_id, history)
        result = self._attach_research_telemetry(
            result, request_id, str(task_id or "desktop"), request_started)
        self._record_conversation_turn(task_id, command, result)
        return result

    def _attach_research_telemetry(self, result, request_id, session_id, started):
        result = dict(result or {})
        decision = self.orchestrator.last_decision
        executions = list(result.get("executions") or [])
        if result.get("tool"):
            executions = executions or [{"tool": result.get("tool"),
                                          "result": result}]
        research_names = {"web_research", "web_research_learn"}
        local_tools = [str(item.get("tool")) for item in executions
                       if item.get("tool") and item.get("tool") not in research_names]
        research_runs = [item for item in executions
                         if item.get("tool") in research_names]
        providers, source_count = [], 0
        official_count = community_count = 0
        source_conflict = False
        fallback_used = bool(result.get("synthesis_fallback"))
        search_ms = fetch_ms = 0
        for item in research_runs:
            payload = item.get("result") or {}
            telemetry = payload.get("telemetry") or {}
            provider = telemetry.get("provider_selected") or telemetry.get("provider")
            if provider and provider not in providers:
                providers.append(provider)
            source_count += int(telemetry.get("pages_fetched") or 0)
            official_count += int(telemetry.get("official_source_count") or 0)
            community_count += int(telemetry.get("community_source_count") or 0)
            source_conflict = source_conflict or bool(telemetry.get("source_conflict"))
            fallback_used = fallback_used or bool(telemetry.get("fallback_used"))
            search_ms += int(telemetry.get("search_ms") or 0)
            fetch_ms += int(telemetry.get("fetch_ms") or 0)
        level = getattr(decision, "research_level", "NO_RESEARCH")
        reason = getattr(decision, "research_reason", "GENERAL_KNOWLEDGE_SUFFICIENT")
        answer_route = getattr(decision, "answer_route", "TOOL_ONLY" if local_tools else "DIRECT")
        provider = result.get("synthesis_provider") or result.get("provider") or ""
        metadata = {
            "request_id": request_id, "response_id": request_id,
            "session_id": session_id,
            "timestamp": time.time(),
            "route": answer_route, "status": "SUCCESS" if result.get("ok", True) else "ERROR",
            "answer_route": answer_route,
            "research_decision": "YES" if level != "NO_RESEARCH" else "NO",
            "research_level": level, "research_reason": reason,
            "router_decision_ms": getattr(decision, "router_decision_ms", 0),
            "local_tools_used": local_tools,
            "research_providers_used": providers,
            "research_provider": providers[0] if providers else "",
            "research_used": bool(research_runs),
            "tools_used": local_tools,
            "source_count": source_count,
            "official_source_count": official_count,
            "community_source_count": community_count,
            "source_conflict": source_conflict,
            "active_provider": provider,
            "active_model": result.get("model", ""),
            "llm_provider": provider,
            "llm_model": result.get("model", ""),
            "fallback_used": fallback_used,
            "fallback_from": result.get("fallback_from", ""),
            "fallback_to": result.get("fallback_to", ""),
            "fallback_reason": result.get("fallback_reason", ""),
            "search_ms": search_ms, "fetch_ms": fetch_ms,
            "synthesis_ms": int(result.get("synthesis_ms") or 0),
            "total_ms": int((time.perf_counter() - started) * 1000),
            "llm_latency_ms": int(result.get("llm_latency_ms") or result.get("latency_ms") or 0),
            "research_latency_ms": search_ms + fetch_ms,
            "total_latency_ms": int((time.perf_counter() - started) * 1000),
            "error_type": str(result.get("error_type") or ""),
        }
        result["routing_metadata"] = metadata
        result.setdefault("response_id", request_id)
        with self._ai_status_lock:
            self._last_request_telemetry = dict(metadata)
        print("[JARVIS-RESEARCH-ROUTE] " + json.dumps(
            metadata, ensure_ascii=True, default=str), flush=True)
        return result

    def _execute_command_once(self, command, task_id, conversation_history):
        command = str(command or "").strip()
        if not command:
            return {"ok": False, "error": "Comando vazio"}
        if command.lower().strip(" .,!") in {"pare", "cancelar", "interromper", "pare jarvis", "parar jarvis"}:
            self.cancellation.request_cancel()
            try:
                self.computer_missions.cancel_current_mission()
            except Exception:
                pass
            self.state = AgentState.IDLE
            self.audit.add(task_id=task_id, command=command, tool="cancel",
                           risk=Risk.LOW.value, status="cancelamento_solicitado",
                           result="Cancelamento solicitado")
            return {"ok": True, "message": "Cancelamento solicitado.", "cancel_requested": True}
        self.cancellation.clear_cancel()
        if self.computer_missions.planner.can_plan(command):
            self.state = AgentState.EXECUTING
            return self.run_computer_mission(command, task_id)
        self.state = AgentState.PLANNING
        intent = self._parse(command)
        if not intent:
            exact = self._resolve_exact_tool_name(command)
            if exact:
                if exact.get("clarification_required"):
                    self.state = AgentState.IDLE
                    self.audit.add(task_id=task_id, command=command,
                                   tool=exact.get("tool", ""),
                                   status="clarification_required",
                                   result=exact.get("message", ""))
                    return exact
                return self.execute_tool(exact["tool"], exact.get("args", {}),
                                         command, task_id)
            # NL fallback: use Brain (orchestrator + ModelRouter + LLM)
            try:
                from .brain import get_brain
                brain = get_brain(self.registry, self.legacy_memory,
                                  orchestrator=self.orchestrator,
                                  memory_v2=getattr(self, "memory_v2", None))
                supports_history = (
                    "conversation_history" in
                    inspect.signature(brain.interpret).parameters)
                if conversation_history and supports_history:
                    brain_result = brain.interpret(
                        command, conversation_history=conversation_history)
                else:
                    brain_result = brain.interpret(command)
                if brain_result.get("ok"):
                    plan = brain_result.get("plan", {})
                    llm_info = getattr(brain, "last_llm", {})
                    llm_provider = llm_info.get("provider", "unknown")
                    llm_model = llm_info.get("model", "unknown")
                    # CONVERSATION: textual response, no tool
                    if "response" in plan:
                        self.audit.add(task_id=task_id, command=command,
                                       tool="llm_conversation", status="ok",
                                       result="LLM:%s/%s -> resposta textual" % (llm_provider, llm_model))
                        print("[JARVIS-CONTEXT] ACTIVE_PROVIDER=%s ACTIVE_MODEL=%s" % (
                            llm_provider, llm_model), flush=True)
                        return {"ok": True, "message": plan["response"],
                                "provider": llm_provider, "model": llm_model}
                    # TOOL PROPOSAL: validated by Brain, execute via security pipeline
                    if "tool" in plan:
                        tool_name = plan["tool"]
                        tool_args = plan.get("args", {})
                        self.audit.add(task_id=task_id, command=command,
                                       tool=tool_name, status="llm_proposta",
                                       result="LLM:%s/%s -> %s" % (llm_provider, llm_model, tool_name))
                        result = self.execute_tool(tool_name, tool_args,
                                                   command, task_id)
                        if tool_name in {"web_research", "web_research_learn"}:
                            return self._synthesize_single_tool_result(
                                brain, command, tool_name, tool_args, result)
                        return result
                    if "steps" in plan:
                        return self._execute_plan(brain, command, plan, task_id)
                # Brain returned error or unparseable
                error_msg = brain_result.get("error", "Não consegui processar.")
                self.audit.add(task_id=task_id, command=command,
                               tool="llm_fallback", status="erro",
                               result=error_msg)
                return {"ok": False, "error": error_msg}
            except Exception as e:
                self.audit.add(task_id=task_id, command=command,
                               tool="llm_fallback", status="excecao",
                               result=str(e)[:200])
                return {"ok": False,
                        "error": "Não entendi o comando. Tente: 'abrir calculadora', "
                                 "'tirar print', 'listar processos', 'volume baixo', etc."}
        return self.execute_tool(intent[0], intent[1], command, task_id)

    def run_computer_mission(self, request, task_id="desktop",
                             authorized_overwrite_paths=None,
                             pause_after_checkpoint=""):
        """Run a bounded Computer Use mission through the existing core."""
        return self.computer_missions.run(
            request, task_id=task_id,
            authorized_overwrite_paths=authorized_overwrite_paths,
            pause_after_checkpoint=pause_after_checkpoint)

    def resume_computer_mission(self, mission_id, token, task_id="desktop"):
        """Resume only the pending mission step after SecurityManager approval."""
        return self.computer_missions.resume(mission_id, token, task_id=task_id)

    def resume_current_mission(self, mission_id, resume_token, task_id="desktop"):
        """Resume a mission from its explicit durable checkpoint token."""
        result = self.computer_missions.resume_current_mission(
            mission_id, resume_token, task_id=task_id)
        self.task_manager.reconcile_background_mission_state(task_id, result)
        return result

    def pause_current_mission(self, reason="operator_requested"):
        """Request a safe pause at the next checkpoint boundary."""
        return self.computer_missions.pause_current_mission(reason)

    def cancel_current_mission(self):
        """Cooperatively cancel the active mission between actions."""
        self.cancellation.request_cancel()
        return self.computer_missions.cancel_current_mission()

    def _conversation_snapshot(self, task_id):
        session_id = str(task_id or "desktop")
        with self._conversation_lock:
            return [dict(item) for item in
                    self._conversation_histories.get(session_id, ())[-12:]]

    @staticmethod
    def _context_result(result):
        result = dict(result or {})
        safe = {key: value for key, value in result.items()
                if key not in {"token", "state"}}
        return json.dumps(safe, ensure_ascii=False, default=str)[:6000]

    def _record_conversation_turn(self, task_id, command, result):
        session_id = str(task_id or "desktop")
        if not command:
            return
        kind = ("TOOL_ERROR" if not result.get("ok") else
                "TOOL_RESULT" if result.get("tool") or result.get("executions") else
                "ASSISTANT_RESPONSE")
        assistant = result.get("message") or result.get("error") or "Sem resposta."
        if kind.startswith("TOOL_"):
            assistant = kind + ": " + self._context_result(result)
        with self._conversation_lock:
            history = self._conversation_histories.setdefault(session_id, [])
            history.extend(({"role": "user", "content": command},
                            {"role": "assistant", "content": str(assistant)}))
            self._conversation_histories[session_id] = history[-12:]

        previous = self._conversation_snapshot(session_id)[:-2]
        print("[JARVIS-CONTEXT] SESSION_ID_PRESENT=%s HISTORY_TURNS_SENT=%d "
              "LAST_USER_INCLUDED=%s LAST_ASSISTANT_INCLUDED=%s "
              "LAST_TOOL_RESULT_INCLUDED=%s LAST_TOOL_ERROR_INCLUDED=%s" % (
                  bool(session_id), len(previous),
                  any(item.get("role") == "user" for item in previous),
                  any(item.get("role") == "assistant" for item in previous),
                  any("TOOL_RESULT:" in item.get("content", "") for item in previous),
                  any("TOOL_ERROR:" in item.get("content", "") for item in previous)),
              flush=True)

    def _synthesize_single_tool_result(self, brain, command, tool_name, args, result):
        execution = {"step_index": 0, "tool": tool_name, "args": args,
                     "ok": bool(result.get("ok")),
                     "status": "completed" if result.get("ok") else "failed",
                     "result": {key: value for key, value in result.items()
                                if key not in {"token", "state", "risk"}}}
        if not result.get("ok"):
            return result
        synthesis = brain.synthesize_tool_results(command, [execution])
        if not synthesis.get("ok"):
            return result
        return {**result, "message": synthesis["response"],
                "final_synthesis": True,
                "synthesis_provider": synthesis.get("provider", "")}

    def _execute_plan(self, brain, command, plan, task_id):
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        is_market_plan = any(
            step.get("intent") == "market_analysis" or
            step.get("tool") in self.MARKET_PLAN_TOOLS
            for step in steps
        )
        max_plan_steps = self.MARKET_PLAN_MAX_STEPS if is_market_plan else self.MAX_PLAN_STEPS
        classification = getattr(brain.orchestrator.last_decision,
                                 "data_classification", None)
        secure_command = ("[REDACTED]" if getattr(classification, "value", classification) == "SECRET"
                          else command)
        if len(steps) > max_plan_steps:
            error = f"Plano excede o limite de {max_plan_steps} etapas."
            brain.clear_steps()
            self.audit.add(task_id=task_id, command=secure_command, tool="multi_tool_plan",
                           status="plan_rejected", result=error)
            return {"ok": False, "error": error}
        validation_error = brain._validate_plan(plan)
        self.audit.add(task_id=task_id, command=secure_command, tool="multi_tool_plan",
                       arguments={"plan_step_count": len(steps)},
                       status="plan_validated" if not validation_error else "plan_rejected",
                       result={"plan_validated": not bool(validation_error)})
        if validation_error:
            brain.clear_steps()
            return {"ok": False, "error": validation_error}

        executions = []
        for index, step in enumerate(steps):
            tool = self.registry.get(step["tool"])
            prepared_args, risk, _, preparation_error = self._prepare_execution(
                tool, step.get("args", {}))
            if preparation_error:
                result = {"ok": False, "error": preparation_error,
                          "tool": tool.name, "risk": risk.value}
            else:
                result = self.execute_tool(tool.name, step.get("args", {}),
                                           secure_command, task_id)
            execution = {
                "step_index": index,
                "tool": tool.name,
                "args": AuditLog._sanitize(prepared_args),
                "ok": bool(result.get("ok")) and not result.get("confirmation_required", False),
                "status": ("confirmation_required" if result.get("confirmation_required")
                           else "completed" if result.get("ok") else "failed"),
                "risk": result.get("risk", risk.value),
                "result": AuditLog._sanitize({
                    key: value for key, value in result.items()
                    if key not in {"token", "state", "risk", "tool"}
                }),
                "evidence_scope": ("WEB_EVIDENCE" if tool.name in
                                   {"web_research", "web_research_learn"}
                                   else "LOCAL_MARKET_DATA" if tool.name in self.MARKET_PLAN_TOOLS
                                   else "LOCAL_EVIDENCE"),
            }
            executions.append(execution)
            self.audit.add(task_id=task_id, command=secure_command, tool=tool.name,
                           arguments={"step_index": index, "step_tool": tool.name},
                           risk=execution["risk"], status="plan_step_result",
                           result={"ok": execution["ok"], "status": execution["status"]})
            if result.get("confirmation_required"):
                brain.clear_steps()
                self.audit.add(task_id=task_id, command=secure_command, tool=tool.name,
                               risk=execution["risk"], status="plan_paused_for_confirmation",
                               result={"step_index": index, "remaining_steps": len(steps) - index - 1})
                return {**result, "plan_paused": True,
                        "completed_steps": executions[:-1],
                        "message": result.get("message", "") +
                                   " O plano será encerrado após esta ação por segurança."}
            if not result.get("ok") and not (
                    is_market_plan and tool.name in self.MARKET_OPTIONAL_TOOLS):
                break

        brain.clear_steps()
        synthesis_started = time.perf_counter()
        synthesis = brain.synthesize_tool_results(
            command, self._compact_synthesis_executions(executions))
        synthesis_ms = int((time.perf_counter() - synthesis_started) * 1000)
        provider = synthesis.get("provider", "none")
        if synthesis.get("ok"):
            message = synthesis["response"]
            synthesis_status = "ok"
        else:
            message = self._deterministic_plan_summary(executions)
            synthesis_status = "fallback"
        self.audit.add(task_id=task_id, command=secure_command, tool="final_synthesis",
                       status=synthesis_status,
                       result={"provider": provider, "execution_count": len(executions)})
        perf_diagnostic = self._performance_diagnostic(executions)
        return {"ok": all(item["ok"] or (
                    is_market_plan and item["tool"] in self.MARKET_OPTIONAL_TOOLS)
                           for item in executions), "message": message,
                "executions": executions, "final_synthesis": True,
                "synthesis_provider": provider,
                "synthesis_ms": synthesis_ms,
                "perf_diagnostic": perf_diagnostic,
                "synthesis_fallback": not synthesis.get("ok")}

    @staticmethod
    def _compact_synthesis_executions(executions):
        compact = []
        for execution in executions:
            item = dict(execution)
            result = dict(item.get("result") or {})
            if item.get("tool") == "list_processes":
                result.pop("processes", None)
                result["top_cpu"] = list(result.get("top_cpu") or [])[:5]
                result["top_memory"] = list(result.get("top_memory") or [])[:5]
                if result.get("message"):
                    result["message"] = str(result["message"])[:2000]
            item["result"] = result
            compact.append(item)
        return compact

    @staticmethod
    def _performance_diagnostic(executions):
        status = processes = {}
        for execution in executions:
            if execution.get("tool") == "system_status":
                status = execution.get("result") or {}
            elif execution.get("tool") == "list_processes":
                processes = execution.get("result") or {}
        if not status and not processes:
            return {}
        top_cpu = list(processes.get("top_cpu") or [])
        top_memory = list(processes.get("top_memory") or [])
        cpu_process = top_cpu[0] if top_cpu else {}
        memory_process = top_memory[0] if top_memory else {}
        top_cpu_now = cpu_process.get("cpu_percent_now")
        principal_supported = isinstance(top_cpu_now, (int, float)) and top_cpu_now >= 1.0
        return {
            "cpu_total_now": status.get("cpu_total_now"),
            "top_cpu_process": ((cpu_process.get("display_name") or cpu_process.get("name"))
                                if principal_supported else None),
            "top_cpu_candidate": cpu_process.get("display_name") or cpu_process.get("name"),
            "top_cpu_percent_now": top_cpu_now,
            "top_memory_process": memory_process.get("display_name") or memory_process.get("name"),
            "disk_capacity_used_percent": status.get("disk_capacity_used_percent"),
            "disk_free_gb": status.get("disk_free_gb"),
            "cpu_metric_available": bool(top_cpu),
            "principal_cpu_supported": principal_supported,
        }

    @staticmethod
    def _deterministic_plan_summary(executions):
        parts = []
        for item in executions:
            result = item.get("result", {})
            if item.get("ok"):
                detail = result.get("message") if isinstance(result, dict) else ""
                parts.append(f"{item['tool']}: {detail or 'concluído.'}")
            else:
                detail = result.get("error") if isinstance(result, dict) else ""
                parts.append(f"{item['tool']}: não foi possível obter esta parte"
                             + (f" ({detail})" if detail else "."))
        return " ".join(parts) or "Não foi possível obter resultados para esta solicitação."

    def _resolve_exact_tool_name(self, command):
        """Resolve a literal tool name without bypassing execute_tool/security."""
        raw = str(command or "").strip()
        if not raw:
            return None
        lowered = raw.lower()
        matches = [tool for name, tool in self.registry._tools.items()
                   if lowered == name.lower()]
        if not matches:
            return None
        tool = matches[0]
        if not tool.llm_enabled:
            return None
        missing = self._missing_required_arguments(tool, {})
        if missing:
            return {
                "ok": True,
                "clarification_required": True,
                "tool": tool.name,
                "missing": missing,
                "message": self._clarification_for_missing_args(tool, missing),
            }
        return {"tool": tool.name, "args": {}, "exact_tool_name": True}

    def _missing_required_arguments(self, tool, arguments):
        signature = inspect.signature(tool.handler)
        return [name for name in tool.parameters
                if name not in arguments
                and name in signature.parameters
                and signature.parameters[name].default is inspect.Parameter.empty]

    @staticmethod
    def _clarification_for_missing_args(tool, missing):
        if tool.name == "open_program" and "name" in missing:
            return "Qual programa você quer abrir?"
        if len(missing) == 1:
            return "Qual valor você quer usar para %s?" % missing[0]
        return "Quais valores você quer usar para: %s?" % ", ".join(missing)

    def execute_tool(self, name, arguments, command="",
                     task_id="desktop", confirmed=False,
                     authorization_scope="", target_url="",
                     allowed_hosts=(), page_barrier=""):
        tool = self.registry.get(name)
        if not tool:
            self.audit.add(task_id=task_id, command=command, tool=str(name),
                           status="rejeitado", result="Ferramenta não cadastrada")
            return {"ok": False, "error": "Ferramenta não cadastrada."}
        arguments, effective_risk, force_confirmation, preparation_error = self._prepare_execution(tool, arguments)
        if preparation_error:
            self.state = AgentState.ERROR
            self.audit.add(task_id=task_id, command=command, tool=name,
                           arguments=arguments, risk=effective_risk.value,
                           status="rejeitado", result=preparation_error)
            return {"ok": False, "error": preparation_error, "tool": name}
        error = self._validate(tool, arguments)
        if error:
            self.audit.add(task_id=task_id, command=command, tool=name,
                           arguments=arguments, risk=effective_risk.value,
                           status="rejeitado", result=error)
            return {"ok": False, "error": error}
        if self.cancellation.is_cancelled():
            return {"ok": False, "error": "Execução cancelada antes de iniciar.", "cancelled": True}
        decision = self.security.decision(
            tool, effective_risk, force_confirmation,
            authorization_scope=authorization_scope,
            target_url=target_url,
            allowed_hosts=allowed_hosts,
            page_barrier=page_barrier)
        if decision == "deny":
            self.state = AgentState.IDLE
            return {"ok": False,
                    "error": "Ferramenta bloqueada pela política de segurança."}
        if decision == "confirm" and not confirmed:
            token = self.security.create_confirmation(tool, arguments, command, effective_risk)
            self.state = AgentState.WAITING_CONFIRMATION
            self.audit.add(task_id=task_id, command=command, tool=name,
                           arguments=arguments, risk=effective_risk.value,
                           status="aguardando_confirmacao",
                           result="Expira em 60 segundos")
            return {"ok": True, "confirmation_required": True, "token": token,
                    "action": name, "risk": effective_risk.value,
                    "message": f"Confirmação {effective_risk.value} obrigatória. "
                               f"Expira em 60 segundos."}
        started = time.time()
        self.state = AgentState.EXECUTING
        try:
            if self.dry_run:
                result = {"ok": True,
                          "message": f"SIMULAÇÃO: executaria {tool.description}.",
                          "verified": True, "verification": "dry_run_simulation"}
            else:
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(tool.handler, **arguments)
                try:
                    result = future.result(timeout=tool.timeout)
                except TimeoutError:
                    future.cancel()
                    result = {"ok": False, "error": f"Ferramenta excedeu o limite de {tool.timeout} segundos."}
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
            status = ("simulado" if self.dry_run
                      else ("executado" if result.get("ok") else "falhou"))
        except Exception as exc:
            result, status = {"ok": False, "error": str(exc)}, "erro"
        self.state = (AgentState.IDLE if result.get("ok")
                      else AgentState.ERROR)
        result = self._apply_verification(tool, arguments, result)
        self.audit.add(
            task_id=task_id, command=command, tool=name,
            arguments=arguments, risk=effective_risk.value, status=status,
            result={"message": result.get("message") or result.get("error"),
                    "response_policy": result.get("response_policy"),
                    "success": result.get("success"), "verified": result.get("verified"),
                    "verification": result.get("verification")},
            elapsed_ms=int((time.time() - started) * 1000))
        result.update({"tool": name, "risk": effective_risk.value,
                        "state": self.state.value})
        return result

    def _apply_verification(self, tool, arguments, result):
        result = dict(result or {})
        success = bool(result.get("ok"))
        verified = bool(result.get("verified", False))
        verification = str(result.get("verification") or "none")
        if success and not self.dry_run and "verified" not in result:
            verified, verification = self._verify_postcondition(tool.name, arguments, result)
        result.update({"success": success, "verified": verified,
                       "verification": verification,
                       "response_policy": tool.response_policy.value})
        if success and not verified and tool.response_policy == ResponsePolicy.FINAL:
            result["message"] = (
                f"Enviei o comando para {tool.description.lower()}, "
                "mas não consegui confirmar o resultado."
            )
        return result

    def _verify_postcondition(self, name, args, result):
        if name == "get_exchange_rate":
            valid = isinstance(result.get("price"), (int, float)) and bool(result.get("provider"))
            return valid, "provider_payload" if valid else "invalid_provider_payload"
        if name in {"web_research", "web_research_learn"}:
            valid = bool(result.get("ok")) and bool(result.get("telemetry"))
            return valid, "research_report" if valid else "research_failed"
        if name in {"get_time", "get_date", "get_ip", "system_status", "get_username",
                    "get_active_window", "get_battery", "get_network", "is_running"}:
            return True, "query_completed"
        if name == "open_program":
            return self._program_is_running(args.get("name", "")), "process_lookup"
        if name == "close_program":
            return not self._program_is_running(args.get("name", "")), "process_lookup"
        source = Path(str(args.get("source", ""))) if args.get("source") else None
        if name == "copy_file":
            return Path(str(args.get("dest", ""))).exists(), "destination_exists"
        if name == "move_file":
            valid = Path(str(args.get("dest", ""))).exists() and bool(source and not source.exists())
            return valid, "destination_exists_source_absent"
        if name == "rename_file" and source:
            dest = source.parent / str(args.get("new_name", ""))
            return dest.exists() and not source.exists(), "renamed_path_exists"
        if name == "delete_file":
            return not Path(str(args.get("path", ""))).exists(), "path_absent"
        if name == "create_folder":
            target = Path(str(args.get("path", "")))
            return target.is_dir(), "directory_exists"
        return False, "postcondition_unavailable"

    def _program_is_running(self, name):
        exe = Path(str(self.PROGRAMS.get(str(name).lower(), name))).name.lower()
        aliases = {exe}
        if exe == "calc.exe":
            aliases.add("calculatorapp.exe")
        try:
            done = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                  capture_output=True, text=True, timeout=5)
            output = done.stdout.lower()
            return any(f'"{candidate}"' in output for candidate in aliases)
        except Exception:
            return False

    def confirm(self, token, task_id="desktop"):
        item = self.security.consume(token)
        if not item:
            return {"ok": False,
                    "error": "Confirmação inválida ou expirada."}
        return self.execute_tool(item["tool"], item["arguments"],
                                 item["command"], task_id, confirmed=True)

    def deny_confirmation(self, token, task_id="desktop"):
        """Consume a confirmation token without executing. Fail-closed."""
        item = self.security.consume(token)
        if item:
            self.audit.add(task_id=task_id, command=item.get("command", ""),
                           tool=item.get("tool", ""), risk=item.get("risk", "unknown"),
                           status="cancelado_pelo_operador",
                           result="Confirmação negada pelo operador")
        return {"ok": True, "denied": True,
                "message": "Ação cancelada pelo operador."}

    def record_response_metrics(self, route, skill, tool, telemetry, result, ack=None,
                                task_id="desktop"):
        """Registra apenas contadores/estados P0; nunca prompt ou conteúdo do usuário."""
        metrics = dict(telemetry or {})
        outcome = dict(result or {})
        ack = dict(ack or {})
        self.audit.add(task_id=task_id, command="response_metrics", tool=str(tool or ""),
            arguments={"request_id": metrics.get("request_id", ""), "route": route,
                "skill": skill, "llm_calls_before_tool": metrics.get("llm_calls_before_tool", 0),
                "llm_calls_after_tool": metrics.get("llm_calls_after_tool", 0),
                "total_llm_calls": metrics.get("total_llm_calls", 0),
                "static_prompt_size": metrics.get("static_prompt_size", 0),
                "runtime_context_size": metrics.get("runtime_context_size", 0),
                "tool_catalog_size": metrics.get("tool_catalog_size", 0),
                "ack_emitted": bool(ack.get("emitted"))},
            risk="LOW", status="p0_metrics",
            result={"response_policy": outcome.get("response_policy", "NEEDS_SYNTHESIS"),
                "success": bool(outcome.get("success", outcome.get("ok"))),
                "verified": bool(outcome.get("verified")),
                "verification": outcome.get("verification", "none")})

    # ═══════════════════════════════════════════════════════════════
    # VALIDAÇÃO
    # ═══════════════════════════════════════════════════════════════
    def _validate(self, tool, arguments):
        if not isinstance(arguments, dict):
            return "Argumentos inválidos."
        unknown = set(arguments) - set(tool.parameters)
        if unknown:
            return "Parâmetro não permitido: " + ", ".join(sorted(unknown))
        signature = inspect.signature(tool.handler)
        for key, expected in tool.parameters.items():
            parameter = signature.parameters.get(key)
            if key not in arguments and parameter and parameter.default is inspect.Parameter.empty:
                return f"Parâmetro obrigatório ausente: {key}"
            if key in arguments and (isinstance(arguments[key], bool) and expected is int
                                     or not isinstance(arguments[key], expected)):
                return f"Parâmetro inválido: {key} (esperado {expected.__name__})"
        return None

    def _prepare_execution(self, tool, arguments):
        if not isinstance(arguments, dict):
            return arguments, tool.risk, False, None
        normalized = dict(arguments)
        risk = tool.risk
        force_confirmation = False
        if tool.name in {"open_any_exe", "delete_file"} and isinstance(normalized.get("path"), str):
            normalized["path"] = str(Path(os.path.expandvars(
                os.path.expanduser(normalized["path"]))).resolve())
        if tool.name == "open_any_exe":
            path = Path(normalized.get("path", ""))
            blocked = {"cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe",
                       "cscript.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe"}
            if path.name.lower() in blocked:
                return normalized, Risk.CRITICAL, True, "Executável de script ou shell bloqueado pela política."
            if not path.exists() or not path.is_file() or path.suffix.lower() != ".exe":
                return normalized, Risk.HIGH, True, "O caminho deve apontar para um arquivo .exe existente."
            lowered = str(path).lower()
            suspicious = any(part in lowered for part in ("\\downloads\\", "\\temp\\",
                             "\\appdata\\local\\temp\\", "\\cache\\", "\\\\"))
            trusted_paths = {str(Path(v).resolve()).lower() for v in self.PROGRAMS.values()
                             if Path(v).is_absolute()}
            if lowered in trusted_paths:
                risk = Risk.LOW
            elif suspicious:
                risk, force_confirmation = Risk.CRITICAL, True
            elif lowered.startswith(("c:\\program files\\", "c:\\program files (x86)\\")):
                risk, force_confirmation = Risk.MEDIUM, True
            else:
                risk, force_confirmation = Risk.HIGH, True
        if tool.name == "kill_process":
            name_map = {"gerenciador de tarefas": "taskmgr", "task manager": "taskmgr",
                        "chrome": "chrome", "edge": "msedge", "firefox": "firefox"}
            name = str(normalized.get("name", "")).lower().removesuffix(".exe")
            name = name_map.get(name, name)
            protected = {"system", "registry", "smss", "csrss", "wininit", "services",
                         "lsass", "svchost", "winlogon", "server_agent", "ollama", "python"}
            if name in protected:
                return normalized, Risk.CRITICAL, True, "Processo protegido não pode ser encerrado por esta ferramenta."
            normalized["name"] = name + ".exe"
            risk, force_confirmation = Risk.HIGH, True
        if tool.name == "delete_file":
            risk, force_confirmation = Risk.HIGH, True
        return normalized, risk, force_confirmation, None

    # ═══════════════════════════════════════════════════════════════
    # PARSER DE COMANDOS EM LINGUAGEM NATURAL
    # ═══════════════════════════════════════════════════════════════
    def _parse(self, command):
        lower = command.lower().strip()

        # ── CONCEPTUAL BYPASS ──
        # Perguntas conceituais devem ir para Brain/LLM, não para parser determinístico.
        # Uses shared is_conceptual_query() from orchestrator module.
        try:
            from .orchestrator.orchestrator import is_conceptual_query
            if is_conceptual_query(command):
                return None
        except Exception:
            pass

        # Helper: word-boundary match for short ambiguous terms
        def _match(text, *terms):
            for t in terms:
                if len(t) <= 3:
                    if re.search(r'\b' + re.escape(t) + r'\b', text):
                        return True
                elif t in text:
                    return True
            return False

        # ── SISTEMA ──
        if "reiniciar" in lower or "reinicia" in lower:
            return "restart", {}
        if "desligar" in lower or "desliga" in lower or "desligue" in lower:
            return "shutdown", {}
        if any(w in lower for w in ("bloquear", "bloqueia", "trancar", "trancar pc",
                                     "bloquear sessão", "bloquear computador")):
            return "lock_windows", {}
        if any(w in lower for w in ("minimizar tudo", "minimiza tudo",
                                     "mostrar área", "mostrar desktop",
                                     "mostrar area")):
            return "show_desktop", {}
        if "minimizar" in lower and any(w in lower for w in ("tudo", "tela", "janelas")):
            return "minimize_all", {}
        if any(w in lower for w in ("centro de ações", "centro de acoes",
                                     "action center", "notificações")):
            return "open_control_center", {}

        # ── CONTROLE DE JANELAS ──
        if any(w in lower for w in ("fechar janela", "feche janela",
                                     "fechar esta janela")):
            return "close_active_window", {}
        if any(w in lower for w in ("maximizar", "maximiza",
                                     "tela cheia", "tela inteira")):
            return "maximize_window", {}
        if any(w in lower for w in ("minimizar janela", "minimiza janela",
                                     "esconder janela")):
            return "minimize_window", {}
        if any(w in lower for w in ("trocar janela", "alternar janela",
                                     "próxima janela", "proxima janela",
                                     "alt tab")):
            return "switch_window", {}

        # ── OPERAÇÕES COM ARQUIVOS ──
        if any(w in lower for w in ("copiar arquivo", "copiar", "copie")):
            copy_match = re.search(r"copiar?\s+(?:o\s+|arquivo\s+)?(.+?)\s+(?:para|pra|p/|->)\s+(.+)$", lower)
            if copy_match:
                return "copy_file", {"source": copy_match.group(1).strip(), "dest": copy_match.group(2).strip()}
        if any(w in lower for w in ("mover arquivo", "mover", "mova")):
            move_match = re.search(r"mover?\s+(?:o\s+|arquivo\s+)?(.+?)\s+(?:para|pra|p/|->)\s+(.+)$", lower)
            if move_match:
                return "move_file", {"source": move_match.group(1).strip(), "dest": move_match.group(2).strip()}
        if any(w in lower for w in ("renomear", "renomeie", "renomear arquivo")):
            rename_match = re.search(r"renomear?\s+(?:o\s+|arquivo\s+)?(.+?)\s+(?:para|pra|p/|para)\s+(.+)$", lower)
            if rename_match:
                return "rename_file", {"source": rename_match.group(1).strip(), "new_name": rename_match.group(2).strip()}
        if any(w in lower for w in ("excluir arquivo", "apagar arquivo",
                                     "deletar arquivo", "excluir", "apagar")):
            del_match = re.search(r"(?:excluir|apagar|deletar)\s+(?:o\s+|arquivo\s+)?(.+)$", lower)
            if del_match:
                return "delete_file", {"path": del_match.group(1).strip()}
        if any(w in lower for w in ("criar pasta", "criar uma pasta", "nova pasta")):
            mkdir_match = re.search(r"(?:criar|nova)\s+(?:a\s+)?pasta\s+(.+)$", lower)
            if mkdir_match:
                return "create_folder", {"path": mkdir_match.group(1).strip()}
        if any(w in lower for w in ("listar pasta", "lista de",
                                     "conteúdo da pasta", "conteudo da pasta",
                                     "o que tem na pasta", "abrir pasta")):
            folder_match = re.search(r"(?:listar|lista|conteúdo|conteudo|o que tem|abra a?|abrir a?)\s+(?:pasta\s+|de\s+)?(.+)$", lower)
            if folder_match:
                folder_name = folder_match.group(1).strip()
                for alias, special in self.SPECIAL_FOLDERS.items():
                    if alias in folder_name:
                        return "list_folder", {"path": str(Path.home() / special)}
                return "list_folder", {"path": folder_name}

        # ── HORA / DATA / INFO ──
        if any(w in lower for w in ("que horas", "hora atual", "horas são",
                                     "horas sao", "que hora")):
            return "get_time", {}
        if _match(lower, "data", "dia atual", "que dia",
                  "data de hoje"):
            return "get_date", {}
        if _match(lower, "ip", "endereço ip", "endereco ip"):
            return "get_ip", {}
        if any(w in lower for w in ("usuário", "usuario", "quem está",
                                     "quem esta", "nome do usuário")):
            return "get_username", {}
        if any(w in lower for w in ("janela ativa", "janela aberta",
                                     "qual janela", "programa ativo")):
            return "get_active_window", {}
        if any(w in lower for w in ("bateria", "battery")):
            return "get_battery", {}
        if any(w in lower for w in ("rede", "network", "conexão",
                                     "conexao", "internet")):
            return "get_network", {}
        if any(w in lower for w in ("arquivos recentes", "recentes",
                                     "últimos arquivos", "ultimos arquivos")):
            return "get_recent_files", {}

        # ── VOLUME ──
        if any(w in lower for w in ("aumentar volume", "aumenta volume",
                                     "volume pra cima", "volume mais",
                                     "aumentar som", "mais volume")):
            return "volume_up", {}
        if any(w in lower for w in ("diminuir volume", "diminui volume",
                                     "volume pra baixo", "menos volume",
                                     "abaixar volume", "baixar volume",
                                     "diminuir som")):
            return "volume_down", {}
        if any(w in lower for w in ("silenciar", "mudo", "mudo o som",
                                     "mutar", "mutar som", "sem som",
                                     "silenciar áudio", "silenciar audio")):
            return "volume_mute", {}
        vol_match = re.search(r"volume\s*(?:em|para|=)\s*(\d+)", lower)
        if vol_match:
            return "volume_set", {"level": int(vol_match.group(1))}

        # ── SISTEMA / STATUS ──
        if _match(lower, "cpu", "processador", "uso do processador"):
            return "system_status", {}
        if _match(lower, "memória", "memoria", "ram",
                  "memória ram", "memoria ram"):
            return "system_status", {}
        if _match(lower, "disco", "espaço", "espaco",
                  "armazenamento", "hd"):
            return "system_status", {}
        if _match(lower, "status do computador", "status do pc",
                  "como está o pc", "como esta o pc",
                  "saúde do pc", "saude do pc",
                  "status do sistema", "como está o sistema",
                  "como esta o sistema", "status geral"):
            return "system_status", {}

        # ── VISÃO (ver/ler tela com IA) ──
        if any(w in lower for w in ("veja minha tela", "veja a tela", "olhe a tela",
                                     "olhe minha tela", "o que esta aparecendo",
                                     "o que apareceu", "leia a tela", "leia o erro",
                                     "analise a tela", "ve o que tem na tela",
                                     "onde esta o botao", "o que voce ve")):
            # Extrair pergunta opcional
            question = ""
            q_match = re.search(r"(?:onde esta|qual|que erro|o que)[^?]*\??", lower)
            if q_match:
                question = q_match.group().strip()
            return "analyze_screen", {"question": question}

        # ── SCREENSHOT ──
        if any(w in lower for w in ("captura", "screenshot", "print",
                                     "print da tela", "print da tela",
                                     "tirar print", "tirar screenshot",
                                     "capturar tela", "capturar a tela",
                                     "tirar captura", "tire um print",
                                     "tire print", "tira print")):
            return "take_screenshot", {}
        if any(w in lower for w in ("captura janela", "print janela",
                                     "capturar janela")):
            window = re.sub(r".*(?:captura|print|da )\s*(?:janela|de)\s*", "",
                            lower).strip()
            return "take_screenshot_window", {"window": window or "ativa"}

        # ── PROCESSOS (só sem verbo de abertura) ──
        if any(w in lower for w in ("listar processos", "lista de processos",
                                     "processos abertos", "quais processos",
                                     "o que está rodando", "o que esta rodando",
                                     "programas abertos", "quais programas",
                                     "liste processos", "liste os processos",
                                     "mostre processos", "mostre os processos",
                                     "exiba processos", "exibir processos")):
            return "list_processes", {}
        if any(w in lower for w in ("fechar processo", "encerrar processo",
                                     "matar processo", "kill process")):
            name = re.sub(r".*(?:fechar|encerrar|matar|kill)\s*(?:processo|o)\s*",
                          "", lower).strip()
            if name:
                return "kill_process", {"name": name}
        if any(w in lower for w in ("está aberto", "esta aberto",
                                     "está rodando", "esta rodando",
                                     "tem o", "tem o ")):
            name = re.sub(r".*(?:está|esta|tem)\s*(?:o|a)?\s*", "", lower).strip()
            if name:
                return "is_running", {"name": name}

        # ── URL / SITE ──
        url_match = re.search(
            r"(?:abra|abrir|abre|acessar|acesse|ir para|abrir o site|abrir site)"
            r"\s+(?:o\s+)?(?:site\s+)?(https?://\S+|www\.\S+|\S+\.com\S*)",
            lower)
        if url_match:
            url = url_match.group(1)
            if not url.startswith("http"):
                url = "https://" + url
            return "open_url", {"url": url}

        # ── PASTAS ESPECIAIS ──
        for alias, folder_name in self.SPECIAL_FOLDERS.items():
            if alias in lower and any(w in lower for w in (
                    "abrir", "abra", "abre", "acessar", "acesse",
                    "ir para", "vai para", "vá para", "mostre",
                    "abra a pasta", "abra pasta")):
                return "open_folder", {"name": folder_name}
        # Sem verbo de abertura para pastas especiais — detectar sozinho
        for alias, folder_name in self.SPECIAL_FOLDERS.items():
            if lower.strip() == alias:
                return "open_folder", {"name": folder_name}

        # ── PROGRAMAS CADASTRADOS ──
        # Ordenar por comprimento (mais longo primeiro) para pegar nomes compostos
        sorted_programs = sorted(self.PROGRAMS.keys(), key=len, reverse=True)
        for prog_name in sorted_programs:
            if prog_name in lower:
                if any(w in lower for w in ("fechar", "feche", "encerrar",
                                             "encerre", "matar", "kill")):
                    return "close_program", {"name": prog_name}
                if any(w in lower for w in ("abrir", "abra", "abre",
                                             "iniciar", "inicia", "start")):
                    return "open_program", {"name": prog_name}
                # Sem verbo — se está no nome do programa, abre
                return "open_program", {"name": prog_name}

        # ── ABRIR QUALQUER EXE POR NOME ──
        exe_match = re.search(
            r"(?:abra|abrir|abre|iniciar|executar|rode|execute)\s+"
            r"(?:o\s+|a\s+)?(.+)$", lower)
        if exe_match:
            name = exe_match.group(1).strip()
            # Tentar como programa cadastrado
            for prog_name in sorted_programs:
                if prog_name in name:
                    return "open_program", {"name": prog_name}
            # Tentar como caminho de exe
            if name.endswith((".exe", ".cmd", ".bat", ".msc")):
                return "open_any_exe", {"path": name}

        # ── ABRIR PASTA POR CAMINHO ──
        path_match = re.search(
            r"(?:abra|abrir|abre|acessar|acesse|ir para|abra a pasta|abrir pasta)"
            r"\s+(?:a\s+)?(?:pasta\s+)?[\"']?(.+?)[\"']?\s*$", command, re.I)
        if path_match:
            path = path_match.group(1).strip().strip('"').strip("'")
            # Verificar se é pasta especial
            for alias, folder_name in self.SPECIAL_FOLDERS.items():
                if alias in path.lower():
                    return "open_folder", {"name": folder_name}
            # Nomes especiais do Windows que NÃO são paths reais
            _WINDOWS_SPECIAL_NAMES = {
                "lixeira", "recycle bin", "papel de lixeira",
                "meu computador", "este computador", "my computer",
                "rede", "network", "painel de controle", "control panel",
                "configurações", "settings", "bloco de notas",
            }
            if path.lower().strip() in _WINDOWS_SPECIAL_NAMES:
                return None
            return "open_path", {"path": path}

        # ── ABRIR ARQUIVO ──
        file_match = re.search(
            r"(?:abra|abrir|abre|abrir o arquivo|abra o arquivo)\s+"
            r"[\"']?([^\s\"']+\.\w+)[\"']?", command, re.I)
        if file_match:
            return "open_file", {"path": file_match.group(1)}

        # ── BUSCAR ARQUIVOS ──
        if any(w in lower for w in ("buscar arquivo", "procurar arquivo",
                                     "buscar arquivos", "procurar arquivos",
                                     "achar arquivo", "encontrar arquivo",
                                     "onde está", "onde esta")):
            query = re.sub(
                r".*(?:buscar|procurar|achar|encontrar|onde está|onde esta)"
                r"\s*(?:o\s+|a\s+|arquivos?\s*)?", "", lower).strip()
            if query:
                return "search_files", {"query": query, "folder": str(Path.home())}

        # ── ABRIR QUALQUER CAMINHO RESTANTE ──
        open_match = re.search(
            r"(?:abra|abrir|abre)\s+(.+)$", command, re.I)
        if open_match:
            target = open_match.group(1).strip().strip('"').strip("'")
            # Verificar se é pasta especial
            for alias, folder_name in self.SPECIAL_FOLDERS.items():
                if alias in target.lower():
                    return "open_folder", {"name": folder_name}
            # Verificar se é programa cadastrado
            for prog_name in sorted_programs:
                if prog_name in target.lower():
                    return "open_program", {"name": prog_name}
            # Nomes especiais do Windows que NÃO são paths reais
            # e não têm tool registrada → deixar Brain/LLM decidir
            _WINDOWS_SPECIAL_NAMES = {
                "lixeira", "recycle bin", "papel de lixeira",
                "meu computador", "este computador", "my computer",
                "rede", "network", "painel de controle", "control panel",
                "configurações", "settings", "bloco de notas",
            }
            target_lower = target.lower().strip()
            if target_lower in _WINDOWS_SPECIAL_NAMES:
                return None
            return "open_path", {"path": target}

        return None

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — PROGRAMAS
    # ═══════════════════════════════════════════════════════════════
    def _open_program(self, name):
        exe = self.PROGRAMS.get(name.lower())
        if not exe:
            return {"ok": False, "error": f"Programa '{name}' não encontrado no cadastro."}
        try:
            subprocess.Popen([exe], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            return {"ok": True, "message": f"{name.title()} aberto."}
        except FileNotFoundError:
            return {"ok": False, "error": f"Executável '{exe}' não encontrado no sistema."}

    def _close_program(self, name):
        exe = self.PROGRAMS.get(name.lower())
        if not exe:
            return {"ok": False, "error": f"Programa '{name}' não encontrado no cadastro."}
        done = subprocess.run(
            ["taskkill", "/IM", Path(exe).name, "/T"],
            capture_output=True, timeout=10)
        if done.returncode == 0:
            return {"ok": True, "message": f"{name.title()} encerrado."}
        return {"ok": False, "error": f"Não encontrei {name} aberto."}

    def _open_any_exe(self, path):
        try:
            subprocess.Popen([path], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            return {"ok": True, "message": f"{path} iniciado."}
        except FileNotFoundError:
            return {"ok": False, "error": f"Executável '{path}' não encontrado."}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — PASTAS E ARQUIVOS
    # ═══════════════════════════════════════════════════════════════
    def _open_folder(self, name):
        # Normalizar: lower + sem acentos
        name_lower = name.lower().strip()
        # Se é caminho absoluto
        if Path(name).is_absolute():
            path = Path(name)
        # Pasta especial (case-insensitive)
        elif name_lower in self.SPECIAL_FOLDERS:
            folder = self.SPECIAL_FOLDERS[name_lower]
            if Path(folder).is_absolute():
                path = Path(folder)
            else:
                path = Path.home() / folder
        else:
            path = Path(name).expanduser()
        if not path.exists():
            return {"ok": False, "error": f"Pasta não encontrada: {path}"}
        os.startfile(str(path))
        return {"ok": True, "message": f"Pasta aberta: {path}"}

    def _open_file(self, path):
        target = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
        if not target.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {target}"}
        os.startfile(str(target))
        return {"ok": True, "message": f"Arquivo aberto: {target.name}"}

    def _open_path(self, path):
        target = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
        if not target.exists():
            return {"ok": False, "error": f"Caminho não encontrado: {target}"}
        os.startfile(str(target))
        return {"ok": True, "message": f"Aberto: {target}"}

    def _search_files(self, query, folder=None):
        search_in = Path(folder) if folder else Path.home()
        results = []
        try:
            for item in search_in.rglob(f"*{query}*"):
                if len(results) >= 20:
                    break
                if item.is_file():
                    results.append(str(item))
        except PermissionError:
            pass
        if not results:
            return {"ok": True, "message": f"Nenhum arquivo encontrado com '{query}' em {search_in}."}
        msg = f"Encontrei {len(results)} arquivo(s) com '{query}':\n"
        msg += "\n".join(f"  • {r}" for r in results[:10])
        return {"ok": True, "message": msg, "files": results}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — PROCESSOS
    # ═══════════════════════════════════════════════════════════════
    def _list_processes(self):
        try:
            import psutil
            logical_cpus = max(1, psutil.cpu_count(logical=True) or 1)
            sampled = []
            for proc in psutil.process_iter(("pid", "name", "exe", "memory_info",
                                             "memory_percent", "cpu_times", "status")):
                try:
                    proc.cpu_percent(None)
                    sampled.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            time.sleep(.25)
            processes = []
            for proc in sampled:
                try:
                    info = proc.as_dict(attrs=("pid", "name", "exe", "memory_info",
                                               "memory_percent", "cpu_times", "status"))
                    if int(info.get("pid") or 0) == 0:
                        continue
                    raw_cpu = proc.cpu_percent(None)
                    cpu_now = round(max(0.0, raw_cpu / logical_cpus), 2)
                    cpu_times = info.get("cpu_times")
                    cpu_total = round(float((getattr(cpu_times, "user", 0.0) or 0.0) +
                                            (getattr(cpu_times, "system", 0.0) or 0.0)), 2)
                    memory_info = info.get("memory_info")
                    path = str(info.get("exe") or "")
                    identity = self._safe_process_identity(info.get("name"), path)
                    processes.append({
                        "pid": info.get("pid"), "name": info.get("name") or "unknown",
                        "cpu_percent_now": cpu_now, "cpu_time_total": cpu_total,
                        "memory_mb": round(float(getattr(memory_info, "rss", 0) or 0) / 1048576, 1),
                        "memory_percent": round(float(info.get("memory_percent") or 0), 2),
                        "status": info.get("status") or "unknown", "executable_path": path,
                        **identity,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            top = sorted(processes, key=lambda item: item["cpu_percent_now"], reverse=True)[:15]
            lines = []
            for p in top:
                lines.append("  • %s (PID %s) CPU agora: %.2f%% | CPU total: %.1fs | RAM: %.1fMB" % (
                    p["display_name"], p["pid"], p["cpu_percent_now"],
                    p["cpu_time_total"], p["memory_mb"]))
            msg = f"Processos amostrados ({len(processes)} total):\n" + "\n".join(lines)
            by_memory = sorted(processes, key=lambda item: item["memory_mb"], reverse=True)[:15]
            return {"ok": True, "message": msg, "count": len(processes),
                    "processes": top, "top_cpu": top,
                    "top_memory": by_memory, "sample_interval_ms": 250,
                    "cpu_metric_source": "psutil_two_sample_normalized_by_logical_cpu"}
        except Exception as e:
            return {"ok": False, "error": f"Erro ao listar processos: {e}"}

    @staticmethod
    def _safe_process_identity(name, executable_path):
        process_name = str(name or "unknown")
        path = str(executable_path or "")
        product = company = ""
        if path and os.name == "nt":
            try:
                import win32api
                translations = win32api.GetFileVersionInfo(path, r"\VarFileInfo\Translation")
                if translations:
                    lang, codepage = translations[0]
                    prefix = "\\StringFileInfo\\%04x%04x\\" % (lang, codepage)
                    product = str(win32api.GetFileVersionInfo(path, prefix + "ProductName") or "").strip()
                    company = str(win32api.GetFileVersionInfo(path, prefix + "CompanyName") or "").strip()
            except Exception:
                pass
        if product:
            return {"display_name": product, "product_name": product,
                    "company_name": company, "identity_source": "version_info",
                    "identity_confidence": "high"}
        return {"display_name": process_name, "product_name": "",
                "company_name": company,
                "identity_source": "path" if path else "unknown",
                "identity_confidence": "medium" if path else "low"}

    def _kill_process(self, name):
        # Mapear nomes conhecidos
        name_map = {
            "gerenciador de tarefas": "taskmgr.exe",
            "task manager": "taskmgr.exe",
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
            "firefox": "firefox.exe",
        }
        exe_name = name_map.get(name.lower(), name)
        if not exe_name.endswith(".exe"):
            exe_name += ".exe"
        done = subprocess.run(
            ["taskkill", "/IM", exe_name, "/F", "/T"],
            capture_output=True, timeout=10)
        if done.returncode == 0:
            return {"ok": True, "message": f"Processo '{exe_name}' encerrado."}
        return {"ok": False, "error": f"Não encontrei '{exe_name}' rodando."}

    def _is_running(self, name):
        name_map = {
            "gerenciador de tarefas": "taskmgr.exe",
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
        }
        exe_name = name_map.get(name.lower(), name)
        if not exe_name.endswith(".exe"):
            exe_name += ".exe"
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}"],
            capture_output=True, text=True, timeout=5)
        found = exe_name.lower() in result.stdout.lower()
        return {"ok": True,
                "message": f"{name.title()} {'está' if found else 'não está'} aberto.",
                "running": found}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — SISTEMA
    # ═══════════════════════════════════════════════════════════════
    def _system_status(self):
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong),
                ("avail_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended", ctypes.c_ulonglong),
            ]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))

        cpu_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor | "
             "Measure-Object LoadPercentage -Average).Average"],
            capture_output=True, text=True, timeout=8)
        cpu = int(float(cpu_result.stdout.strip() or 0))

        disk = shutil.disk_usage(Path.home().anchor)
        disk_percent = (disk.used / disk.total * 100) if disk.total else 0
        disk_free_gb = disk.free / (1024**3)

        mem_total_gb = memory.total_phys / (1024**3)
        mem_free_gb = memory.avail_phys / (1024**3)

        msg = (
            f"CPU: {cpu}% | "
            f"RAM: {memory.load}% ({mem_free_gb:.1f}GB livres de {mem_total_gb:.1f}GB) | "
            f"Disco: {disk_percent:.0f}% da capacidade ocupada ({disk_free_gb:.1f}GB livres)"
        )
        return {"ok": True, "message": msg,
                "cpu_total_now": cpu, "memory_used_percent": int(memory.load),
                "memory_free_gb": round(mem_free_gb, 1),
                "memory_total_gb": round(mem_total_gb, 1),
                "disk_capacity_used_percent": round(disk_percent, 1),
                "disk_free_gb": round(disk_free_gb, 1),
                "disk_activity_percent": None}

    def _get_time(self):
        now = time.strftime("%H:%M:%S")
        return {"ok": True, "message": f"São {now}."}

    def _get_date(self):
        import locale
        try:
            locale.setlocale(locale.LC_TIME, "pt_BR.UTF-8")
        except Exception:
            pass
        now = time.strftime("%A, %d de %B de %Y")
        return {"ok": True, "message": f"Hoje é {now}."}

    def _get_ip(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Invoke-WebRequest -Uri 'https://api.ipify.org' "
                 "-UseBasicParsing).Content"],
                capture_output=True, text=True, timeout=10)
            ip = result.stdout.strip()
            return {"ok": True, "message": f"Seu IP é {ip}."}
        except Exception:
            return {"ok": True, "message": "Não consegui obter o IP."}

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)
        return {"ok": True, "message": f"Abrindo {url} no navegador."}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — BROWSER (Playwright V1)
    # ═══════════════════════════════════════════════════════════════

    def _browser_open(self, visible=False, provider="default"):
        from .browser import get_browser_thread
        selected_provider = str(provider or "default").casefold()
        if visible and selected_provider == "default":
            selected_provider = "chrome"
        if visible and selected_provider != "chrome":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DISABLED",
                    "provider": selected_provider}
        bt = get_browser_thread(headless=not bool(visible), provider=selected_provider)
        return bt.submit("start")

    def _browser_navigate(self, url=""):
        from .browser import get_browser_thread
        return get_browser_thread().submit("navigate", url)

    def _browser_get_page_info(self):
        from .browser import get_browser_thread
        return get_browser_thread().submit("get_page_info")

    def _browser_read_page(self):
        from .browser import get_browser_thread
        return get_browser_thread().submit("read_page")

    def _browser_get_elements(self):
        from .browser import get_browser_thread
        return get_browser_thread().submit("get_elements")

    def _browser_click(self, ref="", selector="", text=""):
        from .browser import get_browser_thread
        return get_browser_thread().submit("click", ref=ref, selector=selector, text=text)

    def _browser_type(self, ref="", selector="", text="", clear=True):
        from .browser import get_browser_thread
        return get_browser_thread().submit("type_text", ref=ref, selector=selector, text=text, clear=clear)

    def _browser_search(self, query="", ref=""):
        from .browser import get_browser_thread
        return get_browser_thread().submit("search", query=query, ref=ref)

    def _browser_wait_for_navigation(self, timeout_ms=15000):
        from .browser import get_browser_thread
        return get_browser_thread().submit("wait_for_navigation", timeout_ms=timeout_ms)

    def _browser_wait_for_results(self, timeout_ms=10000):
        from .browser import get_browser_thread
        return get_browser_thread().submit("wait_for_results", timeout_ms=timeout_ms)

    def _browser_scroll(self, direction="down", amount=500):
        from .browser import get_browser_thread
        return get_browser_thread().submit("scroll", direction=direction, amount=amount)

    def _browser_back(self):
        from .browser import get_browser_thread
        return get_browser_thread().submit("go_back")

    def _browser_forward(self):
        from .browser import get_browser_thread
        return get_browser_thread().submit("go_forward")

    def _browser_screenshot(self, full_page=False):
        from .browser import get_browser_thread
        return get_browser_thread().submit("screenshot", full_page=full_page)

    def _browser_close(self):
        from .browser import get_browser_thread
        bt = get_browser_thread()
        result = bt.submit("stop")
        bt.stop()
        return result

    def _browser_health(self):
        from .browser import get_browser_thread
        return get_browser_thread().submit("health")

    def _browser_record_window(self, pid=0, window_id=0):
        from .browser import get_browser_thread
        return get_browser_thread().submit("record_window_identity", process_id=pid,
                                           window_id=window_id)

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — SCREENSHOT
    # ═══════════════════════════════════════════════════════════════
    def _take_screenshot(self):
        from PIL import ImageGrab
        folder = Path.home() / "Pictures" / "Golden Jarvis"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("captura_%Y%m%d_%H%M%S.png")
        ImageGrab.grab(all_screens=True).save(path)
        return {"ok": True, "message": f"Captura salva em {path}",
                "path": str(path)}

    def _take_screenshot_window(self, window):
        from PIL import ImageGrab
        folder = Path.home() / "Pictures" / "Golden Jarvis"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("captura_%Y%m%d_%H%M%S.png")
        # Capturar tela inteira (simplificado)
        ImageGrab.grab(all_screens=True).save(path)
        return {"ok": True, "message": f"Captura de '{window}' salva em {path}",
                "path": str(path)}

    def _analyze_screen(self, question=""):
        """Analisa a tela com o modelo visual (qwen2.5vl)."""
        try:
            from .vision import get_vision
            vision = get_vision()
            result = vision.analyze_screen(question or "")
            if result.get("ok"):
                return {"ok": True, "message": result.get("analysis", ""),
                        "screenshot": result.get("screenshot_path", "")}
            return result
        except Exception as e:
            return {"ok": False, "error": f"Erro na analise visual: {e}"}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — VOLUME (via PowerShell)
    # ═══════════════════════════════════════════════════════════════
    def _volume_up(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$obj = New-Object -ComObject WScript.Shell; "
             "1..5 | ForEach-Object { $obj.SendKeys([char]175) }"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Volume aumentado."}

    def _volume_down(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$obj = New-Object -ComObject WScript.Shell; "
             "1..5 | ForEach-Object { $obj.SendKeys([char]174) }"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Volume diminuído."}

    def _volume_mute(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$obj = New-Object -ComObject WScript.Shell; "
             "$obj.SendKeys([char]173)"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Áudio silenciado."}

    def _volume_set(self, level):
        level = max(0, min(100, level))
        # Usar nircmd ou powershell
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$wshShell = New-Object -ComObject WScript.Shell; "
             f"1..50 | ForEach-Object {{ $wshShell.SendKeys([char]174) }}; "
             f"1..{level // 2} | ForEach-Object {{ $wshShell.SendKeys([char]175) }}"],
            capture_output=True, timeout=10)
        return {"ok": True, "message": f"Volume definido para {level}%."}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — WINDOWS
    # ═══════════════════════════════════════════════════════════════
    def _lock(self):
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return {"ok": True, "message": "Sessão do Windows bloqueada."}

    def _shutdown(self):
        subprocess.Popen(["shutdown", "/s", "/t", "30",
                          "/c", "Solicitado pelo Golden Jarvis"])
        return {"ok": True, "message": "Desligamento agendado para 30 segundos."}

    def _restart(self):
        subprocess.Popen(["shutdown", "/r", "/t", "30",
                          "/c", "Solicitado pelo Golden Jarvis"])
        return {"ok": True, "message": "Reinício agendado para 30 segundos."}

    def _minimize_all(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('^{ESC}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Todas as janelas minimizadas."}

    def _show_desktop(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('^{d}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Área de trabalho exibida."}

    def _open_action_center(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('^{a}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Centro de Ações aberto."}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — ARQUIVOS
    # ═══════════════════════════════════════════════════════════════
    def _copy_file(self, source, dest):
        s = Path(source)
        if not s.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {source}"}
        d = Path(dest)
        if s.is_dir():
            shutil.copytree(str(s), str(d))
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(s), str(d))
        return {"ok": True, "message": f"Copiado: {s.name} → {d}"}

    def _move_file(self, source, dest):
        s = Path(source)
        if not s.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {source}"}
        d = Path(dest)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return {"ok": True, "message": f"Movido: {s.name} → {d}"}

    def _rename_file(self, source, new_name):
        s = Path(source)
        if not s.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {source}"}
        d = s.parent / new_name
        s.rename(d)
        return {"ok": True, "message": f"Renomeado: {s.name} → {d.name}"}

    def _delete_file(self, path):
        target = Path(path).resolve()
        if not target.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {path}"}
        if target.is_dir():
            return {"ok": False, "error": "delete_file não exclui pastas. Use uma ferramenta específica."}
        target.unlink()
        return {"ok": True, "message": f"Excluído: {target.name}"}

    def _create_folder(self, path):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "message": f"Pasta criada: {target}"}

    def _list_folder(self, path):
        target = Path(path)
        if not target.exists():
            return {"ok": False, "error": f"Pasta não encontrada: {path}"}
        if not target.is_dir():
            return {"ok": False, "error": f"Não é uma pasta: {path}"}
        items = []
        for item in sorted(target.iterdir()):
            tipo = "📁" if item.is_dir() else "📄"
            tamanho = ""
            if item.is_file():
                size = item.stat().st_size
                if size > 1024*1024:
                    tamanho = f" ({size//1024//1024}MB)"
                elif size > 1024:
                    tamanho = f" ({size//1024}KB)"
            items.append(f"  {tipo} {item.name}{tamanho}")
        msg = f"Conteúdo de {target.name} ({len(items)} itens):\n" + "\n".join(items[:25])
        return {"ok": True, "message": msg, "count": len(items)}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — LIXEIRA
    # ═══════════════════════════════════════════════════════════════
    def _recycle_bin_status(self):
        """Consulta a lixeira sem excluir nada. Somente leitura."""
        try:
            import subprocess
            # PowerShell: lista itens da lixeira via COM Object
            ps_script = (
                '$shell = New-Object -ComObject Shell.Application; '
                '$folder = $shell.Namespace(0x0A); '
                '$items = $folder.Items(); '
                '$count = $items.Count; '
                '$size = 0; '
                'foreach ($item in $items) { $size += $folder.GetDetailsOf($item, 2) -replace "[^0-9]","" -as [long] }; '
                'Write-Output "$count|$size"'
            )
            result = subprocess.run(
                ['powershell', '-Command', ps_script],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if "|" in output:
                parts = output.split("|")
                count = int(parts[0]) if parts[0].isdigit() else 0
                # Size from PowerShell GetDetailsOf is unreliable, use alternative
                size_str = parts[1] if len(parts) > 1 else "0"
            else:
                count = 0
                size_str = "0"

            # Alternative: use dir command on recycle bin folder
            rb_path = Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "INetCache"
            # More reliable: use PowerShell to get actual recycle bin info
            ps_reliable = (
                '$rb = (New-Object -ComObject Shell.Application).Namespace(0x0A); '
                '$count = $rb.Items().Count; '
                '$totalSize = 0; '
                'foreach ($item in $rb.Items()) { '
                '  $totalSize += (Get-Item $item.Path -ErrorAction SilentlyContinue).Length '
                '}; '
                'Write-Output "$count|$totalSize"'
            )
            result2 = subprocess.run(
                ['powershell', '-Command', ps_reliable],
                capture_output=True, text=True, timeout=10
            )
            output2 = result2.stdout.strip()
            if "|" in output2:
                parts2 = output2.split("|")
                count = int(parts2[0]) if parts2[0].isdigit() else 0
                total_size = int(parts2[1]) if parts2[1].isdigit() else 0
            else:
                total_size = 0

            if count == 0:
                msg = "Lixeira vazia."
            else:
                if total_size > 1024 * 1024 * 1024:
                    size_msg = f"{total_size / (1024**3):.1f} GB"
                elif total_size > 1024 * 1024:
                    size_msg = f"{total_size / (1024**2):.1f} MB"
                elif total_size > 1024:
                    size_msg = f"{total_size / 1024:.1f} KB"
                else:
                    size_msg = f"{total_size} bytes"
                msg = f"Lixeira contém {count} item(s), total aproximado: {size_msg}."

            return {"ok": True, "message": msg, "count": count, "size_bytes": total_size}
        except Exception as e:
            return {"ok": False, "error": f"Erro ao consultar lixeira: {str(e)}"}

    def _empty_recycle_bin(self):
        """Esvazia a lixeira do Windows. Ação IRREVERSÍVEL.
        Requer confirmação do SecurityManager (Risk.CRITICAL).
        """
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-Command', 'Clear-RecycleBin -Force -ErrorAction Stop'],
                capture_output=True, text=True, timeout=15
            )
            return {"ok": True, "message": "Lixeira esvaziada com sucesso."}
        except subprocess.CalledProcessError:
            # Lixeira já vazia ou erro
            return {"ok": True, "message": "Lixeira esvaziada (ou já estava vazia)."}
        except Exception as e:
            return {"ok": False, "error": f"Erro ao esvaziar lixeira: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — INFO DO SISTEMA
    # ═══════════════════════════════════════════════════════════════
    def _get_username(self):
        import getpass
        user = getpass.getuser()
        return {"ok": True, "message": f"Usuário: {user}"}

    def _get_active_window(self):
        try:
            import ctypes.wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            return {"ok": True, "message": f"Janela ativa: {title or 'Sem título'}"}
        except Exception as e:
            return {"ok": False, "error": f"Não consegui obter janela ativa: {e}"}

    def _get_battery(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus | ConvertTo-Json"],
                capture_output=True, text=True, timeout=8)
            import json
            data = json.loads(result.stdout or "{}")
            if isinstance(data, dict) and data:
                level = data.get("EstimatedChargeRemaining", "?")
                status = "carregando" if data.get("BatteryStatus") == 2 else "bateria"
                return {"ok": True, "message": f"Bateria: {level}% ({status})"}
            return {"ok": True, "message": "Desktop sem bateria (conectado à rede)."}
        except Exception:
            return {"ok": True, "message": "Não consegui obter status da bateria."}

    def _get_network(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
                 "Select-Object Name, InterfaceDescription, LinkSpeed | ConvertTo-Json"],
                capture_output=True, text=True, timeout=8)
            import json
            adapters = json.loads(result.stdout or "[]")
            if isinstance(adapters, dict):
                adapters = [adapters]
            if not adapters:
                return {"ok": True, "message": "Nenhuma conexão de rede ativa."}
            lines = []
            for a in adapters:
                name = a.get("Name", "?")
                speed = a.get("LinkSpeed", "?")
                desc = a.get("InterfaceDescription", "")
                lines.append(f"  • {name}: {speed} ({desc})")
            return {"ok": True, "message": "Redes ativas:\n" + "\n".join(lines)}
        except Exception:
            return {"ok": True, "message": "Não consegui obter informações de rede."}

    def _get_recent_files(self):
        recent = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Recent"
        if not recent.exists():
            return {"ok": True, "message": "Pasta de recentes não encontrada."}
        files = []
        for item in sorted(recent.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if len(files) >= 15:
                break
            if item.is_file():
                files.append(f"  • {item.stem}")
        if not files:
            return {"ok": True, "message": "Nenhum arquivo recente encontrado."}
        return {"ok": True, "message": "Arquivos recentes:\n" + "\n".join(files)}

    # ═══════════════════════════════════════════════════════════════
    # HANDLERS — CONTROLE DE JANELAS
    # ═══════════════════════════════════════════════════════════════
    def _close_active_window(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('%{F4}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Janela ativa fechada."}

    def _maximize_window(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('^{UP}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Janela maximizada."}

    def _minimize_window(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('%{DOWN}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Janela minimizada."}

    def _switch_window(self):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wsh = New-Object -ComObject WScript.Shell; "
             "$wsh.SendKeys('%{TAB}')"],
            capture_output=True, timeout=5)
        return {"ok": True, "message": "Alternando janela..."}
