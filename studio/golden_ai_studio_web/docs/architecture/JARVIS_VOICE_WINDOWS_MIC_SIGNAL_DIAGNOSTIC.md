# Jarvis Windows Microphone Signal Path Diagnostic

Status: `DIAGNOSTIC_COMPLETE_EXTERNAL_OR_HOST_PATH_UNRESOLVED`.

Baseline: `714c476`.

## Scope and safety

This gate inspected the real Windows microphone path without changing the
Windows audio configuration, endpoint defaults, VAD thresholds, STT settings,
voice architecture, dependencies, database files, or `device_registry.json`.
The captures were bounded and numeric-only. No microphone PCM, recording,
transcript, or cloud payload was persisted.

No automatic repair was attempted. `pycaw` and `soundcard` were not installed
in the existing virtual environment, so endpoint volume/gain could not be read
through those optional libraries and no package was installed to obtain them.

## Windows state

```yaml
USERPROFILE: C:\\Users\\Anderson
KNOWN_FOLDER_DOCUMENTS: C:\\Users\\Anderson\\Documents
KNOWN_FOLDER_DOCUMENTS_EXISTS: YES
MICROPHONE_CONSENT: Allow
MICROPHONE_NONPACKAGED_CONSENT: Allow
DOCUMENTS_REDIRECTED_TO_ONEDRIVE: NO_EVIDENCE
DEVICE_REGISTRY_TOUCHED: NO
WINDOWS_AUDIO_SETTINGS_CHANGED: NO
```

The Windows Known Folder and the environment profile agree in this session.
The parent directory exists. No hardcoded user-profile path was introduced by
this diagnostic.

## Device and host-API inventory

The selected production input remains device `1`:

```yaml
SELECTED_INPUT_DEVICE: 1
SELECTED_INPUT_NAME: Microfone (3- USB Audio Device)
SELECTED_INPUT_HOST_API: MME
SELECTED_INPUT_MAX_CHANNELS: 1
SELECTED_INPUT_DEFAULT_RATE: 44100
SELECTED_OUTPUT_DEVICE: 3
SELECTED_OUTPUT_NAME: Alto-falantes (3- USB Audio Device)
```

The same or similarly named USB input is exposed through multiple host APIs:

| Device | Host API | Default rate | 16 kHz mono probe |
|---:|---|---:|---|
| 1 | MME | 44,100 | opened |
| 7 | Windows DirectSound | 44,100 | opened |
| 15 | Windows WASAPI | 48,000 | invalid sample rate |
| 24 | Windows WDM-KS | 44,100 | invalid device |

Native-rate passive probes opened for devices `7`, `15`, and `24`; they are
host/API observations only and are not human speech tests.

## MME selected-path observations

### Previous human-confirmed speech window

The operator confirmed speaking the requested phrase during the bounded
speech-only window. This is the only evidence in this gate that is labeled
human speech. It showed valid frame timing and a near-zero signal:

```yaml
HUMAN_CONFIRMATION: SIM
ACTUAL_RATE: 16000
FRAMES_RECEIVED: 200
FRAME_DROPS: 0
RAW_PCM16_RMS_MEAN: 0.478
RAW_PCM16_RMS_MAX: 0.522
RAW_PCM16_PEAK_MAX: 1
RAW_PCM16_NONZERO_PERCENT: NOT_CAPTURED_IN_THAT_RUN
RAW_PCM16_UNIQUE_VALUES: NOT_CAPTURED_IN_THAT_RUN
RAW_PCM16_CLIPPED_PERCENT: NOT_CAPTURED_IN_THAT_RUN
FRAME_HASH_OR_BYTE_CHANGE: NOT_CAPTURED_IN_THAT_RUN
VAD_PROB_MAX: 0.03321
VAD_SPEECH_STARTED: NO
```

This supports the earlier `MIC_SIGNAL_TOO_LOW` finding at the provider
boundary. It does not justify lowering the VAD threshold.

### Current passive baseline, no human speech

A later three-second passive capture with the operator silent produced a
materially different, non-silent signal and high Silero probabilities:

```yaml
HUMAN_SPEECH_CLAIM: NO
FRAMES_EXPECTED: 100
FRAMES_RECEIVED: 101
FRAME_DROPS: 0
RAW_PCM16_RMS_MEAN: 93.9956
RAW_PCM16_RMS_MAX: 287.8024
RAW_PCM16_MIN: -988
RAW_PCM16_MAX: 922
RAW_PCM16_PEAK_MAX: 988
RAW_PCM16_NONZERO_PERCENT: 99.0986
RAW_PCM16_UNIQUE_VALUES_PER_FRAME_MEAN: 226.0693
RAW_PCM16_UNIQUE_VALUES_PER_FRAME_MAX: 378
RAW_PCM16_CLIPPED_PERCENT: 0
FRAME_HASH_UNIQUE_COUNT: 101
FRAME_BYTE_CHANGE_DETECTED: YES
VAD_PROB_MIN: 0.18310
VAD_PROB_MAX: 0.99356
VAD_PROB_MEAN: 0.92685
VAD_SPEECH_STARTED: YES
```

Because no human speech occurred, this must be classified as non-silent
signal/noise or another capture-path source, not as successful speech capture.
The difference from the earlier human-confirmed run means the path is not
stable enough to claim a single fixed gain diagnosis from passive VAD output.

## DirectSound comparison

One bounded human-confirmed attempt was made on device `7`, one attempt only.
The provider reported frames during the window, but the existing pipeline
diagnostic observer consumed zero frames/probabilities for that window:

```yaml
HOST_API: Windows DirectSound
DEVICE: 7
HUMAN_CONFIRMATION: SIM
PROVIDER_FRAMES_DURING_WINDOW: 199
PIPELINE_FRAMES_RECEIVED: 0
VAD_PROBABILITY_RESPONDED: NO
VAD_SPEECH_STARTED: NO
```

This is a delivery/consumer mismatch in that run, not evidence that human
speech was absent. It is also not evidence that DirectSound is a valid
production replacement.

A separate passive three-second DirectSound capture did reach the pipeline,
but again no human speech occurred and the signal was high/noisy:

```yaml
HUMAN_SPEECH_CLAIM: NO
FRAMES_RECEIVED: 100
RAW_PCM16_RMS_MEAN: 55.6783
RAW_PCM16_PEAK_MAX: 466
RAW_PCM16_NONZERO_PERCENT: 98.50625
RAW_PCM16_UNIQUE_VALUES_PER_FRAME_MEAN: 174.24
RAW_PCM16_CLIPPED_PERCENT: 0
FRAME_HASH_UNIQUE_COUNT: 100
FRAME_BYTE_CHANGE_DETECTED: YES
VAD_PROB_MAX: 0.99122
VAD_SPEECH_STARTED: YES
```

The DirectSound passive result has the same important limitation: a VAD event
in a silent human window is not a human-speech proof.

## Native-rate passive probes

These probes used the existing `sounddevice` library directly and did not send
audio to STT or persist it:

```yaml
DEVICE_7_DIRECTSOUND_44100:
  FRAMES: 56
  RMS: 220.129
  PEAK: 3499
  ERRORS: 0
DEVICE_15_WASAPI_48000:
  FRAMES: 117
  RMS: 75.927
  PEAK: 524
  ERRORS: 0
DEVICE_24_WDM_KS_44100:
  FRAMES: 17
  RMS: 122.273
  PEAK: 916
  ERRORS: 0
```

These measurements confirm host/API-specific behavior, but no alternate
endpoint is promoted because none received a human-confirmed speech sample
with an interpretable pipeline result.

## Root-cause boundary

```yaml
PCM_FRAME_CONTRACT: PASS
FRAME_CONTINUITY: PASS_ON_MME_HUMAN_RUN
WINDOWS_MICROPHONE_PERMISSION: PASS
MME_HUMAN_SIGNAL_LEVEL: FAIL_IN_PRIOR_CONFIRMED_RUN
PASSIVE_SIGNAL_STABILITY: FAIL_OR_UNRESOLVED
HOST_API_CAPTURE_PATH_DIFFERENCE: OBSERVED
PIPELINE_CONSUMER_MISMATCH_ON_DIRECTSOUND_ATTEMPT: OBSERVED
PRODUCTION_ENDPOINT_REPLACEMENT_JUSTIFIED: NO
VAD_THRESHOLD_TUNING_JUSTIFIED: NO
AUTOMATIC_REPAIR_JUSTIFIED: NO
```

The narrowest defensible conclusion is `EXTERNAL_OR_HOST_API_CAPTURE_PATH`
with unresolved variability. The evidence does not distinguish USB device
routing, Windows mixer/input gain, endpoint selection, ambient/noise source,
or host-API delivery behavior. The next action requires a controlled human
comparison with one endpoint at a time, not production tuning.

## Regression and retention

The diagnostic harness remains opt-in and reuses the existing voice path. The
new metrics are aggregate values and SHA-256 frame hashes held in memory only;
raw PCM is never retained in the observation object. Focused tests passed.

```yaml
FOCUSED_TESTS: 7 passed
PY_COMPILE: PASS
GIT_DIFF_CHECK: PASS
RAW_MIC_AUDIO_PERSISTED: NO
TRANSCRIPT_PERSISTED: NO
CLOUD_SERVICE_USED: NO
DEPENDENCIES_INSTALLED: NO
DEVICE_REGISTRY_TOUCHED: NO
```

## Gate result

```yaml
WINDOWS_MIC_SIGNAL_DIAGNOSTIC: PARTIAL
ROOT_CAUSE_CONFIRMED: NO
EXTERNAL_OR_HOST_API_PATH_SUSPECTED: YES
REAL_HUMAN_SPEECH_VALIDATED_ON_CURRENT_SIGNAL: NO
PRODUCTION_CHANGED: NO
NEXT_GATE: CONTROLLED_HUMAN_ENDPOINT_COMPARISON
```
