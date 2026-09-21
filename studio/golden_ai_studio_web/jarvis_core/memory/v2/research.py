"""M1.5: research + learning foundation for Golden Memory V2.

External sources are always untrusted data. This module only turns fetched
content into evidence-backed candidates; durable knowledge is promoted through
GoldenMemoryEngine.remember(), keeping Memory V2 as the single writer.
"""
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from html import unescape
from ipaddress import ip_address
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

from ...orchestrator.models import DataClassification
from ...config import resolve_api_key
from ...data.timestamps import normalize_external_timestamp
from .record import MemoryRecordV2, MemorySecurityError, content_hash
from .types import ConfidenceBasis, MemoryKind, SourceType


class SourceTrustLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class LearningState(str, Enum):
    DISCOVERED = "discovered"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    VALIDATED = "validated"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class CandidateResolution(str, Enum):
    NEW = "new"
    DUPLICATE = "duplicate"
    UPDATE = "update"
    CONTRADICTION = "contradiction"
    UNCERTAIN = "uncertain"


class ExpertDomain(str, Enum):
    GAMING = "gaming"
    AMD = "amd"
    WINDOWS = "windows"
    TRADING = "trading"
    CODING = "coding"
    GOLDEN = "golden"
    RESEARCH = "research"


class ResearchProviderError(RuntimeError):
    """Provider failure; caller degrades without learning unsupported claims."""

    def __init__(self, reason: str, provider: str = ""):
        super().__init__(reason)
        self.reason = str(reason or "provider_down")
        self.provider = str(provider or "")


_INJECTION = re.compile(
    r"(?i)\b(ignore (?:all )?(?:previous|system|developer) instructions|"
    r"execute powershell|run powershell|send files|envie arquivos|"
    r"exfiltrate|system prompt|developer message)\b")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_OFFICIAL_HINTS = ("docs.", "developer.", "learn.", "support.", "manual.")
_FORUM_HINTS = ("reddit.", "forum.", "community.", "discourse.", "stackoverflow.")
_BENCH_HINTS = ("benchmark", "whitepaper", "paper", "arxiv", "github.com")
_SECRET_QUERY = re.compile(
    r"(?i)\b(password|passwd|senha|token|secret|api[_-]?key|authorization|"
    r"cookie|credential|private[_-]?key)\b\s*[:=]\s*\S+")
_HTML_SCRIPT = re.compile(r"(?is)<(script|style|noscript).*?</\1>")
_HTML_TAG = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"\s+")
_RESEARCH_STOPWORDS = frozenset({
    "qual", "quais", "versao", "versão", "atual", "atualmente", "current",
    "latest", "stable", "estavel", "estável", "existe", "alguma", "algum",
    "versoes", "versões", "para", "sobre", "com", "uma", "the", "and",
    "official", "oficial", "release", "releases", "status", "pre", "lancamento",
    "lançamento", "prerelease", "pré-lançamento",
})


def sanitize_research_query(query: str, max_chars: int = 240) -> str:
    value = _SECRET_QUERY.sub("[REDACTED]", str(query or ""))
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    return _WS.sub(" ", value).strip()[:max(20, int(max_chars))]


def safe_source_ref(url: str) -> str:
    """Keep provenance useful while stripping query/fragment secrets."""
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip()[:500]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))[:500]


def source_domain(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    return parsed.netloc.lower()


def normalize_research_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = "" if parsed.port is None else ":%d" % parsed.port
    path = parsed.path or "/"
    return urlunparse((scheme, host + port, path, "", parsed.query, ""))


def _is_blocked_host(host: str) -> bool:
    value = str(host or "").strip().strip("[]").lower()
    if not value or value in {"localhost", "localhost.localdomain",
                              "metadata.google.internal"}:
        return True
    try:
        candidates = [ip_address(value)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(value, None, proto=socket.IPPROTO_TCP)
            candidates = [ip_address(info[4][0]) for info in infos]
        except Exception as exc:
            raise ResearchProviderError("dns_resolution_failed") from exc
    for ip in candidates:
        if (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return True
    return False


def validate_fetch_url(url: str) -> str:
    normalized = normalize_research_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ResearchProviderError("unsupported_url_scheme")
    if _is_blocked_host(parsed.hostname or ""):
        raise ResearchProviderError("blocked_ssrf_target")
    return normalized


@dataclass(frozen=True)
class ResearchResult:
    title: str
    url: str
    snippet: str = ""
    source_type: str = ""
    domain: str = ""
    timestamp: float = 0.0
    provider: str = ""
    score: float = 0.0
    published_date: str = ""
    query: str = ""


@dataclass(frozen=True)
class FetchedSource:
    title: str
    url: str
    content: str
    source_type: str = ""
    fetched_at: float = 0.0
    content_type: str = ""
    provider: str = ""


class ResearchProvider(ABC):
    """Decoupled provider contract. No shell/browser automation required."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> List[ResearchResult]:
        ...

    @abstractmethod
    def fetch(self, result: ResearchResult) -> FetchedSource:
        ...


class StaticResearchProvider(ResearchProvider):
    """Deterministic adapter for tests and pre-fetched/manual research."""

    def __init__(self, sources: Iterable[FetchedSource]):
        self.sources = list(sources)

    def search(self, query: str, limit: int = 5) -> List[ResearchResult]:
        if query == "__provider_failure__":
            raise ResearchProviderError("static provider failure")
        return [ResearchResult(s.title, s.url, "", s.source_type,
                               source_domain(s.url), s.fetched_at, "static")
                for s in self.sources[:max(0, int(limit))]]

    def fetch(self, result: ResearchResult) -> FetchedSource:
        for source in self.sources:
            if source.url == result.url:
                return source
        raise ResearchProviderError("result unavailable")


def classify_provider_error(exc: Exception) -> str:
    if isinstance(exc, ResearchProviderError):
        return exc.reason
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return "auth_error"
        if exc.code == 429:
            return "rate_limit"
        if 500 <= exc.code <= 599:
            return "provider_down"
        return "http_%d" % exc.code
    text = str(exc).lower()
    for marker in ("missing_key", "auth_error", "rate_limit", "timeout",
                   "provider_down", "invalid_response"):
        if marker in text:
            return marker
    return type(exc).__name__


class SafeHTTPFetcher:
    allowed_content_types = (
        "text/html", "text/plain", "application/xhtml+xml",
        "application/json", "text/markdown")

    def __init__(self, timeout: float = 8.0, max_bytes: int = 250000,
                 max_redirects: int = 3, user_agent: str = "GoldenResearch/1.0"):
        self.timeout = float(timeout)
        self.max_bytes = max(4096, int(max_bytes))
        self.max_redirects = max(0, int(max_redirects))
        self.user_agent = user_agent
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self._opener = urllib.request.build_opener(NoRedirect)

    def fetch(self, url: str, title: str = "", source_type: str = "",
              provider: str = "") -> FetchedSource:
        current = validate_fetch_url(url)
        redirects = 0
        while True:
            req = urllib.request.Request(current, headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,text/plain,application/json;q=0.8,*/*;q=0.2",
            })
            try:
                context = ssl.create_default_context()
                https = urllib.request.HTTPSHandler(context=context)
                opener = urllib.request.build_opener(
                    https, *self._opener.handlers)
                with opener.open(req, timeout=self.timeout) as resp:
                    final_url = validate_fetch_url(resp.geturl())
                    if final_url != current:
                        redirects += 1
                        if redirects > self.max_redirects:
                            raise ResearchProviderError("redirect_limit_exceeded")
                        current = final_url
                        continue
                    ctype = (resp.headers.get("Content-Type", "")
                             .split(";", 1)[0].strip().lower())
                    if ctype and ctype not in self.allowed_content_types:
                        raise ResearchProviderError("unsupported_content_type")
                    declared = resp.headers.get("Content-Length")
                    if declared and int(declared) > self.max_bytes:
                        raise ResearchProviderError("oversized_page")
                    body = resp.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        raise ResearchProviderError("oversized_page")
                    charset = resp.headers.get_content_charset() or "utf-8"
                    text = body.decode(charset, errors="replace")
                    return FetchedSource(
                        title=title or self._title(text) or final_url,
                        url=final_url, content=self._extract_text(text, ctype),
                        source_type=source_type, fetched_at=time.time(),
                        content_type=ctype, provider=provider)
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("Location", "")
                    next_url = urllib.parse.urljoin(current, location)
                    current = validate_fetch_url(next_url)
                    redirects += 1
                    if redirects > self.max_redirects:
                        raise ResearchProviderError("redirect_limit_exceeded") from exc
                    continue
                raise ResearchProviderError("http_%d" % exc.code) from exc
            except ResearchProviderError:
                raise
            except Exception as exc:
                raise ResearchProviderError(type(exc).__name__) from exc

    @staticmethod
    def _title(text: str) -> str:
        match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text or "")
        return _WS.sub(" ", unescape(match.group(1))).strip()[:160] if match else ""

    @staticmethod
    def _extract_text(text: str, content_type: str) -> str:
        if content_type == "application/json":
            try:
                loaded = json.loads(text)
                return _WS.sub(" ", json.dumps(loaded, ensure_ascii=False))[:8000]
            except Exception:
                return _WS.sub(" ", text)[:8000]
        cleaned = _HTML_SCRIPT.sub(" ", text or "")
        cleaned = _HTML_TAG.sub(" ", cleaned)
        return _WS.sub(" ", unescape(cleaned)).strip()[:8000]


class BraveSearchResearchProvider(ResearchProvider):
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, fetcher: Optional[SafeHTTPFetcher] = None,
                 timeout: float = 8.0, retries: int = 1):
        if not str(api_key or "").strip():
            raise ResearchProviderError("missing_brave_api_key")
        self.api_key = str(api_key)
        self.fetcher = fetcher or SafeHTTPFetcher(timeout=timeout)
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))

    def search(self, query: str, limit: int = 5) -> List[ResearchResult]:
        q = sanitize_research_query(query)
        if not q:
            return []
        limit = max(1, min(int(limit), 10))
        params = urllib.parse.urlencode({"q": q, "count": limit,
                                         "safesearch": "moderate"})
        url = self.endpoint + "?" + params
        last_error = None
        for _ in range(self.retries + 1):
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
                "User-Agent": "GoldenResearch/1.0",
            })
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read(512000).decode("utf-8", "replace"))
                rows = payload.get("web", {}).get("results", [])
                return self._parse_results(rows, limit, q)
            except Exception as exc:
                last_error = exc
                if (time.perf_counter() - started) >= self.timeout:
                    break
        reason = classify_provider_error(last_error) if last_error else "provider_down"
        raise ResearchProviderError(reason, provider="brave")

    def fetch(self, result: ResearchResult) -> FetchedSource:
        return self.fetcher.fetch(result.url, title=result.title,
                                  source_type=result.source_type,
                                  provider="brave")

    def health_check(self) -> Dict[str, Any]:
        """Safe auth/endpoint probe. Never returns or logs the API key."""
        started = time.perf_counter()
        try:
            results = self.search("AMD Radeon Anti-Lag official documentation",
                                  limit=1)
            return {"ok": bool(results), "provider": "brave",
                    "key_present": bool(self.api_key),
                    "auth": "valid" if results else "unknown",
                    "endpoint": "reachable" if results else "empty",
                    "results_count": len(results),
                    "search_ms": int((time.perf_counter() - started) * 1000)}
        except ResearchProviderError as exc:
            text = str(exc)
            auth = "invalid" if any(code in text for code in (
                "http_401", "http_403", "HTTPError")) else "unknown"
            return {"ok": False, "provider": "brave",
                    "key_present": bool(self.api_key), "auth": auth,
                    "endpoint": "failed", "error": text[:120],
                    "search_ms": int((time.perf_counter() - started) * 1000)}

    @staticmethod
    def _parse_results(rows: Iterable[Dict[str, Any]],
                       limit: int, query: str = "") -> List[ResearchResult]:
        out: List[ResearchResult] = []
        seen = set()
        for row in rows:
            raw_url = str(row.get("url", "") or "")
            try:
                url = validate_fetch_url(raw_url)
            except Exception:
                continue
            ref = safe_source_ref(url)
            if ref in seen:
                continue
            seen.add(ref)
            out.append(ResearchResult(
                title=_WS.sub(" ", str(row.get("title", "") or "")).strip()[:160],
                url=url,
                snippet=_WS.sub(" ", str(row.get("description", "") or "")).strip()[:500],
                source_type="web",
                domain=source_domain(url),
                timestamp=time.time(),
                provider="brave"))
            if len(out) >= limit:
                break
        return out


class TavilyResearchProvider(ResearchProvider):
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, fetcher: Optional[SafeHTTPFetcher] = None,
                 timeout: float = 8.0, retries: int = 1):
        if not str(api_key or "").strip():
            raise ResearchProviderError("missing_key", provider="tavily")
        self.api_key = str(api_key)
        self.fetcher = fetcher or SafeHTTPFetcher(timeout=timeout)
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))

    def search(self, query: str, limit: int = 5) -> List[ResearchResult]:
        q = sanitize_research_query(query)
        if not q:
            return []
        limit = max(1, min(int(limit), 10))
        payload = json.dumps({
            "query": q,
            "search_depth": "basic",
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
        }).encode("utf-8")
        last_error = None
        for _ in range(self.retries + 1):
            req = urllib.request.Request(self.endpoint, data=payload, headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "GoldenResearch/1.0",
            }, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read(512000).decode("utf-8", "replace"))
                rows = data.get("results")
                if not isinstance(rows, list):
                    raise ResearchProviderError("invalid_response", provider="tavily")
                return self._parse_results(rows, limit, q)
            except Exception as exc:
                last_error = exc
                if classify_provider_error(exc) in {"auth_error", "rate_limit"}:
                    break
        raise ResearchProviderError(classify_provider_error(last_error),
                                    provider="tavily")

    def fetch(self, result: ResearchResult) -> FetchedSource:
        return self.fetcher.fetch(result.url, title=result.title,
                                  source_type=result.source_type,
                                  provider="tavily")

    def health_check(self) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            results = self.search("AMD Radeon Anti-Lag official documentation",
                                  limit=1)
            return {"ok": bool(results), "provider": "tavily",
                    "key_present": bool(self.api_key),
                    "auth": "valid" if results else "unknown",
                    "endpoint": "reachable" if results else "empty",
                    "results_count": len(results),
                    "search_ms": int((time.perf_counter() - started) * 1000)}
        except Exception as exc:
            reason = classify_provider_error(exc)
            return {"ok": False, "provider": "tavily",
                    "key_present": bool(self.api_key),
                    "auth": "invalid" if reason == "auth_error" else reason,
                    "endpoint": "failed", "error": reason,
                    "search_ms": int((time.perf_counter() - started) * 1000)}

    @staticmethod
    def _parse_results(rows: Iterable[Dict[str, Any]],
                       limit: int, query: str = "") -> List[ResearchResult]:
        out: List[ResearchResult] = []
        seen = set()
        for row in rows:
            try:
                url = validate_fetch_url(str(row.get("url", "") or ""))
            except Exception:
                continue
            ref = safe_source_ref(url)
            if ref in seen:
                continue
            seen.add(ref)
            out.append(ResearchResult(
                title=_WS.sub(" ", str(row.get("title", "") or "")).strip()[:160],
                url=url,
                snippet=_WS.sub(" ", str(row.get("content", "") or "")).strip()[:500],
                source_type="web",
                domain=source_domain(url),
                timestamp=time.time(),
                provider="tavily",
                score=float(row.get("score") or 0.0),
                published_date=str(row.get("published_date") or ""),
                query=query))
            if len(out) >= limit:
                break
        return out


class GroqWebResearchProvider(ResearchProvider):
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, fetcher: Optional[SafeHTTPFetcher] = None,
                 timeout: float = 12.0, retries: int = 1, model: str = ""):
        if not str(api_key or "").strip():
            raise ResearchProviderError("missing_key", provider="groq")
        self.api_key = str(api_key)
        self.fetcher = fetcher or SafeHTTPFetcher(timeout=timeout)
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.model = model or os.getenv("JARVIS_GROQ_WEB_MODEL",
                                        "groq/compound")

    def _build_body(self, query: str) -> bytes:
        return json.dumps({
            "model": self.model,
            "messages": [
                {"role": "user", "content": query},
            ],
            "temperature": 0,
            "max_tokens": 800,
        }).encode("utf-8")

    def search(self, query: str, limit: int = 5) -> List[ResearchResult]:
        q = sanitize_research_query(query)
        if not q:
            return []
        limit = max(1, min(int(limit), 8))
        prompts = [
            ("Search: %s. Return JSON: "
             "{\"results\":[{\"title\":\"...\",\"url\":\"...\",\"snippet\":\"...\"}]}"
             " - only real URLs." % q),
            ("Find web results for: %s. "
             "List title, URL, snippet as JSON array." % q),
        ]
        last_error = None
        for attempt in range(self.retries + 1):
            prompt = prompts[min(attempt, len(prompts) - 1)]
            body = self._build_body(prompt)
            req = urllib.request.Request(self.endpoint, data=body, headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "GoldenResearch/1.0",
            }, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(
                        resp.read(512000).decode("utf-8", "replace"))
                return self._parse_response(payload, limit)
            except Exception as exc:
                last_error = exc
                reason = classify_provider_error(exc)
                if reason in {"auth_error", "rate_limit"}:
                    break
                if reason == "http_413":
                    if attempt < self.retries:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    return []
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise ResearchProviderError(classify_provider_error(last_error),
                                    provider="groq")

    def fetch(self, result: ResearchResult) -> FetchedSource:
        return self.fetcher.fetch(result.url, title=result.title,
                                  source_type=result.source_type,
                                  provider="groq")

    def health_check(self) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            results = self.search("AMD Radeon Anti-Lag official documentation",
                                  limit=1)
            return {"ok": bool(results), "provider": "groq",
                    "key_present": bool(self.api_key),
                    "auth": "valid" if results else "unknown",
                    "endpoint": "reachable" if results else "empty",
                    "results_count": len(results),
                    "search_ms": int((time.perf_counter() - started) * 1000)}
        except Exception as exc:
            reason = classify_provider_error(exc)
            return {"ok": False, "provider": "groq",
                    "key_present": bool(self.api_key),
                    "auth": "invalid" if reason == "auth_error" else reason,
                    "endpoint": "failed", "error": reason,
                    "search_ms": int((time.perf_counter() - started) * 1000)}

    @staticmethod
    def _parse_response(payload: Dict[str, Any],
                        limit: int) -> List[ResearchResult]:
        try:
            message = payload["choices"][0]["message"]
            content = message.get("content", "")
        except Exception as exc:
            raise ResearchProviderError("invalid_response", provider="groq") from exc
        rows = []
        for tool in message.get("executed_tools", []) or []:
            search_results = tool.get("search_results", {}) or {}
            candidates = (search_results.get("results", [])
                          if isinstance(search_results, dict) else [])
            for row in candidates:
                if isinstance(row, dict):
                    rows.append({"title": row.get("title", ""),
                                 "url": row.get("url", ""),
                                 "snippet": row.get("content", row.get("snippet", ""))})
        if rows:
            return GroqWebResearchProvider._parse_rows(rows, limit)
        match = re.search(r"\{.*\}", str(content or ""), re.S)
        if not match:
            raise ResearchProviderError("invalid_response", provider="groq")
        try:
            data = json.loads(match.group(0))
        except Exception as exc:
            raise ResearchProviderError("invalid_response", provider="groq") from exc
        rows = data.get("results")
        if not isinstance(rows, list):
            raise ResearchProviderError("invalid_response", provider="groq")
        return GroqWebResearchProvider._parse_rows(rows, limit)

    @staticmethod
    def _parse_rows(rows: Iterable[Dict[str, Any]],
                    limit: int) -> List[ResearchResult]:
        out: List[ResearchResult] = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                url = validate_fetch_url(str(row.get("url", "") or ""))
            except Exception:
                continue
            ref = safe_source_ref(url)
            if ref in seen:
                continue
            seen.add(ref)
            out.append(ResearchResult(
                title=_WS.sub(" ", str(row.get("title", "") or "")).strip()[:160],
                url=url,
                snippet=_WS.sub(" ", str(row.get("snippet", "") or "")).strip()[:500],
                source_type="web",
                domain=source_domain(url),
                timestamp=time.time(),
                provider="groq"))
            if len(out) >= limit:
                break
        if not out:
            raise ResearchProviderError("invalid_response", provider="groq")
        return out


class AutoResearchProvider(ResearchProvider):
    def __init__(self, providers: Iterable[tuple[str, Optional[ResearchProvider]]]):
        pairs = list(providers)
        self.providers = [(name, provider) for name, provider in pairs if provider]
        self.unavailable = [{"provider": name, "reason": "missing_key"}
                            for name, provider in pairs if provider is None]
        self.last_selected = ""
        self.last_failures: List[Dict[str, str]] = []
        self.last_fallback_used = False
        self._cooldowns: Dict[str, float] = {}
        self.provider_states: Dict[str, Dict[str, Any]] = {}
        for name, provider in pairs:
            self.provider_states[name] = {
                "status": "CONFIGURED" if provider is not None else "NOT_CONFIGURED",
                "configured": provider is not None, "cooldown_until": 0.0,
                "last_error": "", "last_success": 0.0,
            }

    def search(self, query: str, limit: int = 5) -> List[ResearchResult]:
        self.last_selected = ""
        self.last_failures = list(self.unavailable)
        self.last_fallback_used = False
        if not self.providers:
            raise ResearchProviderError("missing_key", provider="auto")
        for index, (name, provider) in enumerate(self.providers):
            if self._cooldowns.get(name, 0.0) > time.monotonic():
                self.provider_states[name]["status"] = "COOLDOWN"
                self.provider_states[name]["cooldown_until"] = self._cooldowns[name]
                self.last_failures.append({"provider": name, "reason": "rate_limit_cooldown"})
                continue
            try:
                results = provider.search(query, limit=limit)
                if not results:
                    raise ResearchProviderError("invalid_response", provider=name)
                self.last_selected = name
                self.last_fallback_used = index > 0 or bool(self.last_failures)
                self.provider_states[name].update({
                    "status": "AVAILABLE", "last_error": "",
                    "last_success": time.time(), "cooldown_until": 0.0})
                return self._dedupe(results, limit)
            except Exception as exc:
                reason = classify_provider_error(exc)
                if reason == "rate_limit":
                    self._cooldowns[name] = time.monotonic() + float(
                        os.getenv("GOLDEN_RESEARCH_RATE_LIMIT_COOLDOWN", "60"))
                state = {"rate_limit": "RATE_LIMIT", "auth_error": "AUTH_ERROR",
                         "timeout": "TIMEOUT"}.get(reason, "ERROR")
                self.provider_states[name].update({
                    "status": state,
                    "last_error": reason,
                    "cooldown_until": self._cooldowns.get(name, 0.0),
                })
                self.last_failures.append({
                    "provider": name,
                    "reason": reason,
                })
                continue
        reason = self.last_failures[-1]["reason"] if self.last_failures else "provider_down"
        raise ResearchProviderError(reason, provider="auto")

    def status(self) -> Dict[str, Any]:
        now = time.monotonic()
        providers = {}
        for name, state in self.provider_states.items():
            item = dict(state)
            item["cooldown_active"] = bool(item.get("cooldown_until", 0.0) > now)
            providers[name] = item
        final_status = ("AVAILABLE" if self.last_selected else
                        "UNAVAILABLE" if self.last_failures else
                        "NOT_CHECKED" if any(item.get("configured")
                                             for item in providers.values())
                        else "NOT_CONFIGURED")
        return {"selected": self.last_selected,
                "fallback_count": len(self.last_failures),
                "final_status": final_status,
                "providers": providers}

    def fetch(self, result: ResearchResult) -> FetchedSource:
        provider_name = result.provider or self.last_selected
        for name, provider in self.providers:
            if name == provider_name:
                return provider.fetch(result)
        if self.providers:
            return self.providers[0][1].fetch(result)
        raise ResearchProviderError("provider_down", provider="auto")

    @staticmethod
    def _dedupe(results: Iterable[ResearchResult],
                limit: int) -> List[ResearchResult]:
        out: List[ResearchResult] = []
        seen = set()
        for result in results:
            ref = safe_source_ref(result.url)
            if not ref or ref in seen:
                continue
            seen.add(ref)
            out.append(result)
            if len(out) >= limit:
                break
        return out


def build_research_provider_from_env() -> Optional[ResearchProvider]:
    provider = (os.getenv("JARVIS_RESEARCH_PROVIDER")
                or os.getenv("GOLDEN_RESEARCH_PROVIDER")
                or "auto").strip().lower()
    timeout = float(os.getenv("GOLDEN_RESEARCH_TIMEOUT", "8"))
    max_bytes = int(os.getenv("GOLDEN_RESEARCH_MAX_BYTES", "250000"))
    redirects = int(os.getenv("GOLDEN_RESEARCH_MAX_REDIRECTS", "3"))
    retries = int(os.getenv("GOLDEN_RESEARCH_RETRIES", "1"))
    fetcher = SafeHTTPFetcher(timeout=timeout, max_bytes=max_bytes,
                              max_redirects=redirects)
    def tavily():
        key = resolve_api_key("TAVILY_API_KEY", "tavily_api_key")
        return TavilyResearchProvider(key, fetcher=fetcher, timeout=timeout,
                                      retries=retries) if key else None

    def groq():
        key = resolve_api_key("GROQ_API_KEY", "groq_api_key")
        return GroqWebResearchProvider(key, fetcher=fetcher, timeout=timeout,
                                       retries=1) if key else None

    def brave():
        key = resolve_api_key("BRAVE_SEARCH_API_KEY", "brave_search_api_key")
        return BraveSearchResearchProvider(key, fetcher=fetcher,
                                           timeout=timeout, retries=retries) if key else None
    if provider == "tavily":
        return tavily()
    if provider == "groq":
        return groq()
    if provider == "brave":
        return brave()
    if provider == "auto":
        return AutoResearchProvider((
            ("tavily", tavily()),
            ("groq", groq()),
            ("brave", brave()),
        ))
    if provider in {"none", "off", "disabled"}:
        return None
    return None


def research_provider_health_from_env() -> Dict[str, Any]:
    provider_name = (os.getenv("JARVIS_RESEARCH_PROVIDER")
                     or os.getenv("GOLDEN_RESEARCH_PROVIDER")
                     or "auto").strip().lower()
    key_specs = {"tavily": ("TAVILY_API_KEY", "tavily_api_key"),
                 "groq": ("GROQ_API_KEY", "groq_api_key"),
                 "brave": ("BRAVE_SEARCH_API_KEY", "brave_search_api_key")}
    if provider_name == "auto":
        order = ("tavily", "groq", "brave")
        availability = {name: bool(resolve_api_key(env, jkey))
                        for name, (env, jkey) in key_specs.items()}
        if not any(availability.values()):
            return {"ok": False, "provider": "auto", "provider_order": list(order),
                    "key_present": False, "auth": "missing_key",
                    "endpoint": "not_checked", "availability": availability}
    elif provider_name in key_specs:
        env, jkey = key_specs[provider_name]
        if not resolve_api_key(env, jkey):
            return {"ok": False, "provider": provider_name, "key_present": False,
                    "auth": "missing_key", "endpoint": "not_checked"}
    elif provider_name not in key_specs:
        return {"ok": False, "provider": provider_name or "",
                "key_present": False, "auth": "unknown",
                "endpoint": "unsupported_provider"}
    provider = build_research_provider_from_env()
    if provider is None:
        return {"ok": False, "provider": provider_name, "key_present": True,
                "auth": "unknown", "endpoint": "provider_unavailable"}
    if isinstance(provider, AutoResearchProvider):
        for name, child in provider.providers:
            health = getattr(child, "health_check", None)
            result = health() if callable(health) else {
                "ok": False, "provider": name, "auth": "unknown",
                "endpoint": "health_unavailable"}
            if result.get("ok"):
                result["provider_selected"] = name
                result["fallback_used"] = name != "tavily"
                result["provider_order"] = ["tavily", "groq", "brave"]
                return result
        return {"ok": False, "provider": "auto",
                "provider_order": ["tavily", "groq", "brave"],
                "auth": "unavailable", "endpoint": "failed"}
    health = getattr(provider, "health_check", None)
    if callable(health):
        return health()
    return {"ok": False, "provider": "brave", "key_present": True,
            "auth": "unknown", "endpoint": "health_unavailable"}


class SourceTrustEvaluator:
    """Separates source trust from content confidence."""

    official_domains = ("microsoft.com", "amd.com", "python.org", "nodejs.org", "openai.com")

    def evaluate(self, source: FetchedSource | ResearchResult) -> SourceTrustLevel:
        explicit = str(getattr(source, "source_type", "") or "").lower()
        url = str(getattr(source, "url", "") or "")
        domain = source_domain(url)
        haystack = " ".join([explicit, domain, url.lower(),
                             str(getattr(source, "title", "") or "").lower()])
        if explicit in ("official", "official_docs", "primary"):
            return SourceTrustLevel.A
        if any(domain.endswith(d) for d in self.official_domains) or any(
                h in haystack for h in _OFFICIAL_HINTS):
            return SourceTrustLevel.A
        if explicit in ("benchmark", "technical_benchmark", "paper") or any(
                h in haystack for h in _BENCH_HINTS):
            return SourceTrustLevel.B
        if explicit in ("forum", "community", "reddit") or any(
                h in haystack for h in _FORUM_HINTS):
            return SourceTrustLevel.D
        return SourceTrustLevel.E

    @staticmethod
    def aggregate(levels: Iterable[SourceTrustLevel],
                  domains: Iterable[str]) -> SourceTrustLevel:
        values = list(levels)
        unique_domains = {d for d in domains if d}
        if not values:
            return SourceTrustLevel.E
        if SourceTrustLevel.A in values:
            return SourceTrustLevel.A
        if SourceTrustLevel.B in values:
            return SourceTrustLevel.B
        if len(unique_domains) >= 2 and all(v != SourceTrustLevel.D for v in values):
            return SourceTrustLevel.C
        if all(v == SourceTrustLevel.D for v in values):
            return SourceTrustLevel.D
        return SourceTrustLevel.E


@dataclass
class EvidenceRecord:
    url: str
    title: str
    source_type: str
    timestamp: float
    domain: str
    trust: SourceTrustLevel
    confidence: float
    basis: str
    quote: str = ""
    prompt_injection_flags: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        temporal = normalize_external_timestamp(self.timestamp, "research_epoch")
        return {
            "url": safe_source_ref(self.url),
            "title": self.title,
            "source_type": self.source_type,
            "timestamp": self.timestamp,
            **temporal,
            "domain": self.domain,
            "trust": self.trust.value,
            "confidence": round(float(self.confidence), 4),
            "basis": self.basis,
            "prompt_injection_flags": list(self.prompt_injection_flags),
        }


@dataclass
class KnowledgeCandidate:
    claim: str
    topic: str = ""
    state: LearningState = LearningState.DISCOVERED
    confidence: float = 0.0
    trust: SourceTrustLevel = SourceTrustLevel.E
    evidences: List[EvidenceRecord] = field(default_factory=list)
    privacy: DataClassification = DataClassification.PUBLIC
    project: str = ""
    candidate_type: MemoryKind = MemoryKind.SEMANTIC
    canonical_key: str = ""
    resolution: CandidateResolution = CandidateResolution.UNCERTAIN
    local_context: Dict[str, Any] = field(default_factory=dict)
    promoted_memory_id: Optional[int] = None

    def refresh_assessment(self) -> None:
        domains = [e.domain for e in self.evidences]
        self.trust = SourceTrustEvaluator.aggregate([e.trust for e in self.evidences],
                                                    domains)
        if not self.evidences:
            self.confidence = 0.0
            self.state = LearningState.DISCOVERED
            return
        base = max(e.confidence for e in self.evidences)
        independent_bonus = min(0.12, 0.04 * max(0, len(set(domains)) - 1))
        if self.trust == SourceTrustLevel.A:
            base = max(base, 0.86)
        elif self.trust == SourceTrustLevel.B:
            base = max(base, 0.76)
        elif self.trust == SourceTrustLevel.D:
            independent_bonus = 0.0
            base = min(base, 0.58)
        self.confidence = min(0.98, base + independent_bonus)
        if self.confidence >= 0.84 and self.trust in (SourceTrustLevel.A,
                                                      SourceTrustLevel.B):
            self.state = LearningState.VALIDATED
        elif self.confidence >= 0.62 and self.trust != SourceTrustLevel.E:
            self.state = LearningState.SUPPORTED
        else:
            self.state = LearningState.DISCOVERED

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        if evidence.to_metadata() not in [e.to_metadata() for e in self.evidences]:
            self.evidences.append(evidence)
        self.refresh_assessment()


@dataclass
class LocalExperience:
    context: Dict[str, Any]
    metric: str
    result: str
    observed_at: float = 0.0

    def as_candidate_context(self) -> Dict[str, Any]:
        data = dict(self.context or {})
        data.update({"metric": self.metric, "result": self.result,
                     "observed_at": self.observed_at or time.time()})
        return data


@dataclass
class ExpertProfile:
    domain: ExpertDomain
    memory_ids: List[int] = field(default_factory=list)
    candidate_hashes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def index_memory(self, memory_id: int) -> None:
        if int(memory_id) not in self.memory_ids:
            self.memory_ids.append(int(memory_id))

    def index_candidate(self, candidate: KnowledgeCandidate) -> None:
        digest = content_hash(candidate.claim)
        if digest not in self.candidate_hashes:
            self.candidate_hashes.append(digest)


@dataclass
class ResearchReport:
    query: str
    candidates: List[KnowledgeCandidate] = field(default_factory=list)
    evidences: List[EvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    provider: str = ""
    elapsed_ms: int = 0
    search_ms: int = 0
    fetch_ms: int = 0
    results_count: int = 0
    pages_fetched: int = 0
    candidates_created: int = 0
    promoted: int = 0
    disputed: int = 0
    failed: int = 0
    provider_selected: str = ""
    fallback_used: bool = False
    failure_reason: str = ""
    provider_failures: List[Dict[str, str]] = field(default_factory=list)
    official_retry_count: int = 0
    raw_query: str = ""
    provider_query: str = ""


class ResearchEngine:
    def __init__(self, provider: Optional[ResearchProvider] = None,
                 trust_evaluator: Optional[SourceTrustEvaluator] = None):
        self.provider = provider
        self.trust_evaluator = trust_evaluator or SourceTrustEvaluator()

    def research(self, query: str, limit: int = 5,
                 privacy: DataClassification = DataClassification.PUBLIC,
                 project: str = "", topic: str = "", _official_retry: bool = True) -> ResearchReport:
        if privacy == DataClassification.SECRET:
            raise MemorySecurityError("SECRET não pode sair para pesquisa web")
        started = time.perf_counter()
        sanitized_query = sanitize_research_query(query)
        report = ResearchReport(query=sanitized_query, raw_query=str(query or ""),
                                provider=type(self.provider).__name__
                                if self.provider else "")
        if self.provider is None:
            report.errors.append("research_provider_unavailable")
            return report
        try:
            search_started = time.perf_counter()
            results = self.provider.search(sanitized_query, limit=limit)
            report.provider_query = sanitized_query
            # One bounded rescue search for time-sensitive queries when the
            # first response is irrelevant or lacks a trustworthy source.
            if self._needs_official_rescue(sanitized_query, results):
                rescue_query = sanitized_query + " official authoritative source"
                rescued = self.provider.search(rescue_query, limit=limit)
                report.official_retry_count = 1
                report.provider_query = rescue_query
                if rescued:
                    results = rescued
            report.search_ms = int((time.perf_counter() - search_started) * 1000)
        except Exception as exc:
            reason = classify_provider_error(exc)
            report.errors.append("provider_search_failed:%s" % reason)
            report.elapsed_ms = int((time.perf_counter() - started) * 1000)
            report.failed += 1
            report.failure_reason = reason
            report.provider_selected = getattr(self.provider, "last_selected", "")
            report.provider_failures = list(getattr(self.provider,
                                                    "last_failures", []) or [])
            return report
        report.provider_selected = (getattr(self.provider, "last_selected", "")
                                    or (results[0].provider if results else "")
                                    or report.provider)
        report.fallback_used = bool(getattr(self.provider,
                                            "last_fallback_used", False))
        report.provider_failures = list(getattr(self.provider,
                                                "last_failures", []) or [])
        by_claim: Dict[str, KnowledgeCandidate] = {}
        seen_results = set()
        for result in results:
            ref = safe_source_ref(result.url)
            if not ref or ref in seen_results:
                continue
            if (self._is_time_sensitive(sanitized_query) and
                    self._relevance_score(sanitized_query, result) <= 0):
                report.errors.append("irrelevant_result:%s" % source_domain(result.url))
                continue
            seen_results.add(ref)
            try:
                fetch_started = time.perf_counter()
                source = self.provider.fetch(result)
                report.fetch_ms += int((time.perf_counter() - fetch_started) * 1000)
                report.pages_fetched += 1
            except Exception as exc:
                reason = classify_provider_error(exc)
                report.errors.append("provider_fetch_failed:%s" % reason)
                report.failure_reason = report.failure_reason or reason
                report.failed += 1
                # If the search result itself is an authoritative source, keep
                # its bounded provider snippet as provenance instead of losing
                # the official source only because its page is oversized.
                if (self._relevance_score(sanitized_query, result) > 0 and
                        self.trust_evaluator.evaluate(result) == SourceTrustLevel.A and
                        str(result.snippet or "").strip()):
                    evidence = EvidenceRecord(
                        url=result.url, title=result.title,
                        source_type=result.source_type or "web",
                        timestamp=result.timestamp or time.time(),
                        domain=source_domain(result.url), trust=SourceTrustLevel.A,
                        confidence=self._evidence_confidence(SourceTrustLevel.A),
                        basis="official_search_result_snippet",
                        quote=str(result.snippet)[:800])
                    candidate = by_claim.setdefault(
                        content_hash(evidence.quote),
                        KnowledgeCandidate(claim=evidence.quote, topic=topic or query,
                                           privacy=privacy, project=project))
                    candidate.add_evidence(evidence)
                    report.evidences.append(evidence)
                continue
            trust = self.trust_evaluator.evaluate(source)
            flags = self._prompt_injection_flags(source.content)
            evidence_conf = self._evidence_confidence(trust)
            for claim in self._extract_claims(source.content):
                evidence = EvidenceRecord(
                    url=source.url, title=source.title,
                    source_type=source.source_type or result.source_type or "web",
                    timestamp=source.fetched_at or time.time(),
                    domain=source_domain(source.url), trust=trust,
                    confidence=evidence_conf,
                    basis=self._basis_for_trust(trust), quote=claim[:240],
                    prompt_injection_flags=flags)
                key = content_hash(claim)
                candidate = by_claim.setdefault(
                    key, KnowledgeCandidate(claim=claim, topic=topic or query,
                                            privacy=privacy, project=project))
                candidate.add_evidence(evidence)
                report.evidences.append(evidence)
        report.candidates = list(by_claim.values())
        report.results_count = len(seen_results)
        report.candidates_created = len(report.candidates)
        report.disputed = sum(1 for c in report.candidates
                              if c.state == LearningState.DISPUTED)
        if (_official_retry and report.official_retry_count == 0 and
                self._is_time_sensitive(sanitized_query) and
                not any(e.trust in (SourceTrustLevel.A, SourceTrustLevel.B)
                        for e in report.evidences)):
            rescue_query = sanitized_query + " official authoritative source"
            rescued = self.research(rescue_query, limit=limit, privacy=privacy,
                                    project=project, topic=topic,
                                    _official_retry=False)
            report.candidates.extend(rescued.candidates)
            report.evidences.extend(rescued.evidences)
            report.results_count += rescued.results_count
            report.pages_fetched += rescued.pages_fetched
            report.fetch_ms += rescued.fetch_ms
            report.search_ms += rescued.search_ms
            report.errors.extend(rescued.errors)
            report.provider_failures.extend(rescued.provider_failures)
            report.official_retry_count = 1
            report.provider_query = rescue_query
        report.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return report

    def _needs_official_rescue(self, query: str, results: Iterable[ResearchResult]) -> bool:
        if not self._is_time_sensitive(query):
            return False
        usable = [item for item in results if self._relevance_score(query, item) > 0]
        return not usable or not any(self.trust_evaluator.evaluate(item) in (
            SourceTrustLevel.A, SourceTrustLevel.B) for item in usable)

    @staticmethod
    def _is_time_sensitive(query: str) -> bool:
        return bool(re.search(
            r"\b(atual|atualmente|current|latest|stable|est[aá]vel|release|vers[aã]o|status)\b",
            str(query or ""), re.I))

    @staticmethod
    def _relevance_score(query: str, result: ResearchResult) -> int:
        terms = [term for term in re.findall(r"[a-z0-9]{3,}", str(query or "").lower())
                 if term not in _RESEARCH_STOPWORDS]
        if not terms:
            return 1
        haystack = " ".join((result.title, result.url, result.snippet)).lower()
        return sum(1 for term in set(terms) if term in haystack)

    @staticmethod
    def _extract_claims(content: str) -> List[str]:
        claims = []
        for raw in _SENTENCE.split(str(content or "")):
            text = re.sub(r"\s+", " ", raw).strip()
            if len(text) < 12 or _INJECTION.search(text):
                continue
            claims.append(text[:800])
        return claims[:20]

    @staticmethod
    def _prompt_injection_flags(content: str) -> List[str]:
        return sorted({m.group(0).lower()[:80] for m in _INJECTION.finditer(
            str(content or ""))})

    @staticmethod
    def _evidence_confidence(trust: SourceTrustLevel) -> float:
        return {SourceTrustLevel.A: 0.9, SourceTrustLevel.B: 0.78,
                SourceTrustLevel.C: 0.68, SourceTrustLevel.D: 0.52,
                SourceTrustLevel.E: 0.42}.get(trust, 0.4)

    @staticmethod
    def _basis_for_trust(trust: SourceTrustLevel) -> str:
        if trust == SourceTrustLevel.A:
            return "official_primary_source"
        if trust == SourceTrustLevel.B:
            return "technical_reproduction"
        if trust == SourceTrustLevel.C:
            return "multiple_independent_sources"
        if trust == SourceTrustLevel.D:
            return "community_report"
        return "isolated_hypothesis"


class LearningEngine:
    def __init__(self, memory_engine, research_engine: Optional[ResearchEngine] = None):
        self.memory = memory_engine
        self.research_engine = research_engine or ResearchEngine()

    def research_candidates(self, query: str, **kwargs) -> ResearchReport:
        report = self.research_engine.research(query, **kwargs)
        self.assess_candidates(report.candidates)
        report.disputed = sum(1 for c in report.candidates
                              if c.state == LearningState.DISPUTED)
        return report

    def research_and_learn(self, query: str, max_promotions: int = 5,
                           **kwargs) -> ResearchReport:
        report = self.research_candidates(query, **kwargs)
        promoted = 0
        for candidate in report.candidates:
            if promoted >= max(0, int(max_promotions)):
                break
            if candidate.resolution == CandidateResolution.CONTRADICTION:
                continue
            record = self.promote(candidate)
            if record is not None:
                promoted += 1
        report.promoted = promoted
        report.disputed = sum(1 for c in report.candidates
                              if c.state == LearningState.DISPUTED)
        return report

    def assess_candidates(self, candidates: Iterable[KnowledgeCandidate]) -> None:
        items = list(candidates)
        for candidate in items:
            candidate.resolution = self.compare_with_memory(candidate)
        for index, candidate in enumerate(items):
            for other in items[index + 1:]:
                if self.memory.consolidator._contradicts(candidate.claim, other.claim):
                    candidate.state = LearningState.DISPUTED
                    other.state = LearningState.DISPUTED
                    candidate.resolution = CandidateResolution.CONTRADICTION
                    other.resolution = CandidateResolution.CONTRADICTION

    def compare_with_memory(self, candidate: KnowledgeCandidate) -> CandidateResolution:
        exact = self.memory.store.find_by_hash(content_hash(candidate.claim),
                                               candidate.project)
        if exact is not None:
            return CandidateResolution.DUPLICATE
        incoming = MemoryRecordV2(
            memory_type=candidate.candidate_type,
            content=candidate.claim,
            title=candidate.topic[:120],
            confidence=candidate.confidence,
            confidence_basis=self._basis(candidate),
            privacy=candidate.privacy,
            source_type=self._source_type(candidate),
            source_ref=(safe_source_ref(candidate.evidences[0].url)
                        if candidate.evidences else ""),
            project=candidate.project,
            metadata=self._metadata(candidate),
            canonical_key=candidate.canonical_key)
        incoming.content_hash = content_hash(incoming.content)
        canonical = (self.memory.store.find_by_canonical(candidate.canonical_key,
                                                         candidate.project)
                     if candidate.canonical_key else None)
        decision = self.memory.consolidator.assess(incoming, canonical=canonical)
        mapping = {
            "new": CandidateResolution.NEW,
            "exact_duplicate": CandidateResolution.DUPLICATE,
            "semantic_duplicate": CandidateResolution.DUPLICATE,
            "update": CandidateResolution.UPDATE,
            "contradiction": CandidateResolution.CONTRADICTION,
            "uncertain": CandidateResolution.UNCERTAIN,
            "complement": CandidateResolution.NEW,
        }
        return mapping.get(decision.kind.value, CandidateResolution.UNCERTAIN)

    def promote(self, candidate: KnowledgeCandidate,
                expert: Optional[ExpertProfile] = None):
        if candidate.privacy == DataClassification.SECRET:
            raise MemorySecurityError("SECRET não pode ser promovido de pesquisa")
        if candidate.state not in (LearningState.SUPPORTED, LearningState.VALIDATED):
            candidate.state = LearningState.REJECTED
            return None
        record = self.memory.remember(
            candidate.claim,
            memory_type=candidate.candidate_type,
            title=candidate.topic[:120],
            confidence=candidate.confidence,
            confidence_basis=self._basis(candidate),
            privacy=candidate.privacy,
            source_type=self._source_type(candidate),
            source_ref=(safe_source_ref(candidate.evidences[0].url)
                        if candidate.evidences else ""),
            project=candidate.project,
            tags=["research", candidate.trust.value.lower()],
            metadata=self._metadata(candidate),
            canonical_key=candidate.canonical_key)
        candidate.promoted_memory_id = record.id
        if record.status.value == "disputed":
            candidate.state = LearningState.DISPUTED
        if expert is not None and record.id is not None:
            expert.index_memory(record.id)
        return record

    @staticmethod
    def _basis(candidate: KnowledgeCandidate) -> ConfidenceBasis:
        if candidate.trust == SourceTrustLevel.A:
            return ConfidenceBasis.DOCUMENTED
        if candidate.trust == SourceTrustLevel.B:
            return ConfidenceBasis.TEST_CONFIRMED
        return ConfidenceBasis.SOURCE_CONFIRMED

    @staticmethod
    def _source_type(candidate: KnowledgeCandidate) -> SourceType:
        if candidate.trust == SourceTrustLevel.A:
            return SourceType.OFFICIAL_DOCS
        if candidate.trust == SourceTrustLevel.B:
            return SourceType.TECHNICAL_BENCHMARK
        if candidate.trust == SourceTrustLevel.D:
            return SourceType.COMMUNITY_FORUM
        return SourceType.WEB_ARTICLE

    @staticmethod
    def _metadata(candidate: KnowledgeCandidate) -> Dict[str, Any]:
        return {
            "research": {
                "state": candidate.state.value,
                "resolution": candidate.resolution.value,
                "trust": candidate.trust.value,
                "topic": candidate.topic,
                "local_context": dict(candidate.local_context or {}),
                "evidence": [e.to_metadata() for e in candidate.evidences],
            }
        }
