from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import ComandoPC, DispositivoPC


ALLOWED_PC_TOOLS = frozenset({
    "verificar_status_pc",
    "verificar_ollama",
    "verificar_jarvis",
    "verificar_mt5",
    "abrir_aplicativo_autorizado",
})

BLOCKED_PC_TOOLS = frozenset({
    "executar_shell",
    "executar_cmd",
    "executar_powershell",
    "apagar_arquivo",
    "mover_arquivo",
    "baixar_programa",
    "instalar_programa",
    "alterar_registro",
    "reiniciar_computador",
    "desligar_computador",
    "enviar_ordem_trading",
    "pagamento",
    "transferencia",
})

CONFIRMATION_REQUIRED = frozenset({"abrir_aplicativo_autorizado"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def ensure_allowed_command(tipo: str, payload: dict | None = None) -> None:
    if tipo in BLOCKED_PC_TOOLS or tipo not in ALLOWED_PC_TOOLS:
        raise ValueError("Comando nao autorizado para o agente do PC.")
    payload = payload or {}
    if tipo == "abrir_aplicativo_autorizado":
        programa = payload.get("programa")
        if not isinstance(programa, str) or not programa.strip():
            raise ValueError("Informe apenas a chave de um programa autorizado.")
        forbidden = ("\\", "/", ":", "..", ".exe", ".bat", ".ps1")
        if any(part in programa for part in forbidden):
            raise ValueError("Caminho arbitrario bloqueado. Use somente a chave autorizada.")


def create_pc_command(db: Session, usuario_id: int, dispositivo: DispositivoPC, tipo: str, payload: dict | None = None) -> ComandoPC:
    payload = payload or {}
    ensure_allowed_command(tipo, payload)
    now = utcnow()
    status = "aguardando_confirmacao" if tipo in CONFIRMATION_REQUIRED else "pendente"
    comando = ComandoPC(
        dispositivo_id=dispositivo.id,
        usuario_id=usuario_id,
        tipo=tipo,
        payload_json=json.dumps(payload, ensure_ascii=True),
        status=status,
        solicitado_em=now,
        expira_em=now + timedelta(minutes=15),
    )
    db.add(comando)
    db.commit()
    db.refresh(comando)
    return comando


def confirm_pc_command(db: Session, comando: ComandoPC) -> ComandoPC:
    now = utcnow()
    expira_em = comando.expira_em
    if expira_em.tzinfo is None:
        expira_em = expira_em.replace(tzinfo=timezone.utc)
    if comando.status != "aguardando_confirmacao":
        raise ValueError("Comando nao esta aguardando confirmacao.")
    if expira_em < now:
        comando.status = "expirado"
        db.commit()
        raise ValueError("Comando expirado.")
    comando.status = "pendente"
    comando.confirmado_em = now
    db.commit()
    db.refresh(comando)
    return comando


def cancel_pc_command(db: Session, comando: ComandoPC) -> ComandoPC:
    if comando.status in {"concluido", "executando"}:
        raise ValueError("Comando ja foi iniciado e nao pode ser cancelado.")
    comando.status = "cancelado"
    comando.concluido_em = utcnow()
    db.commit()
    db.refresh(comando)
    return comando


def next_pending_command(db: Session, dispositivo_id: int) -> ComandoPC | None:
    now = utcnow()
    expired = db.query(ComandoPC).filter(
        ComandoPC.dispositivo_id == dispositivo_id,
        ComandoPC.status.in_(["aguardando_confirmacao", "pendente"]),
        ComandoPC.expira_em < now,
    ).all()
    for comando in expired:
        comando.status = "expirado"
        comando.concluido_em = now
    if expired:
        db.commit()
    comando = db.query(ComandoPC).filter(
        ComandoPC.dispositivo_id == dispositivo_id,
        ComandoPC.status == "pendente",
    ).order_by(ComandoPC.solicitado_em.asc()).first()
    if comando:
        comando.status = "executando"
        comando.iniciado_em = now
        db.commit()
        db.refresh(comando)
    return comando


def finish_pc_command(
    db: Session,
    comando: ComandoPC,
    *,
    ok: bool,
    resultado: dict | None = None,
    erro_codigo: str | None = None,
    erro_mensagem: str | None = None,
) -> ComandoPC:
    if comando.status == "concluido":
        return comando
    comando.status = "concluido" if ok else "erro"
    comando.resultado_json = json.dumps(resultado or {}, ensure_ascii=True)
    comando.erro_codigo = erro_codigo
    comando.erro_mensagem = erro_mensagem
    comando.concluido_em = utcnow()
    db.commit()
    db.refresh(comando)
    return comando
