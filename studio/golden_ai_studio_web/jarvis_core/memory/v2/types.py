"""Golden Memory Engine V2 — tipos canônicos (M1.0 fundação).

Privacy REUTILIZA DataClassification oficial do Orchestrator
(PUBLIC/INTERNAL/SENSITIVE/SECRET). Nenhum segundo sistema de privacy.
"""
from enum import Enum


class MemoryKind(str, Enum):
    WORKING = "working"
    SESSION = "session"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    ENTITY = "entity"
    DECISION = "decision"
    PROCEDURAL = "procedural"
    LESSON = "lesson"


class ConfidenceBasis(str, Enum):
    SOURCE_CONFIRMED = "source_confirmed"
    USER_CONFIRMED = "user_confirmed"
    TEST_CONFIRMED = "test_confirmed"  # M1.2: evidência de teste/benchmark
    DOCUMENTED = "documented"  # M1.2: fonte documental explícita
    INFERRED = "inferred"
    TENTATIVE = "tentative"


class RecordStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"  # M1.2: relação/entidade contestada (não resolve semântica)
    ARCHIVED = "archived"
    MERGED = "merged"  # M1.2: entidade absorvida por merge (ID histórico preservado)
    DELETED_LOGICAL = "deleted_logical"


class SourceType(str, Enum):
    CONVERSATION = "conversation"
    FILE = "file"
    TEST = "test"
    BENCHMARK = "benchmark"
    OFFICIAL_DOCS = "official_docs"
    TECHNICAL_BENCHMARK = "technical_benchmark"
    COMMUNITY_FORUM = "community_forum"
    WEB_ARTICLE = "web_article"
    RESEARCH_PROVIDER = "research_provider"
    USER_EXPLICIT = "user_explicit"
    SYSTEM = "system"
    AGENT = "agent"
    IMPORT = "import"
    LEGACY = "legacy"


class EntityType(str, Enum):
    PERSON = "person"
    PROJECT = "project"
    MODEL = "model"
    PROVIDER = "provider"
    SOFTWARE = "software"
    STRATEGY = "strategy"
    ASSET = "asset"
    DOCUMENT = "document"
    SYSTEM = "system"
    COMPANY = "company"
    CONCEPT = "concept"  # M1.2: ideia/termo (ex.: "Ouro" como conceito ≠ XAUUSD)
    COMPONENT = "component"  # M1.2: parte de sistema (ex.: VOICE_FAST)
    DEVICE = "device"  # M1.2: hardware (ex.: Microfone USB)
    OTHER = "other"
    # Decisão M1.2: SEM DECISION/PROCEDURE/TEST/FEATURE como entity types —
    # MemoryRecords DECISION/PROCEDURAL/LESSON já representam esse
    # conhecimento; duplicar criaria segunda fonte de verdade.


class RelationType(str, Enum):
    USES = "uses"
    USES_MODEL = "uses_model"  # M1.2
    USES_PROVIDER = "uses_provider"  # M1.2
    DEPENDS_ON = "depends_on"
    PROVIDED_BY = "provided_by"
    PART_OF = "part_of"
    HAS_COMPONENT = "has_component"  # M1.2 (inversa de PART_OF)
    RELATED_TO = "related_to"
    INTEGRATES_WITH = "integrates_with"  # M1.2 (simétrica)
    REPLACED_BY = "replaced_by"
    CREATED_BY = "created_by"
    TESTED_BY = "tested_by"
    AFFECTS = "affects"
    TRADES_ASSET = "trades_asset"  # M1.2
    SOLVED_BY = "solved_by"  # M1.2
    CAUSED_BY = "caused_by"  # M1.2
    RESULTED_IN = "resulted_in"  # M1.2
    DOCUMENTED_BY = "documented_by"  # M1.2
    RUNS_ON = "runs_on"  # M1.2


class MatchSource(str, Enum):
    """Fontes de retrieval (contrato híbrido; ranking complexo é M-futuro)."""
    LEXICAL = "lexical"
    VECTOR = "vector"
    METADATA = "metadata"
    GRAPH = "graph"


class EmbeddingState(str, Enum):
    OK = "ok"
    PENDING = "pending"
    DEGRADED = "degraded"
