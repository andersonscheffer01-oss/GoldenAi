"""Deterministic, read-only B4.12 tester materialization and preflight contract."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

from .b2_contracts import content_fingerprint
from .robot_identity_recovery import PROPOSED_CAMPAIGN_PATH
from .shared_temporal_campaign import (
    B4_10_CAMPAIGN_ID, B4_10_MANIFEST_HASH, build_shared_temporal_preflight,
    temporal_state,
)
from .tester_config_reconciliation import (
    MATERIALIZATION_VERSION, materialize_config, output_routing_fingerprint,
    scientific_config_fingerprint,
)

CONTRACT_VERSION = "jarvis-b4.12-deterministic-materialization-v1"
RECEIPT_VERSION = "jarvis-b4.12-execution-preflight-receipt-v1"
TERMINAL_TARGET = r"C:\Program Files\MetaTrader 5\terminal64.exe"
DATA_ROOT_TARGET = "C:\\Users\\Anderson\\AppData\\Roaming\\MetaQuotes\\Terminal\\D0E8209F77C8CF37AD8BF550E51FF075"
_RUN_RE = re.compile(r"^run_[a-f0-9]{32}$")
_CAMPAIGN_RE = re.compile(r"^campaign_[a-f0-9]{32}$")
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)
_ROBOTS = {
    "EA_Canal_Pullback_MT5": {
        "expert": r"EA_Canal_Pullback_MT5\EA_Canal_Pullback_MT5.ex5",
        "preset": "Setup_8_Robusto_Base.set",
        "preset_sha256": "87868b176181d827272d442044a532ce8dde51d856fbb43db4c9cbc3c202562c",
    },
    "Robo_Tendencia_MA9_21_50_Volume": {
        "expert": r"Robo_Tendencia_MA9_21_50_Volume.ex5",
        "preset": None,
        "preset_sha256": None,
    },
}


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _assert_plan_integrity(plan: Mapping[str, Any]) -> None:
    supplied = plan.get("materialization_plan_fingerprint")
    payload = dict(plan)
    payload.pop("materialization_plan_fingerprint", None)
    if (not supplied or content_fingerprint(payload) != supplied or
            plan.get("campaign_id") != B4_10_CAMPAIGN_ID or
            plan.get("campaign_manifest_hash") != B4_10_MANIFEST_HASH or
            plan.get("execution_authorized") is not False):
        raise ValueError("MATERIALIZATION_PLAN_INTEGRITY_MISMATCH")


def _safe_relative(path: str) -> str:
    if not isinstance(path, str) or not path or "\x00" in path or ":" in path:
        raise ValueError("UNSAFE_OUTPUT_PATH")
    normalized = path.replace("/", "\\")
    parts = normalized.split("\\")
    if normalized.startswith("\\") or any(p in {"", ".", ".."} for p in parts):
        raise ValueError("UNSAFE_OUTPUT_PATH")
    if any(any(ch in part for ch in '<>"|?*') or part.endswith((" ", ".")) or
           _WINDOWS_RESERVED.fullmatch(part) for part in parts):
        raise ValueError("UNSAFE_OUTPUT_PATH")
    return "\\".join(parts)


def _render(run: Mapping[str, Any], campaign_id: str) -> str:
    robot = run.get("robot_id")
    if robot not in _ROBOTS:
        raise ValueError("ROBOT_CONTRACT_UNKNOWN")
    expected_tf = "M1" if robot == "EA_Canal_Pullback_MT5" else "M15"
    if run.get("timeframe") != expected_tf:
        raise ValueError("ROBOT_TIMEFRAME_MISMATCH")
    if not _RUN_RE.fullmatch(str(run.get("test_run_id", ""))) or not _CAMPAIGN_RE.fullmatch(campaign_id):
        raise ValueError("CAMPAIGN_OR_RUN_ID_INVALID")
    if run.get("tester_model") != "REAL_TICKS":
        raise ValueError("TESTER_MODEL_MISMATCH")
    if (run.get("optimization"), run.get("use_remote"), run.get("use_cloud"),
            run.get("allow_live_trading")) != (0, 0, 0, 0):
        raise ValueError("UNSAFE_TESTER_SEMANTICS")
    start, end = run["window"]["from"], run["window"]["to"]
    for value in (start, end):
        datetime.strptime(value, "%Y-%m-%d")
    robot_contract = _ROBOTS[robot]
    lines = [
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0", "Enabled=1", "",
        "[Tester]", f"Expert={robot_contract['expert']}", f"Symbol={run['symbol']}",
    ]
    if robot_contract["preset"]:
        lines.append(f"ExpertParameters={robot_contract['preset']}")
    lines.extend([
        f"Period={run['timeframe']}", "Model=4", "Optimization=0", "UseLocal=1",
        "UseRemote=0", "UseCloud=0", "Visual=0", "ReplaceReport=0",
        f"Report=Tester\\Jarvis\\{run['test_run_id']}.htm", "ShutdownTerminal=1",
        f"FromDate={start.replace('-', '.')}", f"ToDate={end.replace('-', '.')}",
    ])
    return "\n".join(lines) + "\n"


def _route(run: Mapping[str, Any], campaign_id: str, market_id: str, ini: str) -> dict[str, Any]:
    run_id = run["test_run_id"]
    report = _safe_relative(f"Tester\\Jarvis\\{run_id}.htm")
    result = _safe_relative(f"tester_runs\\{campaign_id}\\{run_id}\\native_result.json")
    ownership = {
        "contract": CONTRACT_VERSION, "campaign_id": campaign_id,
        "test_run_id": run_id, "robot_id": run["robot_id"],
        "compiled_hash": run["compiled_hash"],
        "parameter_fingerprint": run["parameter_fingerprint"],
        "market_window_id": market_id, "market_window_fingerprint": run["market_window_fingerprint"],
        "report_relative_path": report, "result_relative_path": result,
        "ini_output_fingerprint": output_routing_fingerprint(ini),
    }
    return {**ownership, "output_routing_fingerprint": content_fingerprint(ownership),
            "status": "LOGICAL_ROUTE_ONLY_NOT_CREATED"}


def build_materialization_plan(*, root=None, clock=None) -> dict[str, Any]:
    """Render expected config bytes in memory; never writes or contacts providers."""
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    temporal = build_shared_temporal_preflight(root=root, clock=lambda: now)
    manifest = json.loads(PROPOSED_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    if manifest["campaign_id"] != B4_10_CAMPAIGN_ID or temporal["campaign_manifest_hash"] != B4_10_MANIFEST_HASH:
        raise ValueError("CAMPAIGN_MANIFEST_IDENTITY_MISMATCH")
    windows = {w["window_id"]: w for w in temporal["market_windows"]}
    materialized, routes, planned = [], [], []
    seen_paths: set[str] = set()
    for source, contextual in zip(manifest["manifest"]["planned_runs"], temporal["planned_runs"]):
        if source["test_run_id"] != contextual["test_run_id"]:
            raise ValueError("CAMPAIGN_RUN_ORDER_MISMATCH")
        if source["compiled_hash"] != contextual["compiled_hash"] or source["parameter_fingerprint"] != contextual["parameter_fingerprint"]:
            raise ValueError("ROBOT_IDENTITY_MISMATCH")
        window = windows[contextual["market_window_id"]]
        run = {**contextual, **source, "market_window_id": window["window_id"],
               "market_window_fingerprint": window["window_fingerprint"]}
        robot_contract = _ROBOTS[run["robot_id"]]
        raw = _render(run, B4_10_CAMPAIGN_ID).encode("utf-8")
        text = raw.decode("utf-8")
        ini_scientific_fp = scientific_config_fingerprint(text)
        ini = materialize_config(text, B4_10_CAMPAIGN_ID, run["test_run_id"])
        ini_bytes = ini.encode("utf-8")
        # B4.10's scientific identity includes robot/artifact/parameters; this
        # INI-only fingerprint intentionally remains a separate namespace.
        if scientific_config_fingerprint(ini) != ini_scientific_fp:
            raise ValueError("MATERIALIZATION_CHANGED_INI_SCIENCE")
        report_key = _safe_relative(f"Tester\\Jarvis\\{run['test_run_id']}.htm").casefold()
        result = _safe_relative(f"tester_runs\\{B4_10_CAMPAIGN_ID}\\{run['test_run_id']}\\native_result.json")
        keys = {report_key, result.casefold()}
        if seen_paths.intersection(keys):
            raise ValueError("OUTPUT_PATH_COLLISION")
        seen_paths.update(keys)
        route = _route(run, B4_10_CAMPAIGN_ID, window["window_id"], ini)
        routes.append({"test_run_id": run["test_run_id"], "fingerprint": route["output_routing_fingerprint"],
                       "status": route["status"], "report_relative_path": route["report_relative_path"],
                       "result_relative_path": route["result_relative_path"]})
        materialized.append({"test_run_id": run["test_run_id"],
                             "fingerprint": _hash_bytes(ini_bytes),
                             "bytes": len(ini_bytes), "status": "DRY_RUN_MATERIALIZED_IN_MEMORY"})
        planned.append({**run, "campaign_id": B4_10_CAMPAIGN_ID,
                        "scientific_config_fingerprint": source["scientific_config_fingerprint"],
                        "materialized_config_fingerprint": _hash_bytes(ini_bytes),
                        "ini_scientific_config_fingerprint": ini_scientific_fp,
                        "output_routing_fingerprint": route["output_routing_fingerprint"],
                        "parameter_artifact_contract": {
                            "mode": "VERIFIED_SET_FILE" if robot_contract["preset"] else "COMPILE_TIME_DEFAULTS",
                            "preset_name": robot_contract["preset"],
                            "preset_sha256": robot_contract["preset_sha256"],
                            "parameter_fingerprint": run["parameter_fingerprint"],
                            "revalidate_before_execution": True,
                        },
                        "report_relative_path": route["report_relative_path"],
                        "result_relative_path": route["result_relative_path"],
                        "materialization_status": "DRY_RUN_MATERIALIZED_IN_MEMORY",
                        "context_status": "PENDING_PRE_WINDOW_AND_POST_WINDOW_FREEZE",
                        "authorization": "NOT_GRANTED", "execution": "BLOCKED"})
    payload = {
        "contract_version": CONTRACT_VERSION, "materialization_version": MATERIALIZATION_VERSION,
        "campaign_id": B4_10_CAMPAIGN_ID, "campaign_manifest_hash": B4_10_MANIFEST_HASH,
        "terminal_target": TERMINAL_TARGET, "data_root_target": DATA_ROOT_TARGET,
        "manifest_changed": False, "read_only": True, "authorized": False,
        "execution_authorized": False, "execution_ready": False,
        "planned_runs": planned, "materialized_config_fingerprints": materialized,
        "output_routing_fingerprints": routes,
        "materialized_config_status": "DRY_RUN_MATERIALIZED_IN_MEMORY",
        "output_routing_status": "LOGICAL_ROUTES_UNIQUE_NOT_CREATED",
        "encoding": "UTF-8", "bom": False, "line_endings": "LF", "final_newline": True,
        "parameter_serialization": "ROBOT_BOUND_FINGERPRINT; CANAL VERIFIED .set NAME; TENDENCIA COMPILE-TIME DEFAULTS; NO .set GENERATED",
        "parameter_serialization_status": "PLAN_BOUND; EXACT DEPLOYED PRESET/DEFAULT EFFECTIVE INPUTS REQUIRE EXECUTION-PREFLIGHT REVALIDATION",
        "stale_output_policy": "BLOCK_IF_EXPECTED_REPORT_OR_RESULT_EXISTS_AT_EXECUTION_PREFLIGHT",
        "overwrite_allowed": False,
        "temporal_state": temporal["planned_runs"][0]["lifecycle"],
        "context_required_before_execution": True,
        "pre_window_context_status": "PENDING",
        "post_window_technical_status": "PENDING",
        "post_window_macro_status": "PENDING",
        "execution_order": "WINDOW_COMPLETE -> PRE_WINDOW_CONTEXT_FROZEN -> POST_WINDOW_TECHNICAL_AND_MACRO_CONTEXT_FROZEN -> CONFIG_PREFLIGHT -> HUMAN_APPROVAL -> EXECUTION",
        "approval_contract": {
            "scope_fields": ["campaign_id", "manifest_hash", "bounded_run_ids", "robot_ids", "compiled_hashes",
                             "parameter_fingerprints", "scientific_config_fingerprints", "materialized_config_fingerprints",
                             "output_routing_fingerprints", "window_ids", "tester_model", "terminal_path", "data_root",
                             "expires_at", "single_use"],
            "ttl_seconds": "CANONICAL_SECURITYMANAGER.confirmation_ttl", "use_policy": "SINGLE_USE",
            "development_batch": "ALL_ELIGIBLE_DEVELOPMENT_RUNS_FOR_ONE_COMPLETED_CALENDAR_WINDOW_ONLY",
            "holdout_included": False, "auto_retry": False, "created_now": False,
        },
        "provider_calls": {"tester": 0, "market": 0, "model": 0, "mt5_launch": 0},
        "terminal_process_observation": "NOT_INSPECTED; INJECTED_EXECUTION_PREFLIGHT_REQUIRED",
    }
    payload["materialization_plan_fingerprint"] = content_fingerprint(payload)
    return payload


def build_execution_preflight_receipt(plan: Mapping[str, Any], run_id: str,
                                      observations: Mapping[str, Any], *, evaluated_at: datetime) -> dict[str, Any]:
    """Create immutable non-authorizing receipt from explicit observations only."""
    _assert_plan_integrity(plan)
    if evaluated_at.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")
    matches = [item for item in plan.get("planned_runs", []) if item.get("test_run_id") == run_id]
    if len(matches) != 1:
        raise ValueError("RUN_NOT_IN_FROZEN_PLAN")
    run = matches[0]
    checks = {
        "campaign_manifest": plan.get("campaign_manifest_hash") == B4_10_MANIFEST_HASH,
        "compiled_artifact": observations.get("compiled_hash") == run["compiled_hash"],
        "parameters": observations.get("parameter_fingerprint") == run["parameter_fingerprint"],
        "parameter_artifact": (
            observations.get("preset_sha256") == run["parameter_artifact_contract"]["preset_sha256"]
            if run["parameter_artifact_contract"]["mode"] == "VERIFIED_SET_FILE"
            else observations.get("defaults_source_hash") == run["source_hash"]
        ),
        "scientific_config": observations.get("scientific_config_fingerprint") == run["scientific_config_fingerprint"],
        "materialized_config": observations.get("materialized_config_fingerprint") == run["materialized_config_fingerprint"],
        "output_routing": observations.get("output_routing_fingerprint") == run["output_routing_fingerprint"],
        "market_window": observations.get("market_window_fingerprint") == run["market_window_fingerprint"],
        "context_ready": observations.get("context_status") == "CONTEXT_READY",
        "stale_outputs_absent": observations.get("stale_outputs_present") is False,
        "terminal_process_clear": observations.get("user_mt5_process") == "CLEAR",
        "terminal_target": str(observations.get("terminal_path", "")).casefold() == TERMINAL_TARGET.casefold(),
        "data_root_target": str(observations.get("data_root", "")).casefold() == DATA_ROOT_TARGET.casefold(),
        "fresh_security_approval": observations.get("security_approval_valid") is True,
        "window_complete": temporal_state(run["window"]["from"], run["window"]["to"], evaluated_at) == "TEMPORAL_WINDOW_COMPLETE",
    }
    body = {"receipt_version": RECEIPT_VERSION, "test_run_id": run_id,
            "evaluated_at": evaluated_at.astimezone(timezone.utc).isoformat(),
            "plan_fingerprint": plan.get("materialization_plan_fingerprint"),
            "checks": checks, "status": "PREFLIGHT_READY" if all(checks.values()) else "PREFLIGHT_BLOCKED",
            "authorizes_execution": False}
    return {**body, "receipt_fingerprint": content_fingerprint(body)}


def build_approval_scope(plan: Mapping[str, Any], runs: list[Mapping[str, Any]], *, expires_at: str) -> dict[str, Any]:
    """Canonical approval payload description; deliberately does not mint approval."""
    _assert_plan_integrity(plan)
    if not runs or any(r.get("split") != "DEVELOPMENT" for r in runs):
        raise ValueError("APPROVAL_SCOPE_MUST_BE_DEVELOPMENT_ONLY")
    dates = {(r["window"]["from"], r["window"]["to"]) for r in runs}
    if len(dates) != 1:
        raise ValueError("APPROVAL_SCOPE_MUST_BE_ONE_CALENDAR_WINDOW")
    expected = {r["test_run_id"] for r in plan["planned_runs"]
                if r.get("split") == "DEVELOPMENT" and
                (r["window"]["from"], r["window"]["to"]) in dates}
    supplied = {r.get("test_run_id") for r in runs}
    if supplied != expected:
        raise ValueError("APPROVAL_SCOPE_RUN_SET_MISMATCH")
    frozen = {r["test_run_id"]: r for r in plan["planned_runs"]}
    identity_fields = ("robot_id", "compiled_hash", "parameter_fingerprint",
                       "scientific_config_fingerprint", "materialized_config_fingerprint",
                       "output_routing_fingerprint", "market_window_id", "tester_model")
    for run in runs:
        expected_run = frozen[run["test_run_id"]]
        if any(run.get(field) != expected_run.get(field) for field in identity_fields):
            raise ValueError("APPROVAL_SCOPE_RUN_BINDING_MISMATCH")
    return {"campaign_id": plan["campaign_id"], "manifest_hash": plan["campaign_manifest_hash"],
            "terminal_target": plan["terminal_target"], "data_root_target": plan["data_root_target"],
            "runs": [{k: r[k] for k in ("test_run_id", "robot_id", "compiled_hash", "parameter_fingerprint",
                                        "scientific_config_fingerprint", "materialized_config_fingerprint",
                                        "output_routing_fingerprint", "market_window_id", "tester_model")}
                     for r in sorted(runs, key=lambda x: x["test_run_id"])],
            "expires_at": expires_at, "single_use": True, "approval_created": False}


__all__ = ["CONTRACT_VERSION", "RECEIPT_VERSION", "build_approval_scope",
           "build_execution_preflight_receipt", "build_materialization_plan"]
