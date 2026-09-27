# Jarvis Voice Runtime Foundation

Status: `FOUNDATION` (Voice 2.0 capabilities remain deferred)

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

`voice_foundation.py` defines only contracts. The phase adds no audio device,
model, cloud API, native audio stack, or provider implementation. Raw audio is
kept in memory by the existing capture path and no raw recording or Voice
database is created by the foundation.

The eventual audio runtime must preserve one owner for the active microphone
stream and one owner for playback. The existing realtime queue, VAD, and
barge-in components remain behind the `VoiceService` boundary.

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

The next capability must be selected from Donor Audit 1B after this foundation
passes focused and relevant regression tests.
