import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import DataClassification, ModelProfile, ProviderResult, ProviderState
from .policies import (DEFAULT_MODELS, LOCAL_TIMEOUT_SECONDS,
                       MAX_TRANSIENT_RETRIES, PROVIDER_MODELS,
                       PROVIDER_ORDER, PROVIDER_TIMEOUT_SECONDS,
                       VOICE_FAST_TIMEOUT_SECONDS)

# Estados transitórios que voltam a ser tentados após cooldown (P1.3).
# AUTH_ERROR/OFFLINE nunca retornam sozinhos: exigem reconfig/restart.
RECOVERABLE_STATES = frozenset({ProviderState.RATE_LIMITED,
                                ProviderState.TIMEOUT, ProviderState.DEGRADED})


def provider_cooldown_seconds():
    try:
        return max(0.0, float(os.getenv("JARVIS_PROVIDER_COOLDOWN_SECONDS", "60")))
    except Exception:
        return 60.0


def _local_timeout_seconds():
    try:
        return max(1.0, float(os.getenv("JARVIS_LOCAL_TIMEOUT_SECONDS",
                                       str(LOCAL_TIMEOUT_SECONDS))))
    except Exception:
        return LOCAL_TIMEOUT_SECONDS


@dataclass
class ProviderAdapter:
    name: str
    invoke: Callable[..., Any]
    cloud: bool
    state: ProviderState = ProviderState.AVAILABLE
    last_failure_at: float = 0.0
    last_success: float = 0.0
    last_latency_ms: int = 0
    last_error_type: str = ""
    last_model: str = ""

    def usable(self, now=None):
        """Elegível para tentativa: AVAILABLE ou transitório com cooldown vencido."""
        if self.state == ProviderState.AVAILABLE:
            return True
        if self.state not in RECOVERABLE_STATES:
            return False
        if now is None:
            now = time.time()
        return (now - (self.last_failure_at or 0)) >= provider_cooldown_seconds()


class ModelRouter:
    def __init__(self, timeout=PROVIDER_TIMEOUT_SECONDS, retries=MAX_TRANSIENT_RETRIES):
        self.timeout = timeout
        self.retries = max(0, min(int(retries), 1))
        self.providers: dict[str, ProviderAdapter] = {}
        self.last_health: dict[str, ProviderState] = {
            name: ProviderState.OFFLINE for name in PROVIDER_ORDER
        }

    def register_provider(self, adapter: ProviderAdapter):
        self.providers[adapter.name] = adapter
        self.last_health[adapter.name] = adapter.state

    def select(self, profile: ModelProfile, classification=DataClassification.INTERNAL):
        if profile == ModelProfile.VOICE_FAST:
            if classification == DataClassification.SECRET:
                adapter = self.providers.get("ollama")
                return ([(adapter, "qwen2.5-coder:14b")] if adapter and
                        adapter.usable() else [])
            groq = self.providers.get("groq")
            ollama = self.providers.get("ollama")
            candidates = []
            if groq and groq.usable():
                candidates.extend(((groq, "qwen/qwen3.8-27b"),
                                    (groq, "groq/compound-mini")))
            if ollama and ollama.usable():
                candidates.append((ollama, "qwen2.5-coder:14b"))
            return candidates
        preferred_provider, preferred_model = DEFAULT_MODELS[profile]
        candidates = []
        ordered = (preferred_provider,) + tuple(p for p in PROVIDER_ORDER if p != preferred_provider)
        for provider_name in ordered:
            adapter = self.providers.get(provider_name)
            if not adapter or not adapter.usable():
                continue
            if classification == DataClassification.SECRET and adapter.cloud:
                continue
            model = PROVIDER_MODELS.get(provider_name, {}).get(
                profile, DEFAULT_MODELS[ModelProfile.OFFLINE][1])
            candidates.append((adapter, model))
        return candidates

    def execute(self, payload, profile=ModelProfile.GENERAL,
                classification=DataClassification.INTERNAL, timeout=None) -> ProviderResult:
        candidates = self.select(profile, classification)
        last_error = "nenhum provider disponível"
        attempt_log = []
        for index, (adapter, model) in enumerate(candidates):
            attempts = 1 if profile == ModelProfile.VOICE_FAST else self.retries + 1
            for attempt in range(attempts):
                started = time.perf_counter()
                effective_timeout = (self.timeout if timeout is None else
                                     max(0.001, float(timeout)))
                if profile == ModelProfile.VOICE_FAST:
                    attempt_timeout = (VOICE_FAST_TIMEOUT_SECONDS if adapter.cloud
                                       else 6.0)
                    if timeout is not None:
                        attempt_timeout = effective_timeout
                elif not adapter.cloud:
                    attempt_timeout = (effective_timeout if timeout is not None else
                                       max(self.timeout, _local_timeout_seconds()))
                else:
                    attempt_timeout = effective_timeout
                try:
                    # Timeout por tentativa: provider lento nao bloqueia o
                    # fallback (cada chamada roda em thread propria).
                    pool = ThreadPoolExecutor(max_workers=1)
                    try:
                        future = pool.submit(adapter.invoke, payload=payload,
                                             model=model, timeout=attempt_timeout)
                        output = future.result(timeout=attempt_timeout)
                    finally:
                        pool.shutdown(wait=False, cancel_futures=True)
                    timing = output if isinstance(output, dict) and "text" in output else {}
                    output_text = timing.get("text") if timing else output
                    if output_text is None or (isinstance(output_text, str) and not output_text.strip()):
                        raise RuntimeError("provider retornou resposta vazia")
                    adapter.state = ProviderState.AVAILABLE
                    adapter.last_failure_at = 0.0
                    adapter.last_success = time.time()
                    adapter.last_error_type = ""
                    self.last_health[adapter.name] = ProviderState.AVAILABLE
                    latency = int((time.perf_counter() - started) * 1000)
                    adapter.last_latency_ms = latency
                    adapter.last_model = model
                    ttft = int(timing.get("ttft_ms") or 0)
                    generation = int(timing.get("generation_ms") or max(0, latency - ttft))
                    attempt_log.append({"provider": adapter.name, "model": model,
                        "result": "ok", "elapsed_ms": latency})
                    return ProviderResult(True, adapter.name, model, ProviderState.AVAILABLE,
                        output_text, index > 0, latency, "", ttft, generation,
                        tuple(attempt_log), timing.get("metadata", {}))
                except FutureTimeout as exc:
                    state = ProviderState.TIMEOUT
                    adapter.state = state
                    adapter.last_failure_at = time.time()
                    adapter.last_error_type = state.value
                    self.last_health[adapter.name] = state
                    last_error = f"{adapter.name} excedeu {attempt_timeout:g}s"
                    attempt_log.append({"provider": adapter.name, "model": model,
                        "result": "timeout", "elapsed_ms": int((time.perf_counter()-started)*1000)})
                    if attempt + 1 >= attempts:
                        break
                except Exception as exc:
                    state = self._classify_error(exc)
                    adapter.state = state
                    adapter.last_failure_at = time.time()
                    adapter.last_error_type = state.value
                    self.last_health[adapter.name] = state
                    last_error = str(exc)
                    attempt_log.append({"provider": adapter.name, "model": model,
                        "result": state.value, "elapsed_ms": int((time.perf_counter()-started)*1000)})
                    if state not in {ProviderState.RATE_LIMITED, ProviderState.TIMEOUT,
                                      ProviderState.DEGRADED} or attempt + 1 >= attempts:
                        break
        return ProviderResult(False, "", "", ProviderState.OFFLINE, error=last_error,
                              attempts=tuple(attempt_log))

    def status(self):
        now = time.time()
        return {name: {
            "configured": True,
            "status": adapter.state.value,
            "model": adapter.last_model,
            "latency_ms": adapter.last_latency_ms,
            "last_success": adapter.last_success,
            "last_error_type": adapter.last_error_type,
            "cooldown_until": (adapter.last_failure_at + provider_cooldown_seconds()
                               if adapter.state in RECOVERABLE_STATES else 0.0),
            "cooldown_active": (adapter.state in RECOVERABLE_STATES and
                                not adapter.usable(now)),
        } for name, adapter in self.providers.items()}

    @staticmethod
    def _classify_error(exc):
        from concurrent.futures import TimeoutError as FutureTimeout
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if code == 429:
            return ProviderState.RATE_LIMITED
        if code in (401, 403):
            return ProviderState.AUTH_ERROR
        if isinstance(exc, (TimeoutError, FutureTimeout)):
            return ProviderState.TIMEOUT
        if isinstance(code, int) and code >= 500:
            return ProviderState.DEGRADED
        return ProviderState.OFFLINE
