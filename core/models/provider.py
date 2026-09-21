"""Abstract model provider interface for Multi-Model Local V1.

A ModelProvider abstracts the LLM backend (Ollama, OpenAI, etc.) behind a
uniform interface. The ModelRouter calls the provider to execute chat
requests without knowing the transport details.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResult:
    """Result of a model chat call."""

    text: str
    model_used: str
    error: str | None = None
    raw: Any = None
    tool_calls: list[Any] | None = None


@dataclass
class ModelInfo:
    """Metadata about an available model."""

    name: str
    size_bytes: int = 0
    profile: str = ""
    available: bool = True
    details: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    """Abstract interface for LLM backends."""

    @abstractmethod
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
        """Send a chat request to the model and return the response text.

        Args:
            model: Model name (e.g. "qwen2.5-coder:14b").
            messages: List of {"role": ..., "content": ...} dicts.
            timeout: Socket timeout in seconds.
            options: Ollama options dict (temperature, num_ctx, etc.).
            format_schema: JSON schema for structured output (if supported).
            tools: Optional OpenAI-style tool definitions for tool calling.

        Returns:
            ChatResult with the response text and metadata.
        """

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Return all models known to the provider."""

    @abstractmethod
    def is_available(self, model: str) -> bool:
        """Check whether a specific model is available on the provider."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check whether the provider backend is reachable."""