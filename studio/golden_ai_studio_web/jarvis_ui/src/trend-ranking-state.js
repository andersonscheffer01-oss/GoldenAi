const MAX_BATCH_SIZE = 4;
const ALLOWED_CLASSES = new Set(["FOREX", "METALS", "CRYPTO", "INDICES", "COMMODITIES",
  "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"]);
const TERMINAL_STATES = new Set(["AVALIADO", "DADOS INSUFICIENTES", "INDISPONÍVEL", "FALHO"]);

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function filterTrendCatalogByClass(catalog, assetClass = "ALL") {
  const selected = String(assetClass || "ALL").trim().toUpperCase();
  return (Array.isArray(catalog) ? catalog : []).filter((asset) => {
    const kind = String(asset?.asset_class || "").trim().toUpperCase();
    if (selected === "ALL") return true;
    if (selected === "COMMODITIES_METALS") return kind === "COMMODITIES" || kind === "METALS";
    if (selected === "OTHER_UNKNOWN") return kind === "OTHER" || kind === "OTHER_UNKNOWN";
    return kind === selected;
  });
}

async function digestUniverse(assets) {
  if (!globalThis.crypto?.subtle || typeof TextEncoder === "undefined") {
    throw new Error("UNIVERSE_SHA256_UNAVAILABLE");
  }
  const canonical = assets.map(({ provider_asset_id, provider_symbol, asset_class }) =>
    `${provider_asset_id}\u0000${provider_symbol}\u0000${asset_class}`).join("\n");
  const bytes = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function createTrendScan(catalog, scanId, createdAt = new Date().toISOString(),
                                     digest = digestUniverse) {
  const accepted = new Map();
  const excluded = [];
  for (const source of Array.isArray(catalog) ? catalog : []) {
    const asset = source && typeof source === "object" ? source : {};
    const provider = String(asset.provider || "").trim().toUpperCase();
    const providerSymbol = String(asset.provider_symbol || "").trim();
    const assetId = String(asset.provider_asset_id || "").trim();
    const assetClass = String(asset.asset_class || "").trim().toUpperCase();
    let reason = "";
    if (provider !== "MT5" || !providerSymbol || assetId !== `mt5:${providerSymbol}`) {
      reason = "NON_CANONICAL_MT5_IDENTITY";
    } else if (!ALLOWED_CLASSES.has(assetClass)) {
      reason = "UNSUPPORTED_ASSET_CLASS";
    } else if (accepted.has(assetId)) {
      reason = "DUPLICATE_PROVIDER_ASSET_ID";
    }
    if (reason) {
      excluded.push({ provider_asset_id: assetId || "UNKNOWN", reason });
      continue;
    }
    accepted.set(assetId, {
      provider, provider_asset_id: assetId, provider_symbol: providerSymbol,
      display_symbol: String(asset.display_symbol || providerSymbol).slice(0, 64),
      display_name: String(asset.display_name || providerSymbol).slice(0, 120),
      asset_class: assetClass,
      asset_class_source: String(asset.asset_class_source || "UNKNOWN").slice(0, 48),
    });
  }
  const assets = [...accepted.values()].sort((left, right) =>
    compareText(left.provider_asset_id, right.provider_asset_id));
  if (!assets.length) throw new Error("NO_ELIGIBLE_MT5_ASSETS");
  const excluded_summary = excluded.reduce((summary, item) => {
    summary[item.reason] = (summary[item.reason] || 0) + 1;
    return summary;
  }, {});
  return {
    scan_id: String(scanId), universe_hash: await digest(assets),
    created_at: String(createdAt), universe_total: assets.length,
    excluded, excluded_summary, next_batch_index: 0, paused: false,
    items: assets.map((asset) => ({ asset, state: "PENDENTE", result: null,
      error: "", retry_count: 0, batch_index: null })),
  };
}

export function trendScanSummary(scan) {
  const counts = { evaluated: 0, insufficient: 0, unavailable: 0, failed: 0, pending: 0 };
  for (const item of scan?.items || []) {
    if (item.state === "AVALIADO") counts.evaluated += 1;
    else if (item.state === "DADOS INSUFICIENTES") counts.insufficient += 1;
    else if (item.state === "INDISPONÍVEL") counts.unavailable += 1;
    else if (item.state === "FALHO") counts.failed += 1;
    else counts.pending += 1;
  }
  const terminal = counts.evaluated + counts.insufficient + counts.unavailable + counts.failed;
  const status = counts.pending ? "RANKING PARCIAL"
    : counts.failed ? "COMPLETO COM FALHAS" : "RANKING COMPLETO";
  return {
    ...counts, sufficient: counts.evaluated, terminal,
    total: scan?.universe_total || 0,
    progress_percent: scan?.universe_total
      ? Math.floor((terminal / scan.universe_total) * 100) : 0,
    status: scan?.paused && counts.pending ? "RANKING PARCIAL · PAUSADO" : status,
    invariant_holds: terminal + counts.pending === (scan?.universe_total || 0),
  };
}

export function nextTrendBatch(scan, { failedOnly = false } = {}) {
  const wanted = failedOnly ? "FALHO" : "PENDENTE";
  return (scan?.items || []).filter((item) => item.state === wanted).slice(0, MAX_BATCH_SIZE);
}

export function applyTrendBatch(scan, batch, rows, batchIndex) {
  const byId = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const id = String(row?.asset?.provider_asset_id || "");
    if (id && !byId.has(id)) byId.set(id, row);
  }
  for (const item of batch) {
    const row = byId.get(item.asset.provider_asset_id);
    item.batch_index = batchIndex;
    item.error = "";
    if (!row || row.asset?.provider_symbol !== item.asset.provider_symbol
      || row.asset?.asset_class !== item.asset.asset_class) {
      item.state = "FALHO";
      item.error = row ? "RESULT_IDENTITY_MISMATCH" : "RESULT_MISSING";
      item.result = null;
      continue;
    }
    item.result = row;
    if (Array.isArray(row.read_errors) && row.read_errors.length) {
      item.state = "FALHO";
      item.error = String(row.read_errors[0]?.error_code || "SNAPSHOT_READ_FAILED").slice(0, 80);
      continue;
    }
    const frames = Array.isArray(row.evaluated_timeframes) ? row.evaluated_timeframes : [];
    const available = frames.filter((frame) => frame.status === "AVAILABLE").length;
    if (Number.isFinite(row.directional_score) && available >= 3
      && row.data_state !== "INSUFFICIENT_DATA") {
      item.state = "AVALIADO";
    } else if (frames.length && frames.every((frame) =>
      ["SOURCE_UNAVAILABLE", "SOURCE_DISABLED"].includes(frame.status))) {
      item.state = "INDISPONÍVEL";
    } else if (row.status === "SOURCE_UNAVAILABLE" && !available) {
      item.state = "INDISPONÍVEL";
    } else {
      item.state = "DADOS INSUFICIENTES";
    }
  }
  scan.next_batch_index = Math.max(scan.next_batch_index || 0, batchIndex + 1);
  scan.paused = false;
  return trendScanSummary(scan);
}

export function failTrendBatch(scan, batch, errorCode, batchIndex) {
  const safeCode = String(errorCode || "RANKING_REQUEST_FAILED")
    .replace(/[^A-Z0-9_.-]/gi, "_").slice(0, 80);
  for (const item of batch) {
    item.state = "FALHO";
    item.error = safeCode;
    item.batch_index = batchIndex;
    item.result = null;
  }
  scan.next_batch_index = Math.max(scan.next_batch_index || 0, batchIndex + 1);
  return trendScanSummary(scan);
}

export function retryFailedTrendBatch(scan) {
  const batch = nextTrendBatch(scan, { failedOnly: true });
  for (const item of batch) {
    item.state = "PENDENTE";
    item.error = "";
    item.result = null;
    item.retry_count += 1;
  }
  scan.paused = false;
  return batch;
}

export function pauseTrendScan(scan) {
  if (scan && trendScanSummary(scan).pending) scan.paused = true;
  return trendScanSummary(scan);
}

export function createTrendRequestGate() {
  let locked = false;
  return {
    acquire() {
      if (locked) return false;
      locked = true;
      return true;
    },
    release() { locked = false; },
    get locked() { return locked; },
  };
}

export function trendLeaders(scan) {
  const scored = (scan?.items || []).filter((item) => item.state === "AVALIADO"
    && Number.isFinite(item.result?.directional_score));
  const up = scored.filter((item) => ["ALTA", "ALTA FORTE"].includes(item.result?.trend)
    && item.result.directional_score > 0)
    .sort((a, b) => b.result.directional_score - a.result.directional_score);
  const down = scored.filter((item) => ["BAIXA", "BAIXA FORTE"].includes(item.result?.trend)
    && item.result.directional_score < 0)
    .sort((a, b) => a.result.directional_score - b.result.directional_score);
  return { up, down };
}

export function trendScanProjection(scan) {
  return { scan_id: scan?.scan_id || null, items: scan?.items || [],
    summary: trendScanSummary(scan), leaders: trendLeaders(scan) };
}

const TREND_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
const HORIZON_TIMEFRAMES = Object.freeze({
  SCALP: ["M1", "M5"],
  DAY: ["M5", "M15", "H1"],
  SWING: ["H1", "H4", "D1"],
});
const UP_TRENDS = new Set(["ALTA FORTE", "ALTA"]);
const DOWN_TRENDS = new Set(["BAIXA FORTE", "BAIXA"]);
const FRAME_TRENDS = new Set(["ALTA FORTE", "ALTA", "LATERAL", "BAIXA", "BAIXA FORTE"]);

export function trendFrameMatrixValue(result, timeframe) {
  const frame = (result?.evaluated_timeframes || []).find((item) => item.timeframe === timeframe);
  if (!frame) return "UNKNOWN";
  if (frame.status === "INSUFFICIENT_DATA") return "INSUFICIENTE";
  if (frame.status !== "AVAILABLE") return "UNKNOWN";
  const value = String(frame.trend_classification || "UNKNOWN").toUpperCase();
  return FRAME_TRENDS.has(value) ? value : "UNKNOWN";
}

export function trendFramePresentation(result, timeframe) {
  const classification = trendFrameMatrixValue(result, timeframe);
  const frames = Array.isArray(result?.evaluated_timeframes) ? result.evaluated_timeframes : [];
  const frame = frames.find((item) => item.timeframe === timeframe);
  const score = FRAME_TRENDS.has(classification) && Number.isFinite(frame?.directional_score)
    ? frame.directional_score : null;
  return { classification, score,
    label: score === null ? classification : `${classification} ${score > 0 ? "+" : ""}${score}` };
}

export function deriveTrendHorizon(result, horizon) {
  const timeframes = HORIZON_TIMEFRAMES[horizon];
  if (!timeframes) return "DADOS INSUFICIENTES";
  const values = timeframes.map((timeframe) => trendFrameMatrixValue(result, timeframe));
  if (values.some((value) => !FRAME_TRENDS.has(value))) return "DADOS INSUFICIENTES";
  const directions = new Set(values.map((value) => UP_TRENDS.has(value) ? "UP"
    : DOWN_TRENDS.has(value) ? "DOWN" : "FLAT"));
  if (directions.size > 1) return "DIVERGENTE";
  if (directions.has("FLAT")) return "LATERAL";
  const strong = values.every((value) => value.endsWith("FORTE"));
  return directions.has("UP") ? (strong ? "ALTA FORTE" : "ALTA")
    : (strong ? "BAIXA FORTE" : "BAIXA");
}

export function trendTechnicalExplanation(result) {
  const scalp = deriveTrendHorizon(result, "SCALP");
  const day = deriveTrendHorizon(result, "DAY");
  const swing = deriveTrendHorizon(result, "SWING");
  const direction = (value) => UP_TRENDS.has(value) ? "UP"
    : DOWN_TRENDS.has(value) ? "DOWN" : value === "LATERAL" ? "FLAT" : "UNKNOWN";
  let summary = "Dados insuficientes para uma leitura multitemporal.";
  if (direction(scalp) === "UP" && direction(swing) === "DOWN")
    summary = "Curto prazo em alta; períodos superiores em baixa.";
  else if (direction(scalp) === "DOWN" && direction(swing) === "UP")
    summary = "Curto prazo em baixa; períodos superiores em alta.";
  else if (direction(scalp) === "UP" && direction(day) === "UP" && direction(swing) === "UP")
    summary = "Alta alinhada nos horizontes avaliados.";
  else if (direction(scalp) === "DOWN" && direction(day) === "DOWN" && direction(swing) === "DOWN")
    summary = "Baixa alinhada nos horizontes avaliados.";
  else if (result?.timeframe_divergence === true)
    summary = "Direções divergentes entre períodos avaliados.";
  else if (direction(scalp) === "UP" && direction(swing) === "FLAT")
    summary = "Curto prazo em alta; períodos superiores laterais.";
  else if (direction(scalp) === "DOWN" && direction(swing) === "FLAT")
    summary = "Curto prazo em baixa; períodos superiores laterais.";
  else if ([scalp, day, swing].every((value) => value === "LATERAL"))
    summary = "Predomínio lateral nos horizontes avaliados.";
  else if ([scalp, day, swing].some((value) => value !== "DADOS INSUFICIENTES"))
    summary = "Horizontes avaliados sem alinhamento direcional único.";
  if (result?.extended_trend_risk === "ELEVATED") summary += " Extensão elevada nos dados disponíveis.";
  return summary;
}

export function filterTrendItems(scan, { assetClass = "ALL", trend = "ALL", state = "ALL" } = {}) {
  return (scan?.items || []).filter((item) => {
    const kind = String(item.asset?.asset_class || "OTHER_UNKNOWN").toUpperCase();
    const classMatch = assetClass === "ALL" || (assetClass === "OTHER_UNKNOWN"
      ? ["OTHER", "OTHER_UNKNOWN"].includes(kind) : kind === assetClass);
    if (!classMatch) return false;
    const stateMatch = state === "ALL" || (state === "EVALUATED" && item.state === "AVALIADO")
      || (state === "PENDING" && item.state === "PENDENTE")
      || (state === "INSUFFICIENT" && item.state === "DADOS INSUFICIENTES")
      || (state === "FAILED" && item.state === "FALHO");
    if (!stateMatch) return false;
    if (trend === "ALL") return true;
    if (item.state !== "AVALIADO") return false;
    return item.result?.trend === trend;
  });
}

export { HORIZON_TIMEFRAMES, TREND_TIMEFRAMES };

export const MAX_TREND_BATCH_SIZE = MAX_BATCH_SIZE;
export const TREND_TERMINAL_STATES = TERMINAL_STATES;
