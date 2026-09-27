# Jarvis PT-BR STT Benchmark Corpus

Status: `QUALITY_CORPUS_INSUFFICIENT`

This benchmark intentionally separates human-speech quality from mechanical
provider performance. The repository currently contains WAV artifacts with no
documented license or provenance, including prior microphone-capture artifacts;
those files are excluded and were not opened by the benchmark.

The checked-in benchmark runner uses three in-memory, zero-valued PCM16 signals
of 1, 2, and 4 seconds. They are tagged
`synthetic_performance_non_speech`. They measure model load, process RSS,
transcription wall time, and RTF only. They are not speech and cannot support a
PT-BR WER or recognition-quality conclusion.

An eligible quality corpus must provide, for every item:

- a stable fixture identifier and category;
- a licensed or deliberately created speech file;
- explicit provenance and license/notice;
- an immutable Portuguese reference transcript;
- category membership for everyday PT-BR, Jarvis commands, mixed PT/EN
  technical terms, numbers/dates, identifiers/paths, short, and long speech.

The runner accepts a JSON manifest with `LICENSED_TEST_FIXTURE` entries and
computes standard word-level WER as `(S + D + I) / N`. It preserves raw and
normalized hypotheses in the JSON result. No fixture is included in the
current manifest because no eligible human-speech source was found.
