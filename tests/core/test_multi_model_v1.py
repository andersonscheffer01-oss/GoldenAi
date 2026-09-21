from __future__ import annotations
import unittest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, r'c:\GoldenAI')

from core.models.profiles import ModelProfile, ProfileConfig, get_profile_config, get_model_name_for_profile, DEFAULT_PROFILES
from core.models.provider import ModelProvider, ChatResult, ChatMessage, ModelInfo
from core.models.ollama_provider import OllamaProvider, DEFAULT_OLLAMA_URL
from core.models.registry import ModelRegistry, RegisteredModel
from core.models.circuit_breaker import CircuitBreaker, CircuitState, CircuitEntry
from core.models.router import ModelRouter, RoutingDecision
from core.config import GoldenAISettings, load_settings


class MultiModelV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'GoldenAI'
        (self.root / 'config').mkdir(parents=True)
        (self.root / 'logs').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_profiles_defined(self):
        self.assertEqual(get_model_name_for_profile('FAST'), 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        self.assertEqual(get_model_name_for_profile('CODER'), 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        self.assertEqual(get_model_name_for_profile('EXPERT'), 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')

    def test_b_profile_timeouts(self):
        fast = get_profile_config(ModelProfile.FAST)
        coder = get_profile_config(ModelProfile.CODER)
        expert = get_profile_config(ModelProfile.EXPERT)
        self.assertEqual(fast.timeout_seconds, 60)
        self.assertEqual(coder.timeout_seconds, 120)
        self.assertEqual(expert.timeout_seconds, 300)

    def test_c_provider_interface(self):
        self.assertTrue(issubclass(OllamaProvider, ModelProvider))
        self.assertTrue(hasattr(ModelProvider, 'chat'))
        self.assertTrue(hasattr(ModelProvider, 'list_models'))
        self.assertTrue(hasattr(ModelProvider, 'is_available'))
        self.assertTrue(hasattr(ModelProvider, 'is_connected'))

    def test_d_ollama_default_url(self):
        self.assertEqual(DEFAULT_OLLAMA_URL, 'http://127.0.0.1:11434')
        provider = OllamaProvider()
        self.assertEqual(provider.base_url, 'http://127.0.0.1:11434')

    def test_e_registry_defaults(self):
        registry = ModelRegistry()
        models = registry.list_all()
        self.assertGreaterEqual(len(models), 2)
        names = [m.name for m in models]
        self.assertIn('orcarouter/Qwen3.8-27B-Uncensored:iq4_xs', names)

    def test_f_registry_get_by_profile(self):
        registry = ModelRegistry()
        expert = registry.get_by_profile(ModelProfile.EXPERT)
        self.assertIsNotNone(expert)
        self.assertEqual(expert.name, 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        coder = registry.get_by_profile(ModelProfile.CODER)
        self.assertIsNotNone(coder)
        self.assertEqual(coder.name, 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')

    def test_g_circuit_escalation(self):
        cb = CircuitBreaker(failure_threshold=3)
        self.assertEqual(cb.get_fallback_profile(ModelProfile.EXPERT), ModelProfile.CODER)
        self.assertEqual(cb.get_fallback_profile(ModelProfile.CODER), ModelProfile.FAST)
        self.assertEqual(cb.get_fallback_profile(ModelProfile.FAST), ModelProfile.FAST)

    def test_h_circuit_trips(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure('test-model')
        self.assertTrue(cb.is_tripped('test-model'))

    def test_i_circuit_no_trip_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure('test-model')
        cb.record_failure('test-model')
        self.assertFalse(cb.is_tripped('test-model'))

    def test_j_circuit_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure('m1')
        cb.record_failure('m1')
        self.assertTrue(cb.is_tripped('m1'))
        cb.reset('m1')
        self.assertFalse(cb.is_tripped('m1'))

    def test_k_router_selects_model(self):
        router = ModelRouter(provider=MagicMock())
        decision = router.select(ModelProfile.EXPERT)
        self.assertEqual(decision.model_name, 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        self.assertEqual(decision.profile, ModelProfile.EXPERT)
        self.assertFalse(decision.escalated)

    def test_l_router_escalation(self):
        router = ModelRouter(provider=MagicMock())
        for _ in range(3):
            router.circuit_breaker.record_failure('orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        decision = router.select(ModelProfile.EXPERT)
        self.assertTrue(decision.escalated)
        self.assertEqual(decision.profile, ModelProfile.CODER)

    def test_m_router_get_model_name(self):
        router = ModelRouter(provider=MagicMock())
        self.assertEqual(router.get_model_name('FAST'), 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        self.assertEqual(router.get_model_name('CODER'), 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')
        self.assertEqual(router.get_model_name('EXPERT'), 'orcarouter/Qwen3.8-27B-Uncensored:iq4_xs')

    def test_n_settings_model_fields(self):
        settings = GoldenAISettings()
        self.assertTrue(settings.model_routing_enabled)
        self.assertEqual(settings.ollama_api_url, 'http://127.0.0.1:11434')
        self.assertFalse(settings.model_auto_download)
        self.assertIn('FAST', settings.model_profiles)
        self.assertIn('EXPERT', settings.model_profiles)

    def test_o_model_never_grants_permissions(self):
        from core.permissions import PermissionManager
        settings = GoldenAISettings()
        pm = PermissionManager(settings)
        router = ModelRouter(provider=MagicMock())
        self.assertFalse(hasattr(router, 'can_write'))
        self.assertFalse(hasattr(router, 'can_read'))
        self.assertFalse(hasattr(router, 'can_internet_search'))
        self.assertTrue(pm.can_read(settings.projects_dir).allowed)
        self.assertFalse(pm.can_write(settings.projects_dir).allowed)

    def test_p_permissions_preserved(self):
        settings = GoldenAISettings()
        self.assertTrue(settings.read_only)
        self.assertFalse(settings.write_enabled)
        self.assertTrue(len(settings.protected_paths) > 0)

    def test_q_router_status(self):
        router = ModelRouter(provider=MagicMock())
        status = router.get_status()
        self.assertIn('models', status)
        self.assertIn('available_models', status)
        self.assertIn('circuits', status)
        self.assertIn('orcarouter/Qwen3.8-27B-Uncensored:iq4_xs', status['models'])


if __name__ == '__main__':
    unittest.main()
