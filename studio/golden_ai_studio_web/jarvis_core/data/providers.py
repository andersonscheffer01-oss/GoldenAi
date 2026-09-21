"""
Golden Data Providers — Fase 8.1
================================
Abstração de fontes externas de dados online para o Jarvis.

Arquitetura extensível:
    MarketDataProvider (interface)
        ├── AwesomeAPIProvider  (cotações BRL — sem credencial)   ← atual
        ├── MT5Provider         (futuro — via JarvisService/MT5)
        ├── ForexProvider       (futuro)
        ├── CryptoProvider      (futuro)
        └── MarketNewsProvider  (futuro)

Regras:
    - Toda chamada externa tem timeout.
    - Nenhuma credencial hardcoded (provider atual não exige chave).
    - Providers retornam dados estruturados ou erro — nunca inventam valores.
"""

import json
import time
import urllib.request
from abc import ABC, abstractmethod

# Timeout padrão de rede (segundos) — configurável por env.
import os
from .timestamps import normalize_external_timestamp
DATA_TIMEOUT_SECONDS = float(os.getenv("JARVIS_DATA_TIMEOUT", "8"))


class ProviderError(Exception):
    """Falha de provider (rede, JSON inválido, fonte indisponível)."""


class MarketDataProvider(ABC):
    """Interface de provider de dados de mercado."""

    name = "abstract"

    @abstractmethod
    def get_exchange_rate(self, base: str, quote: str) -> dict:
        """Retorna cotação estruturada ou levanta ProviderError."""


class AwesomeAPIProvider(MarketDataProvider):
    """
    Provider de cotações via AwesomeAPI (economia.awesomeapi.com.br).
    - Gratuito, sem credencial, foco em pares com BRL (e mais).
    - Formato: https://economia.awesomeapi.com.br/json/last/USD-BRL
    """

    name = "awesomeapi"
    BASE_URL = "https://economia.awesomeapi.com.br/json/last/{pair}"

    # Campos por par, ex.: USD-BRL → {"usdbrl": {...}}
    def get_exchange_rate(self, base: str, quote: str) -> dict:
        pair = f"{base}-{quote}"
        url = self.BASE_URL.format(pair=pair.lower())
        started = time.time()
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "GoldenJarvis/2.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=DATA_TIMEOUT_SECONDS) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise ProviderError(f"HTTP {status} de {self.name}")
                raw = resp.read().decode("utf-8", errors="replace")
            latency_ms = int((time.time() - started) * 1000)

            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ProviderError(f"JSON invalido de {self.name}: {exc}") from exc

            key = f"{base.upper()}{quote.upper()}"  # API retorna chaves uppercase (ex.: USDBRL)
            entry = payload.get(key) if isinstance(payload, dict) else None
            if not isinstance(entry, dict):
                raise ProviderError(f"Resposta sem dados para {base}/{quote}")

            raw_timestamp = entry.get("timestamp")
            timestamp = self._to_int(raw_timestamp) or int(time.time())
            return {
                "base": base,
                "quote": quote,
                "price": self._to_float(entry.get("bid")),  # bid ≈ cotação comercial
                "bid": self._to_float(entry.get("bid")),
                "ask": self._to_float(entry.get("ask")),
                "high": self._to_float(entry.get("high")),
                "low": self._to_float(entry.get("low")),
                "pct_change": self._to_float(entry.get("pctChange")),
                "timestamp": timestamp,
                **normalize_external_timestamp(raw_timestamp or timestamp, "awesomeapi_epoch"),
                "provider": self.name,
                "latency_ms": latency_ms,
            }
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Falha de rede em {self.name}: {exc}") from exc

    @staticmethod
    def _to_float(value):
        try:
            return round(float(str(value).replace(",", ".")), 4) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value):
        try:
            return int(float(value)) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None


# Provider ativo — trocável por configuração no futuro.
_DEFAULT_PROVIDER: MarketDataProvider | None = None


def get_default_provider() -> MarketDataProvider:
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = AwesomeAPIProvider()
    return _DEFAULT_PROVIDER


def set_provider(provider: MarketDataProvider):
    """Permite trocar o provider (testes ou fontes futuras)."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider
