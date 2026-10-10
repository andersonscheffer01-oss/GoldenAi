from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_core.service import JarvisService  # noqa: E402
from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE  # noqa: E402


def test_recovery_diagnostics_are_masked_and_classify_empty_actor(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        result = service.golden_trend_scan_recover("device:test-only")
        diagnostics = result["diagnostics"]
        assert result["found"] is False
        assert diagnostics["actor_fingerprint"] != "device:test-only"
        assert len(diagnostics["actor_fingerprint"]) == 16
        assert diagnostics["database_match"] is False
        assert diagnostics["root_cause"] == "DATABASE_MISMATCH"
        assert "path" not in diagnostics
    finally:
        service.close()


def test_recovery_diagnostics_do_not_fingerprint_invalid_identity(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        result = service.golden_trend_scan_recover("anonymous")
        assert result["diagnostics"]["actor_fingerprint"] == "UNKNOWN"
    finally:
        service.close()
