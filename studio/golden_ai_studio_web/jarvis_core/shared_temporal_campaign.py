"""Read-only B4.11 shared temporal preflight for the frozen B4.10 proposal."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from .b2_contracts import content_fingerprint
from .historical_macro_evidence import DERIVATION_VERSION
from .robot_identity_recovery import PROPOSED_CAMPAIGN_PATH

B4_9_CAMPAIGN_ID = "campaign_b49_xauusd_m1_temporal_01"
B4_9_MANIFEST_HASH = "0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4"
B4_10_CAMPAIGN_ID = "campaign_bf3389bc66f0ac7777a3a06719ac5851"
B4_10_MANIFEST_HASH = "0df8521de44446de48141eb59b8ca884baca7fe483407239c4a952c2a25d7f0f"
WINDOW_FINGERPRINT_VERSION = "jarvis-market-window-v1"
CONTEXT_PLAN_VERSION = "jarvis-b4.11-context-plan-v1"
WARMUP_POLICY = {"calendar_days": 7, "source_contract": "B4.7_READ_ONLY_WARMUP"}
TIMEZONE = "UTC"


def _hash(value: Any) -> str:
    return content_fingerprint(value)


def _assert_no_outcomes(value: Any) -> None:
    forbidden = {"profit", "pnl", "balance", "equity", "drawdown", "trades",
                 "outcome", "score", "ontester", "position", "winrate"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = "".join(char for char in str(key).casefold() if char.isalnum())
            if normalized in forbidden:
                raise ValueError("OUTCOME_FEATURE_FORBIDDEN:" + str(key))
            _assert_no_outcomes(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _assert_no_outcomes(child)


def _read_parent(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    data = root / "studio/golden_ai_studio_web/jarvis_core/data"
    b49 = json.loads((data / "b4_9_scientific_campaign.json").read_text(encoding="utf-8"))
    b410 = json.loads(PROPOSED_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    if _hash(b49) != B4_9_MANIFEST_HASH or b49.get("campaign_id") != B4_9_CAMPAIGN_ID:
        raise ValueError("B4_9_IMMUTABILITY_MISMATCH")
    if (b410.get("campaign_id") != B4_10_CAMPAIGN_ID or
            b410.get("b4_9_manifest_hash") != B4_9_MANIFEST_HASH or
            _hash(b410["manifest"]) != B4_10_MANIFEST_HASH):
        raise ValueError("B4_10_MANIFEST_IDENTITY_MISMATCH")
    if b410["manifest"].get("status") != "PROPOSED_NOT_AUTHORIZED":
        raise ValueError("B4_10_AUTHORIZATION_STATE_INVALID")
    return b49, b410


def _instant(day: str, tz: str, *, end: bool = False) -> datetime:
    parsed = date.fromisoformat(day)
    if end:
        parsed += timedelta(days=1)
        return datetime.combine(parsed, time.min, ZoneInfo(tz)).astimezone(timezone.utc)
    return datetime.combine(parsed, time.min, ZoneInfo(tz)).astimezone(timezone.utc)


def temporal_state(start: str, end: str, now: datetime, tz: str = TIMEZONE) -> str:
    if now.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")
    current = now.astimezone(timezone.utc)
    first, after_last = _instant(start, tz), _instant(end, tz, end=True)
    if current < first:
        return "NOT_EXECUTABLE_FUTURE_WINDOW"
    if current < after_last:
        return "NOT_EXECUTABLE_WINDOW_IN_PROGRESS"
    return "TEMPORAL_WINDOW_COMPLETE"


def market_window_identity(symbol: str, timeframe: str, start: str, end: str,
                           tz: str = TIMEZONE,
                           warmup_policy: Mapping[str, Any] = WARMUP_POLICY) -> dict[str, str]:
    semantic = {
        "contract": WINDOW_FINGERPRINT_VERSION, "symbol": symbol,
        "timeframe": timeframe, "start": start, "end": end,
        "timezone": tz, "warmup_policy": dict(warmup_policy),
    }
    fingerprint = _hash(semantic)
    return {"window_id": "market_window_" + fingerprint[:24],
            "window_fingerprint": fingerprint}


def sample_identity(run_id: str, robot_id: str, compiled_hash: str,
                    parameter_fingerprint: str, market_fingerprint: str,
                    tester_model: str) -> str:
    return _hash({"run_id": run_id, "robot_id": robot_id,
                  "compiled_hash": compiled_hash,
                  "parameter_fingerprint": parameter_fingerprint,
                  "market_window_fingerprint": market_fingerprint,
                  "tester_model": tester_model})


def build_shared_temporal_preflight(root: Path | str | None = None,
                                    clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    _, source = _read_parent(repo)
    manifest = source["manifest"]
    runs = manifest["planned_runs"]
    if len(runs) != 16 or len({r["test_run_id"] for r in runs}) != 16:
        raise ValueError("B4_10_PLANNED_RUN_INVENTORY_INVALID")
    robots = {r["robot_id"] for r in runs}
    if robots != {"EA_Canal_Pullback_MT5", "Robo_Tendencia_MA9_21_50_Volume"}:
        raise ValueError("B4_10_ROBOT_SCOPE_CHANGED")

    market_windows: dict[str, dict[str, Any]] = {}
    macro_windows: dict[str, dict[str, Any]] = {}
    planned_runs = []
    scientific_fps = []
    output_fps = []
    current = (clock or (lambda: datetime.now(timezone.utc)))()
    if current.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")

    for run in runs:
        window = run["window"]
        start, end = window["from"], window["to"]
        identity = market_window_identity(run["symbol"], run["timeframe"], start, end)
        market_fp = identity["window_fingerprint"]
        market_id = identity["window_id"]
        entry = market_windows.setdefault(market_id, {
            "window_id": market_id, "symbol": run["symbol"], "timeframe": run["timeframe"],
            "start": start, "end": end, "timezone": TIMEZONE,
            "window_fingerprint": market_fp, "run_ids": [], "robot_ids": [],
            "context_status": "PRE_WINDOW_CONTEXT_PENDING",
            "warmup_policy": WARMUP_POLICY,
        })
        entry["run_ids"].append(run["test_run_id"])
        entry["robot_ids"].append(run["robot_id"])

        macro_semantic = {
            "contract": CONTEXT_PLAN_VERSION, "symbol": run["symbol"],
            "start": start, "end": end, "timezone": TIMEZONE,
            "derivation_version": DERIVATION_VERSION,
            "ex_ante_cutoff": start,
            "post_window_cutoff_exclusive": (date.fromisoformat(end) + timedelta(days=1)).isoformat(),
            "available_at_rule": "AVAILABLE_AT_LE_CUTOFF_AND_NOT_BEFORE_RELEASED_AT",
        }
        macro_fp = _hash(macro_semantic)
        macro_id = "macro_window_" + macro_fp[:24]
        macro = macro_windows.setdefault(macro_id, {
            "window_id": macro_id, "symbol": run["symbol"], "start": start,
            "end": end, "timezone": TIMEZONE, "macro_window_fingerprint": macro_fp,
            "run_ids": [], "robot_ids": [], "derivation_version": DERIVATION_VERSION,
            "ex_ante_context_id": "macro_ex_ante_" + macro_fp[:24],
            "ex_ante_context_fingerprint": _hash({**macro_semantic, "semantics": "EX_ANTE_CONTEXT"}),
            "post_window_context_id": "macro_post_window_" + macro_fp[:24],
            "post_window_context_fingerprint": _hash({**macro_semantic, "semantics": "POST_WINDOW_DESCRIPTIVE_MACRO_CONTEXT"}),
            "ex_ante_status": "PENDING_SCHEDULE_SNAPSHOT_AND_CUTOFF_VALIDATION",
            "post_window_status": "POST_WINDOW_CONTEXT_PENDING",
        })
        macro["run_ids"].append(run["test_run_id"])
        macro["robot_ids"].append(run["robot_id"])

        scientific = run["scientific_config_fingerprint"]
        scientific_fps.append({"test_run_id": run["test_run_id"], "fingerprint": scientific})
        output_fp = _hash({"report": f"Tester/Jarvis/{run['test_run_id']}.htm",
                           "result_owner": run["test_run_id"], "version": "jarvis-output-route-plan-v1"})
        output_fps.append({"test_run_id": run["test_run_id"], "fingerprint": output_fp,
                           "status": "PLAN_ONLY_NOT_MATERIALIZED"})
        planned_runs.append({
            "test_run_id": run["test_run_id"], "robot_id": run["robot_id"],
            "source_hash": run["source_hash"], "compiled_hash": run["compiled_hash"],
            "parameter_fingerprint": run["parameter_fingerprint"],
            "symbol": run["symbol"], "timeframe": run["timeframe"],
            "window": window, "split": run["split"], "tester_model": run["tester_model"],
            "optimization": run["optimization"], "use_remote": run["use_remote"],
            "use_cloud": run["use_cloud"], "allow_live_trading": run["allow_live_trading"],
            "scientific_config_fingerprint": scientific,
            "market_window_id": market_id, "market_window_fingerprint": market_fp,
            "macro_window_id": macro_id, "macro_window_fingerprint": macro_fp,
            "sample_fingerprint": sample_identity(
                run["test_run_id"], run["robot_id"], run["compiled_hash"],
                run["parameter_fingerprint"], market_fp, run["tester_model"]),
            "lifecycle": temporal_state(start, end, current),
        })

    payload = {
        "schema": CONTEXT_PLAN_VERSION,
        "campaign_id": B4_10_CAMPAIGN_ID,
        "campaign_manifest_hash": B4_10_MANIFEST_HASH,
        "b4_9_campaign_id": B4_9_CAMPAIGN_ID,
        "b4_9_manifest_hash": B4_9_MANIFEST_HASH,
        "state": "PROPOSED_NOT_AUTHORIZED", "authorized": False,
        "planned_run_count": len(planned_runs), "executed_new_runs": 0,
        "robot_count": len(robots), "planned_runs": planned_runs,
        "market_windows": list(market_windows.values()),
        "macro_windows": list(macro_windows.values()),
        "scientific_config_fingerprints": scientific_fps,
        "materialized_config_ready": False,
        "materialized_config_status": "MATERIALIZED_CONFIG_PENDING_EXECUTION_PREFLIGHT",
        "materialized_config_fingerprints": [],
        "output_routing_ready": True, "output_routing_fingerprints": output_fps,
        "technical_context_contract": "jarvis-temporal-context-v1",
        "macro_derivation_version": DERIVATION_VERSION,
        "macro_source_policy": "B4.8_CURATED_OFFLINE_ONLY; preserve raw/structured source artifacts in a future approved snapshot; no acquisition now",
        "post_window_context_available_now": False,
        "duplicate_market_contexts_created": 0, "duplicate_macro_contexts_created": 0,
        "execution_authorized": False, "campaign_executable_now": False,
        "holdout_preserved": True,
    }
    _assert_no_outcomes(payload)
    payload["context_plan_fingerprint"] = _hash(payload)
    return payload


def validate_run_binding(run: Mapping[str, Any], *, robot_id: str, compiled_hash: str,
                         parameter_fingerprint: str, symbol: str, timeframe: str,
                         window: Mapping[str, str]) -> None:
    for key, expected in (("robot_id", robot_id), ("compiled_hash", compiled_hash),
                          ("parameter_fingerprint", parameter_fingerprint),
                          ("symbol", symbol), ("timeframe", timeframe)):
        if run.get(key) != expected:
            raise ValueError("RUN_BINDING_MISMATCH:" + key)
    if run.get("window") != window:
        raise ValueError("RUN_BINDING_MISMATCH:window")


__all__ = ["build_shared_temporal_preflight", "market_window_identity", "sample_identity", "temporal_state", "validate_run_binding"]
