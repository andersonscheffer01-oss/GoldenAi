# Jarvis Windows Audio Input Reliability

Baseline: `d126929`

This document records the reuse-first adaptation of the existing
`AudioInputProvider`. It is not a new voice architecture. `VoiceService` still
owns the voice turn, `AudioInputProvider` still owns microphone capture,
`SileroVADAdapter` and `HybridEndpoint` still own VAD/endpointing, and
`TurnManager` plus Golden cancellation still own turn and cancellation policy.

## Donor patterns adopted

| Source project | Source file | Source pattern | Golden target | Classification |
| --- | --- | --- | --- | --- |
| `ndunl075/Jarvis` | `jarvis/audio/devices.py` | Enumerate input-capable devices, match name/host API, query native rate, callback capture, normalize frames, bounded same-device fallback and clean unload | `jarvis_core/realtime_voice/audio_input.py` | `ADAPT` |
| `ndunl075/Jarvis` | `tests/audio/test_devices.py` | Deterministic tests for device matching, lifecycle, wrong frames, callback failure and fallback | `tests/test_voice_batch02a_provider.py` | `REIMPLEMENT_PATTERN` |
| `ONEPUNCHMAN411/Jarvis` | `jarvis/voice/audio_capture.py` | Bounded freshest-frame queue and callback-safe level delivery | `AudioInputProvider` and existing `AudioFrameQueue` | `ADAPT` |
| `ONEPUNCHMAN411/Jarvis` | `jarvis/voice/voice_manager.py` | Signal observations and queue freshness concepts | Provider diagnostics | `ADAPT` |
| `python-sounddevice` | `RawInputStream` / `query_devices` API | PortAudio callback stream plus device/host API metadata | Existing sounddevice boundary | `KEEP_OURS` plus `ADAPT` |

No donor source was copied verbatim. No donor orchestration, voice manager,
VAD, turn manager, or security boundary was imported.

## Capture lifecycle

`AudioInputProvider.start()` now:

1. increments a capture generation;
2. resolves a bounded input candidate;
3. reads its default/native capture rate and input capability;
4. derives a native block size equivalent to one Golden 30 ms frame;
5. starts a conversion worker only when native rate or channel count is not
   already canonical;
6. opens exactly one callback `RawInputStream`;
7. starts the stream.

`stop()` invalidates the generation before stopping/closing the native stream,
then stops the conversion worker. Repeated start/stop calls remain idempotent;
failed starts close any partially opened stream and do not leave a worker
behind. `restart()` is the existing explicit stop-then-start operation.

## Callback and queue policy

The PortAudio callback performs only:

- generation/running validation;
- byte conversion/copy;
- lightweight frame, zero-frame, timestamp and overflow counters;
- direct canonical delivery, or insertion into an internal raw queue.

It does not run VAD, STT, Core, network, file I/O, or blocking work. The
existing `AudioFrameQueue` remains the downstream bounded queue and drops the
oldest frame on overflow so stale backlog does not grow. Native-rate or
multi-channel input uses a separate bounded raw queue of eight callback
buffers; on overflow it also drops the oldest raw buffer and reports both
overflow and drop counters.

Every stream callback closes over the generation that created it. A callback
from a stopped or replaced stream cannot enqueue into the current generation,
including callbacks already scheduled onto the asyncio loop.

## Native-rate and channel strategy

The physical endpoint is opened at its reported `default_samplerate` when
available. The downstream contract is unchanged:

- `NATIVE_RATE`: device-reported default rate;
- `INTERNAL_RATE`: 16000 Hz;
- `INTERNAL_CHANNELS`: 1;
- `INTERNAL_FORMAT`: signed PCM16;
- `INTERNAL_FRAME`: 480 samples / 960 bytes / 30 ms.

For multi-channel endpoints, the first two input channels are mixed by a
deterministic arithmetic mean before conversion. This is not an arbitrary
single-channel pick. The provider caps the native capture channel request at
two because the current Golden contract is mono and the adaptation does not
introduce an unbounded channel policy.

Resampling uses the already-declared `scipy` stack and
`scipy.signal.resample_poly` when available. A `numpy` interpolation fallback
is retained for environments where the optional SciPy import is unavailable;
no dependency was added. Converted samples are accumulated until complete
480-sample frames are available, then delivered through the existing queue.

## Device resolution and fallback

The provider no longer treats a persistent numeric index as the logical
identity of a microphone when device metadata is available.

Resolution order is deliberately conservative:

1. configured device name: current input-capable name matches only;
2. numeric/default runtime selector: current candidate is accepted on first
   resolution;
3. after a prior resolution: same case-insensitive device name and same host
   API are preferred, even if the runtime numeric index changed;
4. input capability and native rate are recorded for the selected candidate.

If the intended device is absent, or its logical identity changes, start
fails as unavailable. The provider does not silently switch to an unrelated
microphone. Matching host-API variants of the intended device are the only
bounded candidate set. No automatic preference for DirectSound, WASAPI, or
WDM-KS was introduced.

## Health and recovery

Diagnostics now expose metadata only:

- `frames_received` and canonical frames delivered;
- `last_frame_at` and `capture_generation`;
- native input overflow and raw-queue overflow/drop counters;
- callback/conversion/device errors;
- exact-zero consecutive frame observation;
- stream state and logical device identity.

`signal_health` is observational (`UNKNOWN`, `OBSERVED`, or `SUSPECT`) and is
not a permanent RMS threshold or an automatic gain control. A quiet human
interval does not restart the stream. Automatic gain, AGC, Windows level
changes, and signal-based infinite retry are not implemented.

The bounded recovery primitive is the existing provider restart path:

`stop -> invalidate generation -> close -> re-enumerate -> resolve intended
device -> reopen`.

There is no new recovery authority or infinite retry loop in this change.

## Privacy and preserved ownership

- Raw audio is never written to disk.
- No WAV diagnostic file is created.
- No transcript is persisted.
- No cloud or remote audio/text path is added.
- No `VoiceService`, VAD, endpoint, TurnManager, SecurityManager, scheduler,
  database, or device registry behavior was changed.
- No AEC, VAD threshold, host API policy, or production device setting was
  changed.

## Test evidence

New deterministic provider tests cover:

- canonical callback delivery;
- native 48 kHz stereo to 16 kHz mono conversion;
- bounded queue/drop behavior;
- input overflow observation;
- device missing without unrelated fallback;
- numeric index re-resolution after enumeration reorder;
- stale callback rejection after stop/restart;
- idempotent lifecycle and failed-start cleanup;
- worker teardown.

Focused provider result: `14 passed`.

Focused related voice regression with the project virtual environment:
`133 passed`.

The initial global-Python invocation produced environment-only collection
failures because `sounddevice` was not installed in that interpreter. It was
not used for the final result; no package was installed.

The prior `0xC0000374` native-crash test-isolation fix remains intact. No real
microphone capture or human speech test was run in this implementation gate.

## Known restrictions

This change provides deterministic lifecycle, resolution, conversion, and
recovery behavior, but it does not prove repeatability on the current physical
USB microphone. The earlier MME result remains `MME_CAN_CAPTURE: YES` with
`CAPTURE_REPEATABILITY: UNRESOLVED`. DirectSound, WASAPI, and WDM-KS policy is
unchanged.

The next permitted step is a controlled real-microphone validation with a
human present. Real-speech VAD and barge-in remain later gates.
