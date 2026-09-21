from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.safety import EvidenceLevel


class EvidenceType(str, Enum):
    SOURCE_CLAIM = "SOURCE_CLAIM"
    OBSERVATION = "OBSERVATION"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    TEST_RESULT = "TEST_RESULT"
    VERIFIED_RESULT = "VERIFIED_RESULT"


class SourceType(str, Enum):
    CHAT = "CHAT"
    FILE = "FILE"
    MARKET = "MARKET"
    QUANT_EXPERIMENT = "QUANT_EXPERIMENT"
    MEDIA = "MEDIA"
    DOCUMENT = "DOCUMENT"
    USER_NOTE = "USER_NOTE"
    SYSTEM = "SYSTEM"


@dataclass
class KnowledgeItem:
    knowledge_id: str
    topic: str
    statement: str
    evidence_type: EvidenceType
    source_type: str
    source_id: str
    source_location: str
    confidence: float
    validation_status: str
    supersedes_id: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_level: EvidenceLevel | str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    archived: bool = False

    def normalized_evidence_level(self) -> str:
        if isinstance(self.evidence_level, EvidenceLevel):
            return self.evidence_level.value
        if self.evidence_level:
            return str(self.evidence_level)
        return str(self.validation_status or "")
