# Jarvis Market AI Pipeline Audit

## AI feature map

| Feature | Endpoint | LLM authority | Context | Persistence/security |
|---|---|---|---|---|
| Central PC text chat | `/api/jarvis/chat` | Canonical Brain -> ModelRouter | User text only | Jarvis tool path; direct REST auth gap |
| Main Chat | Gateway command | Canonical JarvisService -> Brain -> ModelRouter | User command, runtime context and memory boundary | Gateway auth, SecurityManager, AuditLog |
| Deep analysis | `/api/market/ai-context` + `/api/market/analyze` | Direct `ollama_chat` fixed model | M5/M15/H1/H4/D1, levels, fundamentals, events, prior analysis excerpts | JSONL append; bypasses ModelRouter |
| Contextual follow-up | `/api/market/analyze` | Same direct Ollama path | Prior Market context serialized into prompt | JSONL audit row with `pergunta_contextual` |
| Opportunity ranking | `/api/market/opportunity-ranking` | None | Scanner radar fields | Deterministic formula |
| AI performance | `/api/market/ai-performance` | None | JSONL evaluation fields | Can trigger history evaluation |

## Deep analysis call graph

```text
Market AI drawer
  -> getContext() + GoldenChart state
  -> /api/market/ai-context (multi-timeframe data)
  -> /api/market/analysis-history (previous rows)
  -> prompt assembled in ai_radar.js
  -> /api/market/analyze
  -> server_agent._api_market_analyze
  -> ollama_chat(model="qwen2.5-coder:14b")
  -> append data/market_ai_audit.jsonl
  -> HTML <pre> result
```

This is an actual LLM call, but not a canonical Jarvis call. The system prompt is a Golden Radar-specific prompt and does not use `JarvisService.build_messages`, `CanonicalMemoryBoundary`, `ModelRouter` or `AuditLog.add` as its primary receipt path.

## Classification

`ACTUAL_LLM`: deep analysis and contextual follow-up.

`ALGORITHM`: chart indicators, macro factor score, currency strength, scanner calculations, ranking formula and replay evaluation.

`HEURISTIC`: readiness, confluence, risk label and opportunity score. These are not probability estimates.

`HYBRID`: Market Chat, Forex analysis, deep analysis context assembly, analysis performance and history replay.

## Context quality

The deep-analysis context includes selected symbol/timeframe, server-side multi-timeframe candles and derived trend/structure/RSI/ATR/levels, plus FRED/BCB/Trading Economics fields where available and prior JSONL analysis excerpts. It does not include a canonical request provenance id, a single source snapshot id, or a canonical conversation id. The regular Market Chat receives none of these fields.

## Security and provenance findings

- `server_agent.py` exposes `/api/market/analyze` through the unauthenticated HTTP handler used by port 8765.
- The endpoint accepts a client-provided prompt and snapshot and writes the response to a runtime JSONL file.
- No secrets were found in the prompt construction or report fields, but the endpoint has no explicit DataClassification/ModelRouter policy in the inspected path.
- Analysis rows contain timestamp, symbol, timeframe, mode, response, snapshot and evaluation status. They lack provider/model, source hashes, source timestamps per field, request id and canonical audit receipt.
- `/api/market/analysis-history` can perform evaluation work and replace the JSONL file. A future read-only contract should split projection/evaluation from history retrieval.

## Recommended decision

`ADAPT`, then `MERGE` into the canonical Jarvis AI request contract. Preserve the useful multi-timeframe context builder and audit fields, but route generation through JarvisService/Brain/ModelRouter and attach canonical provenance. Do not create a Market Brain or a second ModelRouter.

This gate made no implementation change and did not invoke the model.
