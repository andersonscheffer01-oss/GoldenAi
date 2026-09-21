from __future__ import annotations

import logging
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .models import Auditoria

logger = logging.getLogger(__name__)


def registrar_auditoria(
    db: Session,
    usuario_id: int | None,
    acao: str,
    modulo: str,
    descricao: str,
    ip: str | None,
    sucesso: bool,
) -> Auditoria:
    registro = Auditoria(
        usuario_id=usuario_id,
        acao=acao,
        modulo=modulo,
        descricao=descricao,
        ip=ip,
        sucesso=sucesso,
    )
    for attempt in range(4):
        try:
            db.add(registro)
            db.commit()
            db.refresh(registro)
            return registro
        except OperationalError as exc:
            db.rollback()
            if "database is locked" not in str(exc).lower() or attempt == 3:
                logger.warning("Falha segura ao persistir auditoria: %s", acao)
                return registro
            time.sleep(0.15 * (attempt + 1))
    return registro
