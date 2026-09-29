# Jarvis Market Improvement Backlog

This backlog is derived from the 2026-09-29 read-only audit. It does not authorize implementation, MT5, voice, database migration or trading.

## P0 - security / wrong authority

No reachable Market surface order action or direct broker mutation was found. Keep `dashboard.html` out of the Market Window because it contains legacy MT5 mutating controls.

## P1 - functional correctness

### P1.1 Canonicalize deep analysis

- Issue: `/api/market/analyze` calls fixed `ollama_chat(model="qwen2.5-coder:14b")`.
- Evidence: `server_agent._api_market_analyze`.
- Impact: provider/model drift and bypass of Jarvis policy, memory and canonical audit.
- Proposed fix: retain the Market context builder, submit a typed request through JarvisService/Brain/ModelRouter, and return provider/model metadata.
- Systems: `server_agent.py`, `jarvis_core/brain.py`, `jarvis_core/orchestrator/`, `ai_radar.js`.
- Required test: provider selection, offline/privacy classification, failure fallback and canonical audit receipt.

### P1.2 Separate history read from evaluation write

- Issue: `/api/market/analysis-history` can evaluate pending rows, read MT5 and replace `market_ai_audit.jsonl`.
- Impact: endpoint named as read can mutate runtime evidence and create races with append.
- Proposed fix: an explicit evaluation job/projection boundary; history read must be side-effect-free.
- Required test: GET/read contract leaves file hash unchanged.

## P2 - synchronization

### P2.1 Add canonical Market Chat session metadata

- Issue: Market Chat POST contains text only; no `conversation_id`, `surface`, or explicit session resume.
- Impact: Main and Market DOM histories cannot continue one another.
- Proposed fix: `SEPARATE_THREADS_SAME_BRAIN` by default, with opt-in canonical conversation id and `surface=market` metadata.
- Required test: cross-surface continuation, isolation default, reconnect/resume and idempotency.

### P2.2 Add structured MarketContext to canonical chat

- Issue: the Market chat cannot reliably answer selected asset/timeframe/chart state questions.
- Proposed fix: send bounded symbol, timeframe, snapshot timestamp, freshness, provenance, macro/news summary and data-available flags; never invent unavailable values.
- Required test: context present, unavailable and stale cases.

### P2.3 Protect direct Market HTTP chat

- Issue: `desktop_center.js` posts directly to port 8765, while the Main Chat uses authenticated Gateway WebSocket.
- Impact: inconsistent perimeter and audit behavior.
- Proposed fix: use Gateway for chat or add the same canonical auth/session boundary before accepting direct REST.
- Required test: unauthenticated request denied; authenticated request retains same service identity.

## P3 - data quality

### P3.1 Unified snapshot/provenance contract

Add source, provider, retrieval timestamp, timeframe, transformation, freshness state and correlation id to chart, overview, scanner and AI context responses.

### P3.2 Calendar timezone contract

Store source timezone/offset and render explicit timezone. Do not rely only on browser `toLocaleString`.

### P3.3 News relevance and deduplication

Add stable item ids, canonical URL normalization, parse failure state and asset relevance evidence.

## P4 - UX / observability

### P4.1 Show canonical routing identity

Expose sanitized provider/model/profile/routing state for Main Chat, Market Chat and deep analysis without secrets.

### P4.2 Expose data states per panel

Render `LIVE`, `FRESH`, `CACHED`, `STALE`, `UNKNOWN` and `UNAVAILABLE` at component level, not only in the aggregate Sources board.

### P4.3 Clarify score semantics

Keep labels such as score, readiness, confluence and heuristic risk; never call them confidence/probability without calibration evidence.

## P5 - performance / polish

Add abortable requests and response generation checks, then measure duplicate requests and hidden-tab behavior before optimizing. Preserve the existing visual surface during this work.

## Gate recommendation

The chat uses the canonical Brain/ModelRouter, so the next gate should be `CHAT SESSION + MARKET CONTEXT SYNCHRONIZATION GATE`, preceded or combined with a controlled `MARKET AI PIPELINE CANONICALIZATION GATE` for deep analysis. B3 is not checkpoint-ready from this audit and B4 must not start.
