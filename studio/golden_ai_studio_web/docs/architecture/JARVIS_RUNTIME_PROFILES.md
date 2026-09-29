# Jarvis Runtime Profiles

## Purpose

Runtime profiles make startup capabilities explicit without creating a second
backend or replacing the canonical `JarvisService`. The default profile keeps
the historical startup behavior. The opt-in `web-ai-safe` profile is intended
for Web and AI validation where MT5, trading, Strategy Tester, MQL5 compile,
Radar persistence, and voice hardware must remain inactive.

## Profiles

| Profile | Web/Gateway | Jarvis core and AI | MT5 | Voice | Trading | Tester/compile | Monitor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `default` | enabled | enabled | enabled | enabled | enabled | enabled | enabled |
| `web-ai-safe` | enabled | enabled | disabled by profile | disabled by profile | disabled by profile | disabled by profile | disabled by profile |

Select explicitly at startup:

```powershell
python server_agent.py --port 8765 --runtime-profile web-ai-safe
```

Unknown profile names fail with a clear error. There is no silent fallback.

## Safety boundary

The profile is applied to the existing `DesktopCenter.service` before MT5,
monitor, voice, or Gateway startup. In `web-ai-safe`, startup skips
`mt5_connector.ensure_connection()`, persistent Radar monitor startup, voice
service startup, STT warmup, and microphone access. Disabled HTTP routes and
Jarvis tools return `disabled_by_profile` with an explicit reason.

Market read models remain available through the same backend and return
`DISABLED_BY_PROFILE` / `SOURCE_DISABLED` for MT5-dependent values. Macro/news
and AI paths can therefore be inspected without pretending that terminal data
is live. The profile does not change `market.html`, provider credentials,
device registry, broker state, or authentication policy.

## MT5 lazy-initialization containment

The capability is propagated from `JarvisService.runtime_profile` into the
`GoldenReadBridge` and explicitly into MT5-dependent `market_data` calls. The
legacy connector also fails closed before `mt5.initialize()` or auto-launch
when the active capability is disabled. This protects indirect callers that
were not originally aware of startup profiles.

| Caller | Entry point | Safe-profile behavior |
| --- | --- | --- |
| `market_context_snapshot` | `JarvisService` -> `GoldenReadBridge.market_context` | preserves asset/timeframe; MT5 fields unavailable |
| Golden Radar | `GoldenReadBridge.radar_snapshot/detail` | overview remains read-only; MT5 source disabled |
| Golden Scanner | `GoldenReadBridge.scanner_snapshot` | `SOURCE_DISABLED`; scanner is not started |
| MarketContext | `market_data.get_market_ai_context` | chart/fundamental MT5 reads are skipped |
| Market chart/tick/forex | `market_data` helpers | explicit `SOURCE_DISABLED` result |
| Market read-only tools | `jarvis_core.tools.market_readonly` | disabled status; connector is never initialized |
| Legacy HTTP routes | `server_agent.route_api` | known MT5-dependent paths are blocked by profile |
| Startup/background refresh | `server_agent.start_server` / monitor | MT5 connector and monitor startup are skipped |

`SOURCE_DISABLED` means the source was intentionally unavailable by runtime
capability. It is not a failed connection and must not be relabeled `LIVE` or
`FRESH`. Existing cached observations are preserved only with their existing
freshness and provenance; they are never promoted to live data by safe mode.

## Canonical components

Safe mode still uses the existing Web server, Gateway, `JarvisService`, Brain,
ModelRouter, Memory Boundary, SecurityManager, ToolRegistry, and AuditLog.
The profile status is exposed by the canonical status response and is recorded
in the existing audit boundary. No parallel service or test-only server is
introduced.
