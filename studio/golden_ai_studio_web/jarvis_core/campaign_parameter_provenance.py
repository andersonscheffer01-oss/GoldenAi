"""Read-only parameter and compiled-artifact provenance for B4.10 campaigns."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .mql5_evidence import parse_mql5_inputs, parse_set_parameters
from .robot_catalog import parameter_fingerprint
from .shared_temporal_campaign import B4_10_CAMPAIGN_ID

CANAL = "EA_Canal_Pullback_MT5"
TREND = "Robo_Tendencia_MA9_21_50_Volume"
EXPECTED = {
    CANAL: {
        "source_hash": "0f1ba3526de5e7b679281e38136479beb99dd707fd1b02db1d960ffae103aff4",
        "compiled_hash": "e239e0dfc1c6a10c4bd4f8758b1913946b2423cd0901b8f3486b910fe56267cc",
        "parameter_fingerprint": "7953a3fa4ca05b223411fca3",
        "project_preset_hash": "87868b176181d827272d442044a532ce8dde51d856fbb43db4c9cbc3c202562c",
        "installed_preset_hash": "c1a09b8134a06f9d8a98e005b4000f2a0dfbff22833625b99edd2b5f4ff8308c",
        "historical_manifest_hash": "096e947e4ef3f86a2c7056197c57e19e63442836b2af43d62809feff11a3f668",
        "compile_log_hash": "21c1dae917bbdd99302860f5420f14fdd71ad1dfd28b44cedd2233da23576e1a",
    },
    TREND: {
        "source_hash": "e7bcba2bb39dc6ab7a7389e32fa50f665e2caf62b1f2ecec6c4d6d5362d1130f",
        "compiled_hash": "22f243a500aaf567f291cbaecf11ca87db89986e1be28c1e405009e9034629f4",
        "parameter_fingerprint": "9da7c5af45bacfb4f62de780",
        "compile_log_hash": "ba9007541c2000c4bd395ac4001d12cc1da7b55e9d7efb9767f62c95dba6145c",
        "identity_inventory_hash": "3ecbe671fa14f27434c9606f2affda0bd22e83f357bfa40c13e3cc6d49acafba",
    },
}
DEFAULT_DATA_ROOT = (Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal") /
                     "D0E8209F77C8CF37AD8BF550E51FF075")
PROVENANCE_VERSION = "jarvis-b4.13-typed-parameter-provenance-v1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _read_artifact(path: Path, expected_hash: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "status": "MISSING"}
    raw = path.read_bytes()
    digest = _sha(raw)
    return {"path": str(path), "sha256": digest, "size": len(raw),
            "status": "MATCH" if expected_hash is None or digest == expected_hash else "HASH_MISMATCH"}


def _compile_log_evidence(path: Path, expected_hash: str) -> dict[str, Any]:
    artifact = _read_artifact(path, expected_hash)
    if artifact["status"] != "MATCH":
        raise ValueError("COMPILE_LOG_ARTIFACT_MISMATCH")
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    match = re.search(r"Result\s*:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?", text or "", re.I)
    if not match or int(match.group(1)) != 0:
        raise ValueError("COMPILE_SUCCESS_EVIDENCE_INVALID")
    return {**artifact, "status": "COMPILE_SUCCESS", "errors": int(match.group(1)),
            "warnings": int(match.group(2)), "compiled_hash_recorded_in_log": False}


def _verify_canal_historical_binding(root: Path) -> dict[str, Any]:
    path = (root / "studio/golden_ai_studio_web/tester_campaigns" /
            "campaign_073cebd5e7df446fa9c85bae75ffbe0a/campaign_manifest.json")
    observed = _read_artifact(path, EXPECTED[CANAL]["historical_manifest_hash"])
    if observed["status"] != "MATCH":
        raise ValueError("HISTORICAL_PRESET_COMPILED_BINDING_UNVERIFIED")
    payload = json.loads(path.read_text(encoding="utf-8"))
    robot, preset, compile_evidence = payload.get("robot", {}), payload.get("preset", {}), payload.get("compile_evidence", {})
    identities_match = (
        payload.get("campaign_id") == "campaign_073cebd5e7df446fa9c85bae75ffbe0a" and
        robot.get("robot_id") == CANAL and
        robot.get("source_hash") == EXPECTED[CANAL]["source_hash"] and
        robot.get("compiled_hash") == EXPECTED[CANAL]["compiled_hash"] and
        robot.get("source_compiled_relationship") == "STRONG" and
        preset.get("project_hash") == EXPECTED[CANAL]["project_preset_hash"] and
        preset.get("runtime_hash") == EXPECTED[CANAL]["installed_preset_hash"] and
        preset.get("parameter_fingerprint") == EXPECTED[CANAL]["parameter_fingerprint"] and
        preset.get("semantic_equivalence") == "PASS" and
        compile_evidence.get("status") == "COMPILE_SUCCESS" and
        compile_evidence.get("errors") == 0
    )
    if not identities_match:
        raise ValueError("HISTORICAL_PRESET_COMPILED_BINDING_MISMATCH")
    compile_log = _compile_log_evidence(
        Path(compile_evidence["log_path"]), EXPECTED[CANAL]["compile_log_hash"]
    )
    return {**observed, "campaign_id": payload["campaign_id"],
            "source_hash": robot["source_hash"], "compiled_hash": robot["compiled_hash"],
            "preset_project_hash": preset["project_hash"],
            "preset_runtime_hash": preset["runtime_hash"],
            "parameter_fingerprint": preset["parameter_fingerprint"],
            "semantic_equivalence": preset["semantic_equivalence"],
            "compile_status": compile_evidence["status"], "compile_log": compile_log,
            "binding_status": "VERIFIED"}


def _verify_trend_identity_record(root: Path) -> dict[str, Any]:
    path = root / "studio/golden_ai_studio_web/jarvis_core/data/b4_10_robot_identity_recovery.json"
    observed = _read_artifact(path, EXPECTED[TREND]["identity_inventory_hash"])
    if observed["status"] != "MATCH":
        raise ValueError("B4_10_ROBOT_IDENTITY_EVIDENCE_UNVERIFIED")
    inventory = json.loads(path.read_text(encoding="utf-8"))
    candidates = [item for item in inventory.get("candidates", [])
                  if item.get("candidate_id") == TREND]
    if len(candidates) != 1:
        raise ValueError("B4_10_ROBOT_IDENTITY_RECORD_AMBIGUOUS")
    candidate = candidates[0]
    source, compiled = candidate.get("source_artifacts", []), candidate.get("compiled_artifacts", [])
    parameter, compile_record = candidate.get("parameter_evidence", {}), candidate.get("compile_evidence", {})
    if not (len(source) == len(compiled) == 1 and
            source[0].get("sha256") == EXPECTED[TREND]["source_hash"] and
            compiled[0].get("sha256") == EXPECTED[TREND]["compiled_hash"] and
            parameter.get("fingerprint") == EXPECTED[TREND]["parameter_fingerprint"] and
            parameter.get("input_count") == 31 and
            candidate.get("source_compiled_relationship") == "PARTIAL" and
            compile_record.get("sha256") == EXPECTED[TREND]["compile_log_hash"] and
            compile_record.get("status") == "COMPILE_SUCCESS" and
            compile_record.get("errors") == 0 and
            compile_record.get("compiled_hash_recorded") == "NOT_PRESENT"):
        raise ValueError("B4_10_ROBOT_IDENTITY_RECORD_MISMATCH")
    return {**observed, "robot_id": TREND, "source_hash": source[0]["sha256"],
            "compiled_hash": compiled[0]["sha256"], "parameter_fingerprint": parameter["fingerprint"],
            "relationship": candidate["source_compiled_relationship"],
            "compile_log_hash": compile_record["sha256"], "binding_status": "VERIFIED_WITH_PARTIAL_LINK"}


def _decode_source(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "UTF-8-SIG"
    return raw.decode("utf-8"), "UTF-8"


def _decode_set(raw: bytes) -> tuple[str, str]:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "UTF-16"
    return raw.decode("utf-8-sig"), "UTF-8-SIG" if raw.startswith(b"\xef\xbb\xbf") else "UTF-8"


def _schema_rows(definitions: list[Any]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for definition in definitions:
        key = definition.name.casefold()
        if key in rows:
            raise ValueError("DUPLICATE_SOURCE_INPUT_NAME")
        rows[key] = definition
    return rows


def _typed_snapshot(values: dict[str, Any], schema: dict[str, Any], origin: str) -> tuple[list[dict[str, Any]], bytes]:
    rows = []
    for key in sorted(values):
        definition = schema.get(key.casefold())
        if definition is None:
            raise ValueError("PARAMETER_SCHEMA_UNKNOWN_INPUT")
        rows.append({"name": definition.name, "type": definition.type,
                     "value": values[key], "origin": origin})
    raw = _canonical({"version": PROVENANCE_VERSION, "parameters": rows})
    return rows, raw


def _enum_compatibility(definition: Any, value: Any) -> bool:
    if not definition.type.upper().startswith("ENUM_"):
        return True
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _enum_values(source: str, enum_type: str) -> dict[int, str] | None:
    if enum_type == "ENUM_TIMEFRAMES":
        return {0: "PERIOD_CURRENT", 1: "PERIOD_M1", 2: "PERIOD_M2", 3: "PERIOD_M3",
                4: "PERIOD_M4", 5: "PERIOD_M5", 6: "PERIOD_M6", 10: "PERIOD_M10",
                12: "PERIOD_M12", 15: "PERIOD_M15", 20: "PERIOD_M20", 30: "PERIOD_M30",
                16385: "PERIOD_H1", 16386: "PERIOD_H2", 16387: "PERIOD_H3",
                16388: "PERIOD_H4", 16390: "PERIOD_H6", 16392: "PERIOD_H8",
                16396: "PERIOD_H12", 16408: "PERIOD_D1", 32769: "PERIOD_W1",
                49153: "PERIOD_MN1"}
    if enum_type == "ENUM_MA_METHOD":
        return {0: "MODE_SMA", 1: "MODE_EMA", 2: "MODE_SMMA", 3: "MODE_LWMA"}
    if enum_type == "ENUM_APPLIED_PRICE":
        return {0: "PRICE_CLOSE", 1: "PRICE_OPEN", 2: "PRICE_HIGH", 3: "PRICE_LOW",
                4: "PRICE_MEDIAN", 5: "PRICE_TYPICAL", 6: "PRICE_WEIGHTED"}
    match = re.search(rf"\benum\s+{re.escape(enum_type)}\s*\{{(?P<body>.*?)\}}",
                      source, re.I | re.S)
    if not match:
        return None
    result: dict[int, str] = {}
    next_value = 0
    for item in match.group("body").split(","):
        declaration = re.sub(r"//.*$", "", item).strip()
        if not declaration:
            continue
        name, separator, raw_value = declaration.partition("=")
        try:
            value = int(raw_value.strip(), 0) if separator else next_value
        except ValueError:
            return None
        result[value] = name.strip()
        next_value = value + 1
    return result


def _enum_symbol(source: str, enum_type: str, value: Any) -> str | None:
    if isinstance(value, str):
        values = _enum_values(source, enum_type)
        return value if values is None or value in values.values() else None
    values = _enum_values(source, enum_type)
    if not isinstance(value, int) or isinstance(value, bool) or values is None:
        return None
    return values.get(value)


def _inspect_robot(robot_id: str, root: Path, data_root: Path) -> dict[str, Any]:
    expected = EXPECTED[robot_id]
    if robot_id == CANAL:
        historical_binding = _verify_canal_historical_binding(root)
        source_path = root / "projetos/EA_Canal_Pullback_MT5/EA_Canal_Pullback_MT5.mq5"
        project_ex5 = root / "projetos/EA_Canal_Pullback_MT5/EA_Canal_Pullback_MT5.ex5"
        project_set = root / "projetos/EA_Canal_Pullback_MT5/Setup_8_Robusto_Base.set"
        installed_ex5 = data_root / "MQL5/Experts/EA_Canal_Pullback_MT5/EA_Canal_Pullback_MT5.ex5"
        installed_set = data_root / "MQL5/Profiles/Tester/Setup_8_Robusto_Base.set"
    else:
        historical_binding = _verify_trend_identity_record(root)
        source_path = root / "projetos/Robo_Tendencia_MA9_21_50_Volume.mq5"
        project_ex5 = root / "projetos/Robo_Tendencia_MA9_21_50_Volume.ex5"
        installed_ex5 = data_root / "MQL5/Experts/Robo_Tendencia_MA9_21_50_Volume.ex5"
        project_set = installed_set = None

    source_artifact = _read_artifact(source_path, expected["source_hash"])
    if source_artifact["status"] != "MATCH":
        raise ValueError("SOURCE_ARTIFACT_IDENTITY_MISMATCH")
    source_text, source_encoding = _decode_source(source_path.read_bytes())
    definitions = parse_mql5_inputs(source_text, source_ref=str(source_path))
    compile_log_path = (root / "projetos/EA_Canal_Pullback_MT5/compile_installed_visual_limpo.log"
                        if robot_id == CANAL else
                        root / "projetos/Robo_Tendencia_MA9_21_50_Volume_compile.log")
    compile_log = _compile_log_evidence(compile_log_path, expected["compile_log_hash"])
    schema = _schema_rows(definitions)
    source_defaults = {item.name.casefold(): item.default for item in definitions}

    project_binary = _read_artifact(project_ex5)
    installed_binary = _read_artifact(installed_ex5)
    matching_binaries = [item for item in (project_binary, installed_binary)
                         if item.get("sha256") == expected["compiled_hash"]]
    actual_binary_status = ("AVAILABLE_MULTIPLE_COPIES_IDENTICAL" if len(matching_binaries) > 1
                            else "AVAILABLE_EXACT" if matching_binaries
                            else "MISSING" if all(item["status"] == "MISSING" for item in (project_binary, installed_binary))
                            else "HASH_MISMATCH")
    if actual_binary_status not in {"AVAILABLE_EXACT", "AVAILABLE_MULTIPLE_COPIES_IDENTICAL"}:
        raise ValueError("COMPILED_ARTIFACT_NOT_AVAILABLE_EXACT")

    if robot_id == CANAL:
        project_file = _read_artifact(project_set, expected["project_preset_hash"])
        runtime_file = _read_artifact(installed_set, expected["installed_preset_hash"])
        if project_file["status"] != "MATCH" or runtime_file["status"] != "MATCH":
            raise ValueError("PARAMETER_ARTIFACT_IDENTITY_MISMATCH")
        project_text, project_encoding = _decode_set(project_set.read_bytes())
        runtime_text, runtime_encoding = _decode_set(installed_set.read_bytes())
        campaign_values = parse_set_parameters(project_text)
        installed_values = parse_set_parameters(runtime_text)
        if campaign_values != installed_values:
            raise ValueError("INSTALLED_PARAMETER_SEMANTICS_MISMATCH")
        authority = "B4.9_VERIFIED_PRESET"
        origin = "PRESET"
        artifact = {**project_file, "role": "CAMPAIGN_FROZEN_PRESET", "encoding": project_encoding}
        installed_parameter_artifact = {**runtime_file, "role": "D0_TESTER_PROFILE_PRESET", "encoding": runtime_encoding}
        campaign_source_hash = expected["project_preset_hash"]
        extra = {"installed_parameter_artifact": installed_parameter_artifact,
                 "parameter_artifact_sha256": project_file["sha256"],
                 "installed_parameter_artifact_sha256": runtime_file["sha256"],
                 "historical_binding_evidence": historical_binding}
    else:
        campaign_values = source_defaults
        authority = "B4.10_COMPLETE_SOURCE_INPUT_DEFAULTS"
        origin = "EA_DEFAULT"
        artifact = {**source_artifact, "role": "SOURCE_DEFAULTS", "encoding": source_encoding}
        extra = {"parameter_artifact_sha256": source_artifact["sha256"],
                 "installed_parameter_artifact": None,
                 "installed_parameter_artifact_sha256": None,
                 "historical_binding_evidence": historical_binding}
        campaign_source_hash = source_artifact["sha256"]

    if parameter_fingerprint(campaign_values) != expected["parameter_fingerprint"]:
        raise ValueError("CAMPAIGN_PARAMETER_FINGERPRINT_MISMATCH")
    unknown = sorted(set(campaign_values) - set(schema))
    missing = sorted(set(schema) - set(campaign_values))
    type_mismatches = sorted(key for key, value in campaign_values.items()
                              if key in schema and not _enum_compatibility(schema[key], value))
    for key, value in campaign_values.items():
        definition = schema.get(key)
        if definition is None:
            continue
        kind = definition.type.upper()
        compatible = True
        if kind == "BOOL":
            compatible = isinstance(value, bool)
        elif kind in {"INT", "LONG", "ULONG", "UINT", "SHORT", "USHORT", "CHAR", "UCHAR", "COLOR"}:
            compatible = isinstance(value, int) and not isinstance(value, bool)
        elif kind in {"DOUBLE", "FLOAT"}:
            compatible = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif kind == "STRING":
            compatible = isinstance(value, str)
        elif kind.startswith("ENUM_"):
            allowed = _enum_values(source_text, kind)
            compatible = (_enum_compatibility(definition, value) and
                          (allowed is None or _enum_symbol(source_text, kind, value) is not None))
        if not compatible and key not in type_mismatches:
            type_mismatches.append(key)
    type_mismatches.sort()
    if unknown or type_mismatches:
        raise ValueError("PARAMETER_SCHEMA_MISMATCH")
    if robot_id == CANAL:
        if set(missing) != {"ativarexpansaodecanalcurto", "canalcurtoabaixodepontos",
                           "destacarentradasnografico", "mostrarsomentecanalatual",
                           "tamanhodasetadeentrada"}:
            raise ValueError("UNEXPECTED_MISSING_PARAMETER_SET")
        effective_values = {**campaign_values, **{key: source_defaults[key] for key in missing}}
        effective_origins = {key: ("PRESET" if key in campaign_values else "EA_DEFAULT")
                             for key in effective_values}
    else:
        if missing:
            raise ValueError("INCOMPLETE_SOURCE_DEFAULT_SET")
        effective_values = campaign_values
        effective_origins = {key: "EA_DEFAULT" for key in effective_values}

    rows = []
    for key in sorted(effective_values):
        definition = schema[key]
        value = effective_values[key]
        if definition.type.upper().startswith("ENUM_"):
            value = _enum_symbol(source_text, definition.type.upper(), value)
            if value is None:
                raise ValueError("PARAMETER_ENUM_VALUE_UNRESOLVED")
        rows.append({"name": definition.name, "type": definition.type,
                     "value": value, "origin": effective_origins[key]})
    snapshot = _canonical({"version": PROVENANCE_VERSION, "robot_id": robot_id,
                           "source_sha256": source_artifact["sha256"],
                           "compiled_sha256": expected["compiled_hash"], "parameters": rows})
    recomputed = parameter_fingerprint(campaign_values)
    return {
        "robot_id": robot_id, "source_sha256": source_artifact["sha256"],
        "source_path": str(source_path), "compiled_expected_sha256": expected["compiled_hash"],
        "compiled_status": actual_binary_status,
        "compiled_copies": [project_binary, installed_binary],
        "selected_compiled_path": matching_binaries[0]["path"],
        "installed_compiled_path": str(installed_ex5),
        "installed_compiled_status": installed_binary["status"] if installed_binary.get("sha256") == expected["compiled_hash"] else "NOT_INSTALLED_EXACT",
        "selected_compiled_sha256": expected["compiled_hash"],
        "compiled_size": matching_binaries[0]["size"],
        "source_compiled_relationship": "STRONG_HISTORICAL_MANIFEST_AND_TEST_EVIDENCE" if robot_id == CANAL else "PARTIAL_PATH_AND_TIMESTAMP_CORROBORATION",
        "compile_evidence": compile_log,
        "parameter_authority": authority, "parameter_origin": origin,
        "parameter_source_sha256": campaign_source_hash,
        "parameter_artifact": artifact,
        **extra,
        "parameter_fingerprint_expected": expected["parameter_fingerprint"],
        "parameter_fingerprint_recomputed": recomputed,
        "parameter_fingerprint_match": recomputed == expected["parameter_fingerprint"],
        "input_count": len(schema), "campaign_parameter_count": len(campaign_values),
        "unknown_parameters": unknown, "missing_campaign_parameters": missing,
        "type_mismatches": type_mismatches,
        "schema_status": "COMPATIBLE_WITH_IMPLICIT_SOURCE_DEFAULTS" if missing else "COMPATIBLE",
        "campaign_overrides": sorted(
            key for key, value in campaign_values.items()
            if (value != source_defaults[key] and
                not (schema[key].type.upper().startswith("ENUM_") and
                     _enum_symbol(source_text, schema[key].type.upper(), value) ==
                     _enum_symbol(source_text, schema[key].type.upper(), source_defaults[key])))
        ),
        "effective_parameter_snapshot_sha256": _sha(snapshot),
        "effective_parameter_snapshot_bytes": len(snapshot),
        "effective_parameter_count": len(rows),
        "effective_parameter_fingerprint": parameter_fingerprint(effective_values),
        "effective_parameter_snapshot": rows,
        "parameter_artifact_line_endings": (
            "CRLF_AND_LF_MIXED" if robot_id == CANAL else "SOURCE_DECLARATIONS"
        ),
        "parameter_drift_status": "NO_DRIFT_OBSERVED",
        "artifact_drift_status": "NO_DRIFT_OBSERVED",
        "runtime_install_status": "INSTALLED_EXACT" if matching_binaries[0]["path"].casefold().startswith(str(data_root).casefold()) else "PROJECT_COPY_ONLY",
        "campaign_binding_status": "VERIFIED_BY_FROZEN_CAMPAIGN_AND_PRESET_LINEAGE" if robot_id == CANAL else "VERIFIED_WITH_PARTIAL_SOURCE_COMPILED_LINK",
    }


def build_campaign_parameter_provenance(root: Path | str | None = None,
                                         data_root: Path | str | None = None) -> dict[str, Any]:
    """Rehash fixed artifacts and reconcile frozen parameters; performs no writes."""
    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    terminal_data = Path(data_root or DEFAULT_DATA_ROOT)
    robots = [_inspect_robot(robot, repo, terminal_data) for robot in (CANAL, TREND)]
    return {"version": PROVENANCE_VERSION, "campaign_id": B4_10_CAMPAIGN_ID,
            "read_only": True, "manifest_changed": False, "robots": robots,
            "status": "VERIFIED_WITH_RESTRICTIONS",
            "execution_authorized": False,
            "note": "TREND_COMPILED_ARTIFACT_PRESENT_ONLY_IN_PROJECT_ROOT; RECHECK_INSTALLATION_BEFORE_ANY_EXECUTION"}


def assert_run_parameter_binding(run: dict[str, Any], provenance: dict[str, Any]) -> None:
    if run.get("robot_id") != provenance.get("robot_id"):
        raise ValueError("CROSS_ROBOT_PARAMETER_BINDING")
    if run.get("source_hash") != provenance.get("source_sha256"):
        raise ValueError("SOURCE_HASH_MISMATCH")
    if run.get("compiled_hash") != provenance.get("compiled_expected_sha256"):
        raise ValueError("COMPILED_HASH_MISMATCH")
    if run.get("parameter_fingerprint") != provenance.get("parameter_fingerprint_recomputed"):
        raise ValueError("PARAMETER_FP_MISMATCH")
    if provenance.get("parameter_fingerprint_match") is not True:
        raise ValueError("PARAMETER_FP_MISMATCH")


__all__ = ["CANAL", "TREND", "PROVENANCE_VERSION", "assert_run_parameter_binding",
           "build_campaign_parameter_provenance"]
