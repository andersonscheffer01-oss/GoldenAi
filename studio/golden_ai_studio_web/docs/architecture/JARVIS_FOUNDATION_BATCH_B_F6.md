# Foundation Batch B: F6 Model Router

## Status

F6 is complete with bounded scope. The canonical chat fallback path now uses
`jarvis_core.orchestrator.ModelRouter` even when no provider has been
registered at startup. A lazy local Ollama adapter is registered without a
health probe or generation; the provider client is imported only when the
router actually selects it.

## Consolidated path

`JarvisBrain` chat and research synthesis both execute through the canonical
router. The router still owns provider selection, bounded timeout, fallback,
and `SECRET` filtering. The local adapter preserves the existing
`qwen2.5-coder:14b` policy supplied by `ModelRouter`.

## Deferred paths

The following were audited but intentionally not migrated in F6:

- `server_agent.py` legacy `/api/chat` branches and specialized model labels;
- `jarvis_core/streaming/provider_stream.py` and streaming orchestrators;
- root `core.models.ModelRouter` and `app/*` compatibility paths.

These paths have distinct streaming or legacy compatibility contracts. They
remain operationally classified as deferred adapters/bypasses and are not
additional canonical chat authorities. A future streaming convergence gate
must preserve cancellation, fallback, tool-call handling, and security
boundaries before changing them.

## Validation

- Focused F6 tests: `24 passed, 22 subtests passed`.
- No provider network calls, model downloads, hardware access, or database
  migrations were performed.
- The known Windows temporary SQLite cleanup limitation remains outside F6;
  it is not a provider-router failure.
