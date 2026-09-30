"""Deterministic B4.1 restriction-closure tests.

These tests use fake providers and a loopback HTTP server only. They never
contact a provider, MT5, a broker, Strategy Tester, MetaEditor, or Voice.
"""

from __future__ import annotations

import ast
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest

from jarvis_core.orchestrator.model_router import ModelRouter, ProviderAdapter
from jarvis_core.orchestrator.models import (
    DataClassification,
    ModelProfile,
    ProviderState,
)


STUDIO_ROOT = Path(__file__).resolve().parents[1]
SERVER_SOURCE = STUDIO_ROOT / "server_agent.py"


def _fake_stream(*chunks, error=None):
    def stream(**_kwargs):
        for chunk in chunks:
            yield chunk
        if error:
            raise RuntimeError(error)
    return stream


def _router(*adapters):
    router = ModelRouter(timeout=1, retries=0)
    router.register_provider(adapters[0])
    for adapter in adapters[1:]:
        router.register_provider(adapter)
    return router


def test_router_streams_through_fake_adapter_and_preserves_telemetry():
    calls = []

    def invoke(**_kwargs):
        calls.append("invoke")
        return "unused"

    adapter = ProviderAdapter(
        "ollama", invoke, cloud=False,
        stream=_fake_stream({"choices": [{"delta": {"content": "ola"}}]},
                            {"choices": [{"delta": {"content": " mundo"}}]}),
    )
    events = list(_router(adapter).stream(
        [{"role": "user", "content": "fixture"}],
        profile=ModelProfile.GENERAL,
        classification=DataClassification.INTERNAL,
    ))

    assert [event["type"] for event in events] == [
        "provider_selected", "chunk", "chunk", "done"]
    assert "ola mundo" == "".join(
        event.get("text", "") for event in events if event["type"] == "chunk")
    assert events[-1]["provider"] == "ollama"
    assert calls == []


def test_router_falls_back_only_before_first_chunk():
    first = ProviderAdapter("gemini", lambda **_: "unused", cloud=False,
                            stream=_fake_stream(error="first failed"))
    second = ProviderAdapter("groq", lambda **_: "unused", cloud=False,
                             stream=_fake_stream("fallback"))
    events = list(_router(first, second).stream([]))

    assert [event["type"] for event in events] == [
        "provider_selected", "provider_selected", "chunk", "done"]
    assert events[1]["fallback_used"] is True
    assert events[-1]["fallback_used"] is True


def test_router_does_not_fallback_after_partial_output():
    first = ProviderAdapter("gemini", lambda **_: "unused", cloud=False,
                            stream=_fake_stream("partial", error="late failure"))
    second = ProviderAdapter("groq", lambda **_: "unused", cloud=False,
                             stream=_fake_stream("must not be used"))
    events = list(_router(first, second).stream([]))

    assert [event["type"] for event in events] == [
        "provider_selected", "chunk", "error"]
    assert events[-1]["after_first_chunk"] is True
    assert not any(event.get("provider") == "second" for event in events)


def test_router_cancel_is_cooperative_before_next_chunk():
    cancel = threading.Event()

    def stream(**_kwargs):
        yield "first"
        cancel.set()
        yield "second must not be emitted"

    adapter = ProviderAdapter("ollama", lambda **_: "unused", cloud=False,
                             stream=stream)
    events = list(_router(adapter).stream([], cancel_event=cancel))

    assert [event["type"] for event in events] == [
        "provider_selected", "chunk", "cancelled"]
    assert events[-1]["cancelled"] is True


def test_active_stream_handler_has_no_provider_selection_or_direct_call():
    tree = ast.parse(SERVER_SOURCE.read_text(encoding="utf-8"))
    handler = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "GoldenAIHandler")
    stream = next(node for node in handler.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "handle_stream")
    source = ast.get_source_segment(
        SERVER_SOURCE.read_text(encoding="utf-8"), stream) or ""
    assert "stream_response" in source
    assert "_legacy_service" in source
    for forbidden in ("ollama_chat", "_call_groq_model", "_call_gemini_model",
                      "get_claude_provider", "get_cline_provider", "order_send"):
        assert forbidden not in source


def test_legacy_route_is_frozen_before_handler_dispatch(monkeypatch):
    from server_agent import GoldenAIHandler

    handler = object.__new__(GoldenAIHandler)
    handler.command = "POST"
    audited = []
    monkeypatch.setattr(handler, "_audit_route_boundary",
                        lambda data, path, status, reason: (
                            audited.append((path, status, reason)),
                            ("req-fixture", "corr-fixture"))[1])

    result = handler.route_api("/api/mt5/auto_trade", {
        "_http_context": {"request_id": "req-fixture"}})

    assert result["error"] == "LEGACY_ROUTE_FROZEN"
    assert result["_http_status"] == 409
    assert audited[0][1] == "FROZEN_LEGACY_ROUTE"


def test_loopback_sse_route_preserves_legacy_wire_shape(monkeypatch):
    from server_agent import GoldenAIHandler

    class FakeService:
        def stream_response(self, message, **kwargs):
            assert message == "fixture"
            assert kwargs["surface"] == "legacy_stream"
            yield {"type": "provider_selected", "provider": "fixture",
                   "model": "fixture-model"}
            yield {"type": "chunk", "text": "ola"}
            yield {"type": "chunk", "text": " mundo"}
            yield {"type": "done", "full_response": "ola mundo",
                   "request_id": "req-fixture", "correlation_id": "corr-fixture"}

    class Handler(GoldenAIHandler):
        def _authorize_http(self, method, path):
            return SimpleNamespace(context={
                "request_id": "req-fixture",
                "correlation_id": "corr-fixture",
            })

        def _legacy_service(self):
            return FakeService()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({"message": "fixture", "session_id": "s1"}).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/stream/chat",
            data=body, method="POST", headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=3) as response:
            raw = response.read().decode("utf-8")
        payloads = [json.loads(line[6:]) for line in raw.splitlines()
                    if line.startswith("data: ")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    assert response.headers["Content-Type"] == "text/event-stream"
    assert payloads[0]["stream_event"] == "STREAM_PROVIDER_SELECTED"
    assert [item["token"] for item in payloads[1:3]] == ["ola", " mundo"]
    assert payloads[-1]["done"] is True
    assert payloads[-1]["full_response"] == "ola mundo"


def test_loopback_sse_reaches_service_brain_and_router_with_fake_provider(tmp_path):
    from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE
    from jarvis_core.service import JarvisService
    from server_agent import GoldenAIHandler

    service = JarvisService(tmp_path, runtime_profile=WEB_AI_SAFE_PROFILE)
    calls = []

    def fake_stream(**_kwargs):
        calls.append("provider")
        yield "canonical "
        yield "chain"

    service.orchestrator.models.providers.clear()
    service.orchestrator.models.register_provider(
        ProviderAdapter("ollama", lambda **_: "unused", cloud=False,
                        stream=fake_stream))

    class Handler(GoldenAIHandler):
        def _authorize_http(self, method, path):
            return SimpleNamespace(context={
                "request_id": "req-chain",
                "correlation_id": "corr-chain",
            })

        def _legacy_service(self):
            return service

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({"message": "fixture chain", "session_id": "chain"}).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/stream/chat",
            data=body, method="POST", headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
        payloads = [json.loads(line[6:]) for line in raw.splitlines()
                    if line.startswith("data: ")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        service.close()

    assert calls == ["provider"]
    assert [item["token"] for item in payloads if "token" in item] == [
        "canonical ", "chain"]
    assert payloads[-1]["full_response"] == "canonical chain"
