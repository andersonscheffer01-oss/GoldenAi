"""Provider-neutral TTS and audio-output contracts for VoiceService.

The module is deliberately backend-free.  It owns only lifecycle, PCM event
identity, cancellation and bounded delivery semantics.  A real TTS backend
can be adapted later without creating another Core, turn manager or output
owner.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Iterator, Mapping, Protocol, runtime_checkable

from .voice_foundation import VoiceCancellation, VoiceCancelledError


@dataclass(frozen=True)
class PcmAudioChunk:
    """One backend-neutral PCM event crossing the TTS/output boundary."""

    pcm: bytes
    sample_rate: int
    channels: int = 1
    sample_format: str = "s16le"
    sequence: int = 0
    session_id: str = ""
    turn_id: int = 0
    generation: int = 0
    is_final: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        pcm = bytes(self.pcm or b"")
        if not pcm:
            raise ValueError("PCM chunk cannot be empty")
        if int(self.sample_rate) <= 0:
            raise ValueError("sample_rate must be positive")
        if int(self.channels) <= 0:
            raise ValueError("channels must be positive")
        if self.sample_format != "s16le":
            raise ValueError("only s16le PCM is supported by this boundary")
        object.__setattr__(self, "pcm", pcm)
        object.__setattr__(self, "sample_rate", int(self.sample_rate))
        object.__setattr__(self, "channels", int(self.channels))
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "session_id", str(self.session_id or ""))
        object.__setattr__(self, "turn_id", int(self.turn_id))
        object.__setattr__(self, "generation", int(self.generation))
        object.__setattr__(self, "is_final", bool(self.is_final))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata or {})))

    @property
    def identity(self) -> tuple[str, int, int]:
        """Session/turn/generation identity used by the stale-output gate."""
        return self.session_id, self.turn_id, self.generation


@dataclass(frozen=True)
class TTSResult:
    """Bounded result of one provider-to-output synthesis attempt."""

    ok: bool
    accepted_chunks: int = 0
    dropped_chunks: int = 0
    final_emitted: bool = False
    cancelled: bool = False
    error: str = ""
    duration_ms: int = 0


@runtime_checkable
class TextToSpeechProvider(Protocol):
    """Provider-neutral lifecycle and streaming contract."""

    def warm(self) -> None:
        ...

    def synthesize(
        self,
        text: str,
        *,
        cancellation: VoiceCancellation,
        session_id: str,
        turn_id: int,
        generation: int,
    ) -> Iterable[PcmAudioChunk]:
        ...

    def stream(
        self,
        text: str,
        *,
        cancellation: VoiceCancellation,
        session_id: str,
        turn_id: int,
        generation: int,
    ) -> Iterator[PcmAudioChunk]:
        ...

    def cancel(self) -> None:
        ...

    def release(self) -> None:
        ...


@runtime_checkable
class AudioOutputProvider(Protocol):
    """Bounded PCM sink contract; implementations own the hardware sink."""

    def warm(self) -> None:
        ...

    def enqueue(self, chunk: PcmAudioChunk) -> bool:
        ...

    def cancel(self, reason: str = "cancelled") -> None:
        ...

    def flush(self) -> int:
        ...

    def release(self) -> None:
        ...


class FakeTextToSpeechProvider:
    """Deterministic, hardware/network/model-free TTS provider."""

    def __init__(
        self,
        *,
        sample_rate: int = 22050,
        chunk_delay: float = 0.0,
        failure: BaseException | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.chunk_delay = max(0.0, float(chunk_delay))
        self.failure = failure
        self.calls: list[dict[str, Any]] = []
        self.warm_count = 0
        self.cancel_count = 0
        self.release_count = 0
        self.started = threading.Event()
        self._cancel_event = threading.Event()
        self._lock = threading.RLock()
        self._warmed = False
        self._released = False

    @property
    def released(self) -> bool:
        with self._lock:
            return self._released

    def warm(self) -> None:
        with self._lock:
            if self._released:
                raise RuntimeError("fake TTS provider is released")
            self._cancel_event.clear()
            self._warmed = True
            self.warm_count += 1

    def _check(self, cancellation: VoiceCancellation) -> None:
        cancellation.throw_if_cancelled()
        if self._cancel_event.is_set():
            raise VoiceCancelledError("provider_cancelled")
        with self._lock:
            if self._released:
                raise RuntimeError("fake TTS provider is released")
            if not self._warmed:
                raise RuntimeError("fake TTS provider is not warm")

    def stream(
        self,
        text: str,
        *,
        cancellation: VoiceCancellation,
        session_id: str,
        turn_id: int,
        generation: int,
    ) -> Iterator[PcmAudioChunk]:
        self._check(cancellation)
        if self.failure is not None:
            raise self.failure
        text = str(text or "").strip()
        if not text:
            return
        parts = [part.strip() for part in re.split(r"(?<=[.!?;:])\s+", text) if part.strip()]
        if not parts:
            parts = [text]
        self.calls.append({
            "text": text,
            "session_id": session_id,
            "turn_id": turn_id,
            "generation": generation,
            "parts": len(parts),
        })
        self.started.set()
        for sequence, part in enumerate(parts):
            self._check(cancellation)
            if self.chunk_delay:
                if cancellation.wait(self.chunk_delay) or self._cancel_event.is_set():
                    raise VoiceCancelledError("provider_cancelled")
            pcm = _deterministic_pcm(part, sample_rate=self.sample_rate)
            yield PcmAudioChunk(
                pcm=pcm,
                sample_rate=self.sample_rate,
                sequence=sequence,
                session_id=session_id,
                turn_id=turn_id,
                generation=generation,
                is_final=sequence == len(parts) - 1,
                metadata={"provider": "fake", "text": part},
            )

    def synthesize(
        self,
        text: str,
        *,
        cancellation: VoiceCancellation,
        session_id: str,
        turn_id: int,
        generation: int,
    ) -> list[PcmAudioChunk]:
        return list(self.stream(
            text,
            cancellation=cancellation,
            session_id=session_id,
            turn_id=turn_id,
            generation=generation,
        ))

    def cancel(self) -> None:
        self.cancel_count += 1
        self._cancel_event.set()

    def release(self) -> None:
        self.release_count += 1
        self._cancel_event.set()
        with self._lock:
            self._released = True
            self._warmed = False


def _deterministic_pcm(text: str, *, sample_rate: int) -> bytes:
    """Create stable signed-16-bit PCM without audio hardware or libraries."""
    import math
    import struct

    duration = max(0.02, min(0.12, 0.02 + len(text) / 1800.0))
    sample_count = max(1, int(sample_rate * duration))
    seed = sum((index + 1) * ord(char) for index, char in enumerate(text))
    frequency = 180 + (seed % 140)
    amplitude = 900
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate)))
        for index in range(sample_count)
    )


class FakeAudioOutputProvider:
    """Bounded in-memory PCM sink for deterministic tests."""

    def __init__(self, *, maxsize: int = 8, overflow_policy: str = "drop_oldest") -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if overflow_policy not in {"drop_oldest", "reject"}:
            raise ValueError("overflow_policy must be drop_oldest or reject")
        self.maxsize = int(maxsize)
        self.overflow_policy = overflow_policy
        self._queue: deque[PcmAudioChunk] = deque()
        self._lock = threading.RLock()
        self._cancelled = False
        self._released = False
        self.accepted: list[PcmAudioChunk] = []
        self.dropped = 0
        self.rejected = 0

    @property
    def queued(self) -> tuple[PcmAudioChunk, ...]:
        with self._lock:
            return tuple(self._queue)

    @property
    def qsize(self) -> int:
        with self._lock:
            return len(self._queue)

    def warm(self) -> None:
        with self._lock:
            if self._released:
                raise RuntimeError("fake audio output is released")
            self._cancelled = False

    def enqueue(self, chunk: PcmAudioChunk) -> bool:
        with self._lock:
            if self._cancelled or self._released:
                self.rejected += 1
                return False
            if len(self._queue) >= self.maxsize:
                if self.overflow_policy == "reject":
                    self.rejected += 1
                    return False
                self._queue.popleft()
                self.dropped += 1
            self._queue.append(chunk)
            self.accepted.append(chunk)
            return True

    def cancel(self, reason: str = "cancelled") -> None:
        del reason
        with self._lock:
            self._cancelled = True
        self.flush()

    def flush(self) -> int:
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    def release(self) -> None:
        with self._lock:
            self._released = True
            self._cancelled = True
            self._queue.clear()


class VoiceAudioPipeline:
    """Single VoiceService-owned gate from TTS events to audio output."""

    def __init__(self, provider: TextToSpeechProvider, output: AudioOutputProvider) -> None:
        self.provider = provider
        self.output = output
        self._lock = threading.RLock()
        self._identity: tuple[str, int, int] | None = None
        self._cancellation: VoiceCancellation | None = None
        self._closed = False

    @property
    def identity(self) -> tuple[str, int, int] | None:
        with self._lock:
            return self._identity

    def warm(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("voice audio pipeline is closed")
        self.provider.warm()
        self.output.warm()

    def begin_turn(self, *, session_id: str, turn_id: int, generation: int) -> tuple[str, int, int]:
        with self._lock:
            if self._closed:
                raise RuntimeError("voice audio pipeline is closed")
            previous = self._cancellation
            if previous is not None:
                previous.cancel("new_turn")
            self.provider.cancel()
            self.output.cancel("new_turn")
            self._identity = (str(session_id or ""), int(turn_id), int(generation))
            self._cancellation = VoiceCancellation()
        self.warm()
        return self._identity

    def accept_chunk(self, chunk: PcmAudioChunk) -> bool:
        with self._lock:
            identity = self._identity
            cancellation = self._cancellation
            if identity is None or cancellation is None:
                return False
            if cancellation.is_cancelled or chunk.identity != identity:
                return False
        return self.output.enqueue(chunk)

    def synthesize_current(self, text: str) -> TTSResult:
        started = time.perf_counter()
        with self._lock:
            if self._closed:
                return TTSResult(ok=False, error="pipeline_closed")
            identity = self._identity
            cancellation = self._cancellation
        if identity is None or cancellation is None:
            return TTSResult(ok=False, error="no_active_turn")
        accepted = 0
        dropped = 0
        final_emitted = False
        try:
            chunks = self.provider.stream(
                text,
                cancellation=cancellation,
                session_id=identity[0],
                turn_id=identity[1],
                generation=identity[2],
            )
            for chunk in chunks:
                if self.accept_chunk(chunk):
                    accepted += 1
                    final_emitted = final_emitted or chunk.is_final
                else:
                    dropped += 1
            cancellation.throw_if_cancelled()
            return TTSResult(
                ok=True,
                accepted_chunks=accepted,
                dropped_chunks=dropped,
                final_emitted=final_emitted,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except VoiceCancelledError as exc:
            return TTSResult(
                ok=False,
                accepted_chunks=accepted,
                dropped_chunks=dropped,
                cancelled=True,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return TTSResult(
                ok=False,
                accepted_chunks=accepted,
                dropped_chunks=dropped,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    def speak(
        self,
        text: str,
        *,
        session_id: str,
        turn_id: int,
        generation: int,
    ) -> TTSResult:
        self.begin_turn(session_id=session_id, turn_id=turn_id, generation=generation)
        return self.synthesize_current(text)

    def cancel(self, reason: str = "cancelled") -> None:
        with self._lock:
            cancellation = self._cancellation
        if cancellation is not None:
            cancellation.cancel(reason)
        self.provider.cancel()
        self.output.cancel(reason)

    def release(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            cancellation = self._cancellation
        if cancellation is not None:
            cancellation.cancel("pipeline_release")
        self.provider.cancel()
        self.output.cancel("pipeline_release")
        self.provider.release()
        self.output.release()


__all__ = [
    "AudioOutputProvider",
    "FakeAudioOutputProvider",
    "FakeTextToSpeechProvider",
    "PcmAudioChunk",
    "TTSResult",
    "TextToSpeechProvider",
    "VoiceAudioPipeline",
]
