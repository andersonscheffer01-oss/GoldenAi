"""Single-owner microphone input boundary for the realtime voice pipeline.

The provider owns only the native input stream and delivery of canonical PCM
frames. ``sounddevice`` is imported lazily so hardware-independent Voice
modules and tests remain importable without the optional backend.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue
from jarvis_core.realtime_voice.constants import (
    FRAME_BYTES,
    FRAME_SAMPLES,
    SAMPLE_RATE,
)

log = logging.getLogger(__name__)


class AudioInputError(RuntimeError):
    """Controlled failure for device/backend lifecycle errors."""


class AudioInputUnavailable(AudioInputError):
    """Raised when the optional sounddevice backend is unavailable."""


def _sounddevice_stream_factory(**kwargs: Any) -> Any:
    """Create one RawInputStream without importing sounddevice at module load."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise AudioInputUnavailable("sounddevice is not installed") from exc
    try:
        return sd.RawInputStream(**kwargs)
    except Exception as exc:
        raise AudioInputError(f"could not open audio input stream: {exc}") from exc


class AudioInputProvider:
    """Own one sounddevice stream and enqueue bounded PCM16 frames.

    ``frame_queue`` is normally the queue owned by VoiceService's realtime
    pipeline. The callback never performs I/O, inference, network, or Core
    work; it only validates/copies a frame and schedules a queue insertion.
    """

    def __init__(
        self,
        *,
        frame_queue: Optional[AudioFrameQueue] = None,
        device: Any = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        stream_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._queue = frame_queue or AudioFrameQueue()
        self._device = device
        self._loop = loop
        self._stream_factory = stream_factory or _sounddevice_stream_factory
        self._stream: Any = None
        self._running = False
        self._lock = threading.RLock()
        self._frames_received = 0
        self._invalid_frames = 0
        self._callback_errors = 0
        self._device_errors = 0
        self._sequence = 0
        self._last_frame_at = 0.0
        self._last_error = ""

    @property
    def queue(self) -> AudioFrameQueue:
        return self._queue

    @property
    def device(self) -> Any:
        return self._device

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stream(self) -> Any:
        return self._stream

    def diagnostics(self) -> dict[str, Any]:
        """Return structural counters only; no raw audio is retained."""
        queue_stats = self._queue.diagnostics
        return {
            "running": self._running,
            "device": self._device,
            "frames_received": self._frames_received,
            "invalid_frames": self._invalid_frames,
            "callback_errors": self._callback_errors,
            "device_errors": self._device_errors,
            "sequence": self._sequence,
            "last_frame_at": self._last_frame_at,
            "last_error": self._last_error,
            **queue_stats,
        }

    @classmethod
    def portaudio_readiness(cls) -> dict[str, Any]:
        """Probe import/backend/device enumeration without opening a stream."""
        try:
            import sounddevice as sd
        except ImportError as exc:
            return {"ok": False, "error": f"sounddevice unavailable: {exc}"}
        try:
            version = sd.get_portaudio_version()
            devices = sd.query_devices()
            host_apis = sd.query_hostapis()
            return {
                "ok": True,
                "portaudio_version": version[1] if isinstance(version, tuple) else str(version),
                "device_count": len(devices),
                "host_api_count": len(host_apis),
            }
        except Exception as exc:
            return {"ok": False, "error": f"PortAudio readiness failed: {exc}"}

    def start(self) -> dict[str, Any]:
        """Open exactly one stream; repeated starts do not duplicate it."""
        with self._lock:
            if self._running:
                return {"ok": True, "started": False, "already_running": True}

            self._queue.uncancel()
            self._last_error = ""
            try:
                self._running = True
                self._stream = self._stream_factory(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=FRAME_SAMPLES,
                    device=self._device,
                    callback=self._on_callback,
                )
                self._stream.start()
            except Exception as exc:
                failed_stream = self._stream
                self._running = False
                self._stream = None
                self._device_errors += 1
                self._last_error = str(exc)
                if failed_stream is not None:
                    try:
                        failed_stream.close()
                    except Exception:
                        pass
                return {"ok": False, "started": False, "error": self._last_error}

            return {"ok": True, "started": True, "already_running": False}

    def stop(self) -> dict[str, Any]:
        """Stop and close the stream; repeated stops are safe."""
        with self._lock:
            stream = self._stream
            self._running = False
            self._stream = None

        if stream is None:
            return {"ok": True, "stopped": False, "already_stopped": True}

        errors: list[str] = []
        for method_name in ("stop", "close"):
            method = getattr(stream, method_name, None)
            if method is None:
                continue
            try:
                method()
            except Exception as exc:
                errors.append(str(exc))

        if errors:
            self._device_errors += 1
            self._last_error = "; ".join(errors)
            return {"ok": False, "stopped": True, "error": self._last_error}
        return {"ok": True, "stopped": True}

    def restart(self) -> dict[str, Any]:
        """Cooperatively stop and start the same provider."""
        self.stop()
        return self.start()

    def _on_callback(
        self,
        indata: Any,
        frames: int,
        time_info: Any = None,
        status: Any = None,
    ) -> None:
        del frames, time_info
        if not self._running:
            return
        try:
            if status:
                self._device_errors += 1
                self._last_error = str(status)
            self._accept_frame(bytes(indata))
        except Exception as exc:
            self._callback_errors += 1
            self._last_error = str(exc)

    def _accept_frame(self, frame: bytes) -> None:
        if not self._running:
            return
        if len(frame) != FRAME_BYTES:
            self._invalid_frames += 1
            return

        self._frames_received += 1
        self._sequence += 1
        self._last_frame_at = time.monotonic()
        loop = self._loop
        if loop is None:
            self._enqueue_on_loop(frame)
            return
        try:
            if loop.is_closed():
                self._callback_errors += 1
                return
            loop.call_soon_threadsafe(self._enqueue_on_loop, frame)
        except RuntimeError as exc:
            self._callback_errors += 1
            self._last_error = str(exc)

    def _enqueue_on_loop(self, frame: bytes) -> None:
        if self._running:
            self._queue.put_nowait(frame)


class FakeAudioInputProvider(AudioInputProvider):
    """Deterministic no-hardware provider for lifecycle and integration tests."""

    def __init__(
        self,
        *,
        frame_queue: Optional[AudioFrameQueue] = None,
        frames: Optional[list[bytes]] = None,
    ) -> None:
        super().__init__(frame_queue=frame_queue, stream_factory=lambda **_: _FakeStream())
        self._pending_frames = deque(frames or [])

    def start(self) -> dict[str, Any]:
        result = super().start()
        if result.get("ok") and result.get("started"):
            while self._pending_frames:
                self.emit_frame(self._pending_frames.popleft())
        return result

    def emit_frame(self, frame: bytes) -> None:
        """Deliver one synthetic frame through the same provider contract."""
        self._accept_frame(bytes(frame))


class _FakeStream:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None
