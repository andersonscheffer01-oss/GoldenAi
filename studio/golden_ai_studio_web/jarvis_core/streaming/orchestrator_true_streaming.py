"""True Streaming Orchestrator — LLM → SentenceChunker → Edge TTS Stream → Playback.

Uses true audio streaming instead of sentence-level pipelining.
Audio bytes flow from Edge TTS to playback as they arrive.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from jarvis_core.streaming import is_streaming_enabled
from jarvis_core.streaming.sentence_chunker import Chunk, SentenceChunker
from jarvis_core.streaming.tts_pipeline import AudioChunk, TTSPipeline
from jarvis_core.streaming.audio_player import AudioPlayer
from jarvis_core.streaming.provider_stream import (
    stream_groq,
    stream_openrouter,
    stream_ollama,
)
from jarvis_core.streaming.turn_clock import TurnClock
from jarvis_core.streaming.true_streaming import (
    stream_synthesize,
    create_streaming_audio_chunk,
    MIN_BUFFER_BYTES,
)

log = logging.getLogger(__name__)


@dataclass
class TrueStreamingMetrics:
    """Metrics using unified TurnClock."""
    clock: TurnClock = field(default_factory=TurnClock)
    chunks_emitted: int = 0
    chunks_played: int = 0
    tool_call_detected: bool = False
    tool_call_text: str = ""


class ToolCallDetector:
    """Detects if accumulated tokens form a tool call vs prose response.

    Tool calls are JSON objects: {"tool": "...", "args": {...}}
    Prose responses are plain text.

    Strategy:
    - If FIRST token starts with '{' → tool call (stop immediately)
    - If prose detected first → continue, but watch for JSON transition
    - If JSON-like pattern appears after prose → signal stop
    """

    def __init__(self):
        self._buffer = ""
        self._token_count = 0
        self._phase = "unknown"  # "unknown", "prose", "tool_call"
        self._last_token = ""

    def feed(self, token: str) -> Optional[str]:
        """Feed a token and return detection result.

        Returns:
            "tool_call" if tool call detected (stop speaking)
            "prose" if prose detected (continue speaking)
            None if still undetermined
        """
        if self._phase == "tool_call":
            return "tool_call"

        self._buffer += token
        self._token_count += 1
        self._last_token = token
        stripped = self._buffer.strip()

        # FAST PATH: First token starts with '{' → tool call
        if self._token_count == 1 and stripped.startswith("{"):
            if '"tool"' in stripped or '"response"' in stripped or '"steps"' in stripped:
                self._phase = "tool_call"
                return "tool_call"
            # Even just '{' at start is suspicious - wait for more
            return None

        # Check if LATEST token looks like tool call start
        token_stripped = token.strip()
        if token_stripped.startswith('{"') or token_stripped.startswith('{ "'):
            # JSON object start after prose → tool call transition
            self._phase = "tool_call"
            return "tool_call"

        # Check if buffer now contains JSON tool call pattern
        if '"tool":' in stripped or '"response":' in stripped or '"steps":' in stripped:
            # If we've seen prose, this is a transition
            if self._phase == "prose":
                self._phase = "tool_call"
                return "tool_call"
            # If first token was '{', this is tool call
            if stripped.startswith("{"):
                self._phase = "tool_call"
                return "tool_call"

        # Check if current buffer looks like prose
        if stripped and (stripped[0].isalpha() or stripped[0].isdigit()):
            if self._phase == "unknown":
                self._phase = "prose"
            return "prose"

        return None

    def get_buffer(self) -> str:
        return self._buffer

    def is_tool_call(self) -> bool:
        return self._phase == "tool_call"

    def is_prose(self) -> bool:
        return self._phase == "prose"

    def reset(self):
        self._buffer = ""
        self._token_count = 0
        self._phase = "unknown"
        self._last_token = ""


class TrueStreamingOrchestrator:
    """Orchestrates true streaming LLM → TTS → Playback.

    Uses Edge TTS's native streaming to get audio bytes as they arrive.
    Audio is written to temp files and played as they complete.

    Usage:
        result = await orchestrator.run(
            messages=[...],
            provider="ollama",
            model="qwen2.5-coder:14b",
        )
    """

    def __init__(self):
        self._cancel_event = asyncio.Event()
        self._metrics = TrueStreamingMetrics()

    async def run(
        self,
        messages: list[dict],
        provider: str = "ollama",
        model: str = "qwen2.5-coder:14b",
        on_token: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """Run the full true streaming pipeline.

        Returns:
            {"ok": True, "response": full_text, "metrics": {...}}
            {"ok": False, "error": "tool_call_detected", "tool_call_text": "..."}
        """
        self._metrics = TrueStreamingMetrics()
        clock = self._metrics.clock

        # TURN_START: moment user text is ready
        clock.mark_turn_start()

        chunker = SentenceChunker()
        tts = TTSPipeline(self._cancel_event)
        player = AudioPlayer()
        detector = ToolCallDetector()

        full_response = []
        first_audio_played = False

        try:
            # Check cancellation before starting
            if self._cancel_event.is_set():
                return {"ok": False, "error": "cancelled"}

            # Select provider stream
            stream_fn = self._select_stream(provider)

            # Phase 1: Stream tokens → chunker
            first_token_time = None
            tool_call_stop = False

            async for token in stream_fn(messages, model):
                if self._cancel_event.is_set():
                    break

                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    clock.mark_provider_first_token()

                full_response.append(token)

                if on_token:
                    on_token(token)

                # TOOL CALL SAFETY: Detect if this is a tool call
                detection = detector.feed(token)
                if detection == "tool_call":
                    self._metrics.tool_call_detected = True
                    self._metrics.tool_call_text = detector.get_buffer()
                    tool_call_stop = True
                    log.info("Tool call detected in stream — stopping TTS")
                    break
                elif detection == "prose":
                    pass

                # Feed token to chunker
                if not tool_call_stop:
                    chunks = chunker.feed(token)
                    for chunk in chunks:
                        self._metrics.chunks_emitted += 1
                        if chunk.index == 0:
                            clock.mark_first_text_chunk()

                        # Phase 2: True streaming - synthesize and play immediately
                        await self._synthesize_and_play(
                            chunk.text, chunk.index, chunk.is_final,
                            clock, player, first_audio_played
                        )
                        if not first_audio_played:
                            first_audio_played = True

            if tool_call_stop:
                tts.cancel()
                clock.mark_response_complete()
                return {
                    "ok": False,
                    "error": "tool_call_detected",
                    "tool_call_text": detector.get_buffer(),
                    "full_response": "".join(full_response),
                    "metrics": self._metrics,
                }

            # Mark provider complete
            clock.mark_provider_complete()

            # Flush remaining buffer
            remaining = chunker.flush()
            if remaining:
                self._metrics.chunks_emitted += 1
                await self._synthesize_and_play(
                    remaining.text, remaining.index, remaining.is_final,
                    clock, player, first_audio_played
                )

            # Wait for playback to finish
            await player.wait_for_speech_end()

            clock.mark_response_complete()

            return {
                "ok": True,
                "response": "".join(full_response),
                "metrics": self._metrics,
            }

        except asyncio.CancelledError:
            tts.cancel()
            player.stop()
            return {"ok": False, "error": "cancelled"}
        except Exception as e:
            log.error("True streaming orchestrator error: %s", e)
            tts.cancel()
            player.stop()
            return {"ok": False, "error": str(e)}
        finally:
            tts.cleanup()

    async def _synthesize_and_play(
        self,
        text: str,
        index: int,
        is_final: bool,
        clock: TurnClock,
        player: AudioPlayer,
        first_audio_played: bool,
    ):
        """Synthesize text and play immediately using true streaming."""
        clock.mark_tts_request_start()

        # Use true streaming to get audio bytes
        audio_chunks = []
        async for audio_chunk in stream_synthesize(
            text, index, is_final, self._cancel_event
        ):
            if self._cancel_event.is_set():
                return

            # Mark first audio bytes
            if not first_audio_played and not audio_chunks:
                clock.mark_first_audio_bytes()

            audio_chunks.append(audio_chunk)

        if not audio_chunks:
            return

        # Combine all audio chunks for this sentence
        all_audio = b"".join(chunk.audio_bytes for chunk in audio_chunks)

        if all_audio:
            # Create AudioChunk with temp file
            audio = create_streaming_audio_chunk(
                all_audio, index, text, is_final,
                audio_chunks[0].tts_start_ms,
                audio_chunks[-1].tts_end_ms,
            )

            # Play immediately
            if not first_audio_played:
                clock.mark_playback_start()

            await player.play(audio)
            self._metrics.chunks_played += 1

            # Cleanup temp file
            if audio.audio_path:
                try:
                    os.unlink(audio.audio_path)
                except OSError:
                    pass

    def cancel(self) -> None:
        """Cancel the current streaming operation."""
        self._cancel_event.set()

    def _select_stream(self, provider: str):
        """Select the appropriate streaming function for the provider."""
        if provider == "groq":
            return stream_groq
        elif provider == "openrouter":
            return stream_openrouter
        elif provider == "ollama":
            return stream_ollama
        else:
            # Default to Groq
            return stream_groq

    @property
    def metrics(self) -> TrueStreamingMetrics:
        return self._metrics
