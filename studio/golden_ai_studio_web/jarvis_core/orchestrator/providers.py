"""Adapters finos sobre clientes existentes; não executam ferramentas."""
import re

from .model_router import ProviderAdapter
from .models import ProviderState


class ProviderCallError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _raise_text_error(value):
    text = value if isinstance(value, str) else ""
    if isinstance(value, dict):
        # OpenRouter retorna dict: erro -> excecao; sucesso -> texto.
        err = value.get("error")
        if err:
            text = str(err)
            match = re.search(r"HTTP\s+(\d+)", text, re.I)
            code = int(match.group(1)) if match else None
            if code in (401, 403) or "não configurada" in text or "nao configurada" in text:
                code = code or 401
            raise ProviderCallError(text[:500], code)
        try:
            return value["choices"][0]["message"].get("content", "")
        except (KeyError, IndexError, TypeError):
            raise ProviderCallError("OpenRouter retornou formato inesperado.")
    if not text.lower().startswith(("erro groq:", "erro gemini:", "erro openrouter:")):
        return value
    match = re.search(r"HTTP\s+(\d+)", text, re.I)
    raise ProviderCallError(text[:500], int(match.group(1)) if match else None)


def build_real_adapters(groq_call=None, gemini_call=None):
    adapters = []
    if groq_call:
        def groq(payload, model, timeout):
            keys = {"qwen/qwen3.8-27b": "groq-llama",
                    "groq/compound-mini": "groq-fast",
                    "openai/gpt-oss-120b": "groq-reasoning"}
            try:
                value = groq_call(payload, keys.get(model, "groq-fast"), timeout=timeout,
                                  stream=model in {"qwen/qwen3.8-27b", "groq/compound-mini"})
            except TypeError:
                value = groq_call(payload, keys.get(model, "groq-fast"))
            return value if isinstance(value, dict) and "text" in value else _raise_text_error(value)
        adapters.append(ProviderAdapter("groq", groq, cloud=True))
    if gemini_call:
        def gemini(payload, model, timeout):
            try:
                value = gemini_call(payload, model, timeout=timeout)
            except TypeError:
                value = gemini_call(payload, model)
            return _raise_text_error(value)
        adapters.append(ProviderAdapter("gemini", gemini, cloud=True))
    try:
        from claude_provider import get_claude_provider
        provider = get_claude_provider()
        state = ProviderState.AVAILABLE if provider.api_key else ProviderState.AUTH_ERROR
        def openrouter(payload, model, timeout):
            return _raise_text_error(provider.chat(payload, model=model))
        adapters.append(ProviderAdapter("openrouter", openrouter, cloud=True, state=state))
    except Exception:
        pass
    try:
        from ollama import chat
        def ollama(payload, model, timeout):
            response = chat(model=model, messages=payload, stream=False)
            return response.get("message", {}).get("content", "")
        adapters.append(ProviderAdapter("ollama", ollama, cloud=False))
    except Exception:
        pass
    return adapters


def register_real_adapters(model_router, groq_call=None, gemini_call=None):
    for adapter in build_real_adapters(groq_call, gemini_call):
        model_router.register_provider(adapter)
    return model_router
