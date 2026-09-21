from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import OpenFinanceAccount, OpenFinanceConnection, OpenFinanceTransaction, Usuario
from app.routers.pluggy_finance import item_state, upsert_account, upsert_transaction
from app.security import hash_password


def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed(db):
    user = Usuario(nome="Teste", email="pluggy@example.com", senha_hash=hash_password("Senha123!"))
    db.add(user); db.flush()
    connection = OpenFinanceConnection(usuario_id=user.id, provider="pluggy", environment="personal", external_link_id="item-12345678")
    db.add(connection); db.flush()
    return user, connection


def test_account_and_transaction_upsert_are_idempotent():
    db = session(); user, connection = seed(db)
    account_data = {"id": "acc-1", "name": "Conta Inter", "type": "BANK", "balance": 125.50, "currencyCode": "BRL"}
    account, created = upsert_account(db, user.id, connection.id, account_data)
    assert created is True
    db.flush()
    _, created_again = upsert_account(db, user.id, connection.id, {**account_data, "balance": 130})
    tx = {"id": "tx-1", "date": datetime.now(timezone.utc).isoformat(), "description": "Mercado", "amount": 25, "type": "DEBIT", "status": "POSTED"}
    assert upsert_transaction(db, user.id, connection.id, account, tx) is True
    db.flush()
    assert upsert_transaction(db, user.id, connection.id, account, tx) is False
    db.flush()
    assert created_again is False
    assert db.query(OpenFinanceAccount).count() == 1
    assert db.query(OpenFinanceTransaction).count() == 1
    assert account.current_balance_cents == 13000


def test_credit_card_positive_amount_is_expense():
    db = session(); user, connection = seed(db)
    account, _ = upsert_account(db, user.id, connection.id, {"id": "card-1", "name": "Cartao", "type": "CREDIT", "balance": 100})
    db.flush()
    upsert_transaction(db, user.id, connection.id, account, {"id": "card-tx", "date": "2026-08-30T12:00:00Z", "description": "Compra", "amount": 79.90, "type": "DEBIT"})
    db.flush()
    transaction = db.query(OpenFinanceTransaction).one()
    assert transaction.flow_type == "expense"
    assert transaction.amount_cents == 7990


def test_item_state_requires_widget_for_mfa_or_invalid_credentials():
    assert item_state({"status": "WAITING_USER_INPUT", "statusDetail": {"code": "MFA_REQUIRED"}})[2] is True
    assert item_state({"status": "LOGIN_ERROR", "statusDetail": {"code": "INVALID_CREDENTIALS"}})[2] is True
    assert item_state({"status": "UPDATED", "executionStatus": "SUCCESS"})[2] is False
