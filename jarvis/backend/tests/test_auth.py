import hashlib
import os
import tempfile
from pathlib import Path

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ["JARVIS_DATABASE_URL"] = "sqlite:///" + db_file.name.replace("\\", "/")
os.environ["JARVIS_SECRET_KEY"] = "test_secret_key_only_for_automated_tests"
os.environ["JARVIS_ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import Auditoria, Usuario


client = TestClient(app)
OLD_GOLDEN_DB = Path(r"C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db")


def _hash_old_db():
    return hashlib.sha256(OLD_GOLDEN_DB.read_bytes()).hexdigest()


def setup_module():
    init_db()


def test_register_valid_user():
    response = client.post(
        "/api/auth/register",
        json={"nome": "Admin Teste", "email": "admin@example.com", "senha": "senha-segura-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "admin@example.com"
    assert "senha" not in data
    assert "senha_hash" not in data

    with SessionLocal() as db:
        usuario = db.query(Usuario).filter(Usuario.email == "admin@example.com").first()
        assert usuario is not None
        assert usuario.senha_hash != "senha-segura-123"


def test_register_duplicate_user_is_rejected():
    response = client.post(
        "/api/auth/register",
        json={"nome": "Admin Teste", "email": "admin@example.com", "senha": "senha-segura-123"},
    )
    assert response.status_code == 409


def test_login_valid_user():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "senha": "senha-segura-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["usuario"]["email"] == "admin@example.com"
    assert "senha_hash" not in data["usuario"]


def test_login_invalid_user():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "senha": "senha-errada"},
    )
    assert response.status_code == 401


def test_me_requires_token():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_valid_token():
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "senha": "senha-segura-123"})
    token = login.json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"


def test_logout_revokes_session():
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "senha": "senha-segura-123"})
    token = login.json()["access_token"]
    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    blocked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 401


def test_audit_records_are_created():
    with SessionLocal() as db:
        actions = {row.acao for row in db.query(Auditoria).all()}
    assert "cadastro_usuario" in actions
    assert "cadastro_falhou" in actions
    assert "login_realizado" in actions
    assert "login_falhou" in actions
    assert "logout" in actions
    assert "acesso_negado" in actions


def test_old_golden_runtime_db_was_not_modified_by_jarvis_auth_flow():
    before = _hash_old_db()
    client.get("/api/health")
    client.post("/api/auth/login", json={"email": "admin@example.com", "senha": "senha-segura-123"})
    after = _hash_old_db()
    assert before == after

