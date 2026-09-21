from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..dependencies import client_ip, get_current_user, get_db
from ..models import DispositivoPC, Usuario
from ..services.device_service import (
    confirm_pairing,
    create_pairing_code,
    get_device_by_token,
    mark_disconnected_devices,
    serialize_device,
    update_heartbeat,
)


router = APIRouter(prefix="/api/dispositivos", tags=["devices"])
agent_scheme = HTTPBearer(auto_error=False)


class PairingConfirmRequest(BaseModel):
    codigo: str = Field(min_length=6, max_length=6)
    nome: str = Field(default="PC", max_length=120)
    versao_agente: str = Field(default="0.1.0", max_length=40)
    sistema_operacional: str | None = Field(default=None, max_length=80)


class HeartbeatRequest(BaseModel):
    identificador: str | None = None
    versao_agente: str = "0.1.0"
    sistema_operacional: str | None = None
    horario: str | None = None
    status: dict = Field(default_factory=dict)


def _agent_device(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(agent_scheme),
    db: Session = Depends(get_db),
) -> DispositivoPC:
    return get_device_by_token(request, credentials, db)


@router.post("/pareamento/criar")
def criar_pareamento(
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    codigo, pairing = create_pairing_code(db, usuario.id)
    registrar_auditoria(db, usuario.id, "criar_pareamento_pc", "pc_agent", "Codigo de pareamento criado", client_ip(request), True)
    return {"codigo": codigo, "expira_em": pairing.expira_em.isoformat()}


@router.post("/pareamento/confirmar")
def confirmar_pareamento(payload: PairingConfirmRequest, request: Request, db: Session = Depends(get_db)):
    token, device = confirm_pairing(
        db,
        code=payload.codigo,
        name=payload.nome,
        agent_version=payload.versao_agente,
        operating_system=payload.sistema_operacional,
        ip_address=client_ip(request),
    )
    registrar_auditoria(db, device.usuario_id, "confirmar_pareamento_pc", "pc_agent", "Dispositivo pareado", client_ip(request), True)
    return {"device_token": token, "dispositivo": serialize_device(device)}


@router.get("/pc")
def listar_dispositivos(usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    mark_disconnected_devices(db)
    devices = db.query(DispositivoPC).filter(DispositivoPC.usuario_id == usuario.id).order_by(DispositivoPC.id.desc()).all()
    return {"dispositivos": [serialize_device(device) for device in devices]}


@router.get("/pc/{device_id}")
def obter_dispositivo(device_id: int, usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    mark_disconnected_devices(db)
    device = db.query(DispositivoPC).filter(DispositivoPC.id == device_id, DispositivoPC.usuario_id == usuario.id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo nao encontrado")
    return serialize_device(device)


@router.post("/pc/{device_id}/revogar")
def revogar_dispositivo(
    device_id: int,
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.query(DispositivoPC).filter(DispositivoPC.id == device_id, DispositivoPC.usuario_id == usuario.id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo nao encontrado")
    device.status = "revogado"
    device.revogado_em = datetime.now(timezone.utc)
    db.commit()
    registrar_auditoria(db, usuario.id, "revogar_dispositivo_pc", "pc_agent", f"Dispositivo revogado: {device.nome}", client_ip(request), True)
    return {"ok": True, "dispositivo": serialize_device(device)}


@router.get("/pc/{device_id}/status")
def status_dispositivo(device_id: int, usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    mark_disconnected_devices(db)
    device = db.query(DispositivoPC).filter(DispositivoPC.id == device_id, DispositivoPC.usuario_id == usuario.id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo nao encontrado")
    return serialize_device(device)


@router.post("/agente/heartbeat")
def agente_heartbeat(
    payload: HeartbeatRequest,
    request: Request,
    device: DispositivoPC = Depends(_agent_device),
    db: Session = Depends(get_db),
):
    status_payload = {
        **payload.status,
        "identificador": device.identificador,
        "versao_agente": payload.versao_agente,
        "sistema_operacional": payload.sistema_operacional,
        "horario": payload.horario,
    }
    update_heartbeat(db, device, ip_address=client_ip(request), status_payload=status_payload)
    return {"ok": True, "status": "conectado"}
