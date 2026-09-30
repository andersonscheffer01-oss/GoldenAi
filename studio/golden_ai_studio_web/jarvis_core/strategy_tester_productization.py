"""Canonical contracts for the supervised Strategy Tester capability.

This module is deliberately a contract and dry-run layer. It does not start
MT5, MetaTester, MetaEditor, a broker connection, or an order surface. The
existing StrategyTesterAdapter remains the only process boundary; JarvisService
and SecurityManager remain the owners of authorization and invocation.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


RUN_ID_RE = re.compile(r"^run_[a-f0-9]{32}$")
FIXTURE_ID = "fixture_golden_strategy_tester_v1"
FIXTURE_DISPLAY_NAME = "GoldenStrategyTesterFixture"
PURPOSE = "PIPELINE_VALIDATION_FIXTURE"
TERMINAL_TARGET = r"C:\Program Files\MetaTrader 5\terminal64.exe"
DATA_ROOT_TARGET = (
    "C:\\Users\\Anderson\\AppData\\Roaming\\MetaQuotes\\Terminal\\"
    "D0E8209F77C8CF37AD8BF550E51FF075"
)
ACTION = "STRATEGY_TESTER_RUN"
REQUIRED_CONFIG = {
    "AllowLiveTrading": "0",
    "AllowDllImport": "0",
    "Optimization": "0",
    "UseRemote": "0",
    "UseCloud": "0",
    "Visual": "0",
    "ShutdownTerminal": "1",
}
FORBIDDEN_CONFIG_TOKENS = ("password", "token", "api_key", "credential")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")


def _plan_payload(plan: "TestPlan") -> dict[str, Any]:
    return {
        "test_run_id": plan.test_run_id,
        "robot_id": plan.robot_id,
        "fixture_id": plan.fixture_id,
        "source_hash": plan.source_hash,
        "compiled_hash": plan.compiled_hash,
        "symbol": plan.symbol,
        "timeframe": plan.timeframe,
        "date_from": plan.date_from,
        "date_to": plan.date_to,
        "tester_model": plan.tester_model,
        "deposit": plan.deposit,
        "currency": plan.currency,
        "leverage": plan.leverage,
        "parameter_fingerprint": plan.parameter_fingerprint,
        "terminal_path": plan.terminal_path,
        "terminal_sha256": plan.terminal_sha256,
        "data_root": plan.data_root,
        "expert_relative_path": plan.expert_relative_path,
        "preset_name": plan.preset_name,
        "expected_result_directory": plan.expected_result_directory,
        "expected_result_basename": plan.expected_result_basename,
        "allowed_result_formats": list(plan.allowed_result_formats),
        "tester_report_relative_path": plan.tester_report_relative_path,
        "timeout_seconds": plan.timeout_seconds,
        "purpose": plan.purpose,
        "created_at": plan.created_at,
    }


@dataclass(frozen=True)
class TestPlan:
    """Immutable, action-bound description of one supervised tester run."""

    test_run_id: str
    robot_id: str
    fixture_id: str
    source_hash: str
    compiled_hash: str
    symbol: str
    timeframe: str
    date_from: str
    date_to: str
    tester_model: str
    deposit: str = "NOT_PRESENT"
    currency: str = "NOT_PRESENT"
    leverage: str = "NOT_PRESENT"
    parameter_fingerprint: str = "NOT_PRESENT"
    terminal_path: str = TERMINAL_TARGET
    terminal_sha256: str = "NOT_PRESENT"
    data_root: str = DATA_ROOT_TARGET
    expert_relative_path: str = (
        r"GoldenTestFixtures\GoldenStrategyTesterFixtureCanonical.ex5"
    )
    preset_name: str = ""
    expected_result_directory: str = ""
    expected_result_basename: str = ""
    allowed_result_formats: tuple[str, ...] = (".json",)
    tester_report_relative_path: str = ""
    timeout_seconds: int = 900
    purpose: str = PURPOSE
    created_at: str = field(default_factory=_now)
    plan_fingerprint: str = ""

    @classmethod
    def create(cls, **values: Any) -> "TestPlan":
        values = dict(values)
        values.setdefault("created_at", _now())
        values.setdefault("purpose", PURPOSE)
        values.setdefault("allowed_result_formats", (".json",))
        values["allowed_result_formats"] = tuple(values["allowed_result_formats"])
        draft = cls(**values)
        draft.validate()
        payload = _plan_payload(draft)
        payload["allowed_result_formats"] = draft.allowed_result_formats
        return cls(**payload,
                   plan_fingerprint=_hash_bytes(_canonical(_plan_payload(draft))))

    def validate(self) -> None:
        if not RUN_ID_RE.fullmatch(self.test_run_id):
            raise ValueError("TEST_RUN_ID_INVALID")
        if self.robot_id != FIXTURE_ID or self.fixture_id != FIXTURE_ID:
            raise ValueError("FIXTURE_IDENTITY_MISMATCH")
        if self.purpose != PURPOSE:
            raise ValueError("TEST_PURPOSE_NOT_ALLOWED")
        if not self.source_hash or not self.compiled_hash:
            raise ValueError("FIXTURE_ARTIFACT_HASH_REQUIRED")
        if self.terminal_path != TERMINAL_TARGET:
            raise ValueError("TERMINAL_TARGET_MISMATCH")
        if self.data_root != DATA_ROOT_TARGET:
            raise ValueError("DATA_ROOT_TARGET_MISMATCH")
        if not self.symbol or not self.timeframe or not self.date_from or not self.date_to:
            raise ValueError("TESTER_SCOPE_INCOMPLETE")
        if not self.expected_result_directory or not self.expected_result_basename:
            raise ValueError("RESULT_CONTRACT_INCOMPLETE")
        if not self.expected_result_basename.endswith(".json"):
            raise ValueError("RESULT_FORMAT_NOT_ALLOWED")
        if self.timeout_seconds < 1 or self.timeout_seconds > 3600:
            raise ValueError("TIMEOUT_OUT_OF_RANGE")
        if any(fmt not in {".json"} for fmt in self.allowed_result_formats):
            raise ValueError("RESULT_FORMAT_NOT_ALLOWED")

    def to_dict(self) -> dict[str, Any]:
        result = _plan_payload(self)
        result["allowed_result_formats"] = list(self.allowed_result_formats)
        result["plan_fingerprint"] = self.plan_fingerprint
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TestPlan":
        if not isinstance(payload, dict):
            raise ValueError("TEST_PLAN_OBJECT_REQUIRED")
        values = dict(payload)
        supplied = str(values.pop("plan_fingerprint", ""))
        values["allowed_result_formats"] = tuple(values.get("allowed_result_formats") or ())
        plan = cls(**values, plan_fingerprint=supplied)
        plan.validate()
        expected = _hash_bytes(_canonical(_plan_payload(plan)))
        if supplied != expected:
            raise ValueError("PLAN_FINGERPRINT_MISMATCH")
        return plan


@dataclass(frozen=True)
class ConfigVerification:
    ok: bool
    status: str
    expected_hash: str
    actual_hash: str
    semantic_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "semantic_errors": list(self.semantic_errors),
        }


def render_tester_config(plan: TestPlan) -> bytes:
    """Render deterministic UTF-8/LF tester.ini bytes from the immutable plan."""
    plan.validate()
    lines = [
        "[Experts]",
        "AllowLiveTrading=0",
        "AllowDllImport=0",
        "Enabled=1",
        "",
        "[Tester]",
        f"Expert={plan.expert_relative_path.replace('/', chr(92))}",
        f"Symbol={plan.symbol}",
        f"Period={plan.timeframe}",
        f"Model={_model_value(plan.tester_model)}",
        "Optimization=0",
        "UseLocal=1",
        "UseRemote=0",
        "UseCloud=0",
        "Visual=0",
        "ReplaceReport=0",
        f"Report={plan.tester_report_relative_path}",
        "ShutdownTerminal=1",
        f"FromDate={plan.date_from}",
        f"ToDate={plan.date_to}",
    ]
    if plan.preset_name:
        lines.insert(8, f"ExpertParameters={plan.preset_name}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _model_value(value: str) -> str:
    return {"OHLC": "1", "1 MINUTE OHLC": "1", "OPEN PRICE": "2",
            "REAL TICKS": "4", "EVERY TICK": "0"}.get(str(value).upper(), "0")


def _parse_config(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8")
    parsed: dict[str, str] = {}
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            parsed[f"{section}.{key.strip()}"] = value.strip()
    return parsed


def verify_tester_config(plan: TestPlan, raw: bytes, expected_hash: str = "") -> ConfigVerification:
    """Verify bytes and safety semantics before a process could be launched."""
    actual = _hash_bytes(raw)
    errors: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("UTF8_BOM_NOT_ALLOWED")
    if b"\r\n" in raw:
        errors.append("CRLF_NOT_ALLOWED")
    try:
        parsed = _parse_config(raw)
    except (UnicodeDecodeError, ValueError):
        parsed = {}
        errors.append("CONFIG_ENCODING_INVALID")
    for key, value in REQUIRED_CONFIG.items():
        if parsed.get(f"Experts.{key}", parsed.get(f"Tester.{key}")) != value:
            errors.append(f"CONFIG_{key}_MISMATCH")
    expected_fields = {
        "Tester.Symbol": plan.symbol,
        "Tester.Period": plan.timeframe,
        "Tester.FromDate": plan.date_from,
        "Tester.ToDate": plan.date_to,
        "Tester.Report": plan.tester_report_relative_path,
    }
    for key, value in expected_fields.items():
        if parsed.get(key) != value:
            errors.append(f"CONFIG_{key.replace('.', '_').upper()}_MISMATCH")
    lowered = raw.decode("utf-8", errors="ignore").casefold()
    if any(token in lowered for token in FORBIDDEN_CONFIG_TOKENS):
        errors.append("SECRET_LIKE_CONFIG_FIELD")
    if expected_hash and actual != expected_hash:
        errors.append("CONFIG_HASH_MISMATCH")
    status = "CONFIG_VERIFIED" if not errors else "CONFIG_REJECTED"
    return ConfigVerification(not errors, status, expected_hash, actual, tuple(errors))


@dataclass(frozen=True)
class ResultArtifactContract:
    directory: str
    basename: str
    allowed_formats: tuple[str, ...] = (".json",)

    def candidates(self, roots: Iterable[Path | str]) -> tuple[Path, ...]:
        result: list[Path] = []
        for root in roots:
            candidate = (Path(root).resolve() / self.basename).resolve()
            if candidate.suffix.casefold() not in self.allowed_formats:
                continue
            if candidate not in result:
                result.append(candidate)
        return tuple(result)

    def discover(self, roots: Iterable[Path | str]) -> dict[str, Any]:
        candidates = self.candidates(roots)
        existing = [path for path in candidates if path.is_file()]
        if not existing:
            return {"ok": False, "status": "RESULT_ARTIFACT_MISSING",
                    "candidates": [str(path) for path in candidates]}
        if len(existing) != 1:
            return {"ok": False, "status": "RESULT_ARTIFACT_AMBIGUOUS",
                    "candidates": [str(path) for path in existing]}
        return {"ok": True, "status": "ARTIFACT_FOUND", "path": str(existing[0]),
                "ownership": "BOUNDED_BASENAME_AND_RUN_CONTRACT"}


@dataclass(frozen=True)
class ApprovalScope:
    action: str
    test_run_id: str
    fixture_id: str
    terminal_path: str
    data_root: str
    config_fingerprint: str
    issued_at: str
    expires_at: str
    single_use: bool = True


class SingleUseApproval:
    """Target binding used by dry-run tests; SecurityManager remains owner."""

    def __init__(self, scope: ApprovalScope):
        self.scope = scope
        self._consumed = False

    @classmethod
    def issue(cls, plan: TestPlan, config_fingerprint: str,
              ttl_seconds: int = 300, now: datetime | None = None) -> "SingleUseApproval":
        issued = now or datetime.now(timezone.utc)
        scope = ApprovalScope(ACTION, plan.test_run_id, plan.fixture_id,
                              plan.terminal_path, plan.data_root, config_fingerprint,
                              issued.isoformat(), (issued + timedelta(seconds=ttl_seconds)).isoformat())
        return cls(scope)

    def consume(self, plan: TestPlan, config_fingerprint: str,
                now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        if self._consumed:
            return {"ok": False, "error": "APPROVAL_REUSED"}
        if current >= datetime.fromisoformat(self.scope.expires_at):
            return {"ok": False, "error": "APPROVAL_EXPIRED"}
        if (self.scope.action != ACTION or self.scope.test_run_id != plan.test_run_id or
                self.scope.fixture_id != plan.fixture_id or
                self.scope.terminal_path != plan.terminal_path or
                self.scope.data_root != plan.data_root or
                self.scope.config_fingerprint != config_fingerprint):
            return {"ok": False, "error": "APPROVAL_TARGET_MISMATCH"}
        self._consumed = True
        return {"ok": True, "status": "APPROVAL_CONSUMED", "test_run_id": plan.test_run_id}


def pre_execution_gate(plan: TestPlan, config: ConfigVerification,
                       artifact_known: bool, terminal_isolated: bool,
                       security_allow_with_approval: bool,
                       approval: dict[str, Any], dry_run_passed: bool) -> dict[str, Any]:
    checks = {
        "exact_approved_fixture": plan.fixture_id == FIXTURE_ID and plan.robot_id == FIXTURE_ID,
        "production_ea": False,
        "exact_terminal": plan.terminal_path == TERMINAL_TARGET,
        "exact_data_root": plan.data_root == DATA_ROOT_TARGET,
        "isolated_config": config.ok,
        "config_semantic_validation": config.ok,
        "config_byte_fingerprint": bool(config.ok and config.actual_hash == config.expected_hash),
        "expected_artifact_contract": artifact_known,
        "artifact_directory_isolated": artifact_known,
        "security_manager": security_allow_with_approval,
        "approval_target_bound": bool(approval.get("ok")),
        "approval_single_use": bool(approval.get("ok")),
        "terminal_isolated": terminal_isolated,
        "no_live_trading_mutation": True,
        "no_autotrading_mutation": True,
        "no_order_send_path": True,
        "no_credentials": True,
        "dry_run_suite": dry_run_passed,
        "cleanup_ready": True,
    }
    return {"allowed": all(checks.values()), "checks": checks,
            "blocked_by": [name for name, passed in checks.items() if not passed]}


def classify_process_outcome(timed_out: bool) -> str:
    """Classify a bounded process boundary without owning the process."""
    return "PROCESS_TIMEOUT" if timed_out else "PROCESS_EXITED"


def productization_snapshot() -> dict[str, Any]:
    """Read model for Control Center; it exposes status but no action endpoint."""
    return {
        "capability": "CONTROLLED_STRATEGY_TESTER",
        "mode": "BACKTEST_TESTER",
        "execution_authority": "JarvisService -> StrategyTesterAdapter",
        "security_authority": "SecurityManager",
        "evidence_authority": "RobotCatalog",
        "ui_mode": "READ_ONLY_STATUS",
        "production_execution_enabled": False,
        "optimization": 0,
        "use_remote": 0,
        "use_cloud": 0,
        "allow_live_trading": 0,
        "real_run_count_this_batch": 0,
    }


def dry_run_matrix() -> dict[str, str]:
    """Exercise the critical boundary cases without starting any process."""
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory(prefix="jarvis-b44-dry-") as raw_root:
        root = Path(raw_root)
        plan = TestPlan.create(
            test_run_id="run_" + "a" * 32,
            robot_id=FIXTURE_ID,
            fixture_id=FIXTURE_ID,
            source_hash="a" * 64,
            compiled_hash="b" * 64,
            symbol="EURUSD",
            timeframe="M1",
            date_from="2025.01.02",
            date_to="2025.01.03",
            tester_model="OHLC",
            parameter_fingerprint="c" * 24,
            expected_result_directory=str(root / "run"),
            expected_result_basename="GoldenStrategyTesterFixture_run_" + "a" * 32 + ".json",
            tester_report_relative_path="Tester\\Jarvis\\run_" + "a" * 32 + ".htm",
            created_at="2026-09-29T00:00:00+00:00",
        )
        config_bytes = render_tester_config(plan)
        config_hash = _hash_bytes(config_bytes)
        config_ok = verify_tester_config(plan, config_bytes, config_hash).ok
        config_changed = verify_tester_config(
            plan, config_bytes.replace(b"UseCloud=0", b"UseCloud=1"), config_hash).ok
        approval = SingleUseApproval.issue(plan, config_hash, now=now)
        consumed = approval.consume(plan, config_hash, now=now)["ok"]
        reused = approval.consume(plan, config_hash, now=now)["error"] == "APPROVAL_REUSED"
        expired = SingleUseApproval.issue(plan, config_hash, ttl_seconds=1, now=now)
        expired_ok = expired.consume(plan, config_hash,
                                     now=now + timedelta(seconds=2))["error"] == "APPROVAL_EXPIRED"
        contract = ResultArtifactContract(plan.expected_result_directory,
                                          plan.expected_result_basename)
        missing = contract.discover((root / "agent-a",))["status"] == "RESULT_ARTIFACT_MISSING"
        for agent in (root / "agent-a", root / "agent-b"):
            agent.mkdir()
            (agent / plan.expected_result_basename).write_text("{}", encoding="utf-8")
        ambiguous = contract.discover((root / "agent-a", root / "agent-b"))["status"] == "RESULT_ARTIFACT_AMBIGUOUS"
        fixture_values = plan.to_dict()
        fixture_values.pop("plan_fingerprint", None)
        try:
            TestPlan.create(**{**fixture_values, "fixture_id": "production_robot"})
        except ValueError as exc:
            fixture_mismatch = str(exc) == "FIXTURE_IDENTITY_MISMATCH"
        else:
            fixture_mismatch = False
        terminal_values = plan.to_dict()
        terminal_values.pop("plan_fingerprint", None)
        try:
            TestPlan.create(**{**terminal_values, "terminal_path": "C:\\other\\terminal64.exe"})
        except ValueError as exc:
            wrong_terminal = str(exc) == "TERMINAL_TARGET_MISMATCH"
        else:
            wrong_terminal = False
        try:
            json.loads(b"{")
        except json.JSONDecodeError:
            parse_failure = True
        else:
            parse_failure = False
        stale_approval = SingleUseApproval.issue(plan, config_hash, now=now)
        stale_target = stale_approval.consume(plan, "e" * 64, now=now)["error"] == "APPROVAL_TARGET_MISMATCH"
        return {
            "success": "PASS" if config_ok and consumed else "FAIL",
            "config_mismatch": "PASS" if not config_changed else "FAIL",
            "fixture_mismatch": "PASS" if fixture_mismatch else "FAIL",
            "wrong_terminal": "PASS" if wrong_terminal else "FAIL",
            "missing_artifact": "PASS" if missing else "FAIL",
            "ambiguous_artifact": "PASS" if ambiguous else "FAIL",
            "parse_failure": "PASS" if parse_failure else "FAIL",
            "timeout": "PASS" if classify_process_outcome(True) == "PROCESS_TIMEOUT" else "FAIL",
            "expired_approval": "PASS" if expired_ok else "FAIL",
            "reused_approval": "PASS" if reused else "FAIL",
            "stale_target": "PASS" if stale_target else "FAIL",
        }


__all__ = [
    "ACTION", "ApprovalScope", "ConfigVerification", "DATA_ROOT_TARGET",
    "FIXTURE_DISPLAY_NAME", "FIXTURE_ID", "PURPOSE", "ResultArtifactContract",
    "SingleUseApproval", "TERMINAL_TARGET", "TestPlan", "dry_run_matrix",
    "classify_process_outcome", "pre_execution_gate", "productization_snapshot",
    "render_tester_config",
    "verify_tester_config",
]
