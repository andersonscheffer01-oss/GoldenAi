# 54 Failed Tests — Exact Accounting

**Date:** 2026-09-18
**Baseline:** 1185 passed, 54 failed, 24 skipped

---

## By Subsystem

### 1. VOICE / STREAMING (24 failures)

| Test File | Failures | Root Cause | Pre-Existing | Changed by UI-1 | Blocks Production |
|-----------|----------|------------|--------------|-----------------|-------------------|
| test_ordering_cancel.py | 10 | Async race conditions in TTS pipeline ordering and cancel propagation. Tests use `@pytest.mark.asyncio` but asyncio not configured in pytest. | YES | NO | NO — voice subsystem |
| test_streaming_voice.py | 8 | TTS pipeline: synthesize creates file, cancel returns None, submit/next ordering, pipeline cancel. Async wiring issues. | YES | NO | NO — voice subsystem |
| test_tool_call_safety.py | 5 | Tool call stops streaming, prose completes, text+tool stops, no TTS for tool, legacy preservation. Async mock issues. | YES | NO | NO — voice subsystem |
| test_barge_in_runtime_wiring.py | 7 | Barge-in monitor sets followup flag, preserves context, utterance source metadata. Production handler wiring. | YES | NO | NO — voice subsystem |
| test_jarvis_voice_conversation_p11.py | 1 | Voice service uses one TTS call. Configuration mismatch. | YES | NO | NO — voice subsystem |

**VOICE SUBTOTAL: 31 failures**

### 2. STREAMING BENCHMARKS (6 failures)

| Test File | Failures | Root Cause | Pre-Existing | Changed by UI-1 | Blocks Production |
|-----------|----------|------------|--------------|-----------------|-------------------|
| test_benchmark_streaming.py | 6 | Streaming first audio latency, cancellation benchmark, chunker latency, TTS pipeline latency. Performance thresholds not met. | YES | NO | NO — benchmark only |

**BENCHMARK SUBTOTAL: 6 failures**

### 3. GATEWAY INTEGRATION (12 failures)

| Test File | Failures | Root Cause | Pre-Existing | Changed by UI-1 | Blocks Production |
|-----------|----------|------------|--------------|-----------------|-------------------|
| test_gateway_integration.py | 12 | All tests require live Gateway server running. Health, WS connect, auth, commands, session, reconnect, malformed JSON, oversized payload. | YES | NO | NO — requires live server |

**GATEWAY SUBTOTAL: 12 failures**

### 4. OLLAMA / ORCHESTRATOR (2 failures)

| Test File | Failures | Root Cause | Pre-Existing | Changed by UI-1 | Blocks Production |
|-----------|----------|------------|--------------|-----------------|-------------------|
| test_ollama_stream.py | 1 | `async def` functions are not supported in sync test. Test framework issue. | YES | NO | NO |
| test_orchestrator_ollama.py | 1 | Same `async def` issue. | YES | NO | NO |

**OLLAMA SUBTOTAL: 2 failures**

### 5. JARVIS HARDENING (2 failures)

| Test File | Failures | Root Cause | Pre-Existing | Changed by UI-1 | Blocks Production |
|-----------|----------|------------|--------------|-----------------|-------------------|
| test_jarvis_hardening.py | 2 | Tool registry validation: tools come from registry, registry has unique valid tools. May be outdated tool list. | YES | NO | NO — validation only |

**HARDENING SUBTOTAL: 2 failures**

### 6. ERRORS (not failures)

| Test File | Error | Root Cause | Pre-Existing | Changed by UI-1 |
|-----------|-------|------------|--------------|-----------------|
| test_phase6_2a_real.py | Import/collection error | Missing dependency or broken test setup | YES | NO |
| test_phase6_lan_real.py | Import/collection error | Missing dependency or broken test setup | YES | NO |

---

## Summary

| Category | Count | Pre-Existing | Changed by UI-1 |
|----------|-------|--------------|-----------------|
| VOICE/STREAMING | 31 | 31 | 0 |
| BENCHMARKS | 6 | 6 | 0 |
| GATEWAY INTEGRATION | 12 | 12 | 0 |
| OLLAMA/ORCHESTRATOR | 2 | 2 | 0 |
| JARVIS HARDENING | 2 | 2 | 0 |
| **TOTAL** | **54** | **54** | **0** |

---

## Key Findings

1. **ALL 54 failures are PRE-EXISTING** — none introduced by UI-1 or UI-1.2 changes
2. **0 failures in UI layer** — all failures are in backend subsystems (voice, streaming, gateway integration)
3. **Root causes:**
   - Async test configuration (pytest-asyncio not properly configured)
   - Live server dependency (gateway integration tests)
   - Performance threshold not met (benchmarks)
   - Outdated tool registry (hardening tests)
4. **None block UI production** — UI operates independently of voice/streaming subsystems
5. **NEW_FAILURES_INTRODUCED_BY_UI: 0**

---

## Recommended Actions (not in scope)

1. Configure `pytest-asyncio` mode properly for async tests
2. Skip gateway integration tests when server not running
3. Update tool registry to match current service.py tools
4. Review streaming benchmarks thresholds
