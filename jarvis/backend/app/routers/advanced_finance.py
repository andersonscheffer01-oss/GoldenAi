from __future__ import annotations

import json
from calendar import monthrange
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..dependencies import client_ip, get_current_user, get_db
from ..models import AlertaFinanceiro, Cartao, Categoria, ContaFinanceira, LancamentoFinanceiro, Orcamento, Parcela, Parcelamento, NotificacaoPreferencia, PushSubscription, Usuario
from ..schemas import AlertaCreate, CartaoCreate, CategoriaAvancadaCreate, CategoriaAvancadaPublic, OrcamentoCreate, OrcamentoPublic, ParcelaCreate, ParcelamentoCreate, PushSubscribe
from ..services.alert_service import check_alerts
from ..services.default_categories import ensure_default_categories

router = APIRouter(prefix="/api", tags=["etapa-6"])

def dt(value):
    if not value: return None
    try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise HTTPException(422, "Data invalida.") from exc

def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year, month = value.year + month_index // 12, month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))

def own(db, model, ident, user):
    item = db.query(model).filter(model.id == ident, model.usuario_id == user.id).first()
    if not item: raise HTTPException(404, "Registro nao encontrado.")
    return item

@router.get("/financas/categorias", response_model=list[CategoriaAvancadaPublic])
def list_categories(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_default_categories(db, user.id)
    return db.query(Categoria).filter(Categoria.usuario_id == user.id).order_by(Categoria.ordem, Categoria.nome).all()

@router.post("/financas/categorias", response_model=CategoriaAvancadaPublic, status_code=201)
def add_category(payload: CategoriaAvancadaCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.tipo not in {"despesa", "receita"}: raise HTTPException(422, "Tipo invalido.")
    if payload.categoria_pai_id:
        parent = own(db, Categoria, payload.categoria_pai_id, user)
        if parent.categoria_pai_id == payload.categoria_pai_id: raise HTTPException(422, "Categoria nao pode ser filha dela mesma.")
    item = Categoria(usuario_id=user.id, **payload.model_dump()); db.add(item); db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "categoria_avancada_criada", "financas", item.nome, client_ip(request), True); return item

@router.put("/financas/categorias/{ident}", response_model=CategoriaAvancadaPublic)
def edit_category(ident: int, payload: CategoriaAvancadaCreate, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item = own(db, Categoria, ident, user)
    if payload.categoria_pai_id == ident: raise HTTPException(422, "Ciclo de categoria invalido.")
    if payload.categoria_pai_id: own(db, Categoria, payload.categoria_pai_id, user)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    db.commit(); return item

@router.post("/financas/categorias/{ident}/arquivar", response_model=CategoriaAvancadaPublic)
def archive_category(ident: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item = own(db, Categoria, ident, user); item.ativa = False; item.arquivada_em = datetime.now(timezone.utc); db.commit(); return item

@router.post("/financas/categorias/{ident}/restaurar", response_model=CategoriaAvancadaPublic)
def restore_category(ident: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item = own(db, Categoria, ident, user); item.ativa = True; item.arquivada_em = None; db.commit(); return item

@router.delete("/financas/categorias/{ident}")
def delete_category(ident: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item = own(db, Categoria, ident, user); item.ativa = False; item.arquivada_em = datetime.now(timezone.utc); db.commit(); return {"ok": True}

@router.post("/financas/orcamentos", response_model=OrcamentoPublic, status_code=201)
def add_budget(payload: OrcamentoCreate, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    own(db, Categoria, payload.categoria_id, user)
    if payload.periodicidade not in {"semanal", "mensal", "anual", "personalizado"}: raise HTTPException(422, "Periodicidade invalida.")
    item = Orcamento(usuario_id=user.id, categoria_id=payload.categoria_id, nome=payload.nome, valor_limite_centavos=payload.valor_limite_centavos, periodicidade=payload.periodicidade, data_inicio=dt(payload.data_inicio), data_fim=dt(payload.data_fim), alerta_50=payload.alerta_50, alerta_80=payload.alerta_80, alerta_100=payload.alerta_100, alerta_110=payload.alerta_110); db.add(item); db.commit(); db.refresh(item); return item

@router.get("/financas/orcamentos", response_model=list[OrcamentoPublic])
def list_budgets(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return db.query(Orcamento).filter(Orcamento.usuario_id == user.id, Orcamento.ativo.is_(True)).all()

@router.get("/financas/orcamentos/{ident}", response_model=OrcamentoPublic)
def get_budget(ident: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return own(db, Orcamento, ident, user)

@router.get("/financas/orcamentos/{ident}/progresso")
def budget_progress(ident: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = own(db, Orcamento, ident, user); q = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.categoria_id == budget.categoria_id, LancamentoFinanceiro.tipo == "despesa", LancamentoFinanceiro.status == "ativo", LancamentoFinanceiro.data_compra >= budget.data_inicio)
    if budget.data_fim: q = q.filter(LancamentoFinanceiro.data_compra <= budget.data_fim)
    used = sum(i.valor_centavos for i in q.all()); pct = used * 100 / budget.valor_limite_centavos; state = "excedido" if pct >= 110 else "limite_atingido" if pct >= 100 else "atencao" if pct >= 80 else "normal"
    return {"orcamento_id": ident, "categoria": db.get(Categoria, budget.categoria_id).nome, "periodo": {"inicio": budget.data_inicio.date().isoformat(), "fim": budget.data_fim.date().isoformat() if budget.data_fim else None}, "limite_centavos": budget.valor_limite_centavos, "utilizado_centavos": used, "restante_centavos": budget.valor_limite_centavos-used, "percentual_utilizado": round(pct, 2), "status": state}

@router.delete("/financas/orcamentos/{ident}")
def delete_budget(ident: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): budget=own(db, Orcamento, ident, user); budget.ativo=False; db.commit(); return {"ok": True}

@router.put("/financas/orcamentos/{ident}", response_model=OrcamentoPublic)
def edit_budget(ident: int, payload: OrcamentoCreate, user: Usuario=Depends(get_current_user), db:Session=Depends(get_db)):
    item=own(db, Orcamento, ident, user); own(db, Categoria, payload.categoria_id, user)
    for key,value in payload.model_dump().items(): setattr(item, key, dt(value) if key in ('data_inicio','data_fim') else value)
    db.commit(); db.refresh(item); return item

@router.post("/financas/parcelamentos", status_code=201)
def add_installment_plan(payload: ParcelamentoCreate, user: Usuario=Depends(get_current_user), db:Session=Depends(get_db)):
    own(db, Categoria, payload.categoria_id, user)
    if payload.cartao_id: own(db, Cartao, payload.cartao_id, user)
    item=Parcelamento(usuario_id=user.id, **payload.model_dump(exclude={'data_compra'}), data_compra=dt(payload.data_compra)); db.add(item); db.flush()
    values=[payload.valor_parcela_centavos]*(payload.total_parcelas-1); values.append(payload.valor_total_centavos-sum(values))
    purchase_date = item.data_compra
    for number,value in enumerate(values,1):
        due_date = add_months(purchase_date, number - 1)
        db.add(Parcela(parcelamento_id=item.id,usuario_id=user.id,numero=number,
                       valor_centavos=value,data_prevista=due_date,status='prevista'))
    db.commit(); db.refresh(item); return item

@router.get("/financas/parcelamentos")
def list_plans(user:Usuario=Depends(get_current_user), db:Session=Depends(get_db)): return db.query(Parcelamento).filter(Parcelamento.usuario_id==user.id,Parcelamento.ativo.is_(True)).all()
@router.get("/financas/parcelamentos/{ident}")
def get_plan(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):
    item=own(db,Parcelamento,ident,user); return {"id":item.id,"descricao":item.descricao,"valor_total_centavos":item.valor_total_centavos,"total_parcelas":item.total_parcelas,"parcelas":[{"id":p.id,"numero":p.numero,"valor_centavos":p.valor_centavos,"data_prevista":p.data_prevista,"status":p.status} for p in db.query(Parcela).filter(Parcela.parcelamento_id==item.id).order_by(Parcela.numero)]}
@router.delete("/financas/parcelamentos/{ident}")
def delete_plan(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): item=own(db,Parcelamento,ident,user); item.ativo=False; db.commit(); return {"ok":True}
@router.post("/financas/parcelamentos/{ident}/parcelas", status_code=201)
def add_plan_installment(ident:int,payload:ParcelaCreate,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):
    plan=own(db,Parcelamento,ident,user); item=Parcela(parcelamento_id=plan.id,usuario_id=user.id,numero=payload.numero,valor_centavos=payload.valor_centavos,data_prevista=dt(payload.data_prevista),status='prevista' if payload.data_prevista else 'sem_data'); db.add(item); db.commit(); db.refresh(item); return item
@router.put("/financas/parcelas/{ident}")
def edit_installment(ident:int,payload:ParcelaCreate,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):
    item=own(db,Parcela,ident,user); item.numero=payload.numero; item.valor_centavos=payload.valor_centavos; item.data_prevista=dt(payload.data_prevista); item.status='prevista' if payload.data_prevista else 'sem_data'; db.commit(); return item
@router.post("/financas/parcelas/{ident}/marcar-paga")
def pay_installment(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): item=own(db,Parcela,ident,user); item.status='paga'; db.commit(); return {"ok":True}
@router.post("/financas/parcelas/{ident}/cancelar")
def cancel_installment(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): item=own(db,Parcela,ident,user); item.status='cancelada'; db.commit(); return {"ok":True}

@router.post("/alertas", response_model=dict, status_code=201)
def add_alert(payload: AlertaCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item=AlertaFinanceiro(usuario_id=user.id, **payload.model_dump(exclude={"data_agendada"}), data_agendada=dt(payload.data_agendada)); db.add(item); db.commit(); db.refresh(item); registrar_auditoria(db,user.id,"alerta_criado","alertas",item.titulo,client_ip(request),True); return {"id":item.id,"tipo":item.tipo,"titulo":item.titulo,"mensagem":item.mensagem,"status":item.status,"lido":False}

def public_alert(a):
    return {"id":a.id,"tipo":a.tipo,"titulo":a.titulo,"mensagem":a.mensagem,"status":a.status,"lido":bool(a.lido_em),"data_agendada":a.data_agendada,"categoria_id":a.categoria_id,"orcamento_id":a.orcamento_id,"cartao_id":a.cartao_id,"parcela_id":a.parcela_id,"percentual_gatilho":a.percentual_gatilho,"criado_em":a.criado_em}

@router.get("/alertas")
def list_alerts(filtro:str="todos",user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    q=db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id==user.id,AlertaFinanceiro.status!='cancelado')
    if filtro=="nao_lidos":q=q.filter(AlertaFinanceiro.lido_em.is_(None))
    elif filtro!="todos":
        aliases={"orcamentos":"orcamento","parcelas":"parcela","faturas":"fatura","lembretes":"lembrete","open_finance":"open_finance","sistema":"sistema"}
        term=aliases.get(filtro,filtro);q=q.filter(AlertaFinanceiro.tipo.ilike(f"%{term}%"))
    return [public_alert(a) for a in q.order_by(AlertaFinanceiro.id.desc()).all()]

@router.get("/alertas/contagem")
def alert_count(user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):
    return {"nao_lidos":db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id==user.id,AlertaFinanceiro.status!='cancelado',AlertaFinanceiro.lido_em.is_(None)).count()}

@router.post("/alertas/marcar-todos-lidos")
def read_all_alerts(user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):
    now=datetime.now(timezone.utc);rows=db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id==user.id,AlertaFinanceiro.status!='cancelado',AlertaFinanceiro.lido_em.is_(None)).all()
    for row in rows:row.lido_em=now
    db.commit();return {"ok":True,"atualizados":len(rows)}

@router.get("/alertas/{ident}")
def alert_detail(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):return public_alert(own(db,AlertaFinanceiro,ident,user))

@router.post("/alertas/{ident}/pausar")
def pause_alert(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): a=own(db,AlertaFinanceiro,ident,user); a.status='pausado'; db.commit(); return {"ok":True}
@router.post("/alertas/{ident}/ativar")
def activate_alert(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): a=own(db,AlertaFinanceiro,ident,user); a.status='ativo'; db.commit(); return {"ok":True}
@router.post("/alertas/{ident}/marcar-lido")
def read_alert(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): a=own(db,AlertaFinanceiro,ident,user); a.lido_em=datetime.now(timezone.utc); db.commit(); return {"ok":True}
@router.post("/alertas/{ident}/cancelar")
def cancel_alert_action(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):a=own(db,AlertaFinanceiro,ident,user);a.status='cancelado';db.commit();return {"ok":True}
@router.delete("/alertas/{ident}")
def cancel_alert(ident:int,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)): a=own(db,AlertaFinanceiro,ident,user); a.status='cancelado'; db.commit(); return {"ok":True}

@router.post("/notificacoes/subscribe")
def subscribe(payload: PushSubscribe, user: Usuario=Depends(get_current_user), db: Session=Depends(get_db)):
    item=db.query(PushSubscription).filter(PushSubscription.endpoint==payload.endpoint).first()
    if item: item.usuario_id=user.id; item.subscription_json=json.dumps(payload.model_dump()); item.ativo=True
    else: db.add(PushSubscription(usuario_id=user.id,endpoint=payload.endpoint,subscription_json=json.dumps(payload.model_dump())))
    db.commit(); return {"ok":True,"message":"Inscricao registrada. Push exige HTTPS."}

@router.delete("/notificacoes/subscribe")
def unsubscribe(payload: PushSubscribe, user: Usuario=Depends(get_current_user), db: Session=Depends(get_db)):
    item=db.query(PushSubscription).filter(PushSubscription.endpoint==payload.endpoint,PushSubscription.usuario_id==user.id).first()
    if item: item.ativo=False; db.commit()
    return {"ok":True}

@router.get("/notificacoes/preferencias")
def get_preferences(user: Usuario=Depends(get_current_user), db: Session=Depends(get_db)):
    item=db.query(NotificacaoPreferencia).filter(NotificacaoPreferencia.usuario_id==user.id).first()
    if not item: item=NotificacaoPreferencia(usuario_id=user.id); db.add(item); db.commit(); db.refresh(item)
    return {key:getattr(item,key) for key in ('alertas_financeiros','alertas_orcamento','alertas_parcelas','resumo_diario','resumo_semanal','horario','push_ativado')}

@router.post("/financas/alertas/verificar")
def run_alerts(user: Usuario=Depends(get_current_user), db:Session=Depends(get_db)): return {"criados":check_alerts(db)}
