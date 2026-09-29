# Jarvis Chat Synchronization Audit

## Pipelines

### Main Chat

`jarvis_ui/jarvis.html` -> `src/app.js` -> `src/bridge.js` -> `Gateway.sendCommand()` -> WebSocket `8766/ws` -> `jarvis_core/gateway/gateway.py` -> `JarvisService.execute_command()` -> canonical `Brain`/`CentralOrchestrator`/`ModelRouter` -> `ToolRegistry` and `SecurityManager` -> `AuditLog`.

### Market Chat

`market.html` -> `desktop_center.js` -> `POST /api/jarvis/chat` -> `server_agent.GoldenAIHandler.route_api()` -> `_api_jarvis_chat()` -> `DESKTOP_CENTER.service` plus `get_brain(service.registry)` -> canonical Brain/ModelRouter. Tool plans call `JarvisService.execute_tool()`.

The two paths use the same service singleton and the same Brain factory/registry. The Market path does not use the Gateway WebSocket and does not provide a session id from the UI. Its default is `desktop` and that id is used for telemetry, not as a shared conversation history.

## Authority comparison

| Concern | Main | Market Chat | Result |
|---|---|---|---|
| `JarvisService` | Gateway service | `DESKTOP_CENTER.service` | SAME canonical instance |
| Brain | `get_brain` through service | `get_brain(service.registry)` | SAME canonical Brain factory |
| ModelRouter | Brain -> orchestrator models | Brain -> orchestrator models | SAME authority for chat |
| Model selection | Orchestrator profile/policy | Orchestrator profile/policy | Same authority, different route context |
| Provider selection | ModelRouter fallback | ModelRouter fallback | Same authority |
| Memory boundary | Brain `CanonicalMemoryBoundary` | Brain `CanonicalMemoryBoundary` | Same boundary available |
| SecurityManager | Gateway command plus service execution | service execution for tools | Same execution boundary for tools |
| AuditLog | `execute_command` explicitly records | Tool path records; text path has telemetry but no equivalent explicit receipt proven | PARTIAL equivalence |
| HTTP/Gateway auth | Gateway auth/device token | Direct port 8765 handler has no auth check | GAP / P2 security hardening |
| Conversation history | Gateway session/idempotency, but no shared UI transcript contract | No history argument; only text | NOT SHARED |
| Market context | Not applicable | Not sent | MISSING |

## Model drift

Market Chat itself is not hardcoded to a separate chat model. It reaches the canonical Brain and ModelRouter. The Market deep-analysis path is different and is hardcoded to local Ollama `qwen2.5-coder:14b` in `_api_market_analyze`; this is a separate AI feature and creates model/provider drift relative to Jarvis policy. The UI does not expose a canonical selection control for the Market chat.

## Conversation/session result

`SHARED_THREAD_ID=NO`. The Gateway creates a session for the Main Chat. `desktop_center.js` calls `/api/jarvis/chat` without `session_id`, `conversation_id`, or `conversation_history`. The Market transcript is only a DOM result drawer. Cross-chat continuation is therefore not proven and should not be assumed.

Recommended target: `SEPARATE_THREADS_SAME_BRAIN` first, with an explicit canonical `conversation_id` bridge later when the user opts into sharing. Keep `surface=main|market` metadata and append structured MarketContext rather than creating a second brain.

## Required future bridge

```text
Market UI
  -> selected symbol/timeframe and a bounded MarketContext envelope
  -> canonical chat request with conversation_id/surface
  -> JarvisService / Brain / ModelRouter
  -> canonical memory/security/audit
```

The bridge must distinguish current chart snapshot from user-provided text, carry freshness and provenance, and refuse to invent missing values. It must not mix all Market analysis JSONL into memory automatically.

## Finding

`SAME_JARVIS_SERVICE=YES`, `SAME_BRAIN=YES`, `SAME_MODEL_ROUTER=YES` for Market Chat, but `SHARED_CONVERSATION_HISTORY=NO` and `MARKET_CONTEXT_AVAILABLE_TO_CHAT=NO`. No second `MarketChatService`, `MarketBrain`, or `MarketModelRouter` was found.
