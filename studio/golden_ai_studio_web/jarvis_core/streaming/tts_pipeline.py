"""Streaming TTS pipeline — sentence-level pipelining.

Each sentence chunk is synthesized independently via Edge TTS streaming.
Audio chunks are collected per sentence and played sequentially.

Supports threading.Event for cross-thread cancellation (barge-in).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional, Union

import edge_tts

from jarvis_core.streaming import TTS_QUEUE_MAXSIZE

log = logging.getLogger(__name__)

# Edge TTS config
TTS_VOICE = "pt-BR-FranciscaNeural"
TTS_RATE = "+4%"
TTS_PITCH = "-2Hz"


@dataclass
class AudioChunk:
    index: int
    text: str
    audio_path: Optional[str]
    duration_ms: float
    is_final: bool
    tts_start_ms: float = 0
    tts_end_ms: float = 0


def _is_cancelled(cancel_event: Optional[Union[asyncio.Event, "threading.Event"]]) -> bool:
    """Check if cancel event is set. Works with both asyncio.Event and threading.Event."""
    if cancel_event is None:
        return False
    return cancel_event.is_set()


async def synthesize_sentence(
    text: str,
    chunk_index: int,
    is_final: bool = False,
    cancel_event: Optional[Union[asyncio.Event, "threading.Event"]] = None,
) -> Optional[AudioChunk]:
    """Synthesize one sentence via Edge TTS streaming.

    Returns AudioChunk with path to temp MP3 file.
    If cancelled, returns None.

    Supports both asyncio.Event and threading.Event for cross-thread cancellation.
    """
    tts_start = time.perf_counter()

    try:
        communicate = edge_tts.Communicate(
            text,
            TTS_VOICE,
            rate=TTS_RATE,
            pitch=TTS_PITCH,
        )

        fd, audio_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        audio_chunks = []
        async for chunk in communicate.stream():
            if _is_cancelled(cancel_event):
                # Cleanup temp file
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass
                return None

            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        # Write collected audio to temp file
        audio_bytes = b"".join(audio_chunks)
        if not audio_bytes:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            return None

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        tts_end = time.perf_counter()

        # Estimate duration from file size (MP3 ~16KB/s at our settings)
        duration_ms = len(audio_bytes) / 16.0  # rough estimate

        return AudioChunk(
            index=chunk_index,
            text=text,
            audio_path=audio_path,
            duration_ms=duration_ms,
            is_final=is_final,
            tts_start_ms=tts_start * 1000,
            tts_end_ms=tts_end * 1000,
        )

    except Exception as e:
        log.warning("TTS synthesis failed for chunk %d: %s", chunk_index, e)
        return None


class TTSPipeline:
    """Manages sentence-level TTS synthesis with ordering.

    Chunks are synthesized in order. If chunk N is still synthesizing
    when chunk N-1 finishes, chunk N waits. No overlap.

    Supports threading.Event for cross-thread cancellation (barge-in).
    """

    def __init__(self, cancel_event: Optional[Union[asyncio.Event, "threading.Event"]] = None):
        self._cancel = cancel_event or asyncio.Event()
        self._pending: dict[int, asyncio.Task] = {}
        self._results: dict[int, AudioChunk] = {}
        self._next_index = 0

    async def submit(self, text: str, index: int, is_final: bool = False) -> None:
        """Submit a sentence for synthesis. Starts immediately."""
        task = asyncio.create_task(
            synthesize_sentence(text, index, is_final, self._cancel)
        )
        self._pending[index] = task

    async def next_ready(self) -> Optional[AudioChunk]:
        """Wait for the next in-order chunk to be ready.

        Returns the next AudioChunk in sequence, or None if cancelled.
        """
        if _is_cancelled(self._cancel):
            return None

        # Wait for the next expected index
        target = self._next_index
        if target in self._pending:
            try:
                result = await asyncio.wait_for(self._pending[target], timeout=30)
                del self._pending[target]
                if result is None:
                    # Cancelled or failed — skip this chunk
                    self._next_index += 1
                    return await self.next_ready()
                self._next_index += 1
                return result
            except asyncio.TimeoutError:
                log.warning("TTS chunk %d timed out", target)
                del self._pending[target]
                self._next_index += 1
                return await self.next_ready()
            except asyncio.CancelledError:
                return None

        # No task for this index yet — wait briefly
        try:
            await asyncio.sleep(0.05)
            return await self.next_ready()
        except asyncio.CancelledError:
            return None

    def cancel(self) -> None:
        """Cancel all pending synthesis."""
        if hasattr(self._cancel, 'set'):
            self._cancel.set()
        for task in self._pending.values():
            task.cancel()
        self._pending.clear()

    def cleanup(self) -> None:
        """Remove temp files for all completed results."""
        for chunk in self._results.values():
            if chunk.audio_path:
                try:
                    os.unlink(chunk.audio_path)
                except OSError:
                    pass
        self._results.clear()

    async def synthesize_and_get(self, text: str, index: int, is_final: bool = False) -> Optional[AudioChunk]:
        """Synthesize a sentence and return the audio chunk immediately.

        Unlike submit+next_ready, this doesn't wait for ordering.
        Used for immediate playback during streaming.
        """
        if _is_cancelled(self._cancel):
            return None
        return await synthesize_sentence(text, index, is_final, self._cancel)

    @property
    def pending_count(self) -> int:
        return len(self._pending)
