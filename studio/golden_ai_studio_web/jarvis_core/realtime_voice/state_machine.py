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
from enum import Enum
from typing import Callable, Optional

log = logging.getLogger(__name__)


class ConversationalState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


# Legal transitions: any state can go to IDLE (the "reset" rule)
_LEGAL_TRANSITIONS: dict[ConversationalState, frozenset[ConversationalState]] = {
    ConversationalState.IDLE: frozenset({
        ConversationalState.LISTENING,
        ConversationalState.IDLE,
        ConversationalState.ERROR,
    }),
    ConversationalState.LISTENING: frozenset({
        ConversationalState.THINKING,
        ConversationalState.IDLE,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.THINKING: frozenset({
        ConversationalState.SPEAKING,
        ConversationalState.IDLE,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.SPEAKING: frozenset({
        ConversationalState.IDLE,
        ConversationalState.LISTENING,
        ConversationalState.INTERRUPTED,
        ConversationalState.ERROR,
    }),
    ConversationalState.INTERRUPTED: frozenset({
        ConversationalState.IDLE,
        ConversationalState.LISTENING,
        ConversationalState.ERROR,
    }),
    ConversationalState.ERROR: frozenset({
        ConversationalState.IDLE,
    }),
}


class IllegalTransition(RuntimeError):
    def __init__(self, old: ConversationalState, new: ConversationalState) -> None:
        super().__init__(f"illegal transition: {old.name} -> {new.name}")
        self.old = old
        self.new = new


class VoiceStateMachine:
    """Conversational state machine with optional change listener.

    Not thread-safe by design. Audio loop is the sole driver.
    """

    def __init__(
        self,
        initial: ConversationalState = ConversationalState.IDLE,
        on_change: Optional[Callable[[ConversationalState, ConversationalState], None]] = None,
    ) -> None:
        self._state = initial
        self._on_change = on_change

    @property
    def state(self) -> ConversationalState:
        return self._state

    def transition(self, new: ConversationalState) -> None:
        old = self._state
        if new is old:
            return  # no-op self-transition
        if new not in _LEGAL_TRANSITIONS[old]:
            raise IllegalTransition(old, new)
        self._state = new
        log.debug("voice state: %s -> %s", old.name, new.name)
        if self._on_change is not None:
            try:
                self._on_change(old, new)
            except Exception:
                log.exception("on_change callback raised")

    def force_idle(self) -> None:
        """Force to IDLE regardless of current state (emergency reset)."""
        old = self._state
        if old is ConversationalState.IDLE:
            return
        self._state = ConversationalState.IDLE
        log.debug("voice state: %s -> IDLE (forced)", old.name)
        if self._on_change is not None:
            try:
                self._on_change(old, ConversationalState.IDLE)
            except Exception:
                log.exception("on_change callback raised")

    def is_listening_capable(self) -> bool:
        return self._state in (
            ConversationalState.IDLE,
            ConversationalState.LISTENING,
            ConversationalState.INTERRUPTED,
        )

    def can_barge_in(self) -> bool:
        return self._state == ConversationalState.SPEAKING
