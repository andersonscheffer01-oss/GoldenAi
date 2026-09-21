"""Shared constants for the realtime voice pipeline.

Adapted from ndunl075-jarvis MIT-licensed audio/protocols.py.
"""

from __future__ import annotations

# Audio format: 16 kHz mono int16
SAMPLE_RATE: int = 16_000
FRAME_SAMPLES: int = 480  # 30 ms at 16 kHz
FRAME_BYTES: int = FRAME_SAMPLES * 2  # int16 = 2 bytes/sample
FRAME_DURATION_MS: int = FRAME_SAMPLES * 1000 // SAMPLE_RATE  # 30

# Silero VAD ONNX requires 512-sample windows (32 ms)
VAD_WINDOW_SAMPLES: int = 512
VAD_WINDOW_BYTES: int = VAD_WINDOW_SAMPLES * 2
VAD_WINDOW_MS: int = VAD_WINDOW_SAMPLES * 1000 // SAMPLE_RATE  # 32

# Default VAD parameters
VAD_ENDPOINT_MS_DEFAULT: int = 700
SPEECH_START_WINDOWS_DEFAULT: int = 3  # ~96 ms at 32 ms window
VAD_SPEECH_THRESHOLD_DEFAULT: float = 0.5

# Barge-in
BARGE_IN_GRACE_SECONDS: float = 0.2
POST_WAKE_BLACKOUT_MS: int = 100

# Listening timeout
LISTENING_TIMEOUT_DEFAULT: float = 6.0

# Minimum utterance to send to STT
MIN_UTTERANCE_MS: int = 500

# Queue
AUDIO_QUEUE_MAXSIZE: int = 32  # ~1 second at 33 fps

# Hybrid endpoint
HYBRID_HANGOVER_MS_DEFAULT: int = 250
HYBRID_RMS_THRESHOLD_DEFAULT: float = 300.0
