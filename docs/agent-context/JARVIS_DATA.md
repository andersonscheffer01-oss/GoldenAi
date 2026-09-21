# Dados Online — Fase 8.1 (Cotações)

## O que é
Fontes de dados online para o Jarvis, começando por cotações de moedas.
O Brain NUNCA inventa cotação — sempre chama a ferramenta.

## Arquitetura
```
Brain → ToolRegistry → get_exchange_rate
    → MarketDataService (cache TTL 30s)
        → MarketDataProvider (interface)
            └── AwesomeAPIProvider  ← atual (sem credencial)
        → Internet → JSON estruturado
    falha → cache expirado como fallback (marcado stale) → senão, erro honesto
```

## Arquivos
| Arquivo | Papel |
|---|---|
| `jarvis_core/data/providers.py` | Interface `MarketDataProvider` + `AwesomeAPIProvider` |
| `jarvis_core/data/cache.py` | `TTLCache` thread-safe (com `allow_stale` para fallback) |
| `jarvis_core/data/market_data.py` | `MarketDataService` (validação, cache, falha honesta) |
| `jarvis_core/service.py` | Tool `get_exchange_rate` + aliases de moeda (`CURRENCY_ALIASES`) |

## Tool: get_exchange_rate
- Risk: **LOW** (somente leitura), llm_enabled, sem confirmação.
- Args: `base`, `quote` — aceitam aliases naturais (dólar, euro, real, libra, iene,
  bitcoin, ouro...). Resolução em `JarvisService.resolve_currency()`.
- Retorno: `message` formatado + `base/quote/price/bid/ask/timestamp/provider/from_cache/stale`.
- Contexto brasileiro: "cotação do dólar" sem outra moeda → **USD/BRL** (alias resolve).

## Provider atual: AwesomeAPI
- URL: `https://economia.awesomeapi.com.br/json/last/{PAIR}` (chave uppercase: `USDBRL`).
- Sem credencial, timeout 8s (`JARVIS_DATA_TIMEOUT`).
- Campos não fornecidos → null. `price` usa o bid (cotação comercial).

## Cache e falha
- Cache TTL 30s (`JARVIS_RATE_CACHE_TTL`) — perguntas repetidas não refazem a chamada.
- Falha de rede: **nunca inventa valor**. Retorna "Não consegui consultar a cotação agora."
- Se houver cache expirado: responde com valor antigo + `stale: true` + warning.

## Segurança
- Sem credenciais no código (provider atual é gratuito).
- Moedas validadas contra lista (`SUPPORTED_CURRENCIES`) — URL/arbitrário rejeitado.
- Passa por Registry → SecurityManager → AuditLog como toda tool.

## Prompt do Brain
System prompt reforçado: perguntas de valor atual → SEMPRE chamar `get_exchange_rate`,
nunca responder de conhecimento próprio, nunca inventar número.

## Testes
- `tests/test_jarvis_market_data.py`: 22 testes (provider OK/timeout/offline/JSON
  inválido, cache, TTL, stale fallback, aliases, validação, parse do payload real,
  prompt do Brain) — **sem depender de internet** (mocks).
- Suíte Jarvis completa: **66/66 OK** (hardening 14 + memory 13 + voice 17 + data 22).
- Contagens do hardening atualizadas 46→47 (catálogo) e 45→46 (LLM tools) — esperado,
  pois o Registry ganhou a nova tool.

## Smoke real (2026-09-12)
| Par | Valor | Provider | Latência |
|---|---|---|---|
| USD/BRL | R$ 5.1262 | awesomeapi | 83 ms |
| EUR/BRL | R$ 5.94 | awesomeapi | — |
| GBP/BRL | R$ 6.93 | awesomeapi | — |

E2E pelo LLM: "qual a cotacao do dolar" → plan `{"tool":"get_exchange_rate",
"args":{"base":"USD","quote":"BRL"}}` → "USD: R$ 5.13. Fonte: awesomeapi. Atualizado as 19:30."

## Voz
O Desktop Voice Service (Fase 8) usa o mesmo Brain/Registry — a pergunta falada
"Jarvis, qual a cotação do dólar?" segue: Whisper → Brain → get_exchange_rate → TTS.
Servidor live validado: `tools_from_registry: 46`, tool responde no servidor.

## Extensões futuras (não implementadas)
`MT5Provider`, `ForexProvider`, `CryptoProvider`, `MarketNewsProvider` — basta
implementar a interface `MarketDataProvider` e chamar `set_provider()`.
