"""Async audio frame queue with backpressure, cancel, and flush.

Frame format: 16 kHz mono int16, 480 samples = 960 bytes = 30 ms.

Adapted from ndunl075-jarvis MIT-licensed audio/pipeline.py frame queue topology.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Callable, Optional

from jarvis_core.realtime_voice.constants import (
    AUDIO_QUEUE_MAXSIZE,
    FRAME_BYTES,
    SAMPLE_RATE,
)

log = logging.getLogger(__name__)


class AudioFrameQueue:
    """Bounded async queue for audio frames with producer/consumer semantics.

    Usage:
        queue = AudioFrameQueue()

        # Producer (from mic thread via call_soon_threadsafe):
        queue.put_nowait(frame_bytes)

        # Consumer (async):
        frame = await queue.get()
        queue.task_done()

        # Cancel/flush:
        queue.cancel()
        queue.flush()
    """

    def __init__(self, maxsize: int = AUDIO_QUEUE_MAXSIZE) -> None:
        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=maxsize)
        self._cancelled = False
        self._maxsize = maxsize
        self._overflow_count = 0
        self._dropped_oldest = 0

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def empty(self) -> bool:
        return self._queue.empty()

    @property
    def diagnostics(self) -> dict[str, int]:
        """Return bounded-queue counters without exposing audio frames."""
        return {
            "overflow_count": self._overflow_count,
            "dropped_oldest": self._dropped_oldest,
        }

    def put_nowait(self, frame: bytes) -> None:
        """Put a frame into the queue. Drops oldest on overflow (backpressure)."""
        if self._cancelled:
            return
        if len(frame) != FRAME_BYTES:
            log.error(
                "queue: wrong frame size %d (expected %d)",
                len(frame), FRAME_BYTES,
            )
            return
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            self._overflow_count += 1
            try:
                self._queue.get_nowait()  # drop oldest
                self._dropped_oldest += 1
                self._queue.put_nowait(frame)
                log.warning("queue full; dropped oldest frame")
            except asyncio.QueueEmpty:
                pass

    async def get(self) -> Optional[bytes]:
        """Get next frame. Returns None if cancelled."""
        if self._cancelled:
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None if self._cancelled else b""

    def cancel(self) -> None:
        """Signal cancellation. Drains queue and wakes blocked consumers."""
        self._cancelled = True
        self.flush()

    def uncancel(self) -> None:
        """Reset cancellation state."""
        self._cancelled = False

    def flush(self) -> int:
        """Discard all queued frames. Returns count of frames dropped."""
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        return count


class UtteranceBuffer:
    """Accumulates frames for a single utterance (between SPEECH_STARTED and ENDPOINT).

    Thread-safe for single consumer.
    """

    def __init__(self) -> None:
        self._frames: list[bytes] = []
        self._started_at: float = 0.0
        self._ended_at: float = 0.0
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def sample_count(self) -> int:
        total_bytes = sum(len(f) for f in self._frames)
        return total_bytes // 2  # int16 = 2 bytes per sample

    @property
    def duration_ms(self) -> int:
        return int(self.sample_count * 1000 / SAMPLE_RATE)

    def start(self) -> None:
        """Begin a new utterance."""
        self._frames.clear()
        self._started_at = time.monotonic()
        self._ended_at = 0.0
        self._active = True

    def append(self, frame: bytes) -> None:
        """Add a frame to the current utterance."""
        if not self._active:
            return
        self._frames.append(frame)

    def end(self) -> None:
        """Mark utterance as complete."""
        self._ended_at = time.monotonic()
        self._active = False

    def clear(self) -> None:
        """Discard all data."""
        self._frames.clear()
        self._started_at = 0.0
        self._ended_at = 0.0
        self._active = False

    def get_audio_bytes(self) -> bytes:
        """Concatenate all frames into a single bytes object."""
        return b"".join(self._frames)

    @property
    def latency_ms(self) -> float:
        """Total latency from start to end in ms."""
        if self._started_at == 0:
            return 0.0
        end = self._ended_at if self._ended_at > 0 else time.monotonic()
        return (end - self._started_at) * 1000

    @property
    def silence_wait_ms(self) -> float:
        """Time from last audio to end in ms."""
        if self._ended_at == 0 or self._started_at == 0:
            return 0.0
        return (self._ended_at - self._started_at) * 1000
