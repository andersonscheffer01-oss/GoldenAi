"""Real, provider-neutral PCM output for the Windows voice foundation.

The adapter owns one optional ``sounddevice.RawOutputStream``.  It does not
know about Core, TTS, STT, tools, persistence, or network services; those
concerns remain above :class:`AudioOutputProvider` and VoiceService.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable, Optional

from .voice_tts import AudioOutputProvider, PcmAudioChunk


class AudioOutputError(RuntimeError):
    """Controlled audio-output lifecycle or device error."""


class AudioOutputUnavailable(AudioOutputError):
    """Raised when the optional sounddevice backend is unavailable."""


def _sounddevice_stream_factory(**kwargs: Any) -> Any:
    """Create a RawOutputStream without importing sounddevice at module load."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise AudioOutputUnavailable("sounddevice is not installed") from exc
    try:
        return sd.RawOutputStream(**kwargs)
    except Exception as exc:
        raise AudioOutputError(f"could not open audio output stream: {exc}") from exc


class SoundDeviceAudioOutputProvider:
    """Bounded PCM16 output sink backed by one PortAudio output stream.

    The callback only copies already-validated PCM bytes into ``outdata`` and
    fills silence when the queue is empty.  It never calls Core, VoiceService,
    TTS/STT, security, filesystem, or network code.
    """

    BYTES_PER_SAMPLE = 2
    SUPPORTED_CHANNELS = (1, 2)
    MIN_SAMPLE_RATE = 8_000
    MAX_SAMPLE_RATE = 192_000

    def __init__(
        self,
        *,
        device: Any = None,
        maxsize: int = 8,
        overflow_policy: str = "drop_oldest",
        stream_factory: Optional[Callable[..., Any]] = None,
        sounddevice_module: Any = None,
        recovery_attempts: int = 1,
    ) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if overflow_policy not in {"drop_oldest", "reject"}:
            raise ValueError("overflow_policy must be drop_oldest or reject")
        if recovery_attempts < 0:
            raise ValueError("recovery_attempts cannot be negative")
        self.device = device
        self.maxsize = int(maxsize)
        self.overflow_policy = overflow_policy
        self.recovery_attempts = int(recovery_attempts)
        self._sounddevice = sounddevice_module
        if stream_factory is not None:
            self._stream_factory = stream_factory
        elif sounddevice_module is not None:
            self._stream_factory = lambda **kwargs: sounddevice_module.RawOutputStream(**kwargs)
        else:
            self._stream_factory = _sounddevice_stream_factory

        self._queue: deque[PcmAudioChunk] = deque()
        self._playback_buffer = bytearray()
        self._lock = threading.RLock()
        self._stream: Any = None
        self._running = False
        self._cancelled = True
        self._released = False
        self._format: tuple[int, int, str] | None = None
        self._identity: tuple[str, int, int] | None = None
        self._open_attempts = 0
        self._device_lost = False
        self._last_error = ""
        self._callback_errors = 0
        self._accepted = 0
        self._dropped = 0
        self._rejected = 0

    @property
    def qsize(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def rejected(self) -> int:
        with self._lock:
            return self._rejected

    @property
    def accepted(self) -> int:
        with self._lock:
            return self._accepted

    @property
    def stream(self) -> Any:
        with self._lock:
            return self._stream

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._running and not self._cancelled and not self._released

    @property
    def queue_policy(self) -> str:
        return self.overflow_policy

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._running and not self._cancelled and not self._released,
                "cancelled": self._cancelled,
                "released": self._released,
                "device": self.device,
                "queue_size": len(self._queue),
                "queue_maxsize": self.maxsize,
                "queue_policy": self.overflow_policy,
                "accepted": self._accepted,
                "dropped": self._dropped,
                "rejected": self._rejected,
                "callback_errors": self._callback_errors,
                "open_attempts": self._open_attempts,
                "device_lost": self._device_lost,
                "format": self._format,
                "last_error": self._last_error,
            }

    def warm(self) -> None:
        with self._lock:
            if self._released:
                raise AudioOutputError("audio output is released")
            self._cancelled = False
            self._open_attempts = 0
            self._device_lost = False
            self._last_error = ""
            self._format = None
            self._identity = None

    def enqueue(self, chunk: PcmAudioChunk) -> bool:
        self._validate_chunk(chunk)
        with self._lock:
            if self._cancelled or self._released:
                self._rejected += 1
                return False
            if self._identity is not None and chunk.identity != self._identity:
                self._rejected += 1
                self._last_error = "turn boundary required before changing audio identity"
                return False
            if self._format is not None and self._format != self._chunk_format(chunk):
                self._rejected += 1
                self._last_error = "format change requires a turn boundary"
                return False
            if self._identity is None:
                self._identity = chunk.identity
            if self._format is None:
                self._format = self._chunk_format(chunk)

            if len(self._queue) >= self.maxsize:
                if self.overflow_policy == "reject":
                    self._rejected += 1
                    return False
                self._queue.popleft()
                self._dropped += 1
            self._queue.append(chunk)

            if self._stream is None:
                if not self._open_stream_locked(chunk):
                    self._queue.pop()
                    self._rejected += 1
                    return False
            self._accepted += 1
            return True

    def cancel(self, reason: str = "cancelled") -> None:
        del reason
        stream = self._invalidate_and_detach(flush=True)
        self._close_stream(stream)

    def flush(self) -> int:
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            self._playback_buffer.clear()
            return count

    def stop(self) -> None:
        self.cancel("stopped")

    def restart(self) -> None:
        self.cancel("restart")
        self.warm()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        stream = self._invalidate_and_detach(flush=True)
        self._close_stream(stream)

    shutdown = release

    def recover(self) -> bool:
        """Reopen the same configured device after a bounded device loss."""
        with self._lock:
            if self._released or self._cancelled or not self._device_lost:
                return False
            stream = self._stream
            self._stream = None
            self._running = False
        self._close_stream(stream)
        with self._lock:
            if not self._queue:
                self._device_lost = False
                return True
            return self._open_stream_locked(self._queue[0])

    @classmethod
    def enumerate_devices(cls, sounddevice_module: Any = None) -> list[dict[str, Any]]:
        sd = sounddevice_module or cls._load_sounddevice()
        devices = sd.query_devices()
        if isinstance(devices, dict):
            devices = [devices]
        result = []
        for index, device in enumerate(devices):
            if int(device.get("max_output_channels", 0)) <= 0:
                continue
            result.append({
                "index": index,
                "name": str(device.get("name", "")),
                "max_output_channels": int(device.get("max_output_channels", 0)),
                "default_samplerate": float(device.get("default_samplerate", 0.0)),
            })
        return result

    @classmethod
    def default_output_device(cls, sounddevice_module: Any = None) -> Any:
        sd = sounddevice_module or cls._load_sounddevice()
        default = getattr(getattr(sd, "default", None), "device", None)
        if isinstance(default, (tuple, list)) and len(default) > 1:
            return default[1]
        return default

    @classmethod
    def _load_sounddevice(cls) -> Any:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioOutputUnavailable("sounddevice is not installed") from exc
        return sd

    def _validate_chunk(self, chunk: PcmAudioChunk) -> None:
        if not isinstance(chunk, PcmAudioChunk):
            raise TypeError("audio output accepts PcmAudioChunk only")
        if not self.MIN_SAMPLE_RATE <= chunk.sample_rate <= self.MAX_SAMPLE_RATE:
            raise ValueError("sample_rate is outside the supported range")
        if chunk.channels not in self.SUPPORTED_CHANNELS:
            raise ValueError("only mono or stereo PCM is supported")
        if chunk.sample_format != "s16le":
            raise ValueError("only s16le PCM is supported")
        frame_bytes = self.BYTES_PER_SAMPLE * chunk.channels
        if len(chunk.pcm) == 0 or len(chunk.pcm) % frame_bytes:
            raise ValueError("PCM bytes are not frame aligned")

    @staticmethod
    def _chunk_format(chunk: PcmAudioChunk) -> tuple[int, int, str]:
        return chunk.sample_rate, chunk.channels, chunk.sample_format

    def _open_stream_locked(self, chunk: PcmAudioChunk) -> bool:
        if self._stream is not None:
            return True
        max_attempts = 1 + self.recovery_attempts
        if self._open_attempts >= max_attempts:
            return False
        self._open_attempts += 1
        rate, channels, sample_format = self._chunk_format(chunk)
        try:
            stream = self._stream_factory(
                samplerate=rate,
                channels=channels,
                dtype="int16" if sample_format == "s16le" else sample_format,
                blocksize=0,
                device=self.device,
                callback=self._callback,
            )
            stream.start()
        except Exception as exc:
            self._last_error = str(exc)
            self._running = False
            self._stream = None
            try:
                stream.close()  # type: ignore[has-type]
            except Exception:
                pass
            return False
        self._stream = stream
        self._running = True
        self._device_lost = False
        return True

    def _invalidate_and_detach(self, *, flush: bool) -> Any:
        with self._lock:
            self._cancelled = True
            self._running = False
            stream = self._stream
            self._stream = None
            self._identity = None
            self._format = None
            self._device_lost = False
            if flush:
                self._queue.clear()
                self._playback_buffer.clear()
            return stream

    @staticmethod
    def _close_stream(stream: Any) -> None:
        if stream is None:
            return
        for method_name in ("abort", "stop", "close"):
            method = getattr(stream, method_name, None)
            if method is None:
                continue
            try:
                method()
            except Exception:
                continue

    def _callback(self, outdata: Any, frames: int, time_info: Any = None, status: Any = None) -> None:
        del time_info
        with self._lock:
            channels = self._format[1] if self._format is not None else 1
            requested = max(0, int(frames)) * channels * self.BYTES_PER_SAMPLE
            if status:
                self._callback_errors += 1
                self._last_error = str(status)
                if "device" in str(status).lower() or "underflow" in str(status).lower():
                    self._device_lost = True
            if not self._running or self._cancelled or self._released:
                payload = b"\x00" * requested
            else:
                while len(self._playback_buffer) < requested and self._queue:
                    self._playback_buffer.extend(self._queue.popleft().pcm)
                payload = bytes(self._playback_buffer[:requested])
                del self._playback_buffer[:requested]
                payload += b"\x00" * (requested - len(payload))
        try:
            view = memoryview(outdata).cast("B")
            view[:requested] = payload
        except Exception:
            with self._lock:
                self._callback_errors += 1


__all__ = [
    "AudioOutputError",
    "AudioOutputUnavailable",
    "SoundDeviceAudioOutputProvider",
]
