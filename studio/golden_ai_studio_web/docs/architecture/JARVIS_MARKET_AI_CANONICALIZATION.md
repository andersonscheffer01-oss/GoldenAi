# Jarvis Market AI Canonicalization

## Scope

The approved `market.html` surface remains a Jarvis surface. Market Chat and
Market Deep Analysis use the existing `JarvisService`, `JarvisBrain` and
`ModelRouter` authority. No Market-specific brain, router, memory store,
security manager or provider selector was introduced.

## Routing

`desktop_center.js` sends Market Chat with `surface=market`, a stable browser
`conversation_id`, and a small selected-chart context. The canonical
`/api/jarvis/chat` branch obtains a fresh `MarketContext` from
`JarvisService.market_context_snapshot()` and calls
`JarvisService.generate_response()` with tools disabled.

Deep Analysis follows the same no-tool response boundary through
`/api/market/analyze`. Its mode changes the user instruction only; provider
and model selection remain owned by the canonical orchestrator/router. The
former direct Ollama call in this endpoint was removed. Existing legacy
`/api/chat` compatibility code is outside the Market Deep Analysis path and is
not used by the Market surface.

## Observability and safety

Responses expose provider/model and routing metadata returned by the actual
router. The service records surface, conversation, request/response id,
context timestamp, provider, model and success state in the existing AuditLog.
Market contextual responses cannot propose tools, orders or other mutations.
The HTTP handler remains the existing REST perimeter; it does not create a
second authority. Its lack of a shared authentication perimeter remains a
documented deployment limitation for a later security gate.

## Frontend freshness

The chart loader uses a sequence guard so a response for an older asset cannot
overwrite a newer selection. No polling redesign or provider change was made.
