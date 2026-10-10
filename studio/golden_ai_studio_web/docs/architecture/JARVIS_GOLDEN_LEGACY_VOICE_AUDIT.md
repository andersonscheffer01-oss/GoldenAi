# Golden Legacy Voice Chat Audit

**B0 scope:** static/read-only audit only. No microphone was opened, no Windows audio setting changed, no VAD threshold changed, no model downloaded and no dependency installed.

## Findings

| Field | Result |
|---|---|
| `GOLDEN_LEGACY_VOICE_FOUND` | YES |
| `VOICE_FRONTEND` | `studio_v7.html` `toggleVoice()` uses browser `SpeechRecognition`/`webkitSpeechRecognition`, `pt-BR`, `interimResults=false`; `SpeechSynthesis` is used for message read-aloud. Audio upload is a separate file workflow, not realtime microphone voice. |
| `VOICE_BACKEND` | Legacy Studio submits recognized text through `/api/chat`; uploaded audio uses `/api/audio` and `core.audio.AudioService`. Server also exposes older `/api/jarvis/voice/*` and canonical `/api/jarvis/voice-service/*` routes. |
| `VOICE_STT` | Legacy browser recognition provider/model is browser-managed and not pinned by Golden. Legacy server `jarvis_core.voice.JarvisVoice` can use faster-whisper for base64/audio paths. Canonical `FasterWhisperSTTProvider` is local-only and artifact-pinned. |
| `VOICE_TTS` | Legacy browser `speechSynthesis`; older server path uses Edge TTS (`pt-BR-FranciscaNeural` default). Canonical path has provider-neutral PCM contracts, Windows SAPI and bounded streaming orchestration. |
| `VOICE_VAD` | No application VAD in Studio voice chat. The `AudioContext` analyser in canonical `jarvis_ui/src/voice.js` is amplitude visualization only. Canonical Core owns Silero VAD plus endpointing. |
| `VOICE_STREAMING` | Legacy recognition is single-final-result, not streaming; legacy browser TTS is utterance-based. Canonical bounded TTS streaming exists; canonical STT remains utterance-based and real streaming is not claimed. |
| `VOICE_BARGE_IN` | Legacy Studio has no barge-in. Canonical VoiceService has cancellation, turn identity and barge-in plumbing, but acoustic real-speech barge-in remains unvalidated. |
| `VOICE_SESSION_MODEL` | Legacy recognition object is ephemeral; `/api/chat` keeps bounded in-memory conversation by session id. Canonical uses `VoiceSession`, session/turn/epoch/generation identities and ephemeral voice context. |
| `VOICE_CORE_INTEGRATION` | Legacy Studio text goes to `server_agent.api_chat`, whose legacy model/tool loop is a duplicated authority. Canonical voice goes `VoiceService -> JarvisService -> ToolRegistry/SecurityManager -> providers`. |
| `VOICE_SECURITY_INTEGRATION` | Legacy browser capture has browser permission only; chat may encounter legacy tool permission gates but does not make the browser voice layer canonical. Canonical privileged work is SecurityManager-gated. |
| `VOICE_AUDIT_INTEGRATION` | Legacy path has analytics/in-memory history but no dedicated canonical voice receipt. Canonical telemetry carries session/response/source/TTS identity and privileged work reaches AuditLog through JarvisService. |
| `Desktop integration` | Legacy Studio voice is browser-only. Desktop uses `desktop-voice.js` and Gateway polling of `/api/jarvis/voice-service/*`; no second desktop voice brain is allowed. |
| `Browser/Web integration` | Canonical Web UI uses browser recognition only outside Desktop; Desktop delegates to Core VoiceService. Browser media permission and iframe errors are surfaced. |
| `Windows audio` | Legacy browser path depends on browser/device permission. Canonical local path owns one `sounddevice`/PortAudio `RawInputStream`, 16 kHz mono PCM16 frames, and Windows SAPI output where configured. Existing evidence observed MME and USB audio, but real speech amplitude was near silence. |
| `Dependencies` | Legacy: browser SpeechRecognition/SpeechSynthesis and standard Web APIs. Canonical: sounddevice/PortAudio, local Silero VAD, pinned faster-whisper artifacts, optional SAPI/other TTS provider contracts. |

## Direct comparison with canonical Jarvis Voice

| Concern | Golden legacy Studio | Canonical Jarvis stack | B0 classification |
|---|---|---|---|
| Mic ownership | Browser recognition owns capture | `VoiceService` owns `AudioInputProvider` and one stream | `LEGACY_FREEZE` |
| Audio visualization | Browser analyser feedback | bounded Core diagnostics | `ADAPT` visual contract only |
| VAD | absent | `SileroVADAdapter` + `HybridEndpoint` | `KEEP_OURS` |
| STT | browser-managed, unpinned | local faster-whisper with cancellation/artifact policy | `KEEP_OURS` |
| TTS | browser speech synthesis | provider-neutral PCM, SAPI and bounded streaming | `KEEP_OURS` |
| Wake word | absent in Studio toggle | shared wake lifecycle; older text wake parsing remains legacy | `MERGE` lifecycle only |
| Turn-taking | final browser result immediately sends chat | transcript identity, semantic continuation and turn manager | `KEEP_OURS` |
| Barge-in | absent | cancellation and stale-generation protection; acoustic proof pending | `KEEP_OURS` |
| Browser errors | permission/capture/no-speech/network messages | Core error/state model | `ADAPT` messages into canonical state |
| Session/history | chat session in server memory | VoiceSession plus Core context | `MERGE` read-only context contract |
| Model routing | legacy `/api/chat` provider selection | `ModelRouter` and voice policy | `MIGRATE_AUTHORITY` |
| Security | legacy route/tool gates | SecurityManager and scoped approvals | `LEGACY_FREEZE` |
| Audit | analytics/in-memory | AuditLog and response telemetry | `MIGRATE_AUTHORITY` |

## Useful legacy components and the real microphone restriction

Useful legacy behavior is limited to browser permission/error UX, explicit start/stop affordance and lightweight amplitude visualization. It does **not** solve the current real microphone/VAD restriction: it bypasses the Core PCM/VAD contract and delegates recognition to a browser-managed provider, so its apparent success cannot prove Silero speech detection or Windows signal quality.

The canonical diagnostic already proves aligned 16 kHz frames and a valid stream, while human-confirmed speech produced near-silence amplitude. Reusing browser recognition as a workaround would create a second capture/STT authority and hide the real boundary problem. The safe reuse is UI/error vocabulary and a read-only level indicator behind the existing VoiceService.

`CANONICAL_VOICE_OVERLAP:` high at lifecycle, STT/TTS contracts, session state and Desktop/Web integration; low at the legacy browser implementation itself.

`USEFUL_LEGACY_VOICE_COMPONENTS:` browser permission/error messages, explicit microphone affordance, language selection, simple visual feedback.

`VOICE_REUSE_DECISIONS:` `ADAPT` UI/error patterns; `REFERENCE_ONLY` browser provider behavior; `LEGACY_FREEZE` direct capture/chat; `KEEP_OURS` Core VAD/STT/TTS/session/cancellation; `MIGRATE_AUTHORITY` provider routing and audit.

`VOICE_DUPLICATED_AUTHORITY_FOUND:` YES. The Studio browser path and legacy `server_agent` voice APIs can bypass the canonical VoiceService boundary for capture, STT/TTS or chat routing. No new duplicate is authorized.

`VOICE_RECOVERY_RECOMMENDATION:` keep one canonical VoiceService; adapt only presentation and browser permission feedback; do not retune VAD or replace the real-mic gate. Resolve the input signal gate before claiming acoustic wake, STT or barge-in parity.

`VOICE_CONTROL_CENTER_TARGET:` `Jarvis -> Voice`, with one read model for state, device readiness, wake/VAD/STT/TTS status, session/turn identity, interruption state, approval state, AuditLog link and disabled reasons. Web and Desktop consume the same model.

`REAL_MICROPHONE_TEST: NO`
`WINDOWS_AUDIO_CHANGED: NO`
`VAD_RETUNED: NO`
`MODELS_DOWNLOADED: NO`
`VOICE_SERVICE_REPLACED: NO`
