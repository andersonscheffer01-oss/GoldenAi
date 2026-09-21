"""Estado local do app (cache de polling; sem LLM para refresh)."""
from __future__ import annotations

JARVIS_STATES = ("OFFLINE", "ONLINE", "AGUARDANDO", "OUVINDO", "TRANSCRIBINDO",
                 "PROCESSANDO", "FALANDO", "PENSANDO", "PLANEJANDO",
                 "EXECUTANDO", "AGUARDANDO CONFIRMAÇÃO", "CONCLUÍDO", "ERRO")


# Estados operacionais do VoiceService (fonte real) -> HUD.
VOICE_TO_HUD = {
    "OFF": "OFFLINE",
    "WAITING_WAKE": "AGUARDANDO",
    "LISTENING": "OUVINDO",
    "WAKE_DETECTED": "OUVINDO",
    "TRANSCRIBING": "TRANSCRIBINDO",
    "PROCESSING": "PROCESSANDO",
    "SPEAKING": "FALANDO",
    "ERROR": "ERRO",
}


def hud_for_voice(service_state):
    return VOICE_TO_HUD.get(str(service_state or "").upper(), "")


class JarvisState:
    def __init__(self):
        self.backend_online = False
        self.jarvis = "OFFLINE"
        self.status = {}
        self.brain = {}
        self.voice = {}
        self.tasks = []
        self.orchestrator = {}
        self.skills = []
        self.providers = {}
        self.radar = {}
        self.gpu = {}
        self.last_route = ""
        self.last_brain = ""
        self.last_conf = ""
        self.last_skill = ""
        self.last_provider = ""
        self.last_llm = {}
        self.last_voice_timings = {}
        self.voice_enabled = True
        self.dev_mode = False
        self.minimize_to_tray = True

    def apply_status(self, data):
        self.status = data if isinstance(data, dict) else {}
        self.backend_online = bool(self.status.get("ok"))
        if not self.backend_online and self.jarvis in ("ONLINE", "OUVINDO"):
            self.jarvis = "OFFLINE"

    def set_jarvis(self, value):
        if value in JARVIS_STATES:
            self.jarvis = value
