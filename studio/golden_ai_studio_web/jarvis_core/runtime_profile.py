"""Explicit startup capability profiles for the canonical Jarvis runtime."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeProfile:
    """Runtime capabilities; the default preserves the historical startup."""

    name: str
    web_enabled: bool = True
    gateway_enabled: bool = True
    ai_enabled: bool = True
    memory_enabled: bool = True
    security_enabled: bool = True
    audit_enabled: bool = True
    market_read_models_enabled: bool = True
    market_data_read_enabled: bool = False
    mt5_market_data_read_enabled: bool = False
    mt5_enabled: bool = True
    voice_enabled: bool = True
    trading_enabled: bool = True
    strategy_tester_enabled: bool = True
    mql5_compile_enabled: bool = True
    monitor_enabled: bool = True

    def status(self) -> dict[str, Any]:
        return {
            "runtime_profile": self.name,
            "web": "ENABLED" if self.web_enabled else "DISABLED_BY_PROFILE",
            "gateway": "ENABLED" if self.gateway_enabled else "DISABLED_BY_PROFILE",
            "ai": "ENABLED" if self.ai_enabled else "DISABLED_BY_PROFILE",
            "memory": "ENABLED" if self.memory_enabled else "DISABLED_BY_PROFILE",
            "security": "ENABLED" if self.security_enabled else "DISABLED_BY_PROFILE",
            "audit": "ENABLED" if self.audit_enabled else "DISABLED_BY_PROFILE",
            "market_read_models": (
                "ENABLED" if self.market_read_models_enabled else "DISABLED_BY_PROFILE"),
            "market_data_read": (
                "ENABLED" if self.market_data_read_enabled else "DISABLED_BY_PROFILE"),
            "mt5_market_data_read": (
                "ENABLED" if self.mt5_market_data_read_enabled else "DISABLED_BY_PROFILE"),
            "mt5": "ENABLED" if self.mt5_enabled else "DISABLED_BY_PROFILE",
            "voice": "ENABLED" if self.voice_enabled else "DISABLED_BY_PROFILE",
            "trading": "ENABLED" if self.trading_enabled else "DISABLED_BY_PROFILE",
            "strategy_tester": (
                "ENABLED" if self.strategy_tester_enabled else "DISABLED_BY_PROFILE"),
            "mql5_compile": (
                "ENABLED" if self.mql5_compile_enabled else "DISABLED_BY_PROFILE"),
        }

    def tool_disabled_reason(self, tool_name: str) -> str:
        name = str(tool_name or "").lower()
        if name in {"golden_panel_market_snapshot", "golden_panel_market_update",
                    "golden_panel_analysis", "golden_panel_symbol_discovery"} and not self.market_data_read_enabled:
            return "MARKET_DATA_READ_DISABLED_BY_PROFILE"
        if not self.mt5_enabled and (
                name.startswith("mt5_") or name in {"golden_mt5_read_snapshot"}):
            return "MT5_DISABLED_BY_PROFILE"
        if not self.strategy_tester_enabled and name.startswith("strategy_tester"):
            return "STRATEGY_TESTER_DISABLED_BY_PROFILE"
        # This exact capability is an allowlisted Journal read, not trade authority.
        # JarvisService registers it READ_ONLY and requires per-request human approval.
        if name == "golden_trade_journal_history":
            return ""
        if not self.trading_enabled and any(
                marker in name for marker in
                ("order", "position", "trade", "autotrading", "auto_trading",
                 "broker_mutation")):
            return "TRADING_DISABLED_BY_PROFILE"
        return ""

    def api_disabled_reason(self, path: str) -> str:
        path = str(path or "").lower()
        legacy_mt5_paths = (
            path.startswith("/api/mt5/"),
            path.startswith("/api/ea/"),
            path.startswith("/api/chart_"),
            path in {"/api/meta_strategy", "/api/walk_forward"},
            path.startswith("/api/scanner/"),
            path.startswith("/api/statistics/"),
            path.startswith("/api/risk/"),
            path.startswith("/api/validation/"),
            path in {"/api/strategy_catalog", "/api/strategy_audit",
                     "/api/strategy_matrix", "/api/portfolio_backtest"},
        )
        if not self.mt5_enabled and any(legacy_mt5_paths):
            return "MT5_DISABLED_BY_PROFILE"
        if not self.strategy_tester_enabled and (
                "backtest" in path or "strategy_test" in path or
                path.startswith("/api/strategy_tester")):
            return "STRATEGY_TESTER_DISABLED_BY_PROFILE"
        if not self.mql5_compile_enabled and (
                "/compile" in path or path.startswith("/api/ea/")):
            return "MQL5_COMPILE_DISABLED_BY_PROFILE"
        if not self.voice_enabled and (
                path == "/api/audio" or path == "/api/desktop/speech" or
                path.startswith("/api/jarvis/voice")):
            return "VOICE_DISABLED_BY_PROFILE"
        if not self.trading_enabled and (
                "auto_trade" in path or "/position/" in path or
                "/strategy_manager/" in path):
            return "TRADING_DISABLED_BY_PROFILE"
        return ""


DEFAULT_PROFILE = RuntimeProfile(name="default")
WEB_AI_SAFE_PROFILE = RuntimeProfile(
    name="web-ai-safe",
    market_data_read_enabled=True,
    mt5_market_data_read_enabled=True,
    mt5_enabled=False,
    voice_enabled=False,
    trading_enabled=False,
    strategy_tester_enabled=False,
    mql5_compile_enabled=False,
    monitor_enabled=False,
)

_PROFILES = {
    DEFAULT_PROFILE.name: DEFAULT_PROFILE,
    WEB_AI_SAFE_PROFILE.name: WEB_AI_SAFE_PROFILE,
    "web_ai_safe": WEB_AI_SAFE_PROFILE,
    "WEB_AI_SAFE": WEB_AI_SAFE_PROFILE,
}
_ACTIVE_PROFILE = DEFAULT_PROFILE


def resolve_runtime_profile(value: Any = None) -> RuntimeProfile:
    if isinstance(value, RuntimeProfile):
        return value
    name = str(value or DEFAULT_PROFILE.name).strip()
    profile = _PROFILES.get(name) or _PROFILES.get(name.lower())
    if profile is None:
        valid = ", ".join((DEFAULT_PROFILE.name, WEB_AI_SAFE_PROFILE.name))
        raise ValueError("Perfil de runtime invalido: %s. Use: %s" % (name, valid))
    return profile


def set_active_runtime_profile(value: Any = None) -> RuntimeProfile:
    global _ACTIVE_PROFILE
    _ACTIVE_PROFILE = resolve_runtime_profile(value)
    return _ACTIVE_PROFILE


def active_runtime_profile() -> RuntimeProfile:
    return _ACTIVE_PROFILE
