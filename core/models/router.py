"""Model router for Multi-Model Local V1.

The ModelRouter selects the appropriate model for each task based on
the task type (FAST/CODER/EXPERT), circuit breaker state, and model
availability. It is the single entry point for golden_ai.py to get
the model name for any chat call.

Key invariants:
    - The router NEVER grants permissions. PermissionManager is the
      sole authority for all permission decisions.
    - The router NEVER downloads models. It only uses what is installed.
    - The router falls back gracefully: EXPERT -> CODER -> FAST.
    - When external_first is enabled, chat() tries the external provider
      (NVIDIA) and falls back to the local provider (Ollama) on any error,
      including HTTP 429 / timeout / lack of internet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .circuit_breaker import CircuitBreaker
from .profiles import ModelProfile, get_profile_config
from .provider import ChatResult, ModelProvider
from .registry import ModelRegistry


@dataclass
class RoutingDecision:
    """Result of a model routing decision."""
    model_name: str
    profile: ModelProfile
    timeout_seconds: int
    temperature: float
    escalated: bool = False
    reason: str = ""


@dataclass
class ProviderEntry:
    """A provider in the chat fallback chain."""
    name: str
    provider: ModelProvider
    model_override: str | None = None
    enabled: bool = True
    timeout_override: int | None = None


class ModelRouter:
    """Selects the right model for each task and delegates chat calls.

    Two fallback mechanisms are active:
        1. Profile escalation (select): EXPERT -> CODER -> FAST, all
           resolved against the local provider (Ollama).
        2. Provider chain (chat): external (NVIDIA) first, then local
           (Ollama). Any error in the external provider triggers the
           local fallback, so work never stops on HTTP 429 or network
           issues.
    """

    def __init__(
        self,
        provider: ModelProvider | None = None,
        providers: list[ProviderEntry] | None = None,
        registry: ModelRegistry | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        settings=None,
    ) -> None:
        self.settings = settings

        if providers is None and provider is not None:
            providers = [ProviderEntry(name="ollama", provider=provider, enabled=True)]
        if providers is None:
            providers = self._build_provider_chain(settings)
        self.providers = providers

        # Local provider is the primary for registry/profile resolution.
        self.provider = self._find_local_provider()

        if registry is None:
            registry = ModelRegistry(self.provider, settings)
        self.registry = registry

        if circuit_breaker is None:
            circuit_breaker = CircuitBreaker()
        self.circuit_breaker = circuit_breaker

        self._last_decision: RoutingDecision | None = None

    # ------------------------------------------------------------------
    # Provider chain construction
    # ------------------------------------------------------------------

    def _build_provider_chain(self, settings) -> list[ProviderEntry]:
        chain: list[ProviderEntry] = []

        try:
            from .nvidia_provider import NvidiaProvider

            base_url = getattr(settings, "nvidia_api_url", None) or None
            api_key = getattr(settings, "nvidia_api_key", "") or None
            model_name = getattr(settings, "nvidia_model_name", "") or ""
            timeout = int(getattr(settings, "nvidia_timeout_seconds", 180) or 180)

            nvidia_enabled = bool(api_key) or bool(os_env_nvidia_key())
            nvidia = ProviderEntry(
                name="nvidia",
                provider=NvidiaProvider(
                    base_url=base_url,
                    api_key=api_key,
                ),
                model_override=model_name or None,
                enabled=nvidia_enabled,
                timeout_override=timeout,
            )
        except Exception:
            nvidia = None

        try:
            from .ollama_provider import OllamaProvider

            ollama = ProviderEntry(
                name="ollama",
                provider=OllamaProvider(
                    base_url=getattr(settings, "ollama_api_url", None)
                    or "http://127.0.0.1:11434",
                ),
                enabled=True,
            )
        except Exception:
            ollama = None

        external_first = getattr(settings, "external_first", True)
        entries = [e for e in (nvidia, ollama) if e is not None]

        if external_first:
            entries.sort(key=lambda e: 0 if e.name == "nvidia" else 1)
        else:
            entries.sort(key=lambda e: 0 if e.name == "ollama" else 1)

        return entries

    def _find_local_provider(self) -> ModelProvider | None:
        for entry in self.providers:
            if entry.name == "ollama":
                return entry.provider
        if self.providers:
            return self.providers[0].provider
        return None

    # ------------------------------------------------------------------
    # Profile selection (local model name for a task)
    # ------------------------------------------------------------------

    def select(self, task_profile: ModelProfile | str = ModelProfile.CODER) -> RoutingDecision:
        """Select a model for the given task profile."""
        if isinstance(task_profile, str):
            try:
                task_profile = ModelProfile(task_profile.upper())
            except ValueError:
                task_profile = ModelProfile.CODER

        profile = task_profile
        escalated = False
        reason = "normal"

        for _ in range(len(CircuitBreaker.ESCALATION_CHAIN)):
            model_name = self.registry.get_model_name_for_profile(profile)
            if not self.circuit_breaker.is_tripped(model_name):
                break
            old_profile = profile
            profile = self.circuit_breaker.get_fallback_profile(profile)
            escalated = True
            reason = f"circuit_open:{model_name} -> {profile.value}"
            if profile == old_profile:
                break

        cfg = get_profile_config(profile)
        model_name = self.registry.get_model_name_for_profile(profile)

        decision = RoutingDecision(
            model_name=model_name,
            profile=profile,
            timeout_seconds=cfg.timeout_seconds,
            temperature=cfg.temperature,
            escalated=escalated,
            reason=reason,
        )
        self._last_decision = decision
        return decision

    def get_model_name(self, task_profile: ModelProfile | str = ModelProfile.CODER) -> str:
        """Convenience: return just the model name for a task."""
        return self.select(task_profile).model_name

    def get_timeout(self, task_profile: ModelProfile | str = ModelProfile.CODER) -> int:
        """Convenience: return the timeout for a task profile."""
        return self.select(task_profile).timeout_seconds

    # ------------------------------------------------------------------
    # Chat with provider fallback
    # ------------------------------------------------------------------

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
        """Try each provider in the chain; fall back on any error.

        The external provider (NVIDIA) is tried first when enabled. On
        error (HTTP 429, timeout, no internet, unavailable model) the
        call falls back to the local provider (Ollama) so the work
        continues. Circuit state is recorded per model name.
        """
        errors: list[str] = []
        chain = [e for e in self.providers if e.enabled]

        if format_schema is not None:
            # Saida estruturada: somente o provider local (Ollama) honra
            # 'format' como JSON Schema. NVIDIA/OpenAI-compat retornam texto
            # livre, o que quebra o JSON esperado. Neste caso, local primeiro.
            chain = sorted(chain, key=lambda e: 0 if e.name == "ollama" else 1)

        for entry in chain:
            use_model = entry.model_override or model
            use_timeout = entry.timeout_override or timeout
            if self.circuit_breaker.is_tripped(use_model):
                errors.append(f"circuit_open:{use_model}")
                continue

            try:
                result = entry.provider.chat(
                    use_model,
                    messages,
                    timeout=use_timeout,
                    options=options,
                    format_schema=format_schema,
                    tools=tools,
                )
            except Exception as exc:
                result = ChatResult(
                    text="",
                    model_used=use_model,
                    error=f"{type(exc).__name__}: {exc}",
                )

            if result.error:
                self.circuit_breaker.record_failure(use_model)
                errors.append(result.error)
                continue

            if not (result.text or "").strip() and not result.tool_calls:
                # Resposta vazia nao e sucesso util (ex.: JSON estruturado
                # ignorado pelo provider externo). Tenta o proximo provider.
                self.circuit_breaker.record_failure(use_model)
                errors.append(f"empty_response:{use_model}")
                continue

            self.circuit_breaker.record_success(use_model)
            return result

        return ChatResult(
            text="",
            model_used=model,
            error="; ".join(errors) or "No provider configured",
        )

    # ------------------------------------------------------------------
    # Status / debugging
    # ------------------------------------------------------------------

    def get_last_decision(self) -> RoutingDecision | None:
        """Return the most recent routing decision (for UI display)."""
        return self._last_decision

    def get_status(self) -> dict[str, Any]:
        """Return a full status snapshot for debugging/UI."""
        provider_status: dict[str, Any] = {}
        for entry in self.providers:
            try:
                connected = entry.provider.is_connected()
            except Exception:
                connected = False
            provider_status[entry.name] = {
                "enabled": entry.enabled,
                "connected": connected,
                "model": entry.model_override,
            }
        return {
            "providers": provider_status,
            "provider_connected": self.provider.is_connected() if self.provider else False,
            "models": [m.name for m in self.registry.list_all()],
            "available_models": [m.name for m in self.registry.list_available()],
            "circuits": self.circuit_breaker.get_status(),
        }

    def refresh(self) -> None:
        """Refresh model availability from the local provider."""
        self.registry.refresh_from_provider()


def os_env_nvidia_key() -> str:
    """Return the NVIDIA API key from the environment, if present."""
    import os

    return os.environ.get("NVIDIA_API_KEY", "")
