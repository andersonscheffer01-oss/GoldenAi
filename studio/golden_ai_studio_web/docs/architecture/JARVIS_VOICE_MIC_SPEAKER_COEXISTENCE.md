# Jarvis Voice Mic + Speaker Coexistence Gate

Status: `PASS_WITH_RESTRICTIONS` for the observed Windows configuration.

## Scope and ownership

This was a controlled measurement gate, not an AEC implementation. The real
`AudioInputProvider` and `SoundDeviceAudioOutputProvider` were reused while
`VoiceService`, `TurnManager`, VAD, STT contracts, `SelfTriggerPolicy`, and
existing cancellation remained authoritative. No second owner, Core,
VoiceService, TurnManager, or cancellation system was created.

No TTS provider, cloud audio, DSP/AEC package, model download, database
migration, or `device_registry.json` change was made. Audio was retained only
in bounded process memory for the measurement interval and cleared afterward.

## Observed devices

- Default input: device `1`, `Microfone (3- USB Audio Device)`
- Default output: device `3`, `Alto-falantes (3- USB Audio Device)`
- Both streams used PortAudio host API `MME`.
- Read-only enumeration found 16 output-capable devices.

The names identify the configured Windows endpoints, but do not prove the
physical acoustic layout. The result is therefore `HARDWARE_CONFIGURATION:
PARTIAL`; it should not be generalized to headsets, external speakers, or
another room.

## Method

The input stream used the existing 16 kHz mono PCM16 `AudioInputProvider`. The
output stream used the existing provider with a short 44.1 kHz mono PCM16,
low-amplitude 440 Hz tone. A baseline was captured for 550 ms, playback was
started while the microphone stayed open, playback was cancelled after about
140 ms, and a second short output start/cancel cycle ran before the microphone
closed. No raw PCM was logged or persisted.

Levels are true PCM16 RMS:
`sqrt(mean(sample^2))`; the reported change is `20*log10(playback_rms /
baseline_rms)`. Peak is the maximum absolute signed-16-bit sample. The helper
is `jarvis_core/realtime_voice/coexistence_diagnostics.py` and returns metrics,
not audio.

## Results

| Measurement | Result |
|---|---:|
| Baseline input | 17 frames, RMS 5.106, peak 35 |
| Input during playback | 5 frames, RMS 1.483, peak 7 |
| Input after playback abort | 26 frames, RMS 1.209, peak 7 |
| Input during output restart | 4 frames |
| Playback-to-microphone change | -10.74 dB |
| Input drops/errors | 0 / 0 |
| VAD baseline / playback / after | 0 / 0 / 0 events |
| Output open/restart | PASS / PASS |

Both PortAudio streams opened simultaneously. Input continued during playback,
after output cancellation, and during output restart. The output queue was
empty after cancellation; no input or output stream remained active.

The measured tone did not produce a VAD event, endpoint speech start, or
utterance. `SelfTriggerPolicy` classified the unknown measured level as
`UNCERTAIN`, which preserves the possibility of genuine user interruption;
the experiment did not add a blanket “ignore microphone while speaking” rule.

## STT and real-user interruption

No provenance-approved speech fixture was available. Existing `.wav` files in
the workspace are temporary test artifacts and were not used. Consequently,
speaker-to-STT self-transcription and real human barge-in were not run. A tone
cannot support either conclusion.

## Classification and decision

Observed evidence supports `CLASS_0`: no meaningful speaker leakage was
measured in this configuration, no VAD activation occurred, and no endpoint or
STT utterance was formed. This is not proof that other volumes, devices, rooms,
or human speech are safe.

`AEC_RESEARCH_REQUIRED: NO` based on this gate alone. The smallest next
strategy is `NO_ECHO_INTERVENTION_YET`. A future gate must use an approved
speech fixture or controlled human speech before declaring acoustic barge-in
ready.

`REAL_ACOUSTIC_BARGE_IN_READY: NO`.
