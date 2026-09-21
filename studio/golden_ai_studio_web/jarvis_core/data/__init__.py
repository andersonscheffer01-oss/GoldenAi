"""
Golden Jarvis — Dados Online (Fase 8.1)
=======================================
Fontes externas estruturadas com provider trocável, cache TTL e falha honesta.

    from jarvis_core.data import get_market_data_service
"""

from .market_data import MarketDataService, get_market_data_service
from .providers import (
    MarketDataProvider,
    AwesomeAPIProvider,
    ProviderError,
    set_provider,
    get_default_provider,
)
from .cache import TTLCache

__all__ = [
    "MarketDataService",
    "get_market_data_service",
    "MarketDataProvider",
    "AwesomeAPIProvider",
    "ProviderError",
    "set_provider",
    "get_default_provider",
    "TTLCache",
]
