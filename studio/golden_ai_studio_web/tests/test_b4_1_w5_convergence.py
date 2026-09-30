"""Wave 5 provider-convergence characterization without runtime side effects."""

from __future__ import annotations

import ast
from pathlib import Path


STUDIO_ROOT = Path(__file__).resolve().parents[1]
SERVER = STUDIO_ROOT / "server_agent.py"


def _method_source(name: str) -> str:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "GoldenAIHandler":
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == name:
                    return ast.get_source_segment(
                        SERVER.read_text(encoding="utf-8"), member) or ""
    raise AssertionError(f"method not found: {name}")


def test_legacy_chat_delegates_to_canonical_service_without_direct_provider():
    source = _method_source("api_chat")
    assert "_legacy_service" in source
    assert "generate_response" in source
    assert "conversation_id" in source
    assert "ollama_chat" not in source
    assert "_call_groq_model" not in source
    assert "_call_gemini_model" not in source
    assert "_execute_tool" not in source
    assert "EXECUTION_SERVICE" not in source


def test_legacy_agent_delegates_tool_authority_to_jarvis_service():
    source = _method_source("api_agent")
    assert "_legacy_service" in source
    assert "service.execute_tool" in source
    assert "_active_audit_context" in source
    assert "SecurityManager" in source
    assert "AuditLog" in source
    assert "_execute_tool" not in source
    assert "EXECUTION_SERVICE" not in source


def test_streaming_route_delegates_to_canonical_service():
    source = _method_source("handle_stream")
    assert "stream_response" in source
    assert "_legacy_service" in source
    assert "text/event-stream" in source
    assert "_authorize_http" in source
    assert "ollama_chat" not in source
    assert "_call_groq_model" not in source
    assert "_call_gemini_model" not in source


def test_legacy_routes_remain_protected_and_mapped():
    source = SERVER.read_text(encoding="utf-8")
    assert '"/api/chat": self.api_chat' in source
    assert '"/api/agent": self.api_agent' in source
    assert "data[\"_http_context\"] = decision.context" in source
    assert "decision = self._authorize_http(self.command, self._request_path())" in source
