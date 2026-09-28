"""Deterministic, side-effect-free semantic turn decisions.

This module deliberately does not know about VoiceService, Core, security,
audio devices, STT providers, or TTS.  It only combines transcript evidence
with the acoustic endpoint supplied by the existing voice pipeline.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class SemanticTurnState(str, Enum):
    """Bounded semantic outcomes exposed to future voice orchestration."""

    CONTINUE_LISTENING = "CONTINUE_LISTENING"
    LIKELY_COMPLETE = "LIKELY_COMPLETE"
    COMPLETE = "COMPLETE"
    UNCERTAIN = "UNCERTAIN"


class SemanticTurnReason(str, Enum):
    """Stable, non-sensitive reason codes for decisions and metrics."""

    ACOUSTIC_ENDPOINT_REQUIRED = "ACOUSTIC_ENDPOINT_REQUIRED"
    ACOUSTIC_FALLBACK = "ACOUSTIC_FALLBACK"
    CONTINUATION_TIMEOUT = "CONTINUATION_TIMEOUT"
    EMPTY_TRANSCRIPT = "EMPTY_TRANSCRIPT"
    INCOMPLETE_TRAILING_CONNECTIVE = "INCOMPLETE_TRAILING_CONNECTIVE"
    ELLIPSIS = "ELLIPSIS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID_INPUT = "INVALID_INPUT"
    SPEECH_ACTIVE = "SPEECH_ACTIVE"
    TERMINAL_PUNCTUATION = "TERMINAL_PUNCTUATION"
    COMPLETE_FINAL_PHRASE = "COMPLETE_FINAL_PHRASE"
    PARTIAL_TRANSCRIPT = "PARTIAL_TRANSCRIPT"


@dataclass(frozen=True)
class SemanticTurnConfig:
    """Small bounded configuration surface for the deterministic analyzer."""

    decision_timeout_ms: float = 250.0
    max_continuation_window_ms: float = 1_500.0
    min_complete_words: int = 3
    max_transcript_chars: int = 8_000

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.decision_timeout_ms)) or self.decision_timeout_ms <= 0:
            raise ValueError("decision_timeout_ms must be positive and finite")
        if (
            not math.isfinite(float(self.max_continuation_window_ms))
            or self.max_continuation_window_ms <= 0
        ):
            raise ValueError("max_continuation_window_ms must be positive and finite")
        if int(self.min_complete_words) < 1:
            raise ValueError("min_complete_words must be positive")
        if int(self.max_transcript_chars) < 1:
            raise ValueError("max_transcript_chars must be positive")


@dataclass(frozen=True)
class SemanticTurnInput:
    """Identity and evidence presented to the deterministic analyzer."""

    session_id: str
    turn_id: int
    utterance_id: str
    epoch: int
    transcript: str = ""
    is_final: bool = False
    acoustic_endpoint: bool = False
    speech_active: bool = False
    decision_elapsed_ms: float | None = None
    continuation_elapsed_ms: float | None = None


@dataclass(frozen=True)
class SemanticTurnDecision:
    """Pure data result; it cannot authorize or execute any action."""

    state: SemanticTurnState
    reason_code: SemanticTurnReason
    confidence: float
    session_id: str
    turn_id: int
    utterance_id: str
    epoch: int

    @property
    def should_finalize(self) -> bool:
        """Expose completion without turning the decision into an action."""
        return self.state is SemanticTurnState.COMPLETE


class SemanticTurnDetector(Protocol):
    """Provider-neutral semantic decision contract."""

    def decide(self, evidence: SemanticTurnInput) -> SemanticTurnDecision:
        ...


_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[\wÀ-ÿ]+(?:['’][\wÀ-ÿ]+)?", re.UNICODE)
_TERMINAL_RE = re.compile(r"[.!?؟]$")
_ELLIPSIS_RE = re.compile(r"(?:\.\.\.|…)$")

# These are intentionally small and conservative.  They describe a trailing
# dependency, not a complete Portuguese grammar.
_PT_BR_CONTINUATION_WORDS = frozenset(
    {
        "a",
        "as",
        "até",
        "como",
        "com",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "ela",
        "ele",
        "em",
        "eu",
        "mas",
        "na",
        "nas",
        "no",
        "nos",
        "onde",
        "ou",
        "para",
        "por",
        "porque",
        "qual",
        "que",
        "quando",
        "se",
        "sobre",
        "um",
        "uma",
        "você",
    }
)


class DeterministicSemanticTurnDetector:
    """Small PT-BR-aware heuristic detector with bounded continuation.

    The detector is pure for a given input/configuration.  It never sleeps,
    performs I/O, calls a model, or invokes any Jarvis action boundary.
    """

    def __init__(self, config: SemanticTurnConfig | None = None) -> None:
        self.config = config or SemanticTurnConfig()

    def decide(self, evidence: SemanticTurnInput) -> SemanticTurnDecision:
        identity = self._identity(evidence)
        transcript = self._normalize_text(evidence.transcript)

        if not self._valid_timing(evidence):
            return self._decision(
                evidence,
                SemanticTurnState.UNCERTAIN,
                SemanticTurnReason.INVALID_INPUT,
                0.0,
            )

        if len(transcript) > self.config.max_transcript_chars:
            return self._decision(
                evidence,
                SemanticTurnState.UNCERTAIN,
                SemanticTurnReason.INVALID_INPUT,
                0.0,
            )

        if evidence.speech_active:
            return self._decision(
                evidence,
                SemanticTurnState.CONTINUE_LISTENING,
                SemanticTurnReason.SPEECH_ACTIVE,
                1.0,
            )

        if not transcript:
            return self._decision(
                evidence,
                SemanticTurnState.CONTINUE_LISTENING,
                SemanticTurnReason.EMPTY_TRANSCRIPT,
                0.0,
            )

        if self._timed_out(evidence):
            if evidence.acoustic_endpoint:
                return self._decision(
                    evidence,
                    SemanticTurnState.COMPLETE,
                    SemanticTurnReason.CONTINUATION_TIMEOUT,
                    0.55,
                )
            return self._decision(
                evidence,
                SemanticTurnState.UNCERTAIN,
                SemanticTurnReason.CONTINUATION_TIMEOUT,
                0.2,
            )

        words = self._words(transcript)
        has_ellipsis = bool(_ELLIPSIS_RE.search(transcript))
        trailing_word = words[-1].casefold() if words else ""
        incomplete = has_ellipsis or trailing_word in _PT_BR_CONTINUATION_WORDS
        terminal = bool(_TERMINAL_RE.search(transcript)) and not has_ellipsis

        if incomplete:
            reason = SemanticTurnReason.ELLIPSIS if has_ellipsis else SemanticTurnReason.INCOMPLETE_TRAILING_CONNECTIVE
            return self._decision(
                evidence,
                SemanticTurnState.CONTINUE_LISTENING,
                reason,
                0.9 if has_ellipsis else 0.75,
            )

        if not evidence.acoustic_endpoint:
            if terminal and evidence.is_final:
                return self._decision(
                    evidence,
                    SemanticTurnState.LIKELY_COMPLETE,
                    SemanticTurnReason.TERMINAL_PUNCTUATION,
                    0.8,
                )
            return self._decision(
                evidence,
                SemanticTurnState.LIKELY_COMPLETE if terminal else SemanticTurnState.CONTINUE_LISTENING,
                SemanticTurnReason.ACOUSTIC_ENDPOINT_REQUIRED,
                0.65 if terminal else 0.35,
            )

        if not evidence.is_final:
            return self._decision(
                evidence,
                SemanticTurnState.LIKELY_COMPLETE if terminal else SemanticTurnState.UNCERTAIN,
                SemanticTurnReason.PARTIAL_TRANSCRIPT,
                0.6 if terminal else 0.25,
            )

        if terminal:
            return self._decision(
                evidence,
                SemanticTurnState.COMPLETE,
                SemanticTurnReason.TERMINAL_PUNCTUATION,
                0.9,
            )

        if len(words) >= self.config.min_complete_words:
            return self._decision(
                evidence,
                SemanticTurnState.COMPLETE,
                SemanticTurnReason.COMPLETE_FINAL_PHRASE,
                0.7,
            )

        return self._decision(
            evidence,
            SemanticTurnState.UNCERTAIN,
            SemanticTurnReason.INSUFFICIENT_EVIDENCE,
            0.25,
        )

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        if text is None:
            return ""
        normalized = unicodedata.normalize("NFC", str(text))
        return _WHITESPACE_RE.sub(" ", normalized).strip()

    @staticmethod
    def _words(text: str) -> list[str]:
        return _WORD_RE.findall(text)

    @staticmethod
    def _identity(evidence: SemanticTurnInput) -> tuple[str, int, str, int]:
        return (
            str(evidence.session_id or ""),
            int(evidence.turn_id),
            str(evidence.utterance_id or ""),
            int(evidence.epoch),
        )

    @staticmethod
    def _valid_timing(evidence: SemanticTurnInput) -> bool:
        for value in (evidence.decision_elapsed_ms, evidence.continuation_elapsed_ms):
            if value is not None and (
                not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0
            ):
                return False
        return True

    def _timed_out(self, evidence: SemanticTurnInput) -> bool:
        decision_elapsed = float(evidence.decision_elapsed_ms or 0.0)
        continuation_elapsed = float(evidence.continuation_elapsed_ms or 0.0)
        return (
            decision_elapsed >= self.config.decision_timeout_ms
            or continuation_elapsed >= self.config.max_continuation_window_ms
        )

    @classmethod
    def _decision(
        cls,
        evidence: SemanticTurnInput,
        state: SemanticTurnState,
        reason_code: SemanticTurnReason,
        confidence: float,
    ) -> SemanticTurnDecision:
        return SemanticTurnDecision(
            state=state,
            reason_code=reason_code,
            confidence=max(0.0, min(1.0, float(confidence))),
            session_id=str(evidence.session_id or ""),
            turn_id=int(evidence.turn_id),
            utterance_id=str(evidence.utterance_id or ""),
            epoch=int(evidence.epoch),
        )


__all__ = [
    "DeterministicSemanticTurnDetector",
    "SemanticTurnConfig",
    "SemanticTurnDecision",
    "SemanticTurnDetector",
    "SemanticTurnInput",
    "SemanticTurnReason",
    "SemanticTurnState",
]
