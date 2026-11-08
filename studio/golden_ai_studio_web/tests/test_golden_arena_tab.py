from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "jarvis_ui" / "jarvis.html"
SHELL = ROOT / "jarvis_ui" / "src" / "desktop-shell.js"
CSS = ROOT / "jarvis_ui" / "src" / "desktop-shell.css"
SERVER = ROOT / "server_agent.py"


def test_arena_tab_is_under_intelligence_control_and_maps_to_native_view():
    html = HTML.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")

    nav_start = html.index('<nav id="d2Navigation"')
    nav_end = html.index("</nav>", nav_start)
    nav = html[nav_start:nav_end]
    assert nav.index("INTELIGÊNCIA E CONTROLE") < nav.index('data-d2-route="golden-arena"')
    assert 'data-d2-route="golden-arena"' in nav
    assert 'data-target-view="d2-golden-arena"' in nav
    assert 'data-view="d2-golden-arena"' in html
    assert '"golden-arena": { view: "d2-golden-arena"' in shell
    assert '"d2-golden-arena": "golden-arena"' in shell


def test_arena_tab_uses_read_only_report_contract_without_external_window():
    html = HTML.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert "Golden Scalper Arena" in html
    assert 'data-execution-authority="NONE"' in html
    assert "/api/jarvis/golden/arena/report" in shell
    assert "/api/jarvis/golden/arena/report" in server
    assert "window.open(" not in shell
    assert "execution_authority" in shell
    assert "d2Arena" in css

