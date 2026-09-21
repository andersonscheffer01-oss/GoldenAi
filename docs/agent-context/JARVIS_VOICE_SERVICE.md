# Jarvis Desktop Voice Service — Fase 8

## O que é
Escuta de voz LOCAL no PC, sem navegador. O Golden já inicia ouvindo.

## Fluxo
```
Windows liga → Golden inicia → VoiceService (thread daemon) inicia
→ usuário fala "Jarvis" → OUVINDO → comando ("abra o metatrader")
→ Whisper STT → Brain (Ollama) → Registry → Tool Windows
→ TTS: "MetaTrader aberto."
```

## Arquitetura
- `jarvis_core/voice_service.py` — `VoiceService` (thread daemon, singleton `get_voice_service()`).
- Reutiliza sem duplicar: `voice.py` (wake word/STT/mic), `brain.py` (LLM), `service.py` (tools/segurança/auditoria).
- Auto-start em `start_server()` (server_agent.py), ao lado do monitor RADAR.
- Silêncio filtrado por RMS antes de gastar Whisper (SILENCE_RMS=150, janela de 6s).
- Wake word textual "jarvis" + janela de conversa de 30s para comandos de seguimento.

## TTS (ordem no modo `auto`)
1. **edge-tts** (neural, online) → mp3 → tocado via MediaPlayer WPF nativo (PowerShell).
2. **SAPI do Windows** via pywin32 (offline) — fallback sempre disponível.

## APIs
| Rota | Função |
|---|---|
| `POST /api/jarvis/voice-service/status` | estado, stats, last_heard/response/error |
| `POST /api/jarvis/voice-service/start` | inicia escuta (usa JarvisService do DesktopCenter) |
| `POST /api/jarvis/voice-service/stop` | para a escuta |
| `POST /api/jarvis/voice-service/speak` | fala um texto agora (`{"text": "..."}`) |

## Configuração (variáveis de ambiente)
| Variável | Default | Função |
|---|---|---|
| `JARVIS_VOICE_SERVICE` | `1` | `0` desativa auto-start |
| `JARVIS_VOICE_TTS` | `auto` | `edge` = só neural, `sapi` = só offline |
| `JARVIS_WHISPER_MODEL` | `base` | modelo faster-whisper |

## Bug corrigido na Fase 3 (voice.py)
`process_voice_command()` chamava `touch_interaction()` ANTES do filtro de
conversa → no daemon, qualquer som ambiente virava "conversa ativa" e era
executado como comando. Agora o touch só ocorre em wake word ou conversa real;
silêncio/ruído retornam `ignore` (comportamento já coberto por teste).

## Dependências (venv)
- faster-whisper 1.2.1 ✅ (já existia)
- sounddevice 0.5.6 ✅ (já existia)
- **edge-tts 7.2.8 ✅ (instalado nesta fase; adicionado ao requirements.txt)**
- pywin32 ✅ (já em requirements.txt — usado no fallback SAPI)

## Testes
- `tests/test_jarvis_voice_service.py`: 17/17 (mocks — sem microfone/TTS real).
- Suíte completa Jarvis: **44/44** (hardening 14 + memory 13 + voice 17).
- Smoke real: serviço iniciou com o servidor, transcreveu fala real do microfone,
  ignorou sem wake word, falou nas caixas de som via edge-tts, zero tracebacks.

## Limitações conhecidas
- Whisper roda em CPU (base int8): primeira transcrição tem alguns segundos de latência.
- edge-tts exige internet; sem rede cai para SAPI (voz robótica porém offline).
- Um único microfone padrão do sistema (sem seleção de dispositivo por enquanto).
