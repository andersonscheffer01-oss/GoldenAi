"""
Testes do Realtime Voice Adapter — P1.4
========================================
Unit tests para os componentes adaptados do pipeline OSS.
SEM microfone real. SEM rede. SEM TTS. Tudo mockado ou sintético.

    python -m unittest tests.test_realtime_voice_adapter -v
"""

import asyncio
import os
import struct
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.realtime_voice.constants import (
    AUDIO_QUEUE_MAXSIZE,
    FRAME_BYTES,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    VAD_WINDOW_BYTES,
    VAD_WINDOW_SAMPLES,
)
from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue, UtteranceBuffer
from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    IllegalTransition,
    VoiceStateMachine,
)
from jarvis_core.realtime_voice.barge_in import BargeInController
from jarvis_core.realtime_voice.constants import BARGE_IN_GRACE_SECONDS
from jarvis_core.realtime_voice.integration import (
    RealtimeVoicePipeline,
    rms_energy,
)
from jarvis_core.realtime_voice.vad import (
    SileroVADAdapter,
    VADEvent,
    _Internal,
    VADModelMissingError,
)
from jarvis_core.realtime_voice import is_enabled, FEATURE_FLAG, is_hybrid_enabled, HYBRID_FLAG


def _make_speech_frame(amplitude: int = 8000, num_samples: int = FRAME_SAMPLES) -> bytes:
    """Generate a synthetic speech-like PCM frame."""
    import numpy as np
    t = np.arange(num_samples, dtype=np.float32)
    signal = (amplitude * np.sin(2 * np.pi * 440 * t / SAMPLE_RATE)).astype(np.int16)
    return signal.tobytes()


def _make_silence_frame(num_samples: int = FRAME_SAMPLES) -> bytes:
    """Generate a silence frame."""
    return b"\x00\x00" * num_samples


def _make_wav_bytes(num_samples: int = 1000, amplitude: int = 3000) -> bytes:
    """Generate WAV bytes for testing."""
    import io
    import wave
    import numpy as np
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        signal = (amplitude * np.sin(
            2 * np.pi * 440 * np.arange(num_samples, dtype=np.float32) / SAMPLE_RATE
        )).astype(np.int16)
        wf.writeframes(signal.tobytes())
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════
# FEATURE FLAG
# ═══════════════════════════════════════════════════════════════════


class TestFeatureFlag(unittest.TestCase):
    def test_default_disabled(self):
        env = os.environ.copy()
        env.pop(FEATURE_FLAG, None)
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_enabled())

    def test_enabled_when_set(self):
        with patch.dict(os.environ, {FEATURE_FLAG: "1"}):
            self.assertTrue(is_enabled())

    def test_disabled_when_zero(self):
        with patch.dict(os.environ, {FEATURE_FLAG: "0"}):
            self.assertFalse(is_enabled())


# ═══════════════════════════════════════════════════════════════════
# AUDIO QUEUE
# ═══════════════════════════════════════════════════════════════════


class TestAudioFrameQueue(unittest.TestCase):
    def test_put_get(self):
        q = AudioFrameQueue(maxsize=4)
        frame = _make_speech_frame()
        q.put_nowait(frame)
        self.assertEqual(q.qsize, 1)

    def test_wrong_frame_size_ignored(self):
        q = AudioFrameQueue(maxsize=4)
        q.put_nowait(b"\x00" * 100)  # wrong size
        self.assertTrue(q.empty)

    def test_backpressure_drops_oldest(self):
        q = AudioFrameQueue(maxsize=2)
        f1 = _make_speech_frame(amplitude=1000)
        f2 = _make_speech_frame(amplitude=2000)
        f3 = _make_speech_frame(amplitude=3000)
        q.put_nowait(f1)
        q.put_nowait(f2)
        q.put_nowait(f3)  # should drop f1
        self.assertEqual(q.qsize, 2)

    def test_cancel(self):
        q = AudioFrameQueue(maxsize=4)
        q.cancel()
        self.assertTrue(q.empty)

    def test_flush(self):
        q = AudioFrameQueue(maxsize=4)
        for _ in range(3):
            q.put_nowait(_make_speech_frame())
        dropped = q.flush()
        self.assertEqual(dropped, 3)
        self.assertTrue(q.empty)

    def test_async_get_returns_none_on_cancel(self):
        async def _test():
            q = AudioFrameQueue(maxsize=4)
            q.cancel()
            result = await q.get()
            self.assertIsNone(result)
        asyncio.run(_test())


class TestUtteranceBuffer(unittest.TestCase):
    def test_lifecycle(self):
        buf = UtteranceBuffer()
        self.assertFalse(buf.active)
        self.assertEqual(buf.sample_count, 0)

        buf.start()
        self.assertTrue(buf.active)

        frame = _make_speech_frame()
        buf.append(frame)
        self.assertEqual(buf.sample_count, FRAME_SAMPLES)

        buf.end()
        self.assertFalse(buf.active)
        self.assertGreater(buf.duration_ms, 0)

    def test_clear(self):
        buf = UtteranceBuffer()
        buf.start()
        buf.append(_make_speech_frame())
        buf.clear()
        self.assertFalse(buf.active)
        self.assertEqual(buf.sample_count, 0)

    def test_min_utterance_check(self):
        buf = UtteranceBuffer()
        buf.start()
        buf.append(_make_silence_frame(num_samples=100))
        buf.end()
        # Very short audio
        self.assertLess(buf.duration_ms, 500)


# ═══════════════════════════════════════════════════════════════════
# STATE MACHINE
# ═══════════════════════════════════════════════════════════════════


class TestVoiceStateMachine(unittest.TestCase):
    def test_initial_state(self):
        sm = VoiceStateMachine()
        self.assertEqual(sm.state, ConversationalState.IDLE)

    def test_valid_transitions(self):
        sm = VoiceStateMachine()
        sm.transition(ConversationalState.LISTENING)
        self.assertEqual(sm.state, ConversationalState.LISTENING)
        sm.transition(ConversationalState.THINKING)
        self.assertEqual(sm.state, ConversationalState.THINKING)
        sm.transition(ConversationalState.SPEAKING)
        self.assertEqual(sm.state, ConversationalState.SPEAKING)
        sm.transition(ConversationalState.IDLE)
        self.assertEqual(sm.state, ConversationalState.IDLE)

    def test_illegal_transition(self):
        sm = VoiceStateMachine()
        sm.transition(ConversationalState.LISTENING)
        with self.assertRaises(IllegalTransition):
            sm.transition(ConversationalState.SPEAKING)  # LISTENING -> SPEAKING illegal

    def test_self_transition_noop(self):
        sm = VoiceStateMachine()
        sm.transition(ConversationalState.IDLE)  # no-op
        self.assertEqual(sm.state, ConversationalState.IDLE)

    def test_force_idle(self):
        sm = VoiceStateMachine()
        sm.transition(ConversationalState.LISTENING)
        sm.force_idle()
        self.assertEqual(sm.state, ConversationalState.IDLE)

    def test_any_to_idle(self):
        for state in ConversationalState:
            if state == ConversationalState.ERROR:
                continue
            sm = VoiceStateMachine(initial=state)
            sm.force_idle()
            self.assertEqual(sm.state, ConversationalState.IDLE)

    def test_on_change_callback(self):
        changes = []
        sm = VoiceStateMachine(on_change=lambda old, new: changes.append((old, new)))
        sm.transition(ConversationalState.LISTENING)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], ConversationalState.IDLE)
        self.assertEqual(changes[0][1], ConversationalState.LISTENING)

    def test_can_barge_in(self):
        sm = VoiceStateMachine()
        self.assertFalse(sm.can_barge_in())
        sm.transition(ConversationalState.LISTENING)
        sm.transition(ConversationalState.THINKING)
        sm.transition(ConversationalState.SPEAKING)
        self.assertTrue(sm.can_barge_in())

    def test_is_listening_capable(self):
        sm = VoiceStateMachine()
        self.assertTrue(sm.is_listening_capable())
        sm.transition(ConversationalState.LISTENING)
        self.assertTrue(sm.is_listening_capable())
        sm.transition(ConversationalState.THINKING)
        self.assertFalse(sm.is_listening_capable())


# ═══════════════════════════════════════════════════════════════════
# BARGE-IN
# ═══════════════════════════════════════════════════════════════════


class TestBargeInController(unittest.TestCase):
    def _make_speaking_sm(self) -> VoiceStateMachine:
        sm = VoiceStateMachine()
        sm.transition(ConversationalState.LISTENING)
        sm.transition(ConversationalState.THINKING)
        sm.transition(ConversationalState.SPEAKING)
        return sm

    def test_no_barge_in_when_not_speaking(self):
        sm = VoiceStateMachine()
        bi = BargeInController(sm)
        self.assertFalse(bi.check_barge_in())

    def test_no_barge_in_during_grace(self):
        sm = self._make_speaking_sm()
        bi = BargeInController(sm, grace_seconds=0.5)
        bi.tts_started()
        # Immediately after TTS start — should be suppressed
        self.assertFalse(bi.check_barge_in())

    def test_barge_in_after_grace(self):
        sm = self._make_speaking_sm()
        bi = BargeInController(sm, grace_seconds=0.01)
        bi.tts_started()
        time.sleep(0.02)  # > grace
        self.assertTrue(bi.check_barge_in())

    def test_tts_lifecycle(self):
        sm = self._make_speaking_sm()
        bi = BargeInController(sm)
        self.assertFalse(bi.tts_active)
        bi.tts_started()
        self.assertTrue(bi.tts_active)
        bi.tts_ended()
        self.assertFalse(bi.tts_active)

    def test_self_audio_protection(self):
        sm = self._make_speaking_sm()
        bi = BargeInController(sm, self_audio_protection=True)
        bi.tts_started()
        self.assertTrue(bi.is_self_audio(600))
        bi.tts_ended()
        self.assertFalse(bi.is_self_audio(600))

    def test_self_audio_disabled(self):
        sm = self._make_speaking_sm()
        bi = BargeInController(sm, self_audio_protection=False)
        bi.tts_started()
        self.assertFalse(bi.is_self_audio(600))

    def test_reset(self):
        sm = self._make_speaking_sm()
        bi = BargeInController(sm)
        bi.tts_started()
        bi.reset()
        self.assertFalse(bi.tts_active)


# ═══════════════════════════════════════════════════════════════════
# VAD ADAPTER (unit tests — no real model)
# ═══════════════════════════════════════════════════════════════════


class TestSileroVADAdapter(unittest.TestCase):
    def test_init_defaults(self):
        vad = SileroVADAdapter()
        self.assertEqual(vad.speech_threshold, 0.5)
        self.assertEqual(vad.endpoint_ms, 700)
        self.assertFalse(vad.is_loaded)

    def test_init_custom_params(self):
        vad = SileroVADAdapter(speech_threshold=0.3, endpoint_ms=500)
        self.assertEqual(vad.speech_threshold, 0.3)
        self.assertEqual(vad.endpoint_ms, 500)

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            SileroVADAdapter(speech_threshold=1.5)
        with self.assertRaises(ValueError):
            SileroVADAdapter(speech_threshold=-0.1)

    def test_invalid_endpoint(self):
        with self.assertRaises(ValueError):
            SileroVADAdapter(endpoint_ms=0)

    def test_feed_without_load_returns_none(self):
        async def _test():
            vad = SileroVADAdapter()
            result = await vad.feed(_make_speech_frame())
            self.assertIsNone(result)
        asyncio.run(_test())

    def test_feed_wrong_frame_size(self):
        async def _test():
            vad = SileroVADAdapter()
            vad._session = MagicMock()  # pretend loaded
            result = await vad.feed(b"\x00" * 100)
            self.assertIsNone(result)
        asyncio.run(_test())

    def test_reset(self):
        vad = SileroVADAdapter()
        vad._internal = _Internal.SPEECH
        vad._silence_ms = 100
        vad._consecutive_speech_windows = 5
        vad.reset()
        self.assertEqual(vad._internal, _Internal.SILENCE)
        self.assertEqual(vad._silence_ms, 0)
        self.assertEqual(vad._consecutive_speech_windows, 0)

    def test_step_speech_start(self):
        vad = SileroVADAdapter(speech_start_windows=3)
        # 2 windows below threshold — should not fire
        self.assertIsNone(vad._step(0.4))
        self.assertIsNone(vad._step(0.4))
        # 3 consecutive windows above threshold — should fire on 3rd
        self.assertIsNone(vad._step(0.6))  # consecutive = 1
        self.assertIsNone(vad._step(0.6))  # consecutive = 2
        evt = vad._step(0.6)  # consecutive = 3 → fires
        self.assertEqual(evt, VADEvent.SPEECH_STARTED)
        self.assertEqual(vad._internal, _Internal.SPEECH)

    def test_step_endpoint(self):
        vad = SileroVADAdapter(endpoint_ms=700)
        vad._internal = _Internal.SPEECH
        # Speech continues
        self.assertIsNone(vad._step(0.6))
        # Silence begins
        self.assertIsNone(vad._step(0.3))  # silence_ms = 32
        # 20 more silence windows: total = 32 + 20*32 = 672 < 700
        for _ in range(20):
            self.assertIsNone(vad._step(0.3))
        # 22nd silence window: 672 + 32 = 704 >= 700 → ENDPOINT
        evt = vad._step(0.3)
        self.assertEqual(evt, VADEvent.ENDPOINT)

    def test_step_silence_resets_speech_counter(self):
        vad = SileroVADAdapter(speech_start_windows=3)
        vad._step(0.6)  # consecutive = 1
        vad._step(0.3)  # silence resets consecutive to 0
        vad._step(0.6)  # consecutive = 1 (restart)
        vad._step(0.6)  # consecutive = 2
        # Counter was reset, need 3 consecutive again
        evt = vad._step(0.6)  # consecutive = 3 → fires
        self.assertEqual(evt, VADEvent.SPEECH_STARTED)
        self.assertEqual(vad._internal, _Internal.SPEECH)


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION / PIPELINE
# ═══════════════════════════════════════════════════════════════════


class TestRmsEnergy(unittest.TestCase):
    def test_silence(self):
        frame = _make_silence_frame()
        energy = rms_energy(frame)
        self.assertEqual(energy, 0.0)

    def test_speech(self):
        frame = _make_speech_frame(amplitude=8000)
        energy = rms_energy(frame)
        self.assertGreater(energy, 1000)

    def test_empty_frame(self):
        energy = rms_energy(b"")
        self.assertEqual(energy, 0.0)


class TestRealtimeVoicePipeline(unittest.TestCase):
    def test_init(self):
        pipe = RealtimeVoicePipeline()
        self.assertEqual(pipe.state_machine.state, ConversationalState.IDLE)
        self.assertIsNotNone(pipe.barge_in)
        self.assertIsNotNone(pipe.queue)

    def test_stats_empty_init(self):
        pipe = RealtimeVoicePipeline()
        self.assertEqual(pipe.stats, {})


# ═══════════════════════════════════════════════════════════════════
# NETWORK / PRIVACY
# ═══════════════════════════════════════════════════════════════════


class TestPrivacy(unittest.TestCase):
    """Ensure no module-level network imports."""

    def test_vad_no_network_imports(self):
        import jarvis_core.realtime_voice.vad as mod
        source = open(mod.__file__).read()
        # Should not import requests, httpx, aiohttp, urllib at module level
        for bad in ["import requests", "import httpx", "import aiohttp",
                     "from requests", "from httpx", "from aiohttp"]:
            self.assertNotIn(bad, source, f"Found network import: {bad}")

    def test_audio_queue_no_network_imports(self):
        import jarvis_core.realtime_voice.audio_queue as mod
        source = open(mod.__file__).read()
        for bad in ["import requests", "import httpx", "import aiohttp"]:
            self.assertNotIn(bad, source)

    def test_state_machine_no_network_imports(self):
        import jarvis_core.realtime_voice.state_machine as mod
        source = open(mod.__file__).read()
        for bad in ["import requests", "import httpx", "import aiohttp"]:
            self.assertNotIn(bad, source)

    def test_barge_in_no_network_imports(self):
        import jarvis_core.realtime_voice.barge_in as mod
        source = open(mod.__file__).read()
        for bad in ["import requests", "import httpx", "import aiohttp"]:
            self.assertNotIn(bad, source)


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════


class TestConstants(unittest.TestCase):
    def test_frame_format(self):
        self.assertEqual(SAMPLE_RATE, 16000)
        self.assertEqual(FRAME_SAMPLES, 480)
        self.assertEqual(FRAME_BYTES, 960)

    def test_vad_window(self):
        self.assertEqual(VAD_WINDOW_SAMPLES, 512)
        self.assertEqual(VAD_WINDOW_BYTES, 1024)

    def test_queue_maxsize(self):
        self.assertEqual(AUDIO_QUEUE_MAXSIZE, 32)


# ═══════════════════════════════════════════════════════════════════
# MICROPHONE FAILURE (unit test simulation)
# ═══════════════════════════════════════════════════════════════════


class TestMicrophoneFailure(unittest.TestCase):
    def test_queue_handles_zero_frames(self):
        q = AudioFrameQueue(maxsize=4)
        self.assertTrue(q.empty)
        result = q.flush()
        self.assertEqual(result, 0)

    def test_utterance_buffer_no_frames(self):
        buf = UtteranceBuffer()
        buf.start()
        buf.end()
        self.assertEqual(buf.get_audio_bytes(), b"")


# ═══════════════════════════════════════════════════════════════════
# HYBRID ENDPOINT
# ═══════════════════════════════════════════════════════════════════


class TestHybridFeatureFlag(unittest.TestCase):
    def test_hybrid_default_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(HYBRID_FLAG, None)
            self.assertFalse(is_hybrid_enabled())

    def test_hybrid_enabled_when_set(self):
        with patch.dict(os.environ, {HYBRID_FLAG: "1"}):
            self.assertTrue(is_hybrid_enabled())

    def test_hybrid_disabled_when_zero(self):
        with patch.dict(os.environ, {HYBRID_FLAG: "0"}):
            self.assertFalse(is_hybrid_enabled())


class TestHybridEndpoint(unittest.TestCase):
    def _make(self, **kw):
        from jarvis_core.realtime_voice.hybrid_endpoint import HybridEndpoint
        return HybridEndpoint(**kw)

    def test_init_defaults(self):
        he = self._make()
        self.assertEqual(he.hangover_ms, 250)
        self.assertEqual(he.rms_threshold, 300.0)
        self.assertEqual(he.phase.value, "idle")
        self.assertFalse(he.in_hangover)

    def test_init_custom(self):
        he = self._make(hangover_ms=400, rms_threshold=500.0)
        self.assertEqual(he.hangover_ms, 400)
        self.assertEqual(he.rms_threshold, 500.0)

    def test_invalid_hangover(self):
        with self.assertRaises(ValueError):
            self._make(hangover_ms=-1)

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            self._make(rms_threshold=-1.0)

    def test_on_speech_started(self):
        he = self._make()
        he.on_speech_started()
        self.assertEqual(he.phase.value, "speech")
        self.assertFalse(he.in_hangover)

    def test_endpoint_candidate_opens_hangover(self):
        he = self._make(hangover_ms=250)
        he.on_speech_started()
        frame = _make_speech_frame()
        evt = he.on_endpoint_candidate(frame)
        self.assertIsNone(evt)
        self.assertTrue(he.in_hangover)
        self.assertEqual(he.phase.value, "hangover")
        self.assertEqual(len(he.get_tail_frames()), 1)

    def test_endpoint_candidate_hangover_disabled(self):
        he = self._make(hangover_ms=0)
        he.on_speech_started()
        evt = he.on_endpoint_candidate(_make_speech_frame())
        self.assertEqual(evt.value, "endpoint")
        self.assertFalse(he.in_hangover)

    def test_endpoint_candidate_not_in_speech(self):
        he = self._make()
        evt = he.on_endpoint_candidate(_make_speech_frame())
        self.assertEqual(evt.value, "endpoint")

    def test_feed_hangover_speech_detected(self):
        he = self._make(hangover_ms=250, rms_threshold=300.0)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_speech_frame())
        self.assertTrue(he.in_hangover)
        speech_frame = _make_speech_frame(amplitude=8000)
        evt = he.feed_hangover(speech_frame, rms_energy(speech_frame))
        self.assertEqual(evt.value, "speech_resumed")
        self.assertEqual(he.phase.value, "speech")
        self.assertEqual(len(he.get_tail_frames()), 0)

    def test_feed_hangover_expired(self):
        he = self._make(hangover_ms=1)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        self.assertTrue(he.in_hangover)
        time.sleep(0.01)
        silence = _make_silence_frame()
        evt = he.feed_hangover(silence, 0.0)
        self.assertEqual(evt.value, "endpoint")
        self.assertFalse(he.in_hangover)

    def test_feed_hangover_still_running(self):
        he = self._make(hangover_ms=500)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        silence = _make_silence_frame()
        evt = he.feed_hangover(silence, 0.0)
        self.assertIsNone(evt)
        self.assertTrue(he.in_hangover)

    def test_tail_frames_accumulate(self):
        he = self._make(hangover_ms=500)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        self.assertEqual(len(he.get_tail_frames()), 1)
        he.feed_hangover(_make_silence_frame(), 0.0)
        he.feed_hangover(_make_silence_frame(), 0.0)
        self.assertEqual(len(he.get_tail_frames()), 3)

    def test_tail_cleared_on_cancel(self):
        he = self._make(hangover_ms=500, rms_threshold=300.0)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        self.assertEqual(len(he.get_tail_frames()), 1)
        speech_frame = _make_speech_frame(amplitude=8000)
        he.feed_hangover(speech_frame, rms_energy(speech_frame))
        self.assertEqual(len(he.get_tail_frames()), 0)

    def test_tail_cleared_on_reset(self):
        he = self._make(hangover_ms=500)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        self.assertEqual(len(he.get_tail_frames()), 1)
        he.reset()
        self.assertEqual(len(he.get_tail_frames()), 0)
        self.assertEqual(he.phase.value, "idle")

    def test_rms_energy_silence(self):
        from jarvis_core.realtime_voice.hybrid_endpoint import rms_energy
        self.assertEqual(rms_energy(_make_silence_frame()), 0.0)

    def test_rms_energy_speech(self):
        from jarvis_core.realtime_voice.hybrid_endpoint import rms_energy
        energy = rms_energy(_make_speech_frame(amplitude=8000))
        self.assertGreater(energy, 300.0)

    def test_rms_energy_empty(self):
        from jarvis_core.realtime_voice.hybrid_endpoint import rms_energy
        self.assertEqual(rms_energy(b""), 0.0)
        self.assertEqual(rms_energy(b"\x00"), 0.0)

    def test_hangover_timing(self):
        he = self._make(hangover_ms=50)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        time.sleep(0.06)
        silence = _make_silence_frame()
        evt = he.feed_hangover(silence, 0.0)
        self.assertEqual(evt.value, "endpoint")

    def test_full_cycle(self):
        he = self._make(hangover_ms=10)
        he.on_speech_started()
        self.assertEqual(he.phase.value, "speech")
        evt = he.on_endpoint_candidate(_make_silence_frame())
        self.assertIsNone(evt)
        self.assertTrue(he.in_hangover)
        time.sleep(0.02)
        evt = he.feed_hangover(_make_silence_frame(), 0.0)
        self.assertEqual(evt.value, "endpoint")
        self.assertFalse(he.in_hangover)

    def test_cancel_cycle(self):
        he = self._make(hangover_ms=500, rms_threshold=300.0)
        he.on_speech_started()
        he.on_endpoint_candidate(_make_silence_frame())
        self.assertTrue(he.in_hangover)
        speech = _make_speech_frame(amplitude=8000)
        evt = he.feed_hangover(speech, rms_energy(speech))
        self.assertEqual(evt.value, "speech_resumed")
        self.assertEqual(he.phase.value, "speech")

    def test_hangover_disabled_passes_endpoint(self):
        he = self._make(hangover_ms=0)
        evt = he.on_endpoint_candidate(_make_speech_frame())
        self.assertEqual(evt.value, "endpoint")


if __name__ == "__main__":
    unittest.main()
