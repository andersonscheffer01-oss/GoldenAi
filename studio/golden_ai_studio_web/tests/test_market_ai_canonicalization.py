"""Focused contracts for the canonical Market AI surface."""

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis_core.service import JarvisService
from jarvis_core.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[1]


class _FakeBrain:
    def __init__(self):
        self.calls = []
        self.last_llm = {"provider": "fake-router", "model": "fake-market-model"}

    def generate_response(self, message, **kwargs):
        self.calls.append((message, kwargs))
        return {
            "ok": True,
            "response": "Contexto recebido.",
            "provider": "fake-router",
            "model": "fake-market-model",
            "profile": "GENERAL",
        }


def _bare_service():
    service = JarvisService.__new__(JarvisService)
    service.registry = object()
    service.legacy_memory = None
    service.memory_v2 = None
    service.project_memory = None
    service.orchestrator = SimpleNamespace(last_decision=None)
    service.audit = SimpleNamespace(add=lambda **kwargs: None)
    service._conversation_lock = threading.RLock()
    service._ai_status_lock = threading.RLock()
    service._conversation_histories = {}
    service._last_request_telemetry = {}
    return service


def test_market_context_snapshot_preserves_asset_timeframe_and_provenance():
    service = JarvisService.__new__(JarvisService)
    service.golden_market_context = lambda symbol, timeframe: {
        "ok": True,
        "data": {
            "multitimeframe": {timeframe: {"price": 2345.6, "structure": "bullish"}},
            "fundamentals": {"strength_ranking": ["USD"], "events": [], "pair_news": []},
        },
        "freshness": "CACHED",
        "provenance": {"price": "MT5"},
        "observed_at": "2026-09-29T12:00:00+00:00",
    }
    scanner_calls = []
    service.golden_scanner_snapshot = lambda *args: scanner_calls.append(args)

    result = service.market_context_snapshot(
        {"symbol": "EURUSD", "timeframe": "H1"})
    context = result["context"]

    assert result["ok"] is True
    assert context["surface"] == "market"
    assert context["selected_asset"] == "EURUSD"
    assert context["symbol"] == "EURUSD"
    assert context["timeframe"] == "H1"
    assert context["freshness"] == "CACHED"
    assert context["provenance"]["market"]["price"] == "MT5"
    assert "scanner" not in context["source_timestamps"]
    assert result["scanner"] == {"status": "NOT_USED"}
    assert scanner_calls == []


def test_market_conversations_are_isolated_and_share_one_brain_boundary():
    service = _bare_service()
    brain = _FakeBrain()
    with patch("jarvis_core.brain.get_brain", return_value=brain):
        first = service.generate_response("mensagem A", surface="market",
                                          conversation_id="market-A",
                                          market_context={"symbol": "XAUUSD"})
        second = service.generate_response("mensagem B", surface="market",
                                           conversation_id="market-B",
                                           market_context={"symbol": "EURUSD"})

    assert first["conversation_id"] == "market-A"
    assert second["conversation_id"] == "market-B"
    assert brain.calls[0][1]["conversation_history"] == []
    assert brain.calls[1][1]["conversation_history"] == []
    assert brain.calls[0][1]["market_context"]["symbol"] == "XAUUSD"
    assert brain.calls[1][1]["market_context"]["symbol"] == "EURUSD"
    assert service._conversation_histories["market-A"]
    assert service._conversation_histories["market-B"]


def test_explicit_conversation_id_allows_opt_in_continuity():
    service = _bare_service()
    brain = _FakeBrain()
    with patch("jarvis_core.brain.get_brain", return_value=brain):
        service.generate_response("primeiro", surface="main", conversation_id="shared-1")
        service.generate_response("segundo", surface="market", conversation_id="shared-1")

    assert any(item["content"] == "primeiro"
               for item in brain.calls[1][1]["conversation_history"])


def test_deep_analysis_has_no_independent_model_authority():
    source = (ROOT / "server_agent.py").read_text(encoding="utf-8")
    method = source.split("    def _api_market_analyze", 1)[1].split(
        "    def api_search", 1)[0]
    assert "ollama_chat" not in method
    assert "qwen2.5-coder:14b" not in method
    assert "service.generate_response" in method
    assert "market_context=context" in method


def test_frontend_sends_structured_market_session_context():
    desktop = (ROOT / "desktop_center.js").read_text(encoding="utf-8")
    radar = (ROOT / "ai_radar.js").read_text(encoding="utf-8")
    chart = (ROOT / "chart_terminal.js").read_text(encoding="utf-8")
    assert "surface:'market'" in desktop
    assert "conversation_id:marketConversationId()" in desktop
    assert "market_context:marketContext()" in desktop
    assert "conversation_id:`market-analysis:" in radar
    assert "question,symbol:lastAnalysisContext.chart.symbol" in radar
    assert "const prompt=`ATIVO:" not in radar
    assert "loadSequence" in chart and "requestSequence!==loadSequence" in chart


def test_brain_market_context_is_structured_and_bounded():
    from jarvis_core.brain import JarvisBrain

    brain = JarvisBrain(ToolRegistry())
    messages = brain.build_messages(
        "qual ativo está selecionado?", "", market_context={
            "surface": "market", "symbol": "USDJPY", "timeframe": "H1",
        })
    payload = "\n".join(item["content"] for item in messages)
    assert '"symbol": "USDJPY"' in payload
    assert '"timeframe": "H1"' in payload
    assert "dado observado" in payload
    assert len(payload) < 30000
