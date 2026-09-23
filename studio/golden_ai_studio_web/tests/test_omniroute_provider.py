import os
import unittest
from unittest.mock import patch

from jarvis_core.orchestrator import (DataClassification, ModelProfile, ModelRouter,
    OmniRouteProvider, ProviderCallError, ProviderState)
from jarvis_core.orchestrator.model_router import ProviderAdapter
from jarvis_core.orchestrator.providers import build_omniroute_provider_from_env


class OmniRouteProviderUnitTests(unittest.TestCase):
    def test_disabled_by_default_and_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(build_omniroute_provider_from_env())
        with patch.dict(os.environ, {"OMNIROUTE_ENABLED": "1"}, clear=True), \
             patch("jarvis_core.orchestrator.providers.resolve_api_key", return_value=None):
            provider = build_omniroute_provider_from_env()
        self.assertIsNotNone(provider)
        self.assertFalse(provider.configured)
        self.assertEqual(ProviderState.AUTH_ERROR, provider.as_adapter().state)

    def test_health_models_and_chat_contract(self):
        provider = OmniRouteProvider(api_key="dedicated-test-key")
        responses = {
            ("GET", "/api/health"): {"status": "ok"},
            ("GET", "/v1/models"): {"data": [{"id": "auto"}]},
            ("POST", "/v1/chat/completions"): {
                "id": "resp-1", "model": "provider/model",
                "choices": [{"message": {"content": "JARVIS_OMNIROUTE_OK"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        }
        captured = []

        def fake_request(method, path, payload=None, timeout=None):
            captured.append((method, path, payload))
            return responses[(method, path)]

        with patch.object(provider, "_request_json", side_effect=fake_request):
            self.assertTrue(provider.health()["ok"])
            self.assertEqual([{"id": "auto"}], provider.list_models())
            result = provider.complete([{"role": "user", "content": "ping"}], "auto")
        self.assertEqual("JARVIS_OMNIROUTE_OK", result["text"])
        self.assertEqual("provider/model", result["metadata"]["resolved_model"])
        self.assertEqual("dedicated-test-key", provider.api_key)
        body = captured[-1][2]
        self.assertEqual("auto", body["model"])
        self.assertFalse(body["stream"])

    def test_tool_and_structured_options_are_passthrough_only(self):
        provider = OmniRouteProvider(api_key="k")
        seen = {}

        def fake_request(method, path, payload=None, timeout=None):
            seen.update(payload)
            return {"choices": [{"message": {"content": '{"status":"ok","value":123}'}}]}

        with patch.object(provider, "_request_json", side_effect=fake_request):
            provider.complete({"messages": [], "tools": [{"type": "function"}],
                               "response_format": {"type": "json_object"}}, "auto")
        self.assertIn("tools", seen)
        self.assertEqual({"type": "json_object"}, seen["response_format"])

    def test_http_status_and_invalid_response_are_typed(self):
        provider = OmniRouteProvider(api_key="k")
        for code in (401, 429, 500):
            with self.subTest(code=code):
                error = ProviderCallError("http error", code)
                with patch.object(provider, "_request_json", side_effect=error):
                    with self.assertRaises(ProviderCallError) as caught:
                        provider.list_models()
                self.assertEqual(code, caught.exception.status_code)
        with patch.object(provider, "_request_json", return_value={"unexpected": True}):
            with self.assertRaises(ProviderCallError):
                provider.list_models()

    def test_router_falls_back_when_omniroute_fails(self):
        provider = OmniRouteProvider(api_key="k")
        provider.complete = lambda **_: (_ for _ in ()).throw(ProviderCallError("down"))
        router = ModelRouter(retries=0)
        router.register_provider(provider.as_adapter())
        router.register_provider(ProviderAdapter("ollama",
                                                lambda **_: {"text": "local"},
                                                cloud=False))
        result = router.execute([], ModelProfile.GENERAL, DataClassification.INTERNAL)
        self.assertTrue(result.ok)
        self.assertEqual("ollama", result.provider)
        self.assertTrue(result.fallback_used)


if __name__ == "__main__":
    unittest.main()
