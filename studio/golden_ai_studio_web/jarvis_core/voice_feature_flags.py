"""Central feature flags for the experimental realtime voice path.

All flags are opt-in. Existing streaming/barge-in names remain the canonical
compatibility names; this module prevents new code from inventing duplicates.
"""
from __future__ import annotations

import os


ADAPTIVE_MICROPHONE_FLAG = "JARVIS_VOICE_ADAPTIVE_MICROPHONE"
SHORT_CONFIRMATIONS_FLAG = "JARVIS_VOICE_SHORT_CONFIRMATIONS"
GEMINI_LIVE_FLAG = "JARVIS_GEMINI_LIVE"


def _enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().casefold() in {"1", "true", "yes", "on"}


def adaptive_microphone_enabled() -> bool:
    return _enabled(ADAPTIVE_MICROPHONE_FLAG)


def low_latency_streaming_enabled() -> bool:
    """Reuse the established sentence/true-streaming flags."""
    return _enabled("JARVIS_STREAMING_VOICE") or _enabled("JARVIS_TRUE_AUDIO_STREAMING")


def barge_in_enabled() -> bool:
    """Reuse the established barge-in flag."""
    return _enabled("JARVIS_BARGE_IN")


def short_confirmations_enabled() -> bool:
    return _enabled(SHORT_CONFIRMATIONS_FLAG)


def gemini_live_enabled() -> bool:
    return _enabled(GEMINI_LIVE_FLAG)


def snapshot() -> dict[str, bool]:
    return {
        "voice_adaptive_microphone": adaptive_microphone_enabled(),
        "voice_low_latency_streaming": low_latency_streaming_enabled(),
        "voice_barge_in": barge_in_enabled(),
        "voice_short_confirmations": short_confirmations_enabled(),
        "gemini_live": gemini_live_enabled(),
    }

