import { createTrendScan, trendScanSummary } from "../../jarvis_ui/src/trend-ranking-state.js";
import { createHash } from "node:crypto";

export const fixtureAsset = (symbol) => ({
  provider: "MT5", provider_asset_id: `mt5:${symbol}`, provider_symbol: symbol,
  display_symbol: symbol, display_name: `${symbol} fixture`, asset_class: "FOREX",
  asset_class_source: "FIXTURE",
});

const digestUniverse = async (assets) => {
  const canonical = assets.map(({ provider_asset_id, provider_symbol, asset_class }) =>
    `${provider_asset_id}\u0000${provider_symbol}\u0000${asset_class}`).join("\n");
  return createHash("sha256").update(canonical).digest("hex");
};

export async function makePendingScan(scanId = "00000000-0000-4000-8000-000000000001") {
  const scan = await createTrendScan([fixtureAsset("FXA"), fixtureAsset("FXB"),
    fixtureAsset("FXC"), fixtureAsset("FXD")], scanId,
    "2026-10-09T12:00:00.000Z", digestUniverse);
  return { ...scan, contract_version: "trend-scan-v1", asset_class_filter: "FOREX",
    catalog_observation: { status: "FIXTURE", observed_at: scan.created_at,
      enumerated_count: 4 }, summary: trendScanSummary(scan) };
}

export async function emitPendingScan() {
  return makePendingScan();
}
