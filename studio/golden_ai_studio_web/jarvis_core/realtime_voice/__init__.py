"""Realtime Voice Adapter — optional pipeline for comparison.

Feature flag: JARVIS_REALTIME_VOICE_V2=1 to enable.
Default: 0 (disabled, uses current pipeline).

Hybrid endpoint: JARVIS_HYBRID_ENDPOINT=1 to enable.
Default: 0 (disabled, uses pure Silero or pure RMS).
"""

import os

FEATURE_FLAG = "JARVIS_REALTIME_VOICE_V2"
HYBRID_FLAG = "JARVIS_HYBRID_ENDPOINT"


def is_enabled() -> bool:
    return os.getenv(FEATURE_FLAG, "0") == "1"


def is_hybrid_enabled() -> bool:
    return os.getenv(HYBRID_FLAG, "0") == "1"
