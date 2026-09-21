"""Cliente HTTP central do Golden Jarvis Desktop.

Unico lugar com requests. Widgets/views nunca fazem HTTP direto.
"""
from __future__ import annotations

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
STATUS_TIMEOUT = 6
CHAT_TIMEOUT = 120


class JarvisApiError(RuntimeError):
    pass


class JarvisApiClient:
    """Wrapper fino sobre os endpoints reais do backend Golden."""

    def __init__(self, base_url=DEFAULT_BASE_URL, session=None,
                 status_timeout=STATUS_TIMEOUT, chat_timeout=CHAT_TIMEOUT):
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.session = session or requests.Session()
        self.status_timeout = status_timeout
        self.chat_timeout = chat_timeout

    # -- base --
    def _post(self, path, payload=None, timeout=None):
        url = self.base_url + path
        try:
            resp = self.session.post(url, json=payload or {}, timeout=timeout or self.status_timeout)
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)[:300], "offline": True}
        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "error": f"HTTP {resp.status_code}", "offline": resp.status_code >= 500}
        if isinstance(data, dict):
            return data
        return {"ok": False, "error": "resposta invalida"}

    # -- status / chat / voz --
    def get_status(self):
        return self._post("/api/status", {})

    def chat(self, text):
        return self._post("/api/jarvis/chat", {"text": text}, timeout=self.chat_timeout)

    def brain_status(self):
        return self._post("/api/jarvis/brain/status", {})

    def voice_status(self):
        return self._post("/api/jarvis/voice-service/status", {})

    def voice_start(self):
        return self._post("/api/jarvis/voice-service/start", {})

    def voice_stop(self):
        return self._post("/api/jarvis/voice-service/stop", {})

    def voice_speak(self, text):
        return self._post("/api/jarvis/voice-service/speak", {"text": text})

    def capabilities(self):
        return self._post("/api/capabilities", {})

    # -- tasks reais --
    def tasks_list(self, limit=50, status=None):
        payload = {"limit": limit}
        if status:
            payload["status"] = status
        return self._post("/api/jarvis/tasks/list", payload)

    def tasks_get(self, task_id):
        return self._post("/api/jarvis/tasks/get", {"task_id": task_id})

    def tasks_cancel(self, task_id):
        return self._post("/api/jarvis/tasks/cancel", {"task_id": task_id})

    # -- orchestrator / skills / providers (somente leitura) --
    def orchestrator_status(self):
        return self._post("/api/jarvis/orchestrator/status", {})

    def skills_status(self):
        return self._post("/api/jarvis/skills/status", {})

    def providers_status(self):
        return self._post("/api/jarvis/providers/status", {})

    def radar_status(self):
        return self._post("/api/radar/status", {})

    # -- projetos / filesystem --
    def projects(self):
        return self._post("/api/projects", {})

    def mt5_list_robots(self):
        return self._post("/api/mt5/list_robots", {})

    # -- security --
    def security_status(self):
        return self._post("/api/security/status", {})

    # -- memory --
    def memory_status(self):
        return self._post("/api/jarvis/memory/status", {})

    def memory_recent(self, limit=10, namespace=None):
        payload = {"limit": limit}
        if namespace:
            payload["namespace"] = namespace
        return self._post("/api/jarvis/memory/recent", payload)

    # -- system --
    def system_stats(self):
        return self._post("/api/system/stats", {})

    def risk_status(self):
        return self._post("/api/risk/status", {})
