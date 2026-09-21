from __future__ import annotations

import json
import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..config import get_settings
from ..dependencies import client_ip, get_current_user, get_db
from ..models import (Categoria, LancamentoFinanceiro, OpenFinanceAccount, OpenFinanceBill,
                      OpenFinanceConnection, OpenFinanceImport, OpenFinanceSync,
                      OpenFinanceTransaction, Usuario, utc_now)
from ..services.default_categories import ensure_default_categories
from ..services.pluggy import PluggyClient, PluggyError, cents, parse_datetime, safe_error

router = APIRouter(prefix="/api/open-finance", tags=["open-finance"])


class FinishConnection(BaseModel):
    item_id: str = Field(min_length=8, max_length=100)


class PrepareImport(BaseModel):
    transaction_ids: list[int] = Field(min_length=1, max_length=500)
    expense_category_id: int | None = None
    income_category_id: int | None = None


USER_ACTION_CODES = ("WAITING_USER_INPUT", "INVALID_CREDENTIALS", "MFA", "LOGIN_ERROR", "USER_AUTHORIZATION", "CONSENT_EXPIRED", "ACCOUNT_NEEDS_ACTION")


def item_state(source: dict[str, Any]) -> tuple[str, str, bool]:
    detail = source.get("statusDetail") if isinstance(source.get("statusDetail"), dict) else {}
    status = str(source.get("status") or source.get("executionStatus") or "UNKNOWN").upper()
    code = str(detail.get("code") or detail.get("name") or status).upper()[:80]
    combined = f"{status} {code}"
    return status, code, any(marker in combined for marker in USER_ACTION_CODES)


def connection(db: Session, user_id: int, connection_id: int) -> OpenFinanceConnection:
    item = db.query(OpenFinanceConnection).filter(OpenFinanceConnection.id == connection_id, OpenFinanceConnection.usuario_id == user_id).first()
    if not item: raise HTTPException(404, "Conexao Meu Pluggy nao encontrada.")
    return item


def public_connection(item: OpenFinanceConnection) -> dict[str, Any]:
    return {"id": item.id, "provider": "pluggy", "mode": "personal", "institution_name": item.institution_name,
            "status": item.status, "consent_status": item.consent_status, "last_sync_at": item.last_sync_at,
            "created_at": item.created_at}


def persist_item(db: Session, user_id: int, item_id: str, source: dict[str, Any]) -> OpenFinanceConnection:
    """Keep one local row per Pluggy Item; never merge Items by institution."""
    item = db.query(OpenFinanceConnection).filter(
        OpenFinanceConnection.usuario_id == user_id,
        OpenFinanceConnection.external_link_id == item_id,
    ).first()
    connector = source.get("connector") if isinstance(source.get("connector"), dict) else {}
    if not item:
        item = OpenFinanceConnection(usuario_id=user_id, provider="pluggy", environment="personal", external_link_id=item_id)
        db.add(item)
    item.institution_name = str(connector.get("name") or source.get("connectorName") or "Instituicao conectada")[:180]
    item.institution_code = str(connector.get("id") or source.get("connectorId") or "")[:120] or None
    status = str(source.get("status") or source.get("executionStatus") or "UNKNOWN").upper()
    item.status = "connected" if status in {"SUCCESS", "UPDATED", "PARTIAL_SUCCESS"} else "pending"
    item.consent_status = "active"
    return item


def provider_error(db: Session, user: Usuario, request: Request, action: str, exc: Exception) -> HTTPException:
    message = safe_error(exc)
    registrar_auditoria(db, user.id, action, "open_finance", message, client_ip(request), False)
    return HTTPException(exc.status_code if isinstance(exc, PluggyError) else 502,
                         {"code": getattr(exc, "code", "provider_error"), "message": message})


@router.get("/status")
def status(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    rows = db.query(OpenFinanceConnection).filter(OpenFinanceConnection.usuario_id == user.id).order_by(OpenFinanceConnection.created_at.desc()).all()
    return {"provider": "pluggy", "mode": "personal", "configured": settings.pluggy_configured,
            "read_only": True, "connections": [public_connection(row) for row in rows]}


@router.post("/connect-token")
async def connect_token(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings(); webhook = settings.server_public_url.rstrip("/") + "/api/open-finance/webhooks/pluggy"
    try: token = await PluggyClient(settings).connect_token(user.id, webhook)
    except Exception as exc: raise provider_error(db, user, request, "pluggy_connect_token_error", exc) from exc
    registrar_auditoria(db, user.id, "pluggy_connect_token_created", "open_finance", "Token temporario do Widget criado", client_ip(request), True)
    settings = get_settings()
    return {"connect_token": token, "include_sandbox": settings.environment != "production", "environment": settings.environment}


@router.post("/connections/{connection_id}/update-token")
async def update_token(connection_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = connection(db, user.id, connection_id)
    try: token = await PluggyClient(get_settings()).connect_token(user.id, item_id=conn.external_link_id)
    except Exception as exc: raise provider_error(db, user, request, "pluggy_update_token_error", exc) from exc
    registrar_auditoria(db, user.id, "pluggy_update_token_created", "open_finance", f"Atualizacao interativa da conexao #{conn.id}", client_ip(request), True)
    settings = get_settings()
    return {"connect_token": token, "item_id": conn.external_link_id, "include_sandbox": settings.environment != "production", "environment": settings.environment}


@router.post("/connections/finish")
async def finish(payload: FinishConnection, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    try: source = await PluggyClient(get_settings()).item(payload.item_id)
    except Exception as exc: raise provider_error(db, user, request, "pluggy_connection_error", exc) from exc
    if source.get("clientUserId") not in {None, "", f"jarvis:{user.id}"}: raise HTTPException(403, "Conexao nao pertence a este usuario.")
    item = persist_item(db, user.id, payload.item_id, source); db.commit(); db.refresh(item)
    registrar_auditoria(db, user.id, "pluggy_connected", "open_finance", f"Conexao pessoal #{item.id} criada", client_ip(request), True)
    return {**public_connection(item), "item_id": item.external_link_id,
            "item_id_masked": f"{item.external_link_id[:8]}...{item.external_link_id[-4:]}",
            "accounts": db.query(OpenFinanceAccount).filter_by(usuario_id=user.id, connection_id=item.id).count(),
            "cards": db.query(OpenFinanceAccount).filter_by(usuario_id=user.id, connection_id=item.id, type="CREDIT").count(),
            "bills": db.query(OpenFinanceBill).filter_by(usuario_id=user.id, connection_id=item.id).count(),
            "transactions": db.query(OpenFinanceTransaction).filter_by(usuario_id=user.id, connection_id=item.id).count()}


def upsert_account(db: Session, user_id: int, cid: int, row: dict[str, Any]) -> tuple[OpenFinanceAccount | None, bool]:
    eid = str(row.get("id") or "");
    if not eid: return None, False
    item = db.query(OpenFinanceAccount).filter(OpenFinanceAccount.usuario_id == user_id, OpenFinanceAccount.connection_id == cid, OpenFinanceAccount.external_id == eid).first(); created = item is None
    if not item: item = OpenFinanceAccount(usuario_id=user_id, connection_id=cid, external_id=eid, name="Conta"); db.add(item)
    item.connection_id = cid; item.name = str(row.get("name") or row.get("marketingName") or "Conta")[:180]
    item.type = str(row.get("type") or "")[:60] or None; item.subtype = str(row.get("subtype") or "")[:60] or None
    item.currency = str(row.get("currencyCode") or "BRL")[:3]; item.current_balance_cents = cents(row.get("balance"))
    item.available_balance_cents = cents(row.get("availableBalance") or row.get("available_balance") or row.get("availableCredit")); item.credit_limit_cents = cents(row.get("creditLimit") or row.get("credit_limit") or row.get("limit"))
    return item, created


def upsert_transaction(db: Session, user_id: int, cid: int, account: OpenFinanceAccount, row: dict[str, Any]) -> bool:
    occurred = parse_datetime(row.get("date")); amount = cents(row.get("amount"))
    if not occurred or amount is None: return False
    description = str(row.get("description") or row.get("descriptionRaw") or "Movimentacao")[:255]
    eid = str(row.get("id") or "")
    if not eid:
        fingerprint = f"{user_id}|{account.external_id}|{occurred.isoformat()}|{amount}|{description.casefold().strip()}"
        eid = "hash:" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    item = db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user_id, OpenFinanceTransaction.connection_id == cid, OpenFinanceTransaction.external_id == eid).first(); created = item is None
    if not item: item = OpenFinanceTransaction(usuario_id=user_id, connection_id=cid, external_id=eid, occurred_at=occurred, description="Movimentacao", amount_cents=abs(amount), flow_type="expense"); db.add(item)
    provider_type = str(row.get("type") or "").upper(); is_card = str(account.type or "").upper() == "CREDIT"
    item.connection_id = cid; item.account_external_id = account.external_id; item.occurred_at = occurred
    item.description = description
    item.amount_cents = abs(amount); item.currency = str(row.get("currencyCode") or "BRL")[:3]
    normalized = description.casefold()
    is_bill_payment = any(term in normalized for term in ("pagamento de fatura", "pagamento fatura", "pgto fatura", "débito fatura", "debito fatura"))
    item.flow_type = "settlement" if is_bill_payment else "expense" if (is_card and amount > 0) or (not is_card and provider_type == "DEBIT") else "income"
    item.provider_category = str(row.get("category") or "")[:120] or None; item.status = str(row.get("status") or "")[:40] or None
    return created


def upsert_bill(db: Session, user_id: int, cid: int, account_id: str, row: dict[str, Any]) -> bool:
    eid = str(row.get("id") or "");
    if not eid: return False
    item = db.query(OpenFinanceBill).filter(OpenFinanceBill.usuario_id == user_id, OpenFinanceBill.connection_id == cid, OpenFinanceBill.external_id == eid).first(); created = item is None
    if not item: item = OpenFinanceBill(usuario_id=user_id, connection_id=cid, external_id=eid); db.add(item)
    item.connection_id = cid; item.account_external_id = account_id; item.due_date = parse_datetime(row.get("dueDate"))
    item.total_cents = cents(row.get("totalAmount")); item.minimum_cents = cents(row.get("minimumPaymentAmount")); item.status = str(row.get("status") or "")[:50] or None
    return created


@router.post("/connections/{connection_id}/sync")
async def sync(connection_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = connection(db, user.id, connection_id)
    if conn.status == "disconnected": raise HTTPException(409, "Conexao desconectada.")
    created = updated = transaction_count = bill_count = 0
    provider_accounts: list[str] = []
    try:
        api = PluggyClient(get_settings())
        source = await api.item(conn.external_link_id)
        provider_status, technical_code, needs_user = item_state(source)
        if needs_user:
            conn.status = "action_required"; db.commit()
            registrar_auditoria(db, user.id, "pluggy_user_action_required", "open_finance", f"Conexao #{conn.id}: {technical_code}", client_ip(request), False)
            raise HTTPException(409, {"message": "A instituicao exige sua autorizacao no Widget.", "code": technical_code, "provider_status": provider_status, "requires_user_action": True})
        provider_bundle = []
        for account_data in await api.accounts(conn.external_link_id):
            provider_accounts.append(str(account_data.get("name") or account_data.get("marketingName") or "Conta")[:180])
            external_account_id = str(account_data.get("id") or "")
            transactions = await api.transactions(external_account_id) if external_account_id else []
            bills = await api.bills(external_account_id) if external_account_id and str(account_data.get("type") or "").upper() == "CREDIT" else []
            transaction_count += len(transactions)
            bill_count += len(bills)
            provider_bundle.append((account_data, transactions, bills))
        for account_data, transactions, bills in provider_bundle:
            account, is_new = upsert_account(db, user.id, conn.id, account_data)
            if not account: continue
            created += int(is_new); updated += int(not is_new); db.flush()
            for tx in transactions:
                if upsert_transaction(db, user.id, conn.id, account, tx): created += 1
                else: updated += 1
            for bill in bills:
                if upsert_bill(db, user.id, conn.id, account.external_id, bill): created += 1
                else: updated += 1
        conn.last_sync_at = utc_now(); conn.status = "connected"
        db.add(OpenFinanceSync(usuario_id=user.id, connection_id=conn.id, resource="all", status="success", created_count=created, updated_count=updated)); db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback(); db.add(OpenFinanceSync(usuario_id=user.id, connection_id=conn.id, resource="all", status="error", error_code=getattr(exc, "code", "provider_error"), error_message=safe_error(exc))); db.commit()
        raise provider_error(db, user, request, "pluggy_sync_error", exc) from exc
    registrar_auditoria(db, user.id, "pluggy_synced", "open_finance", f"Conexao #{conn.id}: {created} novos, {updated} atualizados", client_ip(request), True)
    return {"created": created, "updated": updated, "synced_at": conn.last_sync_at,
            "provider_status": provider_status, "provider_accounts": len(provider_accounts),
            "provider_account_names": provider_accounts, "transactions_received": transaction_count,
            "bills_received": bill_count}


@router.post("/connections/sync-all")
async def sync_all(request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    """Refresh every Item registered for this Jarvis user, independently."""
    rows = db.query(OpenFinanceConnection).filter(
        OpenFinanceConnection.usuario_id == user.id,
        OpenFinanceConnection.status != "disconnected",
    ).order_by(OpenFinanceConnection.created_at.asc()).all()
    results = []
    for row in rows:
        try:
            results.append({"connection_id": row.id, "institution": row.institution_name, "result": await sync(row.id, request, user, db)})
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            results.append({"connection_id": row.id, "institution": row.institution_name, "error": detail})
    return {"items_total": len(rows), "items_processed": len(results), "results": results}


@router.get("/diagnostico")
async def diagnostic(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    """Safe multi-Item inventory; excludes all credentials and tokens."""
    settings = get_settings(); api = PluggyClient(settings) if settings.pluggy_configured else None
    rows = db.query(OpenFinanceConnection).filter(OpenFinanceConnection.usuario_id == user.id).order_by(OpenFinanceConnection.created_at.asc()).all()
    items = []
    for row in rows:
        local_accounts = db.query(OpenFinanceAccount).filter_by(usuario_id=user.id, connection_id=row.id).all()
        detail = {"connection_id": row.id, "institution": row.institution_name, "connector_id": row.institution_code,
                  "status": row.status, "last_sync_at": row.last_sync_at,
                  "accounts": sum(str(a.type or '').upper() == 'BANK' for a in local_accounts),
                  "cards": sum(str(a.type or '').upper() == 'CREDIT' for a in local_accounts),
                  "transactions": db.query(OpenFinanceTransaction).filter_by(usuario_id=user.id, connection_id=row.id).count(),
                  "bills": db.query(OpenFinanceBill).filter_by(usuario_id=user.id, connection_id=row.id).count()}
        if api:
            try:
                source = await api.item(row.external_link_id)
                connector = source.get("connector") if isinstance(source.get("connector"), dict) else {}
                detail.update(provider_institution=connector.get("name") or source.get("connectorName"),
                              connector_id=connector.get("id") or source.get("connectorId"),
                              provider_status=source.get("status") or source.get("executionStatus"),
                              status_detail=(source.get("statusDetail") or {}).get("code") if isinstance(source.get("statusDetail"), dict) else None)
            except Exception as exc:
                detail["error"] = safe_error(exc)
        items.append(detail)
    names = ' '.join(str(x.get('provider_institution') or x.get('institution') or '').casefold() for x in items)
    return {"items_total": len(items), "items": items,
            "instituicoes_esperadas": {name: (name.casefold() in names) for name in ("Itaú", "Inter", "BV")},
            "observacao": "A Pluggy nao fornece listagem remota de Items; o Jarvis diagnostica todos os Items registrados por este usuario."}


@router.get("/data")
def get_data(connection_id: int | None = None, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(OpenFinanceConnection).filter(OpenFinanceConnection.usuario_id == user.id)
    if connection_id: q = q.filter(OpenFinanceConnection.id == connection_id)
    conns = q.all(); ids = [c.id for c in conns]
    accounts = db.query(OpenFinanceAccount).filter(OpenFinanceAccount.usuario_id == user.id, OpenFinanceAccount.connection_id.in_(ids)).all() if ids else []
    bills = db.query(OpenFinanceBill).filter(OpenFinanceBill.usuario_id == user.id, OpenFinanceBill.connection_id.in_(ids)).all() if ids else []
    txs = db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user.id, OpenFinanceTransaction.connection_id.in_(ids)).order_by(OpenFinanceTransaction.occurred_at.desc()).limit(500).all() if ids else []
    institutions = {c.id: c.institution_name for c in conns}; item_ids = {c.id: c.external_link_id for c in conns}; account_names = {a.external_id: a.name for a in accounts}
    return {"connections": [public_connection(c) for c in conns],
            "accounts": [{"id": a.id, "external_id": a.external_id, "connection_id": a.connection_id, "item_id": item_ids.get(a.connection_id), "institution_name": institutions.get(a.connection_id), "name": a.name, "type": a.type, "subtype": a.subtype, "currency": a.currency, "current_balance_cents": a.current_balance_cents, "available_balance_cents": a.available_balance_cents, "credit_limit_cents": a.credit_limit_cents} for a in accounts],
            "bills": [{"id": b.id, "account_external_id": b.account_external_id, "account_name": account_names.get(b.account_external_id), "connection_id": b.connection_id, "item_id": item_ids.get(b.connection_id), "institution_name": institutions.get(b.connection_id), "due_date": b.due_date, "total_cents": b.total_cents, "minimum_cents": b.minimum_cents, "status": b.status} for b in bills],
            "transactions": [{"id": t.id, "account_external_id": t.account_external_id, "connection_id": t.connection_id, "item_id": item_ids.get(t.connection_id), "institution_name": institutions.get(t.connection_id), "occurred_at": t.occurred_at, "description": t.description, "amount_cents": t.amount_cents, "currency": t.currency, "flow_type": t.flow_type, "provider_category": t.provider_category, "status": t.status, "import_status": t.import_status} for t in txs]}


def valid_category(db: Session, uid: int, category_id: int | None, kind: str) -> None:
    if not category_id or not db.query(Categoria).filter(Categoria.id == category_id, Categoria.usuario_id == uid, Categoria.tipo == kind, Categoria.ativa.is_(True)).first():
        raise HTTPException(422, f"Selecione uma categoria de {kind} valida.")


@router.post("/imports/prepare")
def prepare_import(payload: PrepareImport, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_default_categories(db, user.id); requested = set(payload.transaction_ids)
    txs = db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user.id, OpenFinanceTransaction.id.in_(requested), OpenFinanceTransaction.import_status == "available").all()
    if len(txs) != len(requested): raise HTTPException(409, "Uma ou mais transacoes ja foram importadas ou estao pendentes.")
    if any(t.flow_type == "expense" for t in txs): valid_category(db, user.id, payload.expense_category_id, "despesa")
    if any(t.flow_type == "income" for t in txs): valid_category(db, user.id, payload.income_category_id, "receita")
    batch = OpenFinanceImport(usuario_id=user.id, transaction_ids_json=json.dumps([t.id for t in txs]), expense_category_id=payload.expense_category_id, income_category_id=payload.income_category_id, summary=f"{len(txs)} transacoes selecionadas")
    db.add(batch)
    for tx in txs: tx.import_status = "pending_confirmation"
    db.commit(); db.refresh(batch)
    registrar_auditoria(db, user.id, "pluggy_import_prepared", "open_finance", f"Lote #{batch.id} aguardando confirmacao", client_ip(request), True)
    return {"id": batch.id, "status": batch.status, "summary": batch.summary}


@router.post("/imports/{batch_id}/confirm")
def confirm_import(batch_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    batch = db.query(OpenFinanceImport).filter(OpenFinanceImport.id == batch_id, OpenFinanceImport.usuario_id == user.id, OpenFinanceImport.status == "pending_confirmation").first()
    if not batch: raise HTTPException(409, "Importacao nao esta aguardando confirmacao.")
    ids = json.loads(batch.transaction_ids_json); txs = db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user.id, OpenFinanceTransaction.id.in_(ids), OpenFinanceTransaction.import_status == "pending_confirmation").all()
    if len(txs) != len(ids): raise HTTPException(409, "O lote foi alterado e nao pode ser importado.")
    created = settled = 0
    for tx in txs:
        if tx.flow_type == "settlement":
            tx.import_status = "imported"; settled += 1
            continue
        category_id = batch.income_category_id if tx.flow_type == "income" else batch.expense_category_id
        entry = LancamentoFinanceiro(usuario_id=user.id, tipo="receita" if tx.flow_type == "income" else "despesa", descricao=tx.description, valor_centavos=tx.amount_cents, moeda=tx.currency, data_compra=tx.occurred_at, categoria_id=category_id, estabelecimento=tx.description, observacoes="Importado do Meu Pluggy apos confirmacao.", origem="open_finance", status="ativo")
        db.add(entry); db.flush(); tx.imported_entry_id = entry.id; tx.import_status = "imported"; created += 1
    batch.status = "confirmed"; batch.confirmed_at = utc_now(); db.commit()
    registrar_auditoria(db, user.id, "pluggy_import_confirmed", "open_finance", f"Lote #{batch.id}: {len(txs)} lancamentos", client_ip(request), True)
    return {"status": "confirmed", "entries_created": created, "bill_settlements_reconciled": settled}


@router.post("/imports/{batch_id}/cancel")
def cancel_import(batch_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    batch = db.query(OpenFinanceImport).filter(OpenFinanceImport.id == batch_id, OpenFinanceImport.usuario_id == user.id, OpenFinanceImport.status == "pending_confirmation").first()
    if not batch: raise HTTPException(409, "Importacao nao esta aguardando confirmacao.")
    ids = json.loads(batch.transaction_ids_json); db.query(OpenFinanceTransaction).filter(OpenFinanceTransaction.usuario_id == user.id, OpenFinanceTransaction.id.in_(ids), OpenFinanceTransaction.import_status == "pending_confirmation").update({"import_status": "available"}, synchronize_session=False)
    batch.status = "cancelled"; batch.cancelled_at = utc_now(); db.commit()
    registrar_auditoria(db, user.id, "pluggy_import_cancelled", "open_finance", f"Lote #{batch.id} cancelado", client_ip(request), True)
    return {"status": "cancelled"}


@router.delete("/connections/{connection_id}")
async def disconnect(connection_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = connection(db, user.id, connection_id)
    try: await PluggyClient(get_settings()).disconnect(conn.external_link_id)
    except Exception as exc: raise provider_error(db, user, request, "pluggy_disconnect_error", exc) from exc
    conn.status = "disconnected"; conn.consent_status = "revoked"; conn.disconnected_at = utc_now(); db.commit()
    registrar_auditoria(db, user.id, "pluggy_disconnected", "open_finance", f"Conexao #{conn.id} revogada", client_ip(request), True)
    return {"status": "disconnected"}


@router.post("/webhooks/pluggy")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json(); event_id = str(payload.get("eventId") or "")[:64]
    if not event_id: raise HTTPException(422, "Evento sem identificador.")
    if db.query(OpenFinanceSync).filter(OpenFinanceSync.event_key == event_id).first(): return {"status": "duplicate"}
    item_id = str(payload.get("itemId") or ""); conn = db.query(OpenFinanceConnection).filter(OpenFinanceConnection.external_link_id == item_id).first() if item_id else None
    if not conn and item_id:
        client_user = str(payload.get("clientUserId") or "")
        if client_user.startswith("jarvis:") and client_user[7:].isdigit():
            source = await PluggyClient(get_settings()).item(item_id)
            conn = persist_item(db, int(client_user[7:]), item_id, source)
    db.add(OpenFinanceSync(usuario_id=conn.usuario_id if conn else None, connection_id=conn.id if conn else None, event_key=event_id, resource=str(payload.get("event") or "event")[:40], status="received")); db.commit()
    return {"status": "received"}
