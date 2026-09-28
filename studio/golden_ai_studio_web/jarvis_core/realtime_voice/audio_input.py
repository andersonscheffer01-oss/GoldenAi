"""Single-owner microphone input boundary for the realtime voice pipeline.

The provider owns one native input stream and delivers only canonical PCM
frames to Golden. Device resolution and conversion are deliberately kept at
this boundary so VAD, STT, VoiceService, and TurnManager retain their existing
contracts.
"""

from __future__ import annotations

import asyncio
import logging
import math
import queue as thread_queue
import threading
import time
from collections import deque
from typing import Any, Callable, Mapping, Optional

from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue
from jarvis_core.realtime_voice.constants import FRAME_BYTES, FRAME_SAMPLES, SAMPLE_RATE

log = logging.getLogger(__name__)

_RAW_QUEUE_MAXSIZE = 8


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


def _sounddevice_device_snapshot() -> dict[str, Any]:
    """Read PortAudio metadata without opening an input stream."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise AudioInputUnavailable("sounddevice is not installed") from exc
    default_device = getattr(sd.default, "device", (None, None))
    if isinstance(default_device, (tuple, list)):
        default_device = default_device[0] if default_device else None
    return {
        "devices": list(sd.query_devices()),
        "hostapis": list(sd.query_hostapis()),
        "default_device": default_device,
    }


class AudioInputProvider:
    """Own one native stream and enqueue bounded 16 kHz mono PCM16 frames.

    The PortAudio callback performs only byte copying, generation validation,
    lightweight counters, and bounded raw-frame enqueueing. Native-rate
    conversion and channel mixing run in a short-lived worker thread when the
    selected endpoint is not already canonical.
    """

    def __init__(
        self,
        *,
        frame_queue: Optional[AudioFrameQueue] = None,
        device: Any = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        stream_factory: Optional[Callable[..., Any]] = None,
        device_query: Optional[Callable[[], Mapping[str, Any]]] = None,
    ) -> None:
        self._queue = frame_queue or AudioFrameQueue()
        self._device = device
        self._loop = loop
        self._hardware_backend = stream_factory is None
        self._stream_factory = stream_factory or _sounddevice_stream_factory
        self._device_query = device_query or (
            _sounddevice_device_snapshot if self._hardware_backend else None
        )
        self._stream: Any = None
        self._running = False
        self._lock = threading.RLock()
        self._generation = 0
        self._frames_received = 0
        self._canonical_frames_delivered = 0
        self._invalid_frames = 0
        self._callback_errors = 0
        self._device_errors = 0
        self._input_overflow = 0
        self._raw_queue_overflow = 0
        self._raw_queue_drops = 0
        self._sequence = 0
        self._last_frame_at = 0.0
        self._last_error = ""
        self._consecutive_zero_frames = 0
        self._resolved_device: Any = device
        self._device_info: dict[str, Any] = {}
        self._logical_identity: dict[str, Any] = {}
        self._native_rate = SAMPLE_RATE
        self._capture_channels = 1
        self._native_blocksize = FRAME_SAMPLES
        self._raw_queue: Optional[thread_queue.Queue[tuple[int, bytes]]] = None
        self._conversion_stop: Optional[threading.Event] = None
        self._conversion_thread: Optional[threading.Thread] = None
        self._conversion_remainder: Any = None

    @property
    def queue(self) -> AudioFrameQueue:
        return self._queue

    @property
    def device(self) -> Any:
        return self._device

    @property
    def resolved_device(self) -> Any:
        return self._resolved_device

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stream(self) -> Any:
        return self._stream

    def diagnostics(self) -> dict[str, Any]:
        """Return structural counters only; no raw audio is retained."""
        signal_health = "UNKNOWN"
        if self._running and self._frames_received:
            signal_health = "SUSPECT" if self._consecutive_zero_frames else "OBSERVED"
        return {
            "running": self._running,
            "stream_active": self._running,
            "device": self._device,
            "resolved_device": self._resolved_device,
            "device_identity": dict(self._logical_identity),
            "native_samplerate": self._native_rate,
            "capture_samplerate": SAMPLE_RATE,
            "capture_channels": 1,
            "capture_format": "PCM16",
            "native_blocksize": self._native_blocksize,
            "frames_received": self._frames_received,
            "canonical_frames_delivered": self._canonical_frames_delivered,
            "invalid_frames": self._invalid_frames,
            "callback_errors": self._callback_errors,
            "device_errors": self._device_errors,
            "input_overflow": self._input_overflow,
            "raw_queue_overflow": self._raw_queue_overflow,
            "raw_queue_drops": self._raw_queue_drops,
            "sequence": self._sequence,
            "capture_generation": self._generation,
            "last_frame_at": self._last_frame_at,
            "consecutive_zero_or_near_zero_frames": self._consecutive_zero_frames,
            "signal_health": signal_health,
            "last_error": self._last_error,
            **self._queue.diagnostics,
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

    @staticmethod
    def _host_api_name(raw: Mapping[str, Any], hostapis: list[Any]) -> str:
        value = raw.get("hostapi", "")
        if isinstance(value, int) and 0 <= value < len(hostapis):
            host = hostapis[value]
            if isinstance(host, Mapping):
                return str(host.get("name", ""))
        return str(value or "")

    @classmethod
    def _device_record(
        cls, index: int, raw: Mapping[str, Any], hostapis: list[Any]
    ) -> dict[str, Any]:
        return {
            "index": index,
            "name": str(raw.get("name", "")).strip(),
            "host_api": cls._host_api_name(raw, hostapis),
            "host_api_index": raw.get("hostapi"),
            "max_input_channels": int(raw.get("max_input_channels", 0) or 0),
            "default_samplerate": float(raw.get("default_samplerate", 0) or 0),
        }

    @staticmethod
    def _same_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        return (
            str(left.get("name", "")).casefold() == str(right.get("name", "")).casefold()
            and str(left.get("host_api", "")).casefold()
            == str(right.get("host_api", "")).casefold()
            and int(left.get("max_input_channels", 0) or 0) > 0
            and int(right.get("max_input_channels", 0) or 0) > 0
        )

    def _resolve_device(self) -> dict[str, Any]:
        """Resolve a bounded candidate without silently choosing unrelated input."""
        if self._device_query is None:
            self._resolved_device = self._device
            self._device_info = {
                "index": self._device,
                "name": "",
                "host_api": "",
                "max_input_channels": 1,
                "default_samplerate": SAMPLE_RATE,
            }
            self._logical_identity = dict(self._device_info)
            return self._device_info

        snapshot = dict(self._device_query() or {})
        devices = list(snapshot.get("devices") or [])
        hostapis = list(snapshot.get("hostapis") or [])
        records = [self._device_record(index, raw, hostapis) for index, raw in enumerate(devices)]
        inputs = [record for record in records if record["max_input_channels"] > 0]
        if not inputs:
            raise AudioInputError("no input-capable microphone was enumerated")

        selector = self._device
        candidates: list[dict[str, Any]] = []
        if isinstance(selector, str) and selector.strip():
            wanted = selector.strip().casefold()
            matches = [record for record in inputs if wanted in record["name"].casefold()]
            if self._logical_identity:
                candidates = [
                    record for record in matches if self._same_identity(record, self._logical_identity)
                ]
            else:
                candidates = matches
        else:
            index = selector if selector is not None else snapshot.get("default_device")
            if isinstance(index, bool):
                index = None
            if isinstance(index, int):
                current = next((record for record in inputs if record["index"] == index), None)
                if self._logical_identity:
                    candidates = [
                        record for record in inputs if self._same_identity(record, self._logical_identity)
                    ]
                    if current is not None and self._same_identity(current, self._logical_identity):
                        candidates.insert(0, current)
                elif current is not None:
                    candidates = [current]

        if not candidates:
            if self._logical_identity:
                raise AudioInputError("intended microphone is unavailable or identity changed")
            raise AudioInputError("configured microphone was not found")

        unique: list[dict[str, Any]] = []
        seen: set[int] = set()
        for candidate in candidates:
            if candidate["index"] not in seen:
                unique.append(candidate)
                seen.add(candidate["index"])
        selected = unique[0]
        self._resolved_device = selected["index"]
        self._device_info = selected
        self._logical_identity = {
            "name": selected["name"],
            "host_api": selected["host_api"],
            "max_input_channels": selected["max_input_channels"],
        }
        return selected

    def _prepare_format(self, info: Mapping[str, Any]) -> None:
        native_rate = float(info.get("default_samplerate", 0) or 0)
        self._native_rate = int(round(native_rate)) if native_rate > 0 else SAMPLE_RATE
        self._capture_channels = max(1, min(int(info.get("max_input_channels", 1) or 1), 2))
        self._native_blocksize = max(1, int(round(self._native_rate * FRAME_SAMPLES / SAMPLE_RATE)))

    def start(self) -> dict[str, Any]:
        """Open exactly one native stream; repeated starts do not duplicate it."""
        with self._lock:
            if self._running:
                return {"ok": True, "started": False, "already_running": True}
            self._queue.uncancel()
            self._last_error = ""
            self._generation += 1
            generation = self._generation
            self._conversion_remainder = None
            try:
                info = self._resolve_device()
                self._prepare_format(info)
                if self._native_rate != SAMPLE_RATE or self._capture_channels != 1:
                    self._start_conversion_worker(generation)
                self._running = True
                callback = lambda indata, frames, time_info=None, status=None: self._on_callback(
                    indata, frames, time_info, status, generation=generation
                )
                self._stream = self._stream_factory(
                    samplerate=self._native_rate,
                    channels=self._capture_channels,
                    dtype="int16",
                    blocksize=self._native_blocksize,
                    device=self._resolved_device,
                    callback=callback,
                )
                self._stream.start()
            except Exception as exc:
                failed_stream = self._stream
                self._running = False
                self._stream = None
                self._generation += 1
                self._device_errors += 1
                self._last_error = str(exc)
                self._stop_conversion_worker()
                if failed_stream is not None:
                    try:
                        failed_stream.stop()
                    except Exception:
                        pass
                    try:
                        failed_stream.close()
                    except Exception:
                        pass
                return {"ok": False, "started": False, "error": self._last_error}
            return {
                "ok": True,
                "started": True,
                "already_running": False,
                "resolved_device": self._resolved_device,
                "native_samplerate": self._native_rate,
                "capture_samplerate": SAMPLE_RATE,
                "capture_channels": 1,
                "capture_generation": generation,
            }

    def stop(self) -> dict[str, Any]:
        """Invalidate callbacks, stop/close the stream, and stop conversion."""
        with self._lock:
            stream = self._stream
            self._generation += 1
            self._running = False
            self._stream = None
        self._stop_conversion_worker()
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

    def _start_conversion_worker(self, generation: int) -> None:
        self._raw_queue = thread_queue.Queue(maxsize=_RAW_QUEUE_MAXSIZE)
        self._conversion_stop = threading.Event()
        self._conversion_thread = threading.Thread(
            target=self._conversion_loop,
            args=(generation,),
            name="golden-audio-converter",
            daemon=True,
        )
        self._conversion_thread.start()

    def _stop_conversion_worker(self) -> None:
        stop_event = self._conversion_stop
        worker = self._conversion_thread
        if stop_event is not None:
            stop_event.set()
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        self._conversion_stop = None
        self._conversion_thread = None
        self._raw_queue = None
        self._conversion_remainder = None

    def _conversion_loop(self, generation: int) -> None:
        raw_queue = self._raw_queue
        stop_event = self._conversion_stop
        if raw_queue is None or stop_event is None:
            return
        while not stop_event.is_set():
            try:
                item_generation, raw = raw_queue.get(timeout=0.05)
            except thread_queue.Empty:
                continue
            if item_generation != generation or not self._is_current(generation):
                continue
            try:
                for frame in self._convert_to_internal_frames(raw):
                    if not self._is_current(generation):
                        break
                    self._deliver_frame(frame, generation)
            except Exception as exc:
                self._callback_errors += 1
                self._last_error = f"audio conversion failed: {exc}"

    def _convert_to_internal_frames(self, raw: bytes) -> list[bytes]:
        """Convert one native callback buffer into zero or more 16 kHz frames."""
        import numpy as np

        stride = self._capture_channels * 2
        if not raw or len(raw) % stride:
            self._invalid_frames += 1
            return []
        samples = np.frombuffer(raw, dtype=np.int16).reshape((-1, self._capture_channels))
        if self._capture_channels > 1:
            mono = np.rint(samples.astype(np.float32).mean(axis=1)).astype(np.int16)
        else:
            mono = samples[:, 0]

        if self._native_rate != SAMPLE_RATE:
            target_count = max(1, int(round(len(mono) * SAMPLE_RATE / self._native_rate)))
            try:
                from scipy.signal import resample_poly

                divisor = math.gcd(self._native_rate, SAMPLE_RATE)
                mono_float = resample_poly(
                    mono.astype(np.float32),
                    SAMPLE_RATE // divisor,
                    self._native_rate // divisor,
                )
                mono = np.rint(mono_float[:target_count]).astype(np.int16)
                if len(mono) < target_count:
                    mono = np.pad(mono, (0, target_count - len(mono)))
            except ImportError:
                source_x = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
                target_x = np.linspace(0.0, 1.0, num=target_count, endpoint=False)
                mono = np.rint(np.interp(target_x, source_x, mono)).astype(np.int16)

        if self._conversion_remainder is not None and len(self._conversion_remainder):
            mono = np.concatenate((self._conversion_remainder, mono))
        frames: list[bytes] = []
        while len(mono) >= FRAME_SAMPLES:
            frames.append(mono[:FRAME_SAMPLES].tobytes())
            mono = mono[FRAME_SAMPLES:]
        self._conversion_remainder = mono
        return frames

    def _is_current(self, generation: int) -> bool:
        return self._running and generation == self._generation

    def _on_callback(
        self,
        indata: Any,
        frames: int,
        time_info: Any = None,
        status: Any = None,
        *,
        generation: Optional[int] = None,
    ) -> None:
        del frames, time_info
        callback_generation = self._generation if generation is None else generation
        if not self._is_current(callback_generation):
            return
        try:
            raw = bytes(indata)
            if status:
                self._device_errors += 1
                self._last_error = str(status)
                if getattr(status, "input_overflow", False) or "overflow" in str(status).casefold():
                    self._input_overflow += 1
            if not raw:
                self._invalid_frames += 1
                return
            self._frames_received += 1
            self._sequence += 1
            self._last_frame_at = time.monotonic()
            self._consecutive_zero_frames = 0 if any(raw) else self._consecutive_zero_frames + 1
            if self._native_rate == SAMPLE_RATE and self._capture_channels == 1:
                self._deliver_frame(raw, callback_generation)
                return
            self._enqueue_raw(callback_generation, raw)
        except Exception as exc:
            self._callback_errors += 1
            self._last_error = str(exc)

    def _enqueue_raw(self, generation: int, raw: bytes) -> None:
        raw_queue = self._raw_queue
        if raw_queue is None or not self._is_current(generation):
            return
        item = (generation, raw)
        try:
            raw_queue.put_nowait(item)
        except thread_queue.Full:
            self._raw_queue_overflow += 1
            try:
                raw_queue.get_nowait()
                self._raw_queue_drops += 1
            except thread_queue.Empty:
                pass
            try:
                raw_queue.put_nowait(item)
            except thread_queue.Full:
                self._raw_queue_drops += 1

    def _deliver_frame(self, frame: bytes, generation: int) -> None:
        if not self._is_current(generation):
            return
        if len(frame) != FRAME_BYTES:
            self._invalid_frames += 1
            return
        self._canonical_frames_delivered += 1
        loop = self._loop
        if loop is None:
            self._enqueue_on_loop(frame, generation)
            return
        try:
            if loop.is_closed():
                self._callback_errors += 1
                return
            loop.call_soon_threadsafe(self._enqueue_on_loop, frame, generation)
        except RuntimeError as exc:
            self._callback_errors += 1
            self._last_error = str(exc)

    def _accept_frame(self, frame: bytes, generation: Optional[int] = None) -> None:
        """Compatibility entry point for deterministic fake providers/tests."""
        self._deliver_frame(bytes(frame), self._generation if generation is None else generation)

    def _enqueue_on_loop(self, frame: bytes, generation: int) -> None:
        if self._is_current(generation):
            self._queue.put_nowait(frame)


class FakeAudioInputProvider(AudioInputProvider):
    """Deterministic no-hardware provider for lifecycle and integration tests."""

    def __init__(
        self,
        *,
        frame_queue: Optional[AudioFrameQueue] = None,
        frames: Optional[list[bytes]] = None,
        device: Any = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        super().__init__(
            frame_queue=frame_queue,
            device=device,
            loop=loop,
            stream_factory=lambda **_: _FakeStream(),
        )
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
