"""True Edge TTS Audio Streaming — yields audio bytes as they arrive.

Instead of waiting for complete sentence synthesis, this module streams
audio bytes directly from Edge TTS's stream() API.

Key insight: Edge TTS yields MP3 frames that can be played immediately.
No need to wait for complete sentences.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

import edge_tts

log = logging.getLogger(__name__)

# Edge TTS config (same as tts_pipeline.py for consistency)
TTS_VOICE = "pt-BR-FranciscaNeural"
TTS_RATE = "+4%"
TTS_PITCH = "-2Hz"

# Minimum audio bytes before starting playback (prevents underrun)
MIN_BUFFER_BYTES = 2048  # ~128ms at 16KB/s MP3

# Maximum buffer size (prevents memory issues)
MAX_BUFFER_BYTES = 64 * 1024  # 64KB


@dataclass
class AudioStreamChunk:
    """A chunk of audio data from the stream."""
    index: int
    text: str
    audio_bytes: bytes
    is_final: bool
    is_first: bool  # True if this is the first chunk for this sentence
    tts_start_ms: float
    tts_end_ms: float


async def stream_synthesize(
    text: str,
    chunk_index: int,
    is_final: bool = False,
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[AudioStreamChunk]:
    """Stream audio bytes from Edge TTS as they arrive.

    Yields AudioStreamChunk objects with partial audio data.
    Each chunk can be written to a file and played immediately.

    Args:
        text: Text to synthesize
        chunk_index: Index of this sentence chunk
        is_final: True if this is the last chunk
        cancel_event: Event to signal cancellation

    Yields:
        AudioStreamChunk with audio bytes
    """
    tts_start = time.perf_counter()

    try:
        communicate = edge_tts.Communicate(
            text,
            TTS_VOICE,
            rate=TTS_RATE,
            pitch=TTS_PITCH,
        )

        audio_buffer = bytearray()
        is_first_chunk = True

        async for chunk in communicate.stream():
            if cancel_event and cancel_event.is_set():
                return

            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])

                # Yield when we have enough data or this is a sentence boundary
                if len(audio_buffer) >= MIN_BUFFER_BYTES or is_first_chunk:
                    tts_end = time.perf_counter()
                    yield AudioStreamChunk(
                        index=chunk_index,
                        text=text,
                        audio_bytes=bytes(audio_buffer),
                        is_final=is_final,
                        is_first=is_first_chunk,
                        tts_start_ms=tts_start * 1000,
                        tts_end_ms=tts_end * 1000,
                    )
                    audio_buffer.clear()
                    is_first_chunk = False

        # Yield any remaining audio
        if audio_buffer:
            tts_end = time.perf_counter()
            yield AudioStreamChunk(
                index=chunk_index,
                text=text,
                audio_bytes=bytes(audio_buffer),
                is_final=is_final,
                is_first=False,
                tts_start_ms=tts_start * 1000,
                tts_end_ms=tts_end * 1000,
            )

    except Exception as e:
        log.warning("TTS streaming failed for chunk %d: %s", chunk_index, e)
        return


async def stream_to_file(
    text: str,
    chunk_index: int,
    output_path: str,
    is_final: bool = False,
    cancel_event: Optional[asyncio.Event] = None,
) -> Optional[Path]:
    """Stream audio to a file, writing bytes as they arrive.

    Returns the path to the complete MP3 file, or None if cancelled/failed.
    """
    tts_start = time.perf_counter()

    try:
        communicate = edge_tts.Communicate(
            text,
            TTS_VOICE,
            rate=TTS_RATE,
            pitch=TTS_PITCH,
        )

        audio_chunks = []
        async for chunk in communicate.stream():
            if cancel_event and cancel_event.is_set():
                # Cleanup
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
                return None

            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        # Write complete file
        audio_bytes = b"".join(audio_chunks)
        if not audio_bytes:
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return None

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        return Path(output_path)

    except Exception as e:
        log.warning("TTS streaming failed for chunk %d: %s", chunk_index, e)
        return None


def create_streaming_audio_chunk(
    audio_bytes: bytes,
    index: int,
    text: str,
    is_final: bool,
    tts_start_ms: float,
    tts_end_ms: float,
) -> "AudioChunk":
    """Create an AudioChunk from streaming audio bytes.

    This creates a temporary file and returns an AudioChunk
    compatible with the existing playback system.
    """
    from jarvis_core.streaming.tts_pipeline import AudioChunk

    # Write to temp file
    fd, audio_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    # Estimate duration from file size (MP3 ~16KB/s at our settings)
    duration_ms = len(audio_bytes) / 16.0

    return AudioChunk(
        index=index,
        text=text,
        audio_path=audio_path,
        duration_ms=duration_ms,
        is_final=is_final,
        tts_start_ms=tts_start_ms,
        tts_end_ms=tts_end_ms,
    )
