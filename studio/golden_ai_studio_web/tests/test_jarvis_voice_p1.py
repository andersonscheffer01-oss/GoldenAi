import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from jarvis_core.brain import JarvisBrain
from jarvis_core.orchestrator import CentralOrchestrator
from jarvis_core.service import JarvisService
from jarvis_core.voice import JarvisVoice
from jarvis_core.voice_service import VoiceService


class VoiceP1Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)

    def tearDown(self):
        self.service.task_manager.shutdown(wait=False)
        self.temp.cleanup()

    def test_adaptive_gate_tracks_noise_without_losing_low_voice(self):
        voice = JarvisVoice()
        quiet_threshold = voice._threshold_for(20)
        noisy_threshold = voice._threshold_for(100)
        self.assertLess(quiet_threshold, 150)
        self.assertGreater(noisy_threshold, quiet_threshold)
        self.assertGreater(300, noisy_threshold)

    def test_noise_and_hallucination_are_rejected(self):
        self.assertEqual("IGNORED_NOISE", JarvisVoice.classify_transcript("", -2, .9, 0)[0])
        result = JarvisVoice.classify_transcript("Obrigado por assistir", -.2, .1, 1)
        self.assertEqual(("IGNORED_NOISE", "known_silence_hallucination"), result)

    def test_low_confidence_and_valid_command_are_distinct(self):
        low = JarvisVoice.classify_transcript("Jarvis abra", -2, .1, 1)
        valid = JarvisVoice.classify_transcript("Jarvis abra a calculadora", -.2, .05, 1)
        self.assertEqual("LOW_CONFIDENCE", low[0])
        self.assertEqual("VALID_COMMAND", valid[0])

    def test_high_risk_confidence_is_stricter(self):
        voice = JarvisVoice()
        result = {"accepted": True, "avg_logprob": -1.0, "no_speech_prob": .2}
        self.assertTrue(voice.accepted_for_risk(result, high_risk=False))
        self.assertFalse(voice.accepted_for_risk(result, high_risk=True))

    def test_warmup_is_non_blocking_and_single(self):
        voice = JarvisVoice()
        def load_model():
            time.sleep(.1)
            voice.whisper_model = object()

        with patch.object(voice, "_ensure_whisper", side_effect=load_model):
            started = time.perf_counter()
            first = voice.warmup_async()
            second = voice.warmup_async()
            elapsed = time.perf_counter() - started
            self.assertIs(first, second)
            self.assertLess(elapsed, .05)
            first.join(timeout=1)
        self.assertEqual("READY", voice.warmup["state"])

    def test_stale_backlog_is_rejected_but_current_capture_is_kept(self):
        service = VoiceService()
        service._latest_capture_at = time.time() - .1
        self.assertTrue(service._capture_is_stale(time.time() - 3, 1.5))
        self.assertFalse(service._capture_is_stale(time.time(), 1.5))

    def test_utterance_id_links_command_to_event(self):
        voice = VoiceService()
        voice.service = self.service
        voice._voice = MagicMock()
        voice._speak = lambda _text: True
        brain = MagicMock()
        brain.interpret.return_value = {"ok": True, "plan": {"response": "ok"}}
        brain.orchestrator.last_decision = None
        brain.last_llm = {}
        brain.request_metrics.return_value = {}
        with patch.object(voice, "_get_brain", return_value=brain):
            voice._handle("teste", {"utterance_id": "utterance-7"})
        self.assertEqual("utterance-7", voice.last_event["utterance_id"])

    def test_tts_guard_prevents_immediate_self_listening(self):
        voice = VoiceService()
        voice.service = self.service
        voice._voice = MagicMock()
        voice._speak = lambda _text: True
        brain = MagicMock()
        brain.interpret.return_value = {"ok": True, "plan": {"response": "resposta"}}
        brain.orchestrator.last_decision = None
        brain.last_llm = {}
        brain.request_metrics.return_value = {}
        with patch.object(voice, "_get_brain", return_value=brain):
            voice._handle("conversa")
        self.assertGreater(voice._ignore_input_until, time.time())

    def test_tts_epoch_invalidates_overlapping_capture(self):
        voice = VoiceService()
        before = voice._tts_epoch
        voice._speak_edge = lambda _text: True
        self.assertTrue(voice._speak("teste"))
        self.assertGreater(voice._tts_epoch, before)
        self.assertFalse(voice._speaking_event.is_set())

    def test_voice_fast_paths_remain_zero_llm_and_clarify_is_safe(self):
        brain = JarvisBrain(self.service.registry, orchestrator=self.service.orchestrator)
        for text, route in (("qual a cotação do dólar", "MARKET_DATA"),
                            ("abra calculadora", "WINDOWS"), ("abra ele", "CLARIFY")):
            with self.subTest(text=text):
                result = brain.interpret(text)
                self.assertTrue(result["ok"])
                self.assertEqual(route, result["orchestrator"])
                self.assertEqual(0, brain.request_metrics()["total_llm_calls"])

    def test_conversation_uses_general_route(self):
        decision = CentralOrchestrator(self.service.registry).decide(
            "me explique o que é inflação")
        self.assertEqual("CONVERSATION", decision.route.value)
        self.assertTrue(decision.requires_ai)


if __name__ == "__main__":
    unittest.main()
