# Market UI Parity After B4.2

The approved Golden `market.html` surface is preserved. The Jarvis Control
Center B3 Market Intelligence surface now consumes the canonical
`/api/jarvis/golden/market-intelligence` snapshot for Radar, Scanner, Risk,
Validation and Performance read states.

The existing visual identity and navigation remain intact. The surface shows
provenance/freshness and explicit empty/disabled states. MT5-disabled fields
remain visibly unavailable while independent partial sources can still render.

No legacy scanner route, direct provider path, order control, or live-trading
authority was added to the Control Center.
