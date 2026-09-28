"""Canonical memory boundary for selected Jarvis service callers.

V2 is the single writer when available. The legacy manager is retained only
as an explicit compatibility fallback until its remaining callers migrate.
"""

from typing import Any, Dict, List, Optional

from .models import MemoryCategory, MemorySource
from .v2.migrations import v2_connect
from .v2.types import ConfidenceBasis, MemoryKind, SourceType


class CanonicalMemoryBoundary:
    """Expose the stable service memory-tool contract over one store."""

    def __init__(self, canonical=None, legacy=None):
        self.canonical = canonical
        self.legacy = legacy

    @property
    def mode(self) -> str:
        return "v2" if self.canonical is not None else "legacy_compatibility"

    @staticmethod
    def _v2_record_dict(record) -> Dict[str, Any]:
        status = str(getattr(record.status, "value", record.status))
        metadata = dict(record.metadata or {})
        return {
            "id": record.id,
            "type": str(getattr(record.memory_type, "value", record.memory_type)),
            "category": metadata.get("category", MemoryCategory.GENERAL.value),
            "content": record.content,
            "importance": int(round(float(record.confidence) * 100)),
            "confidence": record.confidence,
            "source": str(getattr(record.source_type, "value", record.source_type)),
            "source_id": record.source_ref or None,
            "session_id": metadata.get("session_id"),
            "namespace": record.project or "jarvis",
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "last_accessed_at": record.last_accessed_at,
            "access_count": int(metadata.get("access_count", 0) or 0),
            "active": status not in {"archived", "deleted_logical", "superseded"},
            "metadata": metadata,
        }

    def _legacy_record_dict(self, record) -> Dict[str, Any]:
        return {
            "id": record.id,
            "type": record.memory_type.value,
            "category": record.category.value,
            "content": record.content,
            "importance": record.importance,
            "confidence": record.confidence,
            "source": record.source.value,
            "source_id": record.source_id,
            "session_id": record.session_id,
            "namespace": record.namespace,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "last_accessed_at": record.last_accessed_at,
            "access_count": record.access_count,
            "active": record.active,
            "metadata": record.metadata,
        }

    def search(self, query: str, namespace: str = "jarvis", limit: int = 8) -> List[Dict[str, Any]]:
        if self.canonical is None:
            items = self.legacy.search(query, top_k=limit, namespace=namespace)
            return [self._legacy_record_dict(item) for item in items]
        report = self.canonical.hybrid_search(
            query, limit=limit, project=namespace, clearance="INTERNAL")
        records = []
        for result in report.results:
            record = self.canonical.get(result.memory_id)
            if record is not None:
                records.append(self._v2_record_dict(record))
        return records

    def remember(self, content: str, namespace: str = "jarvis") -> Dict[str, Any]:
        if self.canonical is None:
            rid = self.legacy.remember(
                content, source=MemorySource.USER,
                category=MemoryCategory.GENERAL, importance=75,
                confidence=0.95, namespace=namespace)
            return {"ok": bool(rid), "id": rid, "mode": self.mode}
        try:
            record = self.canonical.remember(
                content, memory_type=MemoryKind.SEMANTIC, confidence=0.95,
                confidence_basis=ConfidenceBasis.USER_CONFIRMED,
                source_type=SourceType.USER_EXPLICIT, project=namespace,
                metadata={"category": MemoryCategory.GENERAL.value,
                          "compatibility": "jarvis_memory_tool"})
        except Exception as exc:
            return {"ok": False, "id": 0, "mode": self.mode,
                    "error": str(exc)[:160]}
        return {"ok": bool(record.id), "id": record.id, "mode": self.mode}

    def recent(self, limit: int = 10, namespace: str = "jarvis") -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 50))
        if self.canonical is None:
            items = self.legacy.get_recent(limit=limit, namespace=namespace)
            return [self._legacy_record_dict(item) for item in items]
        with v2_connect(self.canonical.db_path) as conn:
            rows = conn.execute(
                "SELECT id FROM v2_memories WHERE status='active' AND project=? "
                "ORDER BY updated_at DESC LIMIT ?", (namespace, limit)).fetchall()
        return [self._v2_record_dict(self.canonical.get(int(row[0])))
                for row in rows if self.canonical.get(int(row[0])) is not None]
