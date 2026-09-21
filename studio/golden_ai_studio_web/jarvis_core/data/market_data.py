"""
MarketDataService — Fase 8.1
============================
Serviço de dados online do Jarvis. Isolado do Brain e do ToolRegistry.

Fluxo:
    Brain → ToolRegistry → get_exchange_rate → MarketDataService
        → Provider (Internet) → resultado estruturado
        (falha → cache recente, se houver; nunca inventa valor)

Uso:
    from jarvis_core.data.market_data import get_market_data_service
    svc = get_market_data_service()
    svc.get_exchange_rate("USD", "BRL")
"""

import threading
from typing import Optional

from .providers import MarketDataProvider, ProviderError, get_default_provider
from .cache import TTLCache
from .timestamps import normalize_external_timestamp

# Cache de cotação: 30s (dentro da faixa pedida 15–60s).
RATE_CACHE_TTL = float(__import__("os").getenv("JARVIS_RATE_CACHE_TTL", "30"))

# Moedas aceitas — validação antes de qualquer rede.
SUPPORTED_CURRENCIES = {
    "USD", "BRL", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY", "ARS",
    "BTC", "ETH", "XAU", "XAG",
}


class MarketDataService:
    """Consulta dados online com cache e tratamento de falha honesto."""

    def __init__(self, provider: Optional[MarketDataProvider] = None,
                 cache_ttl: float = RATE_CACHE_TTL):
        # provider=None → segue o provider global (troca via set_provider funciona).
        self._explicit_provider = provider
        self.cache = TTLCache(ttl_seconds=cache_ttl)

    @property
    def provider(self) -> MarketDataProvider:
        if self._explicit_provider is not None:
            return self._explicit_provider
        return get_default_provider()

    def get_exchange_rate(self, base: str, quote: str) -> dict:
        base = str(base or "").strip().upper()
        quote = str(quote or "").strip().upper()
        if base not in SUPPORTED_CURRENCIES:
            return {"ok": False, "error": f"Moeda nao suportada: {base}"}
        if quote not in SUPPORTED_CURRENCIES:
            return {"ok": False, "error": f"Moeda nao suportada: {quote}"}
        if base == quote:
            return {"ok": False, "error": "Moedas base e quote devem ser diferentes."}

        cache_key = f"rate:{base}:{quote}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return {**cached, "ok": True, "from_cache": True}

        try:
            rate = self.provider.get_exchange_rate(base, quote)
        except ProviderError as exc:
            return self._failure_with_fallback(base, quote, str(exc))
        except Exception as exc:  # rede inesperada — mesmo tratamento
            return self._failure_with_fallback(base, quote, str(exc))

        if not rate.get("normalized_timestamp"):
            rate = {**rate, **normalize_external_timestamp(
                rate.get("timestamp_raw", rate.get("timestamp")),
                rate.get("timezone_source", "provider_epoch"))}
        self.cache.set(cache_key, rate)
        return {**rate, "ok": True, "from_cache": False}

    def _failure_with_fallback(self, base: str, quote: str, error: str) -> dict:
        """Falha de rede: NUNCA inventa. Usa cache expirado apenas se existir."""
        stale_value = self.cache.get(f"rate:{base}:{quote}", allow_stale=True)
        if stale_value:
            return {**stale_value, "ok": True, "from_cache": True, "stale": True,
                    "warning": "Fonte online indisponivel — exibindo ultima cotacao disponivel.",
                    "error": error}
        return {"ok": False, "error": "Nao consegui consultar a cotacao agora.",
                "detail": error}

    def status(self) -> dict:
        return {
            "ok": True,
            "provider": getattr(self.provider, "name", "unknown"),
            "cache": self.cache.stats(),
        }


# Singleton
_service: MarketDataService | None = None
_lock = threading.Lock()


def get_market_data_service() -> MarketDataService:
    global _service
    with _lock:
        if _service is None:
            _service = MarketDataService()
        return _service
