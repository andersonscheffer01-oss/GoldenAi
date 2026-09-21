from __future__ import annotations

from enum import Enum


class EvidenceLevel(str, Enum):
    SOURCE_CLAIM = "SOURCE_CLAIM"
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"
    TESTED = "TESTED"
    VALIDATED = "VALIDATED"
