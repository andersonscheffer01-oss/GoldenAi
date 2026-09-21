from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (AlertaFinanceiro, LancamentoFinanceiro, OpenFinanceBill,
                      OpenFinanceConnection, Orcamento)


def check_alerts(db: Session) -> int:
    created = 0
    for budget in db.query(Orcamento).filter(Orcamento.ativo.is_(True)).all():
        start = budget.data_inicio
        end = budget.data_fim
        query = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == budget.usuario_id, LancamentoFinanceiro.categoria_id == budget.categoria_id, LancamentoFinanceiro.tipo == "despesa", LancamentoFinanceiro.status == "ativo", LancamentoFinanceiro.data_compra >= start)
        if end: query = query.filter(LancamentoFinanceiro.data_compra <= end)
        used = sum(item.valor_centavos for item in query.all())
        percent = used * 100 / budget.valor_limite_centavos
        for trigger, enabled, kind in ((50, budget.alerta_50, "orcamento_50"), (80, budget.alerta_80, "orcamento_80"), (100, budget.alerta_100, "orcamento_100"), (110, budget.alerta_110, "orcamento_110")):
            exists = db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id == budget.usuario_id, AlertaFinanceiro.orcamento_id == budget.id, AlertaFinanceiro.percentual_gatilho == trigger, AlertaFinanceiro.status != "cancelado").first()
            if enabled and percent >= trigger and not exists:
                db.add(AlertaFinanceiro(usuario_id=budget.usuario_id, tipo=kind, titulo=f"Orcamento: {trigger}%", mensagem=f"Voce ja utilizou {trigger}% do orcamento {budget.nome}.", categoria_id=budget.categoria_id, orcamento_id=budget.id, percentual_gatilho=trigger, canal="dentro_app", status="ativo")); created += 1
    now = datetime.now(timezone.utc)
    for bill in db.query(OpenFinanceBill).filter(OpenFinanceBill.due_date.isnot(None)).all():
        due = bill.due_date
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        status = str(bill.status or "").upper()
        if status in {"PAID", "CLOSED", "CANCELLED"}:
            continue
        days = (due.date() - now.date()).days
        if days < 0:
            kind, title = "open_finance_fatura_atrasada", "Fatura atrasada"
            message = "Uma fatura Open Finance esta vencida e possui saldo em aberto."
        elif days <= 7:
            kind, title = "open_finance_fatura_proxima", "Fatura proxima do vencimento"
            message = f"Uma fatura Open Finance vence em {days} dia(s)."
        else:
            continue
        exists = db.query(AlertaFinanceiro).filter(
            AlertaFinanceiro.usuario_id == bill.usuario_id,
            AlertaFinanceiro.tipo == kind,
            AlertaFinanceiro.data_agendada == due,
            AlertaFinanceiro.status != "cancelado",
        ).first()
        if not exists:
            db.add(AlertaFinanceiro(usuario_id=bill.usuario_id, tipo=kind, titulo=title,
                                     mensagem=message, data_agendada=due, canal="dentro_app",
                                     status="ativo"))
            created += 1
    for conn in db.query(OpenFinanceConnection).filter(OpenFinanceConnection.status == "action_required").all():
        exists = db.query(AlertaFinanceiro).filter(
            AlertaFinanceiro.usuario_id == conn.usuario_id,
            AlertaFinanceiro.tipo == "open_finance_atencao",
            AlertaFinanceiro.status != "cancelado",
            AlertaFinanceiro.mensagem.like(f"%conexao #{conn.id}%"),
        ).first()
        if not exists:
            db.add(AlertaFinanceiro(usuario_id=conn.usuario_id, tipo="open_finance_atencao",
                                     titulo="Open Finance precisa de atenção",
                                     mensagem=f"A conexao #{conn.id} precisa de autorizacao no provedor.",
                                     canal="dentro_app", status="ativo"))
            created += 1
    if created: db.commit()
    return created
