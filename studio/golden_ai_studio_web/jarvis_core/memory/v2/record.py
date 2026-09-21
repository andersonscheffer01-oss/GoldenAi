"""Golden Memory Engine V2 — contratos de registro (M1.0).

Nenhum segredo em metadata/source_ref por acidente: validação rejeita
padrões de credencial em content, summary e metadata (chaves e valores).
"""
import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ...orchestrator.models import DataClassification
from .types import (ConfidenceBasis, EntityType, MatchSource, MemoryKind,
                    RecordStatus, RelationType, SourceType)

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|senha|token|secret|api[_-]?key|authorization|cookie|credential|private[_-]?key)\b\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*"),
)
SECRET_NAME = re.compile(
    r"(?i)^(password|passwd|senha|token|secret|api[_-]?key|authorization|cookie|credential|private[_-]?key)$")


class MemorySecurityError(ValueError):
    """Conteúdo recusado pela política SECRET (nunca persistido)."""


class MemoryValidationError(ValueError):
    """Contrato violado (tipo, privacy, confidence, status, conteúdo)."""


def _scan_secret(value: Any, where: str) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and SECRET_NAME.match(k.strip()):
                raise MemorySecurityError("chave de segredo em %s" % where)
            _scan_secret(k, "%s<key>" % where)
            _scan_secret(v, where)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _scan_secret(item, where)
        return
    if not isinstance(value, str):
        return
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            raise MemorySecurityError("padrão de segredo em %s" % where)


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class MemoryRecordV2:
    id: Optional[int] = None
    memory_type: MemoryKind = MemoryKind.SEMANTIC
    title: str = ""
    content: str = ""
    summary: str = ""
    status: RecordStatus = RecordStatus.ACTIVE
    created_at: float = 0.0
    updated_at: float = 0.0
    last_accessed_at: float = 0.0
    version: int = 1
    confidence: float = 0.5
    confidence_basis: ConfidenceBasis = ConfidenceBasis.INFERRED
    privacy: DataClassification = DataClassification.INTERNAL
    source_type: SourceType = SourceType.SYSTEM
    source_ref: str = ""
    source_timestamp: float = 0.0
    project: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding_status: str = "pending"
    embedding_model: str = ""
    content_hash: str = ""
    canonical_key: str = ""

    def validate(self) -> None:
        if not isinstance(self.memory_type, MemoryKind):
            raise MemoryValidationError("memory_type inválido")
        if not isinstance(self.status, RecordStatus):
            raise MemoryValidationError("status inválido")
        if not isinstance(self.privacy, DataClassification):
            raise MemoryValidationError("privacy inválida (usar DataClassification)")
        if not isinstance(self.confidence_basis, ConfidenceBasis):
            raise MemoryValidationError("confidence_basis inválida")
        if not isinstance(self.source_type, SourceType):
            raise MemoryValidationError("source_type inválida")
        if not isinstance(self.confidence, (int, float)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise MemoryValidationError("confidence fora de [0, 1]")
        if not str(self.content or "").strip():
            raise MemoryValidationError("content vazio")
        if len(self.content) > 8000:
            raise MemoryValidationError("content excessivo")
        _scan_secret(self.content, "content")
        _scan_secret(self.summary, "summary")
        _scan_secret(self.metadata, "metadata")
        _scan_secret(self.source_ref, "source_ref")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntityV2:
    id: Optional[int] = None
    entity_type: EntityType = EntityType.OTHER
    canonical_name: str = ""
    aliases: List[str] = field(default_factory=list)
    privacy: DataClassification = DataClassification.INTERNAL
    confidence: float = 0.5  # M1.2
    confidence_basis: ConfidenceBasis = ConfidenceBasis.INFERRED  # M1.2
    source_type: SourceType = SourceType.SYSTEM  # M1.2 (proveniência)
    source_ref: str = ""  # M1.2
    version: int = 1  # M1.2
    metadata: Dict[str, Any] = field(default_factory=dict)  # M1.2
    created_at: float = 0.0
    updated_at: float = 0.0
    status: RecordStatus = RecordStatus.ACTIVE

    @property
    def normalized_name(self) -> str:  # M1.2 (derivado, não persistido duplo)
        from .graph import normalize_name
        return normalize_name(self.canonical_name)

    def validate(self) -> None:
        if not isinstance(self.entity_type, EntityType):
            raise MemoryValidationError("entity_type inválido")
        if not isinstance(self.privacy, DataClassification):
            raise MemoryValidationError("privacy inválida (usar DataClassification)")
        if not isinstance(self.confidence_basis, ConfidenceBasis):
            raise MemoryValidationError("confidence_basis inválida")
        if not isinstance(self.source_type, SourceType):
            raise MemoryValidationError("source_type inválida")
        if not str(self.canonical_name or "").strip():
            raise MemoryValidationError("canonical_name vazio")
        if not isinstance(self.confidence, (int, float)) or not 0.0 <= float(
                self.confidence) <= 1.0:
            raise MemoryValidationError("confidence fora de [0, 1]")
        _scan_secret(self.canonical_name, "canonical_name")
        for alias in self.aliases:
            _scan_secret(alias, "alias")
        _scan_secret(self.metadata, "entity_metadata")
        _scan_secret(self.source_ref, "entity_source_ref")


@dataclass
class RelationV2:
    id: Optional[int] = None
    source_entity_id: int = 0
    relation_type: RelationType = RelationType.RELATED_TO
    target_entity_id: int = 0
    confidence: float = 0.5
    confidence_basis: ConfidenceBasis = ConfidenceBasis.INFERRED  # M1.2
    privacy: DataClassification = DataClassification.INTERNAL
    source_type: SourceType = SourceType.SYSTEM  # M1.2 (proveniência)
    source_ref: str = ""
    version: int = 1  # M1.2
    metadata: Dict[str, Any] = field(default_factory=dict)  # M1.2
    created_at: float = 0.0
    updated_at: float = 0.0  # M1.2
    status: RecordStatus = RecordStatus.ACTIVE

    def validate(self) -> None:
        from .graph import RELATION_CATALOG
        if not isinstance(self.relation_type, RelationType):
            raise MemoryValidationError("relation_type inválida")
        if self.relation_type.value not in RELATION_CATALOG:
            raise MemoryValidationError("relation_type fora do catálogo")
        if not isinstance(self.privacy, DataClassification):
            raise MemoryValidationError("privacy inválida (usar DataClassification)")
        if not isinstance(self.confidence_basis, ConfidenceBasis):
            raise MemoryValidationError("confidence_basis inválida")
        if not isinstance(self.source_type, SourceType):
            raise MemoryValidationError("source_type inválida")
        if self.source_entity_id == self.target_entity_id:
            raise MemoryValidationError("relação reflexiva")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise MemoryValidationError("confidence fora de [0, 1]")
        _scan_secret(self.source_ref, "source_ref")
        _scan_secret(self.metadata, "relation_metadata")


@dataclass
class MemoryCandidate:
    """Futura decisão 'vale lembrar?' (M1.0: contrato, sem auto-memory)."""
    content: str = ""
    suggested_type: MemoryKind = MemoryKind.SEMANTIC
    importance: int = 50
    confidence: float = 0.5
    privacy: DataClassification = DataClassification.INTERNAL
    source_type: SourceType = SourceType.SYSTEM
    reason: str = ""


@dataclass
class MemorySearchResult:
    memory_id: int = 0
    score: float = 0.0  # legado: espelha final_score
    source: MatchSource = MatchSource.LEXICAL
    match_type: str = ""
    snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # M1.3 hybrid (defaults p/ compat com M1.0):
    title: str = ""
    memory_type: str = ""
    project: str = ""
    privacy: str = "INTERNAL"
    trust: str = "untrusted"
    status: str = "active"
    final_score: float = 0.0
    rank: int = 0
    match_sources: List[str] = field(default_factory=list)
    matched_fields: List[str] = field(default_factory=list)
    entity_matches: List[str] = field(default_factory=list)
    graph_distance: int = -1
    version: int = 1
