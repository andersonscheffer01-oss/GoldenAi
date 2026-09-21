from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.execution import ExecutionService, ExecutionStatus


@dataclass(frozen=True)
class BrowserEnvironment:
    available: bool
    chromium_path: str = ""
    browser_type: str = "chromium"
    error: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserActionResult:
    status: str
    url: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    screenshot_path: str = ""
    duration_ms: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BrowserService:
    """Automacao de navegador via Playwright (chromium headless)."""

    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.screenshots_dir = self.root / "sandbox" / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None

    # ------------------------------------------------------------------
    # Infra
    # ------------------------------------------------------------------

    def audit_environment(self) -> BrowserEnvironment:
        try:
            import playwright
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                path = ""
                try:
                    path = p.chromium.executable_path
                except Exception:
                    path = ""
                env = BrowserEnvironment(
                    available=True,
                    chromium_path=path,
                    browser_type="chromium",
                    evidence={"playwright_version": getattr(playwright, "__version__", "?")},
                )
            return env
        except Exception as exc:
            return BrowserEnvironment(
                available=False,
                error=str(exc),
                evidence={"hint": "pip install playwright && python -m playwright install chromium"},
            )

    def status(self) -> dict[str, Any]:
        env = self.audit_environment()
        return {
            "BROWSER_SUPPORTED": env.available,
            "BROWSER_TYPE": env.browser_type,
            "CHROMIUM_PATH": env.chromium_path,
            "ERROR": env.error,
        }

    def _event(self, task_id: str, action: str, status: str, summary: str, risk: str = "LOW", permission: str = "READ") -> None:
        try:
            self.execution.record_event(
                task_id=task_id, category="BROWSER", action=action, status=status,
                summary=summary[:600], tool_name="browser_service",
                permission_level=permission, risk_level=risk,
            )
            self.audit.record({
                "action_type": action, "status": status, "agent": "core.browser",
                "target": task_id, "result": summary[:600],
            })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Acerto de pagina
    # ------------------------------------------------------------------

    def fetch_page(self, url: str, wait_ms: int = 800, max_text: int = 60000, screenshot: bool = False) -> BrowserActionResult:
        env = self.audit_environment()
        if not env.available:
            return BrowserActionResult("BROWSER_NOT_AVAILABLE", url=url, error=env.error)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return BrowserActionResult("INVALID_URL", url=url, error="URL invalida: precisa ser http(s).")
        started = time.perf_counter()
        self._event(url, "BROWSER_FETCH_STARTED", ExecutionStatus.RUNNING.value, url)
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if wait_ms > 0:
                    page.wait_for_timeout(wait_ms)
                title = page.title() or ""
                text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
                html = ""
                if len(text) > max_text:
                    text = text[:max_text] + "...[truncado]"
                screenshot_path = ""
                if screenshot:
                    fname = f"page_{int(time.time() * 1000)}.png"
                    screenshot_path = str(self.screenshots_dir / fname)
                    page.screenshot(path=screenshot_path, full_page=False)
                browser.close()
            duration = int((time.perf_counter() - started) * 1000)
            self._event(url, "BROWSER_FETCH_COMPLETED", ExecutionStatus.COMPLETED.value, f"titulo={title}; texto={len(text)}")
            return BrowserActionResult(
"COMPLETED", url=url, title=title, text=text, html=html,
                screenshot_path=screenshot_path, duration_ms=duration,
                metadata={"final_url": url},
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._event(url, "BROWSER_FETCH_FAILED", ExecutionStatus.FAILED.value, str(exc))
            return BrowserActionResult("FAILED", url=url, error=str(exc), duration_ms=duration)

    def search_web(self, query: str, max_results: int = 5, wait_ms: int = 1200) -> BrowserActionResult:
        """Pesquisa web: DuckDuckGo HTML (primario, via urllib com UA real),
        Bing renderizado como fallback quando DDG falha."""
        env = self.audit_environment()
        if not env.available:
            return BrowserActionResult("BROWSER_NOT_AVAILABLE", error=env.error)
        started = time.perf_counter()
        self._event(query, "BROWSER_SEARCH_STARTED", ExecutionStatus.RUNNING.value, query)
        try:
            results = self._search_duckduckgo(query, max_results)
            engine = "duckduckgo"
            if not results:
                results = self._search_bing(query, max_results, wait_ms)
                engine = "bing"
            duration = int((time.perf_counter() - started) * 1000)
            self._event(query, "BROWSER_SEARCH_COMPLETED", ExecutionStatus.COMPLETED.value, f"engine={engine}; resultados={len(results)}")
            return BrowserActionResult(
                "COMPLETED",
                title=f"Resultados para: {query}",
                text=json.dumps(results, ensure_ascii=False),
                duration_ms=duration,
                metadata={"results": results, "count": len(results), "engine": engine},
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._event(query, "BROWSER_SEARCH_FAILED", ExecutionStatus.FAILED.value, str(exc))
            return BrowserActionResult("FAILED", error=str(exc), duration_ms=duration)

    @staticmethod
    def _decode_ddg_redirect(url: str) -> str:
        """DDG embrulha URLs reais em //duckduckgo.com/l/?uddg=<url-encoded>."""
        if "uddg=" not in url:
            return url
        try:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            target = params.get("uddg", [""])[0]
            if target.startswith("http"):
                return target
        except Exception:
            pass
        return url

    @staticmethod
    def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, Any]]:
        import urllib.request
        import urllib.error
        from urllib.parse import quote

        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        url = "https://html.duckduckgo.com/html/?q=" + quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read(200000).decode("utf-8", errors="replace")
        if "challenge" in html.lower():
            return []
        import re
        import html as html_mod
        items = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            r'|<a[^>]*href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>',
            html,
        )
        results: list[dict[str, Any]] = []
        for m in items[:max_results]:
            href, title = m[0] or m[2], m[1] or m[3]
            real_url = BrowserService._decode_ddg_redirect(html_mod.unescape(href))
            title = re.sub("<[^>]+>", "", title).strip()
            if not title:
                continue
            results.append({
                "url": real_url,
                "title": title,
                "snippet": "",
                "domain": urllib.parse.urlparse(real_url).hostname or "",
            })
        return results

    def _search_bing(self, query: str, max_results: int = 5, wait_ms: int = 1200) -> list[dict[str, Any]]:
        from playwright.sync_api import sync_playwright

        results: list[dict[str, Any]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            bing_url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
            page.goto(bing_url, timeout=30000, wait_until="domcontentloaded")
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            for item in page.query_selector_all("li.b_algo")[:max_results]:
                anchor = item.query_selector("h2 a")
                if not anchor:
                    continue
                href = anchor.get_attribute("href") or ""
                snippet_el = item.query_selector("p")
                snippet = snippet_el.inner_text().strip() if snippet_el else ""
                real_url = self._decode_bing_redirect(href)
                results.append({
                    "url": real_url,
                    "title": anchor.inner_text().strip(),
                    "snippet": snippet[:300],
                    "domain": urllib.parse.urlparse(real_url).hostname or "",
                })
            browser.close()
        return results

    @staticmethod
    def _decode_bing_redirect(url: str) -> str:
        """Bing embrulha resultados em /ck/a?...&u=a1{base64 da URL real}&ntb=1."""
        if "bing.com/ck/a" not in url:
            return url
        try:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            encoded = params.get("u", [""])[0]
            if not encoded:
                return url
            if encoded.startswith("a1"):
                import base64
                decoded = base64.urlsafe_b64decode(encoded[2:] + "==").decode("utf-8", errors="ignore")
            else:
                decoded = encoded
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass
        return url
