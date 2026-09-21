from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..config import Settings
from ..dependencies import client_ip, get_current_user, get_db
from ..models import Conversa, Mensagem, Usuario
from ..schemas import ChatMessageCreate, ConversaCreate, ConversaDetalhe, ConversaPublic, MensagemPublic
from ..services.chat_service import conversation_for_user, create_conversation, send_message
from ..services.ollama_client import OllamaError


router = APIRouter(prefix="/api/chat", tags=["chat"])
_rate_window: dict[int, deque[float]] = defaultdict(deque)
_MAX_REQUESTS_PER_MINUTE = 20


def _check_rate_limit(user_id: int) -> None:
    now = monotonic()
    bucket = _rate_window[user_id]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= _MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Muitas mensagens em pouco tempo. Aguarde um momento.")
    bucket.append(now)


@router.post("/conversas", response_model=ConversaPublic, status_code=status.HTTP_201_CREATED)
def create_chat_conversation(payload: ConversaCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = create_conversation(db, user, payload.titulo)
    registrar_auditoria(db, user.id, "conversa_criada", "chat", f"Conversa {conversation.id} criada", client_ip(request), True)
    return conversation


@router.get("/conversas", response_model=list[ConversaPublic])
def list_chat_conversations(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Conversa).filter(Conversa.usuario_id == user.id, Conversa.ativa.is_(True)).order_by(Conversa.atualizada_em.desc()).all()


@router.get("/conversas/{conversation_id}", response_model=ConversaDetalhe)
def get_chat_conversation(conversation_id: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = conversation_for_user(db, conversation_id, user)
    if not conversation or not conversation.ativa:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")
    return {**conversation.__dict__, "mensagens": conversation.mensagens}


@router.delete("/conversas/{conversation_id}")
def delete_chat_conversation(conversation_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = conversation_for_user(db, conversation_id, user)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")
    conversation.ativa = False
    db.commit()
    registrar_auditoria(db, user.id, "conversa_excluida", "chat", f"Conversa {conversation_id} excluida", client_ip(request), True)
    return {"ok": True, "message": "Conversa excluida"}


@router.post("/mensagem")
async def post_chat_message(payload: ChatMessageCreate, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = Settings()
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="A mensagem nao pode estar vazia")
    if len(content) > settings.chat_max_message_length:
        raise HTTPException(status_code=422, detail=f"A mensagem pode ter no maximo {settings.chat_max_message_length} caracteres")
    _check_rate_limit(user.id)
    conversation = conversation_for_user(db, payload.conversation_id, user) if payload.conversation_id else None
    if payload.conversation_id and (not conversation or not conversation.ativa):
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")
    if conversation is None:
        conversation = create_conversation(db, user)
    user_message, assistant_message, result_status, error = await send_message(db, user, conversation, content, settings)
    if error:
        registrar_auditoria(db, user.id, "mensagem_erro", "chat", error.code, client_ip(request), False)
        raise HTTPException(status_code=503, detail={"status": "erro", "code": error.code, "message": error.public_message})
    registrar_auditoria(db, user.id, "mensagem_enviada", "chat", f"Mensagem na conversa {conversation.id}", client_ip(request), True)
    return {
        "conversation_id": conversation.id,
        "user_message": MensagemPublic.model_validate(user_message),
        "assistant_message": MensagemPublic.model_validate(assistant_message),
        "status": result_status,
    }
