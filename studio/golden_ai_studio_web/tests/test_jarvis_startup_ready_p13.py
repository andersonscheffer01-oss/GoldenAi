"""P1.3 startup/ready: eager registration, readiness SSOT, voice gate.

Nao toca STT P1.2, VOICE_FAST P1.1, Security/TaskManager, MarketData.
server_agent e importado so pelos helpers puros de boot (sem servidor).
"""
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

import server_agent
from jarvis_core.brain import JarvisBrain
from jarvis_core.orchestrator import (CentralOrchestrator, DataClassification,
    ModelProfile, ModelRouter, ProviderAdapter, Route)
from jarvis_core.orchestrator.models import ProviderState
from jarvis_core.readiness import (CORE_READY, DEGRADED, FAILED, READY,
    STARTING, WARMING, JarvisReadiness, get_readiness)
from jarvis_core.service import JarvisService
from jarvis_core.voice_service import VoiceService


def fake_cloud_429(**kwargs):
    exc = RuntimeError("rate limited")
    exc.status_code = 429
    raise exc


def fake_local_ok(**kwargs):
    return {"text": "local ok", "ttft_ms": 5, "generation_ms": 5}


class ReadinessCase(unittest.TestCase):
    def setUp(self):
        self.ready = JarvisReadiness()

    def test_full_transition_chain(self):
        self.assertTrue(self.ready.begin())
        self.ready.core_ready()
        self.ready.warming()
        self.assertEqual(WARMING, self.ready.status()["state"])
        self.assertEqual(READY, self.ready.complete())
        status = self.ready.status()
        self.assertIsNotNone(status["core_ready_ms"])
        self.assertIsNotNone(status["full_ready_ms"])

    def test_begin_is_idempotent(self):
        self.assertTrue(self.ready.begin())
        self.assertFalse(self.ready.begin())
        self.assertEqual(STARTING, self.ready.status()["state"])

    def test_warmup_failure_becomes_degraded_not_crash(self):
        self.ready.begin()
        self.ready.warming()
        self.assertEqual(DEGRADED, self.ready.complete(
            degraded=True, reason="stt timeout"))
        status = self.ready.status()
        self.assertEqual("stt timeout", status["degraded_reason"])
        # complete apos final e idempotente
        self.assertEqual(DEGRADED, self.ready.complete())

    def test_fail_state(self):
        self.ready.begin()
        self.assertEqual(FAILED, self.ready.fail("core boom"))
        self.assertIn("core", self.ready.status()["fail_reason"])

    def test_singleton_default_is_ready_passthrough(self):
        self.assertEqual(READY, get_readiness().status()["state"]
                         if not get_readiness().status()["startup_started_at"]
                         else get_readiness().status()["state"])

    def test_status_has_no_secrets(self):
        blob = str(self.ready.status())
        self.assertNotIn("gsk_", blob)
        self.assertNotIn("Bearer", blob)


class EagerRegistrationCase(unittest.TestCase):
    def test_double_registration_has_no_duplicates(self):
        from jarvis_core.orchestrator import register_real_adapters
        router = ModelRouter()
        register_real_adapters(router, lambda **k: "g", lambda **k: "m")
        first = sorted(router.providers)
        register_real_adapters(router, lambda **k: "g", lambda **k: "m")
        self.assertEqual(first, sorted(router.providers))
        self.assertEqual(len(first), len(set(first)))

    def test_chain_ready_before_first_prompt(self):
        router = ModelRouter()
        router.register_provider(ProviderAdapter("groq", fake_cloud_429, cloud=True))
        router.register_provider(ProviderAdapter("ollama", fake_local_ok, cloud=False))
        # SECRET continua local mesmo com cloud "pronta"
        secret = router.execute([], ModelProfile.GENERAL, DataClassification.SECRET)
        self.assertEqual("ollama", secret.provider)
        # GENERAL cai no fallback com estados coerentes
        general = router.execute([], ModelProfile.GENERAL)
        self.assertTrue(general.ok and general.fallback_used)
        self.assertEqual(ProviderState.AVAILABLE, router.providers["ollama"].state)
        self.assertEqual(ProviderState.RATE_LIMITED, router.providers["groq"].state)


class BootProbeCase(unittest.TestCase):
    def test_groq_no_key_is_auth_error(self):
        state, _ = server_agent.probe_groq_health("", timeout=1)
        self.assertEqual("AUTH_ERROR", state)

    def test_groq_429_is_rate_limited_without_retry_loop(self):
        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(1)
            raise urllib.error.HTTPError(req.full_url, 429, "slow", {}, None)
        with patch.object(server_agent.urllib.request, "urlopen", fake_urlopen):
            state, detail = server_agent.probe_groq_health("k", timeout=1)
        self.assertEqual("RATE_LIMITED", state)
        self.assertEqual(1, len(calls))

    def test_groq_401_is_auth_error(self):
        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
        with patch.object(server_agent.urllib.request, "urlopen", fake_urlopen):
            state, _ = server_agent.probe_groq_health("k", timeout=1)
        self.assertEqual("AUTH_ERROR", state)

    def test_ollama_offline_when_unreachable(self):
        def fake_urlopen(req, timeout=None):
            raise ConnectionRefusedError("down")
        with patch.object(server_agent.urllib.request, "urlopen", fake_urlopen):
            state, models = server_agent.probe_ollama_health(timeout=1)
        self.assertEqual("OFFLINE", state)
        self.assertEqual([], models)

    def test_groq_handler_delegates(self):
        handler = server_agent.GoldenAIHandler.__new__(server_agent.GoldenAIHandler)
        with patch.object(server_agent, "call_groq_model", return_value="X") as mock:
            out = handler._call_groq_model([], "groq-llama", timeout=3, stream=True)
        self.assertEqual("X", out)
        mock.assert_called_once_with([], "groq-llama", timeout=3, stream=True)


class CooldownRecoveryCase(unittest.TestCase):
    def test_local_timeout_is_generous_but_bounded(self):
        import time as _time
        slow = Mock(side_effect=lambda **k: (_time.sleep(0.3), {"text": "ok"})[1])
        router = ModelRouter(timeout=8, retries=0)
        router.register_provider(ProviderAdapter("ollama", slow, cloud=False))
        with patch.dict("os.environ", {"JARVIS_LOCAL_TIMEOUT_SECONDS": "5"}):
            result = router.execute([], ModelProfile.GENERAL,
                                    DataClassification.SECRET)
        self.assertTrue(result.ok)
        self.assertLess(result.latency_ms, 5000)

    def test_transient_timeout_returns_after_cooldown(self):
        import time as _time
        router = ModelRouter()
        router.register_provider(ProviderAdapter("ollama", fake_local_ok, cloud=False))
        adapter = router.providers["ollama"]
        adapter.state = ProviderState.TIMEOUT
        adapter.last_failure_at = _time.time()
        self.assertEqual([], router.select(ModelProfile.GENERAL,
                                           DataClassification.SECRET))
        adapter.last_failure_at = _time.time() - 3600
        selected = router.select(ModelProfile.GENERAL, DataClassification.SECRET)
        self.assertEqual(1, len(selected))
        self.assertEqual("ollama", selected[0][0].name)

    def test_auth_error_never_returns_alone(self):
        import time as _time
        router = ModelRouter()
        router.register_provider(ProviderAdapter("ollama", fake_local_ok, cloud=False))
        adapter = router.providers["ollama"]
        adapter.state = ProviderState.AUTH_ERROR
        adapter.last_failure_at = _time.time() - 3600
        self.assertEqual([], router.select(ModelProfile.GENERAL,
                                           DataClassification.SECRET))

    def test_success_clears_failure_stamp(self):
        router = ModelRouter(retries=0)
        router.register_provider(ProviderAdapter("ollama", fake_local_ok, cloud=False))
        adapter = router.providers["ollama"]
        adapter.state = ProviderState.TIMEOUT
        import time as _time
        adapter.last_failure_at = _time.time() - 3600
        result = router.execute([], ModelProfile.GENERAL, DataClassification.SECRET)
        self.assertTrue(result.ok)
        self.assertEqual(ProviderState.AVAILABLE, adapter.state)
        self.assertEqual(0.0, adapter.last_failure_at)


class FastPathOutageCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)
        router = ModelRouter()
        router.register_provider(ProviderAdapter(
            "groq", fake_cloud_429, cloud=True,
            state=ProviderState.OFFLINE))
        router.register_provider(ProviderAdapter(
            "ollama", fake_local_ok, cloud=False))
        self.orchestrator = CentralOrchestrator(self.service.registry, mode="shadow")
        self.orchestrator.models = router

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_fast_paths_need_no_cloud(self):
        brain = JarvisBrain(self.service.registry, orchestrator=self.orchestrator)
        with patch.object(brain, "_call_llm", side_effect=AssertionError("LLM")):
            for text, route in (("que horas são?", "SYSTEM"),
                                ("abra a calculadora", "WINDOWS"),
                                ("qual a cotação do dólar?", "MARKET_DATA"),
                                ("abra ele", "CLARIFY")):
                result = brain.interpret(text, source="voice", voice_capture=True)
                self.assertEqual(route, result["orchestrator"])
                self.assertEqual(0, brain.request_metrics()["total_llm_calls"])


class VoiceWarmingGateCase(unittest.TestCase):
    def setUp(self):
        get_readiness().reset()
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)
        self.voice = VoiceService()
        self.voice.service = self.service
        self.voice._voice = Mock()
        self.voice._speak = Mock(return_value=True)

    def tearDown(self):
        get_readiness().reset()
        self.service.close()
        self.temp.cleanup()

    def test_warming_defers_with_spoken_notice(self):
        ready = get_readiness()
        ready.begin()
        ready.core_ready()
        ready.warming()
        brain = Mock()
        with patch.object(self.voice, "_get_brain", return_value=brain):
            self.voice._handle("abra a calculadora",
                               output={"mode": "AUTO", "speak": True})
        brain.interpret.assert_not_called()
        self.voice._speak.assert_called_once()
        self.assertIn("iniciando", self.voice._speak.call_args[0][0].lower())
        self.assertEqual("WARMING", self.voice.last_event["route"])
        self.assertTrue(self.voice.last_event["timings"]["warming"])

    def test_ready_flows_normally(self):
        ready = get_readiness()
        ready.begin()
        ready.complete()
        brain = Mock()
        brain.interpret.return_value = {"ok": True, "plan": {"response": "Oi."}}
        brain.orchestrator.last_decision = None
        brain.last_llm = {"profile": "VOICE_FAST"}
        brain.request_metrics.return_value = {}
        with patch.object(self.voice, "_get_brain", return_value=brain):
            self.voice._handle("ola", output={"mode": "AUTO", "speak": False})
        brain.interpret.assert_called_once()
        self.assertNotEqual("WARMING", self.voice.last_event["route"])

    def test_voice_stop_without_start_is_clean(self):
        voice = VoiceService()
        result = voice.stop()
        self.assertTrue(result["ok"])
        self.assertEqual("OFF", voice.state)


if __name__ == "__main__":
    unittest.main()
