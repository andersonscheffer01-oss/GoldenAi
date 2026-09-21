from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..config import Settings
from ..dependencies import client_ip, get_current_user, get_db
from ..models import AcaoPendente, AlertaFinanceiro, Categoria, ComandoPC, DispositivoPC, LancamentoFinanceiro, Orcamento, Parcela, Usuario
from ..services.financial_commands import execute, pending
from ..services.intent_service import detect
from ..services.pc_command_service import cancel_pc_command, confirm_pc_command, create_pc_command

router = APIRouter(prefix='/api/jarvis', tags=['jarvis-comandos'])

def brl(cents: int) -> str:
    return f'R$ {cents / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

def _new_action(db, user, request, kind, parameters, summary):
    action = pending(db, user, kind, parameters, summary, Settings())
    registrar_auditoria(db, user.id, 'acao_pendente_criada', 'jarvis', summary, client_ip(request), True)
    return {'status': 'aguardando_confirmacao', 'acao_id': action.id, 'resumo': action.resumo, 'message': f'{summary}. Deseja confirmar?'}

def _current_device(db, user):
    return db.query(DispositivoPC).filter(DispositivoPC.usuario_id == user.id, DispositivoPC.revogado_em.is_(None)).order_by(DispositivoPC.ultimo_ping.desc().nullslast()).first()

def _latest_pc_confirmation(db, user):
    return db.query(ComandoPC).filter(ComandoPC.usuario_id == user.id, ComandoPC.status == 'aguardando_confirmacao').order_by(ComandoPC.id.desc()).first()

def _format_pc_status(device):
    if not device or device.status != 'conectado':
        return 'O computador esta desconectado. Nao consigo consultar o estado neste momento.'
    data = {}
    try:
        data = json.loads(device.status_json or '{}')
    except json.JSONDecodeError:
        data = {}
    return (
        f"{device.nome} esta {device.status}. "
        f"CPU: {data.get('cpu_percentual', '--')}%. "
        f"Memoria: {data.get('memoria_percentual', '--')}%. "
        f"Disco livre: {data.get('disco_livre_gb', '--')} GB. "
        f"Ollama: {data.get('ollama', 'verificar')}. "
        f"Jarvis: {data.get('jarvis', 'verificar')}. "
        f"MT5: {data.get('mt5', 'verificar')}."
    )

@router.post('/comando')
def command(payload: dict, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    text = str(payload.get('content', '')).strip()
    parsed = detect(text)
    if parsed['confidence'] < .8:
        return {'status': 'esclarecimento', 'message': 'Nao consegui identificar com seguranca. Pode explicar melhor?', 'intent': parsed['intent']}
    if parsed['intent'] in ('confirmar_acao', 'cancelar_acao'):
        action = db.query(AcaoPendente).filter(AcaoPendente.usuario_id == user.id, AcaoPendente.status == 'aguardando_confirmacao').order_by(AcaoPendente.id.desc()).first()
        if not action:
            pc_command = _latest_pc_confirmation(db, user)
            if not pc_command: return {'status': 'respondida', 'message': 'Nao encontrei nenhuma acao pendente.'}
            if parsed['intent'] == 'cancelar_acao':
                cancel_pc_command(db, pc_command)
                return {'status': 'cancelado', 'message': 'Comando do PC cancelado.'}
            try:
                confirm_pc_command(db, pc_command)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return {'status': 'executado', 'message': 'Comando confirmado. O agente do PC vai executar quando receber a fila.'}
        return finish(action.id, user, db, request, parsed['intent'] == 'cancelar_acao')
    params = parsed['parameters']; normalized = params['texto_normalizado']
    if parsed['intent'].startswith('pc_'):
        device = _current_device(db, user)
        if not device or device.status != 'conectado':
            return {'status': 'respondida', 'message': 'O computador esta desconectado. Nao consigo consultar o estado neste momento.'}
        if parsed['intent'] == 'pc_status':
            return {'status': 'respondida', 'message': _format_pc_status(device)}
        command_map = {
            'pc_verificar_ollama': 'verificar_ollama',
            'pc_verificar_jarvis': 'verificar_jarvis',
            'pc_verificar_mt5': 'verificar_mt5',
            'pc_abrir_aplicativo': 'abrir_aplicativo_autorizado',
        }
        tipo = command_map[parsed['intent']]
        payload_pc = {'programa': params.get('programa') or 'golden_jarvis'} if tipo == 'abrir_aplicativo_autorizado' else {}
        try:
            pc_command = create_pc_command(db, user.id, device, tipo, payload_pc)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        if pc_command.status == 'aguardando_confirmacao':
            programa = payload_pc.get('programa', 'programa')
            return {'status': 'aguardando_confirmacao', 'comando_id': pc_command.id, 'message': f'Deseja abrir {programa} no computador?'}
        return {'status': 'respondida', 'comando_id': pc_command.id, 'message': 'Pedido enviado ao agente do PC. Aguarde alguns segundos e consulte novamente.'}
    if parsed['intent'] in ('consultar_resumo', 'consultar_gastos_periodo', 'consultar_gastos_categoria'):
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if 'mes' in normalized else now - timedelta(days=7) if 'ultimos 7' in normalized else now.replace(hour=0, minute=0, second=0, microsecond=0)
        query = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.tipo == 'despesa', LancamentoFinanceiro.status == 'ativo', LancamentoFinanceiro.data_compra >= start)
        category = next((c for c in db.query(Categoria).filter(Categoria.usuario_id == user.id).all() if c.nome.lower() in normalized), None)
        if category: query = query.filter(LancamentoFinanceiro.categoria_id == category.id)
        items = query.all(); total = sum(i.valor_centavos for i in items); label = 'neste periodo' if start.date() != now.date() else 'hoje'
        return {'status': 'respondida', 'message': f'{label.capitalize()}, voce gastou {brl(total)} em {len(items)} lancamento(s).' if items else 'Ainda nao encontrei lancamentos para esse periodo.'}
    if parsed['intent'] == 'consultar_maior_gasto':
        item = db.query(LancamentoFinanceiro).filter(LancamentoFinanceiro.usuario_id == user.id, LancamentoFinanceiro.tipo == 'despesa', LancamentoFinanceiro.status == 'ativo').order_by(LancamentoFinanceiro.valor_centavos.desc()).first()
        return {'status': 'respondida', 'message': 'Ainda nao encontrei lancamentos.' if not item else f'Seu maior gasto foi {brl(item.valor_centavos)} em {item.descricao}.'}
    if parsed['intent'] == 'consultar_orcamento':
        budgets = db.query(Orcamento).filter(Orcamento.usuario_id == user.id, Orcamento.ativo.is_(True)).all()
        return {'status': 'respondida', 'message': 'Nao encontrei orcamentos ativos.' if not budgets else 'Orcamentos ativos: ' + ', '.join(f'{b.nome}: {brl(b.valor_limite_centavos)}' for b in budgets)}
    if parsed['intent'] == 'consultar_parcelas':
        rows = db.query(Parcela).filter(Parcela.usuario_id == user.id, Parcela.status.in_(['prevista', 'sem_data'])).order_by(Parcela.data_prevista.asc()).all()
        return {'status': 'respondida', 'message': 'Nao encontrei parcelas pendentes.' if not rows else 'Parcelas pendentes: ' + ', '.join(f'#{r.numero} {brl(r.valor_centavos)}' for r in rows)}
    if parsed['intent'] == 'consultar_lembretes':
        rows = db.query(AlertaFinanceiro).filter(AlertaFinanceiro.usuario_id == user.id, AlertaFinanceiro.tipo == 'lembrete_personalizado', AlertaFinanceiro.status == 'ativo').all()
        return {'status': 'respondida', 'message': 'Nao encontrei lembretes ativos.' if not rows else 'Lembretes: ' + ', '.join(r.titulo for r in rows)}
    if parsed['intent'] == 'criar_lancamento':
        if params['valor_centavos'] is None: return {'status': 'esclarecimento', 'message': 'Qual foi o valor do gasto?', 'intent': parsed['intent']}
        return _new_action(db, user, request, 'criar_lancamento_pendente', params, f'Registrar {text}')
    if parsed['intent'] == 'criar_orcamento':
        if params['valor_centavos'] is None: return {'status': 'esclarecimento', 'message': 'Qual sera o limite do orcamento?', 'intent': parsed['intent']}
        params['data_inicio'] = datetime.now(timezone.utc).date().isoformat()
        return _new_action(db, user, request, 'criar_orcamento_pendente', params, f'Criar orcamento mensal de {brl(params["valor_centavos"])}')
    if parsed['intent'] == 'criar_parcelamento':
        if not params['valor_centavos'] or not params['total_parcelas'] or params['total_parcelas'] < 2: return {'status': 'esclarecimento', 'message': 'Informe o valor total e a quantidade de parcelas.', 'intent': parsed['intent']}
        return _new_action(db, user, request, 'criar_parcelamento_pendente', params, f'Criar parcelamento de {brl(params["valor_centavos"])} em {params["total_parcelas"]} parcelas')
    if parsed['intent'] == 'marcar_parcela_paga':
        if not params['parcela_numero']: return {'status': 'esclarecimento', 'message': 'Qual numero de parcela devo marcar como paga?', 'intent': parsed['intent']}
        return _new_action(db, user, request, 'marcar_parcela_paga_pendente', params, f'Marcar a parcela {params["parcela_numero"]} como paga')
    if parsed['intent'] == 'criar_lembrete':
        params.update({'titulo': text[:180], 'mensagem': text, 'data_agendada': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        return _new_action(db, user, request, 'criar_lembrete_pendente', params, f'Criar lembrete: {text}')
    if parsed['intent'] in ('editar_lancamento', 'excluir_lancamento'):
        if not params['lancamento_id']: return {'status': 'esclarecimento', 'message': 'Informe o ID do lancamento para eu alterar ou excluir.', 'intent': parsed['intent']}
        kind = 'editar_lancamento_pendente' if parsed['intent'] == 'editar_lancamento' else 'excluir_lancamento_pendente'
        if kind.startswith('editar') and not params['novo_valor_centavos']: return {'status': 'esclarecimento', 'message': 'Informe o novo valor do lancamento.', 'intent': parsed['intent']}
        return _new_action(db, user, request, kind, params, f'Confirmar {"edicao" if kind.startswith("editar") else "exclusao"} do lancamento {params["lancamento_id"]}')
    return {'status': 'fallback', 'intent': parsed['intent']}

@router.get('/acoes-pendentes')
def list_pending(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return [{'id': a.id, 'tipo': a.tipo, 'resumo': a.resumo, 'status': a.status, 'expira_em': a.expira_em} for a in db.query(AcaoPendente).filter(AcaoPendente.usuario_id == user.id, AcaoPendente.status == 'aguardando_confirmacao', AcaoPendente.expira_em > now).all()]

def finish(ident, user, db, request, cancel=False):
    action = db.query(AcaoPendente).filter(AcaoPendente.id == ident, AcaoPendente.usuario_id == user.id).first()
    if not action: raise HTTPException(404, 'Acao nao encontrada')
    expires = action.expira_em.replace(tzinfo=timezone.utc) if action.expira_em.tzinfo is None else action.expira_em
    if action.status != 'aguardando_confirmacao' or expires < datetime.now(timezone.utc):
        action.status = 'expirado'; db.commit(); raise HTTPException(409, 'Acao expirada ou ja executada')
    if cancel:
        action.status = 'cancelado'; action.cancelado_em = datetime.now(timezone.utc); db.commit(); return {'status': 'cancelado', 'message': 'Acao cancelada.'}
    try: item = execute(db, action, user)
    except ValueError as exc: db.rollback(); raise HTTPException(422, str(exc)) from exc
    action.status = 'executado'; action.confirmado_em = datetime.now(timezone.utc); db.commit()
    registrar_auditoria(db, user.id, 'acao_executada', 'jarvis', str(action.id), client_ip(request), True)
    return {'status': 'executado', 'objeto_id': item.id, 'message': 'Acao executada com sucesso.'}

@router.post('/acoes/{ident}/confirmar')
def confirm(ident: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return finish(ident, user, db, request)

@router.post('/acoes/{ident}/cancelar')
def cancel(ident: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)): return finish(ident, user, db, request, True)
