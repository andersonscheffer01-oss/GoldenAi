"""Hybrid endpoint: Silero END_CANDIDATE + RMS hangover guard.

Sits between Silero VAD and UtteranceBuffer. When Silero declares
an endpoint, opens a configurable hangover window. During hangover,
RMS energy confirms whether speech actually ended.

Feature flag: JARVIS_HYBRID_ENDPOINT=1
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

import numpy as np

from jarvis_core.realtime_voice.constants import (
    HYBRID_HANGOVER_MS_DEFAULT,
    HYBRID_RMS_THRESHOLD_DEFAULT,
)

log = logging.getLogger(__name__)


class HybridPhase(Enum):
    IDLE = "idle"
    SPEECH = "speech"
    HANGOVER = "hangover"


class HybridEvent(Enum):
    SPEECH_STARTED = "speech_started"
    ENDPOINT = "endpoint"
    SPEECH_RESUMED = "speech_resumed"


class HybridEndpoint:
    """Manages hangover window and tail buffer for hybrid endpointing.

    Usage in _frame_loop():
        he = HybridEndpoint(...)
        # On SPEECH_STARTED from Silero:
        he.on_speech_started()
        # On ENDPOINT from Silero (becomes END_CANDIDATE):
        evt = he.on_endpoint_candidate(frame)
        # On every frame during HANGOVER:
        evt = he.feed_hangover(frame, rms_energy)
    """

    def __init__(
        self,
        *,
        hangover_ms: int = HYBRID_HANGOVER_MS_DEFAULT,
        rms_threshold: float = HYBRID_RMS_THRESHOLD_DEFAULT,
        time_fn=None,
    ) -> None:
        if hangover_ms < 0:
            raise ValueError(f"hangover_ms must be >= 0, got {hangover_ms}")
        if rms_threshold < 0:
            raise ValueError(
                f"rms_threshold must be >= 0, got {rms_threshold}"
            )

        self.hangover_ms = hangover_ms
        self.rms_threshold = rms_threshold
        self._time_fn = time_fn or time.monotonic

        self._phase: HybridPhase = HybridPhase.IDLE
        self._hangover_start: float = 0.0
        self._hangover_frames: list[bytes] = []
        self._speech_start_at: float = 0.0

    @property
    def phase(self) -> HybridPhase:
        return self._phase

    @property
    def in_hangover(self) -> bool:
        return self._phase is HybridPhase.HANGOVER

    @property
    def hangover_elapsed_ms(self) -> float:
        if self._phase is not HybridPhase.HANGOVER:
            return 0.0
        return (self._time_fn() - self._hangover_start) * 1000.0

    @property
    def hangover_remaining_ms(self) -> float:
        elapsed = self.hangover_elapsed_ms
        return max(0.0, self.hangover_ms - elapsed)

    def on_speech_started(self) -> None:
        """Called when Silero emits SPEECH_STARTED."""
        self._phase = HybridPhase.SPEECH
        self._speech_start_at = self._time_fn()
        self._hangover_frames.clear()
        log.debug("hybrid: speech started")

    def on_endpoint_candidate(self, frame: bytes) -> Optional[HybridEvent]:
        """Called when Silero emits ENDPOINT during SPEECH.

        Opens the hangover window. Returns None (no final event yet)
        or ENDPOINT if hangover is disabled or not in SPEECH.
        """
        if self._phase is not HybridPhase.SPEECH:
            return HybridEvent.ENDPOINT

        if self.hangover_ms <= 0:
            self._phase = HybridPhase.IDLE
            return HybridEvent.ENDPOINT

        self._phase = HybridPhase.HANGOVER
        self._hangover_start = self._time_fn()
        self._hangover_frames = [frame]
        log.debug(
            "hybrid: ENDPOINT_CANDIDATE, hangover=%dms",
            self.hangover_ms,
        )
        return None

    def feed_hangover(
        self, frame: bytes, rms_energy: float
    ) -> Optional[HybridEvent]:
        """Feed a frame during HANGOVER phase.

        Args:
            frame: The raw PCM frame (FRAME_BYTES).
            rms_energy: Mean absolute amplitude of this frame.

        Returns:
            HybridEvent.SPEECH_RESUMED if speech detected.
            HybridEvent.ENDPOINT if hangover expires.
            None if hangover still in progress.
        """
        if self._phase is not HybridPhase.HANGOVER:
            return None

        elapsed_ms = (self._time_fn() - self._hangover_start) * 1000.0
        if elapsed_ms >= self.hangover_ms:
            log.info(
                "hybrid: hangover expired (%.0fms), confirming endpoint",
                elapsed_ms,
            )
            self._phase = HybridPhase.IDLE
            return HybridEvent.ENDPOINT

        if rms_energy >= self.rms_threshold:
            log.info(
                "hybrid: speech during hangover (rms=%.0f >= %.0f), cancelling",
                rms_energy,
                self.rms_threshold,
            )
            self._phase = HybridPhase.SPEECH
            self._hangover_frames.clear()
            return HybridEvent.SPEECH_RESUMED

        self._hangover_frames.append(frame)
        return None

    def get_tail_frames(self) -> list[bytes]:
        """Get accumulated tail frames."""
        return list(self._hangover_frames)

    def clear_tail(self) -> None:
        """Discard tail frames."""
        self._hangover_frames.clear()

    def reset(self) -> None:
        """Full reset (on barge-in, listen timeout, etc.)."""
        self._phase = HybridPhase.IDLE
        self._hangover_start = 0.0
        self._hangover_frames.clear()
        self._speech_start_at = 0.0


def rms_energy(frame_bytes: bytes) -> float:
    """Compute mean absolute amplitude from int16 PCM bytes."""
    if len(frame_bytes) < 2:
        return 0.0
    samples = np.frombuffer(frame_bytes, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.abs(samples).mean())
