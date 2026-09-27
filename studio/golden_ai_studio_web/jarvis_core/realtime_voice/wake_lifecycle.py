"""Core-owned wake activation lifecycle.

Wake detection remains a provider concern. This module only accepts a
validated activation signal and composes it with the existing voice state
machine; it never calls Core, SecurityManager, tools, or persistence.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional

from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    VoiceStateMachine,
)


@dataclass(frozen=True)
class WakeActivation:
    """Identity and provenance for one accepted wake event."""

    session_id: str
    activation_id: str
    sequence: int
    observed_at: float


class WakeLifecycle:
    """Manage wake arming and activation without a second state machine."""

    def __init__(
        self,
        state_machine: VoiceStateMachine,
        *,
        session_id: Optional[str] = None,
        time_fn=None,
    ) -> None:
        self._state_machine = state_machine
        self._session_id = str(session_id or uuid.uuid4().hex)
        self._time_fn = time_fn or time.time
        self._armed = False
        self._sequence = 0
        self._seen_activation_ids: set[str] = set()
        self._active: Optional[WakeActivation] = None

    @property
    def state_machine(self) -> VoiceStateMachine:
        return self._state_machine

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def active(self) -> Optional[WakeActivation]:
        return self._active

    def arm(self) -> bool:
        """Arm wake observation while keeping the shared machine in IDLE."""
        if self._armed:
            return False
        self._state_machine.force_idle()
        self._armed = True
        return True

    def disarm(self) -> bool:
        """Disarm wake and discard the current activation, if any."""
        changed = self._armed or self._active is not None
        self._armed = False
        self._active = None
        if self._state_machine.state is not ConversationalState.STOPPED:
            self._state_machine.force_idle()
        return changed

    def activate(
        self,
        activation_id: str,
        *,
        session_id: Optional[str] = None,
        observed_at: Optional[float] = None,
    ) -> Optional[WakeActivation]:
        """Accept one activation for the armed current session.

        Duplicate IDs, stale session IDs, and activations while another
        activation is active are rejected without changing state.
        """
        activation_id = str(activation_id or "").strip()
        if not self._armed or not activation_id:
            return None
        if session_id is not None and str(session_id) != self._session_id:
            return None
        if activation_id in self._seen_activation_ids or self._active is not None:
            return None
        if self._state_machine.state is not ConversationalState.IDLE:
            return None

        self._sequence += 1
        activation = WakeActivation(
            session_id=self._session_id,
            activation_id=activation_id,
            sequence=self._sequence,
            observed_at=float(self._time_fn() if observed_at is None else observed_at),
        )
        self._seen_activation_ids.add(activation_id)
        self._active = activation
        self._state_machine.transition(ConversationalState.LISTENING)
        return activation

    def complete(self, activation_id: Optional[str] = None) -> bool:
        """Complete only the current activation."""
        if self._active is None:
            return False
        if activation_id is not None and str(activation_id) != self._active.activation_id:
            return False
        self._active = None
        if self._state_machine.state is ConversationalState.LISTENING:
            self._state_machine.transition(ConversationalState.IDLE)
        return True

    def cancel(self) -> bool:
        """Cancel the current activation and leave wake disarmed."""
        return self.disarm()

    def shutdown(self) -> None:
        """Move the shared machine to its terminal state."""
        self._armed = False
        self._active = None
        self._state_machine.force_stopped()

    def reset_session(self, session_id: Optional[str] = None) -> str:
        """Start a clean session identity without creating another machine."""
        self._armed = False
        self._active = None
        self._sequence = 0
        self._seen_activation_ids.clear()
        self._session_id = str(session_id or uuid.uuid4().hex)
        self._state_machine.force_idle()
        return self._session_id


__all__ = ["WakeActivation", "WakeLifecycle"]
