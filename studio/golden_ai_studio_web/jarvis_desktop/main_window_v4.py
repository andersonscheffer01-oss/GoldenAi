"""MainWindow V4: Golden Jarvis Desktop — Dois modos (CONVERSA / CONTROLE) integrados.

Fase 1: Fundação visual apenas. Não altera backend, Brain, Memory, M1.4, providers,
STT/TTS, VoiceService, ToolRegistry, SecurityManager, Radar, MT5, trading.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow, QMenu,
                                QSizeGrip, QStackedWidget, QSystemTrayIcon,
                                QVBoxLayout, QWidget)

from .api_client import JarvisApiClient
from .gpu import get_gpu_info
from .state import JarvisState, hud_for_voice
from .status_format import mt5_display
from .workers import ApiWorker, Dispatcher, new_token
from .widgets.title_bar_v4 import TitleBarV4
from .widgets.mode_switcher import ModeSwitcher
from .views.conversa_view import ConversaView
from .views.controle_view import ControleView
from .views.config_view import ConfigView
from .views.dev_view import DevView
from .views.ops_view import OpsView
from .views.skills_view import SkillsView
from .views.tasks_view import TasksView

from .theme_v4 import apply_theme_v4, CYAN, GOLD, BAD, GOOD, TEXT_MUTED


FRIENDLY_ERRORS = (("rate limit", "Provider principal indisponível (rate limit). Usando fallback."),
                   ("429", "Provider principal indisponível (rate limit). Usando fallback."),
                   ("excedeu o limite", "O modelo local demorou a responder (Ollama frio/sobrecarregado). Tente novamente."),
                   ("timeout", "O modelo local demorou a responder. Tente novamente."),
                   ("503", "Provider indisponível. Usando fallback."))


def friendly_error(text):
    low = str(text).lower()
    for needle, msg in FRIENDLY_ERRORS:
        if needle in low:
            return msg
    return f"Erro: {text}"


class MainWindowV4(QMainWindow):
    def __init__(self, client=None, start_minimized=False):
        super().__init__()
        self.client = client or JarvisApiClient()
        self.state = JarvisState()
        self.pool = QThreadPool.globalInstance()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowTitle("Golden Jarvis V4")
        self.resize(1450, 900)
        self.setMinimumSize(1150, 720)

        # Apply V4 theme
        apply_theme_v4(QApplication.instance())

        # Root widget with backdrop
        root = QWidget()
        root.setObjectName("rootV4")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)

        # Title Bar V4
        self.titlebar = TitleBarV4(self)
        self.titlebar.retryRequested.connect(self.refresh_all)
        layout.addWidget(self.titlebar)

        # Mode Switcher
        self.mode_switcher = ModeSwitcher()
        self.mode_switcher.modeChanged.connect(self._on_mode_changed)
        self.titlebar.set_mode_switcher(self.mode_switcher)

        # Central Stack (CONVERSA / CONTROLE)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # CONVERSA View
        self.conversa_view = ConversaView(
            on_send=self.send_chat,
            on_voice_toggle=self.toggle_voice
        )
        self.stack.addWidget(self.conversa_view)

        # CONTROLE View
        self.controle_view = ControleView(
            on_manual_command=self._on_manual_command
        )
        self.stack.addWidget(self.controle_view)

        # Existing tabs (preserved, accessible via keyboard shortcuts or menu)
        self._setup_legacy_tabs()

        # Voice mirroring state
        self._voice_baseline = False
        self._seen_event_id = 0
        self._chat_in_flight = False

        # CONTROLE real data cache
        self._controle_providers = {}
        self._controle_skills = []
        self._controle_radar = {}
        self._real_projects = []

        # Offline label
        self.offline_label = QWidget()
        self.offline_label.setVisible(False)

        # System tray
        self._tray()
        self._timers()

        # Start in CONVERSA mode
        self._current_mode = "conversa"
        self.stack.setCurrentWidget(self.conversa_view)

        self.refresh_all()
        if start_minimized:
            self.hide()

    def _setup_legacy_tabs(self):
        """Configura abas legadas (mantidas para compatibilidade)."""
        # Estas não estão no stack principal, mas podem ser acessadas via atalhos
        self.tasks_view = TasksView({"refresh": self.refresh_tasks,
                                     "detail": self.task_detail,
                                     "cancel": self.task_cancel})
        self.radar_view = OpsView("radar")
        self.mt5_view = OpsView("mt5")
        self.skills_view = SkillsView()
        self.config_view = ConfigView({"voice": self.set_voice_enabled,
                                       "dev": self.set_dev_mode,
                                       "tray": self.set_tray_mode,
                                       "min_start": lambda v: None})
        self.dev_view = DevView()

    def _on_mode_changed(self, mode: str):
        """Handler para troca de modo."""
        self._current_mode = mode
        if mode == "conversa":
            self.stack.setCurrentWidget(self.conversa_view)
            self.titlebar.set_mode_label("SHADOW MODE")
        else:
            self.stack.setCurrentWidget(self.controle_view)
            self.titlebar.set_mode_label("CONTROL MODE")

    # ===== Window Controls (TitleBar signals) =====

    def request_close(self):
        """X da title bar: bandeja (se ativo) ou sair. Nunca mata o backend."""
        if self.state.minimize_to_tray:
            self.hide()
        else:
            self._quit()

    def closeEvent(self, event):
        if self.state.minimize_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()

    # ===== Infrastructure =====

    def _run(self, fn, slot, *args, **kwargs):
        if not hasattr(self, "_dispatcher"):
            self._dispatcher = Dispatcher(self)
            self._dispatcher.finished.connect(self._on_worker_done)
            self._pending_workers = {}
        token = new_token()
        worker = ApiWorker(fn, self._dispatcher, token, *args, **kwargs)
        self._pending_workers[token] = (worker, slot)
        self.pool.start(worker)

    def _on_worker_done(self, token, result):
        item = self._pending_workers.pop(token, None)
        if item is not None:
            _, slot = item
            slot(result)

    def _every(self, fn, ms):
        timer = QTimer(self)
        timer.timeout.connect(fn)
        timer.start(ms)
        if not hasattr(self, "_timers_ref"):
            self._timers_ref = []
        self._timers_ref.append(timer)

    def _timers(self):
        self._every(lambda: self._run(self.client.get_status, self.on_status), 5000)
        self._every(lambda: self._run(self.client.voice_status, self.on_voice), 2000)
        self._every(lambda: self._run(self.client.tasks_list, self.on_tasks), 7000)
        self._every(lambda: self._run(get_gpu_info, self.on_gpu), 30000)
        self._every(self.refresh_slow, 15000)
        self._every(lambda: self._run(self.client.radar_status, self.on_radar), 20000)
        self._every(lambda: self._run(self.client.projects, self.on_projects), 30000)
        self._every(self._refresh_controle, 15000)

    def _tray(self):
        self.tray = QSystemTrayIcon(self)
        menu = QMenu()
        for label, fn in (("Abrir Jarvis", self.showNormal),
                          ("Alternar Voz", self.toggle_voice),
                          ("Alternar Modo", self._toggle_mode),
                          ("Status", self.refresh_all),
                          ("Sair", self._quit)):
            action = QAction(label, self)
            action.triggered.connect(fn)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        try:
            self.tray.show()
        except Exception:
            pass

    def _quit(self):
        try:
            self.tray.hide()
        except Exception:
            pass
        self.close()

    def _toggle_mode(self):
        new_mode = "controle" if self._current_mode == "conversa" else "conversa"
        self.mode_switcher.set_mode(new_mode)

    # ===== Polling =====

    def refresh_all(self):
        self._run(self.client.get_status, self.on_status)
        self._run(self.client.voice_status, self.on_voice)
        self._run(get_gpu_info, self.on_gpu)
        self.refresh_tasks()
        self.refresh_slow()
        self._run(self.client.radar_status, self.on_radar)
        self._run(self.client.projects, self.on_projects)
        self._refresh_controle()

    def refresh_slow(self):
        self._run(self.client.orchestrator_status, self.on_orch)
        self._run(self.client.skills_status, self.on_skills)
        self._run(self.client.providers_status, self.on_providers)
        self._run(self.client.capabilities, self.on_caps)
        self._run(self.client.brain_status, self.on_brain)

    def _refresh_controle(self):
        """Atualiza dados reais do modo CONTROLE."""
        self._run(self.client.orchestrator_status, self._on_controle_update)
        self._run(self.client.skills_status, self._on_controle_skills)
        self._run(self.client.providers_status, self._on_controle_providers)
        self._run(self.client.radar_status, self._on_controle_radar)

    # ===== Callbacks =====

    def on_status(self, data):
        self.state.apply_status(data if isinstance(data, dict) else {})
        online = self.state.backend_online
        self.titlebar.set_online(online)
        self.titlebar.set_retry_visible(not online)
        self.offline_label.setVisible(not online)
        if not online:
            self.state.set_jarvis("OFFLINE")
        elif self.state.jarvis == "OFFLINE":
            self.state.set_jarvis("ONLINE")

        # Update CONVERSA view HUD
        self.conversa_view.set_animation_state(self.state.jarvis)

        # Update status footer with real data
        footer = self.conversa_view.get_status_footer()
        footer.update_system(self.state.status)
        footer.update_services(self.state.status, self.state.voice, self.state.radar)

        # MT5 view
        self.mt5_view.render_mt5(mt5_display(self.state.status))

        self._render_config()

    def on_radar(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.radar = data
            self.radar_view.render_radar(data)
            footer = self.conversa_view.get_status_footer()
            footer.update_services(self.state.status, self.state.voice, self.state.radar)
            self._controle_radar = data
        self._update_controle_agents()

    def on_gpu(self, data):
        if isinstance(data, dict):
            self.state.gpu = data
            footer = self.conversa_view.get_status_footer()
            footer.update_system(self.state.status)  # GPU está no status

    def on_voice(self, data):
        self.state.voice = data if isinstance(data, dict) else {}
        data = self.state.voice
        listening = False
        if self.state.backend_online and data.get("ok"):
            hud_state = hud_for_voice(data.get("state", ""))
            v_running = bool(data.get("running"))
            listening = hud_state == "OUVINDO" or (v_running and hud_state in ("TRANSCRIBINDO", "PROCESSANDO", "FALANDO"))

            # HUD reflete a voz, exceto durante voo de chat digitado
            if not self._chat_in_flight and hud_state:
                if hud_state == "OFFLINE":
                    if self.state.jarvis in ("ONLINE", "AGUARDANDO", "OUVINDO", "OFFLINE"):
                        self.state.set_jarvis("OFFLINE")
                else:
                    self.state.set_jarvis(hud_state)

                # Update CONVERSA animation
                interim = ""
                if hud_state in ("TRANSCRIBINDO", "PROCESSANDO", "FALANDO"):
                    interim = str(data.get("last_heard") or "")
                self.conversa_view.set_animation_state(self.state.jarvis)
                # Simular voice level para preview
                if hud_state in ("OUVINDO", "TRANSCRIBINDO"):
                    self.conversa_view.start_voice_simulation()
                else:
                    self.conversa_view.stop_voice_simulation()
            elif not self._chat_in_flight:
                self.conversa_view.set_animation_state(self.state.jarvis)

        self.conversa_view.set_mic_state(listening and self.state.voice_enabled)
        self._mirror_voice(data)

    def _mirror_voice(self, data):
        event = data.get("last_event") if isinstance(data, dict) else {}
        if not isinstance(event, dict) or not event.get("id"):
            if not self._voice_baseline:
                self._voice_baseline = True
            return
        if not self._voice_baseline:
            self._seen_event_id = int(event["id"])
            self._voice_baseline = True
            return
        try:
            eid = int(event.get("id", 0))
        except (TypeError, ValueError):
            return
        if eid <= self._seen_event_id:
            return
        self._seen_event_id = eid
        heard = str(event.get("heard") or "").strip()
        resp = str(event.get("response") or "").strip()
        if not heard and not resp:
            return
        if heard:
            self.conversa_view.add_user_message(f"🎤 {heard}")
        if resp:
            self.conversa_view.add_jarvis_message(resp)
        self.state.last_route = str(event.get("route") or "") or self.state.last_route
        self.state.last_skill = str(event.get("skill") or "") or self.state.last_skill
        try:
            self.state.last_conf = str(float(event.get("confidence", 0)) or "")
        except (TypeError, ValueError):
            pass
        if event.get("tool_provider"):
            self.state.last_provider = str(event["tool_provider"])
        timings = event.get("timings") or {}
        self.state.last_llm = {"provider": str(event.get("tool_provider") or ""),
                               "model": "", "profile": "",
                               "fallback": False,
                               "latency_ms": timings.get("execution_ms", "--"),
                               "voice_timings": timings}
        self.state.last_voice_timings = timings
        self._render_route()

    def on_brain(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.brain = data
        self._render_dev()

    def on_tasks(self, data):
        tasks = (data or {}).get("tasks", []) if isinstance(data, dict) else []
        self.state.tasks = tasks
        self.tasks_view.set_tasks(tasks)
        # Update footer task matrix
        footer = self.conversa_view.get_status_footer()
        footer.update_providers(getattr(self, "_providers", {}), tasks)

    def on_orch(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.orchestrator = data
            self._render_route()
        self._render_dev()
        self._update_controle_agents()

    def on_skills(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.skills = data.get("skills", [])
            self.skills_view.render(data)
            self._controle_skills = data.get("skills", [])
        self._update_controle_agents()

    def on_providers(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._providers = data
            self.state.providers = data
            footer = self.conversa_view.get_status_footer()
            footer.update_providers(data, self.state.tasks)
            self._render_route()
            self._controle_providers = data
        self._render_dev()
        self._update_controle_agents()

    def on_caps(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._caps = data
        self._render_config()

    def on_projects(self, data):
        """Callback para projetos reais."""
        if isinstance(data, dict) and data.get("ok"):
            projects = data.get("projects", [])
            self.controle_view.set_projects(projects)
            self._real_projects = projects

    def _on_controle_update(self, data):
        """Callback para dados reais do CONTROLE — providers + orch + skills + radar."""
        self._update_controle_agents()

    def _on_controle_skills(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._controle_skills = data.get("skills", [])
        self._update_controle_agents()

    def _on_controle_providers(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._controle_providers = data
        self._update_controle_agents()

    def _on_controle_radar(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._controle_radar = data
        self._update_controle_agents()

    def _update_controle_agents(self):
        """Reconstroi agentes reais no CONTROLE com dados de providers/skills/orch/radar."""
        providers = getattr(self, "_controle_providers", {})
        skills = getattr(self, "_controle_skills", [])
        orch = getattr(self, "state", None)
        orch_data = orch.orchestrator if orch else {}
        radar = getattr(self, "_controle_radar", {})
        self.controle_view.set_agents_from_providers(providers, skills, orch_data, radar)

    def _render_route(self):
        last = (self.state.orchestrator or {}).get("last_decision") or {}
        prim = (getattr(self, "_providers", {}) or {}).get("primary") or {}
        dev_extra = ""
        if self.state.dev_mode:
            dev_extra = (f"SKILL {last.get('skill', '--')} · PROV {prim.get('actual_provider', '--')} · "
                         f"PROF {last.get('model_profile', '--')} · FB {prim.get('fallback', '--')} · "
                         f"TOOLS {last.get('tool_count', '--')}")
        self.conversa_view.set_chat_meta(
            last.get("route", self.state.last_route) or self.state.last_route,
            self.state.last_brain, str(last.get("confidence", self.state.last_conf)),
            last.get("skill", self.state.last_skill),
            self.state.last_provider, dev_extra, self.state.last_llm
        )

    def _render_dev(self):
        self.dev_view.render(self.state.orchestrator, getattr(self, "_providers", {}),
                             self.state.brain, self.state.tasks, self.state.voice)

    def _render_config(self):
        self.config_view.render_info(self.client.base_url, getattr(self, "_caps", {}))

    # ===== Chat (typed) =====

    def send_chat(self, text):
        self.submit_message(text, source="typed")

    def submit_message(self, text, source="typed"):
        text = str(text or "").strip()
        if not text:
            return
        self.stack.setCurrentWidget(self.conversa_view)
        self.mode_switcher.set_mode("conversa")
        self.conversa_view.add_user_message(text)
        if not self.state.backend_online:
            self.state.set_jarvis("ERRO")
            self.conversa_view.set_animation_state("ERROR")
            self.conversa_view.add_jarvis_message("Golden Backend indisponível. Clique em TENTAR NOVAMENTE.")
            return
        self.state.set_jarvis("PROCESSANDO")
        self.conversa_view.set_animation_state("PROCESSING")
        self.conversa_view.add_jarvis_message("Recebi. Estou processando.")
        self._chat_in_flight = True
        self._run(self.client.chat, lambda r: self.on_chat_result(r, text), text)

    def on_chat_result(self, result, text):
        result = result if isinstance(result, dict) else {}
        self._chat_in_flight = False
        if result.get("offline"):
            self.state.set_jarvis("ERRO")
            self.conversa_view.set_animation_state("ERROR")
            self.conversa_view.add_jarvis_message("Golden Backend indisponível. Clique em TENTAR NOVAMENTE.")
        elif result.get("ok"):
            tool = result.get("tool", "")
            shadow = result.get("shadow_task") or {}
            self.state.last_brain = result.get("model", "")
            self.state.last_route = result.get("route", "") or tool or self.state.last_route
            self.state.last_skill = result.get("skill", "") or self.state.last_skill
            self.state.last_conf = str(result.get("confidence", "") or "")
            self.state.last_provider = (result.get("tool_provider", "")
                                        or self.state.last_provider)
            llm = result.get("llm") if isinstance(result.get("llm"), dict) else {}
            if llm:
                self.state.last_llm = llm
                if not self.state.last_provider:
                    self.state.last_provider = str(llm.get("provider", ""))
            self.conversa_view.add_jarvis_message(result.get("response", "."))
            self._render_route()
            if shadow.get("task_id"):
                self.conversa_view.add_jarvis_message(f"(Plano validado em SHADOW · task {shadow.get('task_id')} · sem execução)")
            self.state.set_jarvis("CONCLUÍDO")
            self.conversa_view.set_animation_state("IDLE")
            self.refresh_tasks()
            self._run(self.client.orchestrator_status, self.on_orch)
            self._run(self.client.providers_status, self.on_providers)
        else:
            if result.get("approval_required") or "confirm" in str(result.get("error", "")).lower():
                self.state.set_jarvis("AGUARDANDO CONFIRMAÇÃO")
                self.conversa_view.set_animation_state("IDLE")
                self.conversa_view.add_jarvis_message(f"Aguardando confirmação: {result.get('error') or result}")
            elif "esclarec" in str(result.get("response", "") + result.get("error", "")).lower() or (result.get("tool", "") in ("", "none")):
                self.state.set_jarvis("CONCLUÍDO")
                self.conversa_view.set_animation_state("IDLE")
                self.conversa_view.add_jarvis_message(result.get("response") or result.get("error") or "Preciso de mais contexto.")
            else:
                self.state.set_jarvis("ERRO")
                self.conversa_view.set_animation_state("ERROR")
                detail = str(result.get("error", "falha"))
                msg = friendly_error(detail)
                if self.state.dev_mode:
                    msg += f"\n[DEV] {detail[:300]}"
                self.conversa_view.add_jarvis_message(msg)

    # ===== Config switches =====

    def set_voice_enabled(self, enabled):
        self.state.voice_enabled = bool(enabled)
        fn = self.client.voice_start if enabled else self.client.voice_stop
        self._run(fn, self.on_voice)

    def toggle_voice(self):
        self.set_voice_enabled(not self.state.voice_enabled)
        self.config_view.voice.setChecked(self.state.voice_enabled)

    def set_dev_mode(self, enabled):
        self.state.dev_mode = bool(enabled)
        self.conversa_view.get_chat_widget().set_dev(enabled)
        self._render_route()
        if enabled:
            self.dev_view.show()

    def set_tray_mode(self, enabled):
        self.state.minimize_to_tray = bool(enabled)

    # ===== Tasks =====

    def refresh_tasks(self):
        self._run(self.client.tasks_list, self.on_tasks)

    def task_detail(self, task_id):
        if task_id:
            self._run(self.client.tasks_get, self.tasks_view.set_detail, task_id)

    def task_cancel(self, task_id):
        if task_id:
            self._run(self.client.tasks_cancel, lambda _r: self.refresh_tasks())

    # ===== Manual Command (CONTROLE mode) =====

    def _on_manual_command(self, command: str):
        """Processa comando manual do modo CONTROLE."""
        # Por enquanto, envia para o chat (pode ser expandido para roteamento específico)
        self.send_chat(command)

    # ===== Drag & Drop =====

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        names = ""
        if event.mimeData().hasUrls():
            names = ", ".join(u.toLocalFile() or u.toString() for u in event.mimeData().urls())
        elif event.mimeData().hasText():
            names = event.mimeData().text()[:200]
        self.stack.setCurrentWidget(self.conversa_view)
        self.conversa_view.add_jarvis_message(
            f"Recebido: {names or 'conteúdo'}. Ingestão de anexos ainda não implementada "
            "no backend — arraste preparada, execução pendente.")
        event.acceptProposedAction()


def main(argv=None):
    """Entry point para V4."""
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Golden Jarvis V4")
    app.setQuitOnLastWindowClosed(False)
    apply_theme_v4(app)
    base = os.environ.get("GOLDEN_BACKEND_URL", "http://127.0.0.1:8765")
    window = MainWindowV4(JarvisApiClient(base))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())