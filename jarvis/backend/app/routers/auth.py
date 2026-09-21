from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..dependencies import client_ip, get_current_user, get_db
from ..models import Sessao, Usuario
from ..schemas import LoginRequest, MessageResponse, TokenResponse, UsuarioCreate, UsuarioPublic
from ..security import create_access_token, hash_password, verify_password
from ..config import get_settings
from ..services.default_categories import ensure_default_categories


router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=UsuarioPublic, status_code=status.HTTP_201_CREATED)
def register_user(payload: UsuarioCreate, request: Request, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    exists = db.query(Usuario).filter(Usuario.email == email).first()
    if exists:
        registrar_auditoria(db, None, "cadastro_falhou", "auth", f"Email ja cadastrado: {email}", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado")

    usuario = Usuario(nome=payload.nome.strip(), email=email, senha_hash=hash_password(payload.senha), ativo=True)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    ensure_default_categories(db, usuario.id)
    registrar_auditoria(db, usuario.id, "cadastro_usuario", "auth", "Usuario cadastrado", client_ip(request), True)
    return usuario


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    usuario = db.query(Usuario).filter(Usuario.email == email, Usuario.ativo.is_(True)).first()
    if not usuario or not verify_password(payload.senha, usuario.senha_hash):
        registrar_auditoria(db, usuario.id if usuario else None, "login_falhou", "auth", f"Falha de login: {email}", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha invalidos")

    token, token_id, expires_at = create_access_token(usuario.id, usuario.email)
    sessao = Sessao(usuario_id=usuario.id, token_id=token_id, expira_em=expires_at, ativo=True)
    db.add(sessao)
    db.commit()
    registrar_auditoria(db, usuario.id, "login_realizado", "auth", "Login realizado", client_ip(request), True)
    settings = get_settings()
    if settings.environment == "production":
        response.set_cookie(
            "jarvis_session",
            token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=settings.access_token_expire_minutes * 60,
            path="/",
        )
    return TokenResponse(access_token=token, expires_at=expires_at, usuario=usuario)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth = request.headers.get("authorization", "")
    token = auth.split(" ", 1)[1] if " " in auth else request.cookies.get("jarvis_session", "")
    from ..security import decode_access_token

    payload = decode_access_token(token)
    token_id = str(payload.get("jti"))
    sessao = db.query(Sessao).filter(Sessao.token_id == token_id, Sessao.usuario_id == usuario.id).first()
    if sessao:
        sessao.ativo = False
        sessao.revogado_em = datetime.now(timezone.utc)
        db.commit()
    registrar_auditoria(db, usuario.id, "logout", "auth", "Logout realizado", client_ip(request), True)
    response.delete_cookie("jarvis_session", path="/")
    return {"ok": True, "message": "Logout realizado"}


@router.get("/me", response_model=UsuarioPublic)
def me(usuario: Usuario = Depends(get_current_user)):
    return usuario
