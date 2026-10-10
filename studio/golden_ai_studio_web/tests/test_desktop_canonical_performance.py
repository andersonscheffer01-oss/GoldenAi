import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "jarvis_ui" / "src" / "desktop-shell.js"


def test_performance_projection_uses_resolved_journal_metrics_only():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste DOM mockado")
    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function renderCanonicalPerformance(data) {")
    end = source.index("\n  async function loadCanonicalPerformance()", start)
    projection = source[start:end]
    harness = r"""
const vm = require('node:vm');
class Node {
  constructor(children = {}) { this.nodes = children; this.lists = {}; this.textContent = ''; this.children = []; }
  querySelector(selector) { return this.nodes[selector] || null; }
  querySelectorAll(selector) { return this.lists[selector] || []; }
  append(...items) { this.children.push(...items); }
  replaceWith(item) { this.replacement = item; }
  replaceChildren(...items) { this.children = items; }
}
const cell = () => new Node();
const empty = new Node({b:cell(), p:cell()});
const assetPanel = new Node({'.d2DonorEmpty':empty, '.d2MutedTag':cell()});
const body = new Node();
const table = new Node({tbody:body});
table.lists['thead th'] = [cell(),cell(),cell(),cell(),cell()];
const hourPanel = new Node({'.d2DonorSectionTitle p':cell(), '.d2MutedTag':cell(), '.d2PerformanceTable':table});
const summary = cell();
const view = new Node({'.d2AssetPanel':assetPanel, '.d2SessionPanel':hourPanel, '.d2ReportHeading p':summary});
const context = {
  document:{createElement:() => new Node(), querySelector:() => view},
};
vm.runInNewContext(process.argv[1], context);
context.renderCanonicalPerformance({
  asset_performance:{BTCUSD:{wins:2,losses:1,breakeven:0,win_rate:66.7,total_pnl_r:1.25,profit_factor:2,expectancy_r:0.42}},
  hourly_performance:{'9':{hour:9,wins:1,losses:1,breakeven:0,win_rate:50,expectancy_r:0.1,max_drawdown_r:0.5}}
});
if (!assetPanel.nodes['.d2DonorEmpty'].replacement) throw new Error('asset aggregates not rendered');
const assetRow = assetPanel.nodes['.d2DonorEmpty'].replacement.children[0];
if (!assetRow.children[2].textContent.includes('1,25 R') || assetRow.children[2].textContent.includes('US$')) throw new Error('R units or monetary safety lost');
if (!assetRow.children[1].textContent.includes('resultados resolvidos no Journal')) throw new Error('Journal provenance label missing');
if (!hourPanel.nodes['.d2PerformanceTable'].nodes.tbody.children[0].children[0].textContent.includes('09:00')) throw new Error('hourly aggregate not rendered');
if (!hourPanel.nodes['.d2DonorSectionTitle p'].textContent.includes('fuso não normalizado')) throw new Error('timezone uncertainty lost');
if (!summary.textContent.includes('10.000 registros')) throw new Error('source limit missing');
if (!summary.textContent.includes('importações MT5 não provam execução')) throw new Error('import provenance warning missing');
if (!summary.textContent.includes('execução não comprovada')) throw new Error('execution claim warning missing');
if (!summary.textContent.includes('pendentes excluídos')) throw new Error('pending analyses not distinguished');
if (!summary.textContent.includes('sem curva patrimonial')) throw new Error('unsupported equity claim not bounded');
"""
    completed = subprocess.run(
        [node, "-e", harness, projection], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_performance_read_requires_authenticated_explicit_tab_and_caches_once():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste Gateway mockado")
    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  async function loadCanonicalPerformance() {")
    end = source.index('\n  const panel = document.querySelector(".d2PanelView")', start)
    loader = source[start:end]
    route_start = source.index("  function selectRoute(route) {")
    route_end = source.index("\n  root.addEventListener", route_start)
    route = source[route_start:route_end]
    assert 'if (route === "performance") loadCanonicalPerformance();' in route
    assert 'if (route === "operacoes") loadCanonicalPerformance();' not in route
    assert 'if (route === "historico") loadCanonicalPerformance();' not in route
    period_handlers = source[source.index('document.querySelectorAll("[data-d2-period]")'):start]
    assert "button.disabled = true;" in period_handlers
    harness = r"""
const vm = require('node:vm');
const summary = {textContent:''};
const view = {querySelector:() => summary};
let calls = 0;
const context = {
  document:{querySelector:() => view},
  window:{Gateway:{isAuthenticated:false,httpPost:async () => {calls++; return null;}}},
  performanceSnapshotLoaded:false, performanceSnapshotLoading:false,
  renderCanonicalPerformance:() => {},
};
(async () => {
  vm.runInNewContext(process.argv[1] + ';', context);
  await context.loadCanonicalPerformance();
  if (calls !== 0 || !summary.textContent.includes('Aguardando sessão')) throw new Error('unauthenticated read was attempted');
  context.window.Gateway.isAuthenticated = true;
  context.window.Gateway.httpPost = async (path, body) => {
    calls++;
    if (path !== '/api/jarvis/golden/statistics' || Object.keys(body).length) throw new Error('wrong endpoint or arguments');
    return {ok:true, read_only:true, security_state:'READ_ONLY_NO_SIDE_EFFECT', data:{asset_performance:{},hourly_performance:{}}};
  };
  await context.loadCanonicalPerformance();
  await context.loadCanonicalPerformance();
  if (calls !== 1 || !context.performanceSnapshotLoaded) throw new Error('snapshot was not cached for this session');
})();
"""
    completed = subprocess.run(
        [node, "-e", harness, loader], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_operations_and_history_remain_unconsulted_and_no_demo_hydration_runs():
    source = SHELL.read_text(encoding="utf-8")
    html = (ROOT / "jarvis_ui" / "jarvis.html").read_text(encoding="utf-8")
    assert 'MT5 não foi consultado neste modo' in html
    assert 'Trade Journal, tester e AuditLog permanecem fontes distintas.' in html
    assert 'FONTE NÃO CONSULTADA · DATA ORIGINAL · FUSO NÃO CONVERTIDO' in html
    start = source.index("function hydrateDemoViews() {")
    end = source.index("\n}", start)
    hydration = source[start:end]
    assert hydration.index("return;") < hydration.index("analysis.innerHTML = `")
    assert hydration.index("return;") < hydration.index("operations.innerHTML = `")
    assert hydration.index("return;") < hydration.index("performance.innerHTML = `")
    assert hydration.index("return;") < hydration.index("history.innerHTML = `")


def test_performance_markup_and_projection_do_not_imply_real_account_execution():
    source = SHELL.read_text(encoding="utf-8")
    html = (ROOT / "jarvis_ui" / "jarvis.html").read_text(encoding="utf-8")
    start = html.index('<section class="gView d2View d2DonorView d2PerformanceView"')
    end = html.index('\n      <section class="gView d2View d2DonorView d2HistoryView"', start)
    performance = html[start:end]
    assert "EXECUÇÃO NÃO COMPROVADA" in performance
    assert "limite de 10.000 registros por agregado" in performance
    assert "importações não comprovam conta real" in performance
    assert "US$ 1.842,50" not in performance
    assert "199 TRADES · PRINT" not in performance
    assert "Londres <b>92% acerto" not in performance
    assert "125 trades · risco moderado" not in performance
    assert "resultados resolvidos no Journal" in source
