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
import hashlib
import threading
import time

from .b2_contracts import (EvidenceClass, FreshnessState, build_recovery_manifest,
                           provenance_for_payload, utc_now)


READ_ONLY = "READ_ONLY"
NO_SIDE_EFFECT = "NO_SIDE_EFFECT"
UNKNOWN = "UNKNOWN"
UNAVAILABLE = "UNAVAILABLE"
STALE = "STALE"
TREND_RANKING_MAX_ASSETS = 4


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
            "execution_authority": "NONE",
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
    if status in {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED"}:
        return UNAVAILABLE, "DEGRADED", False
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
        "ok": (isinstance(data, dict) and
               (data.get("ok", True) is not False or
                str(data.get("status") or "").upper() in
                {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED"})),
        "capability_id": capability_id,
        "read_only": True,
        "execution_authority": "NONE",
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
        self._trend_ranking_lock = threading.Lock()
        self._trend_ranking_cache = None

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

    def _market_data_read_enabled(self):
        if self.runtime_profile is not None:
            return bool(getattr(self.runtime_profile, "market_data_read_enabled", False))
        try:
            from .runtime_profile import active_runtime_profile
            return bool(active_runtime_profile().market_data_read_enabled)
        except Exception:
            return False

    def _mt5_market_data_read_enabled(self):
        if self.runtime_profile is not None:
            return bool(getattr(self.runtime_profile, "mt5_market_data_read_enabled", False))
        try:
            from .runtime_profile import active_runtime_profile
            return bool(active_runtime_profile().mt5_market_data_read_enabled)
        except Exception:
            return False

    def _market_read_models_enabled(self):
        if self.runtime_profile is not None:
            return bool(getattr(self.runtime_profile, "market_read_models_enabled", True))
        try:
            from .runtime_profile import active_runtime_profile
            return bool(active_runtime_profile().market_read_models_enabled)
        except Exception:
            return False

    @staticmethod
    def _source_disabled(capability_id, source_module):
        return _envelope(capability_id, {
            "ok": False,
            "status": "SOURCE_DISABLED",
            "availability": "SOURCE_DISABLED",
            "reason": "MT5_DISABLED_BY_PROFILE",
            "source": "MT5",
            "execution_authority": "NONE",
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
        return {"ok": True, "read_only": True, "execution_authority": "NONE",
                "capabilities": capabilities, "count": len(capabilities),
                "authority": "JarvisService",
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

    def statistics_snapshot(self) -> dict[str, Any]:
        """Project journal statistics without the legacy dashboard cache write."""
        def read():
            from statistics_engine import get_engine
            engine = get_engine()
            return {
                "strategy_performance": engine.get_strategy_performance(),
                "asset_performance": engine.get_asset_performance(),
                "hourly_performance": engine.get_hourly_performance(),
                "regime_performance": engine.get_regime_performance(),
                "mode_performance": engine.get_mode_performance(),
                "score_calibration": engine.get_score_calibration(),
                "walk_forward": engine.get_walk_forward(),
                "confidence_status": engine.get_confidence_status(),
                "observed_at": _now(),
                "source": "trade_journal.jsonl",
                "source_limit": 10000,
                "source_scope": "up to 10000 journal records per aggregate",
                "record_selection": "resolved result labels only; source provenance is mixed and unverified",
                "execution_provenance": "NOT_VERIFIED",
                "mt5_imports_proven_as_real_account_trades": False,
                "execution_logger_limitation": (
                    "AUTO_TRADE execution fields may be lost because log_analysis "
                    "stores PENDING/false/0; no execution is proven by this Journal"),
                "read_only": True,
                "execution_authority": "NONE",
                "cache_written": False,
            }
        return _safe("golden.statistics", "statistics_engine.py", read,
                     evidence_class="HISTORICAL_EVIDENCE")

    def trade_journal_history(self, symbol="", record_type="ALL",
                              limit=10, offset=0, date_from="", date_to="",
                              exit_type="ALL") -> dict[str, Any]:
        """Expose a bounded allowlisted Journal page through the canonical bridge."""
        def read():
            from trade_journal import TradeJournal
            result = TradeJournal().get_history_page(
                symbol=symbol, record_type=record_type, limit=limit,
                offset=offset, date_from=date_from, date_to=date_to,
                exit_type=exit_type)
            if isinstance(result, dict):
                result = {**result, "read_only": True,
                          "execution_authority": "NONE"}
            return result
        return _safe("golden.trade_journal.history", "trade_journal.jsonl", read,
                     evidence_class="HISTORICAL_EVIDENCE")

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

    def panel_symbol_discovery(self, query: str = "", asset_class: str = "ALL",
                               correlation_id: str = "") -> dict[str, Any]:
        """Discover provider instruments without granting execution authority."""
        query = str(query or "").strip()[:64]
        kind = str(asset_class or "ALL").strip().upper()
        if not self._market_read_models_enabled():
            return _envelope("golden.panel.symbol_discovery", {
                "ok": False, "status": "SOURCE_DISABLED", "query": query,
                "asset_class": kind, "assets": [], "sources": {},
                "reason": "MARKET_READ_MODELS_DISABLED_BY_PROFILE",
                "execution_authority": "NONE"}, "market_data.py",
                correlation_id=correlation_id)
        if kind not in {"ALL", "FOREX", "INDICES", "STOCKS", "ETF", "CRYPTO",
                        "COMMODITIES", "METALS", "OTHER", "OTHER_UNKNOWN"}:
            return _envelope("golden.panel.symbol_discovery", {
                "ok": False, "status": "INVALID_QUERY", "query": query,
                "asset_class": kind, "assets": [],
                "reason": "SUPPORTED_ASSET_CLASS_REQUIRED",
                "execution_authority": "NONE"}, "market_data.py",
                correlation_id=correlation_id)

        assets = []
        sources = {
            "MT5": {"status": "SOURCE_DISABLED_BY_PROFILE" if not self._mt5_market_data_read_enabled()
                     else "NOT_QUERIED", "read_only": True},
        }
        if kind in {"ALL", "CRYPTO", "FOREX", "METALS", "INDICES", "COMMODITIES",
                    "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"}:
            if self._mt5_market_data_read_enabled():
                try:
                    from .tools.market_readonly import mt5_search_symbols
                    result = mt5_search_symbols(query, kind)
                    sources["MT5"] = {"status": result.get("status", "SOURCE_UNAVAILABLE"),
                                      "observed_at": result.get("observed_at"),
                                      "reason": result.get("reason"), "read_only": True,
                                      "classification_counts": result.get("classification_counts", {}),
                                      "enumerated_count": result.get("enumerated_count", 0)}
                    assets.extend(result.get("assets", []))
                except Exception as exc:
                    sources["MT5"] = {"status": "SOURCE_UNAVAILABLE",
                                      "reason": type(exc).__name__, "read_only": True}
            else:
                sources["MT5"] = {"status": "SOURCE_DISABLED_BY_PROFILE", "read_only": True}

        assets.sort(key=lambda item: (str(item.get("asset_class") or ""),
                                      str(item.get("display_name") or "").casefold(),
                                      item.get("provider", ""),
                                      str(item.get("provider_symbol") or "")))
        if assets:
            status = "AVAILABLE"
        elif (kind in {"ALL", "FOREX", "METALS", "CRYPTO", "INDICES", "COMMODITIES",
                       "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"}
              and sources.get("MT5", {}).get("status") in
              {"SOURCE_DISABLED_BY_PROFILE", "SOURCE_DISABLED"}):
            status = "SOURCE_DISABLED"
        elif sources.get("MT5", {}).get("status") == "SOURCE_UNAVAILABLE":
            status = "SOURCE_UNAVAILABLE"
        else:
            status = "NO_MATCH"
        payload = {
            "ok": status == "AVAILABLE", "status": status,
            "query": query, "asset_class": kind, "assets": assets,
            "sources": sources, "observed_at": _now(),
            "execution_authority": "NONE", "read_only": True,
            "fallback_catalog_used": False,
        }
        result = _envelope("golden.panel.symbol_discovery", payload,
                           "market_data.py + market_readonly.py",
                           correlation_id=correlation_id)
        return result

    def panel_market_snapshot(self, provider: str, provider_asset_id: str,
                              provider_symbol: str, asset_class: str,
                              timeframe: str = "M15", count: int = 120,
                              correlation_id: str = "") -> dict[str, Any]:
        """Read one verified selected-asset snapshot through Jarvis-owned providers."""
        provider = str(provider or "").strip()[:40]
        asset_id = str(provider_asset_id or "").strip()[:96]
        symbol = str(provider_symbol or "").strip()[:64]
        kind = str(asset_class or "").strip().upper()[:24]
        timeframe = str(timeframe or "M15").strip().upper()[:8]
        if not self._market_data_read_enabled():
            payload = {"ok": False, "status": "SOURCE_DISABLED",
                       "reason": "MARKET_DATA_READ_DISABLED_BY_PROFILE"}
        elif not symbol or kind not in {"FOREX", "METALS", "CRYPTO", "INDICES", "COMMODITIES",
                                       "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"}:
            payload = {"ok": False, "status": "INVALID_REQUEST", "reason": "ASSET_IDENTITY_REQUIRED"}
        elif provider != "MT5" or asset_id != f"mt5:{symbol}":
            payload = {"ok": False, "status": "IDENTITY_MISMATCH",
                       "reason": "MT5_PROVIDER_IDENTITY_NOT_RECONCILED"}
        elif not self._mt5_market_data_read_enabled():
            payload = {"ok": False, "status": "SOURCE_DISABLED",
                       "reason": "MT5_MARKET_DATA_READ_DISABLED_BY_PROFILE"}
        else:
            from .tools.market_readonly import mt5_market_data_snapshot
            payload = mt5_market_data_snapshot(symbol, timeframe, count)
            source_status = str(payload.get("status") or "").upper()
            asset = payload.get("asset") if isinstance(payload.get("asset"), dict) else {}
            provider_kind = str(asset.get("asset_class") or "").strip().upper()
            if source_status in {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED"}:
                pass
            elif provider_kind and provider_kind != kind:
                payload = {"ok": False, "status": "IDENTITY_MISMATCH",
                           "reason": "PROVIDER_CLASSIFICATION_CHANGED",
                           "provider_symbol": symbol}
            elif payload.get("ok") is True and not provider_kind:
                payload = {"ok": False, "status": "IDENTITY_UNVERIFIED",
                           "reason": "PROVIDER_CLASSIFICATION_UNAVAILABLE",
                           "provider_symbol": symbol}
        payload.setdefault("read_only", True)
        payload.setdefault("capability", "MT5_MARKET_DATA_READ" if provider == "MT5" else "MARKET_DATA_READ")
        payload.setdefault("execution_authority", "NONE")
        return _envelope("golden.panel.market_snapshot", payload,
                         "market_data.py + market_readonly.py",
                         correlation_id=correlation_id)

    @staticmethod
    def _trend_ranking_audit_summary(ranked, scan_metadata, correlation_id,
                                     snapshot_requests, available_snapshots,
                                     candles_returned, cache):
        metadata = scan_metadata if isinstance(scan_metadata, dict) else {}
        assets = []
        safe_frame_states = {"AVAILABLE", "STALE", "SOURCE_UNAVAILABLE",
                             "SOURCE_DISABLED", "INSUFFICIENT_DATA", "UNKNOWN"}
        for row in ranked:
            identity = row.get("asset") if isinstance(row.get("asset"), dict) else {}
            frames = row.get("evaluated_timeframes") if isinstance(row.get("evaluated_timeframes"), list) else []
            available = [str(frame.get("timeframe")) for frame in frames
                         if frame.get("status") == "AVAILABLE"]
            missing = []
            for frame in frames:
                frame_status = str(frame.get("status") or "UNKNOWN").upper()
                if frame_status == "AVAILABLE":
                    continue
                safe_status = frame_status if frame_status in safe_frame_states else "UNKNOWN"
                missing.append({"timeframe": str(frame.get("timeframe") or "UNKNOWN")[:8],
                                "status": safe_status, "error_code": safe_status})
            score = row.get("directional_score")
            if row.get("read_errors"):
                state = "FALHO"
            elif isinstance(score, (int, float)):
                state = "AVALIADO" if len(available) >= 3 else "DADOS INSUFICIENTES"
            elif frames and all(frame.get("status") in {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED"}
                                for frame in frames):
                state = "INDISPONÍVEL"
            else:
                state = "DADOS INSUFICIENTES"
            snapshots = {str(frame.get("timeframe"))[:8]: str(frame.get("snapshot_id"))[:96]
                         for frame in frames if frame.get("snapshot_id") not in {None, "", "UNKNOWN"}}
            assets.append({
                "provider": identity.get("provider", "MT5"),
                "provider_asset_id": identity.get("provider_asset_id", "UNKNOWN"),
                "provider_symbol": identity.get("provider_symbol", "UNKNOWN"),
                "display_symbol": identity.get("display_symbol", identity.get("provider_symbol", "UNKNOWN")),
                "display_name": identity.get("display_name", identity.get("provider_symbol", "UNKNOWN")),
                "asset_class": identity.get("asset_class", "UNKNOWN"),
                "asset_class_source": row.get("asset_class_source", "UNKNOWN"),
                "state": state, "directional_score": score,
                "trend": row.get("trend", "UNKNOWN"),
                "available_timeframes": available, "missing_timeframes": missing,
                "snapshot_ids": snapshots,
                "candles_returned": sum(int(frame.get("candle_count") or 0) for frame in frames),
                "freshness": row.get("freshness", "UNKNOWN"),
                "temporal_authority": row.get("temporal_authority", "UNKNOWN"),
                "timeframe_divergence": row.get("timeframe_divergence", "UNKNOWN"),
                "extended_trend_risk": row.get("extended_trend_risk", "UNKNOWN"),
                "terminal_identity_state": (
                    "ROOT_FINGERPRINT_OBSERVED_NOT_RECONCILED"
                    if row.get("terminal_data_root_fingerprints") else "UNKNOWN"),
                "terminal_data_root_fingerprints": row.get("terminal_data_root_fingerprints", []),
                "candles_in_snapshot_evidence": sum(
                    int(frame.get("candle_count") or 0) for frame in frames),
                "sanitized_errors": row.get("read_errors", []),
            })
        return {
            "schema": "trend-ranking-audit-v1",
            "scan_id": metadata.get("scan_id", "UNKNOWN"),
            "asset_class_filter": metadata.get("asset_class_filter", "ALL"),
            "universe_hash": metadata.get("universe_hash", "UNKNOWN"),
            "universe_hash_verification": "CLIENT_PROVIDED_NOT_RECOMPUTED_BY_CORE",
            "universe_total": metadata.get("universe_total", "UNKNOWN"),
            "excluded_count": metadata.get("excluded_count", 0),
            "excluded_reason_counts": metadata.get("excluded_reason_counts", {}),
            "catalog_source": metadata.get("catalog_source", "UNKNOWN"),
            "catalog_observation": metadata.get("catalog_observation", {}),
            "catalog_observation_verification": "CLIENT_REPORTED_NOT_REVALIDATED_BY_CORE",
            "batch_index": metadata.get("batch_index", "UNKNOWN"),
            "batch_total": metadata.get("batch_total", "UNKNOWN"),
            "batch_asset_ids": metadata.get("batch_asset_ids", []),
            "retry_of_failed_assets": metadata.get("retry_of_failed_assets", False),
            "correlation_id": correlation_id or "UNKNOWN",
            "assets": assets,
            "read_counts": {
                "snapshot_requests": snapshot_requests,
                "available_snapshots": available_snapshots,
                "candles_returned_this_request": candles_returned,
                "cache": cache,
                "per_asset_snapshot_request_limit": 7,
                "batch_snapshot_request_limit": TREND_RANKING_MAX_ASSETS * 7,
                "batch_candle_limit": TREND_RANKING_MAX_ASSETS * 7 * 100,
            },
            "provider": "MT5_READ_ONLY", "external_provider_calls": 0,
            "scanner_scores_used": False, "execution_authority": "NONE",
        }

    def panel_trend_ranking(self, assets: list[dict[str, Any]],
                            correlation_id: str = "",
                            scan_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rank one explicit, bounded MT5 batch using factual OHLC only."""
        allowed_classes = {"FOREX", "METALS", "CRYPTO", "INDICES", "COMMODITIES",
                           "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"}
        normalized = []
        seen = set()
        if not isinstance(assets, list) or not 1 <= len(assets) <= TREND_RANKING_MAX_ASSETS:
            return _envelope("golden.panel.trend_ranking", {
                "ok": False, "status": "INVALID_BATCH_SIZE", "assets": [],
                "maximum_assets": TREND_RANKING_MAX_ASSETS,
                "reason": "BATCH_MUST_CONTAIN_1_TO_4_IDENTITIES",
                "execution_authority": "NONE"}, "market_readonly.py",
                correlation_id=correlation_id)
        for row in assets:
            if not isinstance(row, dict):
                continue
            provider = str(row.get("provider") or "").strip().upper()
            symbol = str(row.get("provider_symbol") or "").strip()[:64]
            asset_id = str(row.get("provider_asset_id") or "").strip()[:96]
            kind = str(row.get("asset_class") or "").strip().upper()[:24]
            if (provider != "MT5" or not symbol.isascii()
                    or not symbol.replace(".", "").replace("_", "").replace("-", "").isalnum()
                    or asset_id != f"mt5:{symbol}" or kind not in allowed_classes):
                continue
            if asset_id in seen:
                continue
            seen.add(asset_id)
            normalized.append({
                "provider": provider, "provider_asset_id": asset_id,
                "provider_symbol": symbol, "symbol": symbol,
                "display_symbol": str(row.get("display_symbol") or symbol)[:64],
                "display_name": str(row.get("display_name") or symbol)[:120],
                "asset_class": kind,
                "asset_class_source": str(row.get("asset_class_source") or "")[:48],
            })
        if not normalized:
            return _envelope("golden.panel.trend_ranking", {
                "ok": False, "status": "INVALID_ASSET_IDENTITIES", "assets": [],
                "reason": "CANONICAL_MT5_IDENTITIES_REQUIRED",
                "execution_authority": "NONE"}, "market_readonly.py",
                correlation_id=correlation_id)
        if not self._market_data_read_enabled() or not self._mt5_market_data_read_enabled():
            return _envelope("golden.panel.trend_ranking", {
                "ok": False, "status": "SOURCE_DISABLED", "assets": [],
                "reason": "MT5_MARKET_DATA_READ_DISABLED_BY_PROFILE",
                "execution_authority": "NONE"}, "market_readonly.py",
                correlation_id=correlation_id)

        scan_metadata = scan_metadata if isinstance(scan_metadata, dict) else {}

        cache_key = tuple((item["provider_asset_id"], item["asset_class"])
                          for item in normalized)
        now = time.monotonic()
        with self._trend_ranking_lock:
            if self._trend_ranking_cache:
                cached_key, expires_at, cached_data = self._trend_ranking_cache
                if cached_key == cache_key and now < expires_at:
                    data = dict(cached_data)
                    data["cache"] = "HIT"
                    data["cache_ttl_seconds"] = 20
                    data["snapshot_requests"] = 0
                    data["available_snapshots"] = 0
                    data["candles_returned"] = 0
                    data["audit_summary"] = self._trend_ranking_audit_summary(
                        data.get("ranked_assets", []), scan_metadata, correlation_id,
                        0, 0, 0, "HIT")
                    return _envelope("golden.panel.trend_ranking", data,
                                     "market_readonly.py + GoldenReadBridge",
                                     correlation_id=correlation_id)

            from .tools.market_readonly import (
                _TREND_COMPONENT_WEIGHTS, _TREND_TIMEFRAMES, _TREND_WEIGHTS,
                rank_market_trend_frames,
            )

            ranked = []
            source_failures = 0
            snapshot_requests = 0
            available_snapshots = 0
            candles_returned = 0
            for asset in normalized:
                frames = {}
                terminal_fingerprints = set()
                asset_class_sources = set()
                read_errors = []
                for timeframe in _TREND_TIMEFRAMES:
                    snapshot_requests += 1
                    try:
                        snapshot_envelope = self.panel_market_snapshot(
                            asset["provider"], asset["provider_asset_id"],
                            asset["provider_symbol"], asset["asset_class"],
                            timeframe, 100, correlation_id)
                    except Exception as exc:
                        read_errors.append({"timeframe": timeframe,
                                            "error_code": type(exc).__name__[:64]})
                        snapshot_envelope = {"ok": False, "data": {
                            "ok": False, "status": "SOURCE_UNAVAILABLE",
                            "reason": "SNAPSHOT_READ_EXCEPTION"}}
                    snapshot = (snapshot_envelope.get("data")
                                if isinstance(snapshot_envelope, dict) else None)
                    snapshot = snapshot if isinstance(snapshot, dict) else {}
                    if snapshot.get("ok") is True:
                        available_snapshots += 1
                        candles = snapshot.get("candles")
                        candles_returned += len(candles) if isinstance(candles, list) else 0
                    provenance = snapshot.get("provenance")
                    data_root = (provenance.get("terminal_data_root")
                                 if isinstance(provenance, dict) else None)
                    if isinstance(data_root, str) and data_root.strip():
                        terminal_fingerprints.add(hashlib.sha256(
                            data_root.strip().encode("utf-8")).hexdigest())
                    actual = snapshot.get("asset") if isinstance(snapshot.get("asset"), dict) else {}
                    if (snapshot.get("ok") is True
                            and (actual.get("provider") != "MT5"
                                 or actual.get("asset_id") != asset["provider_asset_id"]
                                 or actual.get("provider_symbol") != asset["provider_symbol"]
                                 or actual.get("asset_class") != asset["asset_class"]
                                 or snapshot.get("timeframe") != timeframe)):
                        snapshot = {"ok": False, "status": "IDENTITY_MISMATCH",
                                    "reason": "SNAPSHOT_IDENTITY_OR_TIMEFRAME_MISMATCH"}
                    if snapshot.get("ok") is True:
                        class_source = str(actual.get("asset_class_source") or "").strip().upper()
                        if class_source:
                            asset_class_sources.add(class_source)
                    if snapshot.get("ok") is not True:
                        source_failures += 1
                    frames[timeframe] = snapshot
                ranked_row = rank_market_trend_frames(asset, frames)
                ranked_row["asset_class_source"] = (
                    next(iter(asset_class_sources)) if len(asset_class_sources) == 1
                    else "INCONSISTENT_OR_UNKNOWN")
                ranked_row["terminal_data_root_fingerprints"] = sorted(terminal_fingerprints)
                ranked_row["read_errors"] = read_errors
                ranked.append(ranked_row)

            ranked.sort(key=lambda item: (
                item.get("directional_score") is None,
                -(item.get("directional_score") or 0),
                item["asset"].get("provider_symbol", "")))
            data = {
                "ok": bool(ranked), "status": "AVAILABLE" if ranked else "NO_DATA",
                "ranked_assets": ranked, "assets_evaluated": len(normalized),
                "assets_requested": len(assets),
                "maximum_assets_per_batch": TREND_RANKING_MAX_ASSETS,
                "timeframes": list(_TREND_TIMEFRAMES), "candles_per_timeframe": 100,
                "maximum_ohlc_bars": len(normalized) * len(_TREND_TIMEFRAMES) * 100,
                "maximum_market_snapshot_reads": len(normalized) * len(_TREND_TIMEFRAMES),
                "snapshot_requests": snapshot_requests,
                "available_snapshots": available_snapshots,
                "candles_returned": candles_returned,
                "methodology": {
                    "version": "ohlc-trend-v1",
                    "timeframe_weights": dict(_TREND_WEIGHTS),
                    "component_weights": dict(_TREND_COMPONENT_WEIGHTS),
                    "score_bands": {"strong_up_min": 60, "up_min": 25,
                                     "lateral": [-24, 24], "down_max": -25,
                                     "strong_down_max": -60},
                    "minimum_coverage": {"timeframes": 3, "timeframe_groups": 2},
                    "score_semantics": "DIRECTIONAL_INTENSITY_NOT_PROBABILITY",
                },
                "source_failures": source_failures, "cache": "MISS",
                "cache_ttl_seconds": 20, "read_only": True,
                "provider_calls": 0, "scanner_scores_used": False,
                "macro_news_inputs": "NOT_USED_UNVERIFIED_TEMPORAL_SOURCES",
                "execution_authority": "NONE",
                "observed_at": _now(),
            }
            data["audit_summary"] = self._trend_ranking_audit_summary(
                ranked, scan_metadata, correlation_id, snapshot_requests,
                available_snapshots, candles_returned, "MISS")
            self._trend_ranking_cache = (cache_key, time.monotonic() + 20, data)
        return _envelope("golden.panel.trend_ranking", data,
                         "market_readonly.py + GoldenReadBridge",
                         correlation_id=correlation_id)

    def panel_market_update(self, provider: str, provider_asset_id: str,
                            provider_symbol: str, asset_class: str,
                            timeframe: str = "M15",
                            correlation_id: str = "") -> dict[str, Any]:
        provider = str(provider or "").strip()[:40]
        asset_id = str(provider_asset_id or "").strip()[:96]
        symbol = str(provider_symbol or "").strip()[:64]
        kind = str(asset_class or "").strip().upper()[:24]
        timeframe = str(timeframe or "M15").strip().upper()[:8]
        if not self._market_data_read_enabled() or not self._mt5_market_data_read_enabled():
            payload = {"ok": False, "status": "SOURCE_DISABLED",
                       "reason": "MT5_MARKET_DATA_READ_DISABLED_BY_PROFILE"}
        elif (provider != "MT5" or not symbol or asset_id != f"mt5:{symbol}"
              or kind not in {"FOREX", "METALS", "CRYPTO", "INDICES", "COMMODITIES",
                              "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"}):
            payload = {"ok": False, "status": "IDENTITY_MISMATCH",
                       "reason": "MT5_PROVIDER_IDENTITY_NOT_RECONCILED"}
        else:
            from .tools.market_readonly import mt5_market_data_update
            payload = mt5_market_data_update(symbol, timeframe)
            source_status = str(payload.get("status") or "").upper()
            provider_kind = str(payload.get("asset_class") or "").strip().upper()
            if source_status in {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED"}:
                pass
            elif provider_kind and provider_kind != kind:
                payload = {"ok": False, "status": "IDENTITY_MISMATCH",
                           "reason": "PROVIDER_CLASSIFICATION_CHANGED",
                           "provider_symbol": symbol}
            elif payload.get("ok") is True and not provider_kind:
                payload = {"ok": False, "status": "IDENTITY_UNVERIFIED",
                           "reason": "PROVIDER_CLASSIFICATION_UNAVAILABLE",
                           "provider_symbol": symbol}
        payload.setdefault("read_only", True)
        payload.setdefault("execution_authority", "NONE")
        return _envelope("golden.panel.market_update", payload,
                         "market_data.py + market_readonly.py",
                         correlation_id=correlation_id)

    def panel_macro_news(self, symbol: str, asset_class: str,
                         instrument: dict[str, Any] | None = None,
                         correlation_id: str = "") -> dict[str, Any]:
        """Project existing Golden macro/news facts without its derived trade bias."""
        from market_data import _economic_calendar, _macro_snapshot, _market_news, _pair_news
        from .market_read_models import normalize_events, normalize_macro, normalize_news

        instrument = instrument if isinstance(instrument, dict) else {}
        symbol = str(symbol or "").strip()[:64]
        asset_class = str(asset_class or "").strip().upper()[:24]
        now = _now()
        try:
            macro_raw = _macro_snapshot([])
            macro_rows = normalize_macro(macro_raw.get("indicators"))[:12]
            macro = {
                "status": "AVAILABLE" if macro_rows else "UNAVAILABLE",
                "observed_at": macro_raw.get("updated_at") or now,
                "source": "FRED/BCB",
                "freshness": UNKNOWN,
                "facts": macro_rows,
                "read_only": True,
            }
        except Exception as exc:
            macro = {"status": "UNAVAILABLE", "observed_at": now,
                     "source": "market_data._macro_snapshot",
                     "freshness": UNKNOWN, "facts": [],
                     "reason": type(exc).__name__, "read_only": True}

        try:
            rows, calendar_state = _economic_calendar()
            currencies = {str(instrument.get(key) or "").upper()
                          for key in ("currency_base", "currency_quote")}
            currencies.discard("")
            relevant = [row for row in rows if not currencies or
                        str(row.get("currency") or "").upper() in currencies]
            event_rows = normalize_events(relevant)[:12]
            events = {
                "status": "AVAILABLE" if event_rows else "UNAVAILABLE",
                "observed_at": now,
                "source": "Trading Economics" if calendar_state == "online" else calendar_state,
                "freshness": UNKNOWN,
                "facts": event_rows,
                "read_only": True,
            }
        except Exception as exc:
            events = {"status": "UNAVAILABLE", "observed_at": now,
                      "source": "market_data._economic_calendar",
                      "freshness": UNKNOWN, "facts": [],
                      "reason": type(exc).__name__, "read_only": True}

        try:
            base = str(instrument.get("currency_base") or "").upper()
            quote = str(instrument.get("currency_quote") or "").upper()
            if asset_class == "FOREX" and base and quote:
                rows, news_source = _pair_news(base, quote)
            else:
                rows, news_source = _market_news()
            news_rows = normalize_news(rows)[:8]
            news = {"status": "AVAILABLE" if news_rows else "UNAVAILABLE",
                    "observed_at": now, "source": news_source or "UNKNOWN",
                    "freshness": UNKNOWN, "facts": news_rows,
                    "read_only": True}
        except Exception as exc:
            news = {"status": "UNAVAILABLE", "observed_at": now,
                    "source": "market_data news cache", "freshness": UNKNOWN,
                    "facts": [], "reason": type(exc).__name__, "read_only": True}

        payload = {
            "ok": True, "status": "AVAILABLE",
            "symbol": symbol, "asset_class": asset_class,
            "macro": macro, "economic_events": events, "news": news,
            "observed_at": now, "correlation_id": str(correlation_id or "")[:120],
            "read_only": True, "execution_authority": "NONE",
        }
        return _envelope("golden.panel.factual_context", payload,
                         "market_data.py", correlation_id=correlation_id)

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

    def robot_intelligence_snapshot(self, symbol: str = "", timeframe: str = "M15",
                                    robot_id: str = "", correlation_id: str = "") -> dict[str, Any]:
        """Compose catalog evidence and market context without execution authority."""
        from .robot_intelligence import build_robot_intelligence_snapshot

        catalog = self.robot_catalog_summary()
        if robot_id:
            data = catalog.get("data") if isinstance(catalog.get("data"), dict) else {}
            robots = [item for item in data.get("robots", [])
                      if str(item.get("robot_id")) == str(robot_id)]
            catalog = dict(catalog)
            catalog["data"] = dict(data)
            catalog["data"]["robots"] = robots
        market = self.market_intelligence_snapshot(symbol or "XAUUSD", timeframe, correlation_id)
        result = build_robot_intelligence_snapshot(
            catalog, market, symbol=symbol or "XAUUSD", timeframe=timeframe,
            correlation_id=correlation_id,
        )
        result["provenance"] = {
            **result.get("provenance", {}),
            "catalog_envelope": catalog.get("provenance", {}),
            "market_snapshot_id": market.get("snapshot_id", "UNKNOWN"),
        }
        return result

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
            "observed_at": _now(),
            "execution_authority": "NONE",
            "read_only": True,
        })

    def control_center_snapshot(self, symbol: str = "", include_live: bool = False) -> dict[str, Any]:
        payload = {
            "ok": True,
            "read_only": True,
            "execution_authority": "NONE",
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

