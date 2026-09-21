from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app
from app.services.intent_service import detect

client = TestClient(app)


def setup_module():
    init_db()


def login(email):
    client.post('/api/auth/register', json={'nome': 'Comandos completos', 'email': email, 'senha': 'senha-segura-123'})
    return client.post('/api/auth/login', json={'email': email, 'senha': 'senha-segura-123'}).json()['access_token']


def headers(token):
    return {'Authorization': 'Bearer ' + token}


def confirm(token, action_id):
    return client.post(f'/api/jarvis/acoes/{action_id}/confirmar', headers=headers(token))


def test_detects_parcel_count_before_label_and_text_confirmation():
    parsed = detect('Crie um parcelamento de R$ 120 em 3 parcelas')
    assert parsed['intent'] == 'criar_parcelamento'
    assert parsed['parameters']['total_parcelas'] == 3
    assert detect('sim')['intent'] == 'confirmar_acao'
    assert detect('cancelar')['intent'] == 'cancelar_acao'


def test_budget_requires_confirmation_and_is_created():
    token = login('budget-complete@example.com')
    response = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Crie um orcamento de R$ 500'})
    assert response.json()['status'] == 'aguardando_confirmacao'
    result = confirm(token, response.json()['acao_id'])
    assert result.status_code == 200 and result.json()['status'] == 'executado'
    budgets = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Quais sao meus orcamentos?'})
    assert budgets.json()['status'] == 'respondida' and '500,00' in budgets.json()['message']


def test_installment_creation_creates_all_rows_and_query_is_read_only():
    token = login('installments-complete@example.com')
    response = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Crie um parcelamento de R$ 120 em 3 parcelas'})
    assert response.json()['status'] == 'aguardando_confirmacao'
    result = confirm(token, response.json()['acao_id'])
    assert result.status_code == 200 and result.json()['status'] == 'executado'
    rows = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Quais parcelas estao pendentes?'})
    assert rows.json()['status'] == 'respondida' and '#1' in rows.json()['message'] and '#3' in rows.json()['message']


def test_reminder_and_edit_delete_are_confirmation_gated():
    token = login('mutations-complete@example.com')
    reminder = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Me lembre de pagar a conta'})
    assert reminder.json()['status'] == 'aguardando_confirmacao'
    assert client.post(f"/api/jarvis/acoes/{reminder.json()['acao_id']}/cancelar", headers=headers(token)).json()['status'] == 'cancelado'
    expense = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Registre R$ 10 no cafe'})
    assert confirm(token, expense.json()['acao_id']).json()['status'] == 'executado'
    edit = client.post('/api/jarvis/comando', headers=headers(token), json={'content': 'Altere o lancamento 1 para R$ 20'})
    assert edit.json()['status'] == 'aguardando_confirmacao'
