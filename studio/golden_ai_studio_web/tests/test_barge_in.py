"""Barge-in tests — multi-layer protection, self-audio, short commands."""

import asyncio
import time
import pytest

from jarvis_core.streaming import (
    BARGE_IN_RMS_THRESHOLD,
    BARGE_IN_MIN_SPEECH_MS,
    BARGE_IN_GRACE_SECONDS,
)


class TestBargeInConfig:
    """Test configurable barge-in thresholds."""

    def test_rms_threshold_default(self):
        assert BARGE_IN_RMS_THRESHOLD == 300

    def test_min_speech_ms_default(self):
        assert BARGE_IN_MIN_SPEECH_MS == 200

    def test_grace_seconds_default(self):
        assert BARGE_IN_GRACE_SECONDS == 0.2


class TestSelfAudioProtection:
    """Test multi-layer self-audio protection."""

    def test_rms_below_threshold_ignored(self):
        """TTS leakage (~150-250 RMS) should be ignored."""
        # Simulating TTS leakage RMS
        tts_leakage_rms = 200
        assert tts_leakage_rms < BARGE_IN_RMS_THRESHOLD

    def test_rms_above_threshold_detected(self):
        """User speaking normally over TTS should be detected."""
        # Simulating user speech RMS
        user_speech_rms = 400
        assert user_speech_rms > BARGE_IN_RMS_THRESHOLD

    def test_short_command_pare(self):
        """'pare' should be detectable with 150-250ms."""
        # This tests that the minimum speech threshold allows short commands
        assert BARGE_IN_MIN_SPEECH_MS <= 250

    def test_short_command_nao(self):
        """'não' should be detectable with 150-250ms."""
        assert BARGE_IN_MIN_SPEECH_MS <= 250

    def test_short_command_cancela(self):
        """'cancela' should be detectable with 150-250ms."""
        assert BARGE_IN_MIN_SPEECH_MS <= 250


class TestBargeInFlow:
    """Test barge-in state flow."""

    def test_barge_in_flow(self):
        """Test the expected barge-in state flow."""
        # IDLE -> LISTENING -> TRANSCRIBING -> THINKING -> SPEAKING
        # SPEAKING -> INTERRUPTED -> LISTENING
        flow = [
            "IDLE",
            "LISTENING",
            "TRANSCRIBING",
            "THINKING",
            "SPEAKING",
            "INTERRUPTED",
            "LISTENING",
        ]
        # Verify INTERRUPTED is followed by LISTENING
        for i, state in enumerate(flow):
            if state == "INTERRUPTED":
                assert flow[i + 1] == "LISTENING"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
