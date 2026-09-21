"""M1.4: classificação determinística e conservadora antes do write."""
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from .types import MemoryKind, SourceType


class ConsolidationKind(str, Enum):
    NEW = "new"
    EXACT_DUPLICATE = "exact_duplicate"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    UPDATE = "update"
    COMPLEMENT = "complement"
    CONTRADICTION = "contradiction"
    UNCERTAIN = "uncertain"


@dataclass
class ConsolidationDecision:
    kind: ConsolidationKind
    candidate_id: Optional[int] = None
    reason: str = ""
    lexical_similarity: float = 0.0
    vector_similarity: Optional[float] = None
    incoming_vector: Optional[List[float]] = None
    supersede_candidate: bool = False


_TOKENS = re.compile(r"[A-Za-zÀ-ÿ0-9_.+-]+")
_ASSIGNMENT = re.compile(
    r"(?i)^\s*(.+?)(?:\s*=\s*|\s+(?:agora é|não é|nao é|é|era)\s+)(.+?)\s*$")
_NEGATION = re.compile(r"(?i)\b(não|nao|nunca|deixou de|não é|nao é)\b")
_TRUST = {
    SourceType.USER_EXPLICIT: 5,
    SourceType.SYSTEM: 4,
    SourceType.BENCHMARK: 4,
    SourceType.OFFICIAL_DOCS: 4,
    SourceType.TECHNICAL_BENCHMARK: 4,
    SourceType.TEST: 3,
    SourceType.FILE: 2,
    SourceType.IMPORT: 2,
    SourceType.WEB_ARTICLE: 2,
    SourceType.RESEARCH_PROVIDER: 2,
    SourceType.AGENT: 1,
    SourceType.CONVERSATION: 1,
    SourceType.COMMUNITY_FORUM: 1,
    SourceType.LEGACY: 1,
}


class MemoryConsolidator:
    MAX_CANDIDATES = 6
    SEMANTIC_THRESHOLD = 0.94
    LEXICAL_DUPLICATE_THRESHOLD = 0.82

    def __init__(self, engine):
        self.engine = engine

    def assess(self, incoming, canonical=None) -> ConsolidationDecision:
        vector = self._embed(incoming.content)
        if canonical is not None:
            if self._trust(incoming) >= self._trust(canonical):
                return ConsolidationDecision(
                    ConsolidationKind.UPDATE, canonical.id, "canonical_key",
                    incoming_vector=vector)
            return ConsolidationDecision(
                ConsolidationKind.UNCERTAIN, canonical.id,
                "canonical_update_from_lower_trust", incoming_vector=vector)

        report = self.engine.hybrid_search(
            incoming.content, limit=self.MAX_CANDIDATES,
            memory_type=incoming.memory_type.value,
            project=incoming.project, clearance=incoming.privacy.value)
        best = None
        for result in report.results:
            candidate = self.engine.store.load(result.memory_id)
            if candidate is None or candidate.project != incoming.project:
                continue
            lexical = self._lexical(incoming.content, candidate.content)
            cosine = self._cosine(vector,
                                  self.engine.store.load_embedding(candidate.id))
            score = max(lexical, cosine if cosine is not None else 0.0)
            if best is None or score > best[0]:
                best = (score, candidate, lexical, cosine)
        if best is None:
            return ConsolidationDecision(ConsolidationKind.NEW,
                                         incoming_vector=vector)

        _, candidate, lexical, cosine = best
        contradiction = self._contradicts(incoming.content, candidate.content)
        if contradiction:
            stronger = (self._trust(incoming) > self._trust(candidate)
                        and incoming.confidence >= candidate.confidence)
            return ConsolidationDecision(
                ConsolidationKind.CONTRADICTION if stronger
                else ConsolidationKind.UNCERTAIN,
                candidate.id, "conflicting_claim", lexical, cosine, vector,
                supersede_candidate=stronger)

        semantic = cosine is not None and cosine >= self.SEMANTIC_THRESHOLD
        token_mass = len(self._tokens(incoming.content) |
                         self._tokens(candidate.content))
        lexical_duplicate = (token_mass >= 3 and
                             lexical >= self.LEXICAL_DUPLICATE_THRESHOLD)
        if semantic or lexical_duplicate:
            if incoming.memory_type in (MemoryKind.DECISION,
                                        MemoryKind.PROCEDURAL,
                                        MemoryKind.LESSON):
                return ConsolidationDecision(
                    ConsolidationKind.UNCERTAIN, candidate.id,
                    "conservative_structured_memory", lexical, cosine, vector)
            return ConsolidationDecision(
                ConsolidationKind.SEMANTIC_DUPLICATE, candidate.id,
                "equivalent_content", lexical, cosine, vector)
        if lexical >= 0.30 or (cosine is not None and cosine >= 0.75):
            return ConsolidationDecision(
                ConsolidationKind.COMPLEMENT, candidate.id,
                "related_additional_information", lexical, cosine, vector)
        return ConsolidationDecision(ConsolidationKind.NEW,
                                     incoming_vector=vector)

    @staticmethod
    def _tokens(text):
        return {t.lower() for t in _TOKENS.findall(str(text or "")) if len(t) >= 2}

    def _lexical(self, left, right):
        a, b = self._tokens(left), self._tokens(right)
        return len(a & b) / len(a | b) if a and b else 0.0

    @staticmethod
    def _cosine(left, right):
        if not left or not right or len(left) != len(right):
            return None
        denom = math.sqrt(sum(x*x for x in left)) * math.sqrt(sum(x*x for x in right))
        return sum(a*b for a, b in zip(left, right)) / denom if denom else None

    def _embed(self, text):
        if not self.engine._embed:
            return None
        try:
            value = self.engine._embed(text)
            return list(value) if value else None
        except Exception:
            return None

    @staticmethod
    def _trust(record):
        return _TRUST.get(record.source_type, 0)

    def _contradicts(self, left, right):
        a, b = _ASSIGNMENT.match(left), _ASSIGNMENT.match(right)
        if a and b and self._lexical(a.group(1), b.group(1)) >= 0.75:
            return self._lexical(a.group(2), b.group(2)) < 0.35
        shared = self._lexical(left, right)
        return shared >= 0.55 and bool(_NEGATION.search(left)) != bool(
            _NEGATION.search(right))
