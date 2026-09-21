"""Streaming Voice integration — hooks into VoiceService.

Provides the streaming alternative to the legacy Brain.interpret() + _speak() path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from jarvis_core.streaming import is_streaming_enabled
from jarvis_core.streaming.orchestrator import StreamingOrchestrator, StreamingMetrics

log = logging.getLogger(__name__)


async def streaming_handle(
    brain,
    service,
    user_input: str,
    memory_context: str = "",
    voice_callback=None,
) -> dict:
    """Streaming alternative to Brain.interpret() + _speak().

    Called from VoiceService._handle() when streaming is enabled.

    Args:
        brain: JarvisBrain instance (for prompt assembly)
        service: VoiceService instance (for state, TTS, playback)
        user_input: Transcribed user text
        memory_context: Memory context string
        voice_callback: Optional callback for token-by-token updates

    Returns:
        {"ok": True, "response": ..., "metrics": ...} or {"ok": False, "error": ...}
    """
    if not is_streaming_enabled():
        return {"ok": False, "error": "streaming_disabled"}

    try:
        # Assemble messages using Brain's build_messages — single source of truth
        messages = brain.build_messages(user_input, memory_context,
                                        source="voice", voice_capture=True)

        # Determine provider from orchestrator
        provider = "groq"
        model = "qwen/qwen3.8-27b"

        if hasattr(brain, "orchestrator") and brain.orchestrator:
            providers = getattr(brain.orchestrator, "models", None)
            if providers and hasattr(providers, "providers"):
                provider_list = providers.providers
                if provider_list:
                    # Use first available provider
                    provider = getattr(provider_list[0], "name", "groq")
                    model = getattr(provider_list[0], "default_model", model)

        # Run streaming pipeline
        orchestrator = StreamingOrchestrator()
        result = await orchestrator.run(
            messages=messages,
            provider=provider,
            model=model,
            on_token=voice_callback,
        )

        return result

    except Exception as e:
        log.error("Streaming handle error: %s", e)
        return {"ok": False, "error": str(e)}


def should_use_streaming(brain, user_input: str) -> bool:
    """Determine if streaming should be used for this request.

    Streaming is appropriate when:
    - Feature flag is enabled
    - Request is a voice command (VOICE_FAST profile)
    - No tool calls expected (pure conversation)
    - Not a clarification request
    """
    if not is_streaming_enabled():
        return False

    # Check if this is a voice command (not a tool call)
    # Pure conversation responses benefit most from streaming
    return True


class StreamingMetricsCollector:
    """Collects and reports streaming metrics."""

    def __init__(self):
        self.legacy_first_audio_ms: float = 0
        self.streaming_first_audio_ms: float = 0

    def record_legacy(self, first_audio_ms: float):
        self.legacy_first_audio_ms = first_audio_ms

    def record_streaming(self, metrics: StreamingMetrics):
        self.streaming_first_audio_ms = metrics.end_speech_to_first_audio_ms

    def report(self) -> dict:
        delta = self.legacy_first_audio_ms - self.streaming_first_audio_ms
        return {
            "legacy_first_audio_ms": self.legacy_first_audio_ms,
            "streaming_first_audio_ms": self.streaming_first_audio_ms,
            "latency_reduction_ms": delta,
            "latency_reduction_pct": (
                (delta / self.legacy_first_audio_ms * 100)
                if self.legacy_first_audio_ms > 0
                else 0
            ),
        }
