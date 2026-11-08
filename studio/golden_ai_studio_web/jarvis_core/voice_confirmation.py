"""Fail-closed voice confirmation recognition."""
from __future__ import annotations

import re
import unicodedata


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()


def classify_confirmation(text: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", _fold(text)).strip()
    if normalized in {"sim", "sim confirmo", "confirmar", "confirma", "pode", "autorizar"}:
        return "approve"
    if normalized in {"nao", "não", "cancelar", "cancela", "pare", "recusar"}:
        return "deny"
    return None

