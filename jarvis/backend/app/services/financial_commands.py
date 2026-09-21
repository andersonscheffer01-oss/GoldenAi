from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib, json

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import AcaoPendente, AlertaFinanceiro, Categoria, LancamentoFinanceiro, Orcamento, Parcela, Parcelamento, Usuario


def _month_add(value: datetime, months: int) -> datetime:
    month = value.month - 1 + months
    year, month = value.year + month // 12, month % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, 28))


def pending(db: Session, user: Usuario, kind: str, payload: dict, summary: str, settings: Settings):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    action = AcaoPendente(usuario_id=user.id, tipo=kind, payload_json=raw, resumo=summary, hash_acao=hashlib.sha256(raw.encode()).hexdigest(), expira_em=datetime.now(timezone.utc)+timedelta(minutes=settings.pending_action_expire_minutes))
    db.add(action); db.commit(); db.refresh(action); return action


def execute(db: Session, action: AcaoPendente, user: Usuario):
    payload = json.loads(action.payload_json)
    if action.tipo == 'criar_lancamento_pendente':
        category = db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome.ilike(payload.get('categoria', 'Outros'))).first() or db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome == 'Outros').first()
        item = LancamentoFinanceiro(usuario_id=user.id, tipo='despesa', descricao=payload['descricao'], valor_centavos=payload['valor_centavos'], moeda='BRL', data_compra=datetime.fromisoformat(payload['data_compra']).replace(tzinfo=timezone.utc), categoria_id=category.id, origem='chat', status='ativo')
        db.add(item); db.flush(); return item
    if action.tipo == 'criar_orcamento_pendente':
        category = db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome.ilike(payload.get('categoria','Outros'))).first() or db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome == 'Outros').first()
        item = Orcamento(usuario_id=user.id, categoria_id=category.id, nome=category.nome, valor_limite_centavos=payload['valor_centavos'], periodicidade='mensal', data_inicio=datetime.fromisoformat(payload.get('data_inicio', datetime.now(timezone.utc).date().isoformat())).replace(tzinfo=timezone.utc), ativo=True)
        db.add(item); db.flush(); return item
    if action.tipo == 'criar_parcelamento_pendente':
        total = int(payload['total_parcelas'])
        valor_total = int(payload['valor_centavos'])
        valor_parcela = valor_total // total
        category = db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome.ilike(payload.get('categoria', 'Outros'))).first() or db.query(Categoria).filter(Categoria.usuario_id == user.id, Categoria.nome == 'Outros').first()
        item = Parcelamento(usuario_id=user.id, descricao=payload['descricao'], valor_total_centavos=valor_total, total_parcelas=total, valor_parcela_centavos=valor_parcela, data_compra=datetime.now(timezone.utc), categoria_id=category.id, ativo=True)
        db.add(item); db.flush()
        for number in range(1, total + 1):
            amount = valor_parcela + (valor_total - valor_parcela * total if number == total else 0)
            db.add(Parcela(parcelamento_id=item.id, usuario_id=user.id, numero=number, valor_centavos=amount, data_prevista=_month_add(item.data_compra, number - 1), status='prevista'))
        db.flush(); return item
    if action.tipo == 'excluir_lancamento_pendente':
        item = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.id == payload['lancamento_id'], LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.status == 'ativo').first()
        if not item: raise ValueError('Lancamento nao encontrado')
        item.status='excluido'; item.excluido_em=datetime.now(timezone.utc); db.flush(); return item
    if action.tipo == 'editar_lancamento_pendente':
        item = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.id == payload['lancamento_id'], LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.status == 'ativo').first()
        if not item: raise ValueError('Lancamento nao encontrado')
        item.valor_centavos=payload['novo_valor_centavos']; db.flush(); return item
    if action.tipo == 'marcar_parcela_paga_pendente':
        item = db.query(Parcela).filter(Parcela.id == payload.get('parcela_id'), Parcela.usuario_id == user.id).first()
        if not item and payload.get('parcela_numero'):
            item = db.query(Parcela).filter(Parcela.usuario_id == user.id, Parcela.numero == payload['parcela_numero'], Parcela.status != 'paga').order_by(Parcela.id.asc()).first()
        if not item: raise ValueError('Parcela nao encontrada')
        item.status='paga'; db.flush(); return item
    if action.tipo == 'criar_lembrete_pendente':
        item=AlertaFinanceiro(usuario_id=user.id,tipo='lembrete_personalizado',titulo=payload['titulo'],mensagem=payload['mensagem'],data_agendada=datetime.fromisoformat(payload['data_agendada']),status='ativo')
        db.add(item); db.flush(); return item
    if action.tipo == 'cancelar_lembrete_pendente':
        item = db.query(AlertaFinanceiro).filter(AlertaFinanceiro.id == payload['lembrete_id'], AlertaFinanceiro.usuario_id == user.id, AlertaFinanceiro.status == 'ativo').first()
        if not item: raise ValueError('Lembrete nao encontrado')
        item.status = 'cancelado'; db.flush(); return item
    raise ValueError('Ferramenta de acao nao autorizada')
