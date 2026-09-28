"""P1.2 STT robustness: captura, gate, pre-roll, clipping, telemetria raw.

Nao toca Brain, VOICE_FAST, providers ou fast paths de roteamento.
sounddevice e Whisper sao mockados; nenhum audio real e usado.
"""
import io
import os
import sys
import tempfile
import types
import unittest
import wave
from unittest.mock import Mock, patch

import numpy as np

from jarvis_core.voice import (
    JarvisVoice, effective_pre_roll_seconds, get_input_device_info)
from jarvis_core.voice_service import VoiceService

BLOCK = 1024
SILENCE = np.zeros(BLOCK, dtype="int16")
SPEECH = np.full(BLOCK, 2000, dtype="int16")
LOUD = np.full(BLOCK, 12000, dtype="int16")
CLIP = np.full(BLOCK, 32767, dtype="int16")


def install_fake_sounddevice(blocks):
    """sounddevice fake com blocos roteirizados + relógio virtual.

    Os blocos chegam instantaneamente; sem relógio virtual a lógica
    temporal (calibração 350 ms, silêncio final 550 ms) não avança.
    Cada read() avança 1024/16000 s = 64 ms de tempo virtual.
    """
    import jarvis_core.voice as voice_mod

    stream_blocks = list(blocks)
    virtual = {"t": 1000.0}

    def fake_time():
        return virtual["t"]

    class FakeStream:
        def __init__(self, *args, **kwargs):
            self.items = list(stream_blocks)
            self.pos = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, blocksize):
            virtual["t"] += BLOCK / 16000.0
            if self.pos < len(self.items):
                data = self.items[self.pos]
                self.pos += 1
                return data, False
            return np.zeros(blocksize, dtype="int16"), False

    module = types.ModuleType("sounddevice")
    module.InputStream = FakeStream
    module.default = types.SimpleNamespace(device=(None, None))
    module.query_devices = lambda: []
    module.query_hostapis = lambda index: {"name": ""}
    previous_sd = sys.modules.get("sounddevice")
    sys.modules["sounddevice"] = module
    previous_time = voice_mod.time
    voice_mod.time = types.SimpleNamespace(time=fake_time)
    return (previous_sd, previous_time)


def restore_sounddevice(previous):
    import jarvis_core.voice as voice_mod
    previous_sd, previous_time = previous
    voice_mod.time = previous_time
    if previous_sd is None:
        sys.modules.pop("sounddevice", None)
    else:
        sys.modules["sounddevice"] = previous_sd


def wav_frames(record):
    with wave.open(io.BytesIO(record["audio"]), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getsampwidth() == 2
        return wf.getnframes()


class PreRollCase(unittest.TestCase):
    def test_pre_roll_preserves_speech_onset(self):
        previous = install_fake_sounddevice(
            [SILENCE] * 8 + [SPEECH] * 30 + [SILENCE] * 20)
        try:
            voice = JarvisVoice()
            record = voice.record_until_silence(max_seconds=10)
        finally:
            restore_sounddevice(previous)
        self.assertTrue(record["ok"] and record["speech_detected"])
        # O audio final inclui o buffer pre-roll: inicio da fala preservado.
        self.assertGreater(record["pre_roll_ms"], 0)
        self.assertGreaterEqual(
            wav_frames(record), 30 * BLOCK + record["pre_roll_ms"] * 16 - BLOCK)
        self.assertLess(record["speech_start_ms"], 1500)

    def test_pre_roll_override_is_honored(self):
        voice = JarvisVoice()
        voice.pre_roll_seconds = .2
        self.assertAlmostEqual(effective_pre_roll_seconds(voice), .2, places=2)
        self.assertGreater(effective_pre_roll_seconds(JarvisVoice()), .2)


class CalibrationCapCase(unittest.TestCase):
    def test_speech_during_calibration_does_not_explode_threshold(self):
        previous = install_fake_sounddevice(
            [LOUD] * 10 + [SILENCE] * 4 + [SPEECH] * 20 + [SILENCE] * 20)
        try:
            voice = JarvisVoice()
            voice.noise_floor = 20.0
            before = voice._threshold_for(20.0)
            record = voice.record_until_silence(max_seconds=10)
        finally:
            restore_sounddevice(previous)
        self.assertTrue(record["speech_detected"])
        # Sem o cap, o floor iria para ~12000 e o gate travaria.
        self.assertLessEqual(voice.noise_floor, 20.0 * 4 + 1)
        self.assertLess(voice.speech_threshold, before * 10)


class ClippingCase(unittest.TestCase):
    def test_full_scale_is_reported_as_clipping(self):
        previous = install_fake_sounddevice(
            [SILENCE] * 8 + [CLIP] * 12 + [SILENCE] * 20)
        try:
            record = JarvisVoice().record_until_silence(max_seconds=10)
        finally:
            restore_sounddevice(previous)
        self.assertTrue(record["clipping"])
        self.assertGreater(record["clipped_samples"], 0)
        self.assertEqual(record["peak"], 32767)

    def test_normal_speech_has_no_clipping_false_positive(self):
        previous = install_fake_sounddevice(
            [SILENCE] * 8 + [SPEECH] * 12 + [SILENCE] * 20)
        try:
            record = JarvisVoice().record_until_silence(max_seconds=10)
        finally:
            restore_sounddevice(previous)
        self.assertFalse(record["clipping"])
        self.assertEqual(record["clipped_samples"], 0)
        self.assertLess(record["peak"], 30000)


class EndSilenceCase(unittest.TestCase):
    def test_end_silence_target_matches_config(self):
        previous = install_fake_sounddevice(
            [SILENCE] * 8 + [SPEECH] * 10 + [SILENCE] * 30)
        try:
            voice = JarvisVoice()
            record = voice.record_until_silence(max_seconds=10)
        finally:
            restore_sounddevice(previous)
        self.assertTrue(record["speech_detected"])
        self.assertEqual(record["end_silence_target_ms"],
                         int(voice.silence_seconds * 1000))
        self.assertGreaterEqual(record["silence_wait_ms"], 0)


class DeviceInfoCase(unittest.TestCase):
    def test_device_info_shape_without_touching_windows_config(self):
        info = get_input_device_info()
        for key in ("name", "index", "host_api", "channels",
                    "native_samplerate", "capture_samplerate",
                    "capture_channels", "available"):
            self.assertIn(key, info)
        self.assertEqual(info["capture_samplerate"], 16000)
        self.assertEqual(info["capture_channels"], 1)

    def test_status_exposes_mic_and_capture(self):
        status = JarvisVoice().status()
        self.assertIn("mic", status)
        self.assertIn("last_capture", status)
        self.assertIn("pre_roll_seconds", status)
        self.assertIn("initial_prompt", status)


class LowConfidenceFeedbackCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from jarvis_core.service import JarvisService
        self.service = JarvisService(self.temp.name)
        self.voice = VoiceService()
        self.voice.service = self.service
        self.voice._voice = Mock()
        self.voice._speak = Mock(return_value=True)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_low_confidence_speech_asks_for_repeat(self):
        stt = {"accepted": False, "classification": "LOW_CONFIDENCE",
               "rejected_reason": "decoder_confidence", "stt_confidence": 0.2}
        responded = self.voice._handle_rejected_speech(stt, "qual e a...", "u1")
        self.assertTrue(responded)
        self.voice._speak.assert_called_once()
        self.assertIn("repetir", self.voice._speak.call_args[0][0])
        self.assertTrue(self.voice.last_rejection.get("responded"))

    def test_pure_noise_stays_silent(self):
        stt = {"accepted": False, "classification": "IGNORED_NOISE",
               "rejected_reason": "no_speech_probability", "stt_confidence": 0.05}
        responded = self.voice._handle_rejected_speech(stt, "", "u2")
        self.assertFalse(responded)
        self.voice._speak.assert_not_called()

    def test_raw_transcript_telemetry_reaches_last_event(self):
        brain = Mock()
        brain.interpret.return_value = {"ok": True, "plan": {"response": "Oi."}}
        brain.orchestrator.last_decision = None
        brain.last_llm = {"profile": "VOICE_FAST"}
        brain.request_metrics.return_value = {}
        with patch.object(self.voice, "_get_brain", return_value=brain):
            self.voice._handle("ola", output={"mode": "AUTO", "speak": False},
                timings={"utterance_id": "u3", "capture_ms": 100,
                         "raw_transcript": "Jarvis ola",
                         "stt_confidence": 0.9, "avg_logprob": -0.3,
                         "no_speech_prob": 0.01, "compression_ratio": 1.1,
                         "peak": 4000, "clipped_samples": 0,
                         "pre_roll_ms": 448})
        timings = self.voice.last_event["timings"]
        for key in ("raw_transcript", "stt_confidence", "avg_logprob",
                    "no_speech_prob", "compression_ratio", "peak",
                    "clipped_samples", "pre_roll_ms"):
            self.assertIn(key, timings)
        self.assertEqual(self.voice.last_event["heard"], "ola")


class WakePreservationCase(unittest.TestCase):
    def test_wake_word_kept_command_intact(self):
        voice = JarvisVoice()
        action = voice.process_voice_command("Jarvis, abra a calculadora")
        self.assertEqual(action["action"], "execute")
        self.assertEqual(action["command"], "abra a calculadora")

    def test_truncated_wake_is_not_invented(self):
        voice = JarvisVoice()
        action = voice.process_voice_command("arvis, abra a calculadora")
        self.assertEqual(action["action"], "ignore")


if __name__ == "__main__":
    unittest.main()
