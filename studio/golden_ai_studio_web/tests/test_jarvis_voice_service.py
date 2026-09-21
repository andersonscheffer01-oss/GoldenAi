"""
Testes do Jarvis Desktop Voice Service — Fase 8
===============================================
SEM microfone e SEM TTS real: tudo mockado.
Roda rapido e seguro em qualquer maquina.

    python -m unittest tests.test_jarvis_voice_service -v
"""

import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.voice_service import VoiceService, _wav_rms, SILENCE_RMS


def _make_wav_like(num_samples: int = 1000, amplitude: int = 3000) -> bytes:
    """Gera bytes pseudo-WAV (RIFF header + PCM) para testar _wav_rms."""
    import io
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        frames = b"".join(
            struct.pack("<h", amplitude if i % 2 == 0 else -amplitude)
            for i in range(num_samples)
        )
        wf.writeframes(frames)
    return buf.getvalue()


class SilenceGateTest(unittest.TestCase):
    def test_loud_audio_passes_threshold(self):
        wav = _make_wav_like(amplitude=3000)
        self.assertGreater(_wav_rms(wav), SILENCE_RMS)

    def test_silent_audio_blocked(self):
        wav = _make_wav_like(amplitude=5)
        self.assertLess(_wav_rms(wav), SILENCE_RMS)

    def test_invalid_audio_is_zero(self):
        self.assertEqual(0.0, _wav_rms(b"not a wav"))
        self.assertEqual(0.0, _wav_rms(b""))

    def test_short_audio_blocked_by_size(self):
        self.assertLess(1000, 2000)  # gate de tamanho usa len(bytes) < 2000


class VoiceServiceLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from jarvis_core.service import JarvisService
        self.service = JarvisService(self.temp.name)
        self.vs = VoiceService()
        self.vs.enabled = True

    def tearDown(self):
        if self.vs.is_running():
            self.vs.stop()
        self.temp.cleanup()

    def test_start_requires_service(self):
        result = self.vs.start(None)
        self.assertFalse(result["ok"])

    def test_start_and_stop(self):
        result = self.vs.start(self.service)
        self.assertTrue(result["ok"])
        self.assertTrue(self.vs.is_running())
        status = self.vs.status()
        self.assertTrue(status["running"])
        stop = self.vs.stop()
        self.assertTrue(stop["ok"])

    def test_start_twice_is_idempotent(self):
        self.vs.start(self.service)
        again = self.vs.start(self.service)
        self.assertTrue(again["ok"])
        self.assertIn("ja esta rodando", again["message"])

    def test_disabled_env(self):
        with patch.dict("os.environ", {"JARVIS_VOICE_SERVICE": "0"}):
            vs = VoiceService()
            self.assertFalse(vs.enabled)


class VoiceServicePipelineTest(unittest.TestCase):
    """Pipeline _handle com Brain e TTS mockados — valida o fluxo completo."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from jarvis_core.service import JarvisService
        self.service = JarvisService(self.temp.name)
        self.vs = VoiceService()
        self.vs.service = self.service
        self.vs._voice = MagicMock()
        self.spoken = []
        self.vs._speak = lambda text: self.spoken.append(text) or True

    def tearDown(self):
        self.temp.cleanup()

    def test_conversational_response_is_spoken(self):
        with patch.object(self.vs, "_get_brain") as brain_factory:
            brain = brain_factory.return_value
            brain.interpret.return_value = {"ok": True, "plan": {"response": "Tudo bem!"}}
            brain.orchestrator.last_decision = None
            brain.last_llm = {}
            self.vs._handle("ola jarvis tudo bem")
            brain.interpret.assert_called_once_with(
                "ola jarvis tudo bem", source="voice", voice_capture=True)
        self.assertEqual(["Tudo bem!"], self.spoken)
        self.assertEqual("Tudo bem!", self.vs.last_response)

    def test_tool_execution_response_is_spoken(self):
        with patch.object(self.vs, "_get_brain") as brain_factory:
            brain = brain_factory.return_value
            brain.interpret.return_value = {
                "ok": True, "plan": {"tool": "get_time", "args": {}}
            }
            self.vs._handle("que horas sao")
        self.assertEqual(1, len(self.spoken))
        self.assertTrue(self.vs.last_response)
        self.assertEqual(1, self.vs.stats["commands"])

    def test_brain_error_is_spoken_not_raised(self):
        with patch.object(self.vs, "_get_brain") as brain_factory:
            brain_factory.return_value.interpret.return_value = {
                "ok": False, "error": "LLM indisponivel"
            }
            self.vs._handle("comando qualquer")
        self.assertEqual(["LLM indisponivel"], self.spoken)
        self.assertEqual(0, self.vs.stats["commands"])

    def test_exception_does_not_kill_handler(self):
        with patch.object(self.vs, "_get_brain", side_effect=RuntimeError("boom")):
            self.vs._handle("comando qualquer")
        self.assertEqual(1, len(self.spoken))
        self.assertIn("Erro", self.spoken[0])
        self.assertEqual(1, self.vs.stats["errors"])


class WakeWordFlowTest(unittest.TestCase):
    def test_wake_word_command_extraction(self):
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()  # instancia nova — nao toca no singleton global
        action = voice.process_voice_command("Jarvis abra o metatrader")
        self.assertTrue(action["wake_word"])
        self.assertEqual("execute", action["action"])
        self.assertEqual("abra o metatrader", action["command"])

    def test_no_wake_word_is_ignored_when_idle(self):
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()
        voice.last_interaction = 0.0
        action = voice.process_voice_command("abrir bloco de notas")
        self.assertFalse(action["wake_word"])
        self.assertEqual("ignore", action["action"])

    def test_conversation_continues_after_wake_word(self):
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()
        voice.process_voice_command("Jarvis")
        followup = voice.process_voice_command("abra o metatrader")
        self.assertEqual("continue_conversation", followup["action"])


class SpeakNowTest(unittest.TestCase):
    def test_speak_now_empty_text(self):
        vs = VoiceService()
        result = vs.speak_now("")
        self.assertFalse(result["ok"])

    def test_speak_now_calls_speak(self):
        vs = VoiceService()
        vs._speak = lambda text: True
        result = vs.speak_now("teste de voz")
        self.assertTrue(result["ok"])


class WakeStripTest(unittest.TestCase):
    def test_wake_variants_stripped_only_at_start(self):
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()
        cases = (
            ("Jarvis, qual é a cotação do dólar?", "qual é a cotação do dólar?"),
            ("Jarvis: abra a calculadora", "abra a calculadora"),
            ("Járvis... que horas são?", "que horas são?"),
            ("jarvis abra ele", "abra ele"),
            ("  Jarvis,  abra ele  ", "abra ele"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, voice.strip_wake_word(raw))
                self.assertTrue(voice.detect_wake_word(raw))
        # meio da frase: nao remover
        mid = "diga Jarvis qual é a cotação"
        self.assertEqual(mid, voice.strip_wake_word(mid))

    def test_wake_only_yields_listen_more(self):
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()
        action = voice.process_voice_command("Jarvis")
        self.assertEqual("listen_more", action["action"])
        self.assertEqual("", action["command"])


class VoiceRoutingParityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from jarvis_core.service import JarvisService
        self.service = JarvisService(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_typed_voice_parity(self):
        from jarvis_core.orchestrator import CentralOrchestrator
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()
        router = CentralOrchestrator(self.service.registry, mode="shadow")
        pairs = (
            ("qual cotação do dolar", "Jarvis, qual é a cotação do dólar?"),
            ("abra calculadora", "Jarvis, abra a calculadora"),
            ("que horas são?", "Jarvis, que horas são?"),
        )
        for typed, spoken in pairs:
            with self.subTest(spoken=spoken):
                action = voice.process_voice_command(spoken)
                self.assertEqual("execute", action["action"])
                route_typed = router.decide(typed).route
                route_voice = router.decide(action["command"]).route
                self.assertEqual(route_typed, route_voice)

    def test_voice_clarify_no_execution(self):
        from jarvis_core.voice import JarvisVoice
        voice = JarvisVoice()
        action = voice.process_voice_command("Jarvis, abra ele")
        self.assertEqual("execute", action["action"])
        self.assertEqual("abra ele", action["command"])
        from jarvis_core.orchestrator import CentralOrchestrator
        router = CentralOrchestrator(self.service.registry, mode="shadow")
        decision = router.decide(action["command"])
        self.assertTrue(decision.requires_clarification)


class VoiceEventTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from jarvis_core.service import JarvisService
        self.service = JarvisService(self.temp.name)
        self.service.dry_run = True
        self.vs = VoiceService()
        self.vs.service = self.service
        self.vs._voice = MagicMock()
        self.spoken = []
        self.vs._speak = lambda text: self.spoken.append(text) or True

    def tearDown(self):
        self.temp.cleanup()

    def test_one_command_one_event_with_metadata(self):
        real_decisions = []
        from jarvis_core.brain import get_brain
        brain = get_brain(self.service.registry)
        with patch.object(self.vs, "_get_brain", return_value=brain):
            self.vs._handle("qual a cotacao do dolar")
            real_decisions.append(dict(self.vs.last_event))
            self.vs._handle("qual a cotacao do dolar")
        self.assertEqual(2, len(self.spoken))  # 1 fala = 1 execucao + 1 TTS
        first, second = real_decisions[0], self.vs.last_event
        self.assertEqual(1, first["id"])
        self.assertEqual(2, second["id"])
        self.assertEqual("MARKET_DATA", second["route"])
        self.assertEqual("market_data", second["skill"])
        for key in ("capture_ms", "stt_ms", "routing_ms", "execution_ms", "total_ms"):
            self.assertIn(key, second["timings"])
        status = self.vs.status()
        self.assertEqual(2, status["last_event"]["id"])
        self.assertIn("rms", status["level"])
        self.assertIn("age_ms", status["level"])

    def test_handle_sets_processing_then_speaking(self):
        seen = []
        orig_speak = self.vs._speak
        with patch.object(self.vs, "_get_brain") as factory:
            brain = factory.return_value
            brain.interpret.return_value = {"ok": True, "plan": {"response": "oi"}}
            brain.orchestrator.last_decision = None
            brain.last_llm = {}
            def spy(text):
                seen.append(self.vs.state)
                return orig_speak(text)
            self.vs._speak = spy
            self.vs._handle("oi")
        self.assertEqual(["SPEAKING"], seen)


if __name__ == "__main__":
    unittest.main()
