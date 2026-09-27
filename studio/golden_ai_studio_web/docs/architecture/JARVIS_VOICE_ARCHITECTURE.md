# Jarvis Voice Runtime Foundation

Status: `REAL_AUDIO_BOUNDARY_FOUNDATION` (acoustic wake remains deferred)

This document records the first Core-aligned Voice layer after Donor Audit 1B.
It is a capability boundary, not a second Jarvis brain.

## Ownership

`jarvis_core.voice_service.VoiceService` remains the single runtime owner for
the existing local microphone loop, STT entry point, TTS entry point, voice
conversation context, and response telemetry. It receives the existing
`JarvisService` instance and sends commands through that Core boundary.

The runtime does not own an LLM, tool registry, memory database, scheduler,
approval engine, or independent security policy. Privileged work remains:

```text
VoiceService -> JarvisService -> SecurityManager -> authorized capability
                                      |
                                   AuditLog
```

`VoiceSession` is ephemeral runtime identity. It is not persisted and does not
alter the canonical task database or conversation-memory stores.

## State and lifecycle

The existing realtime state machine is the canonical state model and now
explicitly represents:

```text
STOPPED -> IDLE -> LISTENING -> TRANSCRIBING -> THINKING -> SPEAKING -> IDLE
                                      \-> ERROR
SPEAKING -> INTERRUPTED -> LISTENING | IDLE
```

The legacy `VoiceService.state` strings remain available for existing API and
desktop callers. They are mapped into this guarded state machine. Invalid
transitions are rejected by `VoiceStateMachine`; the service records the
transition error and moves to a deterministic error state when possible.
Startup, shutdown, repeated shutdown, and restart are all lifecycle operations
on the same `VoiceService` instance. No second voice loop is created.

Wake activation is represented by `WakeLifecycle`, which composes with this
same `VoiceStateMachine`. It owns only arm/disarm/activate/complete identity;
it is not a second state machine or a wake-word model. Duplicate activation
IDs, stale session IDs, and activation after cancellation are rejected.

## Cancellation

`VoiceCancellation` is a small cooperative event with a stable reason. A
session cancellation is used for runtime shutdown. An operation cancellation
is used for the current turn/TTS boundary and is joined to the existing
`TurnManager` and barge-in cancellation event. No process kill or thread kill
is used as a Voice control mechanism.

Future STT/TTS implementations can consume the `SpeechToTextProvider` and
`TextToSpeechProvider` protocols. They must observe cancellation and must not
create independent Core or security paths.

## Audio and provider boundaries

`AudioInputProvider` is the single VoiceService-owned hardware boundary. It
lazy-imports `sounddevice`, owns one `RawInputStream`, and delivers canonical
PCM frames into the existing bounded queue. It is started only through the
explicit `VoiceService.start_audio_input()` lifecycle; VoiceService does not
autostart the microphone at boot. Raw audio remains in memory and no raw
recording or Voice database is created.

The eventual audio runtime must preserve one owner for the active microphone
stream and one owner for playback. The existing realtime queue, VAD, and
barge-in components remain behind the `VoiceService` boundary.

The current deterministic foundation reuses:

- `SileroVADAdapter` with explicit PCM/frame constants and reset semantics;
- `HybridEndpoint` for optional endpoint hangover behavior;
- `AudioFrameQueue` and `RealtimeVoicePipeline` for bounded frame ownership;
- `AudioInputProvider` and `FakeAudioInputProvider` for one-stream ownership
  and hardware-free lifecycle tests;
- `WakeLifecycle` and the injected canonical state machine in `VoiceService`.

`VoiceService.get_realtime_voice_pipeline()` is the owner boundary for the
optional pipeline, while `start_audio_input()` explicitly binds one provider
to that pipeline queue. Synthetic frames validate audio-to-VAD lifecycle
without opening a device, loading a wake model, or invoking Jarvis Core.

## Security, audit, and privacy

- Existing `SecurityManager`, confirmation model, and `AuditLog` remain the
  only security and audit authorities.
- Voice does not call privileged OS actions directly.
- Session and response identity continue through the existing `session_id`,
  `response_id`, `source_module`, and `tts_owner` telemetry.
- Raw audio is not persisted by this foundation.
- No secrets store or provider credential path is added.

## Donor provenance and constraints

Donor Audit 1B recommended same-Core ownership with adapter isolation first.
Its audio contracts and cancellation/VAD lifecycle were used as conceptual
inputs only. No donor source was copied into Golden. Desktop, tray, installer,
local donor API, and donor process/IPC code remain out of scope.

Process model: same Core ownership with adapter isolation. A separate process
requires measured native-audio failure evidence and an approved authenticated
IPC design; it is not introduced here. IPC added: `NO`.

## Deferred

The following are deliberately not implemented by this foundation:

- wake-word model integration and acoustic VAD changes;
- real or streaming STT/TTS provider work;
- microphone/device selection and speaker-device recovery;
- raw audio persistence or transcript persistence;
- barge-in behavior beyond cancellation readiness;
- Desktop, tray, overlay, installer, and UI integration;
- new scheduler, task, approval, notification, memory, or database systems.

The following remain deliberately deferred:

- acoustic wake detector/model selection and model download;
- real hardware smoke, device selection, and disconnected-device recovery;
- streaming STT/TTS and provider work;
- barge-in execution, even though cancellation readiness is preserved;
- Desktop, tray, overlay, installer, and UI integration.

Donor Audit 1B remains the authority for the acoustic wake capability after
this audio boundary passes focused and relevant regression tests.

The pre-Batch-02 real-audio and wake-provider gate, plus the Batch 02A result,
is recorded in
`JARVIS_VOICE_REAL_AUDIO_DECISION.md`. It selects adaptation of the existing
sounddevice capture behind one VoiceService-owned provider. The acoustic wake
provider and model-license decision remain pending human review.

## Autonomous local STT implementation

The approved local path is now implemented behind the existing voice
boundaries. `FasterWhisperSTTProvider` resolves only the pinned
`Systran/faster-whisper-small` CTranslate2 snapshot at revision
`536b0662742c02347bc0e980a01041f333bce120`, uses CPU `int8`, and passes
`local_files_only=True`. Missing or incomplete artifacts fail closed; there is
no model substitution or network fallback.

The provider accepts bounded in-memory PCM16/WAV utterances and emits final
`TranscriptEvent` values. It does not open audio hardware, persist raw audio,
call Core, execute tools, or create approval decisions. Cancellation is
cooperative: the current session/epoch is invalidated and any late result is
discarded by the transcript acceptance gate.

The explicit `VoiceService.start_audio_input()` path owns the single
`AudioInputProvider`, existing VAD/endpointing, and the STT provider. Only an
accepted final event reaches the existing VoiceService -> JarvisService ->
Core/SecurityManager boundary. Partial events are observable but cannot reach
Core, and duplicate final identities are accepted once.

This batch remains utterance-based rather than true streaming STT. Acoustic
wake, TTS, barge-in execution, remote STT, and Desktop integration remain
deferred. PT-BR quality, realtime factor, and model runtime RAM are still
unmeasured.
