"""Canonical, read-only bridge for existing Golden domain capabilities.

The bridge normalizes legacy Golden observations for Jarvis without copying
scanner, market, risk, validation, robot, or tester engines.  It intentionally
contains no process launch, broker mutation, Strategy Tester execution, or
credential access path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .b2_contracts import (EvidenceClass, FreshnessState, build_recovery_manifest,
                           provenance_for_payload, utc_now)


READ_ONLY = "READ_ONLY"
NO_SIDE_EFFECT = "NO_SIDE_EFFECT"
UNKNOWN = "UNKNOWN"
UNAVAILABLE = "UNAVAILABLE"
STALE = "STALE"


def _now() -> str:
    return utc_now()


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    if hasattr(value, "item"):
        try:
            return _json(value.item())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return _json(vars(value))
    return str(value)


@dataclass(frozen=True)
class GoldenCapability:
    capability_id: str
    canonical_owner: str
    implementation_owner: str
    source_module: str
    read_capabilities: tuple[str, ...]
    mutation_capabilities: tuple[str, ...]
    side_effect_level: str
    security_requirement: str
    audit_requirement: str
    provenance_support: str
    legacy_status: str
    health: str = UNKNOWN
    availability: str = UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "read_only": True,
            "side_effect_class": READ_ONLY,
            "security_state": self.security_requirement,
        }


_CAPABILITIES = (
    GoldenCapability("golden.scanner", "JarvisService", "GoldenScanner",
                     "golden_scanner.py", ("snapshot", "setups", "regime"),
                     ("scan", "auto_trade"), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "source/timestamp/stale", "LEGACY_BRIDGED"),
    GoldenCapability("golden.radar", "JarvisService", "Radar Macro",
                     "market_data.py", ("overview", "news", "macro", "integrity"),
                     ("refresh_provider_cache",), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "provider/timestamp/freshness", "LEGACY_BRIDGED"),
    GoldenCapability("golden.market_data", "JarvisService", "Market Data",
                     "market_data.py + market_readonly.py", ("tick", "candles", "symbol"),
                     ("symbol_select",), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "provider/observed_at", "LEGACY_BRIDGED"),
    GoldenCapability("golden.market_regime", "JarvisService", "meta_strategy",
                     "meta_strategy.py", ("regime", "compatibility"),
                     ("portfolio_change",), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "calculation origin/timestamp", "LEGACY_BRIDGED"),
    GoldenCapability("golden.meta_strategy", "JarvisService", "meta_strategy",
                     "meta_strategy.py", ("ranking", "confluence", "risk metadata"),
                     ("strategy activation",), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "calculated/source", "LEGACY_BRIDGED"),
    GoldenCapability("golden.risk_engine", "JarvisService", "RiskEngine",
                     "risk_engine.py", ("risk report", "lot calculation metadata"),
                     ("risk configuration", "order execution"), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "calculation origin", "LEGACY_BRIDGED"),
    GoldenCapability("golden.validation", "JarvisService", "ValidationEngine",
                     "validation_engine.py + mt5_backtest.py", ("history", "summary"),
                     ("run validation", "run backtest"), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "evidence class/artifact", "LEGACY_BRIDGED"),
    GoldenCapability("golden.strategies", "JarvisService", "Strategy Catalog",
                     "strategy_engine.py + strategy_audit.py", ("catalog", "coverage"),
                     ("strategy mutation",), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "source/calculation", "LEGACY_BRIDGED"),
    GoldenCapability("golden.mql5", "JarvisService", "RobotCatalog",
                     "robot_catalog.py + mql5_evidence.py", ("identity", "artifacts", "evidence"),
                     ("compile", "tester execution", "repertoire mutation"), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "artifact hash/provenance", "CANONICAL_SUBORDINATE"),
    GoldenCapability("golden.deep_analysis", "JarvisService", "Market Context",
                     "market_data.py + meta_strategy.py", ("context", "inputs", "outputs"),
                     ("analysis persistence", "trade execution"), "READ", "READ_ONLY_NO_SIDE_EFFECT",
                     "AuditLog/read receipt", "input/source/timestamp", "LEGACY_BRIDGED"),
)


def _availability(payload: Any) -> tuple[str, str, bool]:
    if not isinstance(payload, dict):
        return UNKNOWN, UNKNOWN, True
    status = str(payload.get("status") or "").upper()
    if status in {"OFFLINE", "UNAVAILABLE", "NOT_FOUND", "INVALID_TIMEFRAME"}:
        return UNAVAILABLE, status, True
    if payload.get("stale") is True or str(payload.get("freshness", "")).upper() == STALE:
        return STALE, STALE, True
    timestamp = payload.get("timestamp") or payload.get("observed_at") or payload.get("updated_at")
    if not timestamp:
        return UNKNOWN, UNKNOWN, True
    return "AVAILABLE", "HEALTHY" if payload.get("ok", True) else "DEGRADED", False


def _envelope(capability_id: str, payload: Any, source_module: str,
              evidence_class: str = "CALCULATED",
              correlation_id: str = "") -> dict[str, Any]:
    data = _json(payload)
    availability, health, stale = _availability(data)
    provenance = provenance_for_payload(
        data, source_module, source_type="GOLDEN_LEGACY",
        evidence_class=evidence_class,
        capability=capability_id.rsplit(".", 1)[-1],
        correlation_id=correlation_id,
    ).to_dict()
    provenance.update({"source_module": source_module,
                       "calculation_origin": provenance.get("calculation_origin")
                       or "existing_golden_implementation"})
    return {
        "ok": isinstance(data, dict) and data.get("ok", True) is not False,
        "capability_id": capability_id,
        "read_only": True,
        "side_effect_class": READ_ONLY,
        "security_state": "READ_ONLY_NO_SIDE_EFFECT",
        "availability": availability,
        "health": health,
        "freshness": (FreshnessState.STALE.value if stale and availability == STALE
                       else provenance["freshness_state"]),
        "stale": stale,
        "evidence_class": evidence_class,
        "observed_at": provenance.get("observed_at"),
        "received_at": provenance.get("received_at"),
        "content_fingerprint": provenance.get("content_fingerprint"),
        "provenance": provenance | {
            "provider": (data.get("source") if isinstance(data, dict) else None) or source_module,
        },
        "data": data,
    }


def _safe(capability_id: str, source_module: str, operation: Callable[[], Any],
          evidence_class: str = "CALCULATED",
          correlation_id: str = "") -> dict[str, Any]:
    try:
        return _envelope(capability_id, operation(), source_module, evidence_class,
                         correlation_id=correlation_id)
    except Exception as exc:
        return _envelope(capability_id, {
            "ok": False,
            "status": UNAVAILABLE,
            "error_code": type(exc).__name__,
            "reason": str(exc)[:240],
        }, source_module, evidence_class, correlation_id=correlation_id)


def _normalize_scan(raw: Any) -> dict[str, Any]:
    value = dict(raw) if isinstance(raw, dict) else {}
    snapshot = value.get("market_snapshot")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    result = {
        "symbol": value.get("symbol", "UNKNOWN"),
        "asset_class": value.get("asset_class", "UNKNOWN"),
        "mode": value.get("mode", value.get("best_mode", "UNKNOWN")),
        "direction": value.get("direction", value.get("best_direction", "UNKNOWN")),
        "price": value.get("price", snapshot.get("price")),
        "spread": value.get("spread", snapshot.get("spread")),
        "score": value.get("score", value.get("score_total", value.get("best_score", 0))),
        "readiness": value.get("readiness", value.get("best_readiness", 0)),
        "alert_state": value.get("alert_state", value.get("best_level", "UNKNOWN")),
        "market_regime": value.get("regime", snapshot.get("regime", "UNKNOWN")),
        "volatility": value.get("volatility", "UNKNOWN"),
        "session": value.get("session", "UNKNOWN"),
        "ADX": value.get("ADX", value.get("adx", snapshot.get("adx"))),
        "HTF_bias": value.get("HTF_bias", value.get("bias", "UNKNOWN")),
        "trend": {tf: value.get(f"trend_{tf.lower()}", value.get(f"trend_{tf}", "UNKNOWN"))
                  for tf in ("H4", "H1", "M15", "M5")},
        "selected_setup": value.get("best_setup", value.get("selected_setup")),
        "alternative_setups": value.get("top_setups_list", value.get("setups", [])),
        "risk_reward": value.get("risk_reward", value.get("best_rr")),
        "confluence": value.get("confluence", value.get("best_confluence")),
        "setup_conditions": value.get("setup_conditions", value.get("best_conditions_met", [])),
        "status": value.get("status", value.get("setup_status", "UNKNOWN")),
        "alert": value.get("alert", value.get("alert_state", "UNKNOWN")),
        "daily_movement": value.get("daily_movement", value.get("daily_pips")),
        "indicators": {
            "RSI_H1": value.get("RSI_H1", value.get("rsi_h1")),
            "RSI_M15": value.get("RSI_M15", value.get("rsi_m15")),
            "ATR_H1": value.get("ATR_H1", value.get("atr_h1")),
            "ATR_M15": value.get("ATR_M15", value.get("atr_m15")),
            "daily_pips": value.get("daily_pips"),
            "daily_range": value.get("daily_range"),
            "BB_width": value.get("BB_width", value.get("bb_width")),
        },
        "support_resistance": value.get("support_resistance", value.get("key_zones", [])),
        "score_semantics": "SCORE_NOT_PROBABILITY",
        "raw_fields_preserved": value,
    }
    return _json(result)


class GoldenReadBridge:
    """Jarvis-owned read facade over existing Golden implementations."""

    def __init__(self, robot_catalog=None, runtime_profile=None):
        self.robot_catalog = robot_catalog
        self.runtime_profile = runtime_profile

    def set_runtime_profile(self, profile):
        self.runtime_profile = profile

    def _mt5_enabled(self):
        if self.runtime_profile is not None:
            return bool(self.runtime_profile.mt5_enabled)
        try:
            from .runtime_profile import active_runtime_profile
            return bool(active_runtime_profile().mt5_enabled)
        except Exception:
            return True

    @staticmethod
    def _source_disabled(capability_id, source_module):
        return _envelope(capability_id, {
            "ok": False,
            "status": "SOURCE_DISABLED",
            "availability": "SOURCE_DISABLED",
            "reason": "MT5_DISABLED_BY_PROFILE",
            "source": "MT5",
        }, source_module)

    def _market_overview(self):
        from market_data import get_market_overview
        if self.runtime_profile is None:
            return get_market_overview()
        return get_market_overview(mt5_enabled=self._mt5_enabled())

    def _market_chart(self, symbol, timeframe):
        from market_data import get_market_chart
        if self.runtime_profile is None:
            return get_market_chart(symbol, timeframe)
        return get_market_chart(symbol, timeframe, mt5_enabled=self._mt5_enabled())

    def _market_ai_context(self, symbol):
        from market_data import get_market_ai_context
        if self.runtime_profile is None:
            return get_market_ai_context(symbol)
        return get_market_ai_context(symbol, mt5_enabled=self._mt5_enabled())

    def capability_registry(self) -> dict[str, Any]:
        capabilities = [item.to_dict() for item in _CAPABILITIES]
        return {"ok": True, "read_only": True, "capabilities": capabilities,
                "count": len(capabilities), "authority": "JarvisService",
                "mutation_execution": "DISABLED_IN_B1", "timestamp": _now()}

    def scanner_snapshot(self, symbol: str = "", limit: int = 3) -> dict[str, Any]:
        if not self._mt5_enabled():
            return self._source_disabled("golden.scanner", "golden_scanner.py")
        from .tools.market_readonly import golden_scanner_results
        result = _safe("golden.scanner", "golden_scanner.py",
                       lambda: golden_scanner_results(symbol, limit))
        data = result["data"]
        if isinstance(data, dict):
            data["normalized_results"] = [_normalize_scan(item) for item in data.get("results", [])]
        return result

    def radar_snapshot(self, symbol: str = "", limit: int = 8) -> dict[str, Any]:
        def read():
            overview = self._market_overview()
            if symbol:
                overview["requested_symbol"] = symbol
            overview["requested_limit"] = max(1, min(int(limit or 8), 20))
            return overview
        return _safe("golden.radar", "market_data.py", read)

    def radar_detail(self, symbol: str = "", timeframe: str = "M15",
                     correlation_id: str = "") -> dict[str, Any]:
        """Project existing Radar providers without copying the Radar UI."""
        def read():
            overview = self._market_overview()
            chart = (self._market_chart(symbol, timeframe)
                     if symbol else {"status": "NOT_REQUESTED", "ok": True})
            assets = overview.get("assets") or []
            groups = {}
            for item in assets:
                groups.setdefault(str(item.get("group") or "UNKNOWN"), []).append(item)
            return {
                "market_map": assets,
                "gold": overview.get("gold") or overview.get("gold_levels"),
                "gold_levels": overview.get("gold_levels"),
                "forex": groups.get("Forex", []),
                "indices": groups.get("Indices", []),
                "crypto": groups.get("Cripto", groups.get("Crypto", [])),
                "news": overview.get("news", []),
                "technical_state": chart,
                "support_resistance": chart.get("levels", []) if isinstance(chart, dict) else [],
                "currency_strength": overview.get("currency_strength", "UNAVAILABLE"),
                "market_sessions": overview.get("sessions", "UNAVAILABLE"),
                "macro_indicators": (overview.get("macro") or {}).get("indicators", []),
                "economic_calendar": overview.get("economic_calendar", []),
                "opportunity_ranking": overview.get("ranking", "UNAVAILABLE"),
                "validation_pipeline": overview.get("validation", "UNAVAILABLE"),
                "performance": overview.get("performance", "UNAVAILABLE"),
                "source_integrity": {"sources": overview.get("sources", []),
                                     "configured": overview.get("configured", {})},
                "replay_metadata": overview.get("replay_metadata", "UNAVAILABLE"),
                "updated_at": overview.get("updated_at"),
                "source": "market_data.py",
            }
        return _safe("golden.radar", "market_data.py", read)

    def market_intelligence_snapshot(self, symbol: str = "XAUUSD",
                                     timeframe: str = "M15",
                                     correlation_id: str = "") -> dict[str, Any]:
        """Build the single coherent, read-only B4.2 market projection."""
        from .market_read_models import build_market_intelligence_snapshot

        symbol = str(symbol or "XAUUSD").strip()[:32]
        timeframe = str(timeframe or "M15").upper().strip()[:8]
        correlation_id = str(correlation_id or _now())[:120]

        def read():
            overview = self._market_overview()
            chart = (self._market_chart(symbol, timeframe)
                     if symbol else {"ok": False, "status": "NOT_REQUESTED"})
            scanner = self.scanner_snapshot(symbol, limit=30)
            risk = self.risk_detail()
            validation = self.validation_detail(limit=30)
            return build_market_intelligence_snapshot(
                overview=overview, chart=chart, scanner=scanner, risk=risk,
                validation=validation, symbol=symbol, timeframe=timeframe,
                correlation_id=correlation_id)

        result = _safe("golden.market_intelligence", "market_read_models.py", read,
                       correlation_id=correlation_id)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        result["snapshot_id"] = data.get("snapshot_id", "")
        result["correlation_id"] = correlation_id
        result["status"] = data.get("status", result.get("availability", UNKNOWN))
        result["freshness"] = data.get("freshness", result.get("freshness", UNKNOWN))
        return result

    def market_context(self, symbol: str = "XAUUSD", timeframe: str = "M15") -> dict[str, Any]:
        def read():
            context = self._market_ai_context(symbol)
            context["requested_timeframe"] = timeframe
            return context
        return _safe("golden.market_data", "market_data.py", read)

    def market_regime(self, symbol: str = "XAUUSD") -> dict[str, Any]:
        if not self._mt5_enabled():
            return self._source_disabled("golden.market_regime", "meta_strategy.py")
        def read():
            from meta_strategy import analyze_symbol
            result = analyze_symbol(symbol)
            return {"symbol": symbol, "regime": result.get("regime"),
                    "market_snapshot": result.get("market_snapshot"),
                    "risk": result.get("risk")}
        return _safe("golden.market_regime", "meta_strategy.py", read)

    def meta_strategy(self, symbol: str = "XAUUSD", limit: int = 8) -> dict[str, Any]:
        if not self._mt5_enabled():
            return self._source_disabled("golden.meta_strategy", "meta_strategy.py")
        def read():
            from meta_strategy import analyze_radar, analyze_symbol
            return analyze_symbol(symbol) if symbol else analyze_radar(limit=limit)
        return _safe("golden.meta_strategy", "meta_strategy.py", read)

    def risk(self) -> dict[str, Any]:
        if not self._mt5_enabled():
            return self._source_disabled("golden.risk_engine", "risk_engine.py")
        from .tools.market_readonly import golden_risk_status
        return _safe("golden.risk_engine", "risk_engine.py", golden_risk_status)

    def risk_detail(self) -> dict[str, Any]:
        if not self._mt5_enabled():
            return self._source_disabled("golden.risk_engine", "risk_engine.py")
        def read():
            from .tools.market_readonly import golden_risk_status
            result = golden_risk_status()
            risk = result.get("risk") or {}
            return {
                "risk_per_trade": risk.get("risk_per_trade_pct"),
                "lot_sizing": risk.get("lot_size") or risk.get("lot_sizing", "UNAVAILABLE"),
                "sl": risk.get("sl") or risk.get("stop_loss", "UNAVAILABLE"),
                "tp": risk.get("tp") or risk.get("take_profit", "UNAVAILABLE"),
                "rr": risk.get("rr") or risk.get("risk_reward", "UNAVAILABLE"),
                "spread_constraints": risk.get("spread_constraints", "UNAVAILABLE"),
                "exposure": risk.get("correlation_report", risk.get("exposure", "UNAVAILABLE")),
                "portfolio_constraints": risk.get("details", "UNAVAILABLE"),
                "risk_state": result.get("status", "UNKNOWN"),
                "calculation_inputs": risk.get("inputs", "UNAVAILABLE"),
                "calculation_outputs": risk,
                "security_authority": "SecurityManager; RiskEngine never authorizes action",
                "source": "risk_engine.py",
                "updated_at": result.get("timestamp"),
            }
        return _safe("golden.risk_engine", "risk_engine.py", read)

    def strategy_summary(self) -> dict[str, Any]:
        def read():
            from strategy_audit import audit_all_strategies, get_audit_summary
            from strategy_engine import list_strategies
            strategies = list_strategies()
            return {"strategies": strategies, "audit": audit_all_strategies(),
                    "summary": get_audit_summary(),
                    "matching_coverage": {
                        "EXISTING_ROBOT_MARKET_MATCHING_COVERAGE": [
                            "GoldenScanner", "meta_strategy", "risk_engine",
                            "Radar Macro", "validation"
                        ],
                        "new_matcher_created": False,
                    }}
        return _safe("golden.strategies", "strategy_engine.py", read)

    def validation_summary(self, limit: int = 20) -> dict[str, Any]:
        def read():
            from mt5_backtest import get_backtest_history
            history = get_backtest_history(max(1, min(int(limit or 20), 100)))
            return {"history": history, "count": len(history),
                    "evidence_policy": {
                        "historical": "HISTORICAL_EVIDENCE",
                        "calculated": "CALCULATED",
                        "synthetic": "SYNTHETIC",
                        "demo": "DEMO",
                        "unknown": "UNKNOWN",
                    }}
        return _safe("golden.validation", "mt5_backtest.py", read,
                     evidence_class="HISTORICAL_EVIDENCE")

    def validation_detail(self, limit: int = 20) -> dict[str, Any]:
        result = self.validation_summary(limit)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        history = data.get("history") or []
        classified = []
        for item in history:
            row = dict(item) if isinstance(item, dict) else {"value": item}
            raw_class = str(row.get("evidence_class") or row.get("evidence_type") or "HISTORICAL_EVIDENCE").upper()
            allowed = {item.value for item in EvidenceClass}
            row["evidence_class"] = raw_class if raw_class in allowed else EvidenceClass.UNKNOWN.value
            classified.append(row)
        if isinstance(data, dict):
            data["history"] = classified
            data["evidence_classes"] = [item.value for item in EvidenceClass]
            data["forward_evidence"] = [item for item in classified if item.get("forward") is True]
        result["data"] = data
        return result

    def deep_analysis_context(self, symbol: str = "XAUUSD") -> dict[str, Any]:
        def read():
            from market_data import get_market_ai_context
            return {"symbol": symbol, "context": self._market_ai_context(symbol),
                    "execution_authority": "NONE",
                    "provider_routing": "Jarvis ModelRouter remains owner"}
        return _safe("golden.deep_analysis", "market_data.py", read)

    def deep_analysis_detail(self, symbol: str = "XAUUSD",
                             correlation_id: str = "") -> dict[str, Any]:
        def read():
            from market_data import get_market_ai_context
            context = self._market_ai_context(symbol)
            strategy = {}
            try:
                if not self._mt5_enabled():
                    raise RuntimeError("MT5_DISABLED_BY_PROFILE")
                from meta_strategy import analyze_symbol
                strategy = analyze_symbol(symbol)
            except Exception as exc:
                strategy = {"status": "UNAVAILABLE", "error": type(exc).__name__}
            return {
                "technical": context.get("multitimeframe", {}),
                "multi_timeframe": context.get("multitimeframe", {}),
                "regime": strategy.get("regime", "UNAVAILABLE"),
                "support_resistance": [item.get("levels", []) for item in context.get("multitimeframe", {}).values()],
                "scanner": strategy.get("market_snapshot", "UNAVAILABLE"),
                "strategy": {key: strategy.get(key) for key in ("best_opportunity", "ranked_setups", "blocked_setups")},
                "risk": strategy.get("risk", "UNAVAILABLE"),
                "macro": context.get("fundamentals", "UNAVAILABLE"),
                "news_events": context.get("fundamentals", {}).get("events", []) if isinstance(context.get("fundamentals"), dict) else [],
                "history": "UNAVAILABLE",
                "performance": "UNAVAILABLE",
                "correlation": "UNAVAILABLE",
                "ai_model_context": {"model_called": False, "provider": "NONE"},
                "source": "market_data.py + meta_strategy.py",
                "updated_at": context.get("updated_at") or strategy.get("generated_at"),
            }
        return _safe("golden.deep_analysis", "market_data.py + meta_strategy.py", read)

    def recovery_manifest(self, root: str) -> dict[str, Any]:
        return build_recovery_manifest(root)

    def robot_catalog_summary(self) -> dict[str, Any]:
        if self.robot_catalog is None:
            return _envelope("golden.mql5", {"ok": False, "status": UNAVAILABLE,
                                              "reason": "catalog_not_bound"}, "robot_catalog.py")
        return _envelope("golden.mql5", self.robot_catalog.snapshot(), "robot_catalog.py",
                         evidence_class="VERIFIED_REAL_EVIDENCE")

    def tester_history(self) -> dict[str, Any]:
        catalog = self.robot_catalog_summary()
        data = catalog.get("data") or {}
        runs = []
        for robot in data.get("robots", []):
            for item in robot.get("test_runs", []):
                runs.append(item)
        return _envelope("golden.mql5", {"test_runs": runs, "count": len(runs),
                                          "execution": "NOT_STARTED_BY_B1"},
                         "robot_catalog.py", evidence_class="HISTORICAL_EVIDENCE")

    def mt5_read_snapshot(self) -> dict[str, Any]:
        if not self._mt5_enabled():
            return self._source_disabled("golden.market_data", "market_readonly.py")
        from .tools import market_readonly as market
        return _safe("golden.market_data", "market_readonly.py", lambda: {
            "terminal": market.mt5_status(),
            "account": market.mt5_account_info(),
            "positions": market.mt5_positions(),
            "orders": market.mt5_orders(),
        })

    def control_center_snapshot(self, symbol: str = "", include_live: bool = False) -> dict[str, Any]:
        payload = {
            "ok": True,
            "read_only": True,
            "authority": "JarvisService",
            "ui_states": ["UI_READ_MODEL", "UI_PROGRESS_STATE", "UI_ERROR_STATE",
                           "UI_EMPTY_STATE", "UI_DISABLED_STATE", "UI_PROVENANCE_VIEW",
                           "UI_SECURITY_STATE"],
            "capabilities": self.capability_registry(),
            "robot_catalog": self.robot_catalog_summary(),
            "tester_evidence": self.tester_history(),
            "strategy": self.strategy_summary(),
            "risk": self.risk(),
            "legacy_execution": {
                "AUTO_TRADE": "LEGACY_EXECUTION_PATH / LEGACY_FREEZE",
                "ENTRAR_NO_TRADE": "LEGACY_EXECUTION_PATH / LEGACY_FREEZE",
                "order_send": "LEGACY_EXECUTION_PATH / LEGACY_FREEZE",
                "invoked": False,
            },
            "voice": {"status": "OUT_OF_SCOPE_B1", "modified": False},
            "timestamp": _now(),
        }
        if include_live:
            payload["mt5"] = self.mt5_read_snapshot()
            payload["radar"] = self.radar_snapshot(symbol)
            payload["market"] = self.market_context(symbol or "XAUUSD")
            payload["scanner"] = self.scanner_snapshot(symbol)
            payload["deep_analysis"] = self.deep_analysis_context(symbol or "XAUUSD")
        else:
            payload["mt5"] = {"availability": UNKNOWN, "status": "NOT_REQUESTED",
                               "read_only": True}
            payload["radar"] = {"availability": UNKNOWN, "status": "NOT_REQUESTED",
                                 "read_only": True}
            payload["market"] = {"availability": UNKNOWN, "status": "NOT_REQUESTED",
                                  "read_only": True}
            payload["scanner"] = {"availability": UNKNOWN, "status": "NOT_REQUESTED",
                                   "read_only": True}
            payload["deep_analysis"] = {"availability": UNKNOWN, "status": "NOT_REQUESTED",
                                         "read_only": True}
        return payload


__all__ = ["GoldenCapability", "GoldenReadBridge", "READ_ONLY", "NO_SIDE_EFFECT"]
