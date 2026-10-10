import test from "node:test";
import assert from "node:assert/strict";
import {
  applyTrendBatch, createTrendRequestGate, createTrendScan, failTrendBatch,
  filterTrendCatalogByClass, filterTrendItems, nextTrendBatch, pauseTrendScan,
  retryFailedTrendBatch, trendFrameMatrixValue, trendFramePresentation,
  trendTechnicalExplanation, deriveTrendHorizon,
  trendLeaders, trendScanProjection, trendScanSummary,
} from "../jarvis_ui/src/trend-ranking-state.js";

const digestFixture = async (assets) => `fixture-${assets.map((asset) => asset.provider_asset_id).join("|")}`;
const asset = (symbol) => ({ provider: "MT5", provider_asset_id: `mt5:${symbol}`,
  provider_symbol: symbol, display_symbol: symbol, display_name: `${symbol} fixture`,
  asset_class: "FOREX" });
const row = (identity, score, available = 4) => ({
  asset: identity, directional_score: score,
  trend: score >= 60 ? "ALTA FORTE" : score > 0 ? "ALTA" : score <= -60 ? "BAIXA FORTE" : "BAIXA",
  data_state: "PARTIAL_TIMEFRAMES_FRESHNESS_UNKNOWN", freshness: "UNKNOWN",
  temporal_authority: "UNKNOWN", timeframe_divergence: false,
  extended_trend_risk: "NOT_ELEVATED", alignment: { aligned: available, available },
  evaluated_timeframes: ["M1", "M5", "M15", "M30", "H1", "H4", "D1"].map((timeframe, index) => ({
    timeframe, status: index < available ? "AVAILABLE" : "INSUFFICIENT_DATA",
    candle_count: index < available ? 100 : 0, snapshot_id: index < available ? `snap-${identity.provider_symbol}-${timeframe}` : "UNKNOWN",
  })),
});

async function scanFor(count = 6) {
  return createTrendScan(Array.from({ length: count }, (_, index) => asset(`FX${index}`)),
    "scan-1", "2026-10-06T00:00:00Z", digestFixture);
}

test("freezes and hashes a deduplicated canonical universe deterministically", async () => {
  const first = await createTrendScan([asset("B"), asset("A"), asset("A"),
    { ...asset("BAD"), provider_asset_id: "other:BAD" },
    { ...asset("NOPE"), asset_class: "UNKNOWN" }], "scan-1", "now", digestFixture);
  const second = await createTrendScan([asset("A"), asset("B")], "scan-2", "now", digestFixture);
  assert.equal(first.universe_total, 2);
  assert.equal(first.universe_hash, second.universe_hash);
  assert.deepEqual(first.items.map((item) => item.asset.provider_asset_id), ["mt5:A", "mt5:B"]);
  assert.deepEqual(first.excluded_summary, {
    DUPLICATE_PROVIDER_ASSET_ID: 1, NON_CANONICAL_MT5_IDENTITY: 1, UNSUPPORTED_ASSET_CLASS: 1,
  });
  const sha = await createTrendScan([asset("EURUSD")], "scan-sha");
  assert.match(sha.universe_hash, /^[a-f0-9]{64}$/);
});

test("aggregates two bounded batches without replacing completed rows", async () => {
  const scan = await scanFor(9);
  const first = nextTrendBatch(scan);
  assert.equal(first.length, 4);
  applyTrendBatch(scan, first, first.map((item, index) => row(item.asset, [80, -90, 30, -40][index])), 0);
  const saved = scan.items[0].result;
  const second = nextTrendBatch(scan);
  assert.equal(second.length, 4);
  applyTrendBatch(scan, second, second.map((item, index) => row(item.asset, [65, -70, 28, -25][index])), 1);
  assert.equal(scan.items.length, 9);
  assert.equal(scan.items[0].result, saved);
  assert.equal(trendScanSummary(scan).pending, 1);
  assert.equal(trendScanSummary(scan).progress_percent, 88);
  assert.equal(trendScanSummary(scan).status, "RANKING PARCIAL");
});

test("up and down leaders sort independently and exclude unscored assets", async () => {
  const scan = await scanFor(4);
  const batch = nextTrendBatch(scan);
  applyTrendBatch(scan, batch, [row(batch[0].asset, 55), row(batch[1].asset, -92),
    row(batch[2].asset, 88), { ...row(batch[3].asset, null), directional_score: null,
      trend: "DADOS INSUFICIENTES", data_state: "INSUFFICIENT_DATA" }], 0);
  const leaders = trendLeaders(scan);
  assert.deepEqual(leaders.up.map((item) => item.result.directional_score), [88, 55]);
  assert.deepEqual(leaders.down.map((item) => item.result.directional_score), [-92]);
  assert.equal(scan.items[3].state, "DADOS INSUFICIENTES");
});

test("leaders include only direction-classified trends and sort by directional strength", async () => {
  const scan = await scanFor(5);
  const batch = nextTrendBatch(scan);
  const rows = [
    { ...row(batch[0].asset, 82), trend: "ALTA FORTE" },
    { ...row(batch[1].asset, -71), trend: "BAIXA" },
    { ...row(batch[2].asset, 18), trend: "LATERAL" },
    { ...row(batch[3].asset, -20), trend: "LATERAL" },
  ];
  applyTrendBatch(scan, batch.slice(0, 4), rows, 0);
  assert.deepEqual(trendLeaders(scan).up.map((item) => item.result.directional_score), [82]);
  assert.deepEqual(trendLeaders(scan).down.map((item) => item.result.directional_score), [-71]);
});

test("class filtering is local, supports the combined commodity-metal class, and preserves the source", async () => {
  const catalog = [asset("EURUSD"), { ...asset("XAUUSD"), asset_class: "METALS" },
    { ...asset("AAPL"), asset_class: "STOCKS" },
    { ...asset("OTHER1"), asset_class: "OTHER" },
    { ...asset("UNKNOWN"), asset_class: "OTHER_UNKNOWN" }];
  const original = catalog.map((item) => item.provider_asset_id);
  assert.deepEqual(filterTrendCatalogByClass(catalog, "COMMODITIES_METALS")
    .map((item) => item.provider_symbol), ["XAUUSD"]);
  assert.deepEqual(filterTrendCatalogByClass(catalog, "STOCKS")
    .map((item) => item.provider_symbol), ["AAPL"]);
  assert.deepEqual(filterTrendCatalogByClass(catalog, "OTHER_UNKNOWN")
    .map((item) => item.provider_symbol), ["OTHER1", "UNKNOWN"]);
  const activeScan = await createTrendScan(catalog, "scan-all", "now", digestFixture);
  const oldHash = activeScan.universe_hash;
  const scan = await createTrendScan(filterTrendCatalogByClass(catalog, "STOCKS"),
    "scan-stock", "now", digestFixture);
  assert.deepEqual(scan.items.map((item) => item.asset.provider_symbol), ["AAPL"]);
  assert.deepEqual(catalog.map((item) => item.provider_asset_id), original);
  assert.equal(scan.universe_total, 1);
  assert.equal(activeScan.items.length, 5);
  assert.equal(activeScan.universe_hash, oldHash);
});

test("failed batch preserves prior evidence and permits a manual retry without duplicates", async () => {
  const scan = await scanFor(6);
  const first = nextTrendBatch(scan);
  applyTrendBatch(scan, first.slice(0, 2), first.slice(0, 2).map((item, index) => row(item.asset, 30 + index)), 0);
  failTrendBatch(scan, first.slice(2), "HTTP_503", 1);
  assert.equal(trendScanSummary(scan).evaluated, 2);
  assert.equal(trendScanSummary(scan).failed, 2);
  assert.equal(trendScanSummary(scan).pending, 2);
  assert.equal(trendScanSummary(scan).invariant_holds, true);
  const retry = retryFailedTrendBatch(scan);
  assert.equal(retry.length, 2);
  applyTrendBatch(scan, retry, retry.map((item, index) => row(item.asset, 45 + index)), 2);
  assert.equal(scan.items.length, 6);
  assert.equal(new Set(scan.items.map((item) => item.asset.provider_asset_id)).size, 6);
  assert.equal(trendScanSummary(scan).status, "RANKING PARCIAL");
});

test("insufficient coverage never becomes a strong direction and completion is exact", async () => {
  const scan = await scanFor(1);
  const [item] = nextTrendBatch(scan);
  const weakCoverage = row(item.asset, null, 2);
  weakCoverage.directional_score = null;
  weakCoverage.trend = "DADOS INSUFICIENTES";
  weakCoverage.data_state = "INSUFFICIENT_DATA";
  applyTrendBatch(scan, [item], [weakCoverage], 0);
  const summary = trendScanSummary(scan);
  assert.equal(item.state, "DADOS INSUFICIENTES");
  assert.equal(summary.progress_percent, 100);
  assert.equal(summary.status, "RANKING COMPLETO");
  assert.equal(summary.terminal + summary.pending, summary.total);
});

test("manual pause/resume and request gate prevent concurrent batches", async () => {
  const scan = await scanFor(5);
  assert.equal(pauseTrendScan(scan).status, "RANKING PARCIAL · PAUSADO");
  const gate = createTrendRequestGate();
  assert.equal(gate.acquire(), true);
  assert.equal(gate.acquire(), false);
  gate.release();
  assert.equal(gate.acquire(), true);
  gate.release();
});

test("a terminal failed batch is complete-with-failures, never a clean completion", async () => {
  const scan = await scanFor(2);
  const batch = nextTrendBatch(scan);
  failTrendBatch(scan, batch, "SOURCE_TIMEOUT", 0);
  const summary = trendScanSummary(scan);
  assert.equal(summary.pending, 0);
  assert.equal(summary.failed, 2);
  assert.equal(summary.progress_percent, 100);
  assert.equal(summary.status, "COMPLETO COM FALHAS");
  assert.equal(summary.invariant_holds, true);
});

test("sanitized per-asset read errors remain failed, not insufficient or scored", async () => {
  const scan = await scanFor(1);
  const [item] = nextTrendBatch(scan);
  const faulty = row(item.asset, 75);
  faulty.read_errors = [{ timeframe: "H1", error_code: "RuntimeError" }];
  applyTrendBatch(scan, [item], [faulty], 0);
  assert.equal(item.state, "FALHO");
  assert.equal(item.error, "RuntimeError");
  assert.equal(trendLeaders(scan).up.length, 0);
});

function frame(timeframe, score, status = "AVAILABLE") {
  const classification = status !== "AVAILABLE" ? undefined
    : score >= 60 ? "ALTA FORTE" : score >= 25 ? "ALTA"
      : score <= -60 ? "BAIXA FORTE" : score <= -25 ? "BAIXA" : "LATERAL";
  return { timeframe, status, directional_score: status === "AVAILABLE" ? score : undefined,
    trend_classification: classification };
}

test("timeframe cells derive only from canonical frame evidence and preserve unknown", () => {
  const result = { evaluated_timeframes: [frame("M1", 72), frame("M5", -30),
    frame("M15", 0), frame("M30", 0, "INSUFFICIENT_DATA")] };
  assert.equal(trendFrameMatrixValue(result, "M1"), "ALTA FORTE");
  assert.equal(trendFrameMatrixValue(result, "M5"), "BAIXA");
  assert.equal(trendFrameMatrixValue(result, "M15"), "LATERAL");
  assert.equal(trendFrameMatrixValue(result, "M30"), "INSUFICIENTE");
  assert.equal(trendFrameMatrixValue(result, "H1"), "UNKNOWN");
  assert.equal(trendFrameMatrixValue({ evaluated_timeframes: [frame("H1", 20, "STALE")] }, "H1"), "UNKNOWN");
});

test("timeframe presentation uses the delivered score without changing classification or results", () => {
  const result = { directional_score: 17, evaluated_timeframes: [
    frame("M1", 60), frame("M5", 25), frame("M15", 24), frame("M30", -24),
    frame("H1", -25), frame("H4", -60), frame("D1", 0, "INSUFFICIENT_DATA"),
  ] };
  const before = structuredClone(result);
  const expected = ["ALTA FORTE +60", "ALTA +25", "LATERAL +24", "LATERAL -24",
    "BAIXA -25", "BAIXA FORTE -60", "INSUFICIENTE"];
  assert.deepEqual(["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    .map((timeframe) => trendFramePresentation(result, timeframe).label), expected);
  assert.deepEqual(trendFramePresentation(result, "H1"),
    { classification: "BAIXA", score: -25, label: "BAIXA -25" });
  assert.deepEqual(trendFramePresentation(result, "D1"),
    { classification: "INSUFICIENTE", score: null, label: "INSUFICIENTE" });
  assert.deepEqual(trendFramePresentation(result, "W1"),
    { classification: "UNKNOWN", score: null, label: "UNKNOWN" });
  assert.equal(result.directional_score, 17);
  assert.deepEqual(result, before);
});

test("technical explanation is deterministic, evidence-only, and does not mutate horizons", () => {
  const result = { evaluated_timeframes: [frame("M1", 62), frame("M5", 62),
    frame("M15", 37), frame("H1", -35), frame("H4", -65), frame("D1", -65)],
    timeframe_divergence: true, extended_trend_risk: "ELEVATED" };
  const before = ["SCALP", "DAY", "SWING"].map((horizon) => deriveTrendHorizon(result, horizon));
  const explanation = trendTechnicalExplanation(result);
  assert.match(explanation, /Curto prazo em alta; períodos superiores em baixa/);
  assert.match(explanation, /Extensão elevada/);
  assert.doesNotMatch(explanation, /COMPRAR|VENDER|ENTRAR|PROBABILIDADE|CHANCE/i);
  assert.deepEqual(["SCALP", "DAY", "SWING"].map((horizon) => deriveTrendHorizon(result, horizon)), before);
  assert.match(trendTechnicalExplanation({ evaluated_timeframes: [] }), /Dados insuficientes/);
  const lateral = { evaluated_timeframes: ["M1", "M5", "M15", "H1", "H4", "D1"]
    .map((timeframe) => frame(timeframe, 5)) };
  assert.match(trendTechnicalExplanation(lateral), /Predomínio lateral/);
});

test("scalp, day, and swing use only their defined frames and require complete directional evidence", () => {
  const result = { evaluated_timeframes: [frame("M1", 75), frame("M5", 62),
    frame("M15", -30), frame("M30", 0), frame("H1", 30),
    frame("H4", 70), frame("D1", 65)] };
  assert.equal(deriveTrendHorizon(result, "SCALP"), "ALTA FORTE");
  assert.equal(deriveTrendHorizon(result, "DAY"), "DIVERGENTE");
  assert.equal(deriveTrendHorizon(result, "SWING"), "ALTA");
  result.evaluated_timeframes = result.evaluated_timeframes.filter((item) => item.timeframe !== "M1");
  assert.equal(deriveTrendHorizon(result, "SCALP"), "DADOS INSUFICIENTES");
});

test("matrix filters are local projections over accumulated scan rows", async () => {
  const scan = await scanFor(4);
  applyTrendBatch(scan, nextTrendBatch(scan), [
    { ...row(scan.items[0].asset, 70), trend: "ALTA FORTE" },
    { ...row(scan.items[1].asset, -50), trend: "BAIXA" },
    { ...row(scan.items[2].asset, 0), trend: "LATERAL" },
    { ...row(scan.items[3].asset, null), trend: "DADOS INSUFICIENTES", directional_score: null },
  ], 0);
  scan.items[3].state = "DADOS INSUFICIENTES";
  scan.items[2].asset.asset_class = "METALS";
  const before = scan.items.slice();
  assert.deepEqual(filterTrendItems(scan, { assetClass: "METALS", trend: "LATERAL" }), [scan.items[2]]);
  assert.deepEqual(filterTrendItems(scan, { state: "INSUFFICIENT" }), [scan.items[3]]);
  assert.deepEqual(filterTrendItems(scan, { trend: "BAIXA" }), [scan.items[1]]);
  assert.equal(filterTrendItems(scan).length, 4);
  assert.deepEqual(scan.items, before);
});

test("Panel and market page navigation project the same scan without resetting its rows", async () => {
  const scan = await scanFor(5);
  applyTrendBatch(scan, nextTrendBatch(scan).slice(0, 4), [
    row(scan.items[0].asset, 80), row(scan.items[1].asset, -75),
    row(scan.items[2].asset, 35), row(scan.items[3].asset, -30),
  ], 0);
  const originalRows = scan.items;
  const views = ["painel", "inteligencia-mercado", "painel", "inteligencia-mercado"];
  const projections = views.map(() => trendScanProjection(scan));
  assert.deepEqual(projections.map((item) => item.scan_id), Array(4).fill("scan-1"));
  assert.ok(projections.every((item) => item.items === originalRows));
  assert.deepEqual(projections.map((item) => item.summary.evaluated), [4, 4, 4, 4]);
  assert.deepEqual(projections[0].leaders.up, projections[3].leaders.up);
  assert.equal(scan.items.length, 5);
  assert.equal(scan.items[4].state, "PENDENTE");
});
