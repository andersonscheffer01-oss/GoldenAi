import hashlib
import os
import tempfile
from pathlib import Path

os.environ["JARVIS_DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name.replace("\\", "/")
os.environ["JARVIS_SECRET_KEY"] = "test_secret_key_only_for_automated_tests"
os.environ["JARVIS_ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import Auditoria, ComandoPC, DispositivoPC, PareamentoPC


client = TestClient(app)
OLD_GOLDEN_DB = Path(r"C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db")


def _hash_old_db():
    return hashlib.sha256(OLD_GOLDEN_DB.read_bytes()).hexdigest()


def _token(email="pc@example.com"):
    client.post("/api/auth/register", json={"nome": "PC Teste", "email": email, "senha": "senha-segura-123"})
    login = client.post("/api/auth/login", json={"email": email, "senha": "senha-segura-123"})
    return login.json()["access_token"]


def _paired_device(email="pc@example.com"):
    token = _token(email)
    headers = {"Authorization": f"Bearer {token}"}
    pairing = client.post("/api/dispositivos/pareamento/criar", headers=headers)
    code = pairing.json()["codigo"]
    confirmed = client.post(
        "/api/dispositivos/pareamento/confirmar",
        json={"codigo": code, "nome": "PC Anderson", "versao_agente": "0.1.0", "sistema_operacional": "Windows"},
    )
    data = confirmed.json()
    return token, headers, data["device_token"], data["dispositivo"]["id"]


def setup_module():
    init_db()


def test_create_pairing_code_stores_hash_only_and_confirms_once():
    token = _token("pair@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/dispositivos/pareamento/criar", headers=headers)
    assert response.status_code == 200
    code = response.json()["codigo"]
    assert len(code) == 6
    with SessionLocal() as db:
        pairing = db.query(PareamentoPC).order_by(PareamentoPC.id.desc()).first()
        assert pairing.codigo_hash != code
    confirm = client.post("/api/dispositivos/pareamento/confirmar", json={"codigo": code, "nome": "PC", "versao_agente": "0.1.0"})
    assert confirm.status_code == 200
    assert confirm.json()["device_token"]
    reused = client.post("/api/dispositivos/pareamento/confirmar", json={"codigo": code, "nome": "PC", "versao_agente": "0.1.0"})
    assert reused.status_code == 409


def test_device_token_required_for_heartbeat_and_status_updates():
    _, _, device_token, _ = _paired_device("heartbeat@example.com")
    blocked = client.post("/api/dispositivos/agente/heartbeat", json={"status": {}})
    assert blocked.status_code == 401
    ok = client.post(
        "/api/dispositivos/agente/heartbeat",
        headers={"Authorization": f"Bearer {device_token}"},
        json={"versao_agente": "0.1.0", "sistema_operacional": "Windows", "status": {"cpu_percentual": 12.5, "memoria_percentual": 44.0, "disco_livre_gb": 100, "ollama": "ativo", "jarvis": "ativo", "mt5": "inativo"}},
    )
    assert ok.status_code == 200
    status_response = client.get("/api/pc/status", headers={"Authorization": f"Bearer {_token('status@example.com')}"})
    assert status_response.status_code in (200, 401)


def test_allowed_command_is_queued_and_shell_is_blocked():
    _, headers, device_token, device_id = _paired_device("commands@example.com")
    allowed = client.post("/api/pc/comandos", headers=headers, json={"dispositivo_id": device_id, "tipo": "verificar_status_pc", "payload": {}})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "pendente"
    next_command = client.get("/api/pc/agente/comandos/proximo", headers={"Authorization": f"Bearer {device_token}"})
    assert next_command.status_code == 200
    assert next_command.json()["comando"]["tipo"] == "verificar_status_pc"
    blocked = client.post("/api/pc/comandos", headers=headers, json={"dispositivo_id": device_id, "tipo": "executar_powershell", "payload": {"script": "dir"}})
    assert blocked.status_code == 403


def test_open_program_requires_confirmation_and_blocks_arbitrary_path():
    _, headers, _, device_id = _paired_device("open@example.com")
    blocked = client.post("/api/pc/comandos", headers=headers, json={"dispositivo_id": device_id, "tipo": "abrir_aplicativo_autorizado", "payload": {"programa": r"C:\Windows\System32\cmd.exe"}})
    assert blocked.status_code == 403
    command = client.post("/api/pc/comandos", headers=headers, json={"dispositivo_id": device_id, "tipo": "abrir_aplicativo_autorizado", "payload": {"programa": "golden_jarvis"}})
    assert command.status_code == 200
    assert command.json()["status"] == "aguardando_confirmacao"
    confirm = client.post(f"/api/pc/comandos/{command.json()['id']}/confirmar", headers=headers)
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "pendente"


def test_revoke_device_and_audit_without_changing_old_golden_db():
    before = _hash_old_db()
    _, headers, device_token, device_id = _paired_device("revoke@example.com")
    revoked = client.post(f"/api/dispositivos/pc/{device_id}/revogar", headers=headers)
    assert revoked.status_code == 200
    heartbeat = client.post("/api/dispositivos/agente/heartbeat", headers={"Authorization": f"Bearer {device_token}"}, json={"status": {}})
    assert heartbeat.status_code == 401
    with SessionLocal() as db:
        assert db.query(Auditoria).filter(Auditoria.acao == "revogar_dispositivo_pc").first() is not None
        assert db.query(DispositivoPC).filter(DispositivoPC.id == device_id, DispositivoPC.status == "revogado").first() is not None
        assert db.query(ComandoPC).filter(ComandoPC.tipo == "enviar_ordem_trading").first() is None
    assert before == _hash_old_db()
