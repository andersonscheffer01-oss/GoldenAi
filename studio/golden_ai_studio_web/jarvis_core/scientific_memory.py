"""Scientific memory contracts adapted to the canonical Jarvis Memory V2.

The adapter uses existing memory records, versions, statuses and graph
relations. It does not create a second store or perform legacy imports.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .b2_contracts import EvidenceClass, content_fingerprint, utc_now
from .memory.v2.types import (ConfidenceBasis, EntityType, MemoryKind,
                               RecordStatus, RelationType, SourceType)


class ScientificContractType(str, Enum):
    EVIDENCE = "EVIDENCE"
    HYPOTHESIS = "HYPOTHESIS"
    EXPERIMENT = "EXPERIMENT"
    REVISION = "REVISION"
    CONFLICT = "CONFLICT"
    SUPERSESSION = "SUPERSESSION"


LEGACY_MEMORY_MATRIX = (
    {"legacy_concept": "typed evidence", "current_jarvis_equivalent": "MemoryRecordV2 metadata/source_type/confidence", "gap": "explicit scientific contract label", "decision": "ADAPT"},
    {"legacy_concept": "revisions", "current_jarvis_equivalent": "MemoryRecordV2 version + v2_memory_versions", "gap": "stable revision relationship", "decision": "ADAPT"},
    {"legacy_concept": "conflicts", "current_jarvis_equivalent": "RecordStatus.DISPUTED + consolidation evidence", "gap": "explicit conflict contract", "decision": "ADAPT"},
    {"legacy_concept": "supersession", "current_jarvis_equivalent": "RecordStatus.SUPERSEDED", "gap": "explicit supersedes relationship", "decision": "ADAPT"},
    {"legacy_concept": "experiment links", "current_jarvis_equivalent": "Memory V2 graph relations", "gap": "scientific relation vocabulary", "decision": "ADAPT"},
    {"legacy_concept": "hypothesis links", "current_jarvis_equivalent": "Memory V2 graph relations", "gap": "typed hypothesis/evidence contracts", "decision": "ADAPT"},
)


@dataclass(frozen=True)
class ScientificMemoryRecord:
    contract_type: str
    content: str
    source: str = ""
    artifact: str = ""
    created_at: str = ""
    observed_at: str | None = None
    status: str = "CANDIDATE"
    provenance: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    source_record_identity: str = ""
    supersedes_id: str = ""
    revises_id: str = ""
    conflicts_with_id: str = ""

    @property
    def scientific_id(self) -> str:
        return content_fingerprint({
            "contract_type": self.contract_type, "content": self.content,
            "source": self.source, "artifact": self.artifact,
            "source_record_identity": self.source_record_identity,
        })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"scientific_id": self.scientific_id}

    @property
    def confidence_state(self) -> str:
        return "UNKNOWN" if self.confidence is None else "KNOWN"


class CanonicalScientificMemory:
    """Explicit adapter over the already-canonical Memory V2 engine."""

    def __init__(self, engine=None):
        self.engine = engine

    @staticmethod
    def contract_matrix() -> list[dict[str, str]]:
        return [dict(item) for item in LEGACY_MEMORY_MATRIX]

    def status(self) -> dict[str, Any]:
        if self.engine is None:
            return {"ok": False, "status": "UNAVAILABLE", "authority": "CanonicalMemoryBoundary",
                    "schema_change_required": False, "import_executed": False}
        try:
            engine_status = self.engine.status()
            graph = self.engine.graph_stats()
            return {"ok": True, "status": "AVAILABLE", "authority": "CanonicalMemoryBoundary",
                    "engine": engine_status, "graph": graph,
                    "contract_types": [item.value for item in ScientificContractType],
                    "schema_change_required": False, "import_executed": False}
        except Exception as exc:
            return {"ok": False, "status": "DEGRADED", "authority": "CanonicalMemoryBoundary",
                    "error": type(exc).__name__, "schema_change_required": False,
                    "import_executed": False}

    def prepare(self, contract_type: ScientificContractType | str, content: str,
                **kwargs: Any) -> ScientificMemoryRecord:
        normalized = (contract_type.value if isinstance(contract_type, ScientificContractType)
                      else ScientificContractType(str(contract_type).upper()).value)
        return ScientificMemoryRecord(contract_type=normalized, content=str(content or ""),
                                      created_at=str(kwargs.pop("created_at", "") or utc_now()),
                                      **kwargs)

    def remember(self, record: ScientificMemoryRecord) -> dict[str, Any]:
        """Persist one explicit record through Memory V2; never imports legacy data."""
        if self.engine is None:
            return {"ok": False, "status": "UNAVAILABLE", "error": "MEMORY_ENGINE_UNAVAILABLE"}
        try:
            contract = ScientificContractType(record.contract_type)
            metadata = dict(record.provenance or {})
            metadata.update({
                "scientific_contract": contract.value,
                "scientific_id": record.scientific_id,
                "artifact": record.artifact,
                "observed_at": record.observed_at,
                "evidence_class": metadata.get("evidence_class", EvidenceClass.UNKNOWN.value),
                "supersedes_id": record.supersedes_id,
                "revises_id": record.revises_id,
                "conflicts_with_id": record.conflicts_with_id,
                "scientific_confidence": record.confidence,
                "confidence_state": record.confidence_state,
            })
            # Memory V2 currently stores a required numeric confidence column.
            # Preserve scientific UNKNOWN explicitly in metadata instead of
            # presenting the engine's legacy numeric default as source truth.
            confidence = (0.5 if record.confidence is None
                          else float(record.confidence))
            memory_type = {
                ScientificContractType.EVIDENCE: MemoryKind.EPISODIC,
                ScientificContractType.HYPOTHESIS: MemoryKind.SEMANTIC,
                ScientificContractType.EXPERIMENT: MemoryKind.EPISODIC,
                ScientificContractType.REVISION: MemoryKind.DECISION,
                ScientificContractType.CONFLICT: MemoryKind.DECISION,
                ScientificContractType.SUPERSESSION: MemoryKind.DECISION,
            }[contract]
            saved = self.engine.remember(
                record.content, memory_type=memory_type, title=contract.value,
                summary=record.content[:240], confidence=confidence,
                confidence_basis=ConfidenceBasis.DOCUMENTED,
                source_type=SourceType.LEGACY if record.source else SourceType.SYSTEM,
                source_ref=record.source or record.source_record_identity,
                metadata=metadata, project="jarvis-scientific",
                tags=["scientific", contract.value.lower()], canonical_key="",
            )
            entity = self.engine.upsert_entity(
                "scientific:" + record.scientific_id, EntityType.COMPONENT,
                source_type=SourceType.SYSTEM,
                source_ref=record.source or record.source_record_identity,
                metadata={"scientific_id": record.scientific_id,
                          "contract_type": contract.value,
                          "memory_id": int(saved.id),
                          "confidence_state": record.confidence_state,
                          "scientific_confidence": record.confidence},
            )
            self.engine.link_memory(int(saved.id), int(entity.id), link_role="scientific_contract")
            relations = []
            for relation_type, target_id in (
                    (RelationType.REVISES, record.revises_id),
                    (RelationType.CONTRADICTS, record.conflicts_with_id),
                    (RelationType.SUPERSEDES, record.supersedes_id)):
                if target_id:
                    relations.append(self._apply_relation(
                        entity, relation_type, str(target_id)))
            return {"ok": True, "status": "STORED_CANONICAL", "memory_id": saved.id,
                    "entity_id": entity.id, "scientific_id": record.scientific_id,
                    "canonical_confidence": record.confidence,
                    "confidence_state": record.confidence_state,
                    "relations": relations,
                    "schema_change_required": False, "import_executed": False}
        except Exception as exc:
            return {"ok": False, "status": "REJECTED", "error": type(exc).__name__,
                    "message": str(exc)[:240], "schema_change_required": False}

    def _find_scientific_entity(self, scientific_id: str):
        resolved = self.engine.find_entity(
            "scientific:" + str(scientific_id),
            entity_type=EntityType.COMPONENT.value)
        if resolved is None:
            return None
        # The public resolver returns a GraphNode. Relation/status updates need
        # the canonical entity metadata, including the linked memory id.
        return self.engine.store.get_entity(int(resolved.entity_id))

    def _apply_relation(self, source_entity, relation_type: RelationType,
                        target_scientific_id: str) -> dict[str, Any]:
        target_entity = self._find_scientific_entity(target_scientific_id)
        if target_entity is None:
            return {"ok": False, "status": "TARGET_NOT_FOUND",
                    "relation_type": relation_type.value,
                    "target_scientific_id": target_scientific_id}
        self._apply_status_semantics(source_entity, target_entity, relation_type)
        relation = self.engine.link_entities(
            int(source_entity.id), relation_type, int(target_entity.id),
            confidence_basis=ConfidenceBasis.DOCUMENTED,
            source_type=SourceType.SYSTEM,
            source_ref="scientific-memory-contract",
            metadata={"scientific_relationship": True,
                      "target_scientific_id": target_scientific_id},
        )
        return {"ok": True, "status": "LINKED_CANONICAL",
                "relation_id": relation.id, "relation_type": relation_type.value,
                "target_scientific_id": target_scientific_id}

    def _apply_status_semantics(self, source_entity, target_entity,
                                relation_type: RelationType) -> None:
        if source_entity is None or target_entity is None:
            return
        source_memory_id = int((source_entity.metadata or {}).get("memory_id") or 0)
        target_memory_id = int((target_entity.metadata or {}).get("memory_id") or 0)
        if relation_type == RelationType.CONTRADICTS:
            if source_memory_id:
                self.engine.update(source_memory_id, status=RecordStatus.DISPUTED)
            if target_memory_id:
                self.engine.update(target_memory_id, status=RecordStatus.DISPUTED)
        elif relation_type == RelationType.SUPERSEDES and target_memory_id:
            self.engine.update(target_memory_id, status=RecordStatus.SUPERSEDED)

    def link(self, source_entity_id: int, relation_type: RelationType | str,
             target_entity_id: int, source_ref: str = "") -> dict[str, Any]:
        if self.engine is None:
            return {"ok": False, "status": "UNAVAILABLE"}
        try:
            relation = (relation_type if isinstance(relation_type, RelationType)
                        else RelationType(str(relation_type).lower()))
            saved = self.engine.link_entities(
                int(source_entity_id), relation, int(target_entity_id),
                confidence_basis=ConfidenceBasis.DOCUMENTED,
                source_type=SourceType.SYSTEM, source_ref=source_ref,
                metadata={"scientific_relationship": True},
            )
            self._apply_status_semantics(
                self.engine.store.get_entity(int(source_entity_id)),
                self.engine.store.get_entity(int(target_entity_id)), relation)
            return {"ok": True, "status": "LINKED_CANONICAL", "relation_id": saved.id,
                    "relation_type": relation.value}
        except Exception as exc:
            return {"ok": False, "status": "REJECTED", "error": type(exc).__name__,
                    "message": str(exc)[:240]}


__all__ = ["CanonicalScientificMemory", "ScientificContractType",
           "ScientificMemoryRecord", "LEGACY_MEMORY_MATRIX"]
