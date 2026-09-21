"""Testes do JarvisApiClient (mocks HTTP; sem backend real)."""
import unittest

from jarvis_desktop.api_client import JarvisApiClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        for suffix, payload in self.routes.items():
            if url.endswith(suffix):
                return FakeResponse(payload() if callable(payload) else payload)
        return FakeResponse({"ok": False, "error": "rota desconhecida"})


class ApiClientCase(unittest.TestCase):
    def _client(self, routes):
        return JarvisApiClient("http://127.0.0.1:8765", session=FakeSession(routes))

    def test_status_chat_tasks_orchestrator_skills_providers(self):
        client = self._client({
            "/api/status": {"ok": True, "status": "online"},
            "/api/jarvis/chat": {"ok": True, "response": "USD/BRL R$ 5,13", "tool": "get_exchange_rate"},
            "/api/jarvis/tasks/list": {"ok": True, "tasks": [{"id": "t1", "status": "QUEUED"}]},
            "/api/jarvis/tasks/get": {"ok": True, "task": {"id": "t1"}, "steps": []},
            "/api/jarvis/tasks/cancel": {"ok": True, "cancelled": True},
            "/api/jarvis/orchestrator/status": {"ok": True, "mode": "shadow", "last_decision": None},
            "/api/jarvis/skills/status": {"ok": True, "skills": [{"name": "system", "status": "READY"}]},
            "/api/jarvis/providers/status": {"ok": True, "providers": []},
        })
        self.assertTrue(client.get_status()["ok"])
        chat = client.chat("qual a cotacao do dolar")
        self.assertTrue(chat["ok"])
        self.assertEqual("get_exchange_rate", chat["tool"])
        self.assertTrue(client.tasks_list()["ok"])
        self.assertTrue(client.tasks_get("t1")["ok"])
        self.assertTrue(client.tasks_cancel("t1")["cancelled"])
        orch = client.orchestrator_status()
        self.assertEqual("shadow", orch["mode"])
        self.assertTrue(client.skills_status()["ok"])
        self.assertTrue(client.providers_status()["ok"])

    def test_offline_maps_to_offline_flag(self):
        import requests

        class DownSession:
            def post(self, *a, **k):
                raise requests.ConnectionError("down")

        client = JarvisApiClient("http://127.0.0.1:8765", session=DownSession())
        result = client.get_status()
        self.assertFalse(result["ok"])
        self.assertTrue(result["offline"])

    def test_no_requests_leak_outside_client(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1] / "jarvis_desktop"
        offenders = []
        for path in root.rglob("*.py"):
            if path.name == "api_client.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "import requests" in text or "requests.post" in text or "requests.get" in text:
                offenders.append(path.name)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
