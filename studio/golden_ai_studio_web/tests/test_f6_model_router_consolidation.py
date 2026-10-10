import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from jarvis_core.brain import JarvisBrain
from jarvis_core.orchestrator import (CentralOrchestrator, ModelRouter,
                                      ProviderAdapter, register_local_ollama_adapter)
from jarvis_core.service import JarvisService


class ModelRouterConsolidationF6Tests(unittest.TestCase):
    def test_local_adapter_is_lazy_and_owned_by_canonical_router(self):
        router = ModelRouter(retries=0)
        register_local_ollama_adapter(router)
        self.assertEqual(["ollama"], sorted(router.providers))

        chat = Mock(return_value={"message": {"content": "resposta local"}})
        fake_ollama = types.SimpleNamespace(chat=chat)
        with patch.dict(sys.modules, {"ollama": fake_ollama}):
            result = router.execute({"messages": []})

        self.assertTrue(result.ok)
        self.assertEqual("ollama", result.provider)
        self.assertEqual("resposta local", result.output)
        chat.assert_called_once()

    def test_brain_empty_router_uses_router_local_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            service = JarvisService(directory)
            try:
                router = ModelRouter(retries=0)
                orchestrator = CentralOrchestrator(service.registry, mode="on",
                                                   model_router=router)
                brain = JarvisBrain(service.registry, orchestrator=orchestrator)
                chat = Mock(return_value={"message": {"content": "ok pelo router"}})
                fake_ollama = types.SimpleNamespace(chat=chat)
                with patch.dict(sys.modules, {"ollama": fake_ollama}):
                    result = brain._call_llm("teste")

                self.assertTrue(result["ok"])
                self.assertEqual("ollama", result["provider"])
                self.assertIn("ollama", router.providers)
                chat.assert_called_once()
            finally:
                service.close()

    def test_secret_policy_excludes_cloud_after_local_registration(self):
        router = ModelRouter(retries=0)
        cloud = Mock(return_value="cloud")
        local = Mock(return_value="local")
        router.register_provider(ProviderAdapter("groq", cloud, cloud=True))
        router.register_provider(ProviderAdapter("ollama", local, cloud=False))

        from jarvis_core.orchestrator.models import DataClassification
        result = router.execute("secret", classification=DataClassification.SECRET)

        self.assertTrue(result.ok)
        self.assertEqual("ollama", result.provider)
        cloud.assert_not_called()
        local.assert_called_once()

    def test_provider_allowlist_blocks_cloud_fallback_for_public_panel_analysis(self):
        router = ModelRouter(retries=0)
        cloud = Mock(return_value="cloud")
        local = Mock(return_value="local")
        router.register_provider(ProviderAdapter("gemini", cloud, cloud=True))
        router.register_provider(ProviderAdapter("ollama", local, cloud=False))

        from jarvis_core.orchestrator.models import DataClassification, ModelProfile
        result = router.execute("public market context", profile=ModelProfile.DEEP,
                                classification=DataClassification.PUBLIC,
                                allowed_providers=("ollama",))

        self.assertTrue(result.ok)
        self.assertEqual("ollama", result.provider)
        cloud.assert_not_called()
        local.assert_called_once()

    def test_one_shot_transient_error_does_not_retry_or_fallback(self):
        class TemporaryProviderFailure(RuntimeError):
            status_code = 503

        router = ModelRouter(retries=1)
        first = Mock(side_effect=TemporaryProviderFailure("temporary"))
        second = Mock(return_value="must not be called")
        router.register_provider(ProviderAdapter("gemini", first, cloud=True))
        router.register_provider(ProviderAdapter("ollama", second, cloud=False))

        from jarvis_core.orchestrator.models import DataClassification, ModelProfile
        result = router.execute("payload", profile=ModelProfile.DEEP,
                                classification=DataClassification.PUBLIC,
                                one_shot=True)

        self.assertFalse(result.ok)
        self.assertEqual(1, len(result.attempts))
        self.assertEqual("DEGRADED", result.attempts[0]["result"])
        first.assert_called_once()
        second.assert_not_called()

    def test_one_shot_timeout_does_not_retry_or_fallback(self):
        router = ModelRouter(timeout=0.01, retries=1)
        first = Mock(side_effect=TimeoutError("timed out"))
        second = Mock(return_value="must not be called")
        router.register_provider(ProviderAdapter("gemini", first, cloud=True))
        router.register_provider(ProviderAdapter("ollama", second, cloud=False))

        from jarvis_core.orchestrator.models import DataClassification, ModelProfile
        result = router.execute("payload", profile=ModelProfile.DEEP,
                                classification=DataClassification.PUBLIC,
                                one_shot=True)

        self.assertFalse(result.ok)
        self.assertEqual(1, len(result.attempts))
        self.assertEqual("timeout", result.attempts[0]["result"])
        first.assert_called_once()
        second.assert_not_called()

    def test_one_shot_with_no_available_provider_makes_no_attempt(self):
        from jarvis_core.orchestrator.models import (DataClassification, ModelProfile,
                                                    ProviderState)
        router = ModelRouter(retries=1)
        unavailable = Mock(return_value="must not be called")
        fallback = Mock(return_value="must not be called")
        router.register_provider(ProviderAdapter(
            "gemini", unavailable, cloud=True, state=ProviderState.OFFLINE))
        router.register_provider(ProviderAdapter("ollama", fallback, cloud=False))

        result = router.execute("payload", profile=ModelProfile.DEEP,
                                classification=DataClassification.PUBLIC,
                                one_shot=True)

        self.assertFalse(result.ok)
        self.assertEqual((), result.attempts)
        unavailable.assert_not_called()
        fallback.assert_not_called()

    def test_one_shot_error_metadata_is_sanitized_and_classified(self):
        class ProviderFailure(RuntimeError):
            status_code = 429

        router = ModelRouter(retries=1)
        preferred = Mock(side_effect=ProviderFailure(
            "HTTP 429 private body api_key=do-not-log"))
        fallback = Mock(return_value="must not run")
        router.register_provider(ProviderAdapter("gemini", preferred, cloud=True))
        router.register_provider(ProviderAdapter("ollama", fallback, cloud=False))

        from jarvis_core.orchestrator.models import DataClassification, ModelProfile
        result = router.execute("private prompt", profile=ModelProfile.DEEP,
                                classification=DataClassification.PUBLIC, one_shot=True)

        self.assertFalse(result.ok)
        self.assertEqual("QUOTA_OR_RATE_LIMIT_HTTP_429", result.error)
        self.assertEqual("QUOTA_OR_RATE_LIMIT_HTTP_429", result.attempts[0]["error_code"])
        self.assertEqual(429, result.attempts[0]["http_status"])
        self.assertNotIn("private body", str(result.attempts))
        self.assertNotIn("api_key", str(result.attempts))
        preferred.assert_called_once()
        fallback.assert_not_called()

    def test_http_503_result_preserves_attempted_provider_and_model(self):
        from jarvis_core.orchestrator.models import DataClassification, ModelProfile
        from jarvis_core.orchestrator.providers import ProviderCallError

        router = ModelRouter(retries=1)
        preferred = Mock(side_effect=ProviderCallError(
            "private response body api_key=do-not-log", 503))
        fallback = Mock(return_value="must not run")
        router.register_provider(ProviderAdapter("gemini", preferred, cloud=True))
        router.register_provider(ProviderAdapter("ollama", fallback, cloud=False))
        selected = router.select(ModelProfile.DEEP, DataClassification.PUBLIC)
        expected_provider, expected_model = selected[0]

        result = router.execute("private prompt", profile=ModelProfile.DEEP,
                                classification=DataClassification.PUBLIC,
                                one_shot=True)

        self.assertFalse(result.ok)
        self.assertEqual(expected_provider.name, result.provider)
        self.assertEqual(expected_model, result.model)
        self.assertEqual("PROVIDER_HTTP_FAILURE_HTTP_503", result.error)
        self.assertEqual(503, result.attempts[0]["http_status"])
        self.assertEqual(expected_provider.name, result.attempts[0]["provider"])
        self.assertEqual(expected_model, result.attempts[0]["model"])
        self.assertNotIn("private response body", str(result))
        self.assertNotIn("api_key", str(result))
        preferred.assert_called_once()
        fallback.assert_not_called()

    def test_provider_http_error_codes_are_distinguishable_without_body(self):
        from jarvis_core.orchestrator.models import ProviderState
        from jarvis_core.orchestrator.providers import ProviderCallError

        expected = {
            401: ("AUTHENTICATION_HTTP_401", ProviderState.AUTH_ERROR),
            403: ("AUTHORIZATION_HTTP_403", ProviderState.AUTH_ERROR),
            404: ("MODEL_OR_ENDPOINT_HTTP_404", ProviderState.OFFLINE),
            429: ("QUOTA_OR_RATE_LIMIT_HTTP_429", ProviderState.RATE_LIMITED),
            503: ("PROVIDER_HTTP_FAILURE_HTTP_503", ProviderState.DEGRADED),
        }
        for status, (error_code, state) in expected.items():
            error = ProviderCallError("private response body", status)
            self.assertEqual((error_code, status),
                             ModelRouter._safe_error_metadata(error))
            self.assertEqual(state, ModelRouter._classify_error(error))

        timeout = TimeoutError("private timeout detail")
        self.assertEqual(("TIMEOUT", None), ModelRouter._safe_error_metadata(timeout))
        self.assertEqual(ProviderState.TIMEOUT, ModelRouter._classify_error(timeout))

        from jarvis_core.orchestrator.providers import _raise_text_error
        with self.assertRaises(ProviderCallError) as caught:
            _raise_text_error("Erro Gemini: RESPONSE_PARSE_ERROR")
        self.assertEqual(("INTEGRATION_OR_PARSING", None),
                         ModelRouter._safe_error_metadata(caught.exception))


if __name__ == "__main__":
    unittest.main()
