from types import SimpleNamespace
from pathlib import Path

import pytest

from jarvis_core.runtime_profile import (
    DEFAULT_PROFILE, WEB_AI_SAFE_PROFILE, set_active_runtime_profile,
)
from jarvis_core.tools import market_readonly as market
import market_data


@pytest.fixture
def safe_market_profile():
    set_active_runtime_profile(WEB_AI_SAFE_PROFILE)
    try:
        yield
    finally:
        set_active_runtime_profile(DEFAULT_PROFILE)


def _process(pid, executable):
    return SimpleNamespace(pid=pid, info={"name": "terminal64.exe", "exe": executable})


class _FakeMT5:
    def __init__(self, profiles):
        self.profiles = profiles
        self.active_path = None
        self.initialize_calls = []
        self.shutdown_calls = 0

    def initialize(self, *, path, timeout, portable):
        self.initialize_calls.append((path, timeout, portable))
        self.active_path = path
        return self.profiles[path].get("initialize", True)

    def shutdown(self):
        self.shutdown_calls += 1
        self.active_path = None

    def terminal_info(self):
        profile = self.profiles[self.active_path]
        return SimpleNamespace(
            connected=profile.get("connected", True),
            name=profile.get("terminal_name", "MetaTrader 5"),
            company=profile.get("company", ""),
            data_path=profile.get("data_path", "C:\\MT5\\data"),
        )

    def account_info(self):
        profile = self.profiles[self.active_path]
        return SimpleNamespace(
            server=profile.get("server", "Broker-Demo"),
            company=profile.get("company", ""),
            login=profile.get("login", 1234),
        )


def _install_fake_mt5(monkeypatch, processes, profiles):
    fake = _FakeMT5(profiles)
    monkeypatch.setitem(
        __import__("sys").modules,
        "psutil",
        SimpleNamespace(process_iter=lambda _attrs: processes),
    )
    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", fake)
    return fake


def test_market_connection_prefers_hantec_among_open_terminals(monkeypatch, safe_market_profile):
    other = r"C:\Brokers\Other\terminal64.exe"
    hantec = r"C:\Brokers\Hantec\terminal64.exe"
    fake = _install_fake_mt5(
        monkeypatch,
        [_process(10, other), _process(11, hantec)],
        {other: {"server": "Other-Demo"}, hantec: {"server": "HantecMarkets-Demo"}},
    )

    mt5, terminal, reason = market._market_data_connection()

    assert reason == ""
    assert mt5 is fake
    assert terminal.connected is True
    assert fake.active_path == hantec


def test_market_connection_accepts_one_non_hantec_terminal(monkeypatch, safe_market_profile):
    path = r"C:\Brokers\Pepperstone\terminal64.exe"
    fake = _install_fake_mt5(monkeypatch, [_process(12, path)], {path: {"server": "Pepperstone-Demo"}})

    mt5, _terminal, reason = market._market_data_connection()

    assert reason == ""
    assert mt5 is fake
    assert fake.active_path == path


def test_market_connection_fails_closed_for_multiple_non_hantec_terminals(monkeypatch, safe_market_profile):
    first = r"C:\Brokers\First\terminal64.exe"
    second = r"C:\Brokers\Second\terminal64.exe"
    fake = _install_fake_mt5(
        monkeypatch,
        [_process(13, first), _process(14, second)],
        {first: {"server": "First-Demo"}, second: {"server": "Second-Demo"}},
    )

    mt5, terminal, reason = market._market_data_connection()

    assert mt5 is None and terminal is None
    assert reason == "MT5_TERMINAL_AMBIGUOUS"
    assert fake.active_path is None


def test_market_connection_does_not_initialize_when_no_mt5_process_is_open(monkeypatch, safe_market_profile):
    fake = _install_fake_mt5(monkeypatch, [], {})

    mt5, terminal, reason = market._market_data_connection()

    assert mt5 is None and terminal is None
    assert reason == "NO_OPEN_MT5_TERMINAL"
    assert fake.initialize_calls == []


def test_market_connection_rechecks_process_before_initialize(monkeypatch, safe_market_profile):
    path = r"C:\Brokers\Hantec\terminal64.exe"
    candidate = {"pid": 17, "executable": path, "process_name": "terminal64.exe"}
    fake = _install_fake_mt5(monkeypatch, [], {path: {"server": "HantecMarkets-Demo"}})
    discoveries = iter(([candidate], []))
    monkeypatch.setattr(market, "_discover_open_mt5_terminals",
                        lambda: next(discoveries))

    mt5, terminal, reason = market._market_data_connection()

    assert mt5 is None and terminal is None
    assert reason == "MT5_TERMINAL_NOT_CONNECTED"
    assert fake.initialize_calls == []


def test_market_connection_tries_next_candidate_after_disconnected_terminal(monkeypatch, safe_market_profile):
    disconnected = r"C:\Brokers\Disconnected\terminal64.exe"
    available = r"C:\Brokers\Available\terminal64.exe"
    fake = _install_fake_mt5(
        monkeypatch,
        [_process(15, disconnected), _process(16, available)],
        {
            disconnected: {"server": "Disconnected-Demo", "connected": False},
            available: {"server": "Available-Demo", "connected": True},
        },
    )

    mt5, _terminal, reason = market._market_data_connection()

    assert reason == ""
    assert mt5 is fake
    assert fake.active_path == available


def test_connection_uses_shared_readonly_attach_instead_of_legacy_connector(monkeypatch):
    terminal = SimpleNamespace(connected=True)
    account = SimpleNamespace(server="HantecMarkets-Demo")
    fake = SimpleNamespace(account_info=lambda: account)
    monkeypatch.setattr(market, "_market_data_connection", lambda: (fake, terminal, ""))
    monkeypatch.setitem(
        __import__("sys").modules,
        "mt5_connector",
        SimpleNamespace(ensure_connection=lambda: (_ for _ in ()).throw(
            AssertionError("legacy connector must not be used"))),
    )
    result = market._connection()

    assert result == (fake, terminal, account, "")


def test_readonly_connection_is_allowed_when_trading_is_disabled(monkeypatch, safe_market_profile):
    terminal = SimpleNamespace(connected=True)
    account = SimpleNamespace(server="HantecMarkets-Demo")
    fake = SimpleNamespace(account_info=lambda: account)
    monkeypatch.setattr(market, "_market_data_connection", lambda: (fake, terminal, ""))

    result = market._connection()

    assert result == (fake, terminal, account, "")


def test_default_profile_exposes_market_reads_without_changing_execution_authority():
    assert DEFAULT_PROFILE.market_data_read_enabled is True
    assert DEFAULT_PROFILE.mt5_market_data_read_enabled is True
    assert DEFAULT_PROFILE.trading_enabled is True


def test_gold_path_is_classified_as_metals_even_with_broker_usd_metadata():
    info = SimpleNamespace(path="Gold\\XAUUSD", currency_base="USD", currency_profit="USD")
    fake_mt5 = SimpleNamespace()

    assert market._classify_mt5_instrument(info, fake_mt5) == (
        "METALS", "MT5_SYMBOL_PATH_GROUP")


def test_market_snapshot_exposes_top_level_readonly_contract(monkeypatch):
    class _SnapshotMT5:
        TIMEFRAME_M15 = 15

        def symbol_info(self, symbol):
            return SimpleNamespace(name=symbol, description="Gold vs US Dollar",
                                   path="Gold\\XAUUSD", currency_base="USD",
                                   currency_profit="USD", digits=2, point=0.01,
                                   trade_tick_size=0.01)

        def symbol_info_tick(self, _symbol):
            return SimpleNamespace(bid=4070.0, ask=4071.0, last=4070.5,
                                   time=1794079300, time_msc=1794079300000)

        def copy_rates_from_pos(self, _symbol, _timeframe, _start, count):
            return [SimpleNamespace(time=1794079300 - (count - index) * 900,
                                    open=4000.0 + index, high=4001.0 + index,
                                    low=3999.0 + index, close=4000.5 + index,
                                    tick_volume=10, real_volume=0)
                    for index in range(count)]

    monkeypatch.setattr(market, "_market_data_connection",
                        lambda: (_SnapshotMT5(), SimpleNamespace(data_path="hantec"), ""))

    result = market.mt5_market_data_snapshot("XAUUSD", "M15", 60)

    assert result["provider"] == "MT5"
    assert result["provider_symbol"] == "XAUUSD"
    assert result["read_only"] is True
    assert result["execution_authority"] == "NONE"


def test_canonical_market_data_errors_keep_readonly_contract():
    results = [
        market.mt5_market_data_snapshot("", "M15", 60),
        market.mt5_market_data_update("", "M15"),
    ]

    for result in results:
        assert result["provider"] == "MT5"
        assert result["read_only"] is True
        assert result["execution_authority"] == "NONE"


def test_legacy_market_data_source_uses_shared_readonly_boundary():
    source = Path(market_data.__file__).read_text(encoding="utf-8")

    assert "get_readonly_mt5_connection" in source
    assert "ensure_connection" not in source
    assert "symbol_select" not in source


def test_legacy_market_tick_reads_through_shared_connection_without_mutation(monkeypatch):
    class _MarketDataMT5:
        def symbol_info(self, symbol):
            return SimpleNamespace(name=symbol, digits=2, point=0.01)

        def symbol_info_tick(self, symbol):
            return SimpleNamespace(bid=2300.10, ask=2300.30, last=2300.20,
                                   time=123, time_msc=123000)

    fake = _MarketDataMT5()
    monkeypatch.setattr(market_data, "_readonly_mt5_connection",
                        lambda: (fake, SimpleNamespace(), ""))

    result = market_data.get_market_tick("XAUUSD")

    assert result["ok"] is True
    assert result["symbol"] == "XAUUSD"
    assert result["bid"] == 2300.10
    assert result["read_only"] is True
    assert result["execution_authority"] == "NONE"


def test_legacy_market_tick_uses_read_permission_when_trading_is_disabled(
        monkeypatch, safe_market_profile):
    class _MarketDataMT5:
        def symbol_info(self, symbol):
            return SimpleNamespace(name=symbol, digits=2, point=0.01)

        def symbol_info_tick(self, symbol):
            return SimpleNamespace(bid=4070.10, ask=4071.10, last=4070.60,
                                   time=123, time_msc=123000)

    monkeypatch.setattr(market_data, "_readonly_mt5_connection",
                        lambda: (_MarketDataMT5(), SimpleNamespace(), ""))

    result = market_data.get_market_tick("XAUUSD")

    assert result["ok"] is True
    assert result["source"] == "MetaTrader 5"
    assert result["read_only"] is True
    assert result["execution_authority"] == "NONE"


def test_legacy_market_analysis_contract_is_readonly_when_source_is_disabled(monkeypatch):
    monkeypatch.setattr(market_data, "_mt5_enabled", lambda override=None: False)

    chart = market_data.get_market_chart("XAUUSD", "M15")
    context = market_data.get_market_ai_context("XAUUSD")

    for result in (chart, context):
        assert result["provider"] == "MT5"
        assert result["read_only"] is True
        assert result["execution_authority"] == "NONE"

