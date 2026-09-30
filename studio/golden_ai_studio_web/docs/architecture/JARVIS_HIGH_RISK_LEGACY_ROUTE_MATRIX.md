# JARVIS High-Risk Legacy Route Matrix

Static/implementation matrix after restriction closure. A frozen route is
authenticated first, audited, and rejected before its legacy handler runs.

| Family | Representative routes | Classification | Current result | Authority |
|---|---|---|---|---|
| MT5 status/positions | `/api/mt5/status`, `/api/mt5/positions` | PURE_READ | compatibility read; safe profile blocks | legacy read provider, follow-up |
| MT5 catalog | `/api/mt5/list_robots`, `/api/mt5/robot_details` | PURE_READ | compatibility read | RobotCatalog migration candidate |
| Compile | `/api/mt5/compile` | COMPILE/PROCESS_MUTATION | `LEGACY_ROUTE_FROZEN` | Jarvis SecurityManager target |
| Backtest | `/api/mt5/backtest`, `/api/mt5/real_backtest` | BACKTEST/PROCESS_MUTATION | `LEGACY_ROUTE_FROZEN` | Tester evidence gate |
| Import | `/api/mt5/import_history` | FILESYSTEM/DB MUTATION | `LEGACY_ROUTE_FROZEN` | canonical data gate |
| Scanner | `/api/scanner/*` | READ_WITH_LAZY_SIDE_EFFECT_RISK | frozen; safe profile remains disabled | Golden read-model batch |
| Risk | `/api/risk/*` | READ/CONFIG HIGH RISK | frozen; safe profile remains disabled | canonical risk read model |
| Validation | `/api/validation/*` | SIMULATION/EXTERNAL DATA | frozen; safe profile remains disabled | validation read model |
| Strategy | `/api/strategy_*`, `/api/meta_strategy`, `/api/walk_forward` | SIMULATION/MT5 READ | frozen | strategy read-model batch |
| Position manager | `/api/position/*` | PROCESS/TRADING MUTATION | frozen | no canonical broker authority |
| Auto-trade | `/api/mt5/auto_trade` | TRADING_MUTATION | frozen | never migrated here |
| Close position | `/api/mt5/close_position` | TRADING_MUTATION | frozen | never migrated here |
| Strategy manager | `/api/strategy_manager/*` | PROCESS/CONFIG MUTATION | frozen | separate approval gate |
| Monitor | `/api/monitor/*` | PROCESS MUTATION | frozen | observability gate |
| Journal | `/api/journal/*` | DATA MUTATION/READ | frozen | canonical journal reconciliation |

## Common frozen response

`ok=false`, `error=LEGACY_ROUTE_FROZEN`, HTTP status `409`, route/request/
correlation identifiers, canonical SecurityManager owner, and canonical
AuditLog owner. The response is not a silent no-op and does not call the
executor, MT5, broker, Strategy Tester, MetaEditor, or legacy provider.

## Profile distinction

`web-ai-safe` is a runtime containment decision and returns
`disabled_by_profile=true` for MT5, scanner, risk, validation, tester, MQL5,
trading, and Voice paths. The default profile's freeze is an architectural
legacy containment decision. Neither path creates a bypass.
