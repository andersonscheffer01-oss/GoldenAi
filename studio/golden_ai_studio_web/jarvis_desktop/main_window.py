"""Janela V3: frameless + title bar propria + backdrop + HUD protagonista."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QSizeGrip,
                               QSystemTrayIcon, QMenu, QTabWidget, QVBoxLayout,
                               QWidget)

from .api_client import JarvisApiClient
from .gpu import get_gpu_info
from .state import JarvisState, hud_for_voice
from .status_format import mt5_display
from .workers import ApiWorker, Dispatcher, new_token
from .widgets.backdrop import Backdrop
from .widgets.chat_view import ChatWidget
from .widgets.hud import HudWidget
from .widgets.status_panels import ProvidersPanel, SystemPanel
from .widgets.title_bar import TitleBar
from .views.config_view import ConfigView
from .views.dev_view import DevView
from .views.ops_view import OpsView
from .views.skills_view import SkillsView
from .views.tasks_view import TasksView

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


def _norm(text):
    """Normaliza para deduplicacao (caixa/espacos), sem alterar o original."""
    return " ".join(str(text).split()).casefold()


class MainWindow(QMainWindow):
    def __init__(self, client=None, start_minimized=False):
        super().__init__()
        self.client = client or JarvisApiClient()
        self.state = JarvisState()
        self.pool = QThreadPool.globalInstance()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowTitle("Golden Jarvis")
        self.resize(1450, 880)
        self.setMinimumSize(1150, 720)

        root = Backdrop()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 6, 10, 6)

        self.titlebar = TitleBar(self)
        self.titlebar.retry.clicked.connect(lambda: self.refresh_all())
        layout.addWidget(self.titlebar)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        self.sys_panel = SystemPanel()
        self.sys_panel.setFixedWidth(250)
        self.hud = HudWidget()
        self.prov_panel = ProvidersPanel()
        self.prov_panel.setFixedWidth(250)
        center = QVBoxLayout()
        center.setSpacing(4)
        center.addWidget(self.hud)
        link = QLabel("SYS ◄── CORE ──► NET")
        link.setProperty("class", "tag")
        link.setAlignment(Qt.AlignCenter)
        center.addWidget(link)
        self.tabs = QTabWidget()
        self.chat = ChatWidget(on_send=self.send_chat, on_voice_toggle=self.toggle_voice)
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
        for name, widget in (("CHAT", self.chat), ("TASKS", self.tasks_view),
                             ("RADAR", self.radar_view), ("MT5", self.mt5_view),
                             ("SKILLS", self.skills_view), ("CONFIG", self.config_view),
                             ("DEV", self.dev_view)):
            self.tabs.addTab(widget, name)
        center.addWidget(self.tabs, 1)
        mid.addWidget(self.sys_panel)
        mid.addLayout(center, 1)
        mid.addWidget(self.prov_panel)
        layout.addLayout(mid, 1)

        # Espelho de voz por evento (id): o VoiceService executa sozinho;
        # o Desktop apenas reflete (NUNCA reenvia -> sem dupla execucao).
        # So vira conversa o que GEROU resposta (comando executado ou erro).
        self._voice_baseline = False
        self._seen_event_id = 0
        self._chat_in_flight = False

        bottom = QHBoxLayout()
        self.offline_label = QLabel("Golden Backend indisponível — porta 8765.")
        self.offline_label.setProperty("class", "muted")
        self.offline_label.setVisible(False)
        bottom.addWidget(self.offline_label)
        bottom.addStretch(1)
        bottom.addWidget(QSizeGrip(self))
        layout.addLayout(bottom)

        self._tray()
        self._timers()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.refresh_all()
        if start_minimized:
            self.hide()

    def _on_tab_changed(self, _index):
        # Foco vai para o input sempre que o CHAT fica visivel.
        if self.tabs.currentWidget() is self.chat:
            self.chat.input.setFocus()

    def showEvent(self, event):  # noqa: N802 - assinatura Qt
        super().showEvent(event)
        self.chat.input.setFocus()

    # -- infra --
    def _run(self, fn, slot, *args, **kwargs):
        # Dispatcher permanente + retencao por token: o worker nunca emite
        # sinal proprio, entao a resposta sempre chega (sem GCquat/roubo).
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

    def _tray(self):
        self.tray = QSystemTrayIcon(self)
        menu = QMenu()
        for label, fn in (("Abrir Jarvis", self.showNormal),
                          ("Ativar/Desativar Voz", self.toggle_voice),
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

    def request_close(self):
        """X da title bar: bandeja (se ativo) ou sair. Nunca mata o backend."""
        if self.state.minimize_to_tray:
            self.hide()
        else:
            self._quit()

    def closeEvent(self, event):  # noqa: N802 - assinatura Qt
        if self.state.minimize_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()

    # -- polling (leve; sem LLM; sem provider por frame) --
    def refresh_all(self):
        self._run(self.client.get_status, self.on_status)
        self._run(self.client.voice_status, self.on_voice)
        self._run(get_gpu_info, self.on_gpu)
        self.refresh_tasks()
        self.refresh_slow()
        self._run(self.client.radar_status, self.on_radar)

    def refresh_slow(self):
        self._run(self.client.orchestrator_status, self.on_orch)
        self._run(self.client.skills_status, self.on_skills)
        self._run(self.client.providers_status, self.on_providers)
        self._run(self.client.capabilities, self.on_caps)
        self._run(self.client.brain_status, self.on_brain)

    def on_status(self, data):
        self.state.apply_status(data if isinstance(data, dict) else {})
        online = self.state.backend_online
        self.titlebar.set_online(online)
        self.titlebar.retry.setVisible(not online)
        self.offline_label.setVisible(not online)
        if not online:
            self.state.set_jarvis("OFFLINE")
        elif self.state.jarvis == "OFFLINE":
            self.state.set_jarvis("ONLINE")
        self.hud.set_state(self.state.jarvis, self.state.voice_enabled and self.state.jarvis == "OUVINDO")
        self.sys_panel.update_system(self.state.status)
        self.sys_panel.update_services(self.state.status, self.state.voice, self.state.radar)
        self.mt5_view.render_mt5(mt5_display(self.state.status))
        self._render_config()

    def on_radar(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.radar = data
            self.radar_view.render_radar(data)
            self.sys_panel.update_services(self.state.status, self.state.voice, self.state.radar)

    def on_gpu(self, data):
        if isinstance(data, dict):
            self.state.gpu = data
            self.sys_panel.update_gpu(data)

    def on_voice(self, data):
        self.state.voice = data if isinstance(data, dict) else {}
        data = self.state.voice
        listening = False
        if self.state.backend_online and data.get("ok"):
            hud_state = hud_for_voice(data.get("state", ""))
            v_running = bool(data.get("running"))
            listening = hud_state == "OUVINDO" or (v_running and hud_state in ("TRANSCRIBINDO", "PROCESSANDO", "FALANDO"))
            # HUD reflete a voz, exceto durante voo de chat digitado.
            if not self._chat_in_flight and hud_state:
                if hud_state == "OFFLINE":
                    if self.state.jarvis in ("ONLINE", "AGUARDANDO", "OUVINDO", "OFFLINE"):
                        self.state.set_jarvis("OFFLINE")
                else:
                    self.state.set_jarvis(hud_state)
                interim = ""
                if hud_state in ("TRANSCRIBINDO", "PROCESSANDO", "FALANDO"):
                    interim = str(data.get("last_heard") or "")
                self.hud.set_state(self.state.jarvis,
                                   self.state.voice_enabled and v_running,
                                   data.get("level"), interim)
            elif not self._chat_in_flight:
                self.hud.set_state(self.state.jarvis)
        self.chat.set_mic_state(listening and self.state.voice_enabled)
        self.sys_panel.update_services(self.state.status, self.state.voice, self.state.radar)
        self._mirror_voice(data)

    def _mirror_voice(self, data):
        """Reflete conversa de voz por ID de evento, sem reenviar.

        Ruido ignorado (sem evento) nunca entra no chat; wake sozinha
        tambem nao. Metadados (route/skill/conf/provider/latency) vem do
        MESMO evento — sem misturar com outras requisicoes.
        """
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
            self.chat.add_user(f"🎤 {heard}")
        if resp:
            self.chat.add_jarvis(resp)
        # Metadados do MESMO comando de voz.
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
        self.prov_panel.update(getattr(self, "_providers", {}), tasks)
        self._render_dev()

    def on_orch(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.orchestrator = data
            self._render_route()
        self._render_dev()

    def on_skills(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self.state.skills = data.get("skills", [])
            self.skills_view.render(data)

    def on_providers(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._providers = data
            self.state.providers = data
            self.prov_panel.update(data, self.state.tasks)
            self._render_route()
        self._render_dev()

    def on_caps(self, data):
        if isinstance(data, dict) and data.get("ok"):
            self._caps = data
        self._render_config()

    def _render_route(self):
        last = (self.state.orchestrator or {}).get("last_decision") or {}
        prim = (getattr(self, "_providers", {}) or {}).get("primary") or {}
        dev_extra = ""
        if self.state.dev_mode:
            dev_extra = (f"SKILL {last.get('skill', '--')} · PROV {prim.get('actual_provider', '--')} · "
                         f"PROF {last.get('model_profile', '--')} · FB {prim.get('fallback', '--')} · "
                         f"TOOLS {last.get('tool_count', '--')}")
        self.chat.set_meta(last.get("route", self.state.last_route) or self.state.last_route,
                           self.state.last_brain, str(last.get("confidence", self.state.last_conf)),
                           last.get("skill", self.state.last_skill),
                           self.state.last_provider, dev_extra, self.state.last_llm)

    def _render_dev(self):
        self.dev_view.render(self.state.orchestrator, getattr(self, "_providers", {}),
                             self.state.brain, self.state.tasks, self.state.voice)

    def _render_config(self):
        self.config_view.render_info(self.client.base_url, getattr(self, "_caps", {}))

    # -- chat real (caminho unico: typed ou voice-manual usam este fluxo) --
    def send_chat(self, text):
        self.submit_message(text, source="typed")

    def submit_message(self, text, source="typed"):
        """Unica porta de envio do Desktop para /api/jarvis/chat.

        source: 'typed' (teclado) — voz do VoiceService NAO passa aqui
        (o servico ja executa; o Desktop so espelha via _mirror_voice).
        """
        text = str(text or "").strip()
        if not text:
            return
        self.tabs.setCurrentWidget(self.chat)
        self.chat.add_user(text)
        if not self.state.backend_online:
            self.state.set_jarvis("ERRO")
            self.hud.set_state("ERRO")
            self.chat.add_jarvis("Golden Backend indisponível. Clique em TENTAR NOVAMENTE.")
            return
        self.state.set_jarvis("PROCESSANDO")
        self.hud.set_state("PROCESSANDO")
        self.chat.add_jarvis("Recebi. Estou processando.")
        self._chat_in_flight = True
        self._run(self.client.chat, lambda r: self.on_chat_result(r, text), text)

    def on_chat_result(self, result, text):
        result = result if isinstance(result, dict) else {}
        self._chat_in_flight = False
        if result.get("offline"):
            self.state.set_jarvis("ERRO")
            self.chat.add_jarvis("Golden Backend indisponível. Clique em TENTAR NOVAMENTE.")
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
            self.chat.add_jarvis(result.get("response", "."))
            self._render_route()
            if shadow.get("task_id"):
                self.chat.add_jarvis(f"(Plano validado em SHADOW · task {shadow.get('task_id')} · sem execução)")
            self.state.set_jarvis("CONCLUÍDO")
            self.refresh_tasks()
            self._run(self.client.orchestrator_status, self.on_orch)
            self._run(self.client.providers_status, self.on_providers)
        else:
            if result.get("approval_required") or "confirm" in str(result.get("error", "")).lower():
                self.state.set_jarvis("AGUARDANDO CONFIRMAÇÃO")
                self.chat.add_jarvis(f"Aguardando confirmação: {result.get('error') or result}")
            elif "esclarec" in str(result.get("response", "") + result.get("error", "")).lower() or (result.get("tool", "") in ("", "none")):
                self.state.set_jarvis("CONCLUÍDO")
                self.chat.add_jarvis(result.get("response") or result.get("error") or "Preciso de mais contexto.")
            else:
                self.state.set_jarvis("ERRO")
                detail = str(result.get("error", "falha"))
                msg = friendly_error(detail)
                if self.state.dev_mode:
                    msg += f"\n[DEV] {detail[:300]}"
                self.chat.add_jarvis(msg)
        self.hud.set_state(self.state.jarvis)

    # -- config switches (reais) --
    def set_voice_enabled(self, enabled):
        self.state.voice_enabled = bool(enabled)
        fn = self.client.voice_start if enabled else self.client.voice_stop
        self._run(fn, self.on_voice)

    def toggle_voice(self):
        self.set_voice_enabled(not self.state.voice_enabled)
        self.config_view.voice.setChecked(self.state.voice_enabled)

    def set_dev_mode(self, enabled):
        self.state.dev_mode = bool(enabled)
        self.chat.set_dev(enabled)
        self._render_route()
        if enabled:
            self.tabs.setCurrentWidget(self.dev_view)

    def set_tray_mode(self, enabled):
        self.state.minimize_to_tray = bool(enabled)

    # -- tasks reais --
    def refresh_tasks(self):
        self._run(self.client.tasks_list, self.on_tasks)

    def task_detail(self, task_id):
        if task_id:
            self._run(self.client.tasks_get, self.tasks_view.set_detail, task_id)

    def task_cancel(self, task_id):
        if task_id:
            self._run(self.client.tasks_cancel, lambda _r: self.refresh_tasks())

    # -- drag and drop honesto --
    def dragEnterEvent(self, event):  # noqa: N802 - assinatura Qt
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802 - assinatura Qt
        names = ""
        if event.mimeData().hasUrls():
            names = ", ".join(u.toLocalFile() or u.toString() for u in event.mimeData().urls())
        elif event.mimeData().hasText():
            names = event.mimeData().text()[:200]
        self.tabs.setCurrentWidget(self.chat)
        self.chat.add_jarvis(
            f"Recebido: {names or 'conteúdo'}. Ingestão de anexos ainda não implementada "
            "no backend — arraste preparada, execução pendente.")
        event.acceptProposedAction()
