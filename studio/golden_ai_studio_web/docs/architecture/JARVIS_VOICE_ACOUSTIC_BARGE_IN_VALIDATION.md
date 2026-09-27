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

## Controlled human attempts

Three bounded attempts were authorized and executed. Attempts 1 and 2 used a
short deterministic tone with the real input and output devices. Attempt 3 used
the same path with a slightly more audible, still bounded tone. No attempt
observed human speech while playback was active:

| Attempt | Mic opened | Playback active | Human speech/VAD | Barge-in |
|---:|---|---|---|---|
| 1 | PASS | PASS | NOT DETECTED | NOT RUN |
| 2 | PASS | PASS | NOT DETECTED | NOT RUN |
| 3 | PASS | PASS | NOT DETECTED | NOT RUN |

The first harness invocation was invalid before playback because of a local
diagnostic variable error and was not counted as a controlled attempt. It was
cleaned up by process exit; no audio or transcript was persisted. The valid
attempts closed the input stream cleanly and aborted/flushed output on their
bounded timeout. They do not provide evidence for genuine human interruption,
generation invalidation, endpointing, or STT handling.

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

## Hardened diagnostic harness

The controlled coordinator is now persisted at
`jarvis_core/realtime_voice/human_barge_in_harness.py`. It is opt-in and is
not part of normal startup or the pytest collection. It uses the existing
`AudioInputProvider`, `RealtimeVoicePipeline`, `SileroVADAdapter`,
`BargeInController`, `VoiceService`, and provider-neutral audio output. The
harness only observes the existing VAD and installed VoiceService callback; it
does not call `accept_barge_in`, inject a VAD event, inject an endpoint, force a
cancellation, or create a second audio owner.

The coordinator now verifies microphone frame delivery before opening the
human speech window, confirms the output stream is active before printing the
human prompt, emits explicit playback/window timestamps, distinguishes
`BARGE_IN` from `TIMEOUT`, and keeps the bounded PCM tone and all diagnostics
in memory. It does not persist microphone audio or transcripts.

## Follow-up controlled attempts

The three earlier harness attempts remain historical attempts with
`REAL_HUMAN_SPEECH_USED: NO` and `VALID_ACOUSTIC_BARGE_IN_ATTEMPTS: 0`.
Three follow-up coordinator runs were made after hardening:

| Attempt | Playback/window coordination | VAD | Abort cause | Human speech evidence | Valid acoustic attempt |
|---:|---|---|---|---|---|
| 4 | Coordinator prompt was not observable in time | triggered | `BARGE_IN` | not attributable to human speech | NO |
| 5 | Coordinator prompt was not observable in time | triggered | `BARGE_IN` | not independently confirmed | NO |
| 6 | Prompt was coordinated after the countdown | not triggered | `TIMEOUT` | none observed | NO |

Attempts 4 and 5 prove only that the canonical pipeline can reach the
production barge-in callback under real hardware conditions; without verified
human speech during playback they are not acoustic barge-in evidence. Attempt
6 proves the synchronized no-speech path and clean timeout teardown. No
production thresholds, providers, devices, security boundaries, or turn-taking
logic were changed.

```yaml
HARNESS_ATTEMPTS_PREVIOUS: 3
HARNESS_ATTEMPTS_FOLLOW_UP: 3
VALID_ACOUSTIC_BARGE_IN_ATTEMPTS: 0
REAL_HUMAN_SPEECH_USED: NO
PRODUCTION_VOICE_LOGIC_CHANGED: NO
```

The real human gate remains pending. It must be repeated only when the human
operator can observe the live prompt and speak during confirmed playback.

## Interactive human-confirmed attempt

One interactive attempt was executed after baseline `7aeda32`. The operator
confirmed `SIM` after the harness stopped and asked whether the phrase had been
spoken during playback. This confirmation is kept separate from the technical
signals.

```yaml
HUMAN_CONFIRMATION: SIM
REAL_HUMAN_SPEECH_USED: YES
VALID_ACOUSTIC_ATTEMPT: YES
PLAYBACK_CONFIRMED_ACTIVE: YES
MIC_CONFIRMED_ACTIVE: YES
HUMAN_WINDOW_DURATION_SECONDS: 7.014
MIC_FRAMES_DURING_WINDOW: 234
INPUT_LEVEL_DURING_WINDOW: 246.46
VAD_TRIGGERED: NO
ENDPOINT_TRIGGERED: NO
SELF_TRIGGER_POLICY_DECISION: NOT_REACHED
OLD_GENERATION_INVALIDATED: NO
QUEUE_FLUSHED: YES
REAL_PLAYBACK_ABORTED: YES
PLAYBACK_ABORT_CAUSE: TIMEOUT
MIC_SURVIVED_ABORT: YES
USER_UTTERANCE_REMAINS_VALID: NO
LOCAL_STT_RECEIVED_USER_UTTERANCE: NO
OLD_AUDIO_RESUMED: NO
OLD_COMPLETION_IGNORED: NO
```

This is real evidence that the microphone path delivered frames while the
speaker was active, but the production VAD did not emit `SPEECH_STARTED` for
the confirmed human phrase. The deepest successful stage is
`REAL_MIC_CAPTURE`; the failure stage is `VAD`. No VAD threshold, model,
turn-taking, cancellation, or AEC behavior was changed. This gate therefore
failed at VAD and is ready for a separate, narrow VAD sensitivity investigation.

```yaml
REAL_HUMAN_BARGE_IN_VALIDATION: FAILED
ACOUSTIC_INTERRUPTION_VALIDATED: NO
POST_BARGE_IN_STT_VALIDATED: NO
SPEECH_SELF_TRIGGER_VALIDATION: INCONCLUSIVE
REAL_ACOUSTIC_BARGE_IN_VALIDATED: NO
AEC_NEEDED_BASED_ON_EVIDENCE: INCONCLUSIVE
AEC_RESEARCH_REQUIRED: NO
DEEPEST_SUCCESSFUL_STAGE: REAL_MIC_CAPTURE
FAILURE_STAGE: VAD
```
