"""Small, Core-aligned contracts shared by the Golden voice runtime.

This module deliberately contains no audio backend, model loader, network
client, or persistence. ``VoiceService`` remains the runtime owner; these
objects make its lifecycle and future provider seams explicit and testable.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


class VoiceCancelledError(RuntimeError):
    """Raised by a cooperative provider when its operation is cancelled."""


class VoiceCancellation:
    """Thread-safe cancellation signal with an auditable reason."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason = ""

    @property
    def event(self) -> threading.Event:
        """Expose the event for existing thread/async bridge code."""
        return self._event

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str = "cancelled") -> bool:
        """Cancel once and retain the first reason; return whether it changed."""
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = str(reason or "cancelled")
            self._event.set()
            return True

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise VoiceCancelledError(self.reason or "cancelled")


@dataclass
class VoiceSession:
    """Ephemeral identity for one Voice runtime session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    state: Any = None
    cancellation: VoiceCancellation = field(default_factory=VoiceCancellation)
    metadata: dict[str, Any] = field(default_factory=dict)

    def cancel(self, reason: str = "session_cancelled") -> bool:
        return self.cancellation.cancel(reason)


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """Minimal future STT boundary; implementations remain Core-owned."""

    def transcribe(
        self,
        audio: bytes,
        *,
        sample_rate: int,
        cancellation: VoiceCancellation,
    ) -> str:
        ...


@runtime_checkable
class TextToSpeechProvider(Protocol):
    """Minimal future TTS boundary with cooperative cancellation."""

    def speak(self, text: str, *, cancellation: VoiceCancellation) -> None:
        ...

    def cancel(self) -> None:
        ...


@runtime_checkable
class AudioInput(Protocol):
    """Future audio source boundary; no device is opened by this module."""

    def close(self) -> None:
        ...


@runtime_checkable
class AudioOutput(Protocol):
    """Future playback boundary; one runtime owns active output."""

    def stop(self) -> None:
        ...


__all__ = [
    "AudioInput",
    "AudioOutput",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "VoiceCancellation",
    "VoiceCancelledError",
    "VoiceSession",
]
