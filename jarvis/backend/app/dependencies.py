from __future__ import annotations

from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .audit import registrar_auditoria
from .database import SessionLocal
from .models import Sessao, Usuario
from .security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    if request.client:
        return request.client.host
    return ""


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    token = credentials.credentials if credentials else request.cookies.get("jarvis_session")
    if not token:
        registrar_auditoria(db, None, "acesso_negado", "auth", "Token ausente", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")

    try:
        payload = decode_access_token(token)
        usuario_id = int(payload.get("sub"))
        token_id = str(payload.get("jti"))
    except (jwt.InvalidTokenError, TypeError, ValueError):
        registrar_auditoria(db, None, "acesso_negado", "auth", "Token invalido", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    sessao = db.query(Sessao).filter(Sessao.token_id == token_id).first()
    now = datetime.now(timezone.utc)
    expira_em = sessao.expira_em if sessao else None
    if expira_em is not None and expira_em.tzinfo is None:
        expira_em = expira_em.replace(tzinfo=timezone.utc)
    if not sessao or not sessao.ativo or sessao.revogado_em is not None or expira_em < now:
        registrar_auditoria(db, usuario_id, "acesso_negado", "auth", "Sessao expirada ou revogada", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao expirada ou revogada")

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.ativo.is_(True)).first()
    if not usuario:
        registrar_auditoria(db, usuario_id, "acesso_negado", "auth", "Usuario inativo ou inexistente", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inativo ou inexistente")
    return usuario
