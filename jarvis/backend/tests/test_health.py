import os
import tempfile

os.environ["JARVIS_DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name.replace("\\", "/")
os.environ["JARVIS_SECRET_KEY"] = "test_secret_key_only_for_automated_tests"
os.environ["JARVIS_ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "golden-jarvis"
    assert data["environment"] == "test"
    assert data["database"] == "connected"


def test_startup_status_is_safe_and_local_only():
    response = client.get("/api/startup-status")
    assert response.status_code == 200
    data = response.json()
    assert data["jarvis"] == "online"
    assert data["port"] == 8780
    assert data["local_url"] == "http://127.0.0.1:8780/app"
    assert set(data) == {
        "jarvis", "ollama", "port", "local_ip", "local_url", "lan_url",
        "last_startup", "last_health_check", "startup_status", "startup_error",
        "sleep_notice",
    }
    serialized = response.text.lower()
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "password" not in serialized
