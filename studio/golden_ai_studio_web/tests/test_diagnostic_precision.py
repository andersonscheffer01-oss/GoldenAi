from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from jarvis_core.data.timestamps import normalize_external_timestamp
from jarvis_core.memory.v2.research import (
    AutoResearchProvider, FetchedSource, ResearchProviderError,
    StaticResearchProvider,
)
from jarvis_core.service import JarvisService


def _executions(cpu_now, cpu_total=99999.0):
    process = {"name": "TslGame.exe", "display_name": "TslGame.exe",
               "cpu_percent_now": cpu_now, "cpu_time_total": cpu_total,
               "memory_mb": 100.0}
    return [
        {"tool": "system_status", "result": {
            "cpu_total_now": 80, "disk_capacity_used_percent": 94,
            "disk_free_gb": 13.6}},
        {"tool": "list_processes", "result": {
            "top_cpu": [process], "top_memory": [process]}},
    ]


def test_high_cpu_time_with_low_instant_cpu_is_not_current_culprit():
    diagnostic = JarvisService._performance_diagnostic(_executions(.2))
    assert diagnostic["top_cpu_process"] is None
    assert diagnostic["top_cpu_candidate"] == "TslGame.exe"
    assert diagnostic["principal_cpu_supported"] is False


def test_high_instant_cpu_can_be_current_culprit():
    diagnostic = JarvisService._performance_diagnostic(_executions(42.0))
    assert diagnostic["top_cpu_process"] == "TslGame.exe"
    assert diagnostic["principal_cpu_supported"] is True


def test_disk_metric_is_capacity_not_activity():
    diagnostic = JarvisService._performance_diagnostic(_executions(2.0))
    assert diagnostic["disk_capacity_used_percent"] == 94
    assert "disk_activity_percent" not in diagnostic


def test_provider_initial_state_is_not_checked_not_failed():
    provider = AutoResearchProvider((("healthy", _healthy()),))
    assert provider.status()["final_status"] == "NOT_CHECKED"


def test_unknown_tslgame_keeps_process_name():
    identity = JarvisService._safe_process_identity("TslGame.exe", "")
    assert identity["display_name"] == "TslGame.exe"
    assert identity["identity_source"] == "unknown"
    assert "Division" not in identity["display_name"]


def test_local_version_info_can_supply_product_identity():
    fake = SimpleNamespace(GetFileVersionInfo=lambda path, key: (
        [(0x409, 0x4B0)] if key == r"\VarFileInfo\Translation" else
        "Confirmed Product" if key.endswith("ProductName") else "Confirmed Company"))
    with patch("jarvis_core.service.os.name", "nt"), patch.dict("sys.modules", {"win32api": fake}):
        identity = JarvisService._safe_process_identity("app.exe", r"C:\Apps\app.exe")
    assert identity["display_name"] == "Confirmed Product"
    assert identity["identity_source"] == "version_info"
    assert identity["identity_confidence"] == "high"


def test_epoch_utc_converts_to_system_local():
    raw = 1726100000
    result = normalize_external_timestamp(raw, "provider_epoch")
    expected = datetime.fromtimestamp(raw, timezone.utc).astimezone().strftime("%H:%M")
    assert result["display_timestamp"] == expected
    assert result["normalized_timestamp"].endswith("+00:00")


def test_known_offset_converts_to_system_local():
    result = normalize_external_timestamp("2026-01-10T18:30:00+00:00", "provider_iso")
    assert result["normalized_timestamp"] == "2026-01-10T18:30:00+00:00"
    assert result["timezone_source"] == "provider_iso"


def test_naive_timestamp_does_not_invent_timezone():
    result = normalize_external_timestamp("2026-01-10 18:30:00")
    assert result["normalized_timestamp"] == ""
    assert result["display_timestamp"] == "2026-01-10 18:30:00"
    assert result["timezone_source"] == "source_unspecified"


class _Failing:
    def __init__(self, reason):
        self.reason = reason
        self.calls = 0

    def search(self, query, limit=5):
        self.calls += 1
        raise ResearchProviderError(self.reason)

    def fetch(self, result):
        raise AssertionError


def _healthy():
    return StaticResearchProvider([
        FetchedSource("Docs", "https://docs.python.org/3/", "official")])


def test_missing_key_is_not_configured_and_skipped():
    provider = AutoResearchProvider((("missing", None), ("healthy", _healthy())))
    provider.search("python", 1)
    assert provider.status()["providers"]["missing"]["status"] == "NOT_CONFIGURED"


def test_rate_limit_sets_cooldown_and_falls_back():
    limited = _Failing("rate_limit")
    provider = AutoResearchProvider((("limited", limited), ("healthy", _healthy())))
    provider.search("python", 1)
    provider.search("python", 1)
    status = provider.status()
    assert limited.calls == 1
    assert status["providers"]["limited"]["cooldown_active"] is True
    assert status["selected"] == "healthy"


def test_all_providers_fail_reports_unavailable():
    provider = AutoResearchProvider((("broken", _Failing("provider_down")),))
    try:
        provider.search("python", 1)
    except ResearchProviderError:
        pass
    assert provider.status()["final_status"] == "UNAVAILABLE"


def test_healthy_provider_records_last_success():
    provider = AutoResearchProvider((("healthy", _healthy()),))
    provider.search("python", 1)
    state = provider.status()["providers"]["healthy"]
    assert state["status"] == "AVAILABLE"
    assert state["last_success"] > 0
