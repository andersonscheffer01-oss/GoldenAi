"""Bounded native Strategy Tester result providers.

The bridge reads MT5 tester evidence as untrusted data.  It does not launch
MT5, grant execution authority, write the Robot Catalog, or infer metrics that
are absent from the raw artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .mql5_evidence import GoldenTestRunManifest, parse_result_json, reconcile_result


BRIDGE_VERSION = "jarvis-tester-result-bridge-v2"
MAX_NATIVE_LOG_BYTES = 8 * 1024 * 1024
NATIVE_LOG_KIND = "NATIVE_LOG"
FIXTURE_JSON_KIND = "EA_CUSTOM_ARTIFACT"
AUDIT_EVENTS = (
    "RESULT_PROVIDER_SELECTED",
    "RAW_TESTER_ARTIFACT_DISCOVERED",
    "RAW_TESTER_ARTIFACT_REJECTED",
    "RAW_TESTER_ARTIFACT_VERIFIED",
    "TESTER_RESULT_NORMALIZED",
    "TESTER_RESULT_RECONCILED",
    "TESTER_RESULT_CONFLICT",
)


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return _hash_bytes(raw)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _safe_child(root: Path | str, candidate: Path | str) -> Path:
    base = Path(root).resolve()
    path = Path(candidate).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("ARTIFACT_PATH_OUTSIDE_BOUNDARY") from exc
    return path


def _identity(expected: Mapping[str, Any], key: str, default: str = "NOT_PRESENT") -> str:
    value = expected.get(key, default)
    return str(value if value not in (None, "") else default)


@dataclass(frozen=True)
class MetricProvenance:
    raw_field: str
    raw_value: Any
    normalized_value: Any
    unit: str
    source_artifact: str
    provider: str
    confidence: str = "OBSERVED"
    status: str = "OBSERVED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedTesterResult:
    test_run_id: str
    campaign_id: str
    robot_id: str
    source_hash: str
    compiled_hash: str
    parameter_fingerprint: str
    symbol: str
    timeframe: str
    date_from: str
    date_to: str
    tester_model: str
    terminal_version: str
    data_root: str
    started_at: str
    finished_at: str
    artifact_kind: str
    artifact_path: str
    artifact_hash: str
    provider: str
    parser_version: str
    metrics: dict[str, Any]
    raw_metric_provenance: dict[str, MetricProvenance]
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    reconciliation_status: str = "UNRESOLVED"
    normalized_artifact_fingerprint: str = ""

    @classmethod
    def create(cls, **values: Any) -> "NormalizedTesterResult":
        values = dict(values)
        values["warnings"] = tuple(values.get("warnings") or ())
        values["limitations"] = tuple(values.get("limitations") or ())
        values["raw_metric_provenance"] = dict(values.get("raw_metric_provenance") or {})
        draft = cls(**values)
        payload = draft.to_dict(include_fingerprint=False)
        return cls(**{**values, "normalized_artifact_fingerprint": _canonical_hash(payload)})

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        payload["limitations"] = list(self.limitations)
        payload["raw_metric_provenance"] = {
            key: value.to_dict() if isinstance(value, MetricProvenance) else value
            for key, value in self.raw_metric_provenance.items()
        }
        if not include_fingerprint:
            payload.pop("normalized_artifact_fingerprint", None)
        return payload


@dataclass(frozen=True)
class NativeTesterLogContract:
    data_root: str
    test_run_id: str
    campaign_id: str
    robot_id: str
    source_hash: str
    compiled_hash: str
    parameter_fingerprint: str
    expert_relative_path: str
    symbol: str
    timeframe: str
    date_from: str
    date_to: str
    terminal_version: str = "NOT_PRESENT"
    config_hash: str = "NOT_PRESENT"
    started_at: str = "NOT_PRESENT"
    finished_at: str = "NOT_PRESENT"
    max_bytes: int = MAX_NATIVE_LOG_BYTES

    @property
    def log_directory(self) -> Path:
        return _safe_child(self.data_root, Path(self.data_root) / "Tester" / "logs")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "artifact_kind": NATIVE_LOG_KIND,
            "log_directory": str(self.log_directory),
            "filename_pattern": "YYYYMMDD.log",
            "association": "exact testing block + bounded run window + config identity",
        }


@dataclass(frozen=True)
class ProviderOutcome:
    status: str
    provider: str
    artifact_path: str = ""
    artifact_hash: str = ""
    normalized: NormalizedTesterResult | None = None
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "artifact_path": self.artifact_path,
            "artifact_hash": self.artifact_hash,
            "normalized": self.normalized.to_dict() if self.normalized else None,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


class TesterResultProvider(Protocol):
    """Read-only provider contract shared by native and fixture evidence."""

    provider_name: str
    parser_version: str

    def read(self, *args: Any, **kwargs: Any) -> ProviderOutcome:
        ...


_TEST_RE = re.compile(
    r"(?P<symbol>[A-Za-z0-9._-]+),(?P<timeframe>[A-Za-z0-9]+).*?"
    r"testing of (?P<expert>Experts\\[^\r\n]+?) from "
    r"(?P<date_from>\d{4}\.\d{2}\.\d{2}) [^ ]+ to "
    r"(?P<date_to>\d{4}\.\d{2}\.\d{2}) [^ ]+ started",
    re.IGNORECASE,
)
_BUILD_RE = re.compile(r"MetaTester\s+5\s+build\s+(?P<build>\d+)", re.IGNORECASE)
_DEPOSIT_RE = re.compile(r"initial deposit\s+(?P<value>-?\d+(?:\.\d+)?)\s+(?P<unit>[A-Z]{3})", re.IGNORECASE)
_BALANCE_RE = re.compile(r"final balance\s+(?P<value>-?\d+(?:\.\d+)?)\s+(?P<unit>[A-Z]{3})", re.IGNORECASE)
_TESTER_RE = re.compile(r"OnTester\s+result\s+(?P<value>-?\d+(?:\.\d+)?)", re.IGNORECASE)
_BARS_RE = re.compile(
    r"(?P<symbol>[A-Za-z0-9._-]+),(?P<timeframe>[A-Za-z0-9]+):\s+"
    r"(?P<ticks>\d+)\s+ticks,\s+(?P<bars>\d+)\s+bars generated",
    re.IGNORECASE,
)
_QUALITY_RE = re.compile(r"quality of analyzed history is\s+(?P<value>\d+(?:\.\d+)?)%", re.IGNORECASE)
_MODEL_REAL_TICKS_RE = re.compile(
    r"(?:every tick.*real ticks|generating based on real ticks)", re.IGNORECASE,
)
_MODEL_OHLC_RE = re.compile(r"minutes\s+OHLC\s+ticks generating", re.IGNORECASE)
_ROBUSTO_RE = re.compile(
    r"ROBUSTO\s*\|\s*score=(?P<score>-?\d+(?:\.\d+)?)\s+"
    r"aprovado=(?P<approved>SIM|NAO)\s+posicoes=(?P<positions>\d+)\s+"
    r"vitorias=(?P<wins>\d+)\s+derrotas=(?P<losses>\d+)\s+"
    r"lucro=(?P<net_result>-?\d+(?:\.\d+)?)\s+"
    r"PF=(?P<profit_factor>-?\d+(?:\.\d+)?)\s+"
    r"DD=(?P<drawdown>-?\d+(?:\.\d+)?)%\s+"
    r"expectativa=(?P<expectancy>-?\d+(?:\.\d+)?)\s+"
    r"concentracao=(?P<concentration>-?\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
def _metric(source: str, provider: str, raw_field: str, raw_value: Any,
            normalized: Any, unit: str = "", status: str = "OBSERVED") -> MetricProvenance:
    return MetricProvenance(raw_field, raw_value, normalized, unit, source, provider,
                            "OBSERVED", status)


class NativeTesterLogProvider:
    """Parses only bounded, native MetaTester journal logs."""

    provider_name = "NativeTesterLogProvider"
    parser_version = BRIDGE_VERSION

    def __init__(self, max_bytes: int = MAX_NATIVE_LOG_BYTES):
        self.max_bytes = int(max_bytes)

    def expected_contract(self, plan: Mapping[str, Any]) -> NativeTesterLogContract:
        return NativeTesterLogContract(
            data_root=_identity(plan, "data_root", ""),
            test_run_id=_identity(plan, "test_run_id"),
            campaign_id=_identity(plan, "campaign_id"),
            robot_id=_identity(plan, "robot_id"),
            source_hash=_identity(plan, "source_hash"),
            compiled_hash=_identity(plan, "compiled_hash"),
            parameter_fingerprint=_identity(plan, "parameter_fingerprint"),
            expert_relative_path=_identity(plan, "expert_relative_path"),
            symbol=_identity(plan, "symbol"),
            timeframe=_identity(plan, "timeframe"),
            date_from=_identity(plan, "date_from"),
            date_to=_identity(plan, "date_to"),
            terminal_version=_identity(plan, "terminal_version"),
            config_hash=_identity(plan, "config_hash"),
            started_at=_identity(plan, "started_at"),
            finished_at=_identity(plan, "finished_at"),
            max_bytes=self.max_bytes,
        )

    def discover(self, contract: NativeTesterLogContract,
                 artifact_window: tuple[float, float] | None = None) -> ProviderOutcome:
        directory = contract.log_directory
        if not directory.is_dir():
            return ProviderOutcome("RESULT_ARTIFACT_MISSING", self.provider_name,
                                   limitations=("NATIVE_LOG_DIRECTORY_MISSING",))
        candidates: list[Path] = []
        for path in sorted(directory.glob("*.log"), key=lambda item: str(item).casefold()):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > contract.max_bytes:
                continue
            if artifact_window and stat.st_mtime < float(artifact_window[0]) - 2:
                continue
            candidates.append(path)
        matches = []
        for path in candidates:
            outcome = self.read(path, contract, artifact_window=artifact_window)
            if outcome.status == "RECONCILED" and outcome.normalized:
                matches.append(outcome)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return ProviderOutcome("ARTIFACT_AMBIGUOUS", self.provider_name,
                                   limitations=("MULTIPLE_NATIVE_LOG_MATCHES",))
        return ProviderOutcome("RESULT_ARTIFACT_MISSING", self.provider_name,
                               limitations=("NO_OWNED_NATIVE_LOG_MATCH",))

    def read(self, path: Path | str, contract: NativeTesterLogContract,
             artifact_window: tuple[float, float] | None = None) -> ProviderOutcome:
        try:
            safe_path = _safe_child(contract.log_directory, path)
        except ValueError as exc:
            return ProviderOutcome("PATH_REJECTED", self.provider_name,
                                   warnings=(str(exc),))
        if not safe_path.is_file():
            return ProviderOutcome("RESULT_ARTIFACT_MISSING", self.provider_name,
                                   artifact_path=str(safe_path))
        try:
            stat = safe_path.stat()
            if stat.st_size > contract.max_bytes:
                return ProviderOutcome("ARTIFACT_TOO_LARGE", self.provider_name,
                                       artifact_path=str(safe_path))
            if artifact_window and stat.st_mtime < float(artifact_window[0]) - 2:
                return ProviderOutcome("STALE_ARTIFACT", self.provider_name,
                                       artifact_path=str(safe_path),
                                       warnings=("NATIVE_LOG_PRECEDES_RUN_WINDOW",))
            raw = safe_path.read_bytes()
        except OSError as exc:
            return ProviderOutcome("ARTIFACT_READ_FAILED", self.provider_name,
                                   artifact_path=str(safe_path), warnings=(type(exc).__name__,))
        raw_hash = _hash_bytes(raw)
        text = _decode(raw)
        blocks = self._blocks(text)
        matches = [block for block in blocks if self._matches(block, contract, text)]
        if not matches:
            return ProviderOutcome("ARTIFACT_NOT_OWNED", self.provider_name,
                                   str(safe_path), raw_hash,
                                   limitations=("EXACT_TEST_BLOCK_NOT_FOUND",))
        if len(matches) > 1:
            return ProviderOutcome("ARTIFACT_AMBIGUOUS", self.provider_name,
                                   str(safe_path), raw_hash,
                                   limitations=("MULTIPLE_OWNED_TEST_BLOCKS",))
        normalized = self._normalize(matches[0], contract, str(safe_path), raw_hash)
        return ProviderOutcome("RECONCILED", self.provider_name, str(safe_path),
                               raw_hash, normalized)

    @staticmethod
    def _blocks(text: str) -> list[tuple[re.Match[str], str, str]]:
        matches = list(_TEST_RE.finditer(text))
        return [(match, text[match.start():matches[index + 1].start()
                              if index + 1 < len(matches) else len(text)],
                 text[max(0, match.start() - 2000):match.start()])
                for index, match in enumerate(matches)]

    @staticmethod
    def _matches(block: tuple[re.Match[str], str, str], contract: NativeTesterLogContract,
                 text: str) -> bool:
        match, body, _ = block
        values = match.groupdict()
        expected_expert = "Experts\\" + contract.expert_relative_path.replace("/", "\\")
        actual_expert = values["expert"].strip().rstrip(".")
        if actual_expert.casefold() != expected_expert.casefold():
            return False
        if values["symbol"].casefold() != contract.symbol.casefold():
            return False
        if values["timeframe"].casefold() != contract.timeframe.casefold():
            return False
        if values["date_from"] != contract.date_from or values["date_to"] != contract.date_to:
            return False
        if contract.terminal_version not in ("", "NOT_PRESENT"):
            build = _BUILD_RE.search(text)
            if build and not contract.terminal_version.endswith(build.group("build")):
                return False
        return bool(body.strip())

    def _normalize(self, block: tuple[re.Match[str], str, str], contract: NativeTesterLogContract,
                   artifact_path: str, raw_hash: str) -> NormalizedTesterResult:
        match, body, prefix = block
        context = prefix + body
        metrics: dict[str, Any] = {}
        provenance: dict[str, MetricProvenance] = {}

        def add(name: str, raw_field: str, raw_value: Any, value: Any, unit: str = "") -> None:
            metrics[name] = value
            provenance[name] = _metric(artifact_path, self.provider_name, raw_field,
                                       raw_value, value, unit)

        deposit = _DEPOSIT_RE.search(context)
        if deposit:
            add("initial_deposit", "initial deposit", float(deposit.group("value")),
                float(deposit.group("value")), deposit.group("unit").upper())
        balance = _BALANCE_RE.search(context)
        if balance:
            add("final_balance", "final balance", float(balance.group("value")),
                float(balance.group("value")), balance.group("unit").upper())
        tester = _TESTER_RE.search(body)
        if tester:
            add("on_tester", "OnTester result", float(tester.group("value")),
                float(tester.group("value")))
        bars = _BARS_RE.search(body)
        if bars:
            add("ticks", "ticks", int(bars.group("ticks")), int(bars.group("ticks")), "count")
            add("bars", "bars", int(bars.group("bars")), int(bars.group("bars")), "count")
        quality = _QUALITY_RE.search(context)
        if quality:
            add("history_quality", "quality of analyzed history", float(quality.group("value")),
                float(quality.group("value")), "%")
        robusto = _ROBUSTO_RE.search(body)
        if robusto:
            values = robusto.groupdict()
            add("custom_on_tester_score", "ROBUSTO score", float(values["score"]),
                float(values["score"]))
            add("custom_complete_positions", "ROBUSTO posicoes", int(values["positions"]),
                int(values["positions"]), "count")
            add("custom_wins", "ROBUSTO vitorias", int(values["wins"]),
                int(values["wins"]), "count")
            add("custom_losses", "ROBUSTO derrotas", int(values["losses"]),
                int(values["losses"]), "count")
            add("custom_net_result", "ROBUSTO lucro", float(values["net_result"]),
                float(values["net_result"]))
            add("custom_profit_factor", "ROBUSTO PF", float(values["profit_factor"]),
                float(values["profit_factor"]))
            add("custom_drawdown_percent", "ROBUSTO DD", float(values["drawdown"]),
                float(values["drawdown"]), "%")
            add("custom_expectancy", "ROBUSTO expectativa", float(values["expectancy"]),
                float(values["expectancy"]))
            add("custom_concentration_percent", "ROBUSTO concentracao",
                float(values["concentration"]), float(values["concentration"]), "%")
            add("custom_approved", "ROBUSTO aprovado", values["approved"],
                values["approved"].casefold() == "sim")
        model = "REAL TICKS" if _MODEL_REAL_TICKS_RE.search(context) else \
            "OHLC" if _MODEL_OHLC_RE.search(context) else "UNKNOWN"
        build = _BUILD_RE.search(context)
        limitations = ["NATIVE_TESTER_LOG_EXPOSES_SUBSET_OF_METRICS"]
        if model == "UNKNOWN":
            limitations.append("TESTER_MODEL_NOT_OBSERVED_IN_LOG")
        if "total_trades" not in metrics:
            limitations.append("TOTAL_TRADES_NOT_EXPOSED")
        return NormalizedTesterResult.create(
            test_run_id=contract.test_run_id,
            campaign_id=contract.campaign_id,
            robot_id=contract.robot_id, source_hash=contract.source_hash,
            compiled_hash=contract.compiled_hash,
            parameter_fingerprint=contract.parameter_fingerprint,
            symbol=match.group("symbol"), timeframe=match.group("timeframe"),
            date_from=match.group("date_from"), date_to=match.group("date_to"),
            tester_model=model, terminal_version=contract.terminal_version if contract.terminal_version != "NOT_PRESENT" else ("5.0.0." + build.group("build") if build else "NOT_PRESENT"),
            data_root=contract.data_root, started_at=contract.started_at,
            finished_at=contract.finished_at, artifact_kind=NATIVE_LOG_KIND,
            artifact_path=artifact_path, artifact_hash=raw_hash,
            provider=self.provider_name, parser_version=self.parser_version,
            metrics=metrics, raw_metric_provenance=provenance,
            warnings=(), limitations=tuple(limitations),
            reconciliation_status="RECONCILED",
        )


class FixtureJsonResultProvider:
    """Adapter preserving the proven B4.4 fixture JSON contract."""

    provider_name = "FixtureJsonResultProvider"
    parser_version = BRIDGE_VERSION

    def read(self, path: Path | str, manifest: GoldenTestRunManifest,
             campaign_id: str = "") -> ProviderOutcome:
        try:
            result = parse_result_json(path)
            reconciliation = reconcile_result(manifest, result)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            return ProviderOutcome("CORRUPT_ARTIFACT", self.provider_name,
                                   artifact_path=str(path), warnings=(type(exc).__name__,))
        raw = Path(path).read_bytes()
        provenance = {
            key: _metric(str(path), self.provider_name, key, value, value)
            for key, value in result.metrics.items()
        }
        identity = manifest.identity
        tester = manifest.tester
        normalized = NormalizedTesterResult.create(
            test_run_id=identity.test_run_id, campaign_id=campaign_id,
            robot_id=identity.robot_id, source_hash=identity.source_hash,
            compiled_hash=identity.compiled_hash,
            parameter_fingerprint=identity.parameter_fingerprint,
            symbol=tester.symbol, timeframe=tester.timeframe,
            date_from=str(tester.date_from), date_to=str(tester.date_to),
            tester_model=str(tester.tester_model), terminal_version=str(tester.terminal_build),
            data_root="NOT_PRESENT", started_at=identity.started_at,
            finished_at=identity.finished_at, artifact_kind=FIXTURE_JSON_KIND,
            artifact_path=str(path), artifact_hash=_hash_bytes(raw),
            provider=self.provider_name, parser_version=self.parser_version,
            metrics=result.metrics, raw_metric_provenance=provenance,
            warnings=tuple(result.missing_fields), limitations=(),
            reconciliation_status=reconciliation.status,
        )
        return ProviderOutcome(reconciliation.status, self.provider_name, str(path),
                              _hash_bytes(raw), normalized)


def compare_results(left: NormalizedTesterResult, right: NormalizedTesterResult) -> str:
    """Compare only overlapping normalized metrics; never pick a winner."""
    shared = set(left.metrics).intersection(right.metrics)
    if not shared:
        return "NOT_COMPARABLE"
    if all(left.metrics[key] == right.metrics[key] for key in shared):
        return "MATCH" if set(left.metrics) == set(right.metrics) else "PARTIAL_MATCH"
    return "CONFLICT"


__all__ = [
    "AUDIT_EVENTS", "BRIDGE_VERSION", "FIXTURE_JSON_KIND", "MAX_NATIVE_LOG_BYTES",
    "MetricProvenance", "NativeTesterLogContract", "NativeTesterLogProvider",
    "NormalizedTesterResult", "ProviderOutcome", "TesterResultProvider",
    "FixtureJsonResultProvider",
    "compare_results",
]
