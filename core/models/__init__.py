"""Multi-Model Local V1 module for GoldenAI.

Provides model routing, provider abstraction, and circuit breaking
for local Ollama models. This module NEVER grants permissions and
NEVER downloads models automatically.
"""
from .profiles import ModelProfile, ProfileConfig, get_profile_config, get_model_name_for_profile
from .provider import ModelProvider, ChatResult, ChatMessage, ModelInfo
from .ollama_provider import OllamaProvider, DEFAULT_OLLAMA_URL
from .nvidia_provider import NvidiaProvider, DEFAULT_NVIDIA_URL
from .registry import ModelRegistry, RegisteredModel
from .circuit_breaker import CircuitBreaker, CircuitState, CircuitEntry
from .router import ModelRouter, RoutingDecision, ProviderEntry

__all__ = [
    "ModelProfile",
    "ProfileConfig",
    "get_profile_config",
    "get_model_name_for_profile",
    "ModelProvider",
    "ChatResult",
    "ChatMessage",
    "ModelInfo",
    "OllamaProvider",
    "DEFAULT_OLLAMA_URL",
    "NvidiaProvider",
    "DEFAULT_NVIDIA_URL",
    "ModelRegistry",
    "RegisteredModel",
    "CircuitBreaker",
    "CircuitState",
    "CircuitEntry",
    "ModelRouter",
    "RoutingDecision",
    "ProviderEntry",
]
