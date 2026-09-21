"""Golden Memory Engine V2 — compatibilidade com memória legada (M1.0).

Lê o banco/sistema atual SEM migrar fisicamente e SEM alterar nada.
Código antigo (GoldenMemoryManager) continua funcionando 1:1.
"""
import time
from typing import Any, Dict, List, Optional

from ...orchestrator.models import DataClassification
from .record import MemoryRecordV2
from .types import (ConfidenceBasis, MemoryKind, RecordStatus, SourceType)

_LEGACY_TYPE_TO_KIND = {"session": MemoryKind.SESSION,
                        "episodic": MemoryKind.EPISODIC,
                        "semantic": MemoryKind.SEMANTIC}

_LEGACY_SOURCE_TO_TYPE = {"user": SourceType.USER_EXPLICIT,
                          "jarvis": SourceType.AGENT,
                          "tool": SourceType.SYSTEM,
                          "golden": SourceType.SYSTEM,
                          "radar": SourceType.SYSTEM,
                          "agent": SourceType.AGENT,
                          "import": SourceType.IMPORT,
                          "system": SourceType.SYSTEM}


class LegacyMemoryAdapter:
    """Enxerga o legado como registros V2 (somente leitura)."""

    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def to_v2(record) -> MemoryRecordV2:
        kind = _LEGACY_TYPE_TO_KIND.get(str(getattr(record.memory_type, "value",
                                                    record.memory_type)), MemoryKind.SEMANTIC)
        source = _LEGACY_SOURCE_TO_TYPE.get(str(getattr(record.source, "value",
                                                        record.source)), SourceType.LEGACY)
        return MemoryRecordV2(
            id=record.id, memory_type=kind, title="", content=record.content,
            summary=record.summary,
            status=RecordStatus.ACTIVE if record.active else RecordStatus.ARCHIVED,
            created_at=record.created_at, updated_at=record.updated_at,
            last_accessed_at=record.last_accessed_at, version=1,
            confidence=float(record.confidence),
            confidence_basis=ConfidenceBasis.INFERRED,
            privacy=DataClassification.INTERNAL, source_type=source,
            source_ref=str(record.source_id or ""),
            source_timestamp=record.created_at, project=record.namespace,
            tags=[], metadata=dict(record.metadata or {}),
            embedding_status=("ok" if record.embedding else "pending"),
            embedding_model="", content_hash="", canonical_key="")

    def recall(self, query: str, limit: int = 8,
               namespace: str = "jarvis") -> List[MemoryRecordV2]:
        try:
            items = self.manager.search(str(query or ""), top_k=limit, namespace=namespace)
        except Exception:
            return []
        out = []
        for record in items or []:
            try:
                out.append(self.to_v2(record))
            except Exception:
                continue
        return out

    def legacy_counts(self) -> Dict[str, Any]:
        try:
            return {"memories": self.manager.db.memory_count(active=None),
                    "active": self.manager.db.memory_count(active=True)}
        except Exception:
            return {"memories": -1, "active": -1}
