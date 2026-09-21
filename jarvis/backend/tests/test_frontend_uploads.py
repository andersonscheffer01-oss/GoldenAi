import hashlib
import os
import tempfile
from pathlib import Path

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
upload_dir = Path(tempfile.mkdtemp(prefix="jarvis_upload_test_"))
os.environ["JARVIS_DATABASE_URL"] = "sqlite:///" + db_file.name.replace("\\", "/")
os.environ["JARVIS_SECRET_KEY"] = "test_secret_key_only_for_automated_tests"
os.environ["JARVIS_ENVIRONMENT"] = "test"
os.environ["JARVIS_UPLOAD_MAX_BYTES"] = "1024"

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import Arquivo, Auditoria
from app.services import file_storage


file_storage.UPLOAD_ROOT = upload_dir
file_storage.PENDING_DIR = upload_dir / "pending"
client = TestClient(app)
OLD_GOLDEN_DB = Path(r"C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db")


def setup_module():
    init_db()


def register_and_login(email):
    client.post("/api/auth/register", json={"nome": "Usuario Teste", "email": email, "senha": "senha-segura-123"})
    response = client.post("/api/auth/login", json={"email": email, "senha": "senha-segura-123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_frontend_app_loads():
    response = client.get("/app")
    assert response.status_code == 200
    assert "Golden Jarvis" in response.text


def test_login_page_loads():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Entrar" in response.text


def test_private_api_without_auth_is_rejected():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_upload_without_auth_is_rejected():
    response = client.post("/api/uploads", files={"file": ("foto.png", b"\x89PNG\r\n\x1a\nabc", "image/png")})
    assert response.status_code == 401


def test_valid_image_upload_and_list():
    token = register_and_login("upload-image@example.com")
    response = client.post(
        "/api/uploads",
        headers=auth(token),
        files={"file": ("comprovante.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "recebido"
    assert data["mime_type"] == "image/png"
    assert data["nome_original"] == "comprovante.png"
    assert data["mensagem"] == "Arquivo recebido e aguardando analise."

    listing = client.get("/api/uploads", headers=auth(token))
    assert listing.status_code == 200
    assert len(listing.json()) >= 1


def test_valid_pdf_upload():
    token = register_and_login("upload-pdf@example.com")
    response = client.post(
        "/api/uploads",
        headers=auth(token),
        files={"file": ("boleto.pdf", b"%PDF-1.4\n1 0 obj\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["mime_type"] == "application/pdf"


def test_file_above_limit_is_rejected():
    token = register_and_login("upload-big@example.com")
    content = b"\x89PNG\r\n\x1a\n" + (b"a" * 2048)
    response = client.post(
        "/api/uploads",
        headers=auth(token),
        files={"file": ("grande.png", content, "image/png")},
    )
    assert response.status_code == 413


def test_dangerous_extension_is_rejected():
    token = register_and_login("upload-danger@example.com")
    response = client.post(
        "/api/uploads",
        headers=auth(token),
        files={"file": ("ataque.exe", b"MZfake", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_user_cannot_access_other_users_file():
    token_a = register_and_login("owner@example.com")
    token_b = register_and_login("intruder@example.com")
    created = client.post(
        "/api/uploads",
        headers=auth(token_a),
        files={"file": ("foto.jpg", b"\xff\xd8\xffabc", "image/jpeg")},
    )
    assert created.status_code == 201
    file_id = created.json()["id"]
    blocked = client.get(f"/api/uploads/{file_id}", headers=auth(token_b))
    assert blocked.status_code == 404


def test_authenticated_delete_upload():
    token = register_and_login("delete@example.com")
    created = client.post(
        "/api/uploads",
        headers=auth(token),
        files={"file": ("apagar.webp", b"RIFFxxxxWEBPabc", "image/webp")},
    )
    assert created.status_code == 201
    file_id = created.json()["id"]
    deleted = client.delete(f"/api/uploads/{file_id}", headers=auth(token))
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    gone = client.get(f"/api/uploads/{file_id}", headers=auth(token))
    assert gone.status_code == 404


def test_upload_audit_records_created():
    with SessionLocal() as db:
        actions = {row.acao for row in db.query(Auditoria).all()}
        assert "upload_recebido" in actions
        assert "upload_recusado" in actions


def test_old_golden_database_remains_unchanged():
    before = hashlib.sha256(OLD_GOLDEN_DB.read_bytes()).hexdigest()
    client.get("/api/health")
    after = hashlib.sha256(OLD_GOLDEN_DB.read_bytes()).hexdigest()
    assert before == after

