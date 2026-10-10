from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_core.tools.market_readonly import (  # noqa: E402
    AUTHORIZED_INSTRUMENT_ALIASES,
    AUTHORIZED_INSTRUMENT_COUNT,
    authorized_instrument_for_symbol,
)
from jarvis_core.service import JarvisService  # noqa: E402
from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE  # noqa: E402


def test_authorized_catalog_has_exactly_31_logical_instruments():
    assert AUTHORIZED_INSTRUMENT_COUNT == 31
    assert len(AUTHORIZED_INSTRUMENT_ALIASES) == 31


def test_aliases_share_one_logical_instrument_and_suffixes_do_not_match():
    assert authorized_instrument_for_symbol("SPX") == "SP500"
    assert authorized_instrument_for_symbol("US500") == "SP500"
    assert authorized_instrument_for_symbol("USOIL") == "WTI"
    assert authorized_instrument_for_symbol("UKOIL") == "BRENT"
    assert authorized_instrument_for_symbol("US500Cash") is None
    assert authorized_instrument_for_symbol("BTCJPY") is None


def test_core_rejects_non_allowlisted_analysis_before_market_read(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.generate_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider must not run for a non-allowlisted symbol"))
        result = service.golden_panel_analysis(
            symbol="BTCJPY", timeframe="M15", correlation_id="catalog-gate",
            provider="MT5", provider_asset_id="mt5:BTCJPY",
            provider_symbol="BTCJPY", asset_class="CRYPTO")
        assert result["status"] == "INVALID_REQUEST"
        assert result["reason_code"] == "SYMBOL_NOT_AUTHORIZED"
        assert result["execution_authority"] == "NONE"
    finally:
        service.close()


def test_historical_scan_storage_is_not_changed_by_catalog_resolution():
    assert authorized_instrument_for_symbol("XAUUSD") == "XAUUSD"
    assert authorized_instrument_for_symbol("EURUSD") == "EURUSD"
