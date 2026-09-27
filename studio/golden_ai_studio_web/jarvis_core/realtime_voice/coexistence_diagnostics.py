"""In-memory acoustic coexistence measurements.

This module measures PCM16 levels only. It does not retain audio, open a
device, invoke VAD/STT, or decide whether a user interruption is valid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class PcmLevel:
    """Aggregate level metrics for a bounded collection of PCM16 frames."""

    frame_count: int
    sample_count: int
    rms: float
    peak: float


def measure_pcm16(frames: Iterable[bytes]) -> PcmLevel:
    """Measure true RMS and peak without persisting or returning PCM data."""
    frame_list = list(frames)
    if not frame_list:
        return PcmLevel(frame_count=0, sample_count=0, rms=0.0, peak=0.0)
    samples = np.frombuffer(b"".join(frame_list), dtype=np.int16).astype(np.float64)
    if samples.size == 0:
        return PcmLevel(frame_count=len(frame_list), sample_count=0, rms=0.0, peak=0.0)
    return PcmLevel(
        frame_count=len(frame_list),
        sample_count=int(samples.size),
        rms=float(np.sqrt(np.mean(samples * samples))),
        peak=float(np.max(np.abs(samples))),
    )


def relative_db(baseline_rms: float, observed_rms: float) -> float | None:
    """Return observed-vs-baseline level change using ``20*log10``."""
    if baseline_rms <= 0 or observed_rms <= 0:
        return None
    return float(20.0 * math.log10(observed_rms / baseline_rms))


def classify_echo(
    *,
    playback_to_mic_db: float | None,
    vad_activations: int,
    stt_observed: bool | None,
    false_barge_in: bool | None,
    meaningful_db: float = 6.0,
) -> str:
    """Classify only evidence actually supplied by the measurement gate."""
    if false_barge_in is True:
        return "CLASS_4"
    if stt_observed is True:
        return "CLASS_3"
    if vad_activations > 0:
        return "CLASS_2"
    if playback_to_mic_db is None:
        return "INCONCLUSIVE"
    if playback_to_mic_db >= meaningful_db:
        return "CLASS_1"
    return "CLASS_0"


__all__ = ["PcmLevel", "classify_echo", "measure_pcm16", "relative_db"]
