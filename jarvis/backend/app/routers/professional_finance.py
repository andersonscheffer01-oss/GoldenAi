from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import (AlertaFinanceiro, Cartao, LancamentoFinanceiro, OpenFinanceAccount,
                      OpenFinanceBill, OpenFinanceConnection, OpenFinanceTransaction,
                      Parcela, Parcelamento, Usuario)

router = APIRouter(prefix="/api/financas", tags=["financas-consolidadas"])


def date_bounds(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    try:
        a = date.fromisoformat(start) if start else date.today().replace(day=1)
        b = date.fromisoformat(end) if end else date.today()
    except ValueError as exc: raise HTTPException(422, "Periodo invalido.") from exc
    if b < a: raise HTTPException(422, "Periodo invalido.")
    return datetime.combine(a, time.min, timezone.utc), datetime.combine(b, time.max, timezone.utc)


def effective_status(item: Parcela, now: datetime) -> str:
    if item.status in {"paga", "cancelada"}: return item.status
    if item.data_prevista and item.data_prevista.date() < now.date(): return "atrasada"
    return "aberta" if item.data_prevista else "sem_data"


def commitment_type(description: str) -> str:
    text = description.casefold()
    if any(x in text for x in ("veiculo", "veículo", "carro")): return "financiamento_veiculo"
    if "emprest" in text: return "emprestimo"
    if "financ" in text: return "financiamento_pessoal"
    if "assinatura" in text: return "assinatura_recorrente"
    return "compra_parcelada"

def fallback_due_date(purchase_date: datetime, number: int) -> datetime:
    month_index = purchase_date.month - 1 + number - 1
    year, month = purchase_date.year + month_index // 12, month_index % 12 + 1
    return purchase_date.replace(year=year, month=month, day=min(purchase_date.day, monthrange(year, month)[1]))

def utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@router.get("/consolidado")
def consolidated(data_inicio: str | None = None, data_fim: str | None = None,
                 banco: str | None = None, conta_id: int | None = None,
                 cartao_id: int | None = None, categoria_id: int | None = None,
                 user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    start, end = date_bounds(data_inicio, data_fim)
    q = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == user.id,
        LancamentoFinanceiro.status == "ativo", LancamentoFinanceiro.data_compra >= start,
        LancamentoFinanceiro.data_compra <= end)
    if conta_id: q = q.filter(LancamentoFinanceiro.conta_id == conta_id)
    if cartao_id: q = q.filter(LancamentoFinanceiro.cartao_id == cartao_id)
    if categoria_id: q = q.filter(LancamentoFinanceiro.categoria_id == categoria_id)
    entries = q.all()
    imported_entry_ids = {x.imported_entry_id for x in db.query(OpenFinanceTransaction).filter(
        OpenFinanceTransaction.usuario_id == user.id,
        OpenFinanceTransaction.imported_entry_id.isnot(None),
    ).all()}
    income = sum(x.valor_centavos for x in entries if x.tipo == "receita")
    expenses = sum(x.valor_centavos for x in entries if x.tipo == "despesa")
    connections = {c.id: c for c in db.query(OpenFinanceConnection).filter(OpenFinanceConnection.usuario_id == user.id)}
    accounts = [a for a in db.query(OpenFinanceAccount).filter(OpenFinanceAccount.usuario_id == user.id).all() if str(a.type or "").upper() == "BANK"]
    if banco: accounts = [a for a in accounts if banco.casefold() in str(connections.get(a.connection_id).institution_name if connections.get(a.connection_id) else "").casefold()]
    # Open Finance transactions are included even before manual import. Imported
    # rows are skipped here to avoid counting the same purchase twice.
    of_query = db.query(OpenFinanceTransaction).filter(
        OpenFinanceTransaction.usuario_id == user.id,
        OpenFinanceTransaction.occurred_at >= start,
        OpenFinanceTransaction.occurred_at <= end,
        OpenFinanceTransaction.import_status.in_(["available", "pending_confirmation"]),
        OpenFinanceTransaction.flow_type.in_(["income", "expense"]),
    )
    open_transactions = [t for t in of_query.all() if t.imported_entry_id not in imported_entry_ids]
    if banco:
        allowed_connections = {c.id for c in connections.values() if banco.casefold() in str(c.institution_name or "").casefold()}
        open_transactions = [t for t in open_transactions if t.connection_id in allowed_connections]
    income += sum(t.amount_cents or 0 for t in open_transactions if t.flow_type == "income")
    expenses += sum(t.amount_cents or 0 for t in open_transactions if t.flow_type == "expense")
    bills = db.query(OpenFinanceBill).filter(OpenFinanceBill.usuario_id == user.id).all()
    open_bills = [b for b in bills if b.due_date and start.date() <= b.due_date.date() <= end.date()
                  and str(b.status or "").upper() not in {"PAID", "CLOSED", "CANCELLED"}]
    if banco:
        allowed_connections = {c.id for c in connections.values() if banco.casefold() in str(c.institution_name or "").casefold()}
        open_bills = [b for b in open_bills if b.connection_id in allowed_connections]
    parts = db.query(Parcela).filter(Parcela.usuario_id == user.id, Parcela.data_prevista >= start, Parcela.data_prevista <= end, Parcela.status != "cancelada").all()
    unread = db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id == user.id, AlertaFinanceiro.status != "cancelado", AlertaFinanceiro.lido_em.is_(None)).count()
    pending_rows = db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user.id, OpenFinanceTransaction.import_status.in_(["available", "pending_confirmation"])).all()
    account_names = {a.external_id: a.name for a in db.query(OpenFinanceAccount).filter(OpenFinanceAccount.usuario_id == user.id).all()}
    pending = len(pending_rows)
    pending_value = sum(t.amount_cents or 0 for t in pending_rows)
    account_balances = {}
    for account in accounts:
        name = connections.get(account.connection_id).institution_name if connections.get(account.connection_id) else "Instituição"
        account_balances.setdefault(name, {"instituicao": name, "saldo_centavos": 0, "contas": 0, "ultima_atualizacao": connections.get(account.connection_id).last_sync_at if connections.get(account.connection_id) else None})
        account_balances[name]["saldo_centavos"] += account.current_balance_cents or 0; account_balances[name]["contas"] += 1
    last_sync = max((c.last_sync_at for c in connections.values() if c.last_sync_at), default=None)
    return {"periodo":{"inicio":start.date().isoformat(),"fim":end.date().isoformat()},
        "saldo_atual_contas_centavos":sum(a.current_balance_cents or 0 for a in accounts),
        "receitas_periodo_centavos":income,"despesas_periodo_centavos":expenses,"saldo_periodo_centavos":income-expenses,
        "faturas_abertas_centavos":sum(b.total_cents or 0 for b in open_bills),
        "parcelas_periodo_centavos":sum(p.valor_centavos for p in parts if effective_status(p,datetime.now(timezone.utc))!="paga"),
        "alertas_nao_lidos":unread,"importacoes_pendentes":pending,"importacoes_pendentes_centavos":pending_value,"ultima_sincronizacao":last_sync,
        "saldos_por_instituicao":list(account_balances.values()),
        "itens_total":len(connections),
        "importacoes_pendentes_detalhes":[{"id":t.id,"instituicao":connections.get(t.connection_id).institution_name if connections.get(t.connection_id) else "Instituição","conta_ou_cartao":account_names.get(t.account_external_id,"Não informado"),"valor_centavos":t.amount_cents,"status":t.import_status} for t in pending_rows],
        "contas":[{"id":a.id,"nome":a.name,"banco":connections.get(a.connection_id).institution_name if connections.get(a.connection_id) else None,"saldo_centavos":a.current_balance_cents,"disponivel_centavos":a.available_balance_cents,"atualizado_em":a.updated_at,"origem":"open_finance"} for a in accounts]}


@router.get("/parcelas-profissional")
def installments(mes: str = Query(default_factory=lambda: date.today().strftime("%Y-%m")), banco: str | None = None,
                 cartao_id: int | None = None, situacao: str | None = None,
                 user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        year, month = map(int, mes.split("-")); start = datetime(year,month,1,tzinfo=timezone.utc); end = datetime(year,month,monthrange(year,month)[1],23,59,59,tzinfo=timezone.utc)
    except (ValueError,TypeError) as exc: raise HTTPException(422,"Mes invalido.") from exc
    # Do not filter NULL due dates in SQL: older records may have been created
    # before monthly due dates were persisted and are repaired by fallback_due_date.
    q=db.query(Parcela,Parcelamento).join(Parcelamento,Parcela.parcelamento_id==Parcelamento.id).filter(Parcela.usuario_id==user.id,Parcelamento.ativo.is_(True))
    if cartao_id:q=q.filter(Parcelamento.cartao_id==cartao_id)
    cards={c.id:c for c in db.query(Cartao).filter(Cartao.usuario_id==user.id)}; rows=[]; now=datetime.now(timezone.utc)
    for part,plan in q.all():
        due_date = utc_datetime(part.data_prevista or fallback_due_date(utc_datetime(plan.data_compra), part.numero))
        if not (start <= due_date <= end):
            continue
        card=cards.get(plan.cartao_id); bank=card.banco if card else "Não informado"; status=effective_status(part,now)
        if part.data_prevista is None:
            status = "atrasada" if due_date.date() < now.date() else "aberta"
        if banco and banco.casefold() not in str(bank).casefold():continue
        if situacao and status!=situacao:continue
        rows.append({"id":part.id,"parcelamento_id":plan.id,"descricao":plan.descricao,"banco":bank,"cartao":card.nome if card else "Não informado","cartao_id":plan.cartao_id,"numero":part.numero,"total_parcelas":plan.total_parcelas,"valor_centavos":part.valor_centavos,"vencimento":due_date,"situacao":status,"origem":"manual","tipo_compromisso":commitment_type(plan.descricao)})
    # Card providers commonly encode installment position as "item 03/12" in
    # the transaction description. Expose those bank-provided installments
    # without creating duplicate manual financial entries.
    accounts = {a.external_id: a for a in db.query(OpenFinanceAccount).filter(OpenFinanceAccount.usuario_id == user.id).all()}
    connections = {c.id: c for c in db.query(OpenFinanceConnection).filter(OpenFinanceConnection.usuario_id == user.id).all()}
    for tx in db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user.id).all():
        match = re.search(r"(?:^|\D)(\d{1,2})\s*/\s*(\d{1,2})(?:\D|$)", tx.description or "")
        if not match or tx.flow_type != "expense":
            continue
        number, total = map(int, match.groups())
        if number < 1 or total < number or total < 2:
            continue
        if not tx.occurred_at:
            continue
        due = utc_datetime(tx.occurred_at)
        if not (start <= due <= end):
            continue
        conn = connections.get(tx.connection_id); account = accounts.get(tx.account_external_id)
        bank = conn.institution_name if conn else "Open Finance"
        if banco and banco.casefold() not in bank.casefold():
            continue
        rows.append({"id": f"of-{tx.id}", "parcelamento_id": None, "descricao": tx.description,
                     "banco": bank, "cartao": account.name if account else "Cartão Open Finance",
                     "cartao_id": None, "numero": number, "total_parcelas": total,
                     "valor_centavos": tx.amount_cents, "vencimento": due,
                     "situacao": "paga" if str(tx.status or "").upper() in {"POSTED", "SETTLED"} else "aberta",
                     "origem": "open_finance", "tipo_compromisso": "compra_parcelada"})
    groups={}
    for row in rows:
        group=groups.setdefault(row["banco"],{"banco":row["banco"],"total_centavos":0,"parcelas":[]});group["total_centavos"]+=row["valor_centavos"];group["parcelas"].append(row)
    total=lambda status:sum(r["valor_centavos"] for r in rows if r["situacao"]==status)
    return {"mes":mes,"total_centavos":sum(r["valor_centavos"] for r in rows),"pago_centavos":total("paga"),"aberto_centavos":total("aberta"),"atrasado_centavos":total("atrasada"),"quantidade":len(rows),"grupos":list(groups.values())}


@router.get("/faturas-profissional")
def invoices(data_inicio: str | None=None,data_fim: str|None=None,user:Usuario=Depends(get_current_user),db:Session=Depends(get_db)):
    start,end=date_bounds(data_inicio,data_fim);accounts={a.external_id:a for a in db.query(OpenFinanceAccount).filter(OpenFinanceAccount.usuario_id==user.id)};connections={c.id:c for c in db.query(OpenFinanceConnection).filter(OpenFinanceConnection.usuario_id==user.id)};items=[]
    for bill in db.query(OpenFinanceBill).filter(OpenFinanceBill.usuario_id==user.id).all():
        if bill.due_date and not(start.date()<=bill.due_date.date()<=end.date()):continue
        account=accounts.get(bill.account_external_id);conn=connections.get(bill.connection_id)
        situacao = bill.status or "não informado"; late = bill.due_date and bill.due_date.date() < date.today() and str(situacao).upper() not in {"PAID","CLOSED","CANCELLED"}
        items.append({"id":bill.id,"banco":conn.institution_name if conn else "Não informado","cartao":account.name if account else "Não informado","vencimento":bill.due_date,"total_centavos":bill.total_cents,"minimo_centavos":bill.minimum_cents,"situacao":situacao,"atrasada":late,"atualizado_em":bill.updated_at,"origem":"open_finance"})
    open_items=[x for x in items if str(x["situacao"]).upper() not in {"PAID","CLOSED","CANCELLED"}]
    paid_items=[x for x in items if str(x["situacao"]).upper() in {"PAID","CLOSED"}]
    return {"total_aberto_centavos":sum(x["total_centavos"] or 0 for x in open_items),"total_pago_centavos":sum(x["total_centavos"] or 0 for x in paid_items),"total_atrasado_centavos":sum(x["total_centavos"] or 0 for x in items if x["atrasada"]),"faturas":items}
