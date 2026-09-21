"""Silero ONNX VAD adapter for realtime voice pipeline.

Adapted from ndunl075-jarvis MIT-licensed audio/vad.py.
Uses faster_whisper's silero_vad_v6.onnx model (ONNX-only, no torch).

License: ndunl075-jarvis is MIT. This file is a derived adaptation.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from jarvis_core.realtime_voice.constants import (
    FRAME_BYTES,
    SAMPLE_RATE,
    SPEECH_START_WINDOWS_DEFAULT,
    VAD_ENDPOINT_MS_DEFAULT,
    VAD_SPEECH_THRESHOLD_DEFAULT,
    VAD_WINDOW_BYTES,
    VAD_WINDOW_MS,
    VAD_WINDOW_SAMPLES,
)

log = logging.getLogger(__name__)

# Silero v6 ONNX model: input shape [seq_len, 576] where 576 = 512 + 64 context
_VAD_CONTEXT_SAMPLES: int = 64
_VAD_INPUT_SAMPLES: int = VAD_WINDOW_SAMPLES + _VAD_CONTEXT_SAMPLES  # 576
_VAD_STATE_SHAPE: tuple[int, int, int] = (1, 1, 128)


class VADModelMissingError(RuntimeError):
    """Raised when the silero ONNX file cannot be located."""


class VADEvent(Enum):
    SPEECH_STARTED = "speech_started"
    ENDPOINT = "endpoint"


class _Internal(Enum):
    SILENCE = "silence"
    SPEECH = "speech"


def _find_silero_onnx() -> Optional[Path]:
    """Locate silero_vad_v6.onnx from faster_whisper assets.

    Does NOT import faster_whisper or torch. Uses sysconfig to find
    site-packages and locates the file directly.
    """
    import sysconfig

    purelib = Path(sysconfig.get_paths()["purelib"])
    # faster_whisper ships its own ONNX model
    onnx = purelib / "faster_whisper" / "assets" / "silero_vad_v6.onnx"
    if onnx.exists():
        return onnx
    # Fallback: silero_vad package (if installed separately)
    onnx2 = purelib / "silero_vad" / "data" / "silero_vad.onnx"
    return onnx2 if onnx2.exists() else None


class SileroVADAdapter:
    """Frame-by-frame VAD using Silero ONNX without torch.

    Adapts ndunl075-jarvis audio/vad.py (MIT) to the Golden AI pipeline.
    Uses faster_whisper's silero_vad_v6.onnx model with (h, c) state tensors.
    """

    def __init__(
        self,
        *,
        speech_threshold: float = VAD_SPEECH_THRESHOLD_DEFAULT,
        endpoint_ms: int = VAD_ENDPOINT_MS_DEFAULT,
        speech_start_windows: int = SPEECH_START_WINDOWS_DEFAULT,
        model_path: Optional[Path] = None,
        on_probability: Optional[Callable[[float], None]] = None,
    ) -> None:
        if not 0.0 <= speech_threshold <= 1.0:
            raise ValueError(
                f"speech_threshold must be in [0.0, 1.0], got {speech_threshold}"
            )
        if endpoint_ms <= 0:
            raise ValueError(f"endpoint_ms must be positive, got {endpoint_ms}")
        if speech_start_windows < 1:
            raise ValueError(
                f"speech_start_windows must be >= 1, got {speech_start_windows}"
            )

        self.speech_threshold = speech_threshold
        self.endpoint_ms = endpoint_ms
        self.speech_start_windows = speech_start_windows
        self._model_path = model_path
        self.model_path: Optional[Path] = None
        self._on_probability = on_probability

        self._session: Any = None
        self._h: Optional[np.ndarray] = None
        self._c: Optional[np.ndarray] = None
        self._context: Optional[np.ndarray] = None
        self._buffer = bytearray()
        self._internal: _Internal = _Internal.SILENCE
        self._silence_ms: int = 0
        self._consecutive_speech_windows: int = 0
        self.is_loaded: bool = False

    async def load(self) -> None:
        if self.is_loaded:
            return

        try:
            import onnxruntime as ort
        except ImportError as e:
            raise VADModelMissingError("onnxruntime is not installed") from e

        path = self._model_path or _find_silero_onnx()
        if path is None or not Path(path).exists():
            raise VADModelMissingError(
                "silero ONNX file not found. Expected via faster_whisper "
                "assets or silero_vad package."
            )

        self.model_path = Path(path)
        log.info("[vadapter] silero onnx from: %s", self.model_path)

        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            opts.enable_cpu_mem_arena = False
            opts.log_severity_level = 4
            self._session = ort.InferenceSession(
                str(path),
                providers=["CPUExecutionProvider"],
                sess_options=opts,
            )
        except Exception as e:
            raise VADModelMissingError(
                f"could not load silero ONNX from {path}: {e}"
            ) from e

        self._h = np.zeros(_VAD_STATE_SHAPE, dtype=np.float32)
        self._c = np.zeros(_VAD_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, _VAD_CONTEXT_SAMPLES), dtype=np.float32)
        self.reset()
        self.is_loaded = True

    async def unload(self) -> None:
        if not self.is_loaded:
            return
        self._session = None
        self._h = None
        self._c = None
        self._context = None
        self._buffer.clear()
        self.is_loaded = False

    async def feed(self, frame: bytes) -> Optional[VADEvent]:
        """Feed a single audio frame (FRAME_BYTES of int16 PCM).

        Returns VADEvent on state transition, None otherwise.
        """
        if self._session is None:
            return None
        if len(frame) != FRAME_BYTES:
            log.error(
                "vadapter: wrong frame size %d (expected %d)",
                len(frame), FRAME_BYTES,
            )
            return None

        self._buffer.extend(frame)
        events: list[VADEvent] = []

        while len(self._buffer) >= VAD_WINDOW_BYTES:
            chunk_bytes = bytes(self._buffer[:VAD_WINDOW_BYTES])
            del self._buffer[:VAD_WINDOW_BYTES]

            # Convert int16 PCM -> float32 normalized
            audio = (
                np.frombuffer(chunk_bytes, dtype=np.int16)
                .astype(np.float32) / 32768.0
            )

            # Build input: [context, audio] concatenated -> [1, 576]
            input_array = np.concatenate(
                [self._context.flatten(), audio]
            ).reshape(1, _VAD_INPUT_SAMPLES)

            try:
                prob_arr, new_h, new_c = self._session.run(
                    None,
                    {
                        "input": input_array,
                        "h": self._h,
                        "c": self._c,
                    },
                )
            except Exception:
                log.exception("silero inference raised")
                continue

            self._h = new_h
            self._c = new_c
            # Update context: last 64 samples of the current chunk
            self._context = audio[-_VAD_CONTEXT_SAMPLES:].reshape(1, -1)

            prob = float(np.asarray(prob_arr).squeeze())
            if self._on_probability is not None:
                try:
                    self._on_probability(prob)
                except Exception:
                    log.exception("on_probability callback raised")

            evt = self._step(prob)
            if evt is not None:
                events.append(evt)

        if VADEvent.ENDPOINT in events:
            return VADEvent.ENDPOINT
        if VADEvent.SPEECH_STARTED in events:
            return VADEvent.SPEECH_STARTED
        return None

    def reset(self) -> None:
        """Clear per-session state. Called on entry to LISTENING and on barge-in."""
        if self._h is not None:
            self._h.fill(0)
        if self._c is not None:
            self._c.fill(0)
        if self._context is not None:
            self._context.fill(0)
        self._buffer.clear()
        self._internal = _Internal.SILENCE
        self._silence_ms = 0
        self._consecutive_speech_windows = 0

    def _step(self, prob: float) -> Optional[VADEvent]:
        if self._internal is _Internal.SILENCE:
            if prob >= self.speech_threshold:
                self._consecutive_speech_windows += 1
                if self._consecutive_speech_windows >= self.speech_start_windows:
                    self._internal = _Internal.SPEECH
                    self._silence_ms = 0
                    self._consecutive_speech_windows = 0
                    return VADEvent.SPEECH_STARTED
                return None
            self._consecutive_speech_windows = 0
            return None

        # In SPEECH
        if prob >= self.speech_threshold:
            self._silence_ms = 0
            return None
        self._silence_ms += VAD_WINDOW_MS
        if self._silence_ms >= self.endpoint_ms:
            self._internal = _Internal.SILENCE
            self._silence_ms = 0
            return VADEvent.ENDPOINT
        return None
