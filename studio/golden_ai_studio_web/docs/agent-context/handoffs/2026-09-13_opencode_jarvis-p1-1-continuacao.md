# Handoff — Codex → Opencode — Jarvis P1.1 CONTINUAÇÃO (2026-09-13)

## Estado

P1.1 continuada exatamente onde o Codex parou. Nenhum arquivo resetado
(sem repo git; estado inspecionado por mtime + leitura direta).
Status final: **PASS** — código + testes + smoke de microfone real com
fala humana validados em 2026-09-13.

## Codex preservado (sem alterações)

- `VOICE_FAST` em `orchestrator/models.py` + `policies.py`:
  PRIMARY `groq qwen/qwen3.8-27b`, FALLBACK cloud `groq/compound-mini`,
  LOCAL/SECRET `ollama qwen2.5-coder:14b`, timeout voz 2.5 s.
- `model_router.py`: `select()` filtra por `AVAILABLE`; SECRET nunca vai
  ao cloud; `execute()` marca o adapter **bem-sucedido** como `AVAILABLE`
  (linhas 88-89) — era o ponto final do Codex e está completo/funcional.
- `orchestrator.py`: `source=voice` + CONVERSATION simples → `VOICE_FAST`;
  ação → `GENERAL`; análise profunda → `DEEP`. Fast paths intactos.
- `brain.py`: system prompt falado 1-4 frases PT-BR; histórico ±4 turnos
  só em `VOICE_FAST`; `last_llm` com requested/actual/TTFT/generation.
- `output_mode.py`: AUTO/VOICE/TEXT/VOICE_AND_TEXT + parse determinístico.
- Benchmark `before.json`: qwen3.8-27b TTFT P50 302 ms/total 381 ms;
  compound-mini 1168/1254 ms; ollama quente 47/1679 ms; 8b-instant 0/8.

## Alteração Opencode (1 linha, aditiva)

- `jarvis_core/voice_service.py` (`_handle`, timings): adicionado
  `"fallback": bool(llm.get("fallback", False))` — era o único campo da
  telemetria DEV ausente no evento de voz (route já existia no top-level;
  DEV lê `vent.route` + `vtim.*`). Sem mudança de comportamento.

## Validação

- `py_compile`: 14 módulos P1.1 OK.
- P1.1: `12 passed`. Voz (p1 + service + p11): `46 passed, 11 subtests`.
- Suíte completa: **165 passed, 72 subtests passed** (baseline Codex 166;
  delta = 1 teste a menos coletado, **zero falhas** — sem regressão).
- Recovery verificado por script: primary 429 → fallback ollama OK;
  ollama `AVAILABLE`, groq permanece `RATE_LIMITED` (cooldown respeitado).
- Fast paths 0 LLM, gating texto→GENERAL/voz→VOICE_FAST, output modes,
  contexto `voice_capture=true`, follow-up, TTS único e anti-autoescuta:
  cobertos por testes (todos PASS) + verificação por script.
- Servidor live: `:8765` OK; VoiceService `WAITING_WAKE`, Whisper small PT.

## A/B de estilo (pequeno, mesmo modelo qwen3.8-27b)

`tests/benchmark_voice_conversation_p11_after.json`:
GENERAL 5/8 ok, 676 chars, score 3 · VOICE_FAST 3/8 ok, 169 chars,
score 8 · TTFT P50 ~288 vs ~410 ms. Falhas = rate-limit do burst
(16 chamadas seguidas); resultado direcional confirma prompt de voz
curto e natural. Sem re-benchmark.

## Streaming

Transporte: Groq chamado com `stream=True` p/ modelos de voz + TTFT
medido no benchmark. Síntese incremental (token→TTS/UI): **DEFERRED**
(pipeline serial; documentado como limitação P1).

## Pendente (usuário) — CONCLUÍDO ✅

Smoke microfone real com fala humana, validado em 2026-09-13 (~11:29–11:47):
A. "me explique o Forex" → CONVERSATION/VOICE_FAST/groq-qwen, curta PT-BR,
   falada + mirror. PASS.
B. "qual é a cotação do dólar?" → R$ 5,13 falado = provider real
   (AwesomeAPI 5,1262); MARKET_DATA 0 LLM. PASS.
C. "abra a calculadora" → WINDOWS/open_program, 0 LLM, janela abriu,
   "Calculadora aberto." PASS.
D. "explica de outro jeito" → contexto Forex mantido, reexplicou por
   outro ângulo (alavancagem/liquidez/risco), falado. PASS.
Zero autoescuta (fala do Jarvis nunca virou comando). Observações:
frases sem "Jarvis" fora da janela de 30 s são ignoradas por design;
STT small às vezes trunca o wake word — padrão robusto: "Jarvis, ..." em
frase única e contínua. Não iniciar P2.
