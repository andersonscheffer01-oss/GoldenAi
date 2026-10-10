import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "jarvis_ui" / "src" / "desktop-shell.js"


def _run_dom_test(body):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível para o teste DOM mockado")
    source = SHELL.read_text(encoding="utf-8")
    start = source.index("function createAssetCatalogCombobox(host, options = {}) {")
    controller = "let assetComboboxSequence = 0;\n" + source[start:]
    harness = r"""
const vm = require('node:vm');
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.value = '';
    this.textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.parentElement = null;
    this.className = '';
    this.id = '';
  }
  append(...items) { items.forEach(item => { item.parentElement = this; }); this.children.push(...items); }
  replaceChildren(...items) { this.children.forEach(item => { item.parentElement = null; }); this.children = []; this.append(...items); }
  insertBefore(item, reference) {
    const index = this.children.indexOf(reference);
    if (index < 0) throw new Error('reference child missing');
    item.parentElement = this;
    this.children.splice(index, 0, item);
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  insertAdjacentElement(_position, item) { item.parentElement = this; this.children.push(item); }
  querySelectorAll(selector) {
    const matches = [];
    const visit = node => {
      for (const child of node.children || []) {
        if (selector === child.tagName || (selector.startsWith('[role="') && child.attributes.role === selector.slice(7, -2))) matches.push(child);
        visit(child);
      }
    };
    visit(this);
    return matches;
  }
  querySelector(selector) {
    if (selector === '[data-asset-no-results]') {
      return this.querySelectorAll('div').find(item => item.dataset?.assetNoResults !== undefined) || null;
    }
    if (selector === '[data-golden-analysis-history]') {
      return this.children.find(item => item.dataset?.goldenAnalysisHistory !== undefined) || null;
    }
    return null;
  }
  focus() { this.focused = true; }
  select() { this.selectedText = true; }
  get text() { return this.textContent + this.children.map(item => item.text || item.textContent || '').join(' '); }
}
const provenance = new Element('footer');
const view = new Element('section');
provenance.insertAdjacentElement = (_position, item) => view.children.push(item);
view.querySelector = selector => selector === '.d2AnalysisProvenance' ? provenance : null;
const document = {
  createElement: tag => new Element(tag),
  createTextNode: value => ({textContent:String(value), text:String(value)}),
};
const window = {Gateway:null};
const catalogState = {assets:[
  {provider:'MT5',provider_asset_id:'mt5:XAUUSD',provider_symbol:'XAUUSD',asset_class:'METALS',display_name:'Gold'},
  {provider:'MT5',provider_asset_id:'mt5:EURUSD',provider_symbol:'EURUSD',asset_class:'FOREX',display_name:'Euro vs US Dollar'},
  {provider:'MT5',provider_asset_id:'mt5:BTCUSD',provider_symbol:'BTCUSD',asset_class:'CRYPTO',display_name:'Bitcoin'},
],loaded:true,loading:false,status:'AVAILABLE'};
let sharedCatalogRequests = 0;
const context = {document, window, String, Number, JSON, Set, Array, RegExp, Boolean};
vm.runInNewContext(require('node:fs').readFileSync(0, 'utf8') + '; globalThis.wireGoldenAnalysisHistory = wireGoldenAnalysisHistory; globalThis.createAssetCatalogCombobox = createAssetCatalogCombobox; globalThis.appendGroupedAssetOptions = appendGroupedAssetOptions;', context);
const historyUi = context.wireGoldenAnalysisHistory(view, {
  getCatalog:() => catalogState,
  ensureCatalog:() => { sharedCatalogRequests += 1; },
  assetClassLabel:value => ({FOREX:'FOREX',METALS:'METAIS'}[value] || value),
});
const section = view.children.find(item => item.dataset?.goldenAnalysisHistory !== undefined);
if (!section) throw new Error('history section missing');
function find(node, key) {
  if (node.dataset && Object.prototype.hasOwnProperty.call(node.dataset, key)) return node;
  for (const child of node.children || []) { const found = find(child, key); if (found) return found; }
  return null;
}
function mockCombo(allowAll = false) {
  const wrapper = new Element('label');
  const host = new Element('div');
  wrapper.append(host);
  const combo = context.createAssetCatalogCombobox(host, {allowAll});
  combo.setCatalog(catalogState.assets, {selectedValue:allowAll ? '' : '', emptyLabel:'Catálogo MT5 indisponível',
    assetClassLabel:value => ({FOREX:'FOREX',METALS:'METAIS',CRYPTO:'CRIPTO'}[value] || value)});
  return {wrapper, host, combo};
}
"""
    completed = subprocess.run(
    [node, "-e", harness + body], input=controller, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_panel_and_history_mount_one_combobox_without_separate_search_or_asset_select():
    source = SHELL.read_text(encoding="utf-8")
    assert source.index("let assetComboboxSequence = 0;") < source.index("if (window.__JARVIS_DESKTOP__")
    assert '<div data-panel-asset-select></div>' in source
    assert 'const symbolHost = document.createElement("div");' in source
    assert 'createAssetCatalogCombobox(symbolHost' in source
    assert 'setAttribute("role", "combobox")' in source
    assert 'role", "listbox"' in source
    assert "attachAssetCatalogSearch" not in source
    assert "data-asset-search" not in source
    assert '<select data-panel-asset-select' not in source


def test_history_analysis_section_is_inserted_after_analysis_provenance_and_visible():
    _run_dom_test(r"""
const history = view.children.find(item => item.dataset?.goldenAnalysisHistory !== undefined);
if (!history || history.hidden || history.className !== 'd2DonorSurface d2GoldenAnalysisHistory')
  throw new Error('canonical Analysis History section missing or hidden');
if (view.children.indexOf(history) < 0) throw new Error('history not mounted in the Analysis view');
if (!find(history, 'historyConsult')) throw new Error('explicit History LIST action missing');
""")


def test_history_list_is_explicit_authenticated_filtered_paginated_and_get_recovers_result():
    _run_dom_test(r"""
const consult = find(section, 'historyConsult');
const list = find(section, 'historyList');
const symbolHost = find(section, 'historySymbol');
const symbol = historyUi.symbol;
const mode = find(section, 'historyMode');
const status = find(section, 'historyStatus');
const badge = find(section, 'historyState');
if (symbol.input.attributes.role !== 'combobox' || symbol.listbox.attributes.role !== 'listbox'
    || !symbol.listbox.children.some(item => item.textContent === 'Todos os ativos')) throw new Error('history asset combobox contract missing');
if (!symbol.listbox.querySelectorAll('[role="option"]').some(option => option.textContent === 'XAUUSD · Gold')) throw new Error('MT5 display label/catalog not reused');
if (mode.children[1].textContent !== 'Análise independente' || mode.children[2].textContent !== 'Estratégia definida') throw new Error('friendly mode labels missing');
let calls = [];
const record = {analysis_id:'panel_analysis_fixture1',symbol:'XAUUSD',timeframe:'M15',
  analysis_mode:'INDEPENDENT',status:'COMPLETE',snapshot_id:'snap-1',
  correlation_id:'corr-1',created_at:'2026-10-05T12:00:00Z'};
const analysis = {analysis_id:record.analysis_id,symbol:record.symbol,timeframe:record.timeframe,
  analysis_mode:record.analysis_mode,status:'COMPLETE',analysis_status:'COMPLETE',
  snapshot_id:record.snapshot_id,summary:'Resultado fixture',trend:'ALTA',
  execution_authority:'NONE'};
window.Gateway = {isAuthenticated:false,httpPost:async (...args) => { calls.push(args); return {}; }};
if (calls.length) throw new Error('history queried during initialization');
(async () => {
  await consult.listeners.click();
  if (calls.length || !badge.textContent.includes('AUTENTICAÇÃO')) throw new Error('unauthenticated read was not blocked');
  window.Gateway.isAuthenticated = true;
  symbol.commit('0'); mode.value = 'INDEPENDENT'; status.value = 'COMPLETE';
  const responses = [
    {ok:true,status:'AVAILABLE',data:{items:[record],total:26,limit:25,offset:0,has_more:true}},
    {ok:true,status:'AVAILABLE',data:{items:[{...record,analysis_id:'panel_analysis_fixture2'}],total:26,limit:25,offset:1,has_more:false}},
  ];
  window.Gateway.httpPost = async (path,payload) => {
    calls.push({path,payload});
    if (payload.action === 'LIST') return responses.shift();
    return {ok:true,found:true,status:'FOUND',analysis};
  };
  await consult.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  if (calls.length !== 1 || calls[0].path !== '/api/jarvis/golden/panel-analysis'
      || calls[0].payload.action !== 'LIST' || calls[0].payload.symbol !== 'XAUUSD'
      || calls[0].payload.analysis_mode !== 'INDEPENDENT' || calls[0].payload.status !== 'COMPLETE'
      || calls[0].payload.limit !== 25 || calls[0].payload.offset !== 0) throw new Error('canonical filtered LIST contract mismatch');
  const row = list.children.find(item => item.dataset?.analysisId === record.analysis_id);
  if (!row) throw new Error('list result not rendered: ' + badge.textContent + ' / ' + calls.length + ' / ' + list.children.map(item => item.text).join('|'));
  await list.listeners.click({target:{closest:() => row}});
  await new Promise(resolve => setImmediate(resolve));
  if (calls.length !== 2 || calls[1].payload.action !== 'GET'
      || calls[1].payload.analysis_id !== record.analysis_id) throw new Error('canonical GET not issued for selected row');
  const detail = find(section, 'historyDetail');
  if (detail.hidden || !detail.text.includes('Resultado fixture') || !detail.text.includes('ALTA')) throw new Error('complete result not projected');
  const next = list.children.find(item => item.tagName === 'footer').children[1].children[1];
  if (next.disabled) throw new Error('next page disabled despite has_more');
  await next.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  if (calls.length !== 3 || calls[2].payload.action !== 'LIST' || calls[2].payload.offset !== 1) throw new Error('pagination offset mismatch');
  symbol.commit('');
  if (calls.length !== 3 || list.children.length || !badge.textContent.includes('CONSULTA NECESSÁRIA')) throw new Error('asset filter change did not invalidate without querying');
  responses.push({ok:true,status:'AVAILABLE',data:{items:[],total:0,limit:25,offset:0,has_more:false}});
  await consult.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  if (calls.length !== 4 || calls[3].payload.symbol !== '') throw new Error('all-assets filter did not map to empty symbol');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_history_catalog_unavailable_and_mode_status_filter_changes_do_not_query():
    _run_dom_test(r"""
const consult = find(section, 'historyConsult');
const list = find(section, 'historyList');
const symbol = historyUi.symbol;
const mode = find(section, 'historyMode');
const status = find(section, 'historyStatus');
const badge = find(section, 'historyState');
let calls = 0;
window.Gateway = {isAuthenticated:true,httpPost:async () => { calls += 1; return {ok:true,data:{items:[],limit:25,offset:0,has_more:false}}; }};
catalogState.assets = [];
catalogState.loaded = false;
catalogState.status = 'GATEWAY INDISPONÍVEL · CATÁLOGO NÃO ATUALIZADO';
historyUi.refreshCatalog();
if (!symbol.listbox.querySelectorAll('[role="option"]').some(item => item.textContent === 'Todos os ativos')
    || !symbol.listbox.children.some(item => item.textContent === 'Catálogo MT5 indisponível')) throw new Error('unavailable catalog state missing');
const search = symbol.input;
symbol.input.listeners.focus();
if (sharedCatalogRequests !== 1 || calls !== 0) throw new Error('combobox focus did not reuse the lazy catalog action');
search.value = 'btc';
search.listeners.input();
const allAssets = symbol.listbox.querySelectorAll('[role="option"]').find(option => option.textContent === 'Todos os ativos');
if (allAssets?.hidden || !symbol.listbox.children.some(item => item.textContent === 'Catálogo MT5 indisponível')) throw new Error('all-assets/unavailable state was hidden while searching');
if (calls !== 0 || sharedCatalogRequests !== 1) throw new Error('typing triggered an additional catalog or history request');
  symbol.value = '';
  symbol.commit('');
mode.value = 'STRATEGY';
mode.listeners.change();
status.value = 'ERROR';
status.listeners.change();
  if (calls !== 0 || !badge.textContent.includes('CONSULTA NECESSÁRIA') || list.children.length) throw new Error('filter changes queried history instead of invalidating');
  (async () => {
    if (symbol.value !== '' || !symbol.listbox.children.some(item => item.textContent === 'Catálogo MT5 indisponível')) throw new Error('unavailable catalog produced a selectable fake asset');
    if (calls !== 0) throw new Error('filter changes queried the history');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_shared_asset_search_filters_locally_preserves_selection_and_supports_keyboard():
    _run_dom_test(r"""
const panel = mockCombo();
let panelChanges = 0;
panel.combo.addEventListener('change', () => { panelChanges += 1; });
panel.combo.value = '1';
panel.combo.input.listeners.focus();
if (panel.combo.listbox.hidden || panel.combo.input.attributes['aria-expanded'] !== 'true') throw new Error('focus did not open the full asset list');
panel.combo.input.value = 'XA';
panel.combo.input.listeners.input();
if (panel.combo.value !== '1' || panelChanges) throw new Error('typing changed the selected asset');
let panelOptions = panel.combo.listbox.querySelectorAll('[role="option"]');
const gold = panelOptions.find(option => option.textContent.includes('XAUUSD'));
const euro = panelOptions.find(option => option.textContent.includes('EURUSD'));
if (!gold || gold.hidden || !euro?.hidden) throw new Error('prefix search did not filter the local catalog');
panel.combo.input.value = 'no-such-asset';
panel.combo.input.listeners.input();
if (!panel.combo.listbox.querySelector('[data-asset-no-results]')?.textContent.includes('Nenhum ativo'))
  throw new Error('no-results state missing');
panel.combo.input.value = '';
panel.combo.input.listeners.input();
panel.combo.input.listeners.keydown({key:'Enter',preventDefault(){}});
if (panel.combo.value !== '1' || panelChanges) throw new Error('Enter without a highlighted option selected an asset');
panel.combo.input.value = 'dOlLaR';
panel.combo.input.listeners.input();
panelOptions = panel.combo.listbox.querySelectorAll('[role="option"]');
if (!panelOptions.find(option => option.textContent.includes('XAUUSD'))?.hidden
    || panelOptions.find(option => option.textContent.includes('EURUSD'))?.hidden)
  throw new Error('case-insensitive friendly-name search failed');
panel.combo.input.value = '';
panel.combo.input.listeners.input();
if (panel.combo.listbox.querySelectorAll('[role="option"]').some(option => option.hidden)) throw new Error('clearing search did not restore all assets');
panel.combo.input.listeners.keydown({key:'ArrowDown',preventDefault(){}});
if (!panel.combo.input.attributes['aria-activedescendant']) throw new Error('ArrowDown did not highlight an explicit option');
panel.combo.input.listeners.keydown({key:'Enter',preventDefault(){}});
if (!panel.combo.listbox.hidden || panelChanges !== 1) throw new Error('Enter did not commit the highlighted option');
panel.combo.input.listeners.click();
if (panel.combo.listbox.querySelectorAll('[role="option"]').some(option => option.hidden))
  throw new Error('click did not restore the complete asset list');
const mouseChoice = panel.combo.listbox.querySelectorAll('[role="option"]').find(option => option.textContent.includes('XAUUSD'));
mouseChoice.listeners.click();
if (panel.combo.value !== '0' || panelChanges !== 2) throw new Error('mouse selection did not commit and close the list');
panel.combo.input.value = 'BTC';
panel.combo.input.listeners.input();
panel.combo.input.listeners.keydown({key:'Escape',preventDefault(){}});
if (!panel.combo.listbox.hidden || panel.combo.value !== '0' || panel.combo.input.value !== 'XAUUSD · Gold') throw new Error('Escape did not cancel and restore the latest confirmed selection');
const historySearch = historyUi.symbol.input;
historySearch.listeners.focus();
if (sharedCatalogRequests !== 1) throw new Error('history combobox focus did not reuse the lazy catalog');
""")


def test_history_asset_search_keeps_all_assets_and_selection_without_querying():
    _run_dom_test(r"""
const symbol = historyUi.symbol;
const search = symbol.input;
let requests = 0;
window.Gateway = {isAuthenticated:true,httpPost:async () => { requests += 1; return {}; }};
symbol.value = '0';
search.value = 'btc';
search.listeners.input();
let options = symbol.listbox.querySelectorAll('[role="option"]');
const allAssets = options.find(option => option.textContent === 'Todos os ativos');
const bitcoin = options.find(option => option.textContent.includes('BTCUSD'));
const gold = options.find(option => option.textContent.includes('XAUUSD'));
if (!allAssets || allAssets.hidden || !bitcoin || bitcoin.hidden || !gold?.hidden)
  throw new Error('History BTC search or Todos os ativos preservation failed');
if (symbol.value !== '0' || requests || !find(section, 'historyState').textContent.includes('NÃO CONSULTADO'))
  throw new Error('typing altered active asset or queried/invalidated history');
search.value = 'eUrO vS';
search.listeners.input();
options = symbol.listbox.querySelectorAll('[role="option"]');
if (!options.find(option => option.textContent.includes('EURUSD'))
    || options.find(option => option.textContent.includes('EURUSD')).hidden)
  throw new Error('case-insensitive name fragment did not match');
search.value = '';
search.listeners.input();
if (symbol.listbox.querySelectorAll('[role="option"]').some(option => option.hidden))
  throw new Error('clearing History search did not restore full catalog');
if (symbol.value !== '0' || requests) throw new Error('search clear changed the selected asset or made a request');
""")


def test_error_empty_failed_and_identity_mismatch_records_are_conservative():
    _run_dom_test(r"""
const consult = find(section, 'historyConsult');
const list = find(section, 'historyList');
const badge = find(section, 'historyState');
const symbol = {analysis_id:'panel_analysis_fixture1',symbol:'XAUUSD',timeframe:'M15',
  analysis_mode:'INDEPENDENT',status:'ERROR',snapshot_id:'snap-e',correlation_id:'corr-e'};
const errorAnalysis = {...symbol,summary:'private provider response',directional_bias:'COMPRA',
  confidence:99,entry_scenario:'invented',model_error_code:'PROVIDER_HTTP_FAILURE_HTTP_503'};
let listResponse = {ok:true,data:{items:[symbol],total:1,limit:25,offset:0,has_more:false}};
let getResponse = {ok:true,found:true,status:'FOUND',analysis:errorAnalysis};
window.Gateway = {isAuthenticated:true,httpPost:async (_path,payload) =>
  payload.action === 'LIST' ? listResponse : getResponse};
(async () => {
  await consult.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  const row = list.children.find(item => item.dataset?.analysisId === symbol.analysis_id);
  await list.listeners.click({target:{closest:() => row}});
  await new Promise(resolve => setImmediate(resolve));
  const detail = find(section, 'historyDetail');
  if (!badge.textContent.includes('ANÁLISE COM ERRO')
      || !detail.text.includes('PROVIDER_HTTP_FAILURE_HTTP_503')
      || detail.text.includes('COMPRA') || detail.text.includes('99')
      || detail.text.includes('invented') || detail.text.includes('private provider')) throw new Error('ERROR record exposed analysis conclusion/body: ' + badge.textContent + ' / ' + detail.text);
  getResponse = {...getResponse,analysis:{...errorAnalysis,analysis_id:'panel_analysis_other'}};
  await list.listeners.click({target:{closest:() => row}});
  await new Promise(resolve => setImmediate(resolve));
  if (!badge.textContent.includes('IDENTIDADE DIVERGENTE')) throw new Error('mismatched GET was not rejected');
  listResponse = {ok:true,status:'EMPTY',data:{items:[],total:0,limit:25,offset:0,has_more:false}};
  await consult.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  if (!badge.textContent.includes('NENHUM REGISTRO')) throw new Error('empty result state not distinguished');
  window.Gateway.httpPost = async () => ({ok:false,http_failure:true,http_status:503,error_code:'ANALYSIS_STORE_READ_FAILED'});
  await consult.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  if (!badge.textContent.includes('FALHA DE RECUPERAÇÃO')) throw new Error('HTTP retrieval failure not distinguished');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")
