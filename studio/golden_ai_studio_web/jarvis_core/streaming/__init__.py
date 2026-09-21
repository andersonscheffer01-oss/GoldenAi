"""Streaming Voice Pipeline — P1.4B/P1.4C.

Reduces perceived latency by starting TTS before LLM finishes generating.

Feature flags:
- JARVIS_STREAMING_VOICE=1 to enable sentence-level streaming
- JARVIS_TRUE_AUDIO_STREAMING=1 to enable true audio streaming
- JARVIS_BARGE_IN=1 to enable barge-in during TTS playback

Default: all 0 (disabled, uses legacy sequential pipeline).
"""

from __future__ import annotations

import os

FEATURE_FLAG = "JARVIS_STREAMING_VOICE"
TRUE_STREAMING_FLAG = "JARVIS_TRUE_AUDIO_STREAMING"
BARGE_IN_FLAG = "JARVIS_BARGE_IN"


def is_streaming_enabled() -> bool:
    return os.getenv(FEATURE_FLAG, "0") == "1"


def is_true_streaming_enabled() -> bool:
    return os.getenv(TRUE_STREAMING_FLAG, "0") == "1"


def is_barge_in_enabled() -> bool:
    return os.getenv(BARGE_IN_FLAG, "0") == "1"


# Sentence chunker defaults
SENTENCE_TERMINATORS = ".!?;:"
MIN_CHUNK_CHARS = 8
MAX_CHUNK_CHARS = 300
PAUSE_CHARS = ",:—–"

# TTS queue
TTS_QUEUE_MAXSIZE = 8

# Audio player
AUDIO_OVERLAP_GUARD_MS = 100

# Barge-in configurable thresholds
# These are experimental defaults. Measured during real testing.
# Adjust based on actual RMS_TTS_LEAKAGE, RMS_USER_NORMAL, RMS_USER_OVER_TTS.
BARGE_IN_RMS_THRESHOLD = int(os.getenv("JARVIS_BARGE_IN_RMS_THRESHOLD", "300"))
BARGE_IN_MIN_SPEECH_MS = int(os.getenv("JARVIS_BARGE_IN_MIN_SPEECH_MS", "200"))
BARGE_IN_GRACE_SECONDS = float(os.getenv("JARVIS_BARGE_IN_GRACE_SECONDS", "0.2"))
