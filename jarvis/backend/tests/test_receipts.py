import json

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine, init_db
from app.main import app
from app.models import AnaliseComprovante, Arquivo
from app.routers import receipts
from app.schemas import ReceiptConfidence, ReceiptData
from app.services.receipt_parser import PreparedDocument, ReceiptParserError, parse_receipt_json


client = TestClient(app)


def setup_module():
    init_db()


def register_and_login(email):
    client.post("/api/auth/register", json={"nome": "Recibo Teste", "email": email, "senha": "senha-segura-123"})
    return client.post("/api/auth/login", json={"email": email, "senha": "senha-segura-123"}).json()["access_token"]


def auth(token):
    return {"Authorization": "Bearer " + token}


def upload(token, name="comprovante.jpg", data=b"\xff\xd8\xfffake"):
    response = client.post("/api/uploads", headers=auth(token), files={"file": (name, data, "image/jpeg")})
    assert response.status_code == 201
    return response.json()["id"]


def valid_data(value=42.5):
    return {"tipo_documento": "comprovante_compra", "estabelecimento": "Mercado Teste", "data": "2026-08-30", "valor_total": value, "moeda": "BRL", "confianca": {"estabelecimento": .95, "data": .95, "hora": 0, "valor_total": .95, "forma_pagamento": .8, "itens": .8, "geral": .95}}


async def fake_analysis(document, settings):
    return ReceiptData.model_validate(valid_data()), json.dumps(valid_data())


def test_analyze_image_and_get_pending_result(monkeypatch):
    token = register_and_login("receipt-analysis@example.com")
    file_id = upload(token)
    monkeypatch.setattr(receipts, "analyze_document", fake_analysis)
    monkeypatch.setattr(receipts, "prepare_document", lambda *args: PreparedDocument(images=[b"prepared"], mime_type="image/jpeg"))
    response = client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(token))
    assert response.status_code == 202
    assert response.json()["status"] == "concluida"
    assert response.json()["dados_extraidos"]["valor_total"] == 42.5
    assert client.get(f"/api/comprovantes/{file_id}/analise", headers=auth(token)).status_code == 200


def test_receipt_privacy_and_authentication(monkeypatch):
    owner = register_and_login("receipt-owner@example.com")
    intruder = register_and_login("receipt-intruder@example.com")
    file_id = upload(owner)
    assert client.post(f"/api/comprovantes/{file_id}/analisar").status_code == 401
    assert client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(intruder)).status_code == 404
    monkeypatch.setattr(receipts, "analyze_document", fake_analysis)
    monkeypatch.setattr(receipts, "prepare_document", lambda *args: PreparedDocument(images=[b"prepared"], mime_type="image/jpeg"))
    assert client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(owner)).status_code == 202
    analysis_id = client.get(f"/api/comprovantes/{file_id}/analise", headers=auth(owner)).json()["id"]
    assert client.get(f"/api/comprovantes/{file_id}/analise", headers=auth(intruder)).status_code == 404
    assert client.post(f"/api/analises/{analysis_id}/cancelar", headers=auth(intruder)).status_code == 404


def test_confirm_edit_cancel_and_no_expense_created(monkeypatch):
    token = register_and_login("receipt-confirm@example.com")
    file_id = upload(token, "nota.png", b"\x89PNG\r\n\x1a\nabc")
    monkeypatch.setattr(receipts, "analyze_document", fake_analysis)
    monkeypatch.setattr(receipts, "prepare_document", lambda *args: PreparedDocument(images=[b"prepared"], mime_type="image/jpeg"))
    analysis = client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(token)).json()
    data = valid_data(55)
    confirmed = client.post(f"/api/analises/{analysis['id']}/confirmar", headers=auth(token), json={"dados": data})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmada"
    assert client.post(f"/api/analises/{analysis['id']}/cancelar", headers=auth(token)).status_code == 200
    with SessionLocal() as db:
        assert db.query(AnaliseComprovante).count() >= 1
        assert not engine.dialect.has_table(db.connection(), "gastos")


def test_missing_value_requires_manual_confirmation(monkeypatch):
    token = register_and_login("receipt-no-value@example.com")
    file_id = upload(token)

    async def missing_value(document, settings):
        data = ReceiptData(tipo_documento="comprovante_compra", confianca=ReceiptConfidence(geral=.95))
        return data, json.dumps(data.model_dump())

    monkeypatch.setattr(receipts, "analyze_document", missing_value)
    monkeypatch.setattr(receipts, "prepare_document", lambda *args: PreparedDocument(images=[b"prepared"], mime_type="image/jpeg"))
    analysis = client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(token)).json()
    assert analysis["status"] == "requer_confirmacao"
    blocked = client.post(f"/api/analises/{analysis['id']}/confirmar", headers=auth(token), json={"dados": analysis["dados_extraidos"]})
    assert blocked.status_code == 422


def test_ollama_error_and_retry_limit(monkeypatch):
    token = register_and_login("receipt-error@example.com")
    file_id = upload(token)

    async def failure(document, settings):
        raise ReceiptParserError("OLLAMA_UNAVAILABLE", "Ollama indisponivel")

    monkeypatch.setattr(receipts, "analyze_document", failure)
    monkeypatch.setattr(receipts, "prepare_document", lambda *args: PreparedDocument(images=[b"prepared"], mime_type="image/jpeg"))
    for _ in range(3):
        response = client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(token))
        assert response.status_code == 202
        assert response.json()["status"] == "erro"
    blocked = client.post(f"/api/comprovantes/{file_id}/analisar", headers=auth(token))
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "MAX_ATTEMPTS_REACHED"


def test_invalid_parser_response_is_rejected():
    try:
        parse_receipt_json("not json")
    except ReceiptParserError as error:
        assert error.code == "INVALID_MODEL_RESPONSE"
    else:
        raise AssertionError("invalid JSON should fail")
