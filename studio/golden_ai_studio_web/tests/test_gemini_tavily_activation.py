from unittest.mock import patch

from jarvis_core.config import resolve_api_key
from jarvis_core.memory.v2.research import (
    AutoResearchProvider, FetchedSource, ResearchProviderError,
    StaticResearchProvider, TavilyResearchProvider,
)
from jarvis_core.orchestrator.model_router import ModelRouter, ProviderAdapter
from jarvis_core.orchestrator.models import DataClassification, ModelProfile
from jarvis_core.orchestrator.providers import build_real_adapters


def test_windows_or_golden_keys_are_detected_without_exposing_values():
    assert bool(resolve_api_key("GEMINI_API_KEY", "gemini_api_key"))
    assert bool(resolve_api_key("TAVILY_API_KEY", "tavily_api_key"))


def test_gemini_adapter_preserves_policy_model_and_timeout():
    captured = {}

    def gemini_call(payload, model, timeout=None):
        captured.update(model=model, timeout=timeout)
        return "GEMINI_OK"

    adapter = next(item for item in build_real_adapters(gemini_call=gemini_call)
                   if item.name == "gemini")
    router = ModelRouter(timeout=3, retries=0)
    router.register_provider(adapter)
    result = router.execute([{"role": "user", "content": "test"}],
                            ModelProfile.GENERAL)
    assert result.ok and result.output == "GEMINI_OK"
    assert result.provider == "gemini"
    assert result.model == "gemini-3.8-flash"
    assert captured == {"model": "gemini-3.8-flash", "timeout": 3}


def test_secret_selects_only_local_provider():
    cloud_calls = []
    router = ModelRouter(retries=0)
    router.register_provider(ProviderAdapter(
        "gemini", lambda **kwargs: cloud_calls.append(kwargs) or "cloud", cloud=True))
    router.register_provider(ProviderAdapter("ollama", lambda **kwargs: "local", cloud=False))
    result = router.execute([], ModelProfile.GENERAL, DataClassification.SECRET)
    assert result.ok and result.provider == "ollama"
    assert cloud_calls == []


class _RateLimited:
    def search(self, query, limit=5):
        raise ResearchProviderError("rate_limit", provider="tavily")

    def fetch(self, result):
        raise AssertionError


def test_tavily_rate_limit_falls_back_and_enters_cooldown():
    fallback = StaticResearchProvider([
        FetchedSource("Docs", "https://docs.python.org/3/", "Python docs")])
    provider = AutoResearchProvider((("tavily", _RateLimited()),
                                     ("static", fallback)))
    results = provider.search("python", 1)
    assert results and provider.last_selected == "static"
    assert provider.status()["providers"]["tavily"]["cooldown_active"] is True


def test_tavily_metadata_is_preserved():
    rows = [{"title": "Python", "url": "https://www.python.org/downloads/",
             "content": "Latest Python", "score": .91,
             "published_date": "2026-09-01"}]
    results = TavilyResearchProvider._parse_results(rows, 1, "current python")
    assert results[0].provider == "tavily"
    assert results[0].score == .91
    assert results[0].published_date == "2026-09-01"
    assert results[0].query == "current python"


def test_gemini_429_falls_back_to_local():
    class RateError(RuntimeError):
        status_code = 429

    router = ModelRouter(retries=0)
    router.register_provider(ProviderAdapter(
        "gemini", lambda **kwargs: (_ for _ in ()).throw(RateError()), cloud=True))
    router.register_provider(ProviderAdapter("ollama", lambda **kwargs: "local", cloud=False))
    result = router.execute([], ModelProfile.GENERAL)
    assert result.ok and result.provider == "ollama" and result.fallback_used
    assert router.status()["gemini"]["cooldown_active"] is True
