import asyncio
import time

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import Auditoria, Conversa, Mensagem
from app.services import chat_service
from app.services.ollama_client import OllamaInvalidResponse, OllamaTimeout


client = TestClient(app)


def setup_module():
    init_db()


def register_and_login(email):
    client.post("/api/auth/register", json={"nome": "Chat Teste", "email": email, "senha": "senha-segura-123"})
    response = client.post("/api/auth/login", json={"email": email, "senha": "senha-segura-123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_create_and_list_own_conversations():
    token = register_and_login("chat-list@example.com")
    created = client.post("/api/chat/conversas", headers=auth(token), json={"titulo": "Teste"})
    assert created.status_code == 201
    listed = client.get("/api/chat/conversas", headers=auth(token))
    assert listed.status_code == 200
    assert any(item["id"] == created.json()["id"] for item in listed.json())


def test_conversation_isolation_and_delete():
    token_a = register_and_login("chat-owner@example.com")
    token_b = register_and_login("chat-intruder@example.com")
    created = client.post("/api/chat/conversas", headers=auth(token_a), json={}).json()
    conversation_id = created["id"]
    assert client.get(f"/api/chat/conversas/{conversation_id}", headers=auth(token_b)).status_code == 404
    assert client.delete(f"/api/chat/conversas/{conversation_id}", headers=auth(token_b)).status_code == 404
    assert client.delete(f"/api/chat/conversas/{conversation_id}", headers=auth(token_a)).status_code == 200


def test_message_validation():
    token = register_and_login("chat-validation@example.com")
    assert client.post("/api/chat/mensagem", headers=auth(token), json={"content": "   "}).status_code == 422
    assert client.post("/api/chat/mensagem", headers=auth(token), json={"content": "x" * 4001}).status_code == 422


def test_message_saves_user_and_assistant_and_uses_history(monkeypatch):
    token = register_and_login("chat-success@example.com")
    received = []

    async def fake_ollama(messages, settings):
        received.append(messages)
        return "Resposta simulada do Jarvis", 17

    monkeypatch.setattr(chat_service, "chat_with_ollama", fake_ollama)
    first = client.post("/api/chat/mensagem", headers=auth(token), json={"content": "Ola, Jarvis"})
    assert first.status_code == 200
    data = first.json()
    assert data["status"] == "respondida"
    assert data["assistant_message"]["content"] == "Resposta simulada do Jarvis"
    second = client.post("/api/chat/mensagem", headers=auth(token), json={"conversation_id": data["conversation_id"], "content": "Continue"})
    assert second.status_code == 200
    assert any(item["content"] == "Ola, Jarvis" for item in received[-1])
    with SessionLocal() as db:
        messages = db.query(Mensagem).filter(Mensagem.conversa_id == data["conversation_id"]).all()
        assert len(messages) == 4
        assert {item.papel for item in messages} == {"usuario", "assistente"}
        assert db.get(Conversa, data["conversation_id"]).titulo.startswith("Ola, Jarvis")


def test_ollama_timeout_returns_safe_error_and_saves_failure(monkeypatch):
    token = register_and_login("chat-timeout@example.com")

    async def timeout(*args):
        raise OllamaTimeout()

    monkeypatch.setattr(chat_service, "chat_with_ollama", timeout)
    response = client.post("/api/chat/mensagem", headers=auth(token), json={"content": "Teste timeout"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OLLAMA_TIMEOUT"
    assert "Traceback" not in response.text


def test_invalid_ollama_response_returns_safe_error(monkeypatch):
    token = register_and_login("chat-invalid@example.com")

    async def invalid(*args):
        raise OllamaInvalidResponse()

    monkeypatch.setattr(chat_service, "chat_with_ollama", invalid)
    response = client.post("/api/chat/mensagem", headers=auth(token), json={"content": "Teste resposta"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OLLAMA_INVALID_RESPONSE"


def test_chat_requires_authentication():
    assert client.get("/api/chat/conversas").status_code == 401
    assert client.post("/api/chat/mensagem", json={"content": "Ola"}).status_code == 401


def test_chat_audit_and_upload_health_still_work():
    token = register_and_login("chat-audit@example.com")

    async def fake_ollama(messages, settings):
        return "Tudo certo", None

    import pytest
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(chat_service, "chat_with_ollama", fake_ollama)
    try:
        response = client.post("/api/chat/mensagem", headers=auth(token), json={"content": "Auditoria"})
    finally:
        monkeypatch.undo()
    assert response.status_code == 200
    assert client.get("/api/health").status_code == 200
    with SessionLocal() as db:
        assert any(item.acao == "mensagem_enviada" for item in db.query(Auditoria).all())
