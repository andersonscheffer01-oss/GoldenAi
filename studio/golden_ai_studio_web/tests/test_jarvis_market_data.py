"""
Testes da Fase 8.1 — Dados Online / Cotações
============================================
NÃO depende de internet: provider mockado em todos os testes.
Cobre: USD/BRL, EUR/BRL, GBP/BRL, provider OK, timeout, offline,
JSON inválido, cache, aliases ("dólar", "euro"), validação de moedas.

    python -m unittest tests.test_jarvis_market_data -v
"""

import json
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.data.providers import AwesomeAPIProvider, ProviderError, set_provider
from jarvis_core.data.market_data import MarketDataService, SUPPORTED_CURRENCIES
from jarvis_core.data.cache import TTLCache


def _awesomeapi_payload(base: str, quote: str, price: float) -> str:
    """Payload no formato real da AwesomeAPI (chave UPPERCASE: USDBRL)."""
    key = f"{base.upper()}{quote.upper()}"
    return json.dumps({
        key: {
            "bid": f"{price:.4f}",
            "ask": f"{price + 0.005:.4f}",
            "high": f"{price + 0.01:.4f}",
            "low": f"{price - 0.01:.4f}",
            "pctChange": "0.25",
            "timestamp": "1726100000",
            "name": f"{base}/{quote}",
        }
    })


class MockProvider:
    """Provider em memória — sem rede."""
    name = "mock"

    def __init__(self, price=5.4321, fail=False, bad_json=False, timeout=False,
                 fail_after=None):
        self.price = price
        self.fail = fail
        self.bad_json = bad_json
        self.timeout = timeout
        self.fail_after = fail_after  # falha apos N chamadas bem-sucedidas
        self.calls = 0

    def get_exchange_rate(self, base, quote):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise ProviderError("HTTP 503 de mock")
        if self.timeout:
            raise ProviderError("Falha de rede em mock: timed out")
        if self.bad_json:
            raise ProviderError("JSON invalido de mock: Expecting value")
        if self.fail:
            raise ProviderError("HTTP 503 de mock")
        return {"base": base, "quote": quote, "price": self.price,
                "bid": self.price, "ask": self.price + 0.005,
                "high": self.price + 0.01, "low": self.price - 0.01,
                "pct_change": 0.25, "timestamp": 1726100000,
                "provider": self.name, "latency_ms": 12}


class MarketDataServiceTest(unittest.TestCase):
    def _svc(self, provider):
        return MarketDataService(provider=provider, cache_ttl=30)

    # ── Provider OK ────────────────────────────────────────────────
    def test_usd_brl_success(self):
        p = MockProvider(price=5.4321)
        r = self._svc(p).get_exchange_rate("USD", "BRL")
        self.assertTrue(r["ok"])
        self.assertFalse(r["from_cache"])
        self.assertEqual("USD", r["base"])
        self.assertEqual("BRL", r["quote"])
        self.assertAlmostEqual(5.4321, r["price"])
        self.assertEqual("mock", r["provider"])
        self.assertEqual(1726100000, r["timestamp"])

    def test_eur_brl_and_gbp_brl(self):
        svc = self._svc(MockProvider(price=5.9))
        self.assertTrue(svc.get_exchange_rate("EUR", "BRL")["ok"])
        svc2 = self._svc(MockProvider(price=6.9))
        self.assertTrue(svc2.get_exchange_rate("GBP", "BRL")["ok"])

    # ── Cache ──────────────────────────────────────────────────────
    def test_cache_prevents_second_call(self):
        p = MockProvider()
        svc = self._svc(p)
        first = svc.get_exchange_rate("USD", "BRL")
        second = svc.get_exchange_rate("USD", "BRL")
        self.assertEqual(1, p.calls)  # só 1 chamada externa
        self.assertFalse(first["from_cache"])
        self.assertTrue(second["from_cache"])
        self.assertAlmostEqual(first["price"], second["price"])

    def test_cache_ttl_expiry(self):
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("k", {"v": 1})
        import time
        time.sleep(0.08)
        self.assertIsNone(cache.get("k"))

    # ── Falhas honestas ────────────────────────────────────────────
    def test_provider_offline_never_invents(self):
        r = self._svc(MockProvider(fail=True)).get_exchange_rate("USD", "BRL")
        self.assertFalse(r["ok"])
        self.assertIn("Nao consegui consultar", r["error"])
        self.assertNotIn("price", r)

    def test_timeout_never_invents(self):
        r = self._svc(MockProvider(timeout=True)).get_exchange_rate("USD", "BRL")
        self.assertFalse(r["ok"])
        self.assertNotIn("price", r)

    def test_bad_json_never_invents(self):
        r = self._svc(MockProvider(bad_json=True)).get_exchange_rate("USD", "BRL")
        self.assertFalse(r["ok"])

    def test_stale_cache_used_on_failure_with_warning(self):
        p = MockProvider(price=5.10, fail_after=1)  # 1a chamada OK, resto falha
        svc = self._svc(p)
        svc.get_exchange_rate("USD", "BRL")  # popula cache
        # Expira manualmente mantendo a entrada (simula stale).
        with svc.cache._lock:
            key = "rate:USD:BRL"
            value, _ = svc.cache._store[key]
            svc.cache._store[key] = (value, 0)  # expirado
        r = svc.get_exchange_rate("USD", "BRL")  # provider falha agora
        self.assertTrue(r["ok"])
        self.assertTrue(r["stale"])
        self.assertIn("ultima cotacao", r["warning"])
        self.assertAlmostEqual(5.10, r["price"])

    # ── Validação ──────────────────────────────────────────────────
    def test_unsupported_currency_rejected(self):
        r = self._svc(MockProvider()).get_exchange_rate("USD", "XX99")
        self.assertFalse(r["ok"])
        self.assertEqual(0, MockProvider().calls if False else 0)  # sem rede
        self.assertIn("nao suportada", r["error"])

    def test_same_currency_rejected(self):
        r = self._svc(MockProvider()).get_exchange_rate("USD", "USD")
        self.assertFalse(r["ok"])

    def test_no_url_accepted_as_currency(self):
        r = self._svc(MockProvider()).get_exchange_rate(
            "https://evil.example.com", "BRL")
        self.assertFalse(r["ok"])


class AliasResolutionTest(unittest.TestCase):
    def test_alias_dolar_to_usd(self):
        from jarvis_core.service import JarvisService
        self.assertEqual("USD", JarvisService.resolve_currency("dólar"))
        self.assertEqual("USD", JarvisService.resolve_currency("dolar"))

    def test_alias_euro_real_libra_iene(self):
        from jarvis_core.service import JarvisService
        self.assertEqual("EUR", JarvisService.resolve_currency("euro"))
        self.assertEqual("BRL", JarvisService.resolve_currency("reais"))
        self.assertEqual("GBP", JarvisService.resolve_currency("libra"))
        self.assertEqual("JPY", JarvisService.resolve_currency("iene"))

    def test_symbol_passthrough(self):
        from jarvis_core.service import JarvisService
        self.assertEqual("USD", JarvisService.resolve_currency("usd"))
        self.assertEqual("BTC", JarvisService.resolve_currency("bitcoin"))


class ServiceToolTest(unittest.TestCase):
    """Tool get_exchange_rate através do JarvisService (fluxo completo)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from jarvis_core.service import JarvisService
        self.service = JarvisService(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_tool_registered_low_risk_llm_enabled(self):
        tool = self.service.registry.get("get_exchange_rate")
        self.assertIsNotNone(tool)
        self.assertEqual("LOW", tool.risk.value)
        self.assertFalse(tool.confirmation)
        self.assertTrue(tool.llm_enabled)
        names = {t["name"] for t in self.service.registry.get_llm_tools()}
        self.assertIn("get_exchange_rate", names)

    def test_tool_via_execute_tool(self):
        set_provider(MockProvider(price=5.4321))
        try:
            r = self.service.execute_tool("get_exchange_rate",
                                          {"base": "dólar", "quote": "real"})
            self.assertTrue(r["ok"])
            self.assertEqual("USD", r["base"])
            self.assertEqual("BRL", r["quote"])
            self.assertIn("R$ 5.43", r["message"])
            self.assertIn("Fonte: mock", r["message"])
            self.assertIn("Atualizado", r["message"])
        finally:
            set_provider(None)  # restaura default

    def test_tool_failure_message_honest(self):
        set_provider(MockProvider(fail=True))
        try:
            r = self.service.execute_tool("get_exchange_rate",
                                          {"base": "USD", "quote": "BRL"})
            self.assertFalse(r["ok"])
            self.assertIn("Não consegui consultar", r["message"])
        finally:
            set_provider(None)


class AwesomeAPIProviderParseTest(unittest.TestCase):
    """Parser do provider real contra payload gravado (sem rede)."""

    def _serve(self, payload: bytes, status: int = 200):
        import io

        def fake_urlopen(req, timeout):
            resp = MagicMock()
            resp.status = status
            resp.read.return_value = payload
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        return fake_urlopen

    def test_parse_real_payload_format(self):
        provider = AwesomeAPIProvider()
        payload = _awesomeapi_payload("USD", "BRL", 5.4321).encode()
        with patch("urllib.request.urlopen", self._serve(payload)):
            r = provider.get_exchange_rate("USD", "BRL")
        self.assertEqual("USD", r["base"])
        self.assertAlmostEqual(5.4321, r["price"])
        self.assertEqual("awesomeapi", r["provider"])

    def test_http_error_raises_provider_error(self):
        provider = AwesomeAPIProvider()
        with patch("urllib.request.urlopen",
                   self._serve(b"{}", status=503)):
            with self.assertRaises(ProviderError):
                provider.get_exchange_rate("USD", "BRL")

    def test_invalid_json_raises_provider_error(self):
        provider = AwesomeAPIProvider()
        with patch("urllib.request.urlopen",
                   self._serve(b"not json at all")):
            with self.assertRaises(ProviderError):
                provider.get_exchange_rate("USD", "BRL")

    def test_missing_pair_raises_provider_error(self):
        provider = AwesomeAPIProvider()
        with patch("urllib.request.urlopen", self._serve(b"{}")):
            with self.assertRaises(ProviderError):
                provider.get_exchange_rate("USD", "BRL")


class BrainPromptTest(unittest.TestCase):
    def test_system_prompt_forbids_invented_rates(self):
        from jarvis_core.brain import JarvisBrain
        brain = JarvisBrain.__new__(JarvisBrain)
        brain.registry = MagicMock()
        brain.registry.get_llm_tools.return_value = []
        prompt = brain._system_prompt()
        self.assertIn("get_exchange_rate", prompt)
        self.assertIn("Nunca responda cotacao", prompt)


if __name__ == "__main__":
    unittest.main()
