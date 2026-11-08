from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from jarvis_core.orchestrator import ModelProfile, ModelRouter, ProviderAdapter
from jarvis_core.orchestrator.policies import DEFAULT_MODELS


def test_market_profile_prefers_codex_without_changing_general_profile():
    assert DEFAULT_MODELS[ModelProfile.MARKET] == ("codex", "codex-market")
    assert DEFAULT_MODELS[ModelProfile.GENERAL][0] == "gemini"


def test_market_router_prefers_codex_and_falls_back_to_analysis_provider():
    router = ModelRouter(retries=0)
    codex = Mock(return_value={"text": "resposta Codex"})
    gemini = Mock(return_value={"text": "resposta fallback"})
    router.register_provider(ProviderAdapter(
        "codex", codex, cloud=False,
        supported_profiles=frozenset({ModelProfile.MARKET})))
    router.register_provider(ProviderAdapter("gemini", gemini, cloud=True))

    selected = router.select(ModelProfile.MARKET)
    assert selected[0][0].name == "codex"
    assert selected[0][1] == "codex-market"

    first = router.execute([], profile=ModelProfile.MARKET)
    assert first.ok and first.provider == "codex"
    assert not first.fallback_used

    codex.side_effect = RuntimeError("Codex indisponível")
    second = router.execute([], profile=ModelProfile.MARKET)
    assert second.ok and second.provider == "gemini"
    assert second.fallback_used


def test_codex_provider_uses_read_only_sandbox_and_canonical_text(monkeypatch, tmp_path):
    from codex_provider import CodexProvider
    import codex_provider

    monkeypatch.setattr(codex_provider, "codex_available", lambda: True)
    monkeypatch.setattr(codex_provider, "CODEX_WORKDIR", tmp_path / "workspace")
    monkeypatch.setattr(codex_provider, "CODEX_MODEL", "")
    (tmp_path / "workspace").mkdir()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_path = command[command.index("-o") + 1]
        Path(output_path).write_text("análise somente leitura", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(codex_provider.subprocess, "run", fake_run)
    result = CodexProvider().chat(
        [{"role": "user", "content": "Analise XAUUSD sem executar nada."}],
        model="codex-market", timeout=7)

    assert result["text"] == "análise somente leitura"
    assert result["metadata"]["execution_authority"] == "NONE"
    command = captured["command"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "workspace-write" not in command
    assert "-m" not in command
    assert captured["kwargs"]["timeout"] == 7


def test_codex_adapter_normalizes_legacy_provider_content():
    from jarvis_core.orchestrator.providers import build_codex_adapter

    provider = SimpleNamespace(
        chat=Mock(return_value={"content": "texto legado"}),
    )
    adapter = build_codex_adapter(provider)

    assert adapter is not None
    assert adapter.cloud is False
    assert ModelProfile.MARKET in adapter.supported_profiles
    result = adapter.invoke(payload=[], model="codex-market", timeout=5)
    assert result["text"] == "texto legado"
    assert result["metadata"]["execution_authority"] == "NONE"


def test_market_context_forces_market_profile_for_canonical_brain_surface():
    from jarvis_core.brain import JarvisBrain
    from jarvis_core.orchestrator import CentralOrchestrator
    from jarvis_core.registry import ToolRegistry

    registry = ToolRegistry()
    router = ModelRouter(retries=0)
    calls = []

    def answer(**kwargs):
        calls.append(kwargs)
        return {"text": '{"response": "contexto lido"}'}

    router.register_provider(ProviderAdapter(
        "codex", answer, cloud=False,
        supported_profiles=frozenset({ModelProfile.MARKET})))
    brain = JarvisBrain(registry, orchestrator=CentralOrchestrator(
        registry, model_router=router))
    try:
        result = brain.generate_response(
            "resuma o contexto", market_context={"surface": "market"},
            include_memory_context=False, record_history=False)
    finally:
        brain.close()

    assert result["ok"]
    assert result["provider"] == "codex"
    assert result["profile"] == "MARKET"
    assert calls and calls[0]["model"] == "codex-market"


def test_market_stream_uses_codex_profile_without_execution_authority():
    from jarvis_core.brain import JarvisBrain
    from jarvis_core.orchestrator import CentralOrchestrator
    from jarvis_core.registry import ToolRegistry

    registry = ToolRegistry()
    router = ModelRouter(retries=0)
    router.register_provider(ProviderAdapter(
        "codex", lambda **kwargs: {"text": '{"response":"stream"}'}, cloud=False,
        supported_profiles=frozenset({ModelProfile.MARKET})))
    brain = JarvisBrain(registry, orchestrator=CentralOrchestrator(
        registry, model_router=router))
    try:
        events = list(brain.stream_response(
            "resuma o contexto", source="market",
            market_context={"surface": "market", "execution_authority": "NONE"}))
    finally:
        brain.close()

    assert events[0]["type"] == "provider_selected"
    assert events[0]["provider"] == "codex"
    assert events[-1]["type"] == "done"
    assert brain.last_llm["profile"] == "MARKET"

