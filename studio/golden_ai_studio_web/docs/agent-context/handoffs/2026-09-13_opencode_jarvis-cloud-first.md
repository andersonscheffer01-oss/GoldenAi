# Handoff — Cloud-First LLM (GENERAL/DEEP via ModelRouter)

## Estado

Fast path, voz, visual e TaskManager intactos. SHADOW mantido. Sem segundo
Brain/Router; sem parser paralelo; sem trading.

## Root cause

Pedidos com LLM caíam direto no Ollama porque `brain._call_llm` só usava o
ModelRouter em modo ON. Em shadow ia ao `ollama.chat` direto (lento).

## Mudanças

- `brain.py`: ModelRouter sempre que houver adapters (qualquer modo);
  `last_llm` (provider/model/profile/fallback/latency); prosa vira
  `{"response"}` SOMENTE em skill sem tools (CONVERSATION); tool routes
  seguem fail-closed (hardening verde).
- `model_router.py`: timeout por tentativa (8s, thread própria) → fallback
  rápido; `_classify_error` cobre TimeoutError de futures.
- `providers.py`: OpenRouter dict-error vira `ProviderCallError` (antes um
  `{"error":...}` passava como sucesso); sucesso extrai
  `choices[0].message.content`; sem chave → 401.
- `server_agent.py`: `llm{...}` também no caminho de erro do chat.
- Desktop: `set_meta` com PROFILE/MODEL/FB/latency (+LOCAL p/ ollama);
  `state.last_llm`; metadados por resposta (typed) e via orch poll (voz).

## Validação real

- A "Task Manager": 2.2s, CONVERSATION/GENERAL, openrouter, fb=True,
  latency 1803ms, resposta correta.
- B "ouro x dólar": 30.9s (groq 8s timeout + openrouter fail + gemini
  6.9s), resposta correta sobre USD/ouro.
- Saúde ao vivo: groq RATE_LIMITED (429 real) → pulado na hora;
  PRIMARY=request groq, actual openrouter + reason (teste C ao vivo).
- D (cloud off): cadeia termina no Ollama (unit); E SECRET local-only
  (unit `minha api_key` → cloud nunca chamado; live NÃO executado p/
  não persistir segredo real).
- Fast path intacto: cotação 0.1s MARKET_DATA; calculadora/taskmgr 0.0s;
  clarify instantâneo.
- **125/125 OK**, zero regressão. Backend + app relançados e vivos.

## Latências

routing <1ms · A 2.2s (cloud) · B 30.9s (2 fallbacks) · fast 0.0–0.1s ·
Ollama local ~21s p/ trivial (por isso é fallback, não default).

## Próximo

V4 visual. Nada iniciado.
