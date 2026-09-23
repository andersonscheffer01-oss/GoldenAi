"""Adapters finos sobre clientes existentes; não executam ferramentas."""
import json
import os
import re
import time
import urllib.error
import urllib.request

from ..config import resolve_api_key
from .model_router import ProviderAdapter
from .models import ProviderState


class ProviderCallError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _env_enabled(name):
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


class OmniRouteProvider:
    """Optional OpenAI-compatible backend for the canonical ModelRouter.

    This adapter owns HTTP translation only. It does not register tools, start
    OmniRoute, or change the router's existing provider policy when disabled.
    """

    name = "omniroute"

    def __init__(self, base_url="http://127.0.0.1:20128", api_key=None,
                 timeout=15.0, provider_id="ollama-local", default_model=None):
        self.base_url = str(base_url or "http://127.0.0.1:20128").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.timeout = max(1.0, float(timeout))
        self.provider_id = str(provider_id or "ollama-local").strip()
        self.default_model = str(default_model or "").strip()

    @property
    def configured(self):
        return bool(self.api_key)

    def as_adapter(self):
        return ProviderAdapter(
            self.name,
            self.complete,
            cloud=True,
            state=(ProviderState.AVAILABLE if self.configured
                   else ProviderState.AUTH_ERROR),
        )

    def _request_json(self, method, path, payload=None, timeout=None):
        body = None
        headers = {"Accept": "application/json",
                   "x-omniroute-no-memory": "true",
                   "x-omniroute-compression": "off"}
        if self.provider_id:
            headers["x-omniroute-provider"] = self.provider_id
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except (TypeError, ValueError) as exc:
                    raise ProviderCallError("OmniRoute retornou JSON inválido.") from exc
        except urllib.error.HTTPError as exc:
            raise ProviderCallError("OmniRoute HTTP %s." % exc.code, exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderCallError("OmniRoute indisponível: %s" % type(exc).__name__) from exc

    def health(self, timeout=None):
        """Probe the local health surface without exposing credentials."""
        try:
            data = self._request_json("GET", "/api/health", timeout=timeout)
            return {"ok": True, "provider": self.name, "response": data}
        except ProviderCallError as exc:
            return {"ok": False, "provider": self.name,
                    "status_code": exc.status_code, "error": str(exc)}

    health_check = health

    def list_models(self, timeout=None):
        data = self._request_json("GET", "/v1/models", timeout=timeout)
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ProviderCallError("OmniRoute /v1/models retornou formato inválido.")
        return rows

    def complete(self, payload, model="auto", timeout=None, **options):
        messages = payload.get("messages", []) if isinstance(payload, dict) else payload
        resolved_model = (self.default_model if self.default_model and
                          str(model).startswith("auto") else model)
        request_payload = {"model": resolved_model, "messages": messages, "stream": False}
        if isinstance(payload, dict):
            for key in ("tools", "tool_choice", "response_format", "temperature",
                        "max_tokens", "top_p"):
                if key in payload:
                    request_payload[key] = payload[key]
        for key in ("tools", "tool_choice", "response_format"):
            if key in options:
                request_payload[key] = options[key]
        started = time.perf_counter()
        data = self._request_json("POST", "/v1/chat/completions", request_payload,
                                  timeout=timeout)
        try:
            choice = data["choices"][0]
            message = choice["message"]
            text = message.get("content", "")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderCallError("OmniRoute completions retornou formato inválido.") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderCallError("OmniRoute retornou resposta vazia.")
        metadata = {"provider": self.name,
                    "requested_model": model,
                    "routed_provider": self.provider_id,
                    "latency_ms": int((time.perf_counter() - started) * 1000)}
        if data.get("model"):
            metadata["resolved_model"] = data["model"]
        if isinstance(data.get("usage"), dict):
            metadata["usage"] = data["usage"]
        if data.get("id"):
            metadata["response_id"] = data["id"]
        if message.get("tool_calls"):
            metadata["tool_calls"] = message["tool_calls"]
        return {"text": text, "metadata": metadata}

    def stream(self, payload, model="auto", timeout=None, **options):
        """Yield decoded SSE data for direct integration tests.

        The canonical Jarvis router is non-streaming today, so this method is
        deliberately not wired into ModelRouter.execute yet.
        """
        messages = payload.get("messages", []) if isinstance(payload, dict) else payload
        resolved_model = (self.default_model if self.default_model and
                          str(model).startswith("auto") else model)
        request_payload = {"model": resolved_model, "messages": messages, "stream": True}
        for key in ("tools", "tool_choice", "response_format"):
            if key in options:
                request_payload[key] = options[key]
        body = json.dumps(request_payload).encode("utf-8")
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json",
                   "x-omniroute-no-memory": "true",
                   "x-omniroute-compression": "off"}
        if self.provider_id:
            headers["x-omniroute-provider"] = self.provider_id
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(self.base_url + "/v1/chat/completions",
                                         data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                for raw in response:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        return
                    try:
                        yield json.loads(value)
                    except (TypeError, ValueError) as exc:
                        raise ProviderCallError("OmniRoute retornou SSE inválido.") from exc
        except urllib.error.HTTPError as exc:
            raise ProviderCallError("OmniRoute HTTP %s." % exc.code, exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderCallError("OmniRoute indisponível: %s" % type(exc).__name__) from exc


def build_omniroute_provider_from_env():
    if not _env_enabled("OMNIROUTE_ENABLED"):
        return None
    key = resolve_api_key("OMNIROUTE_API_KEY", "omniroute_api_key")
    return OmniRouteProvider(
        base_url=os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128"),
        api_key=key,
        timeout=float(os.getenv("OMNIROUTE_TIMEOUT_SECONDS", "15")),
        provider_id=os.getenv("OMNIROUTE_PROVIDER_ID", "ollama-local"),
        default_model=os.getenv("OMNIROUTE_MODEL", "qwen2.5-coder:14b"),
    )


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


def register_real_adapters(model_router, groq_call=None, gemini_call=None,
                           omniroute_provider=None):
    for adapter in build_real_adapters(groq_call, gemini_call):
        model_router.register_provider(adapter)
    provider = (omniroute_provider if omniroute_provider is not None
                else build_omniroute_provider_from_env())
    if provider is not None:
        model_router.register_provider(provider.as_adapter())
    return model_router
