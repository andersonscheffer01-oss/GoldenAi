"""P1.4C Integration test — uses REAL production objects.

Simulates barge-in flow WITHOUT hardware.
Tests that VoiceService state machine, follow-up flag, conversation context,
and wake bypass all work correctly through real production code paths.

Production code paths tested:
  - _barge_in_monitor_loop() — sets _barge_in_followup_active, _utterance_source,
    _barge_in_cancel, _turn_manager.cancel_current()
  - _loop() follow-up path — checks _barge_in_followup_active, calls
    _capture_followup_after_barge_in(), bypasses wake word
"""

import os
import sys
import time
import threading
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["JARVIS_STREAMING_VOICE"] = "1"
os.environ["JARVIS_BARGE_IN"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from jarvis_core.voice_service import VoiceService
from jarvis_core.streaming.turn_manager import TurnManager
from jarvis_core.streaming.tts_pipeline import AudioChunk


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _make_speech_frames(num_blocks=20, rms_value=3000):
    """Generate int16 frames with high RMS (simulates user speech)."""
    return [np.full(1024, rms_value, dtype=np.int16) for _ in range(num_blocks)]


def _make_silence_frames(num_blocks=5, rms_value=50):
    """Generate int16 frames with low RMS (simulates silence)."""
    return [np.full(1024, rms_value, dtype=np.int16) for _ in range(num_blocks)]


def _mock_sounddevice_stream(speech_frames, frame_idx=None):
    """Create a mocked sounddevice.InputStream that yields speech frames."""
    if frame_idx is None:
        frame_idx = [0]

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)

    def _read(n):
        idx = frame_idx[0] % len(speech_frames)
        frame = speech_frames[idx]
        frame_idx[0] += 1
        return (frame, 0)

    mock_stream.read = MagicMock(side_effect=_read)
    return mock_stream


def _setup_conversation(vs):
    """Set up an active conversation with one user turn."""
    vs._conversation_messages.append({"role": "user", "content": "me explique o projeto Golden"})
    vs.state = "SPEAKING"
    vs._speaking_event.set()
    return vs._turn_manager.new_turn()


# ═══════════════════════════════════════════════════════════════
# TEST: Production handler sets flags correctly (no manual setup)
# ═══════════════════════════════════════════════════════════════

class TestBargeInProductionHandler:
    """Integration test: run real _barge_in_monitor_loop with mocked hardware.

    Only mocks: sounddevice.InputStream (microphone).
    Production code handles: state transitions, flag setting, turn cancellation.
    """

    def test_monitor_sets_followup_flag_via_production_code(self):
        """Run real _barge_in_monitor_loop — it must set all barge-in flags."""
        vs = VoiceService()
        turn1 = _setup_conversation(vs)

        session_before = vs._session_id
        conversation_before = vs._conversation_id

        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        # Run monitor — production code sets the flags
        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked unavailable")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        # === Assert: production code set these flags ===
        assert vs._barge_in_followup_active is True, \
            "PRODUCTION CODE must set _barge_in_followup_active"
        assert vs._utterance_source == "BARGE_IN", \
            "PRODUCTION CODE must set _utterance_source"
        assert vs._barge_in_cancel.is_set(), \
            "PRODUCTION CODE must set _barge_in_cancel"
        assert vs._turn_manager.is_cancelled(turn1), \
            "PRODUCTION CODE must cancel the current turn"
        assert vs._session_id == session_before, \
            "Session ID must NOT change during barge-in"
        assert vs._conversation_id == conversation_before, \
            "Conversation ID must NOT change during barge-in"

    def test_monitor_preserves_existing_context(self):
        """Verify barge-in monitor does NOT clear conversation messages."""
        vs = VoiceService()
        _setup_conversation(vs)

        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        # Previous user turn still present
        user_turns = [m for m in vs._conversation_messages if m["role"] == "user"]
        assert len(user_turns) == 1
        assert user_turns[0]["content"] == "me explique o projeto Golden"

    def test_monitor_does_not_touch_conversation_messages(self):
        """Monitor must not append or remove from _conversation_messages."""
        vs = VoiceService()
        _setup_conversation(vs)
        msgs_before = len(vs._conversation_messages)

        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        assert len(vs._conversation_messages) == msgs_before


# ═══════════════════════════════════════════════════════════════
# TEST: Follow-up transition via real _loop() path
# ═══════════════════════════════════════════════════════════════

class TestFollowupTransitionViaProductionLoop:
    """Test the _loop() follow-up path.

    Phase 1: Run monitor (mocked hardware) → flags set by production code.
    Phase 2: Run _loop() → processes follow-up, bypasses wake word.
    """

    def test_followup_processed_by_production_loop(self):
        """Full chain: monitor sets flags → _loop() processes follow-up."""
        vs = VoiceService()
        vs.enabled = True
        vs._voice = MagicMock()

        turn1 = _setup_conversation(vs)
        session_before = vs._session_id
        conversation_before = vs._conversation_id

        # ── Phase 1: Run monitor with mocked hardware ──
        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        # Verify monitor set the flags
        assert vs._barge_in_followup_active is True
        assert vs._utterance_source == "BARGE_IN"

        # ── Phase 2: Run _loop() — it picks up the flags ──
        mock_record = {
            "ok": True,
            "audio": b"\x00" * 32000,  # 1 second simulated audio
            "samplerate": 16000,
            "duration_ms": 1000.0,
            "utterance_id": "test_followup",
            "speech_detected": True,
            "preroll_frames": 0,
        }

        handle_calls = []

        def fake_handle(command, timings=None, decision=None, output=None):
            handle_calls.append({"command": command, "timings": timings or {}})

        with patch.object(vs, "_capture_followup_after_barge_in", return_value=mock_record):
            with patch.object(vs._voice, "transcribe_audio_bytes",
                              return_value={"ok": True, "text": "não, quero saber somente da memória"}):
                with patch.object(vs, "_stop_barge_in_monitor"):
                    with patch.object(vs, "_handle", side_effect=fake_handle):
                        with patch.object(vs._voice, "record_until_silence",
                                          return_value={"ok": True, "speech_detected": False,
                                                         "utterance_id": "idle"}):
                            vs.stop_event = threading.Event()
                            threading.Timer(2.0, vs.stop_event.set).start()
                            vs._loop()

        # === Assert: production _loop() processed follow-up ===
        assert vs._barge_in_followup_active is False, \
            "_loop() must reset _barge_in_followup_active after processing"
        assert vs._utterance_source == "", \
            "_loop() must reset _utterance_source after processing"

        # _handle was called with the follow-up command
        assert len(handle_calls) == 1, \
            "_loop() must call _handle() once for the follow-up"
        assert handle_calls[0]["command"] == "não, quero saber somente da memória"
        assert handle_calls[0]["timings"].get("barge_in_followup") is True
        assert handle_calls[0]["timings"].get("utterance_source") == "BARGE_IN"

        # Session/conversation IDs preserved
        assert vs._session_id == session_before
        assert vs._conversation_id == conversation_before

    def test_followup_bypasses_wake_word_check(self):
        """Verify _loop() does NOT go to WAITING_WAKE when follow-up is active."""
        vs = VoiceService()
        vs.enabled = True
        vs._voice = MagicMock()

        _setup_conversation(vs)

        # Run monitor to set flags via production code
        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        # Run _loop() — it should process follow-up, not wait for wake word
        mock_record = {
            "ok": True, "audio": b"\x00" * 32000, "samplerate": 16000,
            "duration_ms": 1000.0, "utterance_id": "test", "speech_detected": True,
            "preroll_frames": 0,
        }

        state_log = []
        original_setattr = object.__setattr__

        def track_state(obj, name, value):
            if name == "state":
                state_log.append(value)
            original_setattr(obj, name, value)

        with patch.object(vs, "_capture_followup_after_barge_in", return_value=mock_record):
            with patch.object(vs._voice, "transcribe_audio_bytes",
                              return_value={"ok": True, "text": "quero saber da memória"}):
                with patch.object(vs, "_stop_barge_in_monitor"):
                    with patch.object(vs._voice, "record_until_silence",
                                      return_value={"ok": True, "speech_detected": False,
                                                     "utterance_id": "idle"}):
                        with patch.object(VoiceService, "__setattr__", track_state):
                            vs.stop_event = threading.Event()
                            threading.Timer(2.0, vs.stop_event.set).start()
                            vs._loop()

        # State must include CAPTURING_FOLLOWUP (set by production _loop())
        assert "CAPTURING_FOLLOWUP" in state_log, \
            "_loop() must enter CAPTURING_FOLLOWUP state for barge-in follow-up"
        # State must NOT include WAITING_WAKE before CAPTURING_FOLLOWUP
        idx_capture = state_log.index("CAPTURING_FOLLOWUP")
        wake_before = [s for s in state_log[:idx_capture] if s == "WAITING_WAKE"]
        assert len(wake_before) == 0, \
            "_loop() must NOT go to WAITING_WAKE when barge-in follow-up is active"


# ═══════════════════════════════════════════════════════════════
# TEST: Context preservation (deterministic, no hardware)
# ═══════════════════════════════════════════════════════════════

class TestConversationContextPreservation:
    """Verify conversation messages survive across cancelled turns."""

    def test_conversation_context_not_cleared(self):
        vs = VoiceService()

        vs._conversation_messages.append({"role": "user", "content": "me explique o Golden"})
        turn1 = vs._turn_manager.new_turn()

        vs._turn_manager.cancel_current()

        assert len(vs._conversation_messages) == 1
        assert vs._conversation_messages[0]["content"] == "me explique o Golden"

        vs._conversation_messages.append({"role": "user", "content": "quero saber da memória"})
        assert len(vs._conversation_messages) == 2

    def test_session_persists_across_barge_in(self):
        vs = VoiceService()
        session_before = vs._session_id
        conv_before = vs._conversation_id

        turn1 = vs._turn_manager.new_turn()
        vs._turn_manager.cancel_current()

        assert vs._session_id == session_before
        assert vs._conversation_id == conv_before

    def test_followup_adds_user_turn_preserves_session(self):
        """Simulate the context update that _loop() does after follow-up."""
        vs = VoiceService()
        session_before = vs._session_id
        conv_before = vs._conversation_id

        vs._conversation_messages.append({"role": "user", "content": "me explique o projeto Golden"})

        # Follow-up arrives (in production, _loop() does this)
        vs._conversation_messages.append({"role": "user", "content": "não, quero saber somente da memória"})

        user_turns = [m for m in vs._conversation_messages if m["role"] == "user"]
        assert len(user_turns) == 2
        assert user_turns[0]["content"] == "me explique o projeto Golden"
        assert user_turns[1]["content"] == "não, quero saber somente da memória"

        # Only 2 messages — no assistant response (not added in this flow)
        assert len(vs._conversation_messages) == 2

        assert vs._session_id == session_before
        assert vs._conversation_id == conv_before


# ═══════════════════════════════════════════════════════════════
# TEST: Utterance source metadata
# ═══════════════════════════════════════════════════════════════

class TestUtteranceSourceMetadata:
    def test_initial_source_is_empty(self):
        vs = VoiceService()
        assert vs._utterance_source == ""

    def test_source_set_to_barge_in_by_monitor(self):
        """Verify monitor sets _utterance_source to BARGE_IN."""
        vs = VoiceService()
        _setup_conversation(vs)

        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        assert vs._utterance_source == "BARGE_IN"

    def test_source_cleared_after_followup_processing(self):
        """Verify _loop() clears _utterance_source after processing."""
        vs = VoiceService()
        vs.enabled = True
        vs._voice = MagicMock()
        _setup_conversation(vs)

        # Run monitor
        speech_frames = _make_speech_frames(num_blocks=20, rms_value=3000)
        mock_stream = _mock_sounddevice_stream(speech_frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with patch.dict(os.environ, {"JARVIS_BARGE_IN_GRACE_SECONDS": "0"}):
                with patch("jarvis_core.realtime_voice.vad._find_silero_onnx",
                           side_effect=Exception("VAD mocked")):
                    vs._barge_in_monitor_stop.clear()
                    vs._barge_in_monitor_loop()

        assert vs._utterance_source == "BARGE_IN"

        # Run _loop()
        mock_record = {
            "ok": True, "audio": b"\x00" * 32000, "samplerate": 16000,
            "duration_ms": 1000.0, "utterance_id": "t", "speech_detected": True,
            "preroll_frames": 0,
        }

        with patch.object(vs, "_capture_followup_after_barge_in", return_value=mock_record):
            with patch.object(vs._voice, "transcribe_audio_bytes",
                              return_value={"ok": True, "text": "teste"}):
                with patch.object(vs, "_stop_barge_in_monitor"):
                    with patch.object(vs._voice, "record_until_silence",
                                      return_value={"ok": True, "speech_detected": False,
                                                     "utterance_id": "idle"}):
                        vs.stop_event = threading.Event()
                        threading.Timer(2.0, vs.stop_event.set).start()
                        vs._loop()

        assert vs._utterance_source == ""


# ═══════════════════════════════════════════════════════════════
# TEST: Pre-roll buffer
# ═══════════════════════════════════════════════════════════════

class TestPrerollBuffer:
    def test_preroll_buffer_circular(self):
        vs = VoiceService()

        for i in range(20):
            frame = np.array([i], dtype=np.int16)
            vs._barge_in_pre_roll.append(frame)
            if len(vs._barge_in_pre_roll) > vs._barge_in_preroll_max_blocks:
                vs._barge_in_pre_roll.pop(0)

        assert len(vs._barge_in_pre_roll) == vs._barge_in_preroll_max_blocks
        assert vs._barge_in_pre_roll[0][0] == 12
        assert vs._barge_in_pre_roll[-1][0] == 19


# ═══════════════════════════════════════════════════════════════
# TEST: Entry points exist
# ═══════════════════════════════════════════════════════════════

class TestVoiceServiceEntryPoint:
    def test_has_capture_followup(self):
        vs = VoiceService()
        assert hasattr(vs, "_capture_followup_after_barge_in")
        assert callable(vs._capture_followup_after_barge_in)

    def test_has_barge_in_followup_active(self):
        vs = VoiceService()
        assert hasattr(vs, "_barge_in_followup_active")
        assert vs._barge_in_followup_active is False

    def test_has_utterance_source(self):
        vs = VoiceService()
        assert hasattr(vs, "_utterance_source")
        assert vs._utterance_source == ""

    def test_has_conversation_id(self):
        vs = VoiceService()
        assert hasattr(vs, "_conversation_id")
        assert isinstance(vs._conversation_id, str)
        assert len(vs._conversation_id) > 0

    def test_has_session_id(self):
        vs = VoiceService()
        assert hasattr(vs, "_session_id")
        assert isinstance(vs._session_id, str)

    def test_has_preroll_buffer(self):
        vs = VoiceService()
        assert hasattr(vs, "_barge_in_pre_roll")
        assert isinstance(vs._barge_in_pre_roll, list)

    def test_has_user_audio_buffer(self):
        vs = VoiceService()
        assert hasattr(vs, "_barge_in_user_audio")
        assert isinstance(vs._barge_in_user_audio, list)

    def test_has_barge_in_monitor_loop(self):
        vs = VoiceService()
        assert hasattr(vs, "_barge_in_monitor_loop")
        assert callable(vs._barge_in_monitor_loop)


# ═══════════════════════════════════════════════════════════════
# TEST: Streaming context — _handle_streaming with build_messages
# ═══════════════════════════════════════════════════════════════

class TestStreamingContextFix:
    """Verify _handle_streaming uses brain.build_messages (not broken _build_messages).

    Tests the fix for the AttributeError bug where brain._build_messages
    did not exist, causing streaming to crash before adding user turns
    to conversation context.
    """

    def test_handle_streaming_no_attribute_error(self):
        """_handle_streaming must not crash with AttributeError."""
        from jarvis_core.streaming.orchestrator import Chunk

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        # Set up conversation context
        vs._conversation_messages.append({"role": "user", "content": "me explique o projeto Golden"})
        session_before = vs._session_id
        conv_before = vs._conversation_id

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_prose(messages, model):
                yield "O Golden é um sistema de trading."
            mock_stream.side_effect = mock_prose

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = [
                    Chunk(index=0, text="O Golden é um sistema de trading.", is_final=True)
                ]
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.synthesize_and_get = AsyncMock(return_value=AudioChunk(
                        index=0, text="O Golden", audio_path=None,
                        duration_ms=100, is_final=True,
                    ))
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer") as mock_player:
                        mock_player.return_value.play = AsyncMock(return_value=100)
                        mock_player.return_value.wait_for_speech_end = AsyncMock()
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            # build_messages must return a valid list (not crash)
                            mock_brain.return_value.build_messages.return_value = [
                                {"role": "system", "content": "test"},
                                {"role": "user", "content": "não, quero saber somente da memória"},
                            ]
                            result = vs._handle_streaming(
                                "não, quero saber somente da memória", {})

                            assert result["handled"] is True

    def test_build_messages_receives_conversation_history(self):
        """brain.build_messages must receive conversation_history from VoiceService."""
        from jarvis_core.streaming.orchestrator import Chunk

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        vs._conversation_messages.append({"role": "user", "content": "me explique o projeto Golden"})

        captured_messages = []

        def fake_build_messages(user_input, memory_context="", source="text",
                                voice_capture=False, conversation_history=None, profile=None):
            msgs = [{"role": "system", "content": "test"}]
            if conversation_history:
                for m in conversation_history:
                    msgs.append({"role": m["role"], "content": m["content"]})
            msgs.append({"role": "user", "content": user_input})
            captured_messages.append(msgs)
            return msgs

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_prose(messages, model):
                yield "resposta"
            mock_stream.side_effect = mock_prose

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = [
                    Chunk(index=0, text="resposta", is_final=True)
                ]
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.synthesize_and_get = AsyncMock(return_value=AudioChunk(
                        index=0, text="r", audio_path=None,
                        duration_ms=50, is_final=True,
                    ))
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer") as mock_player:
                        mock_player.return_value.play = AsyncMock(return_value=50)
                        mock_player.return_value.wait_for_speech_end = AsyncMock()
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            mock_brain.return_value.build_messages.side_effect = fake_build_messages
                            vs._handle_streaming("não, quero saber da memória", {})

        # build_messages was called
        assert len(captured_messages) == 1
        msgs = captured_messages[0]
        # Conversation history (previous user turn) is in the messages
        user_contents = [m["content"] for m in msgs if m["role"] == "user"]
        assert "me explique o projeto Golden" in user_contents
        # New user turn is also present
        assert "não, quero saber da memória" in user_contents

    def test_user_turn_appended_before_build_messages(self):
        """User turn must be in _conversation_messages BEFORE build_messages is called."""
        from jarvis_core.streaming.orchestrator import Chunk

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        vs._conversation_messages.append({"role": "user", "content": "me explique o projeto Golden"})
        msgs_at_build_time = []

        def fake_build_messages(user_input, memory_context="", source="text",
                                voice_capture=False, conversation_history=None, profile=None):
            # Capture conversation state AT THE MOMENT build_messages is called
            msgs_at_build_time.append(list(vs._conversation_messages))
            return [{"role": "user", "content": user_input}]

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_prose(messages, model):
                yield "ok"
            mock_stream.side_effect = mock_prose

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = [
                    Chunk(index=0, text="ok", is_final=True)
                ]
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.synthesize_and_get = AsyncMock(return_value=AudioChunk(
                        index=0, text="o", audio_path=None,
                        duration_ms=50, is_final=True,
                    ))
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer") as mock_player:
                        mock_player.return_value.play = AsyncMock(return_value=50)
                        mock_player.return_value.wait_for_speech_end = AsyncMock()
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            mock_brain.return_value.build_messages.side_effect = fake_build_messages
                            vs._handle_streaming("novo comando", {})

        # At build_messages time, user turn was already appended
        assert len(msgs_at_build_time) == 1
        contents = [m["content"] for m in msgs_at_build_time[0]]
        assert "novo comando" in contents
        assert "me explique o projeto Golden" in contents

    def test_assistant_response_appended_after_streaming(self):
        """Assistant response enters _conversation_messages after successful streaming."""
        from jarvis_core.streaming.orchestrator import Chunk

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        vs._conversation_messages.append({"role": "user", "content": "me explique o projeto Golden"})

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_prose(messages, model):
                yield "O Golden é um sistema de trading."
            mock_stream.side_effect = mock_prose

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = [
                    Chunk(index=0, text="O Golden é um sistema de trading.", is_final=True)
                ]
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.synthesize_and_get = AsyncMock(return_value=AudioChunk(
                        index=0, text="O Golden", audio_path=None,
                        duration_ms=100, is_final=True,
                    ))
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer") as mock_player:
                        mock_player.return_value.play = AsyncMock(return_value=100)
                        mock_player.return_value.wait_for_speech_end = AsyncMock()
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            mock_brain.return_value.build_messages.return_value = [
                                {"role": "user", "content": "novo"},
                            ]
                            vs._handle_streaming("novo", {})

        # user1 + follow-up user + assistant response = 3 messages
        roles = [m["role"] for m in vs._conversation_messages]
        assert roles.count("user") == 2
        assert roles.count("assistant") == 1
        # Assistant response is the last message
        assert vs._conversation_messages[-1]["role"] == "assistant"
        assert "Golden" in vs._conversation_messages[-1]["content"]

    def test_session_ids_unchanged_after_streaming(self):
        """Session and conversation IDs must not change during streaming."""
        from jarvis_core.streaming.orchestrator import Chunk

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        session_before = vs._session_id
        conv_before = vs._conversation_id

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_prose(messages, model):
                yield "ok"
            mock_stream.side_effect = mock_prose

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = [
                    Chunk(index=0, text="ok", is_final=True)
                ]
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.synthesize_and_get = AsyncMock(return_value=AudioChunk(
                        index=0, text="o", audio_path=None,
                        duration_ms=50, is_final=True,
                    ))
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer") as mock_player:
                        mock_player.return_value.play = AsyncMock(return_value=50)
                        mock_player.return_value.wait_for_speech_end = AsyncMock()
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            mock_brain.return_value.build_messages.return_value = []
                            vs._handle_streaming("teste", {})

        assert vs._session_id == session_before
        assert vs._conversation_id == conv_before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
