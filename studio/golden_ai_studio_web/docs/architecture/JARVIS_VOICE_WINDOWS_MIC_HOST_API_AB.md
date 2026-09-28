# Jarvis Windows Microphone Host-API A/B Validation

Status: `PARTIAL_WITH_RESTRICTIONS`.

Baseline: `98edc62`.

## Scope and rules

This gate compared the current USB microphone through the Windows host APIs
without changing production capture, Windows defaults, VAD thresholds, gain,
AEC, STT, or `device_registry.json`. One host API was tested at a time. Raw
PCM was measured in memory only; no audio, WAV, transcript, or cloud payload
was persisted.

Passive probes and VAD events were never treated as human speech. A speech
sample became valid only after the operator explicitly confirmed `SIM`.

## Device matrix

```yaml
TARGET_PHYSICAL_MIC: USB Audio Device, identity inferred from matching names
MME_DEVICE: 1
DIRECTSOUND_DEVICE: 7
WASAPI_DEVICE: 15
WDM_KS_DEVICE: 24
SAME_PHYSICAL_DEVICE_CONFIDENCE: MEDIUM
```

| Host API | Device | Name | Native rate | Prepared stream |
|---|---:|---|---:|---|
| MME | 1 | Microfone (3- USB Audio Device) | 44,100 | PASS |
| DirectSound | 7 | Microfone (3- USB Audio Device) | 44,100 | PASS |
| WASAPI | 15 | Microfone (3- USB Audio Device) | 48,000 | PASS |
| WDM-KS | 24 | Microfone (USB Audio Device) | 44,100 | PASS |

## Human A/B results

### MME

The operator confirmed `SIM`. The endpoint was captured at 16 kHz mono to
match the current Golden input contract.

```yaml
HUMAN_CONFIRMATION: SIM
VALID_HUMAN_SPEECH_SAMPLE: YES
STREAM_OPENED: YES
SILENCE_RMS: 40.2382
SPEECH_RMS: 229.8089
SPEECH_PEAK: 9387
SPEECH_TO_SILENCE_RMS_RATIO: 5.7112
SPEECH_TO_SILENCE_DB: 15.13
FRAME_COUNT: 201
FRAME_DROPS: 0
INPUT_OVERFLOW: 0
HUMAN_SIGNAL_USABLE: YES
```

This is a valid raw MME signal result and differs from the earlier human
confirmed near-zero run. It establishes that the selected MME endpoint can
deliver a usable human signal in this session, but one attempt is not enough
to prove repeatability or justify a production change.

### DirectSound

The operator confirmed `SIM`, but the blocking diagnostic reader returned
impossible zero buffers. The result is therefore not an interpretable acoustic
comparison.

```yaml
HUMAN_CONFIRMATION: SIM
VALID_HUMAN_SPEECH_SAMPLE: YES
PIPELINE_DELIVERY_VALID: NO
MISMATCH_CAUSE: blocking RawInputStream.read returned immediately with zero buffers
SILENCE_RMS: 0
SPEECH_RMS: 0
SPEECH_PEAK: 0
SPEECH_TO_SILENCE_DB: UNAVAILABLE
FRAME_COUNT: 206144
INPUT_OVERFLOW: 0
HUMAN_SIGNAL_USABLE: NO
```

DirectSound is not classified as acoustically poor or good from this run. The
reader/lifecycle mismatch must be fixed or replaced with a callback-backed
diagnostic before another comparison is meaningful. No production switch was
made.

### WASAPI

The operator confirmed `SIM`. The native 48 kHz stream delivered a valid,
bounded raw window, but the confirmed speech window did not increase over the
baseline.

```yaml
HUMAN_CONFIRMATION: SIM
VALID_HUMAN_SPEECH_SAMPLE: YES
PIPELINE_DELIVERY_VALID: RAW_STREAM_ONLY
GOLDEN_16KHZ_PIPELINE_COMPATIBLE: NO
SILENCE_RMS: 740.6491
SPEECH_RMS: 386.1864
SPEECH_PEAK: 6562
SPEECH_TO_SILENCE_DB: -5.66
FRAME_COUNT: 201
FRAME_DROPS: 0
INPUT_OVERFLOW: 0
HUMAN_SIGNAL_USABLE: NO
REPEATABLE: NOT_TESTED
```

The result is valid human evidence but not a usable-signal result. The native
rate also cannot be passed directly to the current 16 kHz provider contract.

### WDM-KS

The stream prepared successfully with a callback probe, but the blocking
diagnostic capture failed before any human window:

```yaml
HUMAN_CONFIRMATION: NOT_RUN
VALID_HUMAN_SPEECH_SAMPLE: NO
PIPELINE_DELIVERY_VALID: NO
ERROR: PaErrorCode -9999, Blocking API not supported yet
SILENCE_RMS: NOT_CAPTURED
SPEECH_RMS: NOT_CAPTURED
HUMAN_SIGNAL_USABLE: NOT_DETERMINED
REPEATABLE: NOT_TESTED
```

No WDM-KS human conclusion is permitted from this attempt.

## Signal decision

```yaml
BEST_HUMAN_SIGNAL_PATH: MME_RAW_16KHZ_IN_THIS_SESSION
MME_CONSISTENTLY_UNUSABLE: NO
ALTERNATIVE_CONSISTENTLY_USABLE: NO
PRODUCTION_HOST_API_CHANGE_JUSTIFIED: NO
PROPOSED_HOST_API: NONE
PRODUCTION_ENDPOINT_REPLACEMENT_JUSTIFIED: NO
MIC_SIGNAL_ROOT_CAUSE_IDENTIFIED: NO
ROOT_CAUSE_CATEGORY: BACKEND_OR_CAPTURE_PATH_VARIABILITY_UNRESOLVED
ROOT_CAUSE_EVIDENCE: MME valid in this run; prior MME near-zero; DirectSound reader mismatch; WASAPI confirmed but below baseline; WDM blocking reader unsupported
REAL_MIC_SIGNAL_USABLE: BACKEND_DEPENDENT
```

The only defensible conclusion is that MME produced the best confirmed raw
signal in this session. Repeatability is not established, and no alternative
backend has two valid usable human samples. Production remains unchanged.

## Native exit-code investigation

The previous broad run printed `181 passed` and then exited abnormally:

```yaml
OBSERVED_EXIT_CODE: -1073740940
SIGNED_DECIMAL: -1073740940
UNSIGNED_DECIMAL: 3221226356
HEX: 0xC0000374
STATUS_NAME_IF_CONFIRMED: STATUS_HEAP_CORRUPTION
```

Bounded minimal raw `sounddevice.RawInputStream` open/read/stop/close probes
for MME, DirectSound, WASAPI, and WDM-KS each exited with code `0`.

The regression suite was isolated by process:

```yaml
PROVIDER_TESTS: 9 passed, exit 0
OUTPUT_TESTS: 9 passed, exit 0
COEXISTENCE_TESTS: 3 passed, exit 0
HARNESS_TESTS: 7 passed, exit 0
RUNTIME_WIRING_BEFORE_FIX: 25 passed, exit -1073740940
```

The failing class was narrowed to follow-up tests that executed the real
`VoiceService._handle()` path while mocking `_stop_barge_in_monitor`. The real
streaming path could start the barge-in monitor, while the mocked stop left its
native `sounddevice` thread alive until interpreter teardown. The smallest
diagnostic fix was test isolation: those tests now also mock
`_start_barge_in_monitor`, because they test follow-up state and not native
audio ownership.

After the fix:

```yaml
FOCUSED_HUMAN_HARNESS_AND_RUNTIME_WIRING: 34 passed
PYTEST_EXIT: 0
ASSERTIONS_COMPLETE_BEFORE_CRASH: YES
PYTEST_SUMMARY_PRINTED: YES
CRASH_TIMING: NO_CRASH_AFTER_FIX
MINIMAL_REPRO_CREATED: YES
MINIMAL_REPRO_RESULT: PASS_FOR_ALL_PROBED_HOST_APIS
MME_NATIVE_EXIT: 0
DIRECTSOUND_NATIVE_EXIT: 0
WASAPI_NATIVE_EXIT: 0
WDM_KS_NATIVE_EXIT: 0
GOLDEN_NATIVE_LIFECYCLE_BUG: NO_PRODUCTION_BUG_FOUND
EXTERNAL_NATIVE_BACKEND_ISSUE: NOT_CONFIRMED
TEST_ISOLATION_DEFECT: FIXED
```

No native failure was masked, and no package upgrade was performed.

## Architecture and privacy

```yaml
VOICE_SERVICE_REMAINS_OWNER: YES
AUDIO_INPUT_PROVIDER_REUSED: YES
SECOND_AUDIO_INPUT_SYSTEM_CREATED: NO
SECOND_VAD_CREATED: NO
TURN_MANAGER_CHANGED: NO
SELF_TRIGGER_POLICY_CHANGED: NO
CANCELLATION_CHANGED: NO
VAD_THRESHOLD_CHANGED: NO
RAW_AUDIO_PERSISTED: NO
WAV_CREATED: NO
TRANSCRIPT_PERSISTED: NO
REMOTE_AUDIO_SENT: NO
REMOTE_TEXT_SENT: NO
CLOUD_USED: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
```

## Regression gate

```yaml
FOCUSED_TESTS: 34 passed
BROADER_VOICE_TESTS: 183 passed
ASSERTION_RESULT: PASS
PROCESS_INTEGRITY_RESULT: PASS
PY_COMPILE: PASS
SECRET_SCAN: NOT_APPLICABLE_TO_DIAGNOSTIC_AUDIO
GIT_DIFF_CHECK: PASS
```

Next gate: repeatability validation for MME, only with a fresh explicit human
authorization and one visible interactive attempt. Do not switch production
host API based on this gate alone. Human barge-in remains `NO`.
