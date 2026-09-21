# Handoff — Jarvis P1.2 STT Robustness (2026-09-13, Opencode)

## Estado

**PASS.** 7/7 intents em fala humana real, wake intacta, zero regressão.
P1.1 preservada (Brain, VOICE_FAST, providers, fast paths intocados).

## Mudanças (só captura/STT/telemetria)

- `jarvis_core/voice.py`: `get_input_device_info()` (somente leitura);
  `JARVIS_PRE_ROLL_SECONDS` (default auto=0,5 s); trava anti-contaminação
  da calibração (`JARVIS_CALIBRATION_MAX_JUMP=4`); peak/clipping por captura
  (`peak`, `clipped_samples`, `near_clip_samples`, `clipping`);
  `pre_roll_ms`/`end_silence_target_ms` no retorno; `last_capture` (sem áudio)
  + `mic` + `initial_prompt` + `pre_roll_seconds` no `status()`.
- `jarvis_core/voice_service.py`: timings com `raw_transcript`,
  `stt_confidence`, `avg_logprob`, `no_speech_prob`, `compression_ratio`,
  `peak`, `clipped_samples`, `pre_roll_ms`; `_handle_rejected_speech()`:
  `LOW_CONFIDENCE` com texto fala "Não entendi bem. Pode repetir?",
  `IGNORED_NOISE` silencioso.
- `jarvis_desktop/views/dev_view.py`: linhas MIC / AUDIO / RAW /
  NORMALIZED / STT CONF.
- `tests/test_jarvis_stt_robustness_p12.py`: 13 novos (pre-roll, calibração,
  clipping ±, end-silence, device shape, status, feedback falado, silêncio
  p/ ruído, raw telemetry, wake preservation ×2). Sounddevice mockado com
  relógio virtual (64 ms/bloco).

## Baseline medido

Mic USB (MME idx 1, mono, nativo 44100→16000, 1 conversão). Gate
`max(110, floor*2.2+55)`; floor real 5–23. Pre-roll 0,5 s; end 550 ms;
small/int8, beam 1, best_of 1, cond_prev=False, prompt=vocabulário.
Gates: no_speech≥0,65 / logprob<-1,35 / compr>2,8.

## Bateria real (defaults) — 7/7

| # | RAW | conf | STT | route |
|---|---|---:|---:|---|
| A horas | "Jarvis, que horas são?" | 0,65 | 2002 | SYSTEM |
| B dólar | "Jarvis, com a cotação do dólar." | 0,72 | 2749 | MARKET_DATA R$5,13 |
| C forex | "Me explique o que é Forex" | 0,70 | 2386 | VOICE_FAST/groq |
| D calc | "Jarvis, abra a calculadora." | 0,69 | 2009 | WINDOWS 0 LLM |
| E taskmgr | "Jarvis, Abre o Gerenciador de Tarefas." | 0,77 | 2363 | WINDOWS 0 LLM |
| F ouro | "Jarvis, o ouro está subindo hoje" | 0,60 | 2030 | VOICE_FAST, honesto sem dado |
| G follow | "Jarvis, explique de outro jeito." | 0,72 | 2030 | VOICE_FAST, contexto ouro |

STT P50 ~2030 ms / P95 ~2749 ms. Sem clipping (peaks 1613–6736).
C-1ª tentativa falhou por restart sem adapters (infra, não STT).

## A/B variante (silence 700 ms + beam 2) — 3 frases

B 0,80/2085 · C 0,65/2255 · G 0,75/1962. Sem ganho fora do ruído →
**final = defaults**. Pre-roll 500 ms validado (onsets intactos; acima do
teto de 300 ms sugerido porque não adiciona latência). Base/prompt-A/B
dispensados (7/7 atingido).

## Validação

- Suíte: **178 passed, 72 subtests** (165 + 13 novos), zero regressão.
- Fast paths + VOICE_FAST + follow-up + output modes + self-listening +
  provider recovery: intactos (testes + bateria real).
- Servidor recarregado na config final; groq ONLINE.

## Limitações / próximo

- Adapters cloud = registro lazy no 1º `/api/jarvis/chat`; restart puro
  deixa voz no Ollama direto (45 s) até registrar. Workaround aplicado;
  eager no boot proposto.
- Janela de captura 6 s pode partir frase lenta (pausa >550 ms fecha gate).
- `LOW_CONFIDENCE` falado coberto por teste, ainda sem prova de campo.
- Não iniciar P2 sem autorização.
