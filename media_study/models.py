from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


class MediaSourceType(str, Enum):
    TEXT = "TEXT"
    TRANSCRIPT = "TRANSCRIPT"
    SRT = "SRT"
    VTT = "VTT"
    DOCUMENT = "DOCUMENT"
    AUDIO_REFERENCE = "AUDIO_REFERENCE"
    VIDEO_REFERENCE = "VIDEO_REFERENCE"
    WEB = "WEB"
    YOUTUBE = "YOUTUBE"


class ClaimKind(str, Enum):
    CONCEPT = "CONCEPT"
    DEFINITION = "DEFINITION"
    RULE = "RULE"
    QUANTITATIVE_CLAIM = "QUANTITATIVE_CLAIM"
    HYPOTHESIS = "HYPOTHESIS"
    OPINION = "OPINION"
    PROCEDURE = "PROCEDURE"
    REFERENCE = "REFERENCE"


@dataclass
class MediaStudy:
    study_id: str
    source_path: str
    source_type: str
    trust_classification: str = "UNTRUSTED_DATA"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaSource:
    source_id: str
    source_type: str
    title: str
    origin: str
    author: str = ""
    source_date: str = ""
    language: str = ""
    duration_seconds: float | None = None
    source_hash: str = ""
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaDocument:
    document_id: str
    source_id: str
    content_hash: str
    text_length: int
    line_count: int
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaSegment:
    segment_id: str
    source_id: str
    order_index: int
    text: str
    start_time: str = ""
    end_time: str = ""
    line_start: int | None = None
    line_end: int | None = None
    segment_hash: str = ""
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str = ""
    confidence: float | None = None


@dataclass
class SourceClaim:
    claim_id: str
    source_id: str
    segment_id: str
    statement: str
    claim_kind: str
    evidence_level: str = "SOURCE_CLAIM"
    timestamp_start: str = ""
    timestamp_end: str = ""
    line_start: int | None = None
    line_end: int | None = None
    confidence: float = 0.5
    numbers: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)


@dataclass
class StudyNote:
    note_id: str
    source_id: str
    text: str
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestableHypothesis:
    hypothesis_id: str
    claim_id: str
    source_id: str
    statement: str
    condition: str = ""
    indicator: str = ""
    parameter: str = ""
    pattern: str = ""
    direction: str = ""
    entry: str = ""
    exit: str = ""
    timeframe: str = ""
    missing_fields: list[str] = field(default_factory=list)
    status: str = "NOT_TESTED"
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StudyResult:
    study_id: str
    source_id: str
    summary: str
    concepts: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    claims: list[SourceClaim] = field(default_factory=list)
    quantitative_claims: list[SourceClaim] = field(default_factory=list)
    hypotheses: list[TestableHypothesis] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    unclear_points: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)


@dataclass
class VisualEvent:
    timestamp_seconds: float
    label: str
    description: str
    confidence: float | None = None


@dataclass
class MultimodalEvent:
    timestamp_seconds: float
    transcript: TranscriptSegment | None = None
    visual_events: list[VisualEvent] = field(default_factory=list)
    notes: str = ""


@dataclass
class MediaKnowledgeItem:
    topic: str
    statement: str
    evidence_type: str = "SOURCE_CLAIM"
    source_location: str = ""
    confidence: float = 0.0


@dataclass
class StudyReport:
    study_id: str
    summary: str
    knowledge: list[MediaKnowledgeItem] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
