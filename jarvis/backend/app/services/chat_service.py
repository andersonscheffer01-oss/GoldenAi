from __future__ import annotations

import time

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Conversa, Mensagem, Usuario
from .ollama_client import SYSTEM_PROMPT, OllamaError, chat_with_ollama


def _title_from_content(content: str) -> str:
    compact = " ".join(content.split())
    return compact[:77] + "..." if len(compact) > 80 else compact or "Nova conversa"


def create_conversation(db: Session, user: Usuario, title: str = "Nova conversa") -> Conversa:
    conversation = Conversa(usuario_id=user.id, titulo=title.strip()[:80] or "Nova conversa")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def conversation_for_user(db: Session, conversation_id: int, user: Usuario) -> Conversa | None:
    return db.query(Conversa).filter(Conversa.id == conversation_id, Conversa.usuario_id == user.id).first()


async def send_message(db: Session, user: Usuario, conversation: Conversa, content: str, settings: Settings) -> tuple[Mensagem, Mensagem | None, str, OllamaError | None]:
    user_message = Mensagem(
        conversa_id=conversation.id, usuario_id=user.id, papel="usuario", conteudo=content, status="enviada"
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    recent = (
        db.query(Mensagem)
        .filter(Mensagem.conversa_id == conversation.id, Mensagem.usuario_id == user.id)
        .order_by(Mensagem.id.desc())
        .limit(settings.chat_history_limit)
        .all()
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(
        {"role": "user" if item.papel == "usuario" else "assistant" if item.papel == "assistente" else "system", "content": item.conteudo}
        for item in reversed(recent)
    )
    started = time.perf_counter()
    try:
        response_content, tokens = await chat_with_ollama(messages, settings)
    except OllamaError as error:
        user_message.status = "erro"
        db.commit()
        return user_message, None, "erro", error

    response_message = Mensagem(
        conversa_id=conversation.id,
        usuario_id=user.id,
        papel="assistente",
        conteudo=response_content,
        modelo=settings.ollama_model,
        tokens_estimados=tokens,
        tempo_resposta_ms=round((time.perf_counter() - started) * 1000),
        status="respondida",
    )
    user_message.status = "respondida"
    if len([item for item in recent if item.papel == "usuario"]) == 1:
        conversation.titulo = _title_from_content(content)
    conversation.atualizada_em = conversation.atualizada_em
    db.add(response_message)
    db.commit()
    db.refresh(response_message)
    return user_message, response_message, "respondida", None
