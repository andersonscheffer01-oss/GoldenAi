# Handoff — Voz definitiva (wake, estados, evento, sem fake)

## Estado

Chat digitado, fast paths, providers e visual intactos. SHADOW mantido.
Sem segundo STT/VoiceService/parser; sem animação de áudio fake.

## Root cause do routing de voz

`strip_wake_word` só removia "jarvis" ASCII grudado e o espelho não
associava resposta ao comando. Agora: normalização compartilhada mínima
(Jarvis/Járvis + pontuação no INÍCIO; meio da frase preservado) e o
comando limpo percorre o MESMO `CentralOrchestrator` do digitado.

## Mudanças

- `voice.py`: `_strip_accents`, detect/strip com variantes; `record_*`
  aceita `level_callback` (RMS real por bloco); `listen_more` p/ wake
  sozinha (antes caía no ignore silencioso do service).
- `voice_service.py`: estados reais WAITING_WAKE/LISTENING/WAKE_DETECTED/
  TRANSCRIBING/PROCESSING/SPEAKING/ERROR/OFF; `last_event{id,heard,route,
  skill,confidence,tool,tool_provider,response,error,timings,capture/stt/
  routing/execution/llm/tts_start/total}`; `level{rms,age_ms}`; plano
  `{"response"}` vira fala (antes caía em "Ferramenta não cadastrada").
- Desktop: `hud_for_voice`, HUD AGUARDANDO/TRANSCRIBINDO/PROCESSANDO/
  FALANDO, pulso modulado pelo RMS real recente (sem dado = sem onda),
  transcrição interim no sub-HUD, espelho por ID com metadados do evento
  (sem reenvio; sem orch poll misturado), poll de voz 2s, DEV com
  VOICE/EVENT/timings, mic real inalterado.

## Validação

- Paridade typed/voice: cotação→MARKET_DATA, calculadora→WINDOWS,
  horas→SYSTEM, "abra ele"→CLARIFY (unit).
- Pipeline real (sem mic): cotação MARKET_DATA 0.97 awesomeapi em 95ms
  exec; clarify sem execução; calculadora ABRIU de verdade; TTS falou
  (edge ~5-12s). Timings por fase registrados.
- Mirror com evento real: YOU+JARVIS+metadados (MARKET_DATA/market_data/
  0.97/AWESOMEAPI/95ms); ruído/wake-sozinha nunca entram no chat;
  1 comando = 1 execução (0 posts a /api/jarvis/chat no espelho).
- T1 ao vivo: service LISTENING rodando, sem evento no silêncio.
- Screenshot: HUD âmbar TRANSCRIBINDO com mic real ativo.
- **132/132 OK**, zero regressão. Backend + app relançados e vivos.

## Limites

- Sem mic neste ambiente p/ STT ponta-a-ponta; mic/STT inalterados.
- Ollama segue lento (fora de escopo desta fase).

## Próximo

V4 visual. Nada iniciado.
