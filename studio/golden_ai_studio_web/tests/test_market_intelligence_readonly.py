from types import SimpleNamespace

from jarvis_core.models import Risk
from jarvis_core.orchestrator import CentralOrchestrator
from jarvis_core.orchestrator.models import ModelProfile, Route
from jarvis_core.registry import ToolRegistry
from jarvis_core.service import JarvisService
from jarvis_core.tools import market_readonly as market


class _FakeMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def __init__(self):
        self.symbol = SimpleNamespace(
            name="XAUUSD", description="Gold vs US Dollar", digits=2, point=0.01,
            trade_tick_size=0.01, trade_tick_value=1.0, volume_min=0.01,
            volume_max=100.0, volume_step=0.01, trade_mode=4,
            currency_base="XAU", currency_profit="USD",
        )
        self.account = SimpleNamespace(
            login=123456, server="Demo", currency="USD", balance=1000.0,
            equity=998.0, margin=10.0, margin_free=988.0,
            margin_level=9980.0, profit=-2.0,
        )

    def terminal_info(self):
        return SimpleNamespace(name="MetaTrader 5", connected=True)

    def account_info(self):
        return self.account

    def symbol_info(self, symbol):
        return self.symbol if symbol == "XAUUSD" else None

    def symbols_get(self):
        return [SimpleNamespace(name="XAUUSDm"), SimpleNamespace(name="EURUSD")]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=2300.10, ask=2300.30, last=2300.20, time=123)

    def positions_get(self):
        return [SimpleNamespace(symbol="XAUUSD", type=0, volume=0.1,
                                price_open=2290.0, price_current=2300.2,
                                sl=2280.0, tp=2320.0, profit=10.0,
                                swap=0.0, ticket=7)]

    def orders_get(self):
        return [SimpleNamespace(symbol="XAUUSD", type=2, volume_current=0.2,
                                volume_initial=0.2, price_open=2295.0,
                                sl=0.0, tp=0.0, ticket=8)]

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return [SimpleNamespace(time=100 + i, open=2300.0 + i,
                                high=2301.0 + i, low=2299.0 + i,
                                close=2300.5 + i, tick_volume=10 + i,
                                real_volume=5 + i) for i in range(min(count, 3))]


def _market_router():
    registry = ToolRegistry()
    names = (
        "mt5_status", "mt5_account_info", "mt5_positions", "mt5_orders",
        "mt5_symbol_tick", "mt5_symbol_info", "mt5_recent_candles",
        "golden_status", "golden_scanner_status", "golden_scanner_results",
        "golden_risk_status", "web_research",
    )
    for name in names:
        registry.register(SimpleNamespace(name=name))
    return CentralOrchestrator(registry, mode="on")


def test_readonly_mt5_adapters_return_structured_connected_state(monkeypatch):
    fake = _FakeMT5()
    monkeypatch.setattr(market, "_connection",
                        lambda: (fake, fake.terminal_info(), fake.account, ""))

    connected_reads = [
        market.mt5_status(), market.mt5_account_info(), market.mt5_positions(),
        market.mt5_orders(), market.mt5_symbol_tick("XAUUSD"),
        market.mt5_symbol_info("XAUUSD"),
    ]
    assert all(item["read_only"] is True for item in connected_reads)
    assert all(item["execution_authority"] == "NONE" for item in connected_reads)
    assert market.mt5_status()["status"] == "CONNECTED"
    assert market.mt5_account_info()["account"]["login"] == "***3456"
    assert market.mt5_positions()["count"] == 1
    assert market.mt5_orders()["count"] == 1
    assert market.mt5_symbol_tick("XAUUSD")["source"] == "MT5"
    assert market.mt5_symbol_info("XAUUSD")["info"]["digits"] == 2
    candles = market.mt5_recent_candles("XAUUSD", "M5", 999)
    assert candles["read_only"] is True
    assert candles["execution_authority"] == "NONE"
    assert candles["count"] == 3
    assert candles["timeframe"] == "M5"


def test_symbol_resolution_does_not_silently_guess(monkeypatch):
    fake = _FakeMT5()
    monkeypatch.setattr(market, "_connection",
                        lambda: (fake, fake.terminal_info(), fake.account, ""))
    result = market.mt5_symbol_tick("XAU")
    assert result["status"] == "NOT_FOUND"
    assert result["suggestions"] == ["XAUUSDm"]


def test_offline_mt5_is_structured_not_generic_exception(monkeypatch):
    monkeypatch.setattr(market, "_connection", lambda: (None, None, None, "terminal offline"))
    result = market.mt5_status()
    assert result["ok"] is True
    assert result["status"] == "OFFLINE"
    assert result["connected"] is False
    assert "error" not in result


def test_readonly_adapter_source_has_no_execution_boundary():
    source = open(market.__file__, encoding="utf-8").read()
    for forbidden in ("order_send", "send_order", "close_position", "modify_position"):
        assert forbidden not in source


def test_market_analysis_routes_readonly_plan_for_multiple_assets():
    router = _market_router()
    for query, symbol in (
        ("analise XAUUSD", "XAUUSD"),
        ("como está o ouro?", "XAUUSD"),
        ("qual tendência do EURUSD", "EURUSD"),
    ):
        decision = router.decide(query)
        assert decision.route == Route.MARKET_ANALYSIS
        assert decision.intent == "market_analysis"
        assert decision.preferred_model_profile == ModelProfile.MARKET
        assert len(decision.steps) == 10
        assert decision.steps[2].args["symbol"] == symbol
        assert decision.steps[-1].tool == "web_research"
        assert decision.answer_route == "TOOL_PLUS_RESEARCH"


def test_market_direct_mt5_queries_and_legacy_trading_route():
    router = _market_router()
    assert router.decide("qual o status do MT5?").steps[0].tool == "mt5_status"
    assert router.decide("qual o preço atual do XAUUSD?").steps[0].tool == "mt5_symbol_tick"
    assert router.decide("analise o ouro").route == Route.TRADING


def test_service_registers_readonly_tools_with_low_risk(tmp_path):
    service = JarvisService(str(tmp_path))
    names = {
        "mt5_status", "mt5_account_info", "mt5_positions", "mt5_orders",
        "mt5_symbol_tick", "mt5_symbol_info", "mt5_recent_candles",
        "golden_status", "golden_scanner_status", "golden_scanner_results",
        "golden_risk_status",
    }
    assert names <= set(service.registry._tools)
    assert all(service.registry.get(name).risk == Risk.LOW for name in names)
    assert service.registry.get("order_send") is None
    assert service.registry.get("send_order") is None
    assert service.registry.validate() == []


def test_market_plan_continues_when_web_is_optional_failure():
    service = JarvisService.__new__(JarvisService)
    service.registry = ToolRegistry()
    service.audit = SimpleNamespace(add=lambda **kwargs: None)
    for name in ("mt5_status", "web_research"):
        service.registry.register(SimpleNamespace(name=name, risk=Risk.LOW))
    service._prepare_execution = lambda tool, args: (args, Risk.LOW, False, "")
    service.execute_tool = lambda name, arguments, command="", task_id="": {
        "ok": name != "web_research", "tool": name,
    }

    class _Brain:
        orchestrator = SimpleNamespace(last_decision=SimpleNamespace(
            data_classification="INTERNAL", route=Route.MARKET_ANALYSIS))

        @staticmethod
        def _validate_plan(plan):
            return None

        @staticmethod
        def clear_steps():
            return None

        @staticmethod
        def synthesize_tool_results(command, executions):
            return {"ok": True, "response": "análise baseada nos dados disponíveis",
                    "provider": "gemini"}

    result = service._execute_plan(_Brain(), "analise XAUUSD", {
        "steps": [
            {"tool": "mt5_status", "args": {}, "intent": "market_analysis"},
            {"tool": "web_research", "args": {}, "intent": "market_analysis"},
        ]
    }, "test")
    assert result["ok"] is True
    assert len(result["executions"]) == 2
    assert result["executions"][1]["ok"] is False

