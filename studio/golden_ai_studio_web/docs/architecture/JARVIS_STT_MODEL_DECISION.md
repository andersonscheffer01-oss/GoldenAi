# Jarvis Local STT Model Artifact Decision

Status: `APPROVED_WITH_RESTRICTIONS`
Research date: `2026-09-27`
Baseline STT decision: `b2eff9a`

This record closes the model-artifact gate left open by
`JARVIS_STT_DECISION.md`. It does not implement STT, load or download a model,
open an audio device, or change runtime behavior.

## Decision

```yaml
SELECTED_STT_PROVIDER: faster-whisper
SELECTED_STT_MODEL: Systran/faster-whisper-small
MODEL_PROVIDER: Systran
MODEL_REPOSITORY: https://huggingface.co/Systran/faster-whisper-small
MODEL_ID: Systran/faster-whisper-small
MODEL_REVISION: 536b0662742c02347bc0e980a01041f333bce120
MODEL_FORMAT: CTranslate2
MODEL_LANGUAGE_TYPE: multilingual
PORTUGUESE_SUPPORTED: YES
SELECTED_DEVICE: cpu
SELECTED_COMPUTE_TYPE: int8
MODEL_DOWNLOAD_REQUIRED: NO
ARTIFACT_ACTION: REUSE_EXISTING_LOCAL_ARTIFACT
MODEL_ARTIFACT_APPROVAL: APPROVED
```

The selected artifact is the exact model already implied by the active Golden
configuration. `jarvis_core/voice.py` defaults `JARVIS_WHISPER_MODEL` to
`small`, and faster-whisper 1.2.1 maps that alias to
`Systran/faster-whisper-small`. No relevant environment override was set during
this audit. Golden also defaults to CPU `int8` inference and language `pt`.

This is an utterance-based selection. It does not turn the existing integration
into true streaming STT. `gpt-live-transcribe` remains a future optional
reference provider and is outside this artifact decision.

## Local artifact identity

The approved snapshot was already present in the Hugging Face cache:

```text
C:\Users\Anderson\.cache\huggingface\hub\
  models--Systran--faster-whisper-small\snapshots\
  536b0662742c02347bc0e980a01041f333bce120
```

The cache `refs/main` value matches the snapshot revision. The snapshot was
created on `2026-09-13T04:42:14.4161628Z` and last updated on
`2026-09-13T04:43:09.0118521Z`. It contains four files totaling 486,212,372
bytes:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `config.json` | 2,370 | `b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828` |
| `model.bin` | 483,546,902 | `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671` |
| `tokenizer.json` | 2,203,239 | `fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab` |
| `vocabulary.txt` | 459,861 | `34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913` |

This is a per-file manifest, not a fabricated single model hash. Artifact
identity confidence is high because the canonical repository mapping, cached
repository name, `refs/main`, snapshot revision, required files, sizes, and
hashes agree.

## Provenance and licenses

The official faster-whisper model card identifies this artifact as a
CTranslate2 conversion of `openai/whisper-small`. The conversion records FP16
stored weights; faster-whisper can select another supported compute type at
inference, which is why Golden's CPU `int8` setting is compatible with this
artifact.

The licensing record must retain all layers rather than treating client code
and model weights as the same artifact:

- faster-whisper code: MIT, per the official repository license.
- converted `Systran/faster-whisper-small` artifact: MIT, per its model card.
- upstream `openai/whisper-small`: Apache-2.0, per its model card.
- upstream Whisper code: MIT, per the official OpenAI repository license.

These records are sufficient for this internal technical selection gate. They
are not a general legal conclusion; redistribution or product packaging still
requires preservation and review of applicable notices.

Official sources:

- https://github.com/SYSTRAN/faster-whisper
- https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py
- https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE
- https://huggingface.co/Systran/faster-whisper-small
- https://huggingface.co/openai/whisper-small
- https://github.com/openai/whisper/blob/main/model-card.md
- https://github.com/openai/whisper/blob/main/LICENSE

## Compatibility

```yaml
CPU: AMD Ryzen 5 5600X, 6 cores / 12 threads
RAM: 31.92 GB
GPU: AMD Radeon RX 9060 XT
CUDA: NOT_AVAILABLE
PYTHON: 3.13.15
FASTER_WHISPER: 1.2.1
CTRANSLATE2: 4.8.1
CPU_COMPATIBILITY: PASS
GPU_REQUIRED: NO
CUDA_REQUIRED: NO
CURRENT_CPU_THREADS: 0 (library default; OMP_NUM_THREADS unset)
CURRENT_WORKERS: 1 (library default)
RUNTIME_RAM_REQUIREMENT: UNMEASURED
REALTIME_FACTOR: UNMEASURED
```

The installed tokenizer exposes `pt` among 100 accepted language codes, and
the model is multilingual. This establishes Portuguese compatibility, not
quality. A later controlled benchmark must cover Brazilian Portuguese mixed
with English technical vocabulary, including Python, JavaScript, React,
Docker, Git, API names, and file paths.

## Acquisition and storage policy

No download is required for the next implementation batch because the exact
approved snapshot exists locally. If reacquisition becomes necessary, it must
use the official repository, the exact approved revision, and explicit human
authorization. The current 486,212,372-byte snapshot is the verified disk size;
network transfer size was not measured and must not be inferred from it.

Passing `small` to the current `WhisperModel` can trigger an implicit Hugging
Face download when the cache is absent. The future adapter must therefore:

1. use an explicit, canonical local model path;
2. require `local_files_only=True` or equivalent fail-closed behavior;
3. pin and verify the approved revision/manifest;
4. never silently substitute another model or revision;
5. report model absence as a bounded provider-unavailable condition.

The planned canonical store is a project-managed model area outside source
code and runtime databases, for example:

```text
C:\GoldenAI\models\stt\Systran\faster-whisper-small\
  536b0662742c02347bc0e980a01041f333bce120\
```

Nothing is copied or moved in this gate. A future acquisition step should write
a manifest containing model ID, source, revision, licenses/notices, per-file
hashes, acquisition date, and tool version. The store must not use the task
database, `device_registry.json`, or an application source directory.

After acquisition, inference is local and requires no network. Raw audio remains
ephemeral and must not be persisted or leave the device. Final transcripts
remain untrusted user input and continue through the existing VoiceService,
JarvisService, Core, SecurityManager, and approval model.

## Gates and restrictions

```yaml
LICENSE_GATE: PASS_WITH_RESTRICTIONS
PROVENANCE_GATE: PASS
PT_BR_GATE: PASS_WITH_RESTRICTIONS
CPU_GATE: PASS
FORMAT_GATE: PASS
PRIVACY_GATE: PASS
STT_OFFLINE_AFTER_MODEL_ACQUISITION: YES
NETWORK_REQUIRED_DURING_INFERENCE: NO
IMPLICIT_MODEL_DOWNLOAD_POSSIBLE: YES
IMPLICIT_DOWNLOAD_ALLOWED_FOR_IMPLEMENTATION: NO
HUMAN_APPROVAL_REQUIRED_FOR_MODEL_DOWNLOAD: YES
RAW_AUDIO_PERSISTED: NO
AUDIO_LEAVES_DEVICE: NO
TRANSCRIPT_TREATED_AS_UNTRUSTED_INPUT: YES
SECOND_JARVIS_CORE_CREATED: NO
SECOND_LLM_LOOP_CREATED: NO
SECOND_SECURITY_MODEL_CREATED: NO
READY_FOR_AUTONOMOUS_STT_BATCH: YES
```

`PASS_WITH_RESTRICTIONS` reflects unmeasured pt-BR quality, RAM, and real-time
factor, plus the need to replace the current symbolic model name with a pinned
local artifact path in the future adapter. These are implementation and
validation constraints, not unresolved artifact identity.

## Next authorized batch outline

- Phase 1: STT contracts, `TranscriptEvent`, and deterministic fake provider.
- Phase 2: faster-whisper adapter using the approved local artifact, with
  cancellation, stale-session, late-result, and duplicate-final guards.
- Phase 3: hardware-free Audio + VAD + STT + VoiceSession end-to-end tests.

Future tests should cover provider lifecycle, unavailable/load-failure paths,
successful transcription, a deliberately reviewed pt-BR fixture, cancellation,
late and stale results, duplicate finals, restart, bounded utterances, no raw
audio persistence, and Core failure isolation. No phase is executed by this
decision record.
