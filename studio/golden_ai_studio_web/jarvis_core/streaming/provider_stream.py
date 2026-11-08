"""Provider streaming adapter — thin interface for LLM token streaming.

Wraps existing providers to emit tokens via AsyncIterator.
Providers without streaming fall back to full-response emulation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import AsyncIterator, Optional

log = logging.getLogger(__name__)


async def stream_groq(
    messages: list[dict],
    model: str = "qwen/qwen3.8-27b",
    timeout: float = 30.0,
) -> AsyncIterator[str]:
    """Stream tokens from Groq via SSE.

    Falls back to non-streaming if streaming fails.
    """
    try:
        import httpx

        # Build Groq-compatible payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.3,
            "max_tokens": 1024,
        }

        api_key = _get_groq_key()
        if not api_key:
            log.warning("No Groq API key — falling back to non-streaming")
            async for token in _fallback_non_streaming(messages, model):
                yield token
            return

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    log.warning("Groq streaming failed: %s", body[:200])
                    async for token in _fallback_non_streaming(messages, model):
                        yield token
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        import json
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue

    except ImportError:
        log.warning("httpx not installed — falling back to non-streaming")
        async for token in _fallback_non_streaming(messages, model):
            yield token
    except Exception as e:
        log.warning("Groq streaming error: %s — falling back", e)
        async for token in _fallback_non_streaming(messages, model):
            yield token


async def stream_openrouter(
    messages: list[dict],
    model: str = "anthropic/claude-sonnet-4",
    timeout: float = 30.0,
) -> AsyncIterator[str]:
    """Stream tokens from OpenRouter.

    Uses existing chat_stream if available, else falls back.
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from claude_provider import ClaudeProvider

        provider = ClaudeProvider()
        # chat_stream is a sync generator — wrap in async
        for chunk in provider.chat_stream(messages=messages, model=model):
            if isinstance(chunk, dict) and "token" in chunk:
                yield chunk["token"]
            elif isinstance(chunk, str):
                yield chunk

    except Exception as e:
        log.warning("OpenRouter streaming error: %s — falling back", e)
        async for token in _fallback_non_streaming(messages, model):
            yield token


async def stream_ollama(
    messages: list[dict],
    model: str = "qwen2.5-coder:14b",
    timeout: float = 45.0,
) -> AsyncIterator[str]:
    """Stream tokens from Ollama (local).

    Ollama SDK supports stream=True returning an iterator.
    """
    try:
        from ollama import chat

        response = chat(model=model, messages=messages, stream=True)
        for chunk in response:
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content

    except Exception as e:
        log.warning("Ollama streaming error: %s — falling back", e)
        async for token in _fallback_non_streaming(messages, model):
            yield token


async def _fallback_non_streaming(
    messages: list[dict],
    model: str,
) -> AsyncIterator[str]:
    """Non-streaming fallback — yields full response as single token."""
    try:
        from ollama import chat

        response = chat(model=model, messages=messages, stream=False)
        content = response.get("message", {}).get("content", "")
        if content:
            yield content
    except Exception as e:
        log.error("Non-streaming fallback failed: %s", e)
        yield f"[Erro: {e}]"


def _get_groq_key() -> Optional[str]:
    """Get Groq API key from environment or config."""
    import os
    key = os.getenv("GROQ_API_KEY")
    if key:
        return key
    # Try config file
    try:
        import json
        config_root = Path(
            os.environ.get("GOLDENAI_ROOT")
            or Path(__file__).resolve().parents[4]
        ).resolve()
        config_path = config_root / "config" / "api_keys.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            return config.get("groq_api_key") or config.get("GROQ_API_KEY")
    except Exception:
        pass
    return None




