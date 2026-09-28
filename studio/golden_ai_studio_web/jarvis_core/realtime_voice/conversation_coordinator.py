"""Identity-aware coordination between STT events and semantic turns.

The coordinator is intentionally below VoiceService and above the existing
VAD/STT contracts.  It returns data for the existing callback path; it never
calls Core, tools, security, audio, or persistence code.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from jarvis_core.voice_foundation import TranscriptEvent

from .semantic_turn import (
    DeterministicSemanticTurnDetector,
    SemanticTurnDecision,
    SemanticTurnDetector,
    SemanticTurnInput,
    SemanticTurnReason,
    SemanticTurnState,
)


class ConversationResultStatus(str, Enum):
    """Bounded coordinator outcomes."""

    PARTIAL_OBSERVED = "PARTIAL_OBSERVED"
    WAITING_CONTINUATION = "WAITING_CONTINUATION"
    COMPLETED = "COMPLETED"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_UNCERTAIN = "REJECTED_UNCERTAIN"
    REJECTED_INVALID = "REJECTED_INVALID"
    CANCELLED = "CANCELLED"
    NOOP = "NOOP"


@dataclass(frozen=True)
class ConversationCompletion:
    """Data returned to the existing VoiceService callback boundary."""

    status: ConversationResultStatus
    eligible_for_dispatch: bool
    event: Optional[TranscriptEvent]
    decision: Optional[SemanticTurnDecision]
    reason_code: str
    session_id: str
    turn_id: int
    utterance_id: str
    epoch: int


class ConversationStreamCoordinator:
    """Coordinate bounded transcript continuation with explicit identity.

    One instance belongs to one realtime pipeline.  Its lock protects only
    bounded in-memory utterance metadata; it never wraps audio callbacks or
    provider work.
    """

    def __init__(
        self,
        semantic_detector: SemanticTurnDetector | None = None,
        *,
        max_segments: int = 4,
        max_transcript_chars: int = 8_000,
    ) -> None:
        if max_segments < 1:
            raise ValueError("max_segments must be positive")
        if max_transcript_chars < 1:
            raise ValueError("max_transcript_chars must be positive")
        self._detector = semantic_detector or DeterministicSemanticTurnDetector()
        self._max_segments = int(max_segments)
        self._max_transcript_chars = int(max_transcript_chars)
        self._lock = threading.RLock()
        self._active = False
        self._cancelled = False
        self._session_id = ""
        self._turn_id = 0
        self._epoch = 0
        self._logical_utterance_id = ""
        self._segments: list[str] = []
        self._seen_partials: set[tuple[str, int, str]] = set()
        self._seen_finals: set[tuple[str, int]] = set()
        self._completed_identity: tuple[str, int, str, int] | None = None
        self._last_event: TranscriptEvent | None = None
        self._continuation_started_at: float | None = None

    @property
    def session_id(self) -> str:
        with self._lock:
            return self._session_id

    @property
    def turn_id(self) -> int:
        with self._lock:
            return self._turn_id

    @property
    def epoch(self) -> int:
        with self._lock:
            return self._epoch

    def begin_session(self, *, session_id: str, turn_id: int, epoch: int) -> None:
        """Start a fresh session and discard all prior utterance metadata."""
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("session_id is required")
        with self._lock:
            self._reset_utterance_locked()
            self._active = True
            self._cancelled = False
            self._session_id = normalized_session
            self._turn_id = int(turn_id)
            self._epoch = int(epoch)

    def replace_turn(self, *, turn_id: int, epoch: int) -> None:
        """Switch the authoritative turn without creating a second owner."""
        with self._lock:
            if not self._active:
                return
            self._reset_utterance_locked()
            self._cancelled = False
            self._turn_id = int(turn_id)
            self._epoch = int(epoch)

    def cancel(self, reason: str = "cancelled") -> None:
        """Invalidate pending events and release bounded utterance memory."""
        del reason
        with self._lock:
            self._cancelled = True
            self._active = False
            self._reset_utterance_locked()

    def diagnostics(self) -> dict[str, object]:
        """Expose bounded non-transcript state for diagnostics/tests."""
        with self._lock:
            return {
                "active": self._active,
                "cancelled": self._cancelled,
                "session_id": self._session_id,
                "turn_id": self._turn_id,
                "epoch": self._epoch,
                "logical_utterance_id": self._logical_utterance_id,
                "segment_count": len(self._segments),
                "seen_partial_count": len(self._seen_partials),
                "seen_final_count": len(self._seen_finals),
                "completed": self._completed_identity is not None,
            }

    def observe_transcript(
        self,
        event: TranscriptEvent,
        *,
        turn_id: int,
        acoustic_endpoint: bool,
        speech_active: bool = False,
        continuation_elapsed_ms: float | None = None,
    ) -> ConversationCompletion:
        """Observe one transcript event and return a data-only outcome."""
        with self._lock:
            if not isinstance(event, TranscriptEvent):
                return self._invalid("INVALID_TRANSCRIPT")
            stale_reason = self._stale_reason(event, int(turn_id))
            if stale_reason:
                return self._rejected_stale(event, stale_reason)
            if not event.utterance_id or not event.text.strip():
                return self._invalid("INVALID_IDENTITY_OR_TRANSCRIPT", event)

            effective_epoch = event.epoch or self._epoch
            if not event.is_final:
                partial_key = (event.utterance_id, int(event.sequence), event.text)
                if partial_key in self._seen_partials:
                    return self._result(
                        ConversationResultStatus.PARTIAL_OBSERVED,
                        False,
                        event,
                        None,
                        "DUPLICATE_PARTIAL_OBSERVED",
                    )
                self._seen_partials.add(partial_key)
                self._bound_seen_sets_locked()
                decision, _analysis_failed = self._safe_decide(
                    turn_id=int(turn_id),
                    utterance_id=event.utterance_id,
                    transcript=event.text,
                    is_final=False,
                    acoustic_endpoint=False,
                    speech_active=speech_active,
                    continuation_elapsed_ms=continuation_elapsed_ms,
                )
                return self._result(
                    ConversationResultStatus.PARTIAL_OBSERVED,
                    False,
                    event,
                    decision,
                    SemanticTurnReason.PARTIAL_TRANSCRIPT.value,
                )

            final_key = (event.utterance_id, effective_epoch)
            if final_key in self._seen_finals:
                return self._result(
                    ConversationResultStatus.REJECTED_DUPLICATE,
                    False,
                    event,
                    None,
                    "DUPLICATE_FINAL",
                )
            self._seen_finals.add(final_key)
            self._bound_seen_sets_locked()

            if not self._logical_utterance_id:
                self._logical_utterance_id = event.utterance_id
            if len(self._segments) >= self._max_segments:
                self._reset_utterance_locked()
                return self._invalid("MAX_SEGMENTS_EXCEEDED", event)
            self._segments.append(event.text.strip())
            self._last_event = event
            combined = self._combined_text_locked()
            if len(combined) > self._max_transcript_chars:
                self._reset_utterance_locked()
                return self._invalid("MAX_TRANSCRIPT_CHARS_EXCEEDED", event)

            if self._continuation_started_at is None and len(self._segments) > 1:
                self._continuation_started_at = time.monotonic()
            elapsed = continuation_elapsed_ms
            if elapsed is None and self._continuation_started_at is not None:
                elapsed = max(0.0, (time.monotonic() - self._continuation_started_at) * 1000.0)

            decision, analysis_failed = self._safe_decide(
                turn_id=int(turn_id),
                utterance_id=self._logical_utterance_id,
                transcript=combined,
                is_final=True,
                acoustic_endpoint=acoustic_endpoint,
                speech_active=speech_active,
                continuation_elapsed_ms=elapsed,
            )
            return self._apply_decision_locked(
                event,
                decision,
                effective_epoch,
                acoustic_endpoint=acoustic_endpoint,
                analysis_failed=analysis_failed,
            )

    def timeout(self) -> ConversationCompletion:
        """Force one bounded acoustic fallback for a pending continuation."""
        with self._lock:
            if not self._active or self._cancelled or not self._segments or self._last_event is None:
                return self._result(
                    ConversationResultStatus.NOOP,
                    False,
                    None,
                    None,
                    "NO_PENDING_CONTINUATION",
                )
            event = self._last_event
            effective_epoch = event.epoch or self._epoch
            decision, analysis_failed = self._safe_decide(
                turn_id=self._turn_id,
                utterance_id=self._logical_utterance_id,
                transcript=self._combined_text_locked(),
                is_final=True,
                acoustic_endpoint=True,
                speech_active=False,
                continuation_elapsed_ms=self._detector.config.max_continuation_window_ms
                if isinstance(self._detector, DeterministicSemanticTurnDetector)
                else None,
            )
            return self._apply_decision_locked(
                event,
                decision,
                effective_epoch,
                acoustic_endpoint=True,
                analysis_failed=analysis_failed,
            )

    def _apply_decision_locked(
        self,
        source_event: TranscriptEvent,
        decision: SemanticTurnDecision,
        effective_epoch: int,
        *,
        acoustic_endpoint: bool,
        analysis_failed: bool,
    ) -> ConversationCompletion:
        if decision.state is SemanticTurnState.CONTINUE_LISTENING:
            if self._continuation_started_at is None:
                self._continuation_started_at = time.monotonic()
            return self._result(
                ConversationResultStatus.WAITING_CONTINUATION,
                False,
                source_event,
                decision,
                decision.reason_code.value,
            )
        if decision.state is SemanticTurnState.COMPLETE:
            return self._complete_locked(source_event, decision, effective_epoch)
        if decision.state is SemanticTurnState.UNCERTAIN and source_event is not None:
            if decision.reason_code is SemanticTurnReason.CONTINUATION_TIMEOUT:
                return self._complete_locked(source_event, decision, effective_epoch)
            if source_event.is_final and acoustic_endpoint and (
                analysis_failed
                or decision.reason_code is not SemanticTurnReason.INVALID_INPUT
            ):
                # Acoustic endpoint is the approved bounded fallback when
                # semantic evidence cannot make a stronger decision.
                return self._complete_locked(
                    source_event,
                    decision,
                    effective_epoch,
                    reason_code=SemanticTurnReason.ACOUSTIC_FALLBACK.value,
                )
        return self._result(
            ConversationResultStatus.REJECTED_UNCERTAIN,
            False,
            source_event,
            decision,
            decision.reason_code.value,
        )

    def _complete_locked(
        self,
        source_event: TranscriptEvent,
        decision: SemanticTurnDecision,
        effective_epoch: int,
        *,
        reason_code: str | None = None,
    ) -> ConversationCompletion:
        output_event = self._build_output_event_locked(source_event, effective_epoch)
        self._completed_identity = (
            self._session_id,
            self._turn_id,
            self._logical_utterance_id,
            effective_epoch,
        )
        self._reset_segments_locked()
        return self._result(
            ConversationResultStatus.COMPLETED,
            True,
            output_event,
            decision,
            reason_code or decision.reason_code.value,
        )

    def _build_output_event_locked(
        self, source_event: TranscriptEvent, effective_epoch: int
    ) -> TranscriptEvent:
        combined = self._combined_text_locked()
        if len(self._segments) == 1 and source_event.utterance_id == self._logical_utterance_id:
            return source_event
        metadata = dict(source_event.metadata)
        metadata["coordinator_segment_count"] = len(self._segments)
        return TranscriptEvent(
            text=combined,
            is_final=True,
            sequence=source_event.sequence,
            session_id=self._session_id,
            utterance_id=self._logical_utterance_id,
            provider=source_event.provider,
            metadata=metadata,
            epoch=effective_epoch,
        )

    def _safe_decide(
        self,
        *,
        turn_id: int,
        utterance_id: str,
        transcript: str,
        is_final: bool,
        acoustic_endpoint: bool,
        speech_active: bool,
        continuation_elapsed_ms: float | None,
    ) -> tuple[SemanticTurnDecision, bool]:
        try:
            return self._detector.decide(
                SemanticTurnInput(
                    session_id=self._session_id,
                    turn_id=turn_id,
                    utterance_id=utterance_id,
                    epoch=self._epoch,
                    transcript=transcript,
                    is_final=is_final,
                    acoustic_endpoint=acoustic_endpoint,
                    speech_active=speech_active,
                    continuation_elapsed_ms=continuation_elapsed_ms,
                )
            ), False
        except Exception:
            # The acoustic endpoint remains the bounded fallback authority.
            return SemanticTurnDecision(
                state=SemanticTurnState.UNCERTAIN,
                reason_code=SemanticTurnReason.ACOUSTIC_FALLBACK,
                confidence=0.0,
                session_id=self._session_id,
                turn_id=turn_id,
                utterance_id=utterance_id,
                epoch=self._epoch,
            ), True

    def _stale_reason(self, event: TranscriptEvent, turn_id: int) -> str:
        if not self._active or self._cancelled:
            return "CANCELLED_OR_INACTIVE"
        if event.session_id != self._session_id:
            return "STALE_SESSION"
        if int(turn_id) != self._turn_id:
            return "STALE_TURN"
        if event.epoch not in (0, self._epoch):
            return "STALE_EPOCH"
        return ""

    def _combined_text_locked(self) -> str:
        text = " ".join(part for part in self._segments if part).strip()
        return text.replace("... ...", "...").replace("… …", "…")

    def _reset_utterance_locked(self) -> None:
        self._reset_segments_locked()
        self._seen_partials.clear()
        self._seen_finals.clear()
        self._completed_identity = None
        self._last_event = None

    def _reset_segments_locked(self) -> None:
        self._logical_utterance_id = ""
        self._segments.clear()
        self._continuation_started_at = None

    def _bound_seen_sets_locked(self) -> None:
        if len(self._seen_partials) > 64:
            self._seen_partials = set(list(self._seen_partials)[-32:])
        if len(self._seen_finals) > self._max_segments:
            self._seen_finals = set(list(self._seen_finals)[-self._max_segments :])

    def _result(
        self,
        status: ConversationResultStatus,
        eligible: bool,
        event: TranscriptEvent | None,
        decision: SemanticTurnDecision | None,
        reason_code: str,
    ) -> ConversationCompletion:
        return ConversationCompletion(
            status=status,
            eligible_for_dispatch=eligible,
            event=event,
            decision=decision,
            reason_code=reason_code,
            session_id=self._session_id,
            turn_id=self._turn_id,
            utterance_id=self._logical_utterance_id or str(getattr(event, "utterance_id", "") or ""),
            epoch=self._epoch,
        )

    def _invalid(self, reason_code: str, event: TranscriptEvent | None = None) -> ConversationCompletion:
        return self._result(
            ConversationResultStatus.REJECTED_INVALID,
            False,
            event,
            None,
            reason_code,
        )

    def _rejected_stale(self, event: TranscriptEvent, reason_code: str) -> ConversationCompletion:
        return self._result(
            ConversationResultStatus.REJECTED_STALE,
            False,
            event,
            None,
            reason_code,
        )


__all__ = [
    "ConversationCompletion",
    "ConversationResultStatus",
    "ConversationStreamCoordinator",
]
