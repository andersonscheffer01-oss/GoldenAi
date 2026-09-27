"""Small, Core-aligned contracts shared by the Golden voice runtime.

This module deliberately contains no audio backend, model loader, network
client, or persistence. ``VoiceService`` remains the runtime owner; these
objects make its lifecycle and future provider seams explicit and testable.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable


class VoiceCancelledError(RuntimeError):
    """Raised by a cooperative provider when its operation is cancelled."""


@dataclass(frozen=True)
class TranscriptEvent:
    """Immutable transcript value crossing the provider boundary."""

    text: str
    is_final: bool
    sequence: int
    session_id: str
    utterance_id: str
    provider: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    epoch: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", str(self.text or ""))
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "session_id", str(self.session_id or ""))
        object.__setattr__(self, "utterance_id", str(self.utterance_id or ""))
        object.__setattr__(self, "provider", str(self.provider or "unknown"))
        object.__setattr__(self, "epoch", int(self.epoch))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata or {})))

    @property
    def identity(self) -> tuple[str, str]:
        """The idempotency key for a final transcript."""
        return self.session_id, self.utterance_id


class TranscriptAcceptanceGate:
    """Accept at most one current final per session/utterance identity."""

    def __init__(self, session_id: str = "") -> None:
        self._lock = threading.RLock()
        self._session_id = str(session_id or "")
        self._epoch = 0
        self._cancelled = False
        self._accepted: set[tuple[str, str]] = set()

    @property
    def session_id(self) -> str:
        with self._lock:
            return self._session_id

    @property
    def epoch(self) -> int:
        with self._lock:
            return self._epoch

    def begin(self, session_id: str) -> int:
        with self._lock:
            self._session_id = str(session_id or "")
            self._epoch += 1
            self._cancelled = False
            self._accepted.clear()
            return self._epoch

    def cancel(self) -> int:
        with self._lock:
            self._epoch += 1
            self._cancelled = True
            self._accepted.clear()
            return self._epoch

    def accept(self, event: TranscriptEvent) -> bool:
        """Return true only for one final event from the active epoch."""
        with self._lock:
            if self._cancelled or not event.is_final:
                return False
            if event.session_id != self._session_id:
                return False
            if event.epoch not in (0, self._epoch):
                return False
            if not event.text.strip() or not event.utterance_id:
                return False
            if event.identity in self._accepted:
                return False
            self._accepted.add(event.identity)
            return True


class DeterministicFakeSTTProvider:
    """Hardware/model-free provider for contract and orchestration tests."""

    def __init__(self, responses: list[Any] | None = None, *, provider: str = "fake-stt"):
        self._responses = list(responses or [])
        self.provider = provider
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def queue(self, response: Any) -> None:
        self._responses.append(response)

    def transcribe(
        self,
        audio: bytes,
        *,
        sample_rate: int,
        cancellation: "VoiceCancellation",
        session_id: str = "",
        utterance_id: str = "",
        epoch: int = 0,
    ) -> TranscriptEvent:
        cancellation.throw_if_cancelled()
        if self.closed:
            raise RuntimeError("fake STT provider is closed")
        self.calls.append({
            "audio_bytes": len(audio),
            "sample_rate": sample_rate,
            "session_id": session_id,
            "utterance_id": utterance_id,
            "epoch": epoch,
        })
        response = self._responses.pop(0) if self._responses else ""
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            response = response(cancellation)
        cancellation.throw_if_cancelled()
        if isinstance(response, TranscriptEvent):
            return replace(
                response,
                session_id=response.session_id or session_id,
                utterance_id=response.utterance_id or utterance_id,
                epoch=response.epoch or epoch,
            )
        return TranscriptEvent(
            text=str(response or ""),
            is_final=True,
            sequence=len(self.calls),
            session_id=session_id,
            utterance_id=utterance_id,
            provider=self.provider,
            epoch=epoch,
        )

    def close(self) -> None:
        self.closed = True

    def restart(self) -> None:
        self.closed = False


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
        session_id: str = "",
        utterance_id: str = "",
        epoch: int = 0,
    ) -> TranscriptEvent:
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
    "TranscriptAcceptanceGate",
    "TranscriptEvent",
    "DeterministicFakeSTTProvider",
    "TextToSpeechProvider",
    "VoiceCancellation",
    "VoiceCancelledError",
    "VoiceSession",
]
