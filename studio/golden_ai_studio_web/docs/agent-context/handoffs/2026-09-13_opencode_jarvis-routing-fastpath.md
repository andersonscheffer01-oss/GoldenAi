# Handoff — Routing + Fast Path + Metadados (latência)

## Estado

Pipeline voz/chat intocado. Mudanças só em roteamento determinístico
(arquitetura existente) + metadados frescos. Orchestrator segue `SHADOW`.

## Causas e correções

- **Bug 1 (stale):** voz nunca atualizava a route bar (só typed atualizava).
  Agora: resposta do chat carrega `route/skill/confidence/tool_provider`
  usados imediatamente; mirror de voz dispara `orchestrator/status`
  (last_decision é do comando falado). Rodapé mostra SKILL + PROVIDER.
- **Bug 2 (windows via LLM):** sem regra p/ taskmgr/notepad + fast path só
  em modo ON → CONVERSATION → Ollama → timeout. Novas regras WINDOWS
  (taskmgr singular/plural, notepad, calculadora já existia) e fast path
  determinístico em todos os modos (só LOW-RISK: steps + sem IA/plan/confirm).
- **Latência cotação:** regra MARKET_DATA determinística com moeda pelos
  aliases canônicos do `JarvisService` (sem parser paralelo) → sem LLM.
- Clarify ("abra ele") também sem LLM em qualquer modo (strings do modo
  ON preservadas; blocos antigos intactos).
- Execução continua via `JarvisService.execute_tool` (Security/Audit).

## Validação real

- Cotação: **0.1s** (era timeout 45s) — MARKET_DATA/market_data/0.97/
  deterministic(NONE)/get_exchange_rate/awesomeapi, "USD: R$ 5.13".
- Calculadora/notepad/taskmgr: 0.0–0.1s, `open_program`, sem LLM.
- "abra ele": instantâneo, clarify, nada executado.
- **121/121 OK**, zero regressão. Backend + app relançados e vivos.

## Arquivos

- `jarvis_core/orchestrator/orchestrator.py` (3 regras + `_detect_currency`)
- `jarvis_core/brain.py` (clarify + fast path todos os modos)
- `server_agent.py` (meta route/skill/confidence/tool_provider)
- `jarvis_desktop/`: `state.py` (+skill/provider), `chat_view.py`
  (SKILL/PROVIDER, deterministic→NONE), `main_window.py` (meta imediata,
  mirror atualiza route)
- `tests/test_jarvis_orchestrator.py` (+3), `tests/test_jarvis_desktop_interaction.py` (+1)

## Próximo

V4 visual. Nada iniciado.
