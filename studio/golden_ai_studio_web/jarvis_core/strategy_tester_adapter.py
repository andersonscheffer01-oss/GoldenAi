"""Controlled, fail-closed boundary for one local MT5 Strategy Tester run.

The adapter owns environment discovery, configuration provenance, and the
bounded process lifecycle. It does not own trading decisions, credentials, or
live execution. A real start requires an explicit human-action gate and an
already resolved data directory; discovery alone never starts a process.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .mql5_evidence import (
    EffectiveParameterSet,
    GoldenTestRunManifest,
    ResultEvidence,
    TestRunIdentity,
    TesterConfiguration,
    content_hash,
    parse_result_json,
    reconcile_result,
)


RUN_ID_RE = re.compile(r"^run_[a-f0-9]{32}$")
SAFE_RELATIVE_RE = re.compile(r"^[^:*?\"<>|]+$")
TERMINAL_NAMES = ("terminal64.exe", "terminal.exe")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "TRUNCATED"
    if isinstance(value, dict):
        return {str(k)[:100]: _bounded(v, depth + 1)
                for k, v in list(value.items())[:200]}
    if isinstance(value, (list, tuple)):
        return [_bounded(item, depth + 1) for item in list(value)[:200]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def _default_install_roots() -> tuple[Path, ...]:
    values = (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    )
    return tuple(Path(value) for value in values if value)


def _default_data_parent() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"


def _find_terminals(roots: Iterable[Path]) -> list[Path]:
    found: set[Path] = set()
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        direct = [root / name for name in TERMINAL_NAMES]
        for candidate in direct:
            if candidate.is_file():
                found.add(candidate.resolve())
        # Recurse only through Windows installation roots. A full LOCALAPPDATA
        # walk would mistake test fixtures and unrelated cached binaries for
        # broker installations.
        search_roots = [root]
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata and root.resolve() == Path(local_appdata).resolve():
            programs = root / "Programs"
            search_roots = [programs] if programs.is_dir() else []
        try:
            for search_root in search_roots:
                for candidate in search_root.glob("**/terminal64.exe"):
                    if candidate.is_file():
                        found.add(candidate.resolve())
        except OSError:
            continue
    return sorted(found, key=lambda item: str(item).casefold())


def _data_roots(parent: Path) -> list[Path]:
    if not parent.is_dir():
        return []
    result = []
    for item in parent.iterdir():
        if not item.is_dir() or item.name in {"Common", "Community", "Help"}:
            continue
        if (item / "origin.txt").is_file() or (item / "MQL5").is_dir():
            result.append(item.resolve())
    return sorted(result, key=lambda item: str(item).casefold())


@dataclass(frozen=True)
class StrategyTesterEnvironment:
    terminal_path: str = ""
    metaeditor_path: str = ""
    metatester_path: str = ""
    installation_path: str = ""
    data_roots: tuple[str, ...] = ()
    selected_data_root: str = ""
    terminal_version: str = "NOT_PRESENT"
    terminal_sha256: str = "NOT_PRESENT"
    ambiguity: str = ""
    discovery_errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return bool(self.terminal_path and self.selected_data_root and not self.ambiguity)

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self) | {"ready": self.ready})


def discover_environment(
    install_roots: Optional[Iterable[Path | str]] = None,
    data_parent: Path | str | None = None,
    selected_data_root: Path | str | None = None,
) -> StrategyTesterEnvironment:
    """Discover MT5 files without starting any executable or reading secrets."""
    roots = tuple(Path(item) for item in (install_roots or _default_install_roots()))
    terminals = _find_terminals(roots)
    errors: list[str] = []
    data_roots = _data_roots(Path(data_parent) if data_parent else _default_data_parent())
    selected = Path(selected_data_root).resolve() if selected_data_root else None
    if selected and selected not in data_roots:
        if selected.is_dir() and (selected / "MQL5").is_dir():
            data_roots.append(selected)
        else:
            errors.append("SELECTED_DATA_ROOT_NOT_FOUND")
            selected = None

    ambiguity = ""
    terminal = terminals[0] if len(terminals) == 1 else None
    if not terminals:
        ambiguity = "TERMINAL_NOT_FOUND"
    elif len(terminals) > 1:
        ambiguity = "MULTIPLE_TERMINALS"
    if selected is None:
        if len(data_roots) == 1:
            selected = data_roots[0]
        elif not data_roots:
            ambiguity = ambiguity or "DATA_ROOT_NOT_FOUND"
        else:
            ambiguity = ambiguity or "MULTIPLE_DATA_ROOTS"
    if terminal is None:
        return StrategyTesterEnvironment(data_roots=tuple(str(item) for item in data_roots),
                                         discovery_errors=tuple(errors), ambiguity=ambiguity)
    installation = terminal.parent
    metaeditor = installation / "MetaEditor64.exe"
    metatester = installation / "metatester64.exe"
    # Python's pathlib does not expose Windows PE product-version metadata;
    # do not substitute a timestamp and label it as a build version.
    version = "NOT_PRESENT"
    try:
        terminal_hash = _sha256(terminal)
    except OSError as exc:
        terminal_hash = "NOT_PRESENT"
        errors.append(type(exc).__name__)
    return StrategyTesterEnvironment(
        terminal_path=str(terminal), metaeditor_path=str(metaeditor) if metaeditor.is_file() else "",
        metatester_path=str(metatester) if metatester.is_file() else "",
        installation_path=str(installation), data_roots=tuple(str(item) for item in data_roots),
        selected_data_root=str(selected or ""), terminal_version=version,
        terminal_sha256=terminal_hash, ambiguity=ambiguity, discovery_errors=tuple(errors),
    )


def _safe_child(base: Path, relative: str, label: str) -> Path:
    raw = str(relative or "").strip().replace("/", "\\")
    if not raw or Path(raw).is_absolute() or not SAFE_RELATIVE_RE.fullmatch(raw):
        raise ValueError(f"{label}_PATH_INVALID")
    candidate = (base / Path(raw)).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"{label}_PATH_OUTSIDE_DATA_ROOT") from exc
    return candidate


def manifest_from_dict(payload: dict[str, Any]) -> GoldenTestRunManifest:
    """Rehydrate and verify a serialized manifest before it reaches MT5."""
    if not isinstance(payload, dict):
        raise ValueError("MANIFEST_OBJECT_REQUIRED")
    identity_data = dict(payload.get("identity") or {})
    test_run_id = str(payload.get("test_run_id") or identity_data.get("test_run_id") or "")
    if not RUN_ID_RE.fullmatch(test_run_id):
        raise ValueError("TEST_RUN_ID_INVALID")
    identity_fields = {field: identity_data.get(field, "") for field in TestRunIdentity.__dataclass_fields__}
    identity_fields["test_run_id"] = test_run_id
    identity = TestRunIdentity(**identity_fields)
    tester_data = dict(payload.get("tester") or {})
    tester_values = {
        field: tester_data.get(field, TesterConfiguration.__dataclass_fields__[field].default)
        for field in TesterConfiguration.__dataclass_fields__
    }
    config_ids = tester_values["config_artifact_ids"] or ()
    if isinstance(config_ids, str):
        try:
            parsed_ids = ast.literal_eval(config_ids)
            config_ids = parsed_ids if isinstance(parsed_ids, (list, tuple)) else (config_ids,)
        except (SyntaxError, ValueError):
            config_ids = (config_ids,)
    tester_values["config_artifact_ids"] = tuple(config_ids)
    tester = TesterConfiguration(**tester_values)
    parameters_data = dict(payload.get("parameters") or {})
    values = parameters_data.get("values")
    if not isinstance(values, dict):
        raise ValueError("MANIFEST_PARAMETERS_REQUIRED")
    parameters = EffectiveParameterSet.create(
        values, str(parameters_data.get("origin") or ""),
        source_artifact_id=str(parameters_data.get("source_artifact_id") or ""),
        preset_artifact_id=str(parameters_data.get("preset_artifact_id") or ""),
        source_ref=str(parameters_data.get("source_ref") or ""),
    )
    manifest = GoldenTestRunManifest.create(
        identity, tester, parameters,
        expected_result_artifacts=payload.get("expected_result_artifacts") or (),
        provenance=payload.get("provenance") or (),
    )
    supplied_hash = str(payload.get("manifest_hash") or "")
    if supplied_hash and supplied_hash != manifest.manifest_hash:
        raise ValueError("MANIFEST_HASH_MISMATCH")
    return manifest


@dataclass(frozen=True)
class TesterConfigArtifact:
    path: str
    sha256: str
    content: str
    report_name: str
    expected_report_path: str

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


class StrategyTesterAdapter:
    """One-process local tester boundary with explicit human and data gates."""

    execution_mode = "CONTROLLED_LOCAL_TESTER_CAPABILITY"
    trade_authority = "NONE"
    side_effect_class = "LOCAL_MUTATION"
    _active_lock = threading.Lock()
    _active_run_id = ""

    def __init__(self, catalog=None, process_factory: Callable[..., Any] | None = None,
                 poll_interval: float = 0.25):
        self.catalog = catalog
        self.process_factory = process_factory or subprocess.Popen
        self.poll_interval = max(0.05, float(poll_interval))

    @staticmethod
    def _human_gate(reason: str, environment: StrategyTesterEnvironment | None = None) -> dict[str, Any]:
        return {
            "HUMAN_ACTION_REQUIRED": True,
            "PURPOSE:": "Autorizar uma unica execucao local controlada do Strategy Tester, sem trading ao vivo.",
            "CURRENT_STATE:": reason,
            "WHAT I NEED YOU TO DO:": "Confirme explicitamente que a execucao local isolada pode iniciar e que nao ha outras instancias MT5 abertas.",
            "WHEN TO CLICK / SPEAK:": "Somente depois de revisar o manifesto, simbolo, periodo, EA, preset e a data de teste.",
            "WHAT YOU SHOULD SEE:": "Uma execucao unica, sem janela de ordem, com Optimization=0 e UseRemote/UseCloud=0.",
            "DO NOT:": "Nao habilite trading ao vivo, nao informe credenciais e nao aceite otimizacao ou conexao externa.",
            "AFTER THAT:": "Envie human_action_confirmed=true somente para este test_run_id.",
            "WAITING_FOR_USER:": "YES",
            "environment": environment.to_dict() if environment else None,
        }

    def build_config(
        self, manifest: GoldenTestRunManifest, environment: StrategyTesterEnvironment,
        expert_relative_path: str, preset_relative_path: str = "",
        run_root: Path | str = "", report_relative_path: str = "",
    ) -> TesterConfigArtifact:
        if not RUN_ID_RE.fullmatch(manifest.identity.test_run_id):
            raise ValueError("TEST_RUN_ID_INVALID")
        if not environment.ready:
            raise ValueError("ENVIRONMENT_NOT_RESOLVED")
        data_root = Path(environment.selected_data_root).resolve()
        expert = _safe_child(data_root / "MQL5" / "Experts", expert_relative_path, "EXPERT")
        if expert.suffix.casefold() != ".ex5" or not expert.is_file():
            raise ValueError("COMPILED_EA_REQUIRED")
        preset_name = ""
        if preset_relative_path:
            preset = _safe_child(data_root / "MQL5" / "Profiles" / "Tester", preset_relative_path, "PRESET")
            if not preset.is_file():
                raise ValueError("PRESET_NOT_FOUND")
            preset_name = preset.name
        root = Path(run_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        report_name = report_relative_path.replace("/", "\\") if report_relative_path else \
            f"Tester\\Jarvis\\{manifest.identity.test_run_id}.htm"
        if Path(report_name).is_absolute() or ".." in Path(report_name).parts:
            raise ValueError("REPORT_PATH_INVALID")
        expected_report = (Path(environment.installation_path) / report_name).resolve()
        lines = [
            "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0", "Enabled=1", "",
            "[Tester]", f"Expert={expert.relative_to(data_root / 'MQL5' / 'Experts').as_posix().replace('/', chr(92))}",
            f"Symbol={manifest.tester.symbol}", f"Period={manifest.tester.timeframe}",
            f"Model={_tester_model_value(manifest.tester.tester_model)}", "Optimization=0",
            "UseLocal=1", "UseRemote=0", "UseCloud=0", "Visual=0", "ReplaceReport=0",
            f"Report={report_name}", "ShutdownTerminal=1",
        ]
        if preset_name:
            lines.insert(8, f"ExpertParameters={preset_name}")
        if manifest.tester.date_from not in ("", "NOT_PRESENT"):
            lines.append(f"FromDate={manifest.tester.date_from}")
        if manifest.tester.date_to not in ("", "NOT_PRESENT"):
            lines.append(f"ToDate={manifest.tester.date_to}")
        content = "\n".join(lines) + "\n"
        path = root / "tester.ini"
        path.write_text(content, encoding="utf-8", newline="\n")
        return TesterConfigArtifact(str(path), content_hash(content), content, report_name, str(expected_report))

    def run(
        self, manifest: GoldenTestRunManifest, environment: StrategyTesterEnvironment,
        expert_relative_path: str, preset_relative_path: str = "", managed_root: Path | str = "",
        human_action_confirmed: bool = False, timeout_seconds: int = 900,
        result_json_path: Path | str = "",
    ) -> dict[str, Any]:
        run_id = manifest.identity.test_run_id
        if not human_action_confirmed:
            return {"ok": False, "status": "HUMAN_ACTION_REQUIRED", "test_run_id": run_id,
                    "gate": self._human_gate("Preflight concluido; nenhuma instancia foi iniciada.", environment)}
        if not environment.ready:
            return {"ok": False, "status": "EXECUTION_BLOCKED", "error": "ENVIRONMENT_NOT_RESOLVED",
                    "test_run_id": run_id, "gate": self._human_gate("Ambiente nao resolvido.", environment)}
        if timeout_seconds < 1 or timeout_seconds > 3600:
            return {"ok": False, "status": "EXECUTION_BLOCKED", "error": "TIMEOUT_OUT_OF_RANGE", "test_run_id": run_id}
        with self._active_lock:
            if self._active_run_id:
                return {"ok": False, "status": "EXECUTION_BLOCKED", "error": "RUN_ALREADY_ACTIVE",
                        "active_run_id": self._active_run_id}
            self._active_run_id = run_id
        try:
            run_root = Path(managed_root).resolve() / run_id
            expected_result_path = Path(result_json_path).resolve() if result_json_path else None
            stale_candidates = self._result_candidates(environment, expected_result_path)
            if any(path.is_file() for path in stale_candidates):
                payload = {"ok": False, "status": "EXECUTION_BLOCKED",
                           "error": "STALE_RESULT_ARTIFACT_PRESENT", "test_run_id": run_id,
                           "stale_result_paths": [str(path) for path in stale_candidates if path.is_file()]}
                self._persist(manifest, payload)
                return payload
            config = self.build_config(manifest, environment, expert_relative_path,
                                       preset_relative_path, run_root)
            command = [environment.terminal_path, f"/config:{config.path}"]
            started_at = time.time()
            process = self.process_factory(command, cwd=environment.installation_path,
                                           shell=False, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
            exit_code = None
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                exit_code = process.poll()
                if exit_code is not None:
                    break
                time.sleep(self.poll_interval)
            timed_out = exit_code is None
            if timed_out:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                exit_code = process.returncode
            discovered_result_path = self._discover_result_path(environment, expected_result_path)
            result = self._verify_result(
                manifest, discovered_result_path or result_json_path,
                allowed_roots=(
                    run_root,
                    Path(environment.selected_data_root) / "MQL5" / "Files",
                    Path(environment.selected_data_root).resolve().parents[1] /
                    "Tester" / Path(environment.selected_data_root).name,
                ),
            )
            status = "COMPLETED" if result.get("ok") and not timed_out and exit_code == 0 else \
                "FAILED" if not timed_out else "CANCELLED"
            payload = {"ok": status == "COMPLETED", "status": status, "test_run_id": run_id,
                       "exit_code": exit_code, "timed_out": timed_out,
                       "started_at": started_at, "finished_at": time.time(),
                       "config": config.to_dict(), "result": result}
            self._persist(manifest, payload)
            return payload
        except Exception as exc:
            payload = {"ok": False, "status": "FAILED", "test_run_id": run_id,
                       "error": type(exc).__name__, "message": str(exc)[:500]}
            self._persist(manifest, payload)
            return payload
        finally:
            with self._active_lock:
                self._active_run_id = ""

    @staticmethod
    def _tester_root(environment: StrategyTesterEnvironment) -> Path:
        data_root = Path(environment.selected_data_root).resolve()
        return data_root.parents[1] / "Tester" / data_root.name

    @classmethod
    def _result_candidates(cls, environment: StrategyTesterEnvironment,
                           expected_path: Optional[Path]) -> tuple[Path, ...]:
        if expected_path is None or not expected_path.name:
            return ()
        candidates = [expected_path]
        agent_root = cls._tester_root(environment)
        if agent_root.is_dir():
            candidates.extend(sorted(
                agent_root.glob(f"Agent-*/MQL5/Files/{expected_path.name}"),
                key=lambda item: str(item).casefold(),
            ))
        unique: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in unique:
                unique.append(resolved)
        return tuple(unique)

    @classmethod
    def _discover_result_path(cls, environment: StrategyTesterEnvironment,
                              expected_path: Optional[Path]) -> Optional[Path]:
        existing = [path for path in cls._result_candidates(environment, expected_path)
                    if path.is_file()]
        if not existing:
            return None
        return existing[0] if len(existing) == 1 else None

    def _verify_result(self, manifest: GoldenTestRunManifest, result_json_path: Path | str,
                       allowed_roots: Iterable[Path]) -> dict[str, Any]:
        if not result_json_path:
            return {"ok": False, "status": "UNVERIFIED", "error": "RESULT_JSON_REQUIRED"}
        path = Path(result_json_path).resolve()
        if not any(_is_relative_to(path, Path(root).resolve()) for root in allowed_roots):
            return {"ok": False, "status": "UNVERIFIED", "error": "RESULT_PATH_OUTSIDE_MANAGED_ROOT"}
        if not path.is_file():
            return {"ok": False, "status": "UNVERIFIED", "error": "RESULT_ARTIFACT_MISSING"}
        try:
            evidence: ResultEvidence = parse_result_json(path)
            reconciliation = reconcile_result(manifest, evidence)
            payload = {"ok": reconciliation.status == "RECONCILED", "status": reconciliation.status,
                       "evidence": evidence.to_dict(), "reconciliation": reconciliation.to_dict()}
            if reconciliation.status == "RECONCILED":
                bars = _positive_metric(evidence.metrics, "bars", "total_bars")
                ticks = _positive_metric(evidence.metrics, "ticks", "total_ticks",
                                         "deterministic_tick_count")
                if bars <= 0 or ticks <= 0:
                    payload.update({"ok": False, "status": "INVALID_EVIDENCE",
                                    "error": "NO_MARKET_DATA",
                                    "bars": bars, "ticks": ticks})
            return payload
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            return {"ok": False, "status": "UNVERIFIED", "error": type(exc).__name__}

    def _persist(self, manifest: GoldenTestRunManifest, result: dict[str, Any]) -> None:
        if self.catalog and manifest.identity.robot_id not in {"", "NOT_PRESENT"}:
            self.catalog.record_test_run(manifest.identity.robot_id, manifest.to_dict(), result)


def _tester_model_value(value: Any) -> str:
    normalized = str(value or "").casefold().replace("_", " ")
    return {"every tick": "0", "tick": "0", "ohlc": "1", "1 minute ohlc": "1",
            "open price": "2", "open price only": "2", "real ticks": "4",
            "every tick based on real ticks": "4"}.get(normalized, "0")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _positive_metric(metrics: dict[str, Any], *names: str) -> float:
    for name in names:
        value = metrics.get(name)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric > 0:
            return numeric
    return 0.0


__all__ = [
    "StrategyTesterAdapter", "StrategyTesterEnvironment", "TesterConfigArtifact",
    "discover_environment", "manifest_from_dict",
]
