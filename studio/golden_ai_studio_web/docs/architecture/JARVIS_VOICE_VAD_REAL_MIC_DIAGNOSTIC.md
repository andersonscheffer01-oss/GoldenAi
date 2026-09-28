# Jarvis Real-Microphone VAD Diagnostic

Status: `PHASE_A_DIAGNOSTIC_COMPLETE`.

Baseline: `8918a49`.

## Scope and safety

This investigation measured the existing signal path before any tuning. It
did not change VAD thresholds, speech-start duration, sample rate, frame size,
normalization, endpoint settings, STT, TurnManager, SelfTriggerPolicy,
cancellation, Windows audio settings, or `device_registry.json`. Numeric
diagnostics were held in memory only; no microphone PCM, WAV, transcript, or
remote payload was persisted.

## Current VAD contract

| Field | Current value |
|---|---|
| Implementation | `SileroVADAdapter` |
| Model | `silero_vad_v6.onnx` |
| Model source | `faster_whisper/assets/silero_vad_v6.onnx` in the existing local venv |
| Expected and observed input rate | 16,000 Hz |
| Frame | 480 samples, 960 bytes, 30 ms |
| PCM | mono, signed little-endian int16 |
| Silero tensor | float32 `[1, 576]` |
| Silero input range | approximately `[-1.0, 1.0]` |
| Normalization | `int16.astype(float32) / 32768.0` |
| VAD window | 512 samples plus 64 samples stateful context |
| Speech threshold | `0.5` |
| Speech start | 3 consecutive windows at or above threshold |
| Endpoint | 700 ms below threshold |
| State | persistent across frames; reset on load/start/stop/barge-in/utterance reset |

## Signal path

```text
sounddevice.RawInputStream(device=1, samplerate=16000, mono, int16)
  -> AudioInputProvider._on_callback
  -> AudioInputProvider._accept_frame
  -> AudioFrameQueue
  -> RealtimeVoicePipeline._frame_loop
  -> RealtimeVoicePipeline._feed_vad_safely
  -> SileroVADAdapter.feed
  -> np.frombuffer(..., dtype=int16).astype(float32) / 32768.0
  -> Silero ONNX probability
  -> Silero _step (threshold and consecutive-window state)
  -> HybridEndpoint only after a Silero event
```

The provider delivered correctly aligned frames. The observed stream rate was
16,000 Hz even though the device's default capability is 44.1 kHz; the
requested stream opened at the logical VAD rate and reported that rate at
runtime. No resampler is present or required in this path.

## Silence baseline

Three seconds were measured with the human silent and no speaker playback:

```yaml
FRAMES_EXPECTED: 100
FRAMES_RECEIVED: 100
FRAME_DROPS: 0
MAX_FRAME_GAP_MS: 30.86
INPUT_OVERFLOW: 0
QUEUE_DROPS: 0
RAW_PCM16_RMS_MEAN: 0.516
RAW_PCM16_RMS_MAX: 1.078
RAW_PCM16_PEAK_MAX: 3
NORMALIZED_RMS_MEAN: 0.00001574
NORMALIZED_PEAK_MAX: 0.00009155
SILENCE_VAD_PROB_MIN: 0.00161
SILENCE_VAD_PROB_MAX: 0.03560
SILENCE_VAD_PROB_MEDIAN: 0.00233
VAD_SPEECH_STARTED: NO
```

## Human speech without playback

One speech-only attempt was run with the real microphone and no speaker
playback. The operator confirmed `SIM` after the harness stopped, so the human
speech evidence is valid. The harness did not infer that fact from VAD.

```yaml
HUMAN_CONFIRMATION: SIM
VALID_HUMAN_SPEECH_TEST: YES
ACTUAL_MIC_SAMPLE_RATE: 16000
FRAMES_EXPECTED: 200
FRAMES_RECEIVED: 200
FRAME_DROPS: 0
MAX_FRAME_GAP_MS: 30.17
INPUT_OVERFLOW: 0
QUEUE_DROPS: 0
RAW_PCM16_RMS_MEAN: 0.478
RAW_PCM16_RMS_MAX: 0.522
RAW_PCM16_PEAK_MAX: 1
NORMALIZED_RMS_MEAN: 0.00001460
NORMALIZED_PEAK_MAX: 0.00003052
NORMALIZED_MIN: -0.00003052
NORMALIZED_MAX: 0.00003052
VAD_PROB_MIN: 0.00156
VAD_PROB_MAX: 0.03321
VAD_PROB_MEAN: 0.00322
VAD_PROB_MEDIAN: 0.00305
FRAMES_ABOVE_0_10: 0
FRAMES_ABOVE_0_25: 0
FRAMES_ABOVE_0_50: 0
FRAMES_ABOVE_CURRENT_THRESHOLD: 0
VAD_PROBABILITY_RESPONDED: YES
VAD_SPEECH_STARTED: NO
ENDPOINT_SPEECH_STARTED: NO
```

The human-confirmed speech window produced a signal indistinguishable from
the silence baseline and no probability near the current threshold. This is
evidence of an abnormally low microphone signal at the provider boundary, not
evidence that the VAD threshold should be lowered.

## Synthetic versus real input

The passing adapter tests use 16 kHz, 480-sample PCM frames. Their speech
fixture is a 440 Hz tone with amplitude `8000` (approximately RMS `5657`,
normalized peak `0.244`). The real human window delivered the same rate, frame
size, signedness, and normalization contract, but only peak `1` and normalized
peak `0.0000305`. The meaningful difference is signal amplitude, not shape,
rate, frame alignment, or tensor normalization.

## Root-cause localization

```yaml
DEEPEST_CONFIRMED_WORKING_STAGE: REAL_MIC_CAPTURE
ROOT_CAUSE_CATEGORY: MIC_SIGNAL_TOO_LOW
ROOT_CAUSE_EVIDENCE: human-confirmed speech and silence have near-identical near-zero PCM and Silero probabilities
PCM_CONTRACT_VALID: YES
NORMALIZATION_VALID: YES
SAMPLE_RATE_VALID: YES
FRAME_SIZE_VALID: YES
FRAME_CONTINUITY_VALID: YES
MODEL_INVOCATION_VALID: YES
MODEL_STATE_HANDLING_VALID: YES_BY_CODE_AND_TESTS
VAD_EVENT_EMISSION_VALID: NOT_REACHED_WITH_VALID_SPEECH_SIGNAL
HYBRID_ENDPOINT_VALID: NOT_REACHED
```

The evidence does not distinguish Windows input gain from device routing or
another upstream capture-level issue. No operating-system setting was changed
automatically. Playback comparison is not repeated in this phase because the
speech-only signal path already fails before VAD sensitivity can be assessed.

## Tuning decision

```yaml
VAD_THRESHOLD_TUNING_JUSTIFIED: NO
VAD_START_TRIGGER_TUNING_JUSTIFIED: NO
IMPLEMENTATION_BUG_FOUND: NO
IMPLEMENTATION_BUG_FIXED: NO
PRODUCTION_THRESHOLD_CHANGED: NO
PRODUCTION_VAD_MODEL_CHANGED: NO
```

The next narrow investigation should validate the Windows microphone signal
level, selected endpoint, and device-side routing without changing settings
automatically. Only after real speech produces a normal PCM amplitude and
probability response should VAD calibration be considered.

## Regression and architecture

The diagnostic harness remains opt-in and reuses the existing
`VoiceService`, `AudioInputProvider`, `SileroVADAdapter`, `HybridEndpoint`,
local STT boundary, and Golden cancellation owners. No second VAD, Core,
VoiceService, TurnManager, cancellation system, dependency, or database
migration was introduced. Focused regression tests passed after adding the
numeric observers.

```yaml
RAW_MIC_AUDIO_PERSISTED: NO
TRANSCRIPT_PERSISTED: NO
REMOTE_AUDIO_SENT: NO
REMOTE_TEXT_SENT: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO
```

Next gate: `MIC_SIGNAL_PATH_AND_INPUT_LEVEL_DIAGNOSTIC`.
