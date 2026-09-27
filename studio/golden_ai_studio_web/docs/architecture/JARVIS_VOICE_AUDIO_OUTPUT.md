# Jarvis Voice Audio Output Foundation

## Scope

The Windows output foundation adds one real playback adapter behind the
existing `AudioOutputProvider` contract. `VoiceService` remains the owner of
the `VoiceAudioPipeline`; the adapter does not create a Core, a second voice
service, a second cancellation system, or an alternative playback path.

The implementation is `SoundDeviceAudioOutputProvider` in
`jarvis_core/audio_output.py`. `sounddevice` is imported lazily and the
existing `sounddevice==0.5.6` dependency is reused. No audio is persisted and
no network or remote TTS provider is involved.

## Stream and PCM contract

- Playback uses one `sounddevice.RawOutputStream` per active turn boundary.
- PCM is signed little-endian 16-bit (`s16le`), mono or stereo, with frame
  alignment checked before enqueue.
- Rates from 8 kHz through 192 kHz are accepted by the provider; the selected
  Windows device remains the final authority for whether a rate opens.
- A format or session/turn/generation identity change requires the existing
  pipeline boundary (`cancel` then `warm`). Formats are never mixed in one
  active stream.
- The queue is bounded at `8` chunks by default and uses `drop_oldest`, matching
  the existing in-memory output policy. `reject` is available for callers that
  need lossless admission semantics.

The PortAudio callback only copies queued bytes into `outdata` and fills
silence when the queue is empty. It does not call Core, tools, SecurityManager,
TTS, STT, the filesystem, or the network.

## Cancellation and recovery

Cancellation first marks the provider cancelled, running state false, identity
empty, and queue empty under the provider lock. Only then does it abort, stop,
and close the detached stream. A callback racing with cancellation therefore
can only write silence, and late chunks are rejected. Repeated cancellation,
stop, release, and shutdown are safe.

An open failure is reported to the caller and receives a bounded retry budget
(one retry by default). A callback device-loss status can be recovered against
the same configured device while pending PCM remains. The provider never
silently selects a different device. Enumeration is read-only and does not
read or modify `device_registry.json`.

## Hardware validation boundary

The automated suite uses a fake `RawOutputStream` and opens no microphone or
speaker. A controlled real-speaker smoke, when a valid output device is
available, must use a short, low-amplitude deterministic PCM tone only. It is
not TTS and must not create WAV/temp files. A separate cancellation smoke must
verify that an in-flight buffer is aborted and no zombie stream remains.

This foundation does not claim acoustic barge-in, microphone/speaker
coexistence, echo cancellation, or real TTS quality. Those remain later gates.

## Verification

`tests/test_audio_output.py` covers device enumeration, lifecycle, ordering,
PCM validation, bounded overflow, cancellation before/during playback, late
audio rejection, format boundaries, bounded open recovery, device-loss
recovery, and VoiceService ownership. Existing turn-taking and voice-foundation
tests remain the source of truth for logical barge-in compatibility.
