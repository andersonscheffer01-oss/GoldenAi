# ═══════════════════════════════════════════════════════════════════
# memory/semantic.py
# √ (Golden Jarvis 2.0) Memória semântica persistente
# ═══════════════════════════════════════════════════════════════════
import hashlib
import re
import time
from typing import Any, Dict, List, Optional

from .database import Database
from .models import MemoryCategory, MemoryRecord, MemorySource, MemoryType
from .embeddings import EmbeddingService


class SemanticMemory:
    DUPLICATE_SIMILARITY_THRESHOLD = 0.92

    def __init__(self, db: Database, embedding: EmbeddingService):
        self.db = db
        self.embedding = embedding
        self._normalized_cache: Dict[str, Optional[int]] = {}

    def create(self, content: str, source: MemorySource = MemorySource.JARVIS,
               category: Optional[MemoryCategory] = None,
               session_id: Optional[str] = None, source_id: Optional[str] = None,
               importance: int = 60, confidence: float = 0.7,
               metadata: Optional[Dict[str, Any]] = None, namespace: str = "jarvis") -> int:
        content = content.strip()
        if not content:
            return 0
        existing = self._maybe_duplicate(content, namespace)
        if existing:
            self._update_existing(existing, category, importance, confidence, metadata)
            return existing
        embedding = self.embedding.embed(content)
        record = MemoryRecord(
            memory_type=MemoryType.SEMANTIC,
            category=category or MemoryCategory.GENERAL,
            content=content,
            summary=self._summarize(content),
            importance=min(100, max(0, importance)),
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
            source_id=source_id,
            session_id=session_id,
            namespace=namespace,
            metadata=metadata or {},
        )
        record.embedding = embedding if embedding else None
        return self.db.memory_upsert(record)

    def _summarize(self, content: str, length: int = 160) -> str:
        clean = re.sub(r"<[^>]+>", " ", content)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) <= length:
            return clean
        return clean[: length - 1].rsplit(" ", 1)[0].rstrip() + "…"

    def _maybe_duplicate(self, content: str, namespace: str) -> Optional[int]:
        norm = self._normalize(content)
        cache_key = f"{namespace}:{norm}"
        if cache_key in self._normalized_cache:
            return self._normalized_cache[cache_key]
        with self.db._connect() as db:
            row = db.execute(
                "SELECT id FROM memories WHERE memory_type=? AND namespace=? "
                "AND LOWER(TRIM(content))=? AND active=1",
                (MemoryType.SEMANTIC.value, namespace, norm),
            ).fetchone()
        if row:
            self._normalized_cache[cache_key] = int(row[0])
            return int(row[0])
        if self.embedding.available:
            try:
                target_embedding = self.embedding.embed_sync(content)
                if target_embedding:
                    existing = self._semantic_duplicate(content, target_embedding, namespace)
                    if existing:
                        self._normalized_cache[cache_key] = existing
                        return existing
            except Exception:
                pass
        return None

    def _semantic_duplicate(self, content: str, target_embedding: List[float], namespace: str) -> Optional[int]:
        candidates = self.db.memory_get_all(limit=300, active=True)
        for candidate in candidates:
            if candidate.memory_type != MemoryType.SEMANTIC:
                continue
            if candidate.namespace != namespace:
                continue
            emb = candidate.embedding
            if not emb or len(emb) != len(target_embedding):
                continue
            sim = self._cosine(target_embedding, emb)
            if sim >= self.DUPLICATE_SIMILARITY_THRESHOLD:
                return candidate.id
        return None

    def _cosine(self, a: List[float], b: List[float]) -> float:
        denom = (sum(x * x for x in a) ** 0.5) * (sum(x * x for x in b) ** 0.5)
        if denom == 0:
            return 0.0
        return sum(x * y for x, y in zip(a, b)) / denom

    def _update_existing(self, rid: int, category: Optional[MemoryCategory],
                         importance: int, confidence: float, metadata: Optional[Dict[str, Any]]) -> None:
        with self.db._connect() as db:
            db.execute(
                "UPDATE memories SET category=COALESCE(?, category), importance=COALESCE(?, importance), "
                "confidence=COALESCE(?, confidence), metadata=COALESCE(?, metadata), updated_at=? WHERE id=?",
                (category.value if category else None, importance if importance else None,
                 confidence if confidence else None, json_dumps(metadata) if metadata else None,
                 time.time(), rid),
            )

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _clear_normalized_cache(self) -> None:
        self._normalized_cache.clear()
