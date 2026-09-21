import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import client as client_module
from client import JarvisAgentClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_client_sends_bearer_token_without_url_token(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        return FakeResponse({"ok": True})

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    api = JarvisAgentClient("http://127.0.0.1:8780", "device-secret")
    assert api.heartbeat({"status": {}})["ok"] is True
    assert "device-secret" not in captured["url"]
    assert captured["authorization"] == "Bearer device-secret"
