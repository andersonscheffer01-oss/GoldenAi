# JARVIS UI-D1 — Unified Desktop Design System

**Authority:** the five screenshots establish visual hierarchy; their shared `DESIGN.md` provides intent; `code.html` shows component structure but contains demo data and remote dependencies. This is a proposed unified token contract, not a CSS implementation.

## Visual Principles

- Institutional Forex terminal: dense, quiet, precise, scan-oriented; preserve the donor’s graphite/gold identity and visible information hierarchy.
- Use one shared shell and compact workspace regions; no marketing hero, decorative gradients, oversized card grids, or independent page chrome.
- Gold identifies GoldenAI/analysis and focused primary navigation; blue communicates neutral information/focus; green/red communicate positive/negative outcome only; amber communicates warning; muted gray communicates unknown/disabled.
- Thin separators and tonal surfaces carry hierarchy. Avoid glow, neon, strong elevation and excessive pill badges.
- Every number is tied to a named source, unit, period, evidence class and timestamp when meaningful. Demo values from donor files are never populated in production.

## Canonical Tokens

The shared design brief conflicts with itself: YAML and prose specify different canvas, gold, blue and green values. Resolve to this single set for future implementation; change only through a design review with screenshots.

| Token | Value | Use |
|---|---|---|
| `canvas` | `#0D1117` | App workspace background. |
| `surface-1` | `#161B22` | Main shell panels and table regions. |
| `surface-2` | `#21262D` | Selected/hover/raised compact controls. |
| `surface-3` | `#30363D` | Stronger dividers and neutral control fill. |
| `border` | `#30363D` | 1px structural separator. |
| `text-primary` | `#F0F6FC` | Main labels and readable values. |
| `text-secondary` | `#8B949E` | Metadata, labels and supporting text. |
| `text-disabled` | `#484F58` | Disabled text only when contrast remains legible. |
| `gold` | `#D29922` | Brand, active analysis and focus identity. |
| `gold-focus` | `#E3B341` | Hover/focus emphasis. |
| `info` | `#58A6FF` | Neutral informational state and links. |
| `positive` | `#3FB950` | Positive result/healthy state. |
| `danger` | `#F85149` | Negative result/danger state. |
| `warning` | `#E3B341` | Caution, approval-needed or stale warning. |
| `unknown` | `#8B949E` | Unknown/unavailable, never green. |

Use semantic text/icon/border alongside color. Do not communicate a critical state through color alone. Verify contrast in actual QtWebEngine at target DPI before sign-off.

## Typography and Numbers

- Donor intent: Inter for readable body/headings; JetBrains Mono for aligned prices, counts, IDs and timestamps. Their Google Fonts imports are remote and must not be carried into Desktop runtime.
- Existing Jarvis UI packages local Orbitron, Rajdhani and Share Tech Mono fonts. Reuse the existing local font assets where they preserve donor legibility: restrained Rajdhani/Inter-like sans hierarchy for shell/body, Share Tech Mono for data, Orbitron only for small identity accents. Do not use display fonts for dense prose.
- If exact Inter/JetBrains Mono is selected later, package approved local font files as part of the application; no CDN request at runtime. Use system sans/monospace fallback.
- Nominal desktop scale: title 22–28px; view title 18–22px; section 14–16px; body 12–14px; compact metadata 11–12px; dense table values at least 12px at 100% scale. Respect Windows text scaling; do not shrink critical state labels to fit.
- Tabular numerals, right alignment for values, explicit units and locale-aware formatting (`pt-BR`) for price/currency. Timestamps expose timezone or source timezone.

## Layout, Surfaces and Density

- Desktop-first grid. At 1366x768 keep primary status, active view title, first key data region and Jarvis access visible; do not clip critical controls. At 1920x1080 and 2560x1440 add columns/rows, not oversized whitespace.
- Use 4px base rhythm with 8px multiples; shell gutters 12–16px; workspace margins 16–24px; panel padding 12–16px; table rows 28–36px depending on wrapping and DPI.
- Shell: stable top status band, 220–260px navigation rail (collapsible only by explicit control), flexible central workspace, persistent but compact Jarvis contextual entry. Avoid a permanently oversized chat footer that steals chart/table height; a dock/drawer may expand on request.
- Surface hierarchy: canvas → panel → compact interactive surface. Sections are unframed bands or columns; reserve bordered cards for repeated records or genuinely framed instruments. No nested cards.
- Borders are 1px; radius 4px for controls/panels and maximum 8px for modal/drawer. Pill shape is reserved for tiny count badges only.
- Keep market tables, evidence tables and operational records dense but stable: fixed column sizing for IDs/numbers, truncation with accessible full value, horizontal overflow only where the user can still reach all columns.

## Components

| Component | Contract |
|---|---|
| Top status bar | Real Core/profile/security/approval/source state, timestamp and mode. Each item exposes detail on focus/hover; no decorative “online” lights. |
| Navigation | Icon plus concise label; stable active indication via gold edge/background and text, not color alone. Keyboard navigable and tooltip-enabled when collapsed. |
| KPI/readout | Label, value+unit, evidence/source class, period and as-of. Show `—` plus reason for unknown; never convert unavailable to zero. |
| Table | Sticky header when useful, sortable labels with accessible state, source-bound rows, stable numeric alignment, explicit loading/empty/error/unavailable rows. |
| Chart | Title, metric/unit, range, source/evidence class, last update, accessible textual summary and empty/stale state. No hand-authored values presented as live. |
| Badge | Small textual state with semantic icon/label. Keep catalog, repertoire, compiled artifact, evidence, campaign and authorization badges independent. |
| Button | Familiar icon for icon-only actions, tooltip and accessible name; text+icon for clear commands. Disabled state explains policy/source, not vague failure. Destructive mutations are not donor-derived. |
| Filter | Native select/menu for option sets, segmented tabs only for mutually exclusive short views, date range controls for time windows. Filter state never claims a new data source. |
| Drawer/dialog | Compact, keyboard-safe, focus-managed and explicit scope/target. Confirmation content comes from canonical SecurityManager contract. |
| Jarvis surface | Persistent access; context preview contains allow-listed IDs and view state. It does not acquire execution authority from the displayed page. |

## State Vocabulary

Use one state component contract: `LOADING`, `READY`, `EMPTY`, `STALE`, `SOURCE_UNAVAILABLE`, `DISABLED_BY_PROFILE`, `AUTH_REQUIRED`, `APPROVAL_REQUIRED`, `ERROR`, `UNKNOWN`.

- **Loading:** preserve layout dimensions; identify the source being queried.
- **Empty:** query succeeded and returned no records; distinct from failure.
- **Stale:** retain last known value only with visible stale marker, observation timestamp and age.
- **Unavailable/disabled:** say why and identify the source/profile; never show fake zeros or suggest enabling MT5 if not required.
- **Auth required:** preserve HTTP perimeter semantics; do not map 401 to MT5 disconnected.
- **Approval required:** show the exact pending approval/scope and canonical next state; do not imply success.
- **Error/unknown:** concise safe message plus correlation/request ID where available; do not leak token, secret or raw provider exception.

## Operational Modes and Authority

Persistent mode labels: `ANÁLISE`, `BACKTEST`, `SIMULAÇÃO`, `LIVE`. Each mode has a distinct icon, color treatment, label and accessible text. Default to ANALYSIS. LIVE gets a high-contrast red frame/explicit “AO VIVO” label and requires server-authoritative authorization; MT5 connected is not authorization. Never place mode solely inside a transient view card.

For robots, render `catalog_status`, `repertoire_status`, `source_artifact`, `compiled_artifact`, `tested_artifact`, `parameter_fingerprint`, `evidence_status`, `campaign_status` and `execution_authorization` separately. `ACTIVE_IN_REPERTOIRE != AUTHORIZED_TO_TRADE` is a presentation invariant.

## Responsiveness and Accessibility Review

- Validate 1366x768, 1920x1080 and 2560x1440 with Windows 100%, 125%, 150% DPI; include keyboard-only navigation and high-contrast review.
- No clipped labels, overlapping table actions, chart overlays hiding data, or navigation-induced layout jumps. Text wraps or the column expands before font size is reduced.
- Show visible focus rings, tooltips for non-obvious icons, accessible chart summaries, non-color state labels, and explanatory disabled states.
- Only active/needed view polls and renders; hidden charts pause, and shared market subscriptions are owned once by the canonical data layer.

## Donor Reuse Decisions

`KEEP`: graphite/gold hierarchy, thin dividers, high-density analyst terminal, stable navigation, evidence checklist, trade-detail inspector, per-view comparisons.

`ADAPT`: blue/green/red semantics, metric cards, chart/table structure, status badges and compact filters to canonical source/freshness contracts.

`MERGE`: repeated shell/status/nav/footer into one shared Desktop shell.

`REFERENCE_ONLY`: HTML/Tailwind classes and any data-driven appearance whose values have not been mapped.
`REJECT`: remote CDN dependencies, fake/demo numbers, toast-as-result, account/trade identifiers, “Lia”, fake live state, and direct trading callbacks.
