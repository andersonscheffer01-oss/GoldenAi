"""TurnManager tests — thread-safe authority, stale chunks, cross-thread cancel."""

import asyncio
import threading
import time
import pytest

from jarvis_core.streaming.turn_manager import TurnManager


class TestTurnManagerAuthority:
    """Test TurnManager as single authority for turn IDs."""

    def test_new_turn_increments_id(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        t2 = tm.new_turn()
        t3 = tm.new_turn()
        assert t1 == 1
        assert t2 == 2
        assert t3 == 3

    def test_current_turn_id(self):
        tm = TurnManager()
        assert tm.current_turn_id == 0
        t1 = tm.new_turn()
        assert tm.current_turn_id == t1
        t2 = tm.new_turn()
        assert tm.current_turn_id == t2

    def test_new_turn_cancels_previous(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        t2 = tm.new_turn()
        # t1 should be cancelled
        assert tm.is_cancelled(t1) is True
        assert tm.is_cancelled(t2) is False


class TestStaleChunkProtection:
    """Test stale chunk detection."""

    def test_is_stale_current_turn(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        assert tm.is_stale(t1) is False

    def test_is_stale_old_turn(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        t2 = tm.new_turn()
        assert tm.is_stale(t1) is True
        assert tm.is_stale(t2) is False

    def test_is_stale_unknown_turn(self):
        tm = TurnManager()
        assert tm.is_stale(999) is True

    def test_stale_turn_101_after_102(self):
        """Test the specific scenario: turn 101 stale after turn 102."""
        tm = TurnManager()
        for i in range(1, 103):
            turn_id = tm.new_turn()
        # Turn 101 should be stale
        assert tm.is_stale(101) is True
        assert tm.is_stale(102) is False
        # Cancel event for 101 should be set
        assert tm.get_cancel_event(101).is_set() is True
        # Cancel event for 102 should NOT be set
        assert tm.get_cancel_event(102).is_set() is False


class TestCrossThreadCancel:
    """Test cross-thread cancellation via threading.Event."""

    def test_cancel_event_is_threading_event(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        event = tm.get_cancel_event(t1)
        assert isinstance(event, threading.Event)

    def test_cancel_current_sets_event(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        event = tm.get_cancel_event(t1)
        assert event.is_set() is False
        tm.cancel_current()
        assert event.is_set() is True

    def test_cancel_specific_turn(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        t2 = tm.new_turn()
        tm.cancel_turn(t1)
        assert tm.get_cancel_event(t1).is_set() is True
        assert tm.get_cancel_event(t2).is_set() is False

    def test_cross_thread_cancel(self):
        """Test cancel from another thread reaches the event."""
        tm = TurnManager()
        t1 = tm.new_turn()
        event = tm.get_cancel_event(t1)

        results = []

        def cancel_from_frame_loop():
            time.sleep(0.05)
            tm.cancel_current()
            results.append("cancelled")

        thread = threading.Thread(target=cancel_from_frame_loop)
        thread.start()

        # Wait and check
        assert not event.is_set()
        time.sleep(0.15)
        assert event.is_set()
        assert "cancelled" in results

        thread.join()

    def test_concurrent_new_turn(self):
        """Test concurrent calls to new_turn from multiple threads."""
        tm = TurnManager()
        turn_ids = []

        def create_turn():
            tid = tm.new_turn()
            turn_ids.append(tid)

        threads = [threading.Thread(target=create_turn) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All turn IDs should be unique
        assert len(set(turn_ids)) == 10
        # Current turn should be the last one
        assert tm.current_turn_id == max(turn_ids)


class TestCleanup:
    """Test cleanup methods."""

    def test_cleanup_turn(self):
        tm = TurnManager()
        t1 = tm.new_turn()
        t2 = tm.new_turn()
        tm.cleanup_turn(t1)
        # After cleanup, get_cancel_event returns None
        assert tm.get_cancel_event(t1) is None
        assert tm.get_cancel_event(t2) is not None

    def test_cleanup_all(self):
        tm = TurnManager()
        tm.new_turn()
        tm.new_turn()
        tm.cleanup_all()
        assert tm.current_turn_id == 0
        assert tm.get_cancel_event(1) is None
        assert tm.get_cancel_event(2) is None

    def test_is_cancelled_unknown_turn(self):
        tm = TurnManager()
        assert tm.is_cancelled(999) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
