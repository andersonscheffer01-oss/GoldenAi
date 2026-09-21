from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.execution import ExecutionService, ExecutionStatus

EMBED_MODEL = "nomic-embed-text"
COLLECTION_NAME = "golden_knowledge"
EMBED_DIM = 768


@dataclass(frozen=True)
class QdrantEnvironment:
    available: bool
    error: str = ""
    mode: str = "local"
    collection: str = COLLECTION_NAME
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorSearchResult:
    status: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""
    query: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorMemoryService:
    """Memoria semantica sobre Qdrant (modo local embutido, sem servidor).
    Embeddings via Ollama (nomic-embed-text). Complementa o
    ScientificMemoryService (busca por similaridade em vez de texto exato)."""

    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self._client = None

    # ------------------------------------------------------------------
    # Infra
    # ------------------------------------------------------------------

    def _client_instance(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            db_path = self.root / "data" / "qdrant"
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(db_path))
        return self._client

    def _ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams
        client = self._client_instance()
        if not client.collection_exists(COLLECTION_NAME):
            client.create_collection(
                COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )

    def _audit(self, action: str, status: str, target: str = "", detail: str = "") -> None:
        try:
            self.execution.record_event(
                task_id="qdrant", category="MEMORY", action=action, status=status,
                summary=detail[:600], tool_name="qdrant_service",
                permission_level="READ", risk_level="LOW",
            )
            self.audit.record({
                "action_type": action, "status": status, "agent": "core.qdrant",
                "target": target[:300], "result": detail[:600],
            })
        except Exception:
            pass

    def audit_environment(self) -> QdrantEnvironment:
        try:
            import qdrant_client
            version = getattr(qdrant_client, "__version__", "?")
            return QdrantEnvironment(
                available=True, mode="local", collection=COLLECTION_NAME,
                evidence={"qdrant_client": version, "embed_model": EMBED_MODEL},
            )
        except Exception as exc:
            return QdrantEnvironment(available=False, error=str(exc))

    def status(self) -> dict[str, Any]:
        env = self.audit_environment()
        out = {
            "QDRANT_SUPPORTED": env.available,
            "MODE": env.mode,
            "COLLECTION": env.collection,
            "EMBED_MODEL": EMBED_MODEL,
            "ERROR": env.error,
        }
        try:
            out["POINTS"] = self._client_instance().count(COLLECTION_NAME).count
        except Exception:
            out["POINTS"] = 0
        return out

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        import ollama
        text = text[:4000] if len(text) > 4000 else text
        resp = ollama.embeddings(model=EMBED_MODEL, prompt=text)
        return list(resp["embedding"])

    def _embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import ollama
        trimmed = [t[:4000] if len(t) > 4000 else t for t in texts]
        resp = ollama.embed(model=EMBED_MODEL, input=trimmed)
        return [list(v) for v in resp["embeddings"]]

    # ------------------------------------------------------------------
    # Operacoes
    # ------------------------------------------------------------------

    def store(self, text: str, *, source: str = "", kind: str = "nota", tags: list[str] | None = None) -> dict[str, Any]:
        """Indexa um texto na memoria vetorial. Retorna o id inserido."""
        env = self.audit_environment()
        if not env.available:
            return {"status": "QDRANT_NOT_AVAILABLE", "error": env.error}
        started = time.perf_counter()
        self._audit("MEMORY_STORE_STARTED", "STARTED", source or kind, text[:100])
        try:
            self._ensure_collection()
            from qdrant_client.models import PointStruct
            point_id = str(uuid.uuid4())
            vector = self._embed(text)
            payload = {
                "text": text[:20000],
                "source": source,
                "kind": kind,
                "tags": tags or [],
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._client_instance().upsert(
                COLLECTION_NAME,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("MEMORY_STORE_COMPLETED", "COMPLETED", source or kind, f"id={point_id}")
            return {"status": "COMPLETED", "id": point_id, "duration_ms": duration}
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("MEMORY_STORE_FAILED", "FAILED", source or kind, str(exc))
            return {"status": "FAILED", "error": str(exc), "duration_ms": duration}

    def store_many(self, texts: list[str], *, source: str = "", kind: str = "nota", tags: list[str] | None = None) -> dict[str, Any]:
        env = self.audit_environment()
        if not env.available:
            return {"status": "QDRANT_NOT_AVAILABLE", "error": env.error}
        if not texts:
            return {"status": "COMPLETED", "ids": [], "stored": 0}
        started = time.perf_counter()
        self._audit("MEMORY_STORE_MANY_STARTED", "STARTED", source or kind, f"n={len(texts)}")
        try:
            self._ensure_collection()
            from qdrant_client.models import PointStruct
            ids = []
            payloads = []
            vectors = self._embed_documents(texts)
            for i, (text, vec) in enumerate(zip(texts, vectors)):
                point_id = str(uuid.uuid4())
                ids.append(point_id)
                payloads.append(PointStruct(id=point_id, vector=vec, payload={
                    "text": text[:20000],
                    "source": source,
                    "kind": kind,
                    "tags": tags or [],
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }))
            self._client_instance().upsert(COLLECTION_NAME, points=payloads)
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("MEMORY_STORE_MANY_COMPLETED", "COMPLETED", source or kind, f"n={len(ids)}")
            return {"status": "COMPLETED", "ids": ids, "stored": len(ids), "duration_ms": duration}
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("MEMORY_STORE_MANY_FAILED", "FAILED", source or kind, str(exc))
            return {"status": "FAILED", "error": str(exc), "duration_ms": duration}

    def search(self, query: str, limit: int = 5, kind: str | None = None) -> VectorSearchResult:
        env = self.audit_environment()
        if not env.available:
            return VectorSearchResult("QDRANT_NOT_AVAILABLE", query=query, error=env.error)
        started = time.perf_counter()
        self._audit("MEMORY_SEARCH_STARTED", "STARTED", query, query[:100])
        try:
            self._ensure_collection()
            vector = self._embed(query)
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = None
            if kind:
                query_filter = Filter(must=[FieldCondition(key="kind", match=MatchValue(value=kind))])
            result = self._client_instance().query_points(
                COLLECTION_NAME,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            matches = []
            for hit in result.points:
                payload = hit.payload or {}
                matches.append({
                    "id": str(hit.id),
                    "score": round(float(hit.score), 4),
                    "text": payload.get("text", ""),
                    "source": payload.get("source", ""),
                    "kind": payload.get("kind", ""),
                    "tags": payload.get("tags", []),
                    "created_at": payload.get("created_at", ""),
                })
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("MEMORY_SEARCH_COMPLETED", "COMPLETED", query, f"n={len(matches)}")
            return VectorSearchResult(
                "COMPLETED", matches=matches, duration_ms=duration, query=query,
                metadata={"limit": limit, "kind": kind},
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("MEMORY_SEARCH_FAILED", "FAILED", query, str(exc))
            return VectorSearchResult("FAILED", query=query, error=str(exc), duration_ms=duration)

    def delete_collection(self) -> dict[str, Any]:
        env = self.audit_environment()
        if not env.available:
            return {"status": "QDRANT_NOT_AVAILABLE", "error": env.error}
        try:
            client = self._client_instance()
            if client.collection_exists(COLLECTION_NAME):
                client.delete_collection(COLLECTION_NAME)
            return {"status": "COMPLETED"}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}

    def close(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
                self._client = None
        except Exception:
            pass
