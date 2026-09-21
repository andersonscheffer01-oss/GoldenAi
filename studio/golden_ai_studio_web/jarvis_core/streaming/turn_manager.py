"""TurnManager — single authority for turn lifecycle and cancellation.

Thread-safe. All components check this to detect stale turns and
coordinate cancellation across threads.

Usage:
    tm = TurnManager()
    turn_id = tm.new_turn()        # Cancel previous, create new
    cancel = tm.get_cancel_event(turn_id)  # threading.Event
    if tm.is_stale(turn_id):       # Check if turn is old
        discard(...)
"""

from __future__ import annotations

import threading
from typing import Optional


class TurnManager:
    """Single authority for current turn ID and cancellation.

    Thread-safe via threading.Lock. All methods can be called from any thread.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current_turn_id = 0
        self._cancel_events: dict[int, threading.Event] = {}

    def new_turn(self) -> int:
        """Create a new turn, cancelling the previous one.

        Returns the new turn_id.
        """
        with self._lock:
            # Cancel previous turn if exists
            prev = self._current_turn_id
            if prev in self._cancel_events:
                self._cancel_events[prev].set()

            self._current_turn_id += 1
            turn_id = self._current_turn_id
            self._cancel_events[turn_id] = threading.Event()
            return turn_id

    def get_cancel_event(self, turn_id: int) -> Optional[threading.Event]:
        """Get the cancel event for a specific turn.

        Returns None if turn_id is unknown.
        """
        with self._lock:
            return self._cancel_events.get(turn_id)

    def cancel_current(self) -> None:
        """Cancel the current turn. Thread-safe."""
        with self._lock:
            if self._current_turn_id in self._cancel_events:
                self._cancel_events[self._current_turn_id].set()

    def cancel_turn(self, turn_id: int) -> None:
        """Cancel a specific turn by ID. Thread-safe."""
        with self._lock:
            if turn_id in self._cancel_events:
                self._cancel_events[turn_id].set()

    def is_stale(self, turn_id: int) -> bool:
        """Check if a turn_id is stale (not the current turn).

        Thread-safe. Returns True if turn_id != current_turn_id.
        """
        with self._lock:
            return turn_id != self._current_turn_id

    def is_cancelled(self, turn_id: int) -> bool:
        """Check if a specific turn has been cancelled.

        Thread-safe.
        """
        with self._lock:
            event = self._cancel_events.get(turn_id)
            if event is None:
                return True  # Unknown turn is considered cancelled
            return event.is_set()

    def cleanup_turn(self, turn_id: int) -> None:
        """Remove old turn data to prevent memory leaks.

        Call after turn completes (success or failure).
        """
        with self._lock:
            self._cancel_events.pop(turn_id, None)

    def cleanup_all(self) -> None:
        """Remove all turn data. Used on shutdown."""
        with self._lock:
            self._cancel_events.clear()
            self._current_turn_id = 0

    @property
    def current_turn_id(self) -> int:
        """Get the current turn ID. Thread-safe."""
        with self._lock:
            return self._current_turn_id
