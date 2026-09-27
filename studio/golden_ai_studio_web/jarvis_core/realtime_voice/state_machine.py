"""Conversational state machine adapted from ndunl075-jarvis.

Adapted from ndunl075-jarvis MIT-licensed core/state_machine.py.
Simplified to single-axis ConversationalState for Golden AI integration.
Does NOT replace VoiceService — provides optional state tracking.

Golden AI states map to:
    DORMINDO    → IDLE
    OUVINDO     → LISTENING
    PROCESSANDO → THINKING
    FALANDO     → SPEAKING
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable, Optional

log = logging.getLogger(__name__)


class ConversationalState(Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


# Legal transitions: any state can go to IDLE (the "reset" rule)
_LEGAL_TRANSITIONS: dict[ConversationalState, frozenset[ConversationalState]] = {
    ConversationalState.STOPPED: frozenset({ConversationalState.IDLE}),
    ConversationalState.IDLE: frozenset({
        ConversationalState.LISTENING,
        ConversationalState.THINKING,
        ConversationalState.STOPPED,
        ConversationalState.IDLE,
        ConversationalState.ERROR,
    }),
    ConversationalState.LISTENING: frozenset({
        ConversationalState.TRANSCRIBING,
        ConversationalState.THINKING,
        ConversationalState.IDLE,
        ConversationalState.STOPPED,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.TRANSCRIBING: frozenset({
        ConversationalState.THINKING,
        ConversationalState.LISTENING,
        ConversationalState.IDLE,
        ConversationalState.STOPPED,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.THINKING: frozenset({
        ConversationalState.SPEAKING,
        ConversationalState.IDLE,
        ConversationalState.STOPPED,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.SPEAKING: frozenset({
        ConversationalState.IDLE,
        ConversationalState.LISTENING,
        ConversationalState.STOPPED,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.INTERRUPTED: frozenset({
        ConversationalState.IDLE,
        ConversationalState.LISTENING,
        ConversationalState.STOPPED,
        ConversationalState.ERROR,
    }),
    ConversationalState.ERROR: frozenset({
        ConversationalState.IDLE,
        ConversationalState.STOPPED,
    }),
}


class IllegalTransition(RuntimeError):
    def __init__(self, old: ConversationalState, new: ConversationalState) -> None:
        super().__init__(f"illegal transition: {old.name} -> {new.name}")
        self.old = old
        self.new = new


class VoiceStateMachine:
    """Conversational state machine with optional change listener.

    The realtime loop is the normal driver, but status/shutdown can be read
    from another thread, so transitions are protected by a small lock.
    """

    def __init__(
        self,
        initial: ConversationalState = ConversationalState.IDLE,
        on_change: Optional[Callable[[ConversationalState, ConversationalState], None]] = None,
    ) -> None:
        self._state = initial
        self._on_change = on_change
        self._lock = threading.RLock()
        self._history: list[tuple[ConversationalState, ConversationalState]] = []

    @property
    def state(self) -> ConversationalState:
        with self._lock:
            return self._state

    def transition(self, new: ConversationalState) -> None:
        with self._lock:
            old = self._state
            if new is old:
                return  # no-op self-transition
            if new not in _LEGAL_TRANSITIONS[old]:
                raise IllegalTransition(old, new)
            self._state = new
            self._history.append((old, new))
        log.debug("voice state: %s -> %s", old.name, new.name)
        if self._on_change is not None:
            try:
                self._on_change(old, new)
            except Exception:
                log.exception("on_change callback raised")

    def force_idle(self) -> None:
        """Force to IDLE regardless of current state (emergency reset)."""
        with self._lock:
            old = self._state
            if old is ConversationalState.IDLE:
                return
            self._state = ConversationalState.IDLE
            self._history.append((old, ConversationalState.IDLE))
        log.debug("voice state: %s -> IDLE (forced)", old.name)
        if self._on_change is not None:
            try:
                self._on_change(old, ConversationalState.IDLE)
            except Exception:
                log.exception("on_change callback raised")

    def force_stopped(self) -> None:
        """Move to the terminal runtime state during cooperative shutdown."""
        with self._lock:
            old = self._state
            if old is ConversationalState.STOPPED:
                return
            self._state = ConversationalState.STOPPED
            self._history.append((old, ConversationalState.STOPPED))
        log.debug("voice state: %s -> STOPPED (shutdown)", old.name)

    def can_transition(self, new: ConversationalState) -> bool:
        with self._lock:
            return new is self._state or new in _LEGAL_TRANSITIONS[self._state]

    @property
    def history(self) -> tuple[tuple[ConversationalState, ConversationalState], ...]:
        with self._lock:
            return tuple(self._history)

    def is_listening_capable(self) -> bool:
        return self.state in (
            ConversationalState.IDLE,
            ConversationalState.LISTENING,
            ConversationalState.INTERRUPTED,
        )

    def can_barge_in(self) -> bool:
        return self.state == ConversationalState.SPEAKING


# Public name for future code; keep the historical import stable.
VoiceState = ConversationalState
