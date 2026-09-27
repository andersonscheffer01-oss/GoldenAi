# Jarvis Acoustic Barge-In Validation

Status: `WAITING_FOR_HUMAN_TEST`.

## Gate boundary

This gate validates real speech and human interruption on the current
microphone/speaker configuration. It does not implement AEC, install DSP or
TTS dependencies, download models, tune VAD thresholds, or redesign
turn-taking. Existing `AudioInputProvider`, `SoundDeviceAudioOutputProvider`,
Silero VAD, `HybridEndpoint`, local STT, `SelfTriggerPolicy`, `TurnManager`,
and generation cancellation remain the owners.

## Hardware

- Input: device `1`, `Microfone (3- USB Audio Device)`
- Output: device `3`, `Alto-falantes (3- USB Audio Device)`
- Host API: MME for both input and output
- Default devices: unchanged from the previous coexistence gate
- Hardware configuration: partial; endpoint names do not prove the physical
  room, speaker placement, or general behavior on other devices.

The previous coexistence measurement already proved that both real streams can
open together, input continues during playback and after output abort, and no
stream remains alive afterward. It measured no VAD activation from a short
deterministic tone.

## Speech fixture decision

No approved local speech fixture was found. Existing WAV files are tracked or
temporary test artifacts with no gate-approved language/provenance declaration;
they are not used as speech evidence. No audio was downloaded and no new user
recording was created.

Therefore:

```yaml
LOCAL_SPEECH_FIXTURE_AVAILABLE: NO
SPEECH_FIXTURE_TEST: WAITING_FOR_HUMAN_INPUT
SPEECH_SELF_TRIGGER_VALIDATION: INCONCLUSIVE
```

A future run may use a short user-approved local speech sample, kept only in
memory, or a coordinated human test. It must measure microphone detection,
VAD, endpointing, STT reachability, and whether a false user turn is formed in
that order. A tone cannot establish speech self-transcription.

## Human barge-in procedure

The human test remains intentionally pending because the agent cannot safely
coordinate a spoken interruption without an explicit active session. The
bounded procedure is:

1. Open the real microphone and verify healthy frame delivery.
2. Start a short deterministic playback signal.
3. While playback is active, say a harmless diagnostic phrase such as
   `Jarvis, pare.` Do not use a command with side effects.
4. Observe the existing VAD, endpoint, `SelfTriggerPolicy`, TurnManager and
   cancellation path.
5. Confirm old generation invalidation, queue flush, output abort, microphone
   survival, valid new turn, and no resumed old audio.

No PASS is claimed until real human speech is observed. The test is limited to
three controlled attempts and does not persist microphone audio or transcript
content.

## Current decision

```yaml
REAL_USER_BARGE_IN_TEST: NOT_RUN
REAL_ACOUSTIC_BARGE_IN_VALIDATED: NO
AEC_IMPLEMENTED: NO
AEC_RESEARCH_REQUIRED: NO
PLAYBACK_REFERENCE_GUARD_RESEARCH_REQUIRED: NO
CORRELATION_NEEDED: NOT_NEEDED
RECOMMENDED_NEXT_STRATEGY: WAITING_FOR_CONTROLLED_HUMAN_BARGE_IN_TEST
```

No production code change is justified by the current evidence. Logical
barge-in regression remains covered by the existing deterministic suite.
