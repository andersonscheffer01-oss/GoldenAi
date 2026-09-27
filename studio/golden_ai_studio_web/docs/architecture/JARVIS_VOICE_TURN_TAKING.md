# Jarvis Voice Turn-Taking and Barge-In Foundation

Status: logical foundation complete with hardware-free validation.

## Ownership

`VoiceService` remains the orchestration owner. The existing
`TurnManager`, `VoiceStateMachine`, `VoiceCancellation`, realtime VAD/STT
pipeline, provider-neutral TTS contract, and bounded audio output contract are
reused. No second Core, state machine, turn manager, cancellation framework,
SecurityManager, or task database was introduced.

## Barge-in ordering

`VoiceService.accept_barge_in()` performs the safety-critical sequence:

1. increment the output generation;
2. cancel the old operation token and current turn;
3. cancel TTS and flush the owned audio output;
4. create the next turn with a fresh operation token;
5. transition the shared state machine back to `LISTENING`.

Late Core/TTS/output callbacks are rejected by turn, generation, session, and
cancellation guards. A new response clears only the old barge-in marker; it
does not reuse the old operation token.

The streaming orchestrator now applies the same stale/cancel check after final
TTS synthesis and before final playback, covering the race where cancellation
arrives while the last chunk is being synthesized.

## Self-trigger boundary

`SelfTriggerPolicy` classifies synthetic/input evidence as
`ALLOW_BARGE_IN`, `IGNORE_AS_SELF_TRIGGER`, or `UNCERTAIN`. Known user speech
is allowed, explicit self-output is ignored, and uncertain input remains
observable rather than permanently suppressing VAD during playback. This is a
policy boundary only; real acoustic echo cancellation is not implemented or
validated.

VAD failures are counted and reset at the realtime boundary so one bad model
call does not terminate the processing loop. STT, Core, TTS, output, and
policy failures remain contained by their existing service boundaries.

## Validation limits

The tests use deterministic fake TTS/output and synthetic VAD/barge-in events.
No microphone, speaker, Piper runtime, voice model, Edge TTS, cloud TTS, or
database migration is used by this phase.

```yaml
LOGICAL_BARGE_IN: PASS
REAL_ACOUSTIC_BARGE_IN: NOT_VALIDATED
REAL_AEC: NO
CORE_GENERATION_CANCELLATION: PARTIAL
REAL_TTS_PROVIDER: DEFERRED
```
