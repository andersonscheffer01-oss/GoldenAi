from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..dependencies import client_ip, get_current_user, get_db
from ..models import ComandoPC, DispositivoPC, Usuario
from ..services.device_service import get_device_by_token, mark_disconnected_devices, serialize_device
from ..services.pc_command_service import (
    ALLOWED_PC_TOOLS,
    BLOCKED_PC_TOOLS,
    cancel_pc_command,
    confirm_pc_command,
    create_pc_command,
    finish_pc_command,
    next_pending_command,
    parse_json,
)


router = APIRouter(prefix="/api/pc", tags=["pc-commands"])
agent_scheme = HTTPBearer(auto_error=False)


class CommandCreateRequest(BaseModel):
    dispositivo_id: int
    tipo: str
    payload: dict = Field(default_factory=dict)


class CommandResultRequest(BaseModel):
    ok: bool
    resultado: dict = Field(default_factory=dict)
    erro_codigo: str | None = None
    erro_mensagem: str | None = None


def _agent_device(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(agent_scheme),
    db: Session = Depends(get_db),
) -> DispositivoPC:
    return get_device_by_token(request, credentials, db)


def serialize_command(command: ComandoPC) -> dict:
    return {
        "id": command.id,
        "dispositivo_id": command.dispositivo_id,
        "usuario_id": command.usuario_id,
        "tipo": command.tipo,
        "payload": parse_json(command.payload_json),
        "status": command.status,
        "resultado": parse_json(command.resultado_json),
        "erro_codigo": command.erro_codigo,
        "erro_mensagem": command.erro_mensagem,
        "solicitado_em": command.solicitado_em.isoformat() if command.solicitado_em else None,
        "iniciado_em": command.iniciado_em.isoformat() if command.iniciado_em else None,
        "concluido_em": command.concluido_em.isoformat() if command.concluido_em else None,
        "confirmado_em": command.confirmado_em.isoformat() if command.confirmado_em else None,
        "expira_em": command.expira_em.isoformat() if command.expira_em else None,
    }


@router.get("/status")
def status_pc(usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    mark_disconnected_devices(db)
    device = db.query(DispositivoPC).filter(
        DispositivoPC.usuario_id == usuario.id,
        DispositivoPC.revogado_em.is_(None),
    ).order_by(DispositivoPC.ultimo_ping.desc().nullslast()).first()
    if not device:
        return {"status": "desconectado", "message": "O computador esta desconectado. Nao consigo consultar o estado neste momento."}
    data = serialize_device(device)
    status_data = data.get("status_pc") or {}
    return {
        "dispositivo": device.nome,
        "status": device.status,
        "sistema": device.sistema_operacional,
        "cpu_percentual": status_data.get("cpu_percentual"),
        "memoria_percentual": status_data.get("memoria_percentual"),
        "disco_livre_gb": status_data.get("disco_livre_gb"),
        "ollama": status_data.get("ollama", "verificar"),
        "jarvis": status_data.get("jarvis", "verificar"),
        "mt5": status_data.get("mt5", "verificar"),
        "atualizado_em": device.ultimo_ping.isoformat() if device.ultimo_ping else None,
    }


@router.get("/ferramentas")
def ferramentas_pc(usuario: Usuario = Depends(get_current_user)):
    return {"permitidas": sorted(ALLOWED_PC_TOOLS), "bloqueadas": sorted(BLOCKED_PC_TOOLS)}


@router.post("/comandos")
def criar_comando_pc(
    payload: CommandCreateRequest,
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.query(DispositivoPC).filter(
        DispositivoPC.id == payload.dispositivo_id,
        DispositivoPC.usuario_id == usuario.id,
        DispositivoPC.revogado_em.is_(None),
    ).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo nao encontrado")
    try:
        command = create_pc_command(db, usuario.id, device, payload.tipo, payload.payload)
    except ValueError as exc:
        registrar_auditoria(db, usuario.id, "comando_pc_bloqueado", "pc_agent", str(exc), client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    registrar_auditoria(db, usuario.id, "criar_comando_pc", "pc_agent", f"Comando solicitado: {payload.tipo}", client_ip(request), True)
    return serialize_command(command)


@router.get("/comandos")
def listar_comandos_pc(usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    commands = db.query(ComandoPC).filter(ComandoPC.usuario_id == usuario.id).order_by(ComandoPC.id.desc()).limit(50).all()
    return {"comandos": [serialize_command(command) for command in commands]}


@router.get("/comandos/{command_id}")
def obter_comando_pc(command_id: int, usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    command = db.query(ComandoPC).filter(ComandoPC.id == command_id, ComandoPC.usuario_id == usuario.id).first()
    if not command:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando nao encontrado")
    return serialize_command(command)


@router.post("/comandos/{command_id}/confirmar")
def confirmar_comando_pc(
    command_id: int,
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    command = db.query(ComandoPC).filter(ComandoPC.id == command_id, ComandoPC.usuario_id == usuario.id).first()
    if not command:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando nao encontrado")
    try:
        command = confirm_pc_command(db, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    registrar_auditoria(db, usuario.id, "confirmar_comando_pc", "pc_agent", f"Comando confirmado: {command.tipo}", client_ip(request), True)
    return serialize_command(command)


@router.post("/comandos/{command_id}/cancelar")
def cancelar_comando_pc(
    command_id: int,
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    command = db.query(ComandoPC).filter(ComandoPC.id == command_id, ComandoPC.usuario_id == usuario.id).first()
    if not command:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando nao encontrado")
    try:
        command = cancel_pc_command(db, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    registrar_auditoria(db, usuario.id, "cancelar_comando_pc", "pc_agent", f"Comando cancelado: {command.tipo}", client_ip(request), True)
    return serialize_command(command)


@router.get("/agente/comandos/proximo")
def agente_proximo_comando(device: DispositivoPC = Depends(_agent_device), db: Session = Depends(get_db)):
    command = next_pending_command(db, device.id)
    return {"comando": serialize_command(command) if command else None}


@router.post("/agente/comandos/{command_id}/resultado")
def agente_resultado_comando(
    command_id: int,
    payload: CommandResultRequest,
    device: DispositivoPC = Depends(_agent_device),
    db: Session = Depends(get_db),
):
    command = db.query(ComandoPC).filter(ComandoPC.id == command_id, ComandoPC.dispositivo_id == device.id).first()
    if not command:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando nao encontrado")
    command = finish_pc_command(
        db,
        command,
        ok=payload.ok,
        resultado=payload.resultado,
        erro_codigo=payload.erro_codigo,
        erro_mensagem=payload.erro_mensagem,
    )
    return serialize_command(command)
