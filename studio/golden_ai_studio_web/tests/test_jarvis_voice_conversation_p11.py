import tempfile
import unittest
from unittest.mock import Mock, patch

from jarvis_core.brain import JarvisBrain
from jarvis_core.orchestrator import (CentralOrchestrator, DataClassification,
    ModelProfile, ModelRouter, ProviderAdapter, Route)
from jarvis_core.output_mode import OutputModeManager, to_spoken_text
from jarvis_core.service import JarvisService
from jarvis_core.voice_service import VoiceService


class VoiceConversationP11Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)
        self.orchestrator = CentralOrchestrator(self.service.registry, mode="shadow")

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_simple_voice_conversation_selects_voice_fast(self):
        decision = self.orchestrator.decide("O que é Forex?", source="voice",
                                            voice_capture=True)
        self.assertEqual(Route.CONVERSATION, decision.route)
        self.assertEqual(ModelProfile.VOICE_FAST, decision.preferred_model_profile)

    def test_complex_voice_conversation_uses_deep(self):
        decision = self.orchestrator.decide(
            "Faça uma análise profunda de juros, DXY e ouro e monte cenários.", source="voice")
        self.assertEqual(ModelProfile.DEEP, decision.preferred_model_profile)

    def test_fast_paths_bypass_voice_fast_and_llm(self):
        brain = JarvisBrain(self.service.registry, orchestrator=self.orchestrator)
        with patch.object(brain, "_call_llm", side_effect=AssertionError("LLM")):
            for text, route in (("que horas são?", "SYSTEM"),
                                ("abra a calculadora", "WINDOWS"),
                                ("qual a cotação do dólar?", "MARKET_DATA")):
                result = brain.interpret(text, source="voice", voice_capture=True)
                self.assertEqual(route, result["orchestrator"])
                self.assertEqual(0, brain.request_metrics()["total_llm_calls"])

    def test_voice_fast_fallback_is_short_and_model_specific(self):
        calls = []
        def cloud(**kwargs):
            calls.append(kwargs["model"])
            if len(calls) == 1:
                raise RuntimeError("primary unavailable")
            return {"text": "resposta", "ttft_ms": 20, "generation_ms": 30}
        router = ModelRouter(retries=1)
        router.register_provider(ProviderAdapter("groq", cloud, cloud=True))
        router.register_provider(ProviderAdapter("ollama", lambda **k: "local", cloud=False))
        result = router.execute([], ModelProfile.VOICE_FAST)
        self.assertTrue(result.ok)
        self.assertEqual(["qwen/qwen3.8-27b", "groq/compound-mini"], calls)
        self.assertEqual(2, len(result.attempts))

    def test_secret_voice_fast_never_calls_cloud(self):
        cloud = Mock(return_value="cloud")
        local = Mock(return_value="local")
        router = ModelRouter()
        router.register_provider(ProviderAdapter("groq", cloud, cloud=True))
        router.register_provider(ProviderAdapter("ollama", local, cloud=False))
        result = router.execute([], ModelProfile.VOICE_FAST, DataClassification.SECRET)
        self.assertEqual("ollama", result.provider)
        cloud.assert_not_called()

    def test_output_modes_and_same_utterance_instruction(self):
        manager = OutputModeManager()
        parsed = manager.parse("Me explique Forex, mas quero ouvir a resposta.", "text")
        self.assertEqual("VOICE", parsed["mode"])
        self.assertEqual("Me explique Forex", parsed["content"])
        self.assertTrue(parsed["speak"])
        self.assertFalse(OutputModeManager().parse("responda por escrito", "voice")["speak"])
        self.assertEqual("VOICE_AND_TEXT", OutputModeManager().parse("fale e escreva", "text")["mode"])

    def test_auto_mode_depends_on_source(self):
        manager = OutputModeManager()
        self.assertTrue(manager.parse("olá", "voice")["speak"])
        self.assertFalse(manager.parse("olá", "text")["speak"])

    def test_spoken_response_removes_markdown_and_urls(self):
        spoken = to_spoken_text("### Forex\n- **Mercado** https://example.com")
        self.assertNotIn("#", spoken)
        self.assertNotIn("**", spoken)
        self.assertNotIn("http", spoken)

    def test_voice_runtime_context_is_truthful_and_compact(self):
        brain = JarvisBrain(self.service.registry, orchestrator=self.orchestrator)
        brain._allowed_tools = set()
        context = brain._runtime_context("voice", True)
        self.assertIn("input_source=voice", context)
        self.assertIn("voice_capture=true", context)
        self.assertNotIn("open_program", context)

    def test_follow_up_context_is_sent_without_second_llm(self):
        payloads = []
        router = ModelRouter()
        router.register_provider(ProviderAdapter("groq",
            lambda **k: payloads.append(k["payload"]) or "Entendi.", cloud=True))
        brain = JarvisBrain(self.service.registry, orchestrator=self.orchestrator)
        brain.orchestrator.models = router
        first = brain.interpret("O que é Forex?", source="voice", voice_capture=True)
        second = brain.interpret("Explica de outro jeito.", source="voice", voice_capture=True)
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(2, len(payloads))
        self.assertTrue(any(m.get("content") == "O que é Forex?" for m in payloads[1]))
        self.assertEqual(1, brain.request_metrics()["total_llm_calls"])

    def test_tool_intent_is_not_swallowed(self):
        decision = self.orchestrator.decide(
            "Me explica Forex e depois abre o MetaTrader.", source="voice")
        self.assertNotEqual(ModelProfile.VOICE_FAST, decision.preferred_model_profile)

    def test_voice_service_uses_one_tts_call(self):
        voice = VoiceService(); voice.service = self.service; voice._voice = Mock()
        voice._speak = Mock(return_value=True)
        brain = Mock()
        brain.interpret.return_value = {"ok": True, "plan": {"response": "**Olá.**"}}
        brain.orchestrator.last_decision = None; brain.last_llm = {"profile": "VOICE_FAST"}
        brain.request_metrics.return_value = {}
        with patch.object(voice, "_get_brain", return_value=brain):
            voice._handle("olá", output={"mode": "AUTO", "speak": True})
        voice._speak.assert_called_once_with("Olá.")


if __name__ == "__main__":
    unittest.main()
