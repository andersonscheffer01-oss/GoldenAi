import hashlib
import os
import tempfile
from pathlib import Path

os.environ["JARVIS_DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name.replace("\\", "/")
os.environ["JARVIS_SECRET_KEY"] = "test_secret_key_only_for_automated_tests"
os.environ["JARVIS_ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]
OLD_GOLDEN_DB = Path(r"C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db")


def setup_module():
    init_db()


def auth(email):
    client.post("/api/auth/register", json={"nome": "Dashboard", "email": email, "senha": "senha-segura-123"})
    token = client.post("/api/auth/login", json={"email": email, "senha": "senha-segura-123"}).json()["access_token"]
    return {"Authorization": "Bearer " + token}


def category(headers, name="Mercado"):
    rows = client.get("/api/financas/categorias", headers=headers).json()
    return next(item for item in rows if item["nome"] == name)


def create_entry(headers, category_id, description, value, kind="despesa", day="2026-08-15", **extra):
    return client.post("/api/financas/lancamentos", headers=headers, json={"tipo": kind, "descricao": description, "valor": value, "data_compra": day, "categoria_id": category_id, **extra})


def test_dashboard_empty_state_is_all_zero_and_has_no_fake_invoices():
    headers = auth("redesign-empty@example.com")
    panel = client.get("/api/financas/painel?data_inicio=2026-08-01&data_fim=2026-08-31", headers=headers).json()
    assert panel["resumo"]["quantidade_lancamentos"] == 0
    assert panel["resumo"]["saldo_periodo_centavos"] == 0
    assert panel["faturas"] == {"disponivel": False, "total_centavos": None}
    assert panel["contas"] == [] and panel["cartoes"] == []


def test_dashboard_expenses_income_and_negative_balance_use_centavos():
    headers = auth("redesign-values@example.com"); cat = category(headers)
    create_entry(headers, cat["id"], "Mercado", "150,00")
    create_entry(headers, cat["id"], "Receita", "50,00", kind="receita")
    panel = client.get("/api/financas/painel?data_inicio=2026-08-01&data_fim=2026-08-31", headers=headers).json()
    assert panel["resumo"]["total_despesas_centavos"] == 15000
    assert panel["resumo"]["total_receitas_centavos"] == 5000
    assert panel["resumo"]["saldo_periodo_centavos"] == -10000
    assert panel["media_diaria_despesas_centavos"] == round(15000 / 31)


def test_month_category_and_chart_filters_are_real():
    headers = auth("redesign-filter@example.com"); market = category(headers); health = category(headers, "Saude")
    create_entry(headers, market["id"], "Agosto", "20,00", day="2026-08-10")
    create_entry(headers, health["id"], "Julho", "90,00", day="2026-07-10")
    query = "data_inicio=2026-08-01&data_fim=2026-08-31&categoria_id=" + str(market["id"])
    rows = client.get("/api/financas/por-categoria?" + query, headers=headers).json()
    assert rows == [{"chave": str(market["id"]), "receitas_centavos": 0, "despesas_centavos": 2000, "saldo_centavos": -2000, "valor_centavos": -2000, "nome": "Mercado"}]
    days = client.get("/api/financas/por-dia?" + query, headers=headers).json()
    assert days[0]["chave"] == "2026-08-10" and days[0]["despesas_centavos"] == 2000


def test_paginated_entries_and_detailed_names():
    headers = auth("redesign-page@example.com"); cat = category(headers)
    account = client.post("/api/financas/contas", headers=headers, json={"nome": "Dinheiro", "tipo": "dinheiro"}).json()
    card = client.post("/api/financas/cartoes", headers=headers, json={"nome": "Cartao teste", "ultimos_quatro_digitos": "4321"}).json()
    for index in range(12): create_entry(headers, cat["id"], f"Item {index}", "1,00", conta_id=account["id"], cartao_id=card["id"])
    first = client.get("/api/financas/lancamentos-paginados?data_inicio=2026-08-01&data_fim=2026-08-31&pagina=1&por_pagina=5", headers=headers).json()
    second = client.get("/api/financas/lancamentos-paginados?data_inicio=2026-08-01&data_fim=2026-08-31&pagina=2&por_pagina=5", headers=headers).json()
    assert first["total"] == 12 and first["total_paginas"] == 3 and len(first["itens"]) == 5
    assert len(second["itens"]) == 5 and first["itens"][0]["categoria_nome"] == "Mercado"
    assert first["itens"][0]["conta_nome"] == "Dinheiro" and first["itens"][0]["cartao_nome"] == "Cartao teste"


def test_account_and_card_cards_use_only_owner_data():
    owner = auth("redesign-owner@example.com"); other = auth("redesign-other@example.com"); cat = category(owner)
    account = client.post("/api/financas/contas", headers=owner, json={"nome": "Conta manual", "banco": "Banco", "tipo": "conta_corrente"}).json()
    card = client.post("/api/financas/cartoes", headers=owner, json={"nome": "Cartao manual", "limite_total_centavos": 10000, "ultimos_quatro_digitos": "9876"}).json()
    create_entry(owner, cat["id"], "Despesa", "25,00", conta_id=account["id"], cartao_id=card["id"])
    owner_panel = client.get("/api/financas/painel?data_inicio=2026-08-01&data_fim=2026-08-31", headers=owner).json()
    other_panel = client.get("/api/financas/painel?data_inicio=2026-08-01&data_fim=2026-08-31", headers=other).json()
    assert owner_panel["contas"][0]["saidas_centavos"] == 2500
    assert owner_panel["cartoes"][0]["limite_disponivel_centavos"] == 7500
    assert other_panel["contas"] == [] and other_panel["cartoes"] == []


def test_frontend_has_desktop_mobile_navigation_and_empty_states():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "assets" / "js" / "dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "assets" / "css" / "app.css").read_text(encoding="utf-8")
    for label in ("Visão geral", "Lançamentos", "Contas", "Cartões", "Orçamentos", "Parcelas", "Alertas", "Relatórios", "Jarvis", "Ajustes"):
        assert label in html
    for label in ("Início", "Adicionar", "Mais"):
        assert label in html
    assert "Ainda não há lançamentos" in js and "Nenhum cartão cadastrado" in js and "Nenhum orçamento criado" in js
    assert "@media(max-width:760px)" in css and ".desktop-sidebar" in css and ".bottom-nav" in css


def test_no_fake_bank_or_financial_values_in_frontend_and_old_golden_unchanged():
    before = hashlib.sha256(OLD_GOLDEN_DB.read_bytes()).hexdigest()
    source = (ROOT / "frontend" / "assets" / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "Banco Inter" not in source and "Banco BV" not in source and "Itaú" not in source
    assert "limite_utilizado_centavos" in source and "total_despesas_centavos" in source
    assert before == hashlib.sha256(OLD_GOLDEN_DB.read_bytes()).hexdigest()
