"""Clocks used by the durable background-task scheduler."""
from __future__ import annotations

import threading
import time


class SystemClock:
    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FakeClock(SystemClock):
    """Deterministic clock for scheduler tests; never sleeps the process."""

    def __init__(self, value: float = 0.0):
        self._value = float(value)
        self._lock = threading.RLock()

    def now(self) -> float:
        with self._lock:
            return self._value

    def advance(self, seconds: float) -> float:
        with self._lock:
            self._value += float(seconds)
            return self._value

    def set(self, value: float) -> None:
        with self._lock:
            self._value = float(value)

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


__all__ = ["FakeClock", "SystemClock"]
