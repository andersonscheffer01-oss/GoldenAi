import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "jarvis_ui" / "src" / "desktop-shell.js"


def test_analysis_projection_uses_only_matching_canonical_mock():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de projeção DOM mockada")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function renderAnalysisProjection() {")
    end = source.index('\n  window.Gateway?.on("authenticated"', start)
    projection = source[start:end]

    harness = r"""
const vm = require('node:vm');
class Node {
  constructor(nodes = {}, lists = {}) {
    this.nodes = nodes;
    this.lists = lists;
    this.dataset = {};
    this.textContent = 'fixture placeholder';
  }
  querySelector(selector) { return this.nodes[selector] || null; }
  querySelectorAll(selector) { return this.lists[selector] || []; }
  replaceChildren(...children) { this.children = children; }
  remove() { this.removed = true; }
}
const row = () => new Node({ strong: new Node(), small: new Node(), span: new Node(), b: new Node(), p: new Node() });
const choices = new Node();
const scan = new Node();
const status = new Node();
const title = new Node();
const thesis = new Node({ b: new Node(), p: new Node() });
const checklist = new Node();
const quality = new Node();
const footer = new Node();
const analysis = new Node({
  '.d2SymbolChoices': choices,
  '.d2ScanButton': scan,
  '.d2AnalysisState span': status,
  '.d2AnalysisState b': title,
  '.d2ThesisEmpty': thesis,
  '.d2ChecklistPanel .d2MutedTag': checklist,
  '.d2AudioQuality': quality,
  '.d2AnalysisProvenance': footer,
}, {
  '.d2AnalysisSummary > div': [row(), row(), row(), row()],
  '.d2ThesisPanel .d2EvidenceRows > div': [row(), row(), row(), row()],
  '.d2ParameterRows > div': [row(), row(), row()],
  '.d2CriteriaList em': [new Node(), new Node()],
  '.d2AnalysisProvenance > span': [row(), row(), row(), row()],
});
const asset = {provider:'MT5', provider_asset_id:'mt5:BTCUSD', provider_symbol:'BTCUSD', asset_class:'CRYPTO'};
const result = {
  status:'PARTIAL', analysis_mode:'INDEPENDENT', provider:'MT5', provider_asset_id:'mt5:BTCUSD', provider_symbol:'BTCUSD',
  directional_bias:'INDEFINIDA', confidence:null, summary:'Dados limitados do snapshot BTC.',
  trend:'INDISPONÍVEL', volatility:'INDISPONÍVEL', entry_scenario:'INDISPONÍVEL',
  invalidation:'INDISPONÍVEL', target_scenario:'INDISPONÍVEL', snapshot_id:'snap-btc-1',
  correlation_id:'corr-btc-1', execution_authority:'NONE',
  context_availability:{absolute_utc:'UNKNOWN'}, sources:{technical:{freshness:'UNKNOWN'}},
  model:{provider:'gemini'}, algorithmic_strength:{score:8.5}
};
const context = {
      analysisView: analysis, selectedPanelAsset: asset, selectedTimeframe:'M15', selectedAnalysisMode:'INDEPENDENT',
  selectedIdentityValidated:true,
  latestPanelAnalysis:{asset, timeframe:'M15', mode:'INDEPENDENT', result},
  panelMarketSnapshot:{snapshot_id:'snap-btc-1'},
  panelAnalysisRunning:false, analysisStatus:new Node(),
  document:{createElement:() => new Node()},
};
vm.runInNewContext(process.argv[1] + '; renderAnalysisProjection();', context);
if (!['BTCUSD', 'M15', 'INDEPENDENT', 'PARTIAL'].every(part => status.textContent.includes(part))) throw new Error('status/identity/mode not projected');
if (analysis.dataset.dataRecency !== 'UNKNOWN' || analysis.dataset.temporalAuthority !== 'UNKNOWN') throw new Error('temporal state lost');
if (analysis.dataset.providerAssetId !== 'mt5:BTCUSD' || analysis.dataset.snapshotId !== 'snap-btc-1') throw new Error('provenance identity lost');
if (analysis.lists['.d2AnalysisSummary > div'][0].nodes.strong.textContent !== 'INDEFINIDA') throw new Error('direction not projected');
if (analysis.lists['.d2AnalysisSummary > div'][1].nodes.strong.textContent !== 'INDISPONÍVEL') throw new Error('missing confidence was fabricated');
if (analysis.lists['.d2ParameterRows > div'][0].nodes.strong.textContent.includes('4.139')) throw new Error('demo scenario was fabricated');
if (analysis.lists['.d2CriteriaList em'].some(item => ['VALIDADO', 'SELL', 'BUY'].includes(item.textContent))) throw new Error('mock checklist leaked');
if (!quality.textContent.includes('EXECUTION_AUTHORITY NONE')) throw new Error('execution authority not preserved');
if (!scan.removed || !choices.children[0].textContent.includes('BTCUSD') || !choices.children[0].textContent.includes('M15')) throw new Error('independent controls remain');
if (JSON.stringify(analysis).includes('8.5')) throw new Error('strategy score leaked into analysis');

context.panelMarketSnapshot = {snapshot_id:'snap-btc-2'};
vm.runInNewContext(process.argv[1] + '; renderAnalysisProjection();', context);
if (!status.textContent.includes('NO_ANALYSIS') || analysis.dataset.snapshotId !== '') throw new Error('stale snapshot analysis was displayed');
context.panelMarketSnapshot = {snapshot_id:'snap-btc-1'};

context.latestPanelAnalysis = {asset:{...asset, provider_symbol:'XAUUSD', provider_asset_id:'mt5:XAUUSD'}, timeframe:'M15', mode:'INDEPENDENT', result:{...result, provider_symbol:'XAUUSD', provider_asset_id:'mt5:XAUUSD'}};
vm.runInNewContext(process.argv[1] + '; renderAnalysisProjection();', context);
if (!['BTCUSD', 'M15', 'NO_ANALYSIS'].every(part => status.textContent.includes(part))) throw new Error('mismatched result was displayed');
if (analysis.dataset.snapshotId !== '') throw new Error('mismatched snapshot identity leaked');
context.latestPanelAnalysis = {asset, timeframe:'M15', mode:'STRATEGY', result:{...result, analysis_mode:'STRATEGY'}};
vm.runInNewContext(process.argv[1] + '; renderAnalysisProjection();', context);
if (!status.textContent.includes('NO_ANALYSIS')) throw new Error('result from another mode was displayed');
"""
    completed = subprocess.run(
        [node, "-e", harness, projection],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_demo_view_hydration_stops_after_neutral_panel_shell():
    source = SHELL.read_text(encoding="utf-8")
    start = source.index("function hydrateDemoViews() {")
    end = source.index("\n}", start)
    hydration = source[start:end]

    assert "return;" in hydration
    assert hydration.index("return;") < hydration.index("analysis.innerHTML = `")
    assert hydration.index("return;") < hydration.index("operations.innerHTML = `")


def test_analysis_error_is_rendered_as_failure_without_reusing_analysis_fields():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de projeção DOM mockada")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function renderPanelAnalysis(")
    end = source.index("\n  const observer", start)
    renderer = source[start:end]
    harness = r"""
const vm = require('node:vm');
const asset = {provider:'MT5', provider_asset_id:'mt5:XAUUSD', provider_symbol:'XAUUSD'};
const summary = {textContent:''};
const panel = {querySelector: () => summary};
const analysisStatus = {textContent:'', dataset:{}};
let projectionCalls = 0;
const priorAnalysis = {status:'COMPLETE', directional_bias:'ALTA', confidence:91,
  analysis_mode:'INDEPENDENT', entry_scenario:'old scenario'};
const context = {
  asset, panel, analysisStatus, selectedTimeframe:'M15',
  selectedAnalysisMode:'INDEPENDENT',
  latestPanelAnalysis:{asset, timeframe:'M15', mode:'INDEPENDENT', result:priorAnalysis},
  renderAnalysisProjection(){ projectionCalls += 1; },
  rememberPersistedPanelAnalysis(){},
  invalidatePanelAnalysis(message){ throw new Error('unexpected invalidation: ' + message); },
};
vm.runInNewContext(process.argv[1] + '; renderPanelAnalysis({status:"ERROR",analysis_mode:"INDEPENDENT",provider_asset_id:"mt5:XAUUSD",provider_symbol:"XAUUSD",model_error_code:"PROVIDER_HTTP_FAILURE_HTTP_503",summary:"private provider body"}, asset);', context);
if (context.latestPanelAnalysis.result.status !== 'ERROR') throw new Error('error result not retained');
if (context.latestPanelAnalysis.result === priorAnalysis) throw new Error('previous analysis reused');
if (context.latestPanelAnalysis.result.directional_bias !== undefined || context.latestPanelAnalysis.result.confidence !== undefined) throw new Error('analysis values fabricated');
if (!analysisStatus.textContent.includes('PROVIDER_HTTP_FAILURE_HTTP_503') || analysisStatus.dataset.state !== 'ERROR') throw new Error('sanitized error not shown');
if (summary.textContent !== 'A análise falhou. Nenhuma conclusão foi produzida.') throw new Error('unsafe/provider body displayed');
if (projectionCalls !== 1) throw new Error('error state projection missing');
"""
    completed = subprocess.run(
        [node, "-e", harness, renderer], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_analysis_result_is_rejected_when_panel_snapshot_changed():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de snapshot stale")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function renderPanelAnalysis(")
    end = source.index("\n  const observer", start)
    renderer = source[start:end]
    harness = r"""
const vm = require('node:vm');
const asset = {provider:'MT5', provider_asset_id:'mt5:XAUUSD', provider_symbol:'XAUUSD'};
const summary = {textContent:''};
const field = () => ({textContent:''});
let invalidated = '';
const context = {
  panel:{querySelector:() => field(), querySelectorAll:() => []}, analysisStatus:{textContent:'', dataset:{}},
  selectedAssetHeading:null,
  selectedTimeframe:'M15', selectedAnalysisMode:'INDEPENDENT', selectedPanelAsset:asset,
  panelMarketSnapshot:{snapshot_id:'snap-new'}, latestPanelAnalysis:null,
  renderAnalysisProjection(){}, rememberPersistedPanelAnalysis(){},
  invalidatePanelAnalysis(message){ invalidated = message; },
};
context.asset = asset;
context.stale = {status:'PARTIAL', analysis_mode:'INDEPENDENT', provider_asset_id:'mt5:XAUUSD',
  provider_symbol:'XAUUSD', snapshot_id:'snap-old'};
vm.runInNewContext(process.argv[1] + '; renderPanelAnalysis({analysis:stale}, asset);', context);
if (!invalidated.includes('SNAPSHOT')) throw new Error('stale snapshot was accepted');
if (context.latestPanelAnalysis !== null) throw new Error('stale analysis was retained');
"""
    completed = subprocess.run(
        [node, "-e", harness, renderer], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_panel_snapshot_update_invalidates_previous_analysis_projection():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de invalidação live")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function renderMarketSnapshot(")
    end = source.index("\n  function invalidatePanelAnalysis", start)
    renderer = source[start:end]
    harness = r"""
const vm = require('node:vm');
let invalidated = '';
const text = () => ({textContent:''});
const context = {
  panelMarketSnapshot:{snapshot_id:'snap-old'}, latestPanelAnalysis:{result:{snapshot_id:'snap-old'}},
  selectedTimeframe:'M15', chartTitle:text(), chartQuote:text(), chartMeta:text(),
  chartSource:text(), chartUpdated:text(), chartState:{hidden:false,dataset:{}},
  analysisStatus:{textContent:'',dataset:{}}, analysisButton:{disabled:false}, selectedAssetHeading:null,
  drawMarketCandles:() => false, setMarketChartState(){}, syncAnalysisButton(){},
  invalidatePanelAnalysis(message){ invalidated = message; },
};
const snapshot = {snapshot_id:'snap-new', quote:{}, state:{freshness:'UNKNOWN', time_status:'UNKNOWN', temporal_authority:'UNKNOWN'},
  candles:[], status:'PARTIAL', asset:{provider_symbol:'XAUUSD'}, provenance:{}};
context.asset = {provider_symbol:'XAUUSD'};
context.snapshot = snapshot;
vm.runInNewContext(process.argv[1] + '; renderMarketSnapshot(snapshot, asset);', context);
if (!invalidated.includes('NOVO SNAPSHOT')) throw new Error('live snapshot did not invalidate analysis');
"""
    completed = subprocess.run(
        [node, "-e", harness, renderer], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_persisted_analysis_recovery_uses_authenticated_existing_contract_and_identity():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de recuperação mockada")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function panelAnalysisStorageKey(")
    end = source.index("\n  function setPanelAnalysisMode(mode)", start)
    recovery = source[start:end]
    harness = r"""
const vm = require('node:vm');
const asset = {provider_asset_id:'mt5:BTCUSD', provider_symbol:'BTCUSD'};
const analysis = {analysis_id:'panel_analysis_fixture1', provider_asset_id:'mt5:BTCUSD',
  provider_symbol:'BTCUSD', timeframe:'M15', analysis_mode:'INDEPENDENT', status:'PARTIAL'};
const values = new Map([['jarvis.desktop.golden.analysis.v2::mt5:BTCUSD::M15::INDEPENDENT', analysis.analysis_id]]);
let request = null;
let rendered = null;
const context = {
  selectedTimeframe:'M15', selectedAnalysisMode:'INDEPENDENT', selectedIdentityValidated:true, panelAnalysisRunning:false,
  analysisRecoveryRequestId:0, selectedPanelAsset:asset, asset,
  localStorage:{getItem:key => values.get(key), setItem:(key,value) => values.set(key,value)},
  window:{Gateway:{isAuthenticated:true, httpPost:async (path,payload) => {
    request = {path,payload}; return {ok:true,data:{found:true,analysis}};
  }}},
  renderPanelAnalysis:(envelope,selected,options) => { rendered = {envelope,selected,options}; },
};
(async () => {
  await vm.runInNewContext(`(async () => { ${process.argv[1]}; await recoverPersistedPanelAnalysis(asset); })()`, context);
  if (request.path !== '/api/jarvis/golden/panel-analysis' || request.payload.action !== 'GET') throw new Error('wrong authenticated contract');
  if (request.payload.analysis_id !== analysis.analysis_id) throw new Error('analysis id not used');
  if (!rendered || rendered.envelope.recovered !== true || rendered.envelope.analysis !== analysis) throw new Error('analysis not restored');
  if (values.size !== 1) throw new Error('recovery changed saved state');

  context.selectedPanelAsset = {...asset, provider_asset_id:'mt5:XAUUSD', provider_symbol:'XAUUSD'};
  rendered = null;
  await vm.runInNewContext(`(async () => { ${process.argv[1]}; await recoverPersistedPanelAnalysis(asset); })()`, context);
  if (rendered) throw new Error('identity mismatch was rendered');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    completed = subprocess.run(
        [node, "-e", harness, recovery], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_strategy_mode_fails_closed_without_versioned_core_support_or_network_reads():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de modo mockado")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function setPanelAnalysisMode(mode) {")
    end = source.index("\n  analysisModeSelect?.addEventListener", start)
    mode_controls = source[start:end]
    harness = r"""
const vm = require('node:vm');
const requests = [];
const select = {value:'',disabled:true};
const context = {
  selectedAnalysisMode:'INDEPENDENT', selectedStrategyId:'',
  selectedTimeframe:'M15', analysisRecoveryRequestId:0, latestPanelAnalysis:{status:'ERROR'},
  strategySelect:select, strategyStatus:{textContent:''},
  strategyControls:{hidden:true},
  analysisStatus:{textContent:'Erro anterior',dataset:{state:'ERROR'}},
  window:{Gateway:{httpGet:async path => {requests.push(path);return null;}}},
  invalidatePanelAnalysis(message){ this.invalidated = message; },
  syncAnalysisButton(){}, renderAnalysisProjection(){},
};
vm.runInNewContext(process.argv[1] + ';', context);
context.setPanelAnalysisMode('STRATEGY');
if (requests.length !== 0) throw new Error('mode switch performed network/catalog read');
if (!select.disabled || select.value !== '') throw new Error('strategy selection was not fail-closed');
if (!context.strategyStatus.textContent.includes('NENHUMA ESTRATÉGIA VERSIONADA E VÁLIDA')) throw new Error('strategy absence not explained');
if (!context.analysisStatus.textContent.includes('MODO ESTRATÉGIA')) throw new Error('strategy state not shown');
context.setPanelAnalysisMode('INDEPENDENT');
if (requests.length !== 0) throw new Error('switching back performed network read');
if (context.strategyControls.hidden !== true || context.latestPanelAnalysis !== null) throw new Error('mode switch did not hide strategy/clear prior result');
"""
    completed = subprocess.run(
        [node, "-e", harness, mode_controls], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_analysis_button_sends_explicit_independent_contract_and_stops_on_gateway_failure():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste do handler mockado")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index('  analysisButton?.addEventListener("click", async () => {')
    end = source.index("\n  function renderPanelAnalysis", start)
    handler = source[start:end]
    harness = r"""
const vm = require('node:vm');
let clickHandler;
const requests = [];
const summary = {textContent:'erro anterior'};
const button = {disabled:false, addEventListener(_event, fn){clickHandler=fn;},
  setAttribute(){}, removeAttribute(){}};
const status = {textContent:'',dataset:{state:'ERROR'}};
const asset = {provider:'MT5',provider_asset_id:'mt5:BTCUSD',provider_symbol:'BTCUSD',asset_class:'CRYPTO'};
let response = {ok:true,status:'COMPLETE',analysis_mode:'INDEPENDENT'};
const requestStates = [];
const gateway = {isAuthenticated:true, async httpPost(path,payload){
  requests.push({path,payload});
  requestStates.push({text:status.textContent,state:status.dataset.state,previous:context.latestPanelAnalysis});
  return response;
}};
let rendered = null;
const context = {
  analysisButton:button, analysisStatus:status, panel:{querySelector:()=>summary},
  selectedPanelAsset:asset, selectedTimeframe:'M15', selectedAnalysisMode:'INDEPENDENT',
  selectedStrategyId:'', panelAnalysisRunning:false, latestPanelAnalysis:{status:'ERROR'},
  panelMarketSnapshot:{timeframe:'M15'}, window:{Gateway:gateway},
  analysisEligible:()=>true,
  analysisEligibilityReason:()=>context.selectedAnalysisMode === 'STRATEGY' ? 'STRATEGY_MODE_UNAVAILABLE' : '',
  analysisEligibilityMessage:reason => reason === 'STRATEGY_MODE_UNAVAILABLE'
    ? 'ANÁLISE BLOQUEADA · MODO ESTRATÉGIA SEM ESTRATÉGIA VÁLIDA SUPORTADA.' : reason,
  syncAnalysisButton(){}, renderAnalysisProjection(){},
  renderPanelAnalysis(result, submitted, mode){rendered={result,submitted,mode};},
};
(async () => {
  vm.runInNewContext(process.argv[1] + ';', context);
  await clickHandler();
  if (requests.length !== 1) throw new Error('analysis request count not one');
  const first = requests[0];
  if (first.path !== '/api/jarvis/golden/panel-analysis') throw new Error('noncanonical endpoint');
  if (first.payload.analysis_mode !== 'INDEPENDENT' || first.payload.request_type !== 'ON_DEMAND'
      || first.payload.analysis_style !== 'AUTO' || first.payload.strategy_id !== '') throw new Error('independent contract not explicit');
  if (requestStates[0].state !== 'ANALYZING' || requestStates[0].text !== 'COLETANDO DADOS READ-ONLY...'
      || requestStates[0].previous !== null) throw new Error('prior error was not cleared into processing state');
  if (rendered?.mode !== 'INDEPENDENT') throw new Error('result not associated with submitted mode');
  if (summary.textContent.includes('erro anterior')) throw new Error('old error summary survived new attempt');

  response = {ok:false,http_failure:true,http_status:503,
    error_code:'PROVIDER_HTTP_FAILURE_HTTP_503',request_id:'req-503',correlation_id:'corr-503'};
  status.dataset.state = 'ERROR';
  await clickHandler();
  if (requests.length !== 2) throw new Error('gateway failure caused a retry');
  if (status.dataset.state !== 'ERROR' || !status.textContent.includes('HTTP 503')
      || !status.textContent.includes('PROVIDER_HTTP_FAILURE_HTTP_503')) throw new Error('HTTP error details not shown safely');
  if (status.dataset.requestId !== 'req-503' || status.dataset.correlationId !== 'corr-503') throw new Error('request correlation not retained');
  if (summary.textContent !== 'A análise não foi concluída. Nenhuma conclusão foi produzida.') throw new Error('failure summary missing or stale result survived');

  response = {ok:false,http_failure:true,http_status:null,error_code:'NETWORK_FAILURE',
    request_id:'req-net',correlation_id:'corr-net',failure_stage:'NETWORK_TRANSPORT'};
  await clickHandler();
  if (requests.length !== 3 || !status.textContent.includes('FALHA DE REDE')
      || !status.textContent.includes('NETWORK_FAILURE')) throw new Error('transport failure was lost');

  context.selectedAnalysisMode = 'STRATEGY';
  await clickHandler();
  if (requests.length !== 3 || !status.textContent.includes('MODO ESTRATÉGIA')) throw new Error('unsupported strategy mode reached analysis route');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    completed = subprocess.run(
        [node, "-e", harness, handler], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_analysis_eligibility_reports_actual_blocker_and_keeps_unknown_freshness_eligible():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste de elegibilidade mockado")

    source = SHELL.read_text(encoding="utf-8")
    start = source.index("  function analysisEligibilityReason() {")
    end = source.index("\n  function panelAnalysisStorageKey", start)
    eligibility = source[start:end]
    harness = r"""
const vm = require('node:vm');
const asset = {provider:'MT5',provider_asset_id:'mt5:BTCUSD',provider_symbol:'BTCUSD',asset_class:'CRYPTO'};
const snapshot = {asset:{provider:'MT5',asset_id:'mt5:BTCUSD',provider_symbol:'BTCUSD',asset_class:'CRYPTO'},
  timeframe:'M15',state:{market_data_available:true,freshness:'UNKNOWN'}};
const button = {disabled:false};
const status = {textContent:'',dataset:{}};
const context = {window:{Gateway:{isAuthenticated:true}},selectedPanelAsset:asset,
  selectedIdentityValidated:true,selectedAnalysisMode:'INDEPENDENT',selectedStrategyId:'',
  strategyModeSupportedByCore:false,panelMarketSnapshot:snapshot,selectedTimeframe:'M15',
  analysisButton:button,analysisStatus:status,panelAnalysisRunning:false};
vm.runInNewContext(process.argv[1] + ';', context);
const expected = [
  ['auth','AUTHENTICATION_REQUIRED',() => {context.window.Gateway.isAuthenticated=false;}],
  ['identity','IDENTITY_REVALIDATION_REQUIRED',() => {context.window.Gateway.isAuthenticated=true;context.selectedIdentityValidated=false;}],
  ['snapshot','SNAPSHOT_UNAVAILABLE',() => {context.selectedIdentityValidated=true;context.panelMarketSnapshot=null;}],
  ['snapshot identity','SNAPSHOT_IDENTITY_MISMATCH',() => {context.panelMarketSnapshot={...snapshot,asset:{...snapshot.asset,asset_id:'mt5:XAUUSD'}};}],
  ['market data','MARKET_DATA_UNAVAILABLE',() => {context.panelMarketSnapshot={...snapshot,state:{market_data_available:false,freshness:'UNKNOWN'}};}],
  ['recency','MARKET_DATA_STALE',() => {context.panelMarketSnapshot={...snapshot,state:{market_data_available:true,freshness:'STALE'}};}],
];
for (const [label, reason, prepare] of expected) {
  context.panelMarketSnapshot = snapshot;
  context.window.Gateway.isAuthenticated = true;
  context.selectedIdentityValidated = true;
  prepare();
  if (context.analysisEligibilityReason() !== reason) throw new Error(label + ' blocker not classified');
  context.syncAnalysisButton();
  if (!button.disabled || status.dataset.reason !== reason || !status.textContent) throw new Error(label + ' blocker not visible');
}
context.panelMarketSnapshot = snapshot;
if (context.analysisEligibilityReason() !== '') throw new Error('UNKNOWN freshness should defer to Core gate');
context.syncAnalysisButton();
if (button.disabled || status.dataset.reason !== '' || status.dataset.state !== 'READY') throw new Error('eligibility recovery did not clear prior blocker');
"""
    completed = subprocess.run(
        [node, "-e", harness, eligibility], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_gateway_http_post_preserves_sanitized_network_and_http_failure_metadata():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste mockado do Gateway")

    adapter = (ROOT / "jarvis_ui" / "src" / "gateway-adapter.js").read_text(encoding="utf-8")
    start = adapter.index("    async httpPost(path, data) {")
    end = adapter.index("\n    // ─── Reconnection", start)
    method = adapter[start:end]
    harness = r"""
const vm = require('node:vm');
const logs = [];
const requests = [];
let response;
const context = {
  location:{origin:'https://127.0.0.1:8765'},
  window:{crypto:{randomUUID:()=>'ui-request-1'}},
  fetch:async (url,options) => { requests.push({url,options}); if (response instanceof Error) throw response; return response; },
  console:{warn:(...args)=>logs.push(args),error(){}},
  JSON, String, Number, Math, Date,
};
vm.createContext(context);
vm.runInContext(`class TestGateway {
  getToken(){return 'never-log-this-token';}
  get httpUrl(){return location.origin;}
  ${process.argv[1]}
}
globalThis.gateway = new TestGateway();`, context);
(async () => {
  response = new Error('network failed with never-log-this-token');
  let result = await context.gateway.httpPost('/api/jarvis/golden/panel-analysis', {symbol:'BTCUSD'});
  if (result.http_status !== null || result.error_code !== 'NETWORK_FAILURE'
      || result.failure_stage !== 'NETWORK_TRANSPORT' || result.request_id !== 'ui-request-1'
      || result.correlation_id !== 'ui-request-1') throw new Error('transport diagnostics incomplete');
  if (requests[0].options.headers.Authorization !== 'Bearer never-log-this-token'
      || !requests[0].options.headers['X-Request-ID'] || !requests[0].options.headers['X-Correlation-ID']) throw new Error('request auth/correlation headers changed');

  response = {ok:false,status:503,clone(){return {json:async()=>({code:'PROVIDER_HTTP_FAILURE_HTTP_503',request_id:'server-request',correlation_id:'server-correlation'})};},headers:{get:()=>null}};
  result = await context.gateway.httpPost('/api/jarvis/golden/panel-analysis', {});
  if (result.http_status !== 503 || result.error_code !== 'PROVIDER_HTTP_FAILURE_HTTP_503'
      || result.request_id !== 'server-request' || result.correlation_id !== 'server-correlation'
      || result.failure_stage !== 'HTTP_RESPONSE') throw new Error('HTTP diagnostics incomplete');
  const logged = JSON.stringify(logs);
  if (logged.includes('never-log-this-token') || logged.includes('network failed')) throw new Error('sensitive exception data logged');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    completed = subprocess.run(
        [node, "-e", harness, method], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

