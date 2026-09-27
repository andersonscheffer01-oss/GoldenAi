# Jarvis PT-BR STT Benchmark

Status: `PASS_WITH_RESTRICTIONS`

The approved local artifact was exercised without microphone access, network
STT, model downloads, or Core execution:

- Model: `Systran/faster-whisper-small`
- Revision: `536b0662742c02347bc0e980a01041f333bce120`
- Device and compute type: CPU / `int8`
- Language: `pt`
- Cold model load: `3.722577 s`
- Warm mechanical runs: `3`
- Transcription wall time: `1.352773 s` to `10.682282 s`
- RTF: `0.338193` to `9.476287`, median `5.341141`
- Base RSS: `42,962,944` bytes
- Post-load RSS: `527,437,824` bytes
- Peak transcription RSS: `547,631,104` bytes

The warm inputs were in-memory zero-valued PCM16 signals of 1, 2, and 4
seconds. They are tagged `synthetic_performance_non_speech` and are suitable
only for mechanical timing and memory checks. The observed RTF is not a
representative speech throughput result because the inputs contain no speech.

No eligible licensed PT-BR speech fixture was present. Accordingly:

- WER/CER: not measured;
- human-speech samples: `0`;
- PT-BR recognition quality: unmeasured;
- VAD plus STT end-to-end quality: not run;
- no provider, model, or production parameter was changed.

Unknown-provenance WAV files already present in the workspace were excluded.
See [JARVIS_STT_PTBR_CORPUS.md](JARVIS_STT_PTBR_CORPUS.md) for the admission
rules and the next corpus requirements. Raw benchmark output is recorded in
[JARVIS_STT_PTBR_BENCHMARK.json](JARVIS_STT_PTBR_BENCHMARK.json).

Recommendation: keep the current local STT configuration and acquire an
approved, licensed PT-BR speech corpus before making quality or performance
tuning decisions.
