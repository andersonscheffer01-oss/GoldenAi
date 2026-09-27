"""Barge-in foundation for the realtime voice pipeline.

Provides infrastructure for:
- Jarvis speaking + VAD detects real user speech → cancel TTS → LISTENING
- Self-audio protection (Jarvis hearing its own TTS output)
- Grace period after TTS start
- Cancellation token for response chain

Adapted from ndunl075-jarvis MIT-licensed audio/pipeline.py barge-in logic.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Optional

from jarvis_core.realtime_voice.constants import BARGE_IN_GRACE_SECONDS
from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    VoiceStateMachine,
)

log = logging.getLogger(__name__)


class EchoDecision(str, Enum):
    """Input classification used by the output-aware VAD boundary."""

    ALLOW_BARGE_IN = "allow_barge_in"
    IGNORE_AS_SELF_TRIGGER = "ignore_as_self_trigger"
    UNCERTAIN = "uncertain"


class SelfTriggerPolicy:
    """Deterministic self-trigger policy; this is not acoustic echo cancellation."""

    def __init__(self, *, self_output_threshold: float = 500.0) -> None:
        self.self_output_threshold = float(self_output_threshold)

    def classify(
        self,
        source: str = "unknown",
        *,
        tts_active: bool = False,
        audio_level: float = 0.0,
    ) -> EchoDecision:
        normalized = str(source or "unknown").strip().lower()
        if normalized in {"user", "user_speech", "human", "speech"}:
            return EchoDecision.ALLOW_BARGE_IN
        if normalized in {"self", "self_output", "tts", "echo"}:
            return EchoDecision.IGNORE_AS_SELF_TRIGGER
        # Preserve the existing energy heuristic as a guard only. It does not
        # identify a speaker and must not suppress all speech during playback.
        if tts_active and float(audio_level) > self.self_output_threshold:
            return EchoDecision.IGNORE_AS_SELF_TRIGGER
        return EchoDecision.UNCERTAIN


class BargeInController:
    """Manages barge-in signals with grace period and self-audio protection.

    Integration points:
    - On TTS start: call `tts_started()`
    - On TTS end: call `tts_ended()`
    - On VAD SPEECH_STARTED during SPEAKING: call `check_barge_in()`
    - On user audio route: call `is_self_audio()` to filter feedback
    """

    def __init__(
        self,
        state_machine: VoiceStateMachine,
        *,
        grace_seconds: float = BARGE_IN_GRACE_SECONDS,
        self_audio_protection: bool = True,
        self_trigger_policy: Optional[SelfTriggerPolicy] = None,
    ) -> None:
        self._sm = state_machine
        self._grace_seconds = grace_seconds
        self._self_audio_protection = self_audio_protection
        self._self_trigger_policy = self_trigger_policy or SelfTriggerPolicy()
        self._tts_started_at: Optional[float] = None
        self._tts_active = False
        self._on_barge_in: Optional[Callable[[], None]] = None

    @property
    def tts_active(self) -> bool:
        return self._tts_active

    @property
    def tts_elapsed_seconds(self) -> Optional[float]:
        if self._tts_started_at is None:
            return None
        return time.monotonic() - self._tts_started_at

    def set_barge_in_handler(self, handler: Callable[[], None]) -> None:
        self._on_barge_in = handler

    @property
    def handler_installed(self) -> bool:
        return self._on_barge_in is not None

    @property
    def self_trigger_policy(self) -> SelfTriggerPolicy:
        return self._self_trigger_policy

    def tts_started(self) -> None:
        """Mark TTS playback as started."""
        self._tts_started_at = time.monotonic()
        self._tts_active = True
        log.debug("barge-in: TTS started, grace=%.1fs", self._grace_seconds)

    def tts_ended(self) -> None:
        """Mark TTS playback as ended."""
        self._tts_started_at = None
        self._tts_active = False
        log.debug("barge-in: TTS ended")

    def check_barge_in(self) -> bool:
        """Check if VAD speech during SPEAKING constitutes a valid barge-in.

        Returns True if barge-in should be triggered.
        """
        if not self._sm.can_barge_in():
            return False

        # Grace period: suppress false positives from speaker feedback
        if self._tts_started_at is not None:
            elapsed = time.monotonic() - self._tts_started_at
            if elapsed < self._grace_seconds:
                log.debug(
                    "barge-in: suppressed within grace (%.1fs < %.1fs)",
                    elapsed, self._grace_seconds,
                )
                return False

        log.info(
            "barge-in: triggered after %.1fs of TTS",
            self._tts_started_at is not None
            and (time.monotonic() - self._tts_started_at) or 0,
        )
        self._tts_active = False
        self._tts_started_at = None
        return True

    def trigger_barge_in(self) -> bool:
        """Validate and notify the owner without creating another authority."""
        if not self.check_barge_in():
            return False
        if self._on_barge_in is not None:
            self._on_barge_in()
        return True

    def is_self_audio(self, audio_level: float, threshold: float = 500) -> bool:
        """Heuristic: detect if audio is likely TTS playback leaking into mic.

        Simple energy-based check. True if audio looks like system output
        rather than user speech. This is a basic protection — not a full AEC.
        """
        if not self._self_audio_protection:
            return False
        policy = self._self_trigger_policy
        if threshold != 500:
            policy = SelfTriggerPolicy(self_output_threshold=threshold)
        return policy.classify(
            "unknown", tts_active=self._tts_active, audio_level=audio_level
        ) is EchoDecision.IGNORE_AS_SELF_TRIGGER

    def reset(self) -> None:
        """Reset barge-in state (e.g., on new listen cycle)."""
        self._tts_started_at = None
        self._tts_active = False
