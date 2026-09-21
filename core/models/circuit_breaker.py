"""Circuit breaker and escalation policy for Multi-Model Local V1.

The circuit breaker tracks consecutive failures for each model and
escalates to a fallback profile when the threshold is reached.
This prevents the system from repeatedly hitting a broken model.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from .profiles import ModelProfile, get_profile_config


class CircuitState(str, Enum):
    """State of a model circuit breaker."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Tripped — escalate to fallback
    HALF_OPEN = "HALF_OPEN"  # Testing if model recovered


@dataclass
class CircuitEntry:
    """Per-model circuit breaker state."""

    model_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    opened_at: float = 0.0
    cooldown_seconds: int = 60

    def record_success(self) -> None:
        self.success_count += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()

    def should_try_half_open(self) -> bool:
        """Check if enough time has passed to try a half-open probe."""
        if self.state != CircuitState.OPEN:
            return False
        return (time.time() - self.opened_at) >= self.cooldown_seconds


class CircuitBreaker:
    """Tracks per-model failures and decides when to escalate.

    The escalation policy is:
        EXPERT -> CODER -> FAST
    When a model trips its circuit, the router falls back to the
    next-lower profile. The circuit never grants permissions; it
    only selects which model to call.
    """

    # Profile escalation chain (highest to lowest)
    ESCALATION_CHAIN: list[ModelProfile] = [
        ModelProfile.EXPERT,
        ModelProfile.CODER,
        ModelProfile.FAST,
    ]

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._circuits: dict[str, CircuitEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(self, model_name: str) -> CircuitEntry:
        """Return the circuit entry for a model, creating if needed."""
        if model_name not in self._circuits:
            self._circuits[model_name] = CircuitEntry(
                model_name=model_name,
                cooldown_seconds=self.cooldown_seconds,
            )
        return self._circuits[model_name]

    def is_tripped(self, model_name: str) -> bool:
        """Check if the circuit for a model is tripped (OPEN)."""
        entry = self.get_or_create(model_name)
        if entry.state == CircuitState.OPEN:
            if entry.should_try_half_open():
                entry.state = CircuitState.HALF_OPEN
                return False
            return True
        return False

    def record_success(self, model_name: str) -> None:
        """Record a successful call to the model."""
        entry = self.get_or_create(model_name)
        entry.record_success()

    def record_failure(self, model_name: str) -> None:
        """Record a failed call to the model; may trip the circuit."""
        entry = self.get_or_create(model_name)
        entry.record_failure()
        if entry.failure_count >= self.failure_threshold:
            entry.state = CircuitState.OPEN
            entry.opened_at = time.time()

    def reset(self, model_name: str | None = None) -> None:
        """Reset circuit(s) to CLOSED state."""
        if model_name is None:
            for entry in self._circuits.values():
                entry.state = CircuitState.CLOSED
                entry.failure_count = 0
        else:
            entry = self.get_or_create(model_name)
            entry.state = CircuitState.CLOSED
            entry.failure_count = 0

    def get_fallback_profile(self, current_profile: ModelProfile | str) -> ModelProfile:
        """Return the next-lower profile in the escalation chain."""
        if isinstance(current_profile, str):
            try:
                current_profile = ModelProfile(current_profile.upper())
            except ValueError:
                current_profile = ModelProfile.CODER
        try:
            idx = self.ESCALATION_CHAIN.index(current_profile)
        except ValueError:
            idx = 1  # Default to CODER position
        if idx < len(self.ESCALATION_CHAIN) - 1:
            return self.ESCALATION_CHAIN[idx + 1]
        return self.ESCALATION_CHAIN[-1]  # Already at lowest

    def get_status(self) -> dict[str, dict]:
        """Return a snapshot of all circuit states (for UI/debugging)."""
        result: dict[str, dict] = {}
        for name, entry in self._circuits.items():
            result[name] = {
                "state": entry.state.value,
                "failures": entry.failure_count,
                "successes": entry.success_count,
                "tripped": entry.state == CircuitState.OPEN,
            }
        return result