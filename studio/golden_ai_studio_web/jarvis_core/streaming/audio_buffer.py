"""Streaming Audio Buffer — manages bounded audio playback.

Provides:
- Bounded buffer with backpressure
- Ordered playback
- Cancel support
- Flush support
- No duplication
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Buffer limits
MAX_BUFFER_CHUNKS = 10  # Maximum chunks in buffer
MAX_BUFFER_BYTES = 256 * 1024  # 256KB total buffer


@dataclass
class BufferedAudio:
    """Audio chunk in the buffer."""
    index: int
    audio_path: str
    duration_ms: float
    is_final: bool
    added_at: float


class StreamingAudioBuffer:
    """Bounded audio buffer for streaming playback.

    Features:
    - Backpressure when buffer is full
    - Ordered playback (chunks played in index order)
    - Cancel clears buffer and stops playback
    - Flush sends remaining chunks
    - No duplication (each chunk played exactly once)
    """

    def __init__(self, player, cancel_event: Optional[asyncio.Event] = None):
        """
        Args:
            player: AudioPlayer instance for playback
            cancel_event: Event to signal cancellation
        """
        self._player = player
        self._cancel = cancel_event or asyncio.Event()
        self._buffer: deque[BufferedAudio] = deque()
        self._next_index = 0
        self._total_bytes = 0
        self._playback_task: Optional[asyncio.Task] = None
        self._playing = False
        self._playback_started = False
        self._playback_start_time: Optional[float] = None

    async def add_audio(
        self,
        audio_path: str,
        index: int,
        duration_ms: float,
        is_final: bool = False,
    ) -> bool:
        """Add audio to the buffer.

        Returns:
            True if added, False if buffer full or cancelled
        """
        if self._cancel.is_set():
            return False

        # Backpressure: wait if buffer is full
        while len(self._buffer) >= MAX_BUFFER_CHUNKS and not self._cancel.is_set():
            log.debug("Buffer full, waiting for playback to consume")
            await asyncio.sleep(0.01)

        if self._cancel.is_set():
            return False

        # Add to buffer
        buffered = BufferedAudio(
            index=index,
            audio_path=audio_path,
            duration_ms=duration_ms,
            is_final=is_final,
            added_at=time.perf_counter(),
        )
        self._buffer.append(buffered)
        self._total_bytes += os.path.getsize(audio_path) if os.path.exists(audio_path) else 0

        # Start playback if not already running
        if not self._playing and not self._playback_task:
            self._playback_task = asyncio.create_task(self._playback_loop())

        return True

    async def _playback_loop(self):
        """Play chunks in order as they become available."""
        self._playing = True

        try:
            while not self._cancel.is_set():
                # Check if next chunk is available
                if self._buffer and self._buffer[0].index == self._next_index:
                    chunk = self._buffer.popleft()
                    self._total_bytes -= os.path.getsize(chunk.audio_path) if os.path.exists(chunk.audio_path) else 0

                    # Play the chunk
                    if not self._cancel.is_set():
                        if not self._playback_started:
                            self._playback_start_time = time.perf_counter()
                            self._playback_started = True

                        await self._player.play(chunk.audio_path)

                        # Cleanup temp file
                        try:
                            os.unlink(chunk.audio_path)
                        except OSError:
                            pass

                    self._next_index += 1

                    # If this was the final chunk, we're done
                    if chunk.is_final:
                        break
                else:
                    # Wait for next chunk
                    await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass
        finally:
            self._playing = False
            self._playback_task = None

    async def flush(self):
        """Flush remaining chunks in the buffer."""
        if self._cancel.is_set():
            self._cleanup()
            return

        # Wait for playback to finish
        if self._playback_task:
            try:
                await asyncio.wait_for(self._playback_task, timeout=30)
            except asyncio.TimeoutError:
                log.warning("Flush timed out")
                self._cancel.set()

        self._cleanup()

    def cancel(self):
        """Cancel playback and clear buffer."""
        self._cancel.set()
        if self._playback_task:
            self._playback_task.cancel()
        self._cleanup()

    def _cleanup(self):
        """Remove all temp files from buffer."""
        for chunk in self._buffer:
            try:
                os.unlink(chunk.audio_path)
            except OSError:
                pass
        self._buffer.clear()
        self._total_bytes = 0

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    @property
    def next_index(self) -> int:
        return self._next_index

    @property
    def playback_start_ms(self) -> Optional[float]:
        """Get playback start time in ms (relative to some reference)."""
        if self._playback_start_time is None:
            return None
        return self._playback_start_time * 1000
