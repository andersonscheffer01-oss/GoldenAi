import os
import tempfile
os.environ['JARVIS_DATABASE_URL'] = 'sqlite:///' + tempfile.NamedTemporaryFile(suffix='.db', delete=False).name.replace('\\', '/')
os.environ['JARVIS_SECRET_KEY'] = 'test_secret_key_only_for_automated_tests'
os.environ['JARVIS_ENVIRONMENT'] = 'test'
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from datetime import datetime, timezone
from app.models import (Categoria, Usuario, OpenFinanceConnection, OpenFinanceAccount,
                        OpenFinanceBill, OpenFinanceTransaction)
from app.routers.pluggy_finance import upsert_transaction

client = TestClient(app)
def setup_module(): init_db()
def login(email):
    client.post('/api/auth/register',json={'nome':'Avancado','email':email,'senha':'senha-segura-123'})
    return client.post('/api/auth/login',json={'email':email,'senha':'senha-segura-123'}).json()['access_token']
def h(token): return {'Authorization':'Bearer '+token}

def test_category_hierarchy_archive_restore():
    token=login('advanced-category@example.com'); parent=client.post('/api/financas/categorias',headers=h(token),json={'nome':'Casa','tipo':'despesa'}).json(); child=client.post('/api/financas/categorias',headers=h(token),json={'nome':'Limpeza','categoria_pai_id':parent['id']}).json(); assert child['categoria_pai_id']==parent['id']; assert client.post(f"/api/financas/categorias/{child['id']}/arquivar",headers=h(token)).status_code==200; assert client.post(f"/api/financas/categorias/{child['id']}/restaurar",headers=h(token)).status_code==200; assert client.put(f"/api/financas/categorias/{parent['id']}",headers=h(token),json={'nome':'Casa','categoria_pai_id':parent['id']}).status_code==422

def test_budget_progress_and_alert():
    token=login('advanced-budget@example.com'); category=client.get('/api/financas/categorias',headers=h(token)).json()[0]; budget=client.post('/api/financas/orcamentos',headers=h(token),json={'categoria_id':category['id'],'nome':'Limite mensal','valor_limite_centavos':100000,'data_inicio':'2026-08-01T00:00:00','data_fim':'2026-08-31T23:59:59'}).json(); entry=client.post('/api/financas/lancamentos',headers=h(token),json={'tipo':'despesa','descricao':'Compra','valor':'800,00','data_compra':'2026-08-20','categoria_id':category['id']}); assert entry.status_code==201; progress=client.get(f"/api/financas/orcamentos/{budget['id']}/progresso",headers=h(token)).json(); assert progress['utilizado_centavos']==80000 and progress['status']=='atencao'; assert client.post('/api/financas/alertas/verificar',headers=h(token)).status_code==200; alerts=client.get('/api/alertas',headers=h(token)).json(); assert any(a['tipo']=='orcamento_80' for a in alerts)

def test_installment_sum_and_alert_lifecycle():
    token=login('advanced-installment@example.com'); category=client.get('/api/financas/categorias',headers=h(token)).json()[0]; plan=client.post('/api/financas/parcelamentos',headers=h(token),json={'descricao':'Compra parcelada','valor_total_centavos':1000,'total_parcelas':3,'valor_parcela_centavos':333,'data_compra':'2026-08-30T00:00:00','categoria_id':category['id']}).json(); details=client.get(f"/api/financas/parcelamentos/{plan['id']}",headers=h(token)).json(); assert sum(p['valor_centavos'] for p in details['parcelas'])==1000; alert=client.post('/api/alertas',headers=h(token),json={'titulo':'Lembrete','mensagem':'Teste'}).json(); assert client.post(f"/api/alertas/{alert['id']}/pausar",headers=h(token)).status_code==200; assert client.post(f"/api/alertas/{alert['id']}/ativar",headers=h(token)).status_code==200; assert client.post(f"/api/alertas/{alert['id']}/marcar-lido",headers=h(token)).status_code==200

def test_consolidated_dashboard_separates_balance_and_period():
    token=login('consolidated@example.com'); category=client.get('/api/financas/categorias',headers=h(token)).json()[0]
    client.post('/api/financas/lancamentos',headers=h(token),json={'tipo':'receita','descricao':'Receita','valor':'1000','data_compra':'2026-08-15','categoria_id':category['id']})
    client.post('/api/financas/lancamentos',headers=h(token),json={'tipo':'despesa','descricao':'Despesa','valor':'250','data_compra':'2026-08-16','categoria_id':category['id']})
    with SessionLocal() as db:
        user=db.query(Usuario).filter(Usuario.email=='consolidated@example.com').one(); conn=OpenFinanceConnection(usuario_id=user.id,external_link_id='item-consolidated',institution_name='Banco Teste');db.add(conn);db.flush();db.add(OpenFinanceAccount(usuario_id=user.id,connection_id=conn.id,external_id='account-consolidated',name='Conta corrente',type='BANK',current_balance_cents=345600));db.commit()
    data=client.get('/api/financas/consolidado?data_inicio=2026-08-01&data_fim=2026-08-31',headers=h(token)).json()
    assert data['saldo_atual_contas_centavos']==345600
    assert data['receitas_periodo_centavos']==100000 and data['despesas_periodo_centavos']==25000
    assert data['saldo_periodo_centavos']==75000

def test_professional_installments_invoices_and_alert_filters():
    token=login('professional@example.com'); category=client.get('/api/financas/categorias',headers=h(token)).json()[0]
    card=client.post('/api/financas/cartoes',headers=h(token),json={'nome':'Cartao BV','banco':'BV'}).json()
    plan=client.post('/api/financas/parcelamentos',headers=h(token),json={'descricao':'Financiamento veiculo','valor_total_centavos':120000,'total_parcelas':2,'valor_parcela_centavos':60000,'data_compra':'2026-08-01T00:00:00','categoria_id':category['id'],'cartao_id':card['id']}).json()
    details=client.get(f"/api/financas/parcelamentos/{plan['id']}",headers=h(token)).json()
    client.put(f"/api/financas/parcelas/{details['parcelas'][0]['id']}",headers=h(token),json={'numero':1,'valor_centavos':60000,'data_prevista':'2026-08-10T00:00:00'})
    installments=client.get('/api/financas/parcelas-profissional?mes=2026-08',headers=h(token)).json()
    assert installments['total_centavos']==60000 and installments['grupos'][0]['banco']=='BV'
    assert installments['grupos'][0]['parcelas'][0]['tipo_compromisso']=='financiamento_veiculo'
    alert=client.post('/api/alertas',headers=h(token),json={'tipo':'parcela_vencendo','titulo':'Parcela','mensagem':'Teste'}).json()
    assert len(client.get('/api/alertas?filtro=parcelas',headers=h(token)).json())==1
    assert client.post('/api/alertas/marcar-todos-lidos',headers=h(token)).json()['atualizados']>=1
    assert client.get('/api/alertas?filtro=nao_lidos',headers=h(token)).json()==[]

def test_pluggy_hash_fallback_and_bill_settlement_detection():
    token=login('dedup@example.com')
    with SessionLocal() as db:
        user=db.query(Usuario).filter(Usuario.email=='dedup@example.com').one();conn=OpenFinanceConnection(usuario_id=user.id,external_link_id='item-dedup');db.add(conn);db.flush();account=OpenFinanceAccount(usuario_id=user.id,connection_id=conn.id,external_id='acct-dedup',name='Conta',type='BANK');db.add(account);db.flush()
        row={'date':'2026-08-20T10:00:00Z','amount':-100,'description':'Pagamento de fatura'}
        assert upsert_transaction(db,user.id,conn.id,account,row) is True;db.flush()
        assert upsert_transaction(db,user.id,conn.id,account,row) is False
        tx=db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id==user.id).one()
        assert tx.external_id.startswith('hash:') and tx.flow_type=='settlement'
