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


if __name__ == "__main__":
    unittest.main()
