from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..dependencies import client_ip, get_current_user, get_db
from ..models import AlertaFinanceiro, AnaliseComprovante, Cartao, Categoria, ContaFinanceira, LancamentoFinanceiro, Parcela, Usuario, utc_now
from ..schemas import CartaoCreate, CartaoPublic, CategoriaAvancadaCreate, CategoriaPublic, ContaCreate, ContaPublic, LancamentoCreate, LancamentoPublic
from ..services.default_categories import ensure_default_categories

router = APIRouter(prefix="/api/financas", tags=["financas"])
receipt_router = APIRouter(prefix="/api", tags=["financas"])
PAYMENTS = {"dinheiro", "pix", "debito", "credito", "transferencia", "boleto", "outro"}
TYPES = {"despesa", "receita"}
ACCOUNT_TYPES = {"conta_corrente", "conta_poupanca", "dinheiro", "carteira", "outro"}


def cents(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_date(value: str) -> datetime:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "Data invalida. Use YYYY-MM-DD.") from exc
    return datetime.combine(parsed, time.min, tzinfo=timezone.utc)


def public(item: LancamentoFinanceiro) -> LancamentoPublic:
    return LancamentoPublic.model_validate(item)


def validate_refs(db: Session, payload: LancamentoCreate, user: Usuario) -> None:
    if payload.tipo not in TYPES: raise HTTPException(422, "Tipo de lancamento invalido.")
    if payload.valor <= 0: raise HTTPException(422, "O valor deve ser maior que zero.")
    if payload.forma_pagamento and payload.forma_pagamento not in PAYMENTS: raise HTTPException(422, "Forma de pagamento invalida.")
    if not db.query(Categoria).filter(Categoria.id == payload.categoria_id, Categoria.usuario_id == user.id, Categoria.ativa.is_(True)).first():
        raise HTTPException(422, "Categoria invalida.")
    if payload.conta_id and not db.query(ContaFinanceira).filter(ContaFinanceira.id == payload.conta_id, ContaFinanceira.usuario_id == user.id, ContaFinanceira.ativo.is_(True)).first():
        raise HTTPException(422, "Conta invalida.")
    if payload.cartao_id and not db.query(Cartao).filter(Cartao.id == payload.cartao_id, Cartao.usuario_id == user.id, Cartao.ativo.is_(True)).first():
        raise HTTPException(422, "Cartao invalido.")


@router.get("/categorias", response_model=list[CategoriaPublic])
def categories(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_default_categories(db, user.id)
    return db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.ativa.is_(True)).order_by(Categoria.nome).all()


@router.post("/categorias", response_model=CategoriaPublic, status_code=201)
def create_category(payload: CategoriaAvancadaCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.tipo not in TYPES: raise HTTPException(422, "Tipo de categoria invalido.")
    if payload.categoria_pai_id:
        parent = db.query(Categoria).filter(Categoria.id == payload.categoria_pai_id, Categoria.usuario_id == user.id).first()
        if not parent: raise HTTPException(422, "Categoria pai invalida.")
    item = Categoria(usuario_id=user.id, **payload.model_dump(exclude_none=True))
    db.add(item); db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "categoria_criada", "financas", item.nome, client_ip(request), True)
    return item


@router.get("/contas", response_model=list[ContaPublic])
def accounts(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(ContaFinanceira).filter(ContaFinanceira.usuario_id == user.id, ContaFinanceira.ativo.is_(True)).order_by(ContaFinanceira.nome).all()


@router.post("/contas", response_model=ContaPublic, status_code=201)
def create_account(payload: ContaCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.tipo not in ACCOUNT_TYPES: raise HTTPException(422, "Tipo de conta invalido.")
    item = ContaFinanceira(usuario_id=user.id, nome=payload.nome.strip(), banco=payload.banco, tipo=payload.tipo)
    db.add(item); db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "conta_criada", "financas", item.nome, client_ip(request), True)
    return item


@router.get("/cartoes", response_model=list[CartaoPublic])
def cards(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Cartao).filter(Cartao.usuario_id == user.id, Cartao.ativo.is_(True)).order_by(Cartao.nome).all()


@router.post("/cartoes", response_model=CartaoPublic, status_code=201)
def create_card(payload: CartaoCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    digits = payload.ultimos_quatro_digitos
    if digits and (not digits.isdigit() or len(digits) > 4): raise HTTPException(422, "Informe somente os ultimos quatro digitos.")
    item = Cartao(usuario_id=user.id, **payload.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "cartao_criado", "financas", item.nome, client_ip(request), True)
    return item


@router.post("/lancamentos", response_model=LancamentoPublic, status_code=201)
def create_entry(payload: LancamentoCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    validate_refs(db, payload, user)
    item = LancamentoFinanceiro(usuario_id=user.id, tipo=payload.tipo, descricao=payload.descricao.strip(), valor_centavos=cents(payload.valor), data_compra=parse_date(payload.data_compra), **{key: value for key, value in payload.model_dump().items() if key not in {"tipo", "descricao", "valor", "data_compra"}})
    if payload.total_parcelas and payload.total_parcelas > 1: item.valor_parcela_centavos = item.valor_centavos // payload.total_parcelas
    db.add(item); db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "lancamento_criado", "financas", item.descricao, client_ip(request), True)
    return item


def query_entries(db: Session, user: Usuario, data_inicio: str | None = None, data_fim: str | None = None, categoria_id: int | None = None, forma_pagamento: str | None = None, conta_id: int | None = None, cartao_id: int | None = None, tipo: str | None = None):
    query = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.status == "ativo")
    if data_inicio: query = query.filter(LancamentoFinanceiro.data_compra >= parse_date(data_inicio))
    if data_fim: query = query.filter(LancamentoFinanceiro.data_compra < parse_date(data_fim).replace(hour=23, minute=59, second=59))
    if categoria_id: query = query.filter(LancamentoFinanceiro.categoria_id == categoria_id)
    if forma_pagamento: query = query.filter(LancamentoFinanceiro.forma_pagamento == forma_pagamento)
    if conta_id: query = query.filter(LancamentoFinanceiro.conta_id == conta_id)
    if cartao_id: query = query.filter(LancamentoFinanceiro.cartao_id == cartao_id)
    if tipo: query = query.filter(LancamentoFinanceiro.tipo == tipo)
    return query.order_by(LancamentoFinanceiro.data_compra.desc(), LancamentoFinanceiro.id.desc())


@router.get("/lancamentos", response_model=list[LancamentoPublic])
def list_entries(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db), data_inicio: str | None = None, data_fim: str | None = None, categoria_id: int | None = None, forma_pagamento: str | None = None, conta_id: int | None = None, cartao_id: int | None = None, tipo: str | None = None):
    return query_entries(db, user, data_inicio, data_fim, categoria_id, forma_pagamento, conta_id, cartao_id, tipo).all()


def detailed_entry(item, categories_by_id, accounts_by_id, cards_by_id, receipts_by_analysis):
    data = public(item).model_dump(mode="json")
    data.update({
        "categoria_nome": categories_by_id.get(item.categoria_id),
        "conta_nome": accounts_by_id.get(item.conta_id),
        "cartao_nome": cards_by_id.get(item.cartao_id),
        "tem_comprovante": item.analise_comprovante_id is not None,
        "comprovante_arquivo_id": receipts_by_analysis.get(item.analise_comprovante_id),
    })
    return data


@router.get("/lancamentos-paginados")
def paginated_entries(
    user: Usuario = Depends(get_current_user), db: Session = Depends(get_db),
    data_inicio: str | None = None, data_fim: str | None = None,
    categoria_id: int | None = None, forma_pagamento: str | None = None,
    conta_id: int | None = None, cartao_id: int | None = None,
    tipo: str | None = None, pagina: int = 1, por_pagina: int = 10,
):
    pagina = max(1, pagina)
    por_pagina = min(50, max(1, por_pagina))
    query = query_entries(db, user, data_inicio, data_fim, categoria_id, forma_pagamento, conta_id, cartao_id, tipo)
    total = query.count()
    items = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    categories_by_id = {item.id: item.nome for item in db.query(Categoria).filter(Categoria.usuario_id == user.id)}
    accounts_by_id = {item.id: item.nome for item in db.query(ContaFinanceira).filter(ContaFinanceira.usuario_id == user.id)}
    cards_by_id = {item.id: item.nome for item in db.query(Cartao).filter(Cartao.usuario_id == user.id)}
    receipts_by_analysis = {item.id: item.arquivo_id for item in db.query(AnaliseComprovante).filter(AnaliseComprovante.usuario_id == user.id)}
    return {
        "itens": [detailed_entry(item, categories_by_id, accounts_by_id, cards_by_id, receipts_by_analysis) for item in items],
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": (total + por_pagina - 1) // por_pagina,
    }


def own_entry(db, entry_id, user):
    item = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.id == entry_id, LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.status == "ativo").first()
    if not item: raise HTTPException(404, "Lancamento nao encontrado.")
    return item


@router.get("/lancamentos/{entry_id}", response_model=LancamentoPublic)
def get_entry(entry_id: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return own_entry(db, entry_id, user)


@router.put("/lancamentos/{entry_id}", response_model=LancamentoPublic)
def update_entry(entry_id: int, payload: LancamentoCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item = own_entry(db, entry_id, user); validate_refs(db, payload, user)
    for key, value in payload.model_dump().items():
        if key == "valor": item.valor_centavos = cents(value)
        elif key == "data_compra": item.data_compra = parse_date(value)
        elif hasattr(item, key): setattr(item, key, value)
    db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "lancamento_editado", "financas", item.descricao, client_ip(request), True)
    return item


@router.delete("/lancamentos/{entry_id}")
def delete_entry(entry_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    item = own_entry(db, entry_id, user); item.status = "excluido"; item.excluido_em = utc_now(); db.commit()
    registrar_auditoria(db, user.id, "lancamento_excluido", "financas", item.descricao, client_ip(request), True)
    return {"ok": True, "message": "Lancamento excluido"}


@receipt_router.post("/analises/{analise_id}/gerar-lancamento")
def create_from_receipt(analise_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(AnaliseComprovante).filter(AnaliseComprovante.id == analise_id, AnaliseComprovante.usuario_id == user.id).first()
    if not analysis or analysis.status != "confirmada":
        raise HTTPException(422, {"code": "ANALYSIS_NOT_CONFIRMED", "message": "A analise precisa estar confirmada antes de criar o lancamento."})
    existing = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.analise_comprovante_id == analise_id).first()
    if existing:
        return {"status": "ja_existia", "lancamento_id": existing.id, "mensagem": "Este comprovante ja possui um lancamento financeiro."}
    data = json.loads(analysis.dados_extraidos_json or "{}")
    if data.get("valor_total") is None:
        raise HTTPException(422, {"status": "erro", "code": "MISSING_TOTAL_VALUE", "message": "E necessario informar o valor total antes de criar o lancamento."})
    categoria = db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome == "Outros", Categoria.ativa.is_(True)).first()
    if not categoria:
        categoria = Categoria(usuario_id=user.id, nome="Outros", tipo="despesa"); db.add(categoria); db.flush()
    payment = data.get("forma_pagamento") if data.get("forma_pagamento") in PAYMENTS else None
    digits = data.get("ultimos_quatro_digitos")
    card = db.query(Cartao).filter(Cartao.usuario_id == user.id, Cartao.ultimos_quatro_digitos == digits).first() if digits else None
    entry = LancamentoFinanceiro(
        usuario_id=user.id, tipo="despesa", descricao=data.get("estabelecimento") or "Comprovante", valor_centavos=cents(Decimal(str(data["valor_total"]))),
        moeda=data.get("moeda") or "BRL", data_compra=parse_date(str(data.get("data") or datetime.now().date().isoformat()).split("T", 1)[0]),
        hora_compra=data.get("hora"), categoria_id=categoria.id, cartao_id=card.id if card else None,
        forma_pagamento=payment, estabelecimento=data.get("estabelecimento"), cnpj=data.get("cnpj"), observacoes=data.get("observacoes"), origem="comprovante", analise_comprovante_id=analise_id,
        numero_parcela=data.get("numero_parcela"), total_parcelas=data.get("total_parcelas"), valor_parcela_centavos=cents(Decimal(str(data["valor_parcela"]))) if data.get("valor_parcela") is not None else None,
    )
    db.add(entry); db.commit(); db.refresh(entry)
    registrar_auditoria(db, user.id, "lancamento_comprovante_criado", "financas", str(entry.id), client_ip(request), True)
    return {"status": "criado", "lancamento_id": entry.id, "mensagem": "Lancamento financeiro criado com sucesso."}


def filters(request):
    return request.query_params


def optional_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(422, "Filtro numerico invalido.") from exc


def query_options(request: Request) -> dict:
    return {
        "data_inicio": request.query_params.get("data_inicio"),
        "data_fim": request.query_params.get("data_fim"),
        "categoria_id": optional_int(request.query_params.get("categoria_id")),
        "forma_pagamento": request.query_params.get("forma_pagamento"),
        "conta_id": optional_int(request.query_params.get("conta_id")),
        "cartao_id": optional_int(request.query_params.get("cartao_id")),
        "tipo": request.query_params.get("tipo"),
    }


def summary_data(items):
    expenses = sum(i.valor_centavos for i in items if i.tipo == "despesa")
    income = sum(i.valor_centavos for i in items if i.tipo == "receita")
    return {"total_despesas_centavos": expenses, "total_receitas_centavos": income, "saldo_periodo_centavos": income - expenses, "quantidade_lancamentos": len(items), "maior_gasto_centavos": max([i.valor_centavos for i in items if i.tipo == "despesa"], default=0)}


@router.get("/resumo")
def summary(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    start = request.query_params.get("data_inicio") or date.today().replace(day=1).isoformat(); end = request.query_params.get("data_fim") or date.today().isoformat()
    options = query_options(request)
    items = query_entries(db, user, start, end, options["categoria_id"], options["forma_pagamento"], options["conta_id"], options["cartao_id"], options["tipo"]).all()
    return {"periodo": {"inicio": start, "fim": end}, **summary_data(items)}


@router.get("/painel")
def finance_panel(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    start_text = request.query_params.get("data_inicio") or date.today().replace(day=1).isoformat()
    end_text = request.query_params.get("data_fim") or date.today().isoformat()
    start_date = date.fromisoformat(start_text)
    end_date = date.fromisoformat(end_text)
    if end_date < start_date:
        raise HTTPException(422, "Periodo invalido.")
    span = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    current_items = query_entries(db, user, start_text, end_text).all()
    previous_items = query_entries(db, user, previous_start.isoformat(), previous_end.isoformat()).all()
    accounts = db.query(ContaFinanceira).filter(ContaFinanceira.usuario_id == user.id, ContaFinanceira.ativo.is_(True)).order_by(ContaFinanceira.nome).all()
    cards = db.query(Cartao).filter(Cartao.usuario_id == user.id, Cartao.ativo.is_(True)).order_by(Cartao.nome).all()
    all_active = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.status == "ativo").all()
    account_rows = []
    for account in accounts:
        linked = [item for item in all_active if item.conta_id == account.id]
        income = sum(item.valor_centavos for item in linked if item.tipo == "receita")
        expenses = sum(item.valor_centavos for item in linked if item.tipo == "despesa")
        latest = max(linked, key=lambda item: (item.data_compra, item.id), default=None)
        account_rows.append({"id": account.id, "nome": account.nome, "banco": account.banco, "tipo": account.tipo, "entradas_centavos": income, "saidas_centavos": expenses, "saldo_centavos": income - expenses, "ultimo_lancamento": latest.data_compra.isoformat() if latest else None, "conexao": "manual"})
    card_rows = []
    for card in cards:
        linked = [item for item in all_active if item.cartao_id == card.id and item.tipo == "despesa"]
        used = sum(item.valor_centavos for item in linked)
        installments = sum(1 for item in linked if (item.total_parcelas or 0) > 1)
        available = max((card.limite_total_centavos or 0) - used, 0) if card.limite_total_centavos is not None else None
        card_rows.append({"id": card.id, "nome": card.nome, "banco": card.banco, "ultimos_quatro_digitos": card.ultimos_quatro_digitos, "limite_total_centavos": card.limite_total_centavos, "limite_utilizado_centavos": used, "limite_disponivel_centavos": available, "dia_fechamento": card.dia_fechamento, "dia_vencimento": card.dia_vencimento, "total_parcelas": installments})
    pending_installments = db.query(Parcela).filter(Parcela.usuario_id == user.id, Parcela.status.in_(["pendente", "sem_data"])).all()
    pending_alerts = db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id == user.id, AlertaFinanceiro.status != "cancelado", AlertaFinanceiro.lido_em.is_(None)).count()
    return {
        "periodo": {"inicio": start_text, "fim": end_text},
        "resumo": summary_data(current_items),
        "periodo_anterior": {"inicio": previous_start.isoformat(), "fim": previous_end.isoformat(), **summary_data(previous_items)},
        "faturas": {"disponivel": False, "total_centavos": None},
        "parcelas_comprometidas_centavos": sum(item.valor_centavos for item in pending_installments),
        "alertas_pendentes": pending_alerts,
        "dias_periodo": span,
        "media_diaria_despesas_centavos": round(summary_data(current_items)["total_despesas_centavos"] / span),
        "contas": account_rows,
        "cartoes": card_rows,
    }


def grouped(request: Request, user: Usuario, db: Session, key: str):
    items = query_entries(db, user, **query_options(request)).all()
    totals = {}
    for item in items:
        value = getattr(item, key); label = str(value.date()) if key == "data_compra" else str(value)
        row = totals.setdefault(label, {"receitas_centavos": 0, "despesas_centavos": 0})
        row["receitas_centavos" if item.tipo == "receita" else "despesas_centavos"] += item.valor_centavos
    return [{"chave": k, **v, "saldo_centavos": v["receitas_centavos"] - v["despesas_centavos"], "valor_centavos": v["receitas_centavos"] - v["despesas_centavos"]} for k, v in sorted(totals.items())]


@router.get("/por-categoria")
def by_category(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = grouped(request, user, db, "categoria_id")
    names = {str(item.id): item.nome for item in db.query(Categoria).filter(Categoria.usuario_id == user.id)}
    for row in rows: row["nome"] = names.get(row["chave"], "Outros")
    return rows


@router.get("/por-dia")
def by_day(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return grouped(request, user, db, "data_compra")


@router.get("/por-forma-pagamento")
def by_payment(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return grouped(request, user, db, "forma_pagamento")


@router.get("/maiores-gastos", response_model=list[LancamentoPublic])
def largest(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    items = query_entries(db, user, **query_options(request)).filter(LancamentoFinanceiro.tipo == "despesa").all()
    return sorted(items, key=lambda item: item.valor_centavos, reverse=True)[:10]
