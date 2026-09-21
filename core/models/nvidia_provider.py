"""NVIDIA API model provider for Golden AI."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .provider import ChatResult, ModelInfo, ModelProvider


DEFAULT_NVIDIA_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(ModelProvider):
    """Golden AI provider for NVIDIA hosted models."""

    def __init__(
        self,
        base_url: str = DEFAULT_NVIDIA_URL,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
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
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        if options:
            for key in (
                "temperature",
                "top_p",
                "max_tokens",
                "seed",
                "stop",
            ):
                if key in options:
                    payload[key] = options[key]

        if tools:
            payload["tools"] = tools

        try:
            obj = self._request_json(
                "/chat/completions",
                method="POST",
                payload=payload,
                timeout=timeout,
            )

            choices = obj.get("choices", [])
            if not choices:
                return ChatResult(
                    text="",
                    model_used=payload["model"],
                    error="NVIDIA retornou resposta sem choices.",
                    raw=obj,
                )

            message = choices[0].get("message", {})
            text = message.get("content", "")
            tool_calls = message.get("tool_calls") or None

            return ChatResult(
                text=text if isinstance(text, str) else str(text),
                model_used=obj.get("model", payload["model"]),
                error=None,
                raw=obj,
                tool_calls=tool_calls,
            )

        except Exception as exc:
            return ChatResult(
                text="",
                model_used=payload["model"],
                error=str(exc),
                raw=None,
            )

    def list_models(self) -> list[ModelInfo]:
        try:
            obj = self._request_json(
                "/models",
                method="GET",
                timeout=20,
            )

            models: list[ModelInfo] = []

            for entry in obj.get("data", []):
                name = entry.get("id", "")
                if not name:
                    continue

                models.append(
                    ModelInfo(
                        name=name,
                        size_bytes=0,
                        profile="",
                        available=True,
                        details={
                            "provider": "nvidia",
                            "owned_by": entry.get("owned_by", ""),
                        },
                    )
                )

            self._models_cache = models
            return models

        except Exception:
            self._models_cache = []
            return []

    def is_available(self, model: str) -> bool:
        if not model:
            return False

        models = self._models_cache
        if models is None:
            models = self.list_models()

        return any(item.name == model for item in models)

    def is_connected(self) -> bool:
        if not self.api_key:
            return False

        try:
            self._request_json("/models", method="GET", timeout=10)
            return True
        except Exception:
            return False

    def _request_json(
        self,
        path: str,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
        timeout: int = 120,
    ) -> dict[str, Any]:
        url = self.base_url + path

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=float(timeout),
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw)

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"NVIDIA HTTP {exc.code}: {body}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Falha de conexao NVIDIA: {exc.reason}"
            ) from exc