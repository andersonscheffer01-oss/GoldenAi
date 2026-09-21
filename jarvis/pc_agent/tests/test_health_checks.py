import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import health_checks


def test_system_status_has_safe_basic_fields(monkeypatch):
    monkeypatch.setattr(health_checks, "check_ollama", lambda: {"status": "inativo", "qwen2_5vl_disponivel": False, "modelos": []})
    monkeypatch.setattr(health_checks, "check_jarvis", lambda server_url: "ativo")
    monkeypatch.setattr(health_checks, "check_mt5", lambda: "inativo")
    data = health_checks.system_status("http://127.0.0.1:8780", "0.1.0")
    assert data["sistema_operacional"]
    assert "cpu_percentual" in data
    assert "memoria_percentual" in data
    assert data["jarvis"] == "ativo"
    assert data["mt5"] == "inativo"


def test_ollama_unavailable_is_reported(monkeypatch):
    monkeypatch.setattr(health_checks, "_http_json", lambda url, timeout=3.0: ("inativo", None))
    data = health_checks.check_ollama()
    assert data["status"] == "inativo"
    assert data["qwen2_5vl_disponivel"] is False
