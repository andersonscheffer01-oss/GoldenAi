import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as ranking from "../jarvis_ui/src/trend-ranking-state.js";

const shell = readFileSync(new URL("../jarvis_ui/src/desktop-shell.js", import.meta.url), "utf8");
const begin = shell.indexOf("  const marketView = document.querySelector(\".d2MarketIntelligenceView\");");
const end = shell.indexOf("  if (selectedPanelAsset) {", begin);
assert.ok(begin >= 0 && end > begin, "real Desktop ranking handler must be present");
const handlerSource = shell.slice(begin, end);

class Element {
  constructor(value = "") {
    this.value = value;
    this.textContent = "";
    this.disabled = false;
    this.hidden = false;
    this.children = [];
    this.listeners = new Map();
    this.style = { setProperty() {} };
    this.dataset = {};
  }
  querySelector(selector) { return this.nodes?.get(selector) || null; }
  addEventListener(type, listener) {
    this.listeners.set(type, [...(this.listeners.get(type) || []), listener]);
  }
  click() {
    if (!this.disabled) for (const listener of this.listeners.get("click") || []) listener({ target: this });
  }
  replaceChildren(...nodes) { this.children = nodes; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute() {}
}

const symbols = Array.from({ length: 6 }, (_, index) => ({
  provider: "MT5", provider_asset_id: `mt5:FX${index}`, provider_symbol: `FX${index}`,
  display_symbol: `FX${index}`, display_name: `Forex ${index}`, asset_class: "FOREX",
}));
const resultFor = (asset) => ({
  asset, directional_score: 28, trend: "ALTA", data_state: "AVAILABLE_FRESHNESS_UNKNOWN",
  alignment: { aligned: 7, available: 7 }, freshness: "UNKNOWN", absolute_utc_verified: "UNKNOWN",
  evaluated_timeframes: ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    .map((timeframe) => ({ timeframe, status: "AVAILABLE", directional_score: 28,
      trend_classification: "ALTA" })),
});
const tick = () => new Promise((resolve) => setImmediate(resolve));
async function until(predicate) {
  const deadline = Date.now() + 2000;
  while (!predicate() && Date.now() < deadline) await tick();
  assert.ok(predicate(), "expected mocked handler to advance");
}

function mount(post, catalog = symbols, options = {}) {
  const selectors = ["rows", "status", "batch", "next", "progress", "up", "down", "retry",
    "pause", "excluded", "excluded-details", "excluded-list", "previous", "more",
    "run", "class-select", "market-filter-class", "market-filter-trend", "market-filter-state",
    "market-ranking-counts"];
  const nodes = new Map(selectors.map((name) => [`[data-trend-ranking-${name}]`, new Element()]));
  nodes.set("[data-trend-class-select]", new Element("FOREX"));
  for (const name of ["market-filter-class", "market-filter-trend", "market-filter-state"])
    nodes.set(`[data-${name}]`, new Element("ALL"));
  nodes.set("[data-market-ranking-counts]", new Element());
  nodes.set("[data-trend-scan-persistence]", new Element());
  nodes.set("[data-trend-scan-recover]", new Element());
  const detail = new Element();
  detail.hidden = true;
  detail.nodes = new Map(["title", "body", "close"].map((name) =>
    [`[data-market-asset-detail-${name}]`, new Element()]));
  nodes.set("[data-market-asset-detail]", detail);
  const market = new Element();
  nodes.set("[data-trend-ranking]", { querySelector: (selector) => nodes.get(selector) || null });
  market.nodes = nodes;
  const panelNodes = new Map(["status", "progress", "up", "down"].map((name) =>
    [`[data-panel-trend-${name}]`, new Element()]));
  const panel = { querySelector: (selector) => panelNodes.get(selector) || null };
  const document = {
    querySelector: (selector) => selector === ".d2MarketIntelligenceView" ? market : null,
    createElement: () => new Element(),
  };
  const window = { Gateway: { isAuthenticated: true, httpPost: (path, body) => {
    if (path === "/api/jarvis/golden/trend-scan") {
      if (body.action === "RECOVER") return options.recover || { ok: true, found: false };
      if (body.action === "APPLY_BATCH_RESULTS") return { ok: true, persisted: true,
        scan_id: body.scan_id, revision: body.base_revision + 1,
        updated_at: "2026-10-07T12:00:00Z" };
      if (options.save) return options.save(body);
      return { ok: true, persisted: true, scan_id: body.scan.scan_id,
        revision: body.base_revision + 1, updated_at: "2026-10-07T12:00:00Z" };
    }
    return post(path, body);
  } }, confirm: () => true };
  const bindings = Object.keys(ranking);
  const setup = new Function(...bindings, "document", "window", "panel", "catalog", `
    let trendScan = null;
    let trendScanRevision = 0;
    let trendScanPersisted = false;
    let trendScanRecoveryChecked = false;
    let trendScanRecoveryBusy = false;
    let trendScanSavedAt = "";
    let trendRankingBusy = false;
    let trendScanStarting = false;
    let trendRankingPage = 0;
    let trendRankingRequestId = 0;
    const trendRankingGate = createTrendRequestGate();
    let discoveredAssets = catalog;
    let catalogLoaded = true;
    let catalogLoadedAt = Date.now();
    let panelDiscoveryRunning = false;
    const assetSearchStatus = null;
    const catalogObservation = "fixture";
    const searchPanelAssets = () => { throw Error("unexpected discovery"); };
    const assetClassLabel = (value) => value;
    ${handlerSource}
    return { get scan() { return trendScan; },
      get persisted() { return trendScanPersisted; }, renderTrendRanking };
  `);
  const mounted = setup(...bindings.map((name) => ranking[name]), document, window, panel, catalog);
  return { get scan() { return mounted.scan; }, get persisted() { return mounted.persisted; },
    renderTrendRanking: mounted.renderTrendRanking,
    nodes, panelNodes, detail };
}

function contents(element) {
  return [element.textContent, ...element.children.map(contents)].join(" ");
}

test("Market Intelligence FOREX click creates one bounded first batch and continues only on next click", async () => {
  const requests = [];
  let releaseFirst;
  const firstRequest = new Promise((resolve) => { releaseFirst = resolve; });
  const ui = mount(async (_url, body) => {
    requests.push(body);
    if (requests.length === 1) await firstRequest;
    return { ok: true, data: { ranked_assets: body.assets.map(resultFor) } };
  });
  ui.renderTrendRanking();
  assert.equal(requests.length, 0, "opening and rendering must not query");
  ui.nodes.get("[data-market-filter-trend]").value = "ALTA";
  for (const listener of ui.nodes.get("[data-market-filter-trend]").listeners.get("change") || []) listener();
  assert.equal(requests.length, 0, "local filters must not query");
  const run = ui.nodes.get("[data-trend-ranking-run]");
  assert.equal(run.listeners.get("click")?.length, 1);
  run.click();
  assert.equal(run.disabled, true);
  assert.match(ui.nodes.get("[data-trend-ranking-status]").textContent, /PREPARANDO VARREDURA/);
  run.click();
  await until(() => requests.length === 1);
  assert.equal(requests[0].asset_class_filter, "FOREX");
  assert.ok(requests[0].scan_id);
  assert.ok(requests[0].assets.length >= 1 && requests[0].assets.length <= 4);
  assert.equal(requests.length, 1);
  releaseFirst();
  await until(() => ui.scan?.items.filter((item) => item.state === "AVALIADO").length === 4);
  assert.equal(ui.scan.scan_id, requests[0].scan_id);
  assert.match(ui.nodes.get("[data-market-ranking-counts]").textContent, /RANKING PARCIAL/);
  assert.match(ui.nodes.get("[data-trend-ranking-batch]").textContent, /RANKING PARCIAL/);
  assert.match(contents(ui.nodes.get("[data-trend-ranking-up]")), /FX0/);
  assert.equal(ui.nodes.get("[data-trend-ranking-rows]").children.length > 0, true);
  ui.nodes.get("[data-trend-ranking-next]").click();
  await until(() => requests.length === 2);
  assert.equal(requests[1].scan_id, requests[0].scan_id);
  assert.equal(requests[1].assets.length, 2);
});

test("ranking HTTP failure is sanitized and does not silently clear the message", async () => {
  const ui = mount(async () => { throw new Error("private-path-and-token-must-not-appear"); });
  ui.nodes.get("[data-trend-ranking-run]").click();
  await until(() => ui.nodes.get("[data-trend-ranking-status]").textContent.includes("RANKING_REQUEST_FAILED"));
  const message = ui.nodes.get("[data-trend-ranking-status]").textContent;
  assert.doesNotMatch(message, /private-path|token/);
  assert.equal(ui.nodes.get("[data-trend-ranking-run]").disabled, false);
  assert.equal(ui.scan?.items.slice(0, 4).every((item) => item.state === "FALHO"), true);
});

test("evaluated row detail, close, filters and local pages never query or mutate the scan", async () => {
  const catalog = Array.from({ length: 45 }, (_, index) => ({ ...symbols[0],
    provider_asset_id: `mt5:FX${index}`, provider_symbol: `FX${index}`,
    display_symbol: `FX${index}` }));
  const requests = [];
  const ui = mount(async (_url, body) => {
    requests.push(body);
    return { ok: true, data: { ranked_assets: body.assets.map(resultFor) } };
  }, catalog);
  ui.nodes.get("[data-trend-ranking-run]").click();
  await until(() => ui.scan?.items.filter((item) => item.state === "AVALIADO").length === 4);
  const body = ui.nodes.get("[data-trend-ranking-rows]");
  assert.equal(body.children.length, 40);
  const scanBefore = structuredClone(ui.scan);
  const row = body.children.find((child) => child.dataset.trendAssetId);
  assert.equal(row.children[1].textContent, "ALTA +28");
  assert.equal(row.children[1].dataset.trendValue, "ALTA");
  for (const listener of body.listeners.get("click") || [])
    listener({ target: { closest: () => row } });
  assert.equal(ui.detail.hidden, false);
  assert.match(contents(ui.detail.nodes.get("[data-market-asset-detail-body]")), /ALTA \+28/);
  assert.match(contents(ui.detail.nodes.get("[data-market-asset-detail-body]")), /SCALP/);
  assert.equal(requests.length, 1);
  ui.detail.nodes.get("[data-market-asset-detail-close]").click();
  assert.equal(ui.detail.hidden, true);
  const another = body.children.find((child) => child.dataset.trendAssetId
    && child.dataset.trendAssetId !== row.dataset.trendAssetId);
  for (const listener of body.listeners.get("click") || [])
    listener({ target: { closest: () => another } });
  assert.equal(ui.detail.hidden, false);
  const filter = ui.nodes.get("[data-market-filter-trend]");
  filter.value = "BAIXA";
  for (const listener of filter.listeners.get("change") || []) listener();
  assert.equal(ui.detail.hidden, true);
  filter.value = "ALL";
  for (const listener of filter.listeners.get("change") || []) listener();
  for (const name of ["class", "state"]) {
    const localFilter = ui.nodes.get(`[data-market-filter-${name}]`);
    localFilter.value = name === "class" ? "FOREX" : "EVALUATED";
    for (const listener of localFilter.listeners.get("change") || []) listener();
    localFilter.value = "ALL";
    for (const listener of localFilter.listeners.get("change") || []) listener();
  }
  ui.nodes.get("[data-trend-ranking-more]").click();
  assert.equal(body.children.length, 5);
  assert.equal(requests.length, 1);
  assert.deepEqual(ui.scan, scanBefore);
});

test("matrix does not invent scores for unknown or insufficient frames", async () => {
  const ui = mount(async (_url, body) => ({ ok: true, data: { ranked_assets: body.assets.map((asset) => {
    const result = resultFor(asset);
    result.evaluated_timeframes[0] = { timeframe: "M1", status: "STALE", directional_score: 77 };
    result.evaluated_timeframes[1] = { timeframe: "M5", status: "INSUFFICIENT_DATA" };
    return result;
  }) } }));
  ui.nodes.get("[data-trend-ranking-run]").click();
  await until(() => ui.scan?.items.filter((item) => item.state === "AVALIADO").length === 4);
  const row = ui.nodes.get("[data-trend-ranking-rows]").children[0];
  assert.equal(row.children[1].textContent, "UNKNOWN");
  assert.equal(row.children[2].textContent, "INSUFICIENTE");
  assert.equal(row.children[3].textContent, "ALTA +28");
});

test("authenticated recovery restores 4/79 without discovery, MT5 ranking, or automatic next batch", async () => {
  const catalog = Array.from({ length: 79 }, (_, index) => ({ ...symbols[0],
    provider_asset_id: `mt5:FX${String(index).padStart(3, "0")}`,
    provider_symbol: `FX${String(index).padStart(3, "0")}` }));
  const scan = await ranking.createTrendScan(catalog, globalThis.crypto.randomUUID());
  scan.contract_version = "trend-scan-v1";
  scan.asset_class_filter = "FOREX";
  ranking.applyTrendBatch(scan, ranking.nextTrendBatch(scan),
    scan.items.slice(0, 4).map((item) => resultFor(item.asset)), 0);
  const requests = [];
  const ui = mount(async (path) => { requests.push(path); throw Error("unexpected MT5 read"); },
    catalog, { recover: { ok: true, found: true,
      data: { scan, revision: 2, updated_at: "2026-10-07T12:00:00Z" } } });
  ui.nodes.get("[data-trend-scan-recover]").click();
  await until(() => ui.scan?.items.length === 79);
  assert.equal(ui.scan.scan_id, scan.scan_id);
  assert.equal(ranking.trendScanSummary(ui.scan).evaluated, 4);
  assert.equal(ranking.trendScanSummary(ui.scan).pending, 75);
  assert.equal(ui.persisted, true);
  assert.equal(requests.length, 0);
  assert.match(ui.nodes.get("[data-trend-ranking-status]").textContent, /VARREDURA RECUPERADA/);
  assert.match(ui.nodes.get("[data-trend-scan-persistence]").textContent, /dados históricos não são dados atuais/);
});

test("failed Core save cannot start ranking or claim durable progress", async () => {
  let rankingCalls = 0;
  const ui = mount(async () => { rankingCalls += 1; return { ok: false }; }, symbols,
    { save: () => ({ ok: false, error_code: "SCAN_STORE_FAILED" }) });
  ui.nodes.get("[data-trend-ranking-run]").click();
  await until(() => ui.nodes.get("[data-trend-ranking-status]").textContent.includes("SCAN_STORE_FAILED"));
  assert.equal(rankingCalls, 0);
  assert.equal(ui.scan, null);
  assert.equal(ui.persisted, false);
});
