# B4.8 Historical Macro and Economic Event Evidence

## Scope and authority

- Symbol/timeframe: XAUUSD M1; R1 2026-08-24..28, R2 2026-09-01..05, R3 2026-09-08..12 (UTC boundaries).
- Existing B4.7 technical contexts and B4.7D Robot Catalog associations remain authoritative and unchanged.
- B4.8 is an additive, read-only projection in the canonical Robot Intelligence response and Control Center. It creates no trading authority.
- Source facts are a reviewed, versioned transcription in `jarvis_core/data/b4_8_official_releases.json`, not an archive of HTTP response bytes. The source-file content fingerprint and each normalized-record fingerprint are exposed.

## Reuse-first audit

| Existing source | Finding | Decision |
| --- | --- | --- |
| Golden `market_data.py` FRED CSV: DGS10, T10YIE, DFEDTARU, DTWEXBGS | Latest/current values only; no historical vintage or release-time contract | Reference source IDs only; no point-in-time label |
| Golden Trading Economics calendar | Current calendar, `TRADING_ECONOMICS_KEY` required, no demonstrated historical-vintage contract | Provider subgate stopped; no credential requested or used |
| Golden `_macro_snapshot` gold-bias score | Current heuristic with no historical availability boundary | Reject for B4.8 scientific labeling |
| B4.6 `temporal_market_context` | Outcome/leakage guard, immutable fingerprint pattern | Reuse temporal and no-outcome contract |
| B4.7 reconciled contexts | Frozen technical labels and run IDs | Read-only linkage; no rewrite |
| `CanonicalScientificMemory` | Canonical scientific evidence identity | Prepare evidence IDs; no Memory V2 DB write |

## Primary-source acquisition

| Window | Release | Available at UTC | Original fact retained | Source |
| --- | --- | --- | --- | --- |
| Warm-up (all) | Fed FOMC decision 2026-07-29 | 2026-07-29 18:00 | Target range 3.50-3.75% | [Federal Reserve](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm) |
| R1 | GDP Q2 second estimate | 2026-08-26 12:30 | Real GDP +1.5% annualized | [BEA](https://www.bea.gov/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026) |
| R1 | July PCE | 2026-08-26 12:30 | PCE price index +3.7% year-over-year | [BEA](https://www.bea.gov/news/2026/personal-income-and-outlays-july-2026) |
| R2 | August Employment Situation | 2026-09-04 12:30 | Payroll change +162,000 | [BLS](https://www.bls.gov/news.release/archives/empsit_09042026.htm) |
| R3 | August PPI | 2026-09-10 12:30 | Final demand +0.4% month-over-month | [BLS](https://www.bls.gov/news.release/archives/ppi_09102026.htm) |
| R3 | August CPI | 2026-09-11 12:30 | All items +3.4% year-over-year | [BLS](https://www.bls.gov/news.release/archives/cpi_09112026.htm) |

These are selected XAUUSD/USD-relevant releases, not an exhaustive economic calendar. Historical BLS pages were verified through web retrieval but rejected local HTTP GET with 403. Raw source-response bytes were not preserved for any source; the curated JSON is a normalized transcription, not a substitute raw artifact. BEA pages explicitly say later estimates superseded the original release; linked dynamic tables are not used. `ingested_at` records B4.8 curation on 2026-10-02, not historical Jarvis ingestion. Consensus, surprise, previous, rate/yield time series, USD index and a complete historical event schedule remain UNKNOWN.

## Temporal and derivation contract

- `EX_ANTE_CONTEXT` cutoff is 00:00 UTC at window start. Only records with `released_at <= available_at <= cutoff` may enter. Future in-window releases do not affect it; scheduled-event exposure stays UNKNOWN because contemporaneous schedule provenance is not frozen.
- `POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT` cutoff is 00:00 UTC after the final day. In-window primary releases produce a local deterministic `EVENT_RISK_STATE=HIGH`; this is not a predictive or causal label.
- Window-descriptive facts from R1 can be known by R2; R2 releases can be known by R3. Later releases cannot leak backward. `observed_at/period_reference`, `released_at`, `available_at`, `ingested_at`, and window cutoff are separate fields.
- `MACRO_STATE=PARTIAL` describes coverage, not directional gold bias. USD and Treasury yield states stay UNKNOWN. No economic surprise is computed without contemporaneous consensus.
- The context fingerprint covers window identity, temporal semantics, normalized input evidence, source fingerprint and derivation/rule version. Robot outcomes are neither input nor fingerprint material.
- B4.8 supplements the frozen B4.7 technical context; it does not supersede or rewrite technical labels. Scientific evidence IDs use the canonical `CanonicalScientificMemory.prepare` boundary; persistence is file-backed only. No SQLite schema or content mutation was authorized.

## Read model and Control Center

`robot_intelligence` now supplies six macro contexts (ex-ante and descriptive for each window), each linked to the existing run ID and technical-context fingerprint. Missing source file or invalid evidence is surfaced as `macro_evidence_status=UNAVAILABLE`, without taking down the endpoint. The existing temporal panel displays a separate macro table, official source links with release/availability time, revision and raw-artifact status. The existing `POST_WINDOW_OUTCOME` table remains separate. The screen states `ANALYSIS ONLY`, `BACKTEST`, and `NOT AUTHORIZED FOR LIVE TRADING`.

## Limits and next evidence

Status: `PASS_WITH_RESTRICTIONS`. Primary archived release facts and temporal cutoffs are useful, but raw-response preservation, complete event-calendar provenance, contemporaneous consensus, historical yield/USD vintages, and Memory V2 persistence are not proven. No empirical robot/macro matcher is authorized or ready. A future gate should preserve source bytes where permitted, establish historical calendar publication provenance, and add vintage-aware USD/rate data before stronger scientific claims.
