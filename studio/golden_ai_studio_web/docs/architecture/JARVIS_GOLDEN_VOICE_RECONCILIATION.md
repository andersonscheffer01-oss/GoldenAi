# JARVIS / GOLDEN — Voice Reconciliation

**B0/static restriction:** no microphone test, Windows audio change, VAD retuning, model download or dependency installation was performed.

## Golden legacy voice

| Field | Finding |
|---|---|
| Frontend | `studio_v7.html::toggleVoice()` creates browser `SpeechRecognition`/`webkitSpeechRecognition`, language `pt-BR`, final-result mode, then inserts text and calls `sendMessage()`. `SpeechSynthesis` reads messages. |
| Backend | Text enters legacy `/api/chat`; uploaded audio separately uses `/api/audio` and `core.audio.AudioService`. Server also exposes older `/api/jarvis/voice/*` routes. |
| STT | Browser-managed and unpinned for the Studio toggle; older server voice code can use faster-whisper. No Golden-owned browser model identity. |
| TTS | Browser `speechSynthesis`; an older server path references Edge TTS. Neither is the canonical provider contract. |
| VAD | No application VAD in the Studio toggle. Browser analyser/visual feedback is not speech endpointing. |
| Streaming | Recognition is final-result/utterance oriented; browser TTS is utterance oriented. |
| Barge-in | No legacy Studio barge-in. |
| Wake word | Legacy text/wake parsing exists in server voice helpers, but the Studio toggle is explicit user activation, not a validated acoustic wake loop. |
| Session | Browser recognition object is ephemeral; chat history is legacy session/in-memory behavior. |
| Security/audit | Browser permission is the main capture gate; canonical SecurityManager/AuditLog is not the owner of the browser capture path. |
| Desktop/Web | Studio is browser-first. Desktop has separate adapters but should delegate to Core VoiceService. |
| Windows audio | Browser/device behavior is outside the Core PCM contract; it cannot prove the current Windows mic/VAD issue. |

## Canonical Jarvis Voice

`jarvis_core/voice_service.py` and `realtime_voice/` own session identity, turn/epoch/generation, one `AudioInputProvider`, PortAudio/sounddevice input, 16 kHz mono PCM16 framing, Silero VAD, hybrid endpointing, local faster-whisper boundary, provider-neutral TTS, Windows SAPI fallback, cancellation and stale-generation protection. `VoiceService` routes privileged actions through `JarvisService`, `SecurityManager` and `AuditLog`. Wake lifecycle is a Core-owned lifecycle; provider detection remains replaceable.

Existing evidence confirms stream opening and aligned frames, but the real human speech sample remained near the silence baseline and did not establish a valid VAD speech-start/endpoint or acoustic barge-in. Do not interpret the legacy browser recognizer as proof against that restriction.

## Decisions

| Component | Decision |
|---|---|
| Browser permission/error UX | `ADAPT` into canonical Voice UI |
| Browser capture/STT/TTS | `LEGACY_FREEZE` / `REFERENCE_ONLY` |
| Audio level visualization | `ADAPT` as diagnostic read model only |
| Core VAD, endpointing, STT, TTS, session and cancellation | `KEEP_OURS` |
| Wake lifecycle | `KEEP_OURS`, merge only validated provider signals |
| History/context | `MERGE` read-only context contract, Jarvis owns authority |
| Model/provider routing | `MIGRATE_AUTHORITY` to `ModelRouter` |
| Security and AuditLog | `MIGRATE_AUTHORITY` to Core |

`GOLDEN_LEGACY_VOICE_FOUND: YES`
`CANONICAL_VOICE_OVERLAP: HIGH`
`USEFUL_LEGACY_VOICE_COMPONENTS: permission/error UX, explicit start/stop, language display, level feedback`
`VOICE_DUPLICATED_AUTHORITY_FOUND: YES` — browser/legacy routes can bypass the canonical VoiceService boundary.
`VOICE_RECOVERY_RECOMMENDATION: one Jarvis VoiceService; adapt presentation only; resolve the real signal gate before claiming STT/wake/barge-in parity.`
`VOICE_CONTROL_CENTER_TARGET: Jarvis -> Voice read model shared by Web and Desktop.`

## Radar Macro Voice Chat

### Static scope and evidence

`market.html` does not contain a standalone voice/chat component. It loads
`desktop_center.js`, exposes `data-open-pc` buttons labeled `Central PC`, and
links to `studio_v7.html` for the separate `Chat` view. The voice drawer itself
is injected by `desktop_center.js`; this audit did not execute it.

`desktop_center.js` owns the Radar drawer controls (`pcMic`, continuous
listening, transcript, response speech and quick PC commands). Its browser
capture path constructs `SpeechRecognition`/`webkitSpeechRecognition` with
`pt-BR`, `interimResults=true`, optional `continuous=true`, and sends only the
final transcript to `askBrain()`. No `MediaRecorder`, `getUserMedia`,
`WebSocket`, SSE or application VAD is used in this path.

### Radar call graph

```text
RADAR VOICE UI
  market.html data-open-pc
  -> desktop_center.js injected Central PC drawer / pcMic
  -> browser SpeechRecognition (permission + browser STT)
  -> final transcript, wake-prefix strip for "jarvis"/"golden"
  -> POST /api/jarvis/chat { text }
  -> server_agent._api_jarvis_chat
  -> JarvisService + Brain/Orchestrator/ModelRouter + ToolRegistry
  -> response / tool result
  -> POST /api/desktop/speech { text, voice } when pcSpeak is enabled
  -> Edge TTS or optional ElevenLabs; browser speechSynthesis fallback
  -> audio element / browser TTS -> pcResult and transcript UI
```

The Radar voice path does not call `/api/chat`, `/api/audio`,
`/api/jarvis/voice/transcribe`, `/api/jarvis/voice/tts` or
`/api/jarvis/voice/command`. It calls `/api/jarvis/voice-service/status` only
for status display in `refresh()`; capture and utterance handling remain in the
browser recognition object rather than in `VoiceService`.

### Required Radar classification

`RADAR_VOICE_FOUND: YES — limited to the Central PC voice drawer injected over Radar Macro.`

`RADAR_VOICE_FRONTEND: desktop_center.js; market.html supplies the open buttons and loads the script. Separate from studio_v7.html and jarvis_ui voice modules.`

`RADAR_VOICE_AUDIO_CAPTURE: Browser SpeechRecognition/webkitSpeechRecognition. No MediaRecorder, getUserMedia audio upload, raw PCM stream or PortAudio path.`

`RADAR_VOICE_STT: Browser-managed SpeechRecognition, pt-BR, interim results enabled; provider/model identity is browser-controlled and not pinned by Golden.`

`RADAR_VOICE_TTS: POST /api/desktop/speech; Edge TTS voices are the normal server path, optional ElevenLabs is exposed by the selected voice, and window.speechSynthesis is the browser fallback. Audio is returned as base64 and played through an Audio object.`

`RADAR_VOICE_BACKEND: /api/jarvis/chat for chat/commands; /api/desktop/speech for TTS; /api/desktop/status and /api/desktop/confirm for the PC drawer; /api/jarvis/voice-service/status is observation only.`

`RADAR_VOICE_MODEL: Jarvis Brain -> Orchestrator/ModelRouter; server registers real Groq/Gemini adapters when needed and returns model/routing metadata. The Radar frontend sends no model selection.`

`RADAR_VOICE_CONTEXT: Only the normalized transcript is sent. The frontend strips an optional jarvis/golden prefix and does not attach a Radar snapshot, chart, symbol, timeframe, news, macro or scanner payload.`

`RADAR_VOICE_MT5_CONTEXT: NONE explicit in the voice request. MT5 may be reached only indirectly if the generic Jarvis plan selects an available tool; no Radar chart/tick payload is forwarded.`

`RADAR_VOICE_MACRO_CONTEXT: NONE explicit. market.js loads macro/market data for its own panels, but desktop_center.js does not include it in /api/jarvis/chat.`

`RADAR_VOICE_SCANNER_CONTEXT: NONE explicit. ai_radar.js has separate scanner and analysis endpoints; no scanner result is passed into the voice request.`

`RADAR_VOICE_SECURITY: Browser microphone permission gates SpeechRecognition. Generic Jarvis tool execution proceeds through JarvisService/SecurityManager and confirmation tokens for protected actions; /api/desktop/speech itself is a TTS transport and has no separate canonical voice authorization gate.`

`RADAR_VOICE_AUDIT: Partial. /api/jarvis/chat records response metrics, telemetry and tool security/audit through the canonical service. The browser recognition event and /api/desktop/speech playback do not show a dedicated voice-turn AuditLog event in the traced path.`

`RADAR_VOICE_PROVENANCE: Partial. Chat responses can carry provider/model/routing metadata and canonical request telemetry; the Radar client does not create or propagate a voice session, turn, response, trace or audio artifact identity.`

`RADAR_VOICE_VS_STUDIO: INDEPENDENT_IMPLEMENTATION. Both use browser SpeechRecognition and explicit browser permission, but Studio uses studio_v7.html::toggleVoice -> /api/chat -> browser SpeechSynthesis, while Radar uses desktop_center.js -> /api/jarvis/chat -> server TTS with browser fallback. They do not share a voice component.`

`RADAR_VOICE_VS_JARVIS: UI_ONLY + JARVIS_VOICE_CLIENT boundary is not satisfied for capture. Radar observes VoiceService status but does not call its start/listen/stop flow; canonical VoiceService owns PortAudio/sounddevice, 16 kHz PCM framing, Silero VAD, hybrid endpointing, local faster-whisper, session/turn cancellation and provider-neutral TTS.`

`RADAR_VOICE_REUSE_DECISION: ADAPT permission/error and explicit start/stop presentation only; REFERENCE_ONLY for browser SpeechRecognition and browser TTS; KEEP canonical VoiceService capture, VAD, STT, TTS, session and cancellation; MERGE only a read-only Radar context contract through Jarvis authority if product requirements later call for contextual voice.`

### Radar voice decision matrix

| Component | Classification | Decision | Evidence-based reason |
|---|---|---|---|
| Central PC drawer in Radar | `INDEPENDENT_IMPLEMENTATION` | `ADAPT` | Useful presentation and explicit controls, but separate ownership from canonical VoiceService. |
| Browser SpeechRecognition capture | `SAME_AS_STUDIO` at primitive level | `REFERENCE_ONLY` | Same browser API family as Studio; provider identity and audio signal remain outside Jarvis authority. |
| `/api/jarvis/chat` command path | `JARVIS_VOICE_CLIENT` at command boundary | `KEEP` | It reaches the existing Jarvis Brain and service instead of creating a Golden brain. |
| `/api/jarvis/voice-service/status` polling | `JARVIS_VOICE_CLIENT` read-only | `ADAPT` | Useful status projection; it does not make browser capture canonical. |
| Server TTS plus browser fallback | `INDEPENDENT_IMPLEMENTATION` | `REFERENCE_ONLY` | Existing fallback UX is useful, but canonical TTS/provider policy remains Core-owned. |
| Radar/MT5/macro/scanner context injection | `UI_ONLY` absent | `MERGE` later, read-only | No current voice context builder exists in the traced Radar path. |

`VOICE_DUPLICATED_AUTHORITY_FOUND: YES — Radar browser STT and TTS can bypass the canonical VoiceService capture/session boundary, even though command execution reaches Jarvis Core.`

`VOICE_RECOVERY_RECOMMENDATION: keep one Jarvis VoiceService; adapt the Radar drawer to become a canonical client/read model, and introduce Radar context only through an explicit Jarvis-owned read-only context contract. Do not create a Radar VoiceService or a Golden Voice Brain.`

`VOICE_CONTROL_CENTER_TARGET: Radar Macro -> canonical Jarvis Voice UI/client -> Jarvis VoiceService -> JarvisService/SecurityManager/ToolRegistry/ModelRouter -> providers -> AuditLog.`

`MICROPHONE_TEST: NO`
`VAD_CHANGED: NO`
`WINDOWS_AUDIO_CHANGED: NO`
`MODELS_DOWNLOADED: NO`
`DEPENDENCIES_INSTALLED: NO`
