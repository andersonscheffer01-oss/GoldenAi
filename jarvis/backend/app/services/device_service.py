from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DispositivoPC, PareamentoPC


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_secret(value: str) -> str:
    salt = get_settings().secret_key
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def hash_pairing_code(code: str) -> str:
    return _hash_secret(f"pairing:{code}")


def hash_device_token(token: str) -> str:
    return _hash_secret(f"device:{token}")


def create_pairing_code(db: Session, usuario_id: int) -> tuple[str, PareamentoPC]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    pairing = PareamentoPC(
        usuario_id=usuario_id,
        codigo_hash=hash_pairing_code(code),
        expira_em=utcnow() + timedelta(minutes=10),
    )
    db.add(pairing)
    db.commit()
    db.refresh(pairing)
    return code, pairing


def confirm_pairing(
    db: Session,
    *,
    code: str,
    name: str,
    agent_version: str,
    operating_system: str | None,
    ip_address: str | None,
) -> tuple[str, DispositivoPC]:
    now = utcnow()
    pairing = db.query(PareamentoPC).filter(PareamentoPC.codigo_hash == hash_pairing_code(code)).first()
    if not pairing:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Codigo de pareamento invalido")
    expira_em = pairing.expira_em
    if expira_em.tzinfo is None:
        expira_em = expira_em.replace(tzinfo=timezone.utc)
    if pairing.usado_em is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Codigo de pareamento ja utilizado")
    if expira_em < now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Codigo de pareamento expirado")

    token = secrets.token_urlsafe(40)
    device = DispositivoPC(
        usuario_id=pairing.usuario_id,
        nome=name.strip()[:120] or "PC",
        identificador=uuid4().hex,
        sistema_operacional=operating_system,
        versao_agente=agent_version.strip()[:40] or "0.1.0",
        token_hash=hash_device_token(token),
        status="conectado",
        ultimo_ping=now,
        ip_rede=ip_address,
    )
    pairing.usado_em = now
    db.add(device)
    db.commit()
    db.refresh(device)
    return token, device


def serialize_device(device: DispositivoPC) -> dict[str, Any]:
    status_data = {}
    if device.status_json:
        try:
            parsed = json.loads(device.status_json)
            if isinstance(parsed, dict):
                status_data = parsed
        except json.JSONDecodeError:
            status_data = {}
    return {
        "id": device.id,
        "nome": device.nome,
        "identificador": device.identificador,
        "sistema_operacional": device.sistema_operacional,
        "versao_agente": device.versao_agente,
        "status": device.status,
        "ultimo_ping": device.ultimo_ping.isoformat() if device.ultimo_ping else None,
        "ip_rede": device.ip_rede,
        "criado_em": device.criado_em.isoformat() if device.criado_em else None,
        "atualizado_em": device.atualizado_em.isoformat() if device.atualizado_em else None,
        "revogado_em": device.revogado_em.isoformat() if device.revogado_em else None,
        "status_pc": status_data,
    }


def get_device_by_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> DispositivoPC:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token do dispositivo ausente")
    token_hash = hash_device_token(credentials.credentials)
    device = db.query(DispositivoPC).filter(DispositivoPC.token_hash == token_hash).first()
    if not device or device.revogado_em is not None or device.status == "revogado":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token do dispositivo invalido")
    return device


def update_heartbeat(
    db: Session,
    device: DispositivoPC,
    *,
    ip_address: str | None,
    status_payload: dict[str, Any],
) -> DispositivoPC:
    device.status = "conectado"
    device.ultimo_ping = utcnow()
    device.ip_rede = ip_address
    if status_payload.get("versao_agente"):
        device.versao_agente = str(status_payload["versao_agente"])[:40]
    if status_payload.get("sistema_operacional"):
        device.sistema_operacional = str(status_payload["sistema_operacional"])[:80]
    device.status_json = json.dumps(status_payload, ensure_ascii=True)
    db.commit()
    db.refresh(device)
    return device


def mark_disconnected_devices(db: Session, seconds: int = 90) -> None:
    threshold = utcnow() - timedelta(seconds=seconds)
    devices = db.query(DispositivoPC).filter(
        DispositivoPC.status == "conectado",
        DispositivoPC.revogado_em.is_(None),
        DispositivoPC.ultimo_ping < threshold,
    ).all()
    for device in devices:
        device.status = "desconectado"
    if devices:
        db.commit()
