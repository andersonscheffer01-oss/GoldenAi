"""Golden Memory Engine V2 — Knowledge Graph contratos (M1.2).

- Grafo NÃO é segundo banco: usa v2_entities/v2_relations (+ tabelas
  auxiliares v2_memory_entities/v2_relation_evidence/versions).
- Vocabulário de relações controlado (catálogo central). Sem LLM
  criando relação livremente nesta fase.
- Simétricas são canonicalizadas (menor id primeiro); inversa é
  derivada na consulta, nunca persistida em duplicidade.
- Self-edge bloqueada para todos os tipos (sem allowlist).
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

_WS_RUN = re.compile(r"\s+")


class EdgeDirection(str, Enum):
    DIRECTED = "directed"
    SYMMETRIC = "symmetric"


class ResolutionStatus(str, Enum):
    FOUND = "found"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class TrustTier(str, Enum):
    TRUSTED_INTERNAL = "trusted_internal"
    USER_EDITABLE = "user_editable"
    EXTERNAL = "external"
    UNTRUSTED = "untrusted"


# relation_type -> (direction, inverse_label_or_None, allows_self)
RELATION_CATALOG: Dict[str, tuple] = {
    "uses": (EdgeDirection.DIRECTED, "used_by", False),
    "uses_model": (EdgeDirection.DIRECTED, "model_used_by", False),
    "uses_provider": (EdgeDirection.DIRECTED, "provider_used_by", False),
    "depends_on": (EdgeDirection.DIRECTED, "required_by", False),
    "provided_by": (EdgeDirection.DIRECTED, "provides", False),
    "part_of": (EdgeDirection.DIRECTED, "has_part", False),
    "has_component": (EdgeDirection.DIRECTED, "component_of", False),
    "related_to": (EdgeDirection.SYMMETRIC, None, False),
    "integrates_with": (EdgeDirection.SYMMETRIC, None, False),
    "replaced_by": (EdgeDirection.DIRECTED, "replaces", False),
    "created_by": (EdgeDirection.DIRECTED, "created", False),
    "tested_by": (EdgeDirection.DIRECTED, "tested", False),
    "affects": (EdgeDirection.DIRECTED, "affected_by", False),
    "trades_asset": (EdgeDirection.DIRECTED, "traded_by", False),
    "solved_by": (EdgeDirection.DIRECTED, "solves", False),
    "caused_by": (EdgeDirection.DIRECTED, "causes", False),
    "resulted_in": (EdgeDirection.DIRECTED, "resulted_from", False),
    "documented_by": (EdgeDirection.DIRECTED, "documents", False),
    "runs_on": (EdgeDirection.DIRECTED, "hosts", False),
    "supports": (EdgeDirection.DIRECTED, "supported_by", False),
    "contradicts": (EdgeDirection.DIRECTED, "contradicted_by", False),
    "derived_from": (EdgeDirection.DIRECTED, "source_of", False),
    "supersedes": (EdgeDirection.DIRECTED, "superseded_by", False),
    "revises": (EdgeDirection.DIRECTED, "revised_by", False),
}

# Ordem de restrição: PUBLIC < INTERNAL < SENSITIVE < SECRET.
PRIVACY_RANK = {"PUBLIC": 0, "INTERNAL": 1, "SENSITIVE": 2, "SECRET": 3}


def normalize_name(name: str) -> str:
    """Normalização conservadora: case/whitespace apenas. NÃO funde
    variantes com tokens distintos ("Qwen 3.8" ≠ "Qwen 3.8 27B")."""
    return _WS_RUN.sub(" ", str(name or "").strip().lower()).strip()


def normalize_alias(alias: str) -> str:
    return normalize_name(alias)


def relation_direction(relation_type: str) -> EdgeDirection:
    entry = RELATION_CATALOG.get(str(relation_type or ""))
    if entry is None:
        raise ValueError("relation_type desconhecido: %r" % relation_type)
    return entry[0]


def inverse_label(relation_type: str) -> Optional[str]:
    entry = RELATION_CATALOG.get(str(relation_type or ""))
    if entry is None:
        raise ValueError("relation_type desconhecido: %r" % relation_type)
    return entry[1]


def canonical_edge(relation_type: str, source_id: int,
                   target_id: int) -> tuple:
    """Simétricas: (menor, maior). Direcionais: como informado."""
    if relation_direction(relation_type) == EdgeDirection.SYMMETRIC:
        first, second = (int(source_id), int(target_id)) if int(source_id) <= int(
            target_id) else (int(target_id), int(source_id))
        return first, second
    return int(source_id), int(target_id)


def source_trust(source_type: str) -> TrustTier:
    """Proveniência → tier de confiança (nada externo vira confiável)."""
    trusted = {"system", "benchmark", "official_docs", "technical_benchmark"}
    editable = {"user_explicit"}
    external = {"file", "import", "web_article", "research_provider"}
    value = str(source_type or "")
    if value in trusted:
        return TrustTier.TRUSTED_INTERNAL
    if value in editable:
        return TrustTier.USER_EDITABLE
    if value in external:
        return TrustTier.EXTERNAL
    return TrustTier.UNTRUSTED


def privacy_allows(clearance: str, required: str) -> bool:
    return PRIVACY_RANK.get(str(clearance).upper(), 0) >= PRIVACY_RANK.get(
        str(required).upper(), 99)


# ── contratos de resultado (sem dicts soltos) ──────────────────────

@dataclass
class GraphNode:
    entity_id: int
    entity_type: str
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    privacy: str = "INTERNAL"
    status: str = "active"
    trust: str = TrustTier.UNTRUSTED.value
    confidence: float = 0.5


@dataclass
class GraphEdge:
    relation_id: int
    source_id: int
    target_id: int
    relation_type: str
    directed: bool = True
    confidence: float = 0.5
    status: str = "active"
    privacy: str = "INTERNAL"


@dataclass
class GraphNeighbor:
    edge: GraphEdge
    node: GraphNode
    direction: str = "outgoing"  # outgoing | incoming


@dataclass
class GraphPath:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def names(self) -> List[str]:
        return [n.canonical_name for n in self.nodes]


@dataclass
class GraphResult:
    root_id: int
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    depth: int = 0
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"root_id": self.root_id,
                "entities": [{"id": n.entity_id, "type": n.entity_type,
                              "name": n.canonical_name} for n in self.nodes],
                "relations": [{"id": e.relation_id, "type": e.relation_type,
                               "source": e.source_id, "target": e.target_id}
                              for e in self.edges],
                "root": self.root_id, "depth": self.depth,
                "truncated": self.truncated}


@dataclass
class EntityResolution:
    status: ResolutionStatus
    entity: Optional[GraphNode] = None
    candidates: List[GraphNode] = field(default_factory=list)
