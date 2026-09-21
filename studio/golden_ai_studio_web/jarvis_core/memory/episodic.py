# ═══════════════════════════════════════════════════════════════════
# memory/episodic.py
# √ (Golden Jarvis 2.0) Memória episódica
# ═══════════════════════════════════════════════════════════════════
import re
import time
from typing import Any, Dict, Optional

from .database import Database
from .models import MemoryCategory, MemoryRecord, MemorySource, MemoryType


MARKER_WEIGHTS: Dict[str, int] = {
    "lembre": 75,
    "guarde": 75,
    "quero lembrar": 75,
    "register": 75,
    "guarda": 75,
}

trivial_tokens = frozenset({
    "que horas", "hora atual", "data de hoje", "aumente volume", "diminua volume",
    "silencie", "mute", "tirar print", "screenshot", "capture", "tirar captura",
    "print da tela", "print", "fechar janela", "maximizar", "minimizar", "bateria",
    "ip", "usuario", "processo", "listar",
})


class EpisodicMemory:
    def __init__(self, db: Database):
        self.db = db

    def create(self, content: str, source: MemorySource = MemorySource.JARVIS,
               session_id: Optional[str] = None, source_id: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None, importance: Optional[int] = None) -> int:
        text = self._normalize(content).strip()
        if not text or self._is_trivial(text):
            return 0
        importance = importance if importance is not None else 50
        record = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            category=MemoryCategory.GENERAL,
            content=content,
            summary=self._summarize(content),
            importance=min(100, max(0, importance)),
            confidence=0.5,
            source=source,
            source_id=source_id,
            session_id=session_id,
            namespace="jarvis",
            metadata=metadata or {},
        )
        return self.db.memory_upsert(record)

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _summarize(self, content: str, length: int = 120) -> str:
        clean = re.sub(r"<[^>]+>", " ", content)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) <= length:
            return clean
        return clean[: length - 1].rsplit(" ", 1)[0].rstrip() + "…"

    def _is_trivial(self, text: str) -> bool:
        if not text:
            return True
        if len(text) < 8:
            return True
        for marker in trivial_tokens:
            if marker in text:
                return True
        return False
