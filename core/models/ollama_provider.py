"""Ollama model provider implementation for Multi-Model Local V1.

Implements the ModelProvider interface using the Ollama HTTP API
(http://localhost:11434). This provider does NOT download models;
it only uses models already installed locally.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .provider import ChatResult, ModelInfo, ModelProvider

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class OllamaProvider(ModelProvider):
    """Concrete provider that talks to a local Ollama daemon via HTTP."""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self._models_cache: list[ModelInfo] | None = None

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        timeout: int = 120,
        options: dict[str, Any] | None = None,
        format_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        """Call Ollama /api/chat and return the response text."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options
        if format_schema:
            payload["format"] = format_schema
        if tools:
            payload["tools"] = tools
        try:
            obj = self._post_json_obj("/api/chat", payload, timeout)
            message = obj.get("message") or {}
            tool_calls = message.get("tool_calls") or None
            return ChatResult(
                text=str(message.get("content", "")),
                model_used=model,
                error=None,
                raw=obj,
                tool_calls=tool_calls,
            )
        except Exception as exc:
            return ChatResult(text="", model_used=model, error=str(exc))

    def list_models(self) -> list[ModelInfo]:
        """Return models installed in the local Ollama daemon."""
        if self._models_cache is not None:
            return self._models_cache
        try:
            raw = self._get_json("/api/tags")
            models: list[ModelInfo] = []
            for entry in raw.get("models", []):
                name = entry.get("name", "")
                details = entry.get("details", {})
                size_bytes = entry.get("size", 0)
                models.append(
                    ModelInfo(
                        name=name,
                        size_bytes=size_bytes,
                        profile="",
                        available=True,
                        details=details,
                    )
                )
            self._models_cache = models
            return models
        except Exception:
            self._models_cache = []
            return []

    def is_available(self, model: str) -> bool:
        """Check whether a specific model is installed locally."""
        return any(m.name == model for m in self.list_models())

    def is_connected(self) -> bool:
        """Check whether the Ollama daemon is reachable."""
        try:
            self._get_json("/api/tags")
            return True
        except Exception:
            return False

    def _get_json(self, path: str) -> dict[str, Any]:
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def _post_json(self, path: str, payload: dict[str, Any], timeout: int) -> str:
        url = self.base_url + path
        dados = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=dados,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(bruto)
            return str((obj.get("message") or {}).get("content", ""))

    def _post_json_obj(self, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        url = self.base_url + path
        dados = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=dados,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            return json.loads(bruto)
