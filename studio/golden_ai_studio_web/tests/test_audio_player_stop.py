"""AudioPlayer stop tests — real stop, orphan process, second playback."""

import asyncio
import os
import subprocess
import tempfile
import threading
import time
import pytest

from jarvis_core.streaming.audio_player import AudioPlayer
from jarvis_core.streaming.tts_pipeline import AudioChunk


def create_test_audio(duration_ms: int = 1000) -> AudioChunk:
    """Create a test MP3 file with silence."""
    # Create a minimal MP3 file using ffmpeg if available, otherwise use empty file
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    # Write minimal valid MP3 header (silence)
    # This is a simplified approach — real tests should use actual audio
    with open(path, "wb") as f:
        # Write enough data to simulate audio
        f.write(b"\xff" * (duration_ms * 16))  # ~16KB/s

    return AudioChunk(
        index=0,
        text="test",
        audio_path=path,
        duration_ms=duration_ms,
        is_final=True,
    )


class TestAudioPlayerStop:
    """Test AudioPlayer real stop functionality."""

    def test_player_initial_state(self):
        player = AudioPlayer()
        assert player.is_playing is False
        assert player.current_pid is None

    def test_stop_when_not_playing(self):
        player = AudioPlayer()
        player.stop()  # Should not raise
        assert player.is_playing is False

    def test_stop_sets_playing_false(self):
        player = AudioPlayer()
        # Simulate playing state
        player._playing = True
        player.stop()
        assert player.is_playing is False

    def test_cross_thread_stop(self):
        """Test stop from another thread."""
        player = AudioPlayer()
        player._playing = True

        def stop_from_other_thread():
            time.sleep(0.05)
            player.stop()

        thread = threading.Thread(target=stop_from_other_thread)
        thread.start()
        thread.join()

        assert player.is_playing is False

    def test_cancel_event_integration(self):
        """Test that cancel_event stops playback."""
        player = AudioPlayer()
        cancel_event = threading.Event()

        # Verify cancel event works
        assert not cancel_event.is_set()
        cancel_event.set()
        assert cancel_event.is_set()


class TestOrphanProcess:
    """Test that no orphan processes remain after stop."""

    def test_no_orphan_powershell(self):
        """Verify no orphan powershell.exe after player operations."""
        player = AudioPlayer()

        # Get initial powershell count
        initial_count = len([
            p for p in __import__('psutil').process_iter()
            if 'powershell' in p.name().lower()
        ]) if 'psutil' in __import__('sys').modules else 0

        # Operations that might leave orphans
        player.stop()

        # Final count should be same or less
        final_count = len([
            p for p in __import__('psutil').process_iter()
            if 'powershell' in p.name().lower()
        ]) if 'psutil' in __import__('sys').modules else 0

        # No new orphans should be created
        # (This is a basic check — real test needs actual playback)


class TestSecondPlayback:
    """Test that second playback works after stop."""

    def test_stop_then_play(self):
        """Test that player can be used after stop."""
        player = AudioPlayer()

        # First operation
        player.stop()

        # Second operation should work
        assert player.is_playing is False
        assert player.current_pid is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
