# Jarvis TTS Provider Evaluation

Status: foundation ready, real local PT-BR provider deferred.

## Scope

This pass adds the provider-neutral contract and deterministic tests. It does
not install a TTS runtime, download a model, open an audio device, or run real
TTS. `VoiceService` remains the single owner of the optional TTS/output
pipeline and the existing Edge/SAPI path remains the default.

## Bounded provider review

The prior license gate already evaluated the serious local PT-BR Piper voice
artifacts. This pass did not reopen Faber, Cadu, Jeff, or Edresson because no
new official model-specific licensing evidence was identified. The current
Piper runtime is maintained in [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)
and published as [piper-tts on PyPI](https://pypi.org/project/piper-tts/), but
runtime licensing does not by itself establish a clear license for each voice
checkpoint.

The official [Piper voice repository](https://huggingface.co/rhasspy/piper-voices)
identifies repository metadata and dataset information, but does not provide a
separate, unambiguous commercial-use license for the selected PT-BR voice
artifact. The maintainer's [license discussion](https://github.com/rhasspy/piper/discussions/271)
also leaves checkpoint and voice-training provenance as a per-artifact
responsibility.

Decision:

```text
REAL_TTS_PROVIDER: DEFERRED
PIPER_RUNTIME_INSTALLED: NO
VOICE_MODEL_DOWNLOADED: NO
REAL_TTS_EXECUTED: NO
```

## Foundation now available

`jarvis_core/voice_tts.py` provides:

- provider-neutral `TextToSpeechProvider` lifecycle: `warm`, `synthesize`,
  `stream`, `cancel`, and `release`;
- immutable `PcmAudioChunk` events with PCM format, sequence, final marker,
  session, turn, generation, and metadata;
- deterministic `FakeTextToSpeechProvider` with no hardware, model, or network;
- bounded `AudioOutputProvider` delivery and `FakeAudioOutputProvider` with an
  explicit overflow policy;
- `VoiceAudioPipeline`, the single cancellation and stale-output gate between
  TTS and output.

No provider may be promoted to production until runtime, artifact, voice,
dataset, and redistribution terms are pinned and approved together.
