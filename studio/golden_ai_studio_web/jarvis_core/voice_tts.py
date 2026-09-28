"""Provider-neutral TTS and audio-output contracts for VoiceService.

The module is deliberately backend-free.  It owns only lifecycle, PCM event
identity, cancellation and bounded delivery semantics.  A real TTS backend
can be adapted later without creating another Core, turn manager or output
owner.
"""

from __future__ import annotations

import re
import queue
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
        """Synthesize one complete text through the current turn boundary."""
        return self._synthesize_text(text)

    def synthesize_segment_current(self, text: str) -> TTSResult:
        """Synthesize one segment without replacing the active turn identity."""
        return self._synthesize_text(text)

    def _synthesize_text(self, text: str) -> TTSResult:
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


@dataclass(frozen=True)
class StreamingTextSegment:
    """One deterministic text unit ready for provider-neutral TTS."""

    text: str
    index: int
    is_final: bool = False


class StreamingTextSegmenter:
    """Bounded, provider-neutral segmentation for arbitrary text chunks.

    The segmenter is intentionally conservative: sentence punctuation wins,
    clause punctuation is used only for long enough text, and a forced split
    chooses whitespace before cutting a pathological long token.  It never
    treats transport chunk boundaries as semantic boundaries.
    """

    _ABBREVIATIONS = frozenset(
        {
            "sr.", "sra.", "dr.", "dra.", "prof.", "profa.",
            "gov.", "sta.", "sto.", "av.", "r.", "etc.", "ex.",
        }
    )
    _URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
    _MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

    def __init__(
        self,
        *,
        min_segment_chars: int = 12,
        max_pending_chars: int = 1_200,
        max_input_chunk_chars: int = 1_024,
    ) -> None:
        if min_segment_chars < 1:
            raise ValueError("min_segment_chars must be positive")
        if max_pending_chars < min_segment_chars:
            raise ValueError("max_pending_chars must be >= min_segment_chars")
        if max_input_chunk_chars < 1:
            raise ValueError("max_input_chunk_chars must be positive")
        self.min_segment_chars = int(min_segment_chars)
        self.max_pending_chars = int(max_pending_chars)
        self.max_input_chunk_chars = int(max_input_chunk_chars)
        self._buffer = ""
        self._next_index = 0
        self._finalized = False

    @property
    def pending_text(self) -> str:
        return self._buffer

    @property
    def pending_chars(self) -> int:
        return len(self._buffer)

    @property
    def segment_count(self) -> int:
        return self._next_index

    def reset(self) -> None:
        self._buffer = ""
        self._next_index = 0
        self._finalized = False

    def feed(self, text_chunk: str | None) -> list[StreamingTextSegment]:
        """Consume arbitrary text and emit only complete bounded segments."""
        if self._finalized or not text_chunk:
            return []
        text = str(text_chunk)
        emitted: list[StreamingTextSegment] = []
        for start in range(0, len(text), self.max_input_chunk_chars):
            self._buffer += text[start : start + self.max_input_chunk_chars]
            emitted.extend(self._drain_ready())
        return emitted

    def flush(self) -> StreamingTextSegment | None:
        """Flush meaningful pending text exactly once."""
        if self._finalized:
            return None
        self._finalized = True
        text = self._clean_for_speech(self._buffer)
        self._buffer = ""
        if not text:
            return None
        return self._make_segment(text, is_final=True)

    def _drain_ready(self) -> list[StreamingTextSegment]:
        emitted: list[StreamingTextSegment] = []
        while self._buffer:
            boundary = self._find_natural_boundary()
            if boundary is not None:
                raw = self._buffer[:boundary]
                cleaned = self._clean_for_speech(raw)
                self._buffer = self._buffer[boundary:].lstrip()
                if cleaned:
                    emitted.append(self._make_segment(cleaned))
                continue
            if len(self._buffer) <= self.max_pending_chars:
                break
            boundary = self._find_forced_boundary()
            raw = self._buffer[:boundary]
            self._buffer = self._buffer[boundary:].lstrip()
            cleaned = self._clean_for_speech(raw)
            if cleaned:
                emitted.append(self._make_segment(cleaned))
        return emitted

    def _find_natural_boundary(self) -> int | None:
        text = self._buffer
        url_spans = [match.span() for match in self._URL_RE.finditer(text)]
        for index, char in enumerate(text):
            if self._inside_span(index, url_spans):
                continue
            if char in ".!?…":
                end = index + 1
                while end < len(text) and text[end] in ".!?…":
                    end += 1
                if char == "." and self._period_is_numeric_or_incomplete(text, index, end):
                    continue
                if char == "." and self._is_abbreviation(text[:end]):
                    continue
                if end < len(text) and not text[end].isspace():
                    continue
                return end
            if char == "\n" and index + 1 < len(text) and text[index + 1] == "\n":
                return index + 2
            if char == ";" and index + 1 < len(text) and text[index + 1].isspace():
                if index + 1 >= self.min_segment_chars:
                    return index + 1
            if char == ":" and index + 1 < len(text) and text[index + 1].isspace():
                if index + 1 >= max(self.min_segment_chars * 3, 36):
                    return index + 1
        return None

    def _find_forced_boundary(self) -> int:
        limit = min(self.max_pending_chars, len(self._buffer))
        whitespace = max(
            self._buffer.rfind(" ", self.min_segment_chars, limit + 1),
            self._buffer.rfind("\n", self.min_segment_chars, limit + 1),
        )
        if whitespace >= self.min_segment_chars:
            return whitespace + 1
        return limit

    @classmethod
    def _period_is_numeric_or_incomplete(cls, text: str, index: int, end: int) -> bool:
        next_char = text[end] if end < len(text) else ""
        previous_char = text[index - 1] if index > 0 else ""
        if next_char.isdigit():
            return True
        if not next_char and previous_char.isdigit():
            return True
        return False

    @classmethod
    def _is_abbreviation(cls, text: str) -> bool:
        token = re.search(r"(?:^|\s)([^\s]+)$", text)
        return bool(token and token.group(1).casefold() in cls._ABBREVIATIONS)

    @staticmethod
    def _inside_span(index: int, spans: list[tuple[int, int]]) -> bool:
        return any(start <= index < end for start, end in spans)

    @classmethod
    def _clean_for_speech(cls, text: str) -> str:
        text = cls._MARKDOWN_LINK_RE.sub(r"\1", text)
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
        text = re.sub(r"(?m)^\s*[-*]\s+", "", text)
        text = text.replace("**", "").replace("__", "").replace("`", "")
        return re.sub(r"\s+", " ", text).strip()

    def _make_segment(self, text: str, *, is_final: bool = False) -> StreamingTextSegment:
        segment = StreamingTextSegment(text=text, index=self._next_index, is_final=is_final)
        self._next_index += 1
        return segment


@dataclass(frozen=True)
class StreamingTTSResult:
    """Bounded lifecycle result for one streaming TTS operation."""

    ok: bool
    submitted_segments: int = 0
    completed_segments: int = 0
    stale_rejections: int = 0
    cancelled: bool = False
    error: str = ""
    final_flushed: bool = False


@dataclass(frozen=True)
class _StreamingTTSJob:
    segment: StreamingTextSegment


class StreamingTTSOrchestrator:
    """Serialize bounded text segments through the existing audio pipeline.

    The work queue is intentionally serial. This makes playback ordering
    deterministic and avoids adding a second audio scheduler; backpressure is
    applied to the text producer when the bounded queue is full.
    """

    def __init__(
        self,
        pipeline: VoiceAudioPipeline,
        *,
        max_pending_segments: int = 4,
        segmenter: StreamingTextSegmenter | None = None,
    ) -> None:
        if max_pending_segments < 1:
            raise ValueError("max_pending_segments must be positive")
        self.pipeline = pipeline
        self.max_pending_segments = int(max_pending_segments)
        self.segmenter = segmenter or StreamingTextSegmenter()
        self._lock = threading.RLock()
        self._queue: queue.Queue[_StreamingTTSJob | None] = queue.Queue(
            maxsize=self.max_pending_segments
        )
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._identity: tuple[str, int, int] | None = None
        self._active = False
        self._finishing = False
        self._finished_result: StreamingTTSResult | None = None
        self._error = ""
        self._submitted_segments = 0
        self._completed_segments = 0
        self._stale_rejections = 0
        self._max_queue_depth = 0
        self._seen_chunk_ids: deque[str] = deque(maxlen=64)

    @property
    def identity(self) -> tuple[str, int, int] | None:
        with self._lock:
            return self._identity

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "finishing": self._finishing,
                "identity": self._identity,
                "queue_depth": self._queue.qsize(),
                "queue_maxsize": self.max_pending_segments,
                "max_queue_depth": self._max_queue_depth,
                "submitted_segments": self._submitted_segments,
                "completed_segments": self._completed_segments,
                "stale_rejections": self._stale_rejections,
                "worker_alive": bool(self._worker and self._worker.is_alive()),
                "pending_text_chars": self.segmenter.pending_chars,
                "error": self._error,
            }

    def start_stream(
        self, *, session_id: str, turn_id: int, generation: int
    ) -> tuple[str, int, int]:
        """Start one generation and invalidate any previous stream."""
        self.cancel("new_stream")
        identity = (str(session_id or ""), int(turn_id), int(generation))
        if not identity[0]:
            raise ValueError("session_id is required")
        with self._lock:
            self.pipeline.begin_turn(
                session_id=identity[0], turn_id=identity[1], generation=identity[2]
            )
            self.segmenter.reset()
            self._queue = queue.Queue(maxsize=self.max_pending_segments)
            self._stop_event.clear()
            self._identity = identity
            self._active = True
            self._finishing = False
            self._finished_result = None
            self._error = ""
            self._submitted_segments = 0
            self._completed_segments = 0
            self._stale_rejections = 0
            self._max_queue_depth = 0
            self._seen_chunk_ids.clear()
            work_queue = self._queue
            self._worker = threading.Thread(
                target=self._worker_loop,
                args=(work_queue,),
                name="jarvis-tts-stream",
                daemon=True,
            )
            worker = self._worker
        worker.start()
        return identity

    def feed_text(
        self,
        text_chunk: str | None,
        *,
        session_id: str | None = None,
        turn_id: int | None = None,
        generation: int | None = None,
        chunk_id: str | None = None,
    ) -> int:
        """Feed arbitrary response text with bounded producer backpressure."""
        with self._lock:
            if not self._active or self._finishing:
                return 0
            if not self._matches_identity_locked(session_id, turn_id, generation):
                self._stale_rejections += 1
                return 0
            if chunk_id is not None:
                normalized_chunk_id = str(chunk_id)
                if normalized_chunk_id in self._seen_chunk_ids:
                    return 0
                self._seen_chunk_ids.append(normalized_chunk_id)
            segments = self.segmenter.feed(text_chunk)
        submitted = 0
        for segment in segments:
            if not self._enqueue(_StreamingTTSJob(segment)):
                break
            submitted += 1
            with self._lock:
                self._submitted_segments += 1
        return submitted

    def finish_stream(
        self,
        *,
        session_id: str | None = None,
        turn_id: int | None = None,
        generation: int | None = None,
    ) -> StreamingTTSResult:
        """Flush trailing text once and wait for ordered synthesis."""
        with self._lock:
            if self._finished_result is not None:
                return self._finished_result
            if not self._active:
                return self._result_locked(cancelled=True, error="stream_not_active")
            if not self._matches_identity_locked(session_id, turn_id, generation):
                self._stale_rejections += 1
                return self._result_locked(error="stale_stream_identity")
            self._finishing = True
            trailing = self.segmenter.flush()
        if trailing is not None and not self._enqueue(_StreamingTTSJob(trailing)):
            return self._finish_worker(error="stream_cancelled")
        with self._lock:
            work_queue = self._queue
            worker = self._worker
        work_queue.join()
        self._stop_event.set()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        return self._finish_worker()

    def cancel(self, reason: str = "stream_cancelled") -> StreamingTTSResult:
        """Invalidate text, cancel synthesis, and flush obsolete queued work."""
        with self._lock:
            self._stop_event.set()
            self._active = False
            self._finishing = True
            worker = self._worker
            work_queue = self._queue
        self.pipeline.cancel(reason)
        self._drain_queue(work_queue)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        with self._lock:
            if self._finished_result is None and self._identity is not None:
                self._finished_result = self._result_locked(
                    cancelled=True, error=str(reason or "stream_cancelled")
                )
            return self._finished_result or StreamingTTSResult(
                ok=False, cancelled=True, error=str(reason or "stream_cancelled")
            )

    def close(self) -> StreamingTTSResult:
        return self.cancel("stream_closed")

    def _enqueue(self, job: _StreamingTTSJob) -> bool:
        while True:
            if self._stop_event.is_set():
                return False
            try:
                self._queue.put(job, timeout=0.05)
                with self._lock:
                    self._max_queue_depth = max(
                        self._max_queue_depth, self._queue.qsize()
                    )
                return True
            except queue.Full:
                continue

    def _worker_loop(self, work_queue: queue.Queue[_StreamingTTSJob | None]) -> None:
        while not self._stop_event.is_set():
            try:
                job = work_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if job is None:
                work_queue.task_done()
                return
            try:
                result = self.pipeline.synthesize_segment_current(job.segment.text)
                with self._lock:
                    if result.cancelled:
                        self._error = "tts_cancelled"
                        self._active = False
                        self._stop_event.set()
                        self._drain_queue(work_queue)
                        return
                    if not result.ok:
                        self._error = result.error or "tts_provider_failed"
                        self._stop_event.set()
                        self._active = False
                    elif result.dropped_chunks:
                        self._error = "tts_output_rejected"
                        self._stop_event.set()
                        self._active = False
                    else:
                        self._completed_segments += 1
                if self._error:
                    self.pipeline.cancel(self._error)
                    self._drain_queue(work_queue)
                    return
            except Exception as exc:
                with self._lock:
                    self._error = str(exc)[:240]
                    self._active = False
                    self._stop_event.set()
                self.pipeline.cancel("tts_worker_failed")
                self._drain_queue(work_queue)
                return
            finally:
                work_queue.task_done()

    @staticmethod
    def _drain_queue(work_queue: queue.Queue[_StreamingTTSJob | None]) -> None:
        while True:
            try:
                work_queue.get_nowait()
            except queue.Empty:
                return
            else:
                work_queue.task_done()

    def _finish_worker(self, *, error: str = "") -> StreamingTTSResult:
        with self._lock:
            if error and not self._error:
                self._error = error
            self._active = False
            self._finishing = True
            result = self._result_locked(
                cancelled=error in {"stream_cancelled", "stream_closed"}
                or self._error == "tts_cancelled",
                error=self._error,
                final_flushed=True,
            )
            self._finished_result = result
            return result

    def _result_locked(
        self,
        *,
        cancelled: bool = False,
        error: str = "",
        final_flushed: bool = False,
    ) -> StreamingTTSResult:
        return StreamingTTSResult(
            ok=not error and not cancelled,
            submitted_segments=self._submitted_segments,
            completed_segments=self._completed_segments,
            stale_rejections=self._stale_rejections,
            cancelled=cancelled,
            error=error,
            final_flushed=final_flushed,
        )

    def _matches_identity_locked(
        self,
        session_id: str | None,
        turn_id: int | None,
        generation: int | None,
    ) -> bool:
        identity = self._identity
        if identity is None:
            return False
        return (
            session_id is None or str(session_id) == identity[0]
        ) and (
            turn_id is None or int(turn_id) == identity[1]
        ) and (
            generation is None or int(generation) == identity[2]
        )


__all__ = [
    "AudioOutputProvider",
    "FakeAudioOutputProvider",
    "FakeTextToSpeechProvider",
    "PcmAudioChunk",
    "StreamingTextSegment",
    "StreamingTextSegmenter",
    "StreamingTTSOrchestrator",
    "StreamingTTSResult",
    "TTSResult",
    "TextToSpeechProvider",
    "VoiceAudioPipeline",
]
