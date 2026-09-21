import json

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import AnaliseComprovante, Usuario

client = TestClient(app)


def setup_module(): init_db()


def login(email):
    client.post('/api/auth/register', json={'nome': 'Financeiro Teste', 'email': email, 'senha': 'senha-segura-123'})
    return client.post('/api/auth/login', json={'email': email, 'senha': 'senha-segura-123'}).json()['access_token']


def h(token): return {'Authorization': 'Bearer ' + token}


def entry(token, category, value='42,50', date='2026-08-30', **extra):
    body = {'tipo': 'despesa', 'descricao': 'Compra teste', 'valor': value, 'data_compra': date, 'categoria_id': category, **extra}
    return client.post('/api/financas/lancamentos', headers=h(token), json=body)


def test_manual_finance_records_and_centavos():
    token = login('finance-create@example.com')
    categories = client.get('/api/financas/categorias', headers=h(token)).json()
    assert len(categories) >= 23
    category = next(item for item in categories if item['nome'] == 'Mercado')
    account = client.post('/api/financas/contas', headers=h(token), json={'nome': 'Carteira', 'tipo': 'dinheiro'}).json()
    card = client.post('/api/financas/cartoes', headers=h(token), json={'nome': 'Cartao', 'ultimos_quatro_digitos': '1234'}).json()
    assert card['ultimos_quatro_digitos'] == '1234'
    created = entry(token, category['id'], conta_id=account['id'], cartao_id=card['id'], forma_pagamento='credito')
    assert created.status_code == 201
    assert created.json()['valor_centavos'] == 4250
    income = client.post('/api/financas/lancamentos', headers=h(token), json={'tipo': 'receita', 'descricao': 'Salario', 'valor': '100,00', 'data_compra': '2026-08-30', 'categoria_id': categories[-1]['id']})
    assert income.status_code == 201 and income.json()['valor_centavos'] == 10000
    assert entry(token, category['id'], '0').status_code == 422
    assert entry(token, category['id'], '-1').status_code == 422


def test_finance_isolation_filters_summary_and_soft_delete():
    owner = login('finance-owner@example.com'); other = login('finance-other@example.com')
    category = client.get('/api/financas/categorias', headers=h(owner)).json()[0]
    created = entry(owner, category['id'], '10,00').json()
    assert client.get('/api/financas/lancamentos/' + str(created['id']), headers=h(other)).status_code == 404
    summary = client.get('/api/financas/resumo?data_inicio=2026-08-01&data_fim=2026-08-31', headers=h(owner))
    assert summary.status_code == 200 and summary.json()['total_despesas_centavos'] == 1000
    assert client.get('/api/financas/por-categoria?data_inicio=2026-08-01&data_fim=2026-08-31', headers=h(owner)).status_code == 200
    assert client.get('/api/financas/por-dia?data_inicio=2026-08-01&data_fim=2026-08-31', headers=h(owner)).status_code == 200
    assert client.get('/api/financas/maiores-gastos', headers=h(owner)).status_code == 200
    assert client.delete('/api/financas/lancamentos/' + str(created['id']), headers=h(owner)).status_code == 200
    assert client.get('/api/financas/resumo?data_inicio=2026-08-01&data_fim=2026-08-31', headers=h(owner)).json()['total_despesas_centavos'] == 0


def test_generate_entry_only_from_confirmed_analysis_and_no_duplicate():
    token = login('finance-receipt@example.com')
    with SessionLocal() as db:
        user = db.query(Usuario).filter(Usuario.email == 'finance-receipt@example.com').first()
        analysis = AnaliseComprovante(arquivo_id=999, usuario_id=user.id, status='confirmada', tipo_documento='comprovante_compra', dados_extraidos_json=json.dumps({'estabelecimento': 'Loja', 'valor_total': 42.5, 'data': '2026-08-30', 'moeda': 'BRL'}), confianca_geral=.95)
        db.add(analysis); db.commit(); db.refresh(analysis); analysis_id = analysis.id
    response = client.post(f'/api/analises/{analysis_id}/gerar-lancamento', headers=h(token))
    assert response.status_code == 200 and response.json()['status'] == 'criado'
    duplicate = client.post(f'/api/analises/{analysis_id}/gerar-lancamento', headers=h(token))
    assert duplicate.status_code == 200 and duplicate.json()['status'] == 'ja_existia'
