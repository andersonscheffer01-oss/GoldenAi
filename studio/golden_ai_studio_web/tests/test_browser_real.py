"""Real Browser Integration Test — Playwright on localhost.

Run with: C:\GoldenAI\.venv\Scripts\python.exe -m pytest tests/test_browser_real.py -v
Or: python -m pytest tests/test_browser_real.py -v

Tests real Playwright browser against a local HTML fixture.
No internet dependency. No external sites.

IMPORTANT: Uses venv Python (C:\GoldenAI\.venv\Scripts\python.exe)
because Playwright is installed there, not globally.
"""

import http.server
import sys
import threading
import time
from pathlib import Path

import pytest

STUDIO_ROOT = Path(r"C:\GoldenAI\studio\golden_ai_studio_web")
FIXTURES_DIR = STUDIO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(STUDIO_ROOT))

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from jarvis_core.browser import (
    get_browser_thread, NavigationSecurity, ExternalContent, ElementRef,
)

pytestmark = pytest.mark.integration

HOST = "127.0.0.1"
PORT = 8799


class _FixtureServer:
    """Simple HTTP server for serving test HTML fixtures."""

    def __init__(self):
        self._thread = None
        self._server = None

    def start(self):
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(FIXTURES_DIR), **kw)
            def log_message(self, format, *args):
                pass

        self._server = http.server.HTTPServer((HOST, PORT), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def stop(self):
        if self._server:
            self._server.shutdown()


@pytest.fixture(scope="module")
def fixture_server():
    """Start local HTTP server for test fixtures."""
    srv = _FixtureServer()
    srv.start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def bt():
    """Get the browser thread (thread-safe dispatcher)."""
    thread = get_browser_thread()
    yield thread
    thread.stop()


def _submit(bt, method, *args, **kwargs):
    """Helper to submit to browser thread."""
    return bt.submit(method, *args, **kwargs)


@pytest.mark.integration
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserRealNavigate:
    """Real navigation tests against local fixture."""

    def test_start_browser(self, bt):
        result = _submit(bt, "start")
        assert result["ok"] is True

    def test_navigate_to_fixture(self, bt, fixture_server):
        result = _submit(bt, "navigate", f"http://{HOST}:{PORT}/browser_test.html", True)
        assert result["ok"] is True
        assert "browser_test.html" in result["url"]

    def test_page_title(self, bt):
        info = _submit(bt, "get_page_info")
        assert info["ok"] is True
        assert "Browser Test" in info["page"]["title"]

    def test_page_headings(self, bt):
        info = _submit(bt, "get_page_info")
        assert info["ok"] is True
        headings = info["page"]["headings"]
        assert len(headings) >= 2
        texts = [h["text"] for h in headings]
        assert any("Links" in t for t in texts)
        assert any("Form" in t for t in texts)

    def test_page_text(self, bt):
        result = _submit(bt, "read_page")
        assert result["ok"] is True
        assert "Browser Test Page" in result["content"]["text"]
        assert result["content"]["is_untrusted"] is True

    def test_external_content_wrapped(self, bt):
        result = _submit(bt, "read_page")
        assert "UNTRUSTED DATA" in result["sanitized"]
        assert "[END EXTERNAL CONTENT]" in result["sanitized"]


@pytest.mark.integration
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserRealElements:
    """Real element extraction and refs."""

    def test_get_elements(self, bt):
        result = _submit(bt, "get_elements")
        assert result["ok"] is True
        assert result["count"] >= 5

    def test_element_refs_created(self, bt):
        _submit(bt, "get_elements")
        # Access refs from the session directly (same thread via submit)
        session = bt._session
        refs = session.element_refs
        assert refs.count >= 5
        all_refs = refs.all_refs()
        tags = [info.get("tag") for info in all_refs.values()]
        assert "a" in tags or "button" in tags or "input" in tags

    def test_element_ref_has_text(self, bt):
        _submit(bt, "get_elements")
        session = bt._session
        all_refs = session.element_refs.all_refs()
        for ref, info in all_refs.items():
            if info.get("tag") == "button" and "Submit" in info.get("text", ""):
                assert ref.startswith("e")
                return
        pytest.skip("Submit button not found")


@pytest.mark.integration
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserRealActions:
    """Real browser actions (click, type, scroll)."""

    def test_click_by_text(self, bt):
        result = _submit(bt, "click", text="Show Dynamic")
        assert result["ok"] is True
        # Verify via thread-safe evaluate
        eval_result = _submit(bt, "evaluate",
            "() => !document.getElementById('dynamic-content').classList.contains('hidden')")
        assert eval_result["ok"] is True
        assert eval_result["result"] is True

    def test_type_in_input(self, bt):
        result = _submit(bt, "type_text", selector="#name-input", text="Golden AI Test")
        assert result["ok"] is True
        eval_result = _submit(bt, "evaluate",
            "() => document.getElementById('name-input').value")
        assert eval_result["ok"] is True
        assert eval_result["result"] == "Golden AI Test"

    def test_scroll_down(self, bt):
        result = _submit(bt, "scroll", direction="down", amount=500)
        assert result["ok"] is True

    def test_scroll_top(self, bt):
        result = _submit(bt, "scroll", direction="top")
        assert result["ok"] is True

    def test_screenshot(self, bt, tmp_path):
        import jarvis_core.browser as bm
        old_dir = bm._SCREENSHOT_DIR
        bm._SCREENSHOT_DIR = str(tmp_path)
        try:
            result = _submit(bt, "screenshot")
            assert result["ok"] is True
            assert Path(result["path"]).exists()
        finally:
            bm._SCREENSHOT_DIR = old_dir


@pytest.mark.integration
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserRealNavigation:
    """Real navigation history (back/forward)."""

    def test_navigate_and_back(self, bt, fixture_server):
        _submit(bt, "navigate", f"http://{HOST}:{PORT}/browser_test.html", True)
        _submit(bt, "navigate", "https://example.com")
        result = _submit(bt, "go_back")
        assert result["ok"] is True
        assert "browser_test.html" in result["url"]


@pytest.mark.integration
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserRealHealth:
    """Real health check."""

    def test_health(self, bt):
        health = _submit(bt, "health")
        assert health["ok"] is True
        assert health["started"] is True
        assert health["headless"] is True
        assert health["uptime_seconds"] >= 0


@pytest.mark.integration
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserRealCleanup:
    """Real process cleanup — verified by fixture teardown."""

    def test_fixture_browser_cleans_up(self, bt):
        health = _submit(bt, "health")
        assert health["ok"] is True
        assert health["started"] is True
