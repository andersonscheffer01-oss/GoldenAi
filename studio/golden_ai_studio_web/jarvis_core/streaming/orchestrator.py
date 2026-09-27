"""Streaming Voice Orchestrator — P1.4B/P1.4C main entry point.

Coordinates: Provider streaming → SentenceChunker → TTSPipeline → AudioPlayer.

Provides the same external interface as the legacy Brain.interpret() + _speak()
but with sentence-level pipelining for lower perceived latency.

TOOL CALL SAFETY:
- Detects if LLM is generating a tool call (JSON) vs prose response
- If tool call detected, stops streaming to TTS and returns early
- Caller must handle tool execution via legacy path
- Never bypasses SecurityManager, ToolRegistry, or confirmation system

BARGE-IN SUPPORT:
- Uses TurnManager for single authority on turn lifecycle
- Uses threading.Event for cross-thread cancellation
- Stale chunk protection via turn_id checks
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
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
from jarvis_core.streaming.turn_manager import TurnManager

log = logging.getLogger(__name__)


@dataclass
class StreamingMetrics:
    provider_ttft_ms: float = 0
    first_sentence_ready_ms: float = 0
    tts_start_ms: float = 0
    tts_first_audio_ms: float = 0
    playback_start_ms: float = 0
    end_speech_to_first_audio_ms: float = 0
    total_response_ms: float = 0
    chunks_emitted: int = 0
    chunks_played: int = 0
    chunks_discarded_stale: int = 0
    tool_call_detected: bool = False
    tool_call_text: str = ""
    clock: TurnClock = field(default_factory=TurnClock)
    turn_id: int = 0


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


class StreamingOrchestrator:
    """Orchestrates streaming LLM → TTS → Playback.

    Uses TurnManager for single authority on turn lifecycle.
    Uses threading.Event for cross-thread cancellation.

    Usage:
        result = await orchestrator.run(
            messages=[...],
            provider="groq",
            model="qwen/qwen3.8-27b",
            turn_id=turn_id,
            turn_manager=turn_manager,
        )
    """

    def __init__(self):
        self._metrics = StreamingMetrics()
        self._cancel_lock = threading.Lock()
        self._active_cancel_event: Optional[threading.Event] = None

    async def run(
        self,
        messages: list[dict],
        provider: str = "groq",
        model: str = "qwen/qwen3.8-27b",
        on_token: Optional[Callable[[str], None]] = None,
        turn_id: Optional[int] = None,
        turn_manager: Optional[TurnManager] = None,
    ) -> dict:
        """Run the full streaming pipeline.

        Args:
            messages: LLM messages
            provider: Provider name
            model: Model name
            on_token: Optional callback for each token
            turn_id: Turn ID for stale chunk protection
            turn_manager: TurnManager for cancellation

        Returns:
            {"ok": True, "response": full_text, "metrics": {...}}
            {"ok": False, "error": "tool_call_detected", "tool_call_text": "..."}
        """
        self._metrics = StreamingMetrics()
        clock = self._metrics.clock

        # Get cancel event from TurnManager (threading.Event, cross-thread safe)
        cancel_event: Optional[threading.Event] = None
        if turn_manager is not None and turn_id is not None:
            cancel_event = turn_manager.get_cancel_event(turn_id)
            if cancel_event is None:
                cancel_event = threading.Event()
                cancel_event.set()
            self._metrics.turn_id = turn_id
        else:
            cancel_event = threading.Event()

        with self._cancel_lock:
            self._active_cancel_event = cancel_event

        # TURN_START
        clock.mark_turn_start()

        chunker = SentenceChunker()
        tts = TTSPipeline(cancel_event)
        player = AudioPlayer()
        detector = ToolCallDetector()

        full_response = []
        first_audio_time = None

        stream_iterator = None

        try:
            # Check cancellation before starting (threading.Event, cross-thread safe)
            if cancel_event and cancel_event.is_set():
                return {"ok": False, "error": "cancelled"}

            # Select provider stream
            stream_fn = self._select_stream(provider)

            # Phase 1+2: Stream tokens → chunker → TTS → PLAY IMMEDIATELY
            first_token_time = None
            tool_call_stop = False
            first_audio_played = False

            stream_iterator = stream_fn(messages, model)
            async for token in stream_iterator:
                # Check cancellation (threading.Event, cross-thread safe)
                if cancel_event and cancel_event.is_set():
                    break

                # Check stale turn (another turn may have started)
                if turn_manager and turn_id and turn_manager.is_stale(turn_id):
                    log.info("Turn %d stale, stopping", turn_id)
                    break

                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    clock.mark_provider_first_token()
                    self._metrics.provider_ttft_ms = (
                        (first_token_time - clock._turn_start) * 1000
                    )

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

                # Feed token to chunker and play immediately
                if not tool_call_stop:
                    chunks = chunker.feed(token)
                    for chunk in chunks:
                        # Check stale before TTS
                        if turn_manager and turn_id and turn_manager.is_stale(turn_id):
                            self._metrics.chunks_discarded_stale += 1
                            break

                        self._metrics.chunks_emitted += 1
                        if chunk.index == 0:
                            clock.mark_first_text_chunk()
                            self._metrics.first_sentence_ready_ms = (
                                (time.perf_counter() - clock._turn_start) * 1000
                            )
                        # Submit to TTS and play immediately
                        clock.mark_tts_request_start()
                        self._metrics.tts_start_ms = (
                            (time.perf_counter() - clock._turn_start) * 1000
                        )
                        audio = await tts.synthesize_and_get(chunk.text, chunk.index, chunk.is_final)
                        if audio and not first_audio_played:
                            clock.mark_first_audio_bytes()
                            clock.mark_playback_start()
                            self._metrics.tts_first_audio_ms = (
                                (time.perf_counter() - clock._turn_start) * 1000
                            )
                            self._metrics.playback_start_ms = self._metrics.tts_first_audio_ms
                            first_audio_time = time.perf_counter()
                            first_audio_played = True
                        if audio:
                            # Check stale before playback
                            if turn_manager and turn_id and turn_manager.is_stale(turn_id):
                                self._metrics.chunks_discarded_stale += 1
                                if audio.audio_path:
                                    import os
                                    try:
                                        os.unlink(audio.audio_path)
                                    except OSError:
                                        pass
                                break

                            await player.play(audio, cancel_event)
                            self._metrics.chunks_played += 1
                            if audio.audio_path:
                                import os
                                try:
                                    os.unlink(audio.audio_path)
                                except OSError:
                                    pass

            if cancel_event and cancel_event.is_set():
                tts.cancel()
                player.stop()
                clock.mark_provider_complete()
                clock.mark_response_complete()
                return {"ok": False, "error": "cancelled", "metrics": self._metrics}

            # Mark provider complete
            clock.mark_provider_complete()

            if tool_call_stop:
                tts.cancel()
                player.stop()
                clock.mark_response_complete()
                return {
                    "ok": False,
                    "error": "tool_call_detected",
                    "tool_call_text": detector.get_buffer(),
                    "full_response": "".join(full_response),
                    "metrics": self._metrics,
                }

            # Flush remaining buffer
            remaining = chunker.flush()
            if remaining:
                # Check stale before flushing
                if turn_manager and turn_id and not turn_manager.is_stale(turn_id):
                    self._metrics.chunks_emitted += 1
                    audio = await tts.synthesize_and_get(remaining.text, remaining.index, remaining.is_final)
                    if audio:
                        await player.play(audio, cancel_event)
                        self._metrics.chunks_played += 1
                        if audio.audio_path:
                            import os
                            try:
                                os.unlink(audio.audio_path)
                            except OSError:
                                pass

            # Wait for playback to finish
            await player.wait_for_speech_end()

            clock.mark_response_complete()

            # Calculate end-to-first-audio
            if first_audio_time:
                self._metrics.end_speech_to_first_audio_ms = (
                    (first_audio_time - clock._turn_start) * 1000
                )

            self._metrics.total_response_ms = (
                (time.perf_counter() - clock._turn_start) * 1000
            )

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
            log.error("Streaming orchestrator error: %s", e)
            tts.cancel()
            player.stop()
            return {"ok": False, "error": str(e)}
        finally:
            if stream_iterator is not None:
                close_stream = getattr(stream_iterator, "aclose", None)
                if close_stream is not None:
                    try:
                        await close_stream()
                    except Exception as exc:
                        log.debug("Provider stream close failed: %s", exc)
            tts.cleanup()
            # Cleanup turn data
            if turn_manager is not None and turn_id is not None:
                turn_manager.cleanup_turn(turn_id)
            with self._cancel_lock:
                if self._active_cancel_event is cancel_event:
                    self._active_cancel_event = None

    def cancel(self) -> bool:
        """Cancel the current streaming operation.

        Prefer using TurnManager.cancel_current() when a turn is available.
        The local event keeps the standalone orchestrator contract cooperative.
        """
        with self._cancel_lock:
            event = self._active_cancel_event
            if event is None or event.is_set():
                return False
            event.set()
            return True

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
    def metrics(self) -> StreamingMetrics:
        return self._metrics
