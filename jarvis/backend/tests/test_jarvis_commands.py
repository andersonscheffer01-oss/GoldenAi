from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from app.services.intent_service import money

client=TestClient(app)
def setup_module(): init_db()
def login(email):
    client.post('/api/auth/register',json={'nome':'Comandos','email':email,'senha':'senha-segura-123'})
    return client.post('/api/auth/login',json={'email':email,'senha':'senha-segura-123'}).json()['access_token']
def h(token): return {'Authorization':'Bearer '+token}
def test_money_parser_and_explicit_confirmation():
    assert money('R$ 50') == 5000 and money('R$ 42,50') == 4250 and money('R$ 1.250,90') == 125090
    token=login('commands@example.com')
    prepared=client.post('/api/jarvis/comando',headers=h(token),json={'content':'Registre R$ 50 no mercado'})
    assert prepared.status_code==200 and prepared.json()['status']=='aguardando_confirmacao'
    pending=client.get('/api/jarvis/acoes-pendentes',headers=h(token)).json(); assert len(pending)==1
    executed=client.post(f"/api/jarvis/acoes/{pending[0]['id']}/confirmar",headers=h(token))
    assert executed.status_code==200 and executed.json()['status']=='executado'
    assert client.get('/api/jarvis/acoes-pendentes',headers=h(token)).json()==[]
def test_command_without_value_asks_and_cancel_does_not_create():
    token=login('commands-cancel@example.com')
    response=client.post('/api/jarvis/comando',headers=h(token),json={'content':'Registre um gasto no mercado'})
    assert response.json()['status']=='esclarecimento'
    response=client.post('/api/jarvis/comando',headers=h(token),json={'content':'Registre R$ 10 no mercado'})
    action=response.json()['acao_id']; cancelled=client.post(f'/api/jarvis/acoes/{action}/cancelar',headers=h(token)); assert cancelled.json()['status']=='cancelado'
