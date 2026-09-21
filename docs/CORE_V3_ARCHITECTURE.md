# Golden AI Core V3 Architecture

Core V3 is a safe foundation layer for future agents, quantitative research,
market analysis, media study, auditing, and controlled edits.

## Current Integration

The existing Studio continues to talk to `app/golden_ai.py` through the ConPTY
bridge in `studio/golden_ai_pty_bridge.py`. Core V3 is not imported by the
current engine yet. This avoids regression while making future imports possible.

## Structure

- `core/config`: central settings and path policy.
- `core/permissions`: read/write/command decisions.
- `core/audit`: structured JSONL audit events.
- `core/experiments`: SQLite experiment repository.
- `core/memory`: scientific knowledge models.
- `core/jobs`: ThreadPoolExecutor job manager.
- `core/tools`: tool registry, checkpoint service, SHA-256 hashing.
- `core/safety`: evidence levels and untrusted media policy.
- `agents`: safe skeletons for future specialized agents.
- `quant`: data, strategy, metric, validation, and backtest contracts.
- `market`: market snapshot and regime contracts.
- `media_study`: multimodal study contracts and disabled service methods.

## Permissions And Safety

Core V3 defaults to read-only mode. Writes require explicit authorization and
are blocked in protected directories. Command execution is disabled by default.
Media, PDFs, transcripts, videos, audio, and images are classified as
untrusted data and cannot change system rules or trigger command execution.

## Experiments

Experiments are stored in `data/golden_ai.db` using SQLite. The schema includes
`experiments` and `experiment_artifacts`.

## Memory

Scientific memory is separate from chat history. `KnowledgeItem` preserves
whether an item is a source claim, observation, inference, hypothesis, test
result, or verified result.

## Jobs

Long-running work should use `JobManager` so future UI flows can stay
responsive. Celery/Redis are intentionally not introduced.

## Next Steps

1. Gradually wrap existing `golden_ai.py` tools in `ToolRegistry`.
2. Add read-only audit calls around key engine actions.
3. Add a diff approval workflow before enabling writes.
4. Add repositories for persistent scientific memory.
5. Add real media/backtest implementations only behind permissions.
