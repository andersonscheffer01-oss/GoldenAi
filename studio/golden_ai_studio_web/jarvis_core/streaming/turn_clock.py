"""Unified Turn Clock — fair comparison between Legacy and Streaming pipelines.

All metrics measured from TURN_START (moment user text is ready).

Ensures apples-to-apples comparison between pipelines.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TurnClock:
    """Measures all pipeline events from a single TURN_START.

    Usage:
        clock = TurnClock()
        # ... user text ready ...
        clock.mark_turn_start()
        # ... provider starts streaming ...
        clock.mark_provider_first_token()
        # ... first text chunk ready ...
        clock.mark_first_text_chunk()
        # ... TTS request starts ...
        clock.mark_tts_request_start()
        # ... first audio bytes available ...
        clock.mark_first_audio_bytes()
        # ... playback actually starts ...
        clock.mark_playback_start()
        # ... full response complete ...
        clock.mark_response_complete()

    All marks are relative to TURN_START.
    """

    # Absolute timestamps (internal)
    _turn_start: float = 0
    _provider_first_token: float = 0
    _provider_complete: float = 0
    _first_text_chunk: float = 0
    _tts_request_start: float = 0
    _first_audio_bytes: float = 0
    _playback_start: float = 0
    _response_complete: float = 0

    # Marked flags
    _marked_turn_start: bool = False
    _marked_provider_first_token: bool = False
    _marked_provider_complete: bool = False
    _marked_first_text_chunk: bool = False
    _marked_tts_request_start: bool = False
    _marked_first_audio_bytes: bool = False
    _marked_playback_start: bool = False
    _marked_response_complete: bool = False

    def mark_turn_start(self) -> None:
        """Mark TURN_START — user text is ready, pipeline begins."""
        self._turn_start = time.perf_counter()
        self._marked_turn_start = True

    def mark_provider_first_token(self) -> None:
        """Mark first token from LLM provider."""
        if not self._marked_provider_first_token:
            self._provider_first_token = time.perf_counter()
            self._marked_provider_first_token = True

    def mark_provider_complete(self) -> None:
        """Mark LLM provider complete (all tokens received)."""
        self._provider_complete = time.perf_counter()
        self._marked_provider_complete = True

    def mark_first_text_chunk(self) -> None:
        """Mark first text chunk ready for TTS (sentence boundary)."""
        if not self._marked_first_text_chunk:
            self._first_text_chunk = time.perf_counter()
            self._marked_first_text_chunk = True

    def mark_tts_request_start(self) -> None:
        """Mark TTS synthesis request starts."""
        if not self._marked_tts_request_start:
            self._tts_request_start = time.perf_counter()
            self._marked_tts_request_start = True

    def mark_first_audio_bytes(self) -> None:
        """Mark first audio bytes available (from Edge TTS)."""
        if not self._marked_first_audio_bytes:
            self._first_audio_bytes = time.perf_counter()
            self._marked_first_audio_bytes = True

    def mark_playback_start(self) -> None:
        """Mark audio playback actually starts (speaker output)."""
        if not self._marked_playback_start:
            self._playback_start = time.perf_counter()
            self._marked_playback_start = True

    def mark_response_complete(self) -> None:
        """Mark full response complete (all text + audio)."""
        self._response_complete = time.perf_counter()
        self._marked_response_complete = True

    # ─── Result metrics (milliseconds from TURN_START) ───

    @property
    def provider_first_token_from_turn_ms(self) -> float:
        """Time from TURN_START to first LLM token."""
        if not self._marked_provider_first_token:
            return 0
        return (self._provider_first_token - self._turn_start) * 1000

    @property
    def provider_complete_from_turn_ms(self) -> float:
        """Time from TURN_START to LLM complete."""
        if not self._marked_provider_complete:
            return 0
        return (self._provider_complete - self._turn_start) * 1000

    @property
    def first_text_chunk_from_turn_ms(self) -> float:
        """Time from TURN_START to first sentence ready for TTS."""
        if not self._marked_first_text_chunk:
            return 0
        return (self._first_text_chunk - self._turn_start) * 1000

    @property
    def tts_request_start_from_turn_ms(self) -> float:
        """Time from TURN_START to TTS synthesis start."""
        if not self._marked_tts_request_start:
            return 0
        return (self._tts_request_start - self._turn_start) * 1000

    @property
    def first_audio_bytes_from_turn_ms(self) -> float:
        """Time from TURN_START to first audio bytes available."""
        if not self._marked_first_audio_bytes:
            return 0
        return (self._first_audio_bytes - self._turn_start) * 1000

    @property
    def playback_start_from_turn_ms(self) -> float:
        """Time from TURN_START to audio playback start (KPI)."""
        if not self._marked_playback_start:
            return 0
        return (self._playback_start - self._turn_start) * 1000

    @property
    def response_complete_from_turn_ms(self) -> float:
        """Time from TURN_START to full response complete."""
        if not self._marked_response_complete:
            return 0
        return (self._response_complete - self._turn_start) * 1000

    # ─── Derived metrics ───

    @property
    def tts_synthesis_duration_ms(self) -> float:
        """Duration of TTS synthesis (request start to first audio bytes)."""
        if not self._marked_tts_request_start or not self._marked_first_audio_bytes:
            return 0
        return (self._first_audio_bytes - self._tts_request_start) * 1000

    @property
    def audio_to_playback_ms(self) -> float:
        """Delay from first audio bytes to playback start."""
        if not self._marked_first_audio_bytes or not self._marked_playback_start:
            return 0
        return (self._playback_start - self._first_audio_bytes) * 1000

    def to_dict(self) -> dict:
        """Export all metrics as dictionary."""
        return {
            "provider_first_token_from_turn_ms": self.provider_first_token_from_turn_ms,
            "provider_complete_from_turn_ms": self.provider_complete_from_turn_ms,
            "first_text_chunk_from_turn_ms": self.first_text_chunk_from_turn_ms,
            "tts_request_start_from_turn_ms": self.tts_request_start_from_turn_ms,
            "first_audio_bytes_from_turn_ms": self.first_audio_bytes_from_turn_ms,
            "playback_start_from_turn_ms": self.playback_start_from_turn_ms,
            "response_complete_from_turn_ms": self.response_complete_from_turn_ms,
            "tts_synthesis_duration_ms": self.tts_synthesis_duration_ms,
            "audio_to_playback_ms": self.audio_to_playback_ms,
        }

    def reset(self) -> None:
        """Reset all marks for reuse."""
        self.__init__()
