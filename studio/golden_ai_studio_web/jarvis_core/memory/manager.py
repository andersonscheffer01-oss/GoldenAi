# ═══════════════════════════════════════════════════════════════════
# memory/manager.py
# √ (Golden Jarvis 2.0) Gerenciador central de memória
# ═══════════════════════════════════════════════════════════════════
import json
import os
import time
import threading
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .database import Database
from .embeddings import EmbeddingService
from .episodic import EpisodicMemory
from .models import MemoryCategory, MemoryRecord, MemorySource, MemoryStatus, MemoryType
from .retrieval import RetrievalService
from .semantic import SemanticMemory
from .session import SessionMemory


class GoldenMemoryManager:
    BASE_KEY = "JARVIS_MEMORY_"
    DB_NAME = "golden_memory.db"

    def __init__(self, base_dir: Path | str):
        base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir = base_dir
        db_path = base_dir / "jarvis" / self.DB_NAME
        self.db = Database(db_path)
        self.embedding = EmbeddingService()
        self.session = SessionMemory(self.db)
        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db, self.embedding)
        self.retrieval = RetrievalService(self.db, self.embedding)
        self.lock = threading.RLock()
        self._current_session_id: Optional[str] = None
        self._last_health_check: float = 0
        self._status_cache: Optional[MemoryStatus] = None

    # ── Sessão ──────────────────────────────────────────────────────

    def start_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        with self.lock:
            self._current_session_id = self.session.start_session(metadata)
            return self._current_session_id

    def end_session(self) -> Optional[str]:
        with self.lock:
            session_id = self.session.end_session()
            self._current_session_id = None
            return session_id

    def current_session(self) -> Optional[str]:
        current = self.session.current()
        return self._current_session_id or (current.session_id if current else None)

    # ── Episódico ───────────────────────────────────────────────────

    def remember_episodic(self, content: str, source: MemorySource = MemorySource.JARVIS,
                          session_id: Optional[str] = None, source_id: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None, importance: Optional[int] = None) -> int:
        with self.lock:
            sid = session_id or self.current_session()
            rid = self.episodic.create(content, source, sid, source_id, metadata, importance)
            if rid:
                self._audit_event("memory_created", {"memory_type": "episodic", "id": rid})
            return rid

    # ── Semântico ───────────────────────────────────────────────────

    def remember(self, content: str, source: MemorySource = MemorySource.JARVIS,
                 category: Optional[MemoryCategory] = None,
                 session_id: Optional[str] = None, source_id: Optional[str] = None,
                 importance: int = 60, confidence: float = 0.7,
                 metadata: Optional[Dict[str, Any]] = None, namespace: str = "jarvis") -> int:
        with self.lock:
            if self._unsafe_content_reason(content):
                return 0
            sid = session_id or self.current_session()
            rid = self.semantic.create(content, source, category, sid, source_id, importance,
                                       confidence, metadata, namespace)
            if rid:
                self._audit_event("memory_created", {"memory_type": "semantic", "id": rid})
            return rid

    # ── Busca / Contexto ────────────────────────────────────────────

    def search(self, query: str, top_k: int = 8, namespace: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[MemoryRecord]:
        with self.lock:
            f = dict(filters or {})
            if namespace:
                f['namespace'] = namespace
            return self.retrieval.search(query, top_k, f)

    def get_context(self, query: str, top_k: int = 8, namespace: str = "jarvis") -> str:
        with self.lock:
            return self.retrieval.get_context(query, top_k, namespace)

    def get_recent(self, limit: int = 10, memory_type: Optional[MemoryType] = None,
                   namespace: Optional[str] = None) -> List[MemoryRecord]:
        with self.lock:
            return self.retrieval.get_recent(limit, memory_type, namespace)

    def get_memory(self, rid: int) -> Optional[MemoryRecord]:
        with self.lock:
            return self.retrieval.get_memory(rid)

    def deactivate_memory(self, rid: int) -> bool:
        with self.lock:
            ok = self.retrieval.deactivate(rid)
            if ok:
                self._audit_event("memory_deactivated", {"id": rid})
            return ok

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> MemoryStatus:
        with self.lock:
            if self._status_cache and time.time() - self._last_health_check < 30:
                return self._status_cache
            self._last_health_check = time.time()
            try:
                emb_status = self.embedding.status()
                deb_features: List[str] = []
                if not emb_status.get("available"):
                    deb_features.append("embedding")
                semantic_ok = "degraded" if deb_features else "ok"
                total = self.db.memory_count(active=None)
                active = self.db.memory_count(active=True)
                sess = self.session.current()
                status = MemoryStatus(
                    ok=True,
                    database="ok",
                    sessions="ok",
                    sessions_count=len(self.session.list_recent(50)),
                    semantic=semantic_ok,
                    embedding_model=emb_status.get("model_name") or "unavailable",
                    semantic_search=semantic_ok,
                    total_memories=total,
                    active_memories=active,
                    current_session=sess.session_id if sess else None,
                    degraded_features=deb_features,
                )
                self._status_cache = status
                return status
            except Exception as exc:
                status = MemoryStatus(ok=False, database="error", sessions="error", semantic="error",
                                      embedding_model="error", semantic_search="error",
                                      message=str(exc))
                self._status_cache = status
                return status

    def health_check(self) -> Dict[str, Any]:
        with self.lock:
            emb = self.embedding.health_check()
            self._status_cache = None
            return {
                "ok": emb.get("ok", False),
                "embedding_model": emb.get("model", "unknown"),
                "embedding_dimension": emb.get("dimension", 0),
                "embedding_preview": emb.get("sample_preview", []),
                "embedding_state": emb.get("state", "degraded"),
                "fallback": emb.get("fallback"),
                "memory_status": {
                    "database": self.status().database,
                    "sessions": self.status().sessions,
                    "semantic": self.status().semantic,
                    "total_memories": self.status().total_memories,
                    "active_memories": self.status().active_memories,
                },
            }

    # ── Utils internos ──────────────────────────────────────────────

    def _audit_event(self, event: str, extra: Optional[Dict[str, Any]] = None) -> None:
        try:
            from ..audit import AuditLog
            audit_path = self.base_dir / "jarvis" / "golden_runtime.db"
            audit = AuditLog(audit_path)
            audit.add(task_id="memory", command="memory." + event, tool=event,
                      arguments=extra or {}, risk="LOW", status="info",
                      result=f"evento de memória {event}")
        except Exception:
            pass

    @staticmethod
    def _unsafe_content_reason(content: Any) -> Optional[str]:
        if not isinstance(content, str):
            return "binary"
        text = content.strip()
        if not text or len(text) > 8000:
            return "empty_or_large"
        if re.search(r"(?i)\b(password|passwd|senha|token|secret|api[_-]?key|authorization|cookie|credential)\b\s*[:=]", text):
            return "secret"
        compact = re.sub(r"\s+", "", text)
        if text.lower().startswith("data:") or (len(compact) > 512 and re.fullmatch(r"[A-Za-z0-9+/=]+", compact)):
            return "binary_or_base64"
        return None
