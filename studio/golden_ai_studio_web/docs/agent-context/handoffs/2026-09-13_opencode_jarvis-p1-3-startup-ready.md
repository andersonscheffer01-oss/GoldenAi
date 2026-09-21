# Handoff — Jarvis P1.3 Startup/Ready (2026-09-13, Opencode)

## Estado

**PASS.** Primeira pergunta comporta-se como as demais; restart frio real
testado com voz humana. Suíte **199 passed, 72 subtests**, zero regressão.

## Startup mapeado (antes)

- EAGER: MT5, chaves, HTTP bind, monitor, DESKTOP_CENTER (registry,
  security, orchestrator, tasks, memory), voice start + STT warmup async.
- LAZY (gap): adapters cloud — só no 1º `/api/jarvis/chat` → voz caía no
  Ollama direto (45 s) após restart.
- BACKGROUND: STT warmup, monitor. ON-DEMAND: Ollama model load, TTS vozes.

## Mudanças

- `jarvis_core/readiness.py` (novo): SSOT STARTING→CORE_READY→WARMING→
  READY|DEGRADED|FAILED; tempos core/full/reg/health/sttwarm; default READY
  (pass-through p/ testes); sem segredos.
- `server_agent.py`: `read_jarvis_api_keys`/`call_groq_model`/
  `call_gemini_model` em nível de módulo (métodos delegam, idênticos);
  `probe_groq_health` (models-list, zero token) e `probe_ollama_health`
  (/api/tags); `warm_jarvis_boot()` (eager + probes + STT wait, nunca
  derruba); `start_server` com begin/core_ready/warm-thread/serve em
  try-finally (stop da voz); rota `/api/jarvis/readiness`; bloco
  `readiness` no providers/status.
- `jarvis_core/voice_service.py`: gate em `_handle` — durante WARMING fala
  "Estou iniciando, tente novamente em alguns segundos." (evento WARMING).
- `jarvis_core/orchestrator/model_router.py`: `usable()` + cooldown
  (transitórios retornam após 60 s; AUTH/OFFLINE não); `last_failure_at`;
  timeout local 45 s p/ non-cloud não-voz (SECRET funcionava nunca: 14b CPU
  > 8 s); VOICE_FAST inalterado (2,5/6 s).
- `policies.py`: `LOCAL_TIMEOUT_SECONDS=45` (+env).
- Desktop: `ProvidersPanel` linha JARVIS state; DEV linhas READY.
- `tests/test_jarvis_startup_ready_p13.py`: 20 testes (readiness, eager
  idempotente, SECRET local, 429/auth/offline, cooldown, fast outage,
  warming gate, shutdown). Bug achado por teste: `complete()` virava
  DEGRADED→READY (corrigido p/ terminal idempotente).

## Restart frio real (voz humana)

- Boot: READY, core ~90–120 ms, full ~6,7–6,9 s (STT load, background).
  4/4 adapters EAGER; groq ONLINE (models-list); ollama ONLINE + modelos
  presentes sem carregar; STT warm READY.
- 1º turno voz "Forex": VOICE_FAST/groq/qwen, fallback False, TTFT 347 ms
  (= turnos aquecidos ~341 ms; delta ≈ 0).
- Hora→SYSTEM 0 LLM; calculadora abriu (WINDOWS 0 LLM); dólar R$ 5,13
  (MARKET_DATA 0 LLM). Stats: 7 heard/7 commands/0 errors.
- SECRET ao vivo: "senha" → só ollama (zero cloud); 1ª chamada fria
  estourou 8 s (load 14b), cooldown segurou, 2ª após 60 s com modelo
  residente + timeout 45 s → ok True em 11,8 s.
- Texto 1º turno: CONVERSATION/groq, TTFT 326 ms, total 675 ms.

## Processos

1 listener (:8765, worker 542 MB) + 1 stub pai 4 MB (determinístico em
todo start; ambiental, pré-existente). Desktop: 1 instância (não aberto
em teste; painel atualizado por polling existente).

## Limitações / próximo

- Fallback 429 ao vivo coberto por teste (não simulado em prod p/ não
  destruir config).
- `LOW_CONFIDENCE` falado segue sem prova de campo.
- Janela 6 s pode partir frase lenta (conhecido P1.2).
- Não iniciar P2 sem autorização.
