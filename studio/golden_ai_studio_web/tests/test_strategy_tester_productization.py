import json
from datetime import datetime, timezone
from pathlib import Path

from jarvis_core.strategy_tester_productization import (
    DATA_ROOT_TARGET,
    FIXTURE_ID,
    PURPOSE,
    TERMINAL_TARGET,
    ResultArtifactContract,
    SingleUseApproval,
    TestPlan as StrategyTestPlan,
    dry_run_matrix,
    pre_execution_gate,
    productization_snapshot,
    render_tester_config,
    verify_tester_config,
)


def _plan(tmp_path):
    return StrategyTestPlan.create(
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
        expected_result_directory=str(tmp_path / "run"),
        expected_result_basename="GoldenStrategyTesterFixture_run_" + "a" * 32 + ".json",
        tester_report_relative_path="Tester\\Jarvis\\run_" + "a" * 32 + ".htm",
        created_at="2026-09-29T00:00:00+00:00",
    )


def test_plan_is_immutable_and_round_trips(tmp_path):
    plan = _plan(tmp_path)
    assert plan.plan_fingerprint
    assert StrategyTestPlan.from_dict(plan.to_dict()) == plan
    altered = plan.to_dict()
    altered["symbol"] = "XAUUSD"
    try:
        StrategyTestPlan.from_dict(altered)
    except ValueError as exc:
        assert str(exc) == "PLAN_FINGERPRINT_MISMATCH"
    else:
        raise AssertionError("altered plan was accepted")


def test_config_is_deterministic_and_fail_closed(tmp_path):
    plan = _plan(tmp_path)
    raw = render_tester_config(plan)
    expected = __import__("hashlib").sha256(raw).hexdigest()
    checked = verify_tester_config(plan, raw, expected)
    assert checked.ok is True
    assert b"Optimization=0" in raw
    assert b"UseRemote=0" in raw
    assert b"UseCloud=0" in raw
    assert b"AllowLiveTrading=0" in raw
    changed = raw.replace(b"UseCloud=0", b"UseCloud=1")
    assert verify_tester_config(plan, changed, expected).status == "CONFIG_REJECTED"


def test_bounded_artifact_discovery_distinguishes_missing_and_ambiguous(tmp_path):
    plan = _plan(tmp_path)
    contract = ResultArtifactContract(
        plan.expected_result_directory, plan.expected_result_basename)
    root_a = tmp_path / "agent-a"
    root_b = tmp_path / "agent-b"
    assert contract.discover((root_a,))["status"] == "RESULT_ARTIFACT_MISSING"
    for root in (root_a, root_b):
        root.mkdir()
        (root / plan.expected_result_basename).write_text("{}", encoding="utf-8")
    assert contract.discover((root_a, root_b))["status"] == "RESULT_ARTIFACT_AMBIGUOUS"


def test_single_use_approval_is_bound_and_expires(tmp_path):
    plan = _plan(tmp_path)
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    approval = SingleUseApproval.issue(plan, "d" * 64, ttl_seconds=60, now=now)
    consumed = approval.consume(plan, "d" * 64, now=now)
    assert consumed["ok"] is True
    assert approval.consume(plan, "d" * 64, now=now)["error"] == "APPROVAL_REUSED"
    expired = SingleUseApproval.issue(plan, "d" * 64, ttl_seconds=1, now=now)
    assert expired.consume(plan, "d" * 64, now=now.replace(second=2))["error"] == "APPROVAL_EXPIRED"


def test_pre_execution_gate_blocks_existing_user_terminal(tmp_path):
    plan = _plan(tmp_path)
    raw = render_tester_config(plan)
    config = verify_tester_config(plan, raw, __import__("hashlib").sha256(raw).hexdigest())
    approval = SingleUseApproval.issue(plan, "e" * 64, now=datetime.now(timezone.utc))
    result = pre_execution_gate(plan, config, True, False, True,
                                {"ok": True}, True)
    assert result["allowed"] is False
    assert "terminal_isolated" in result["blocked_by"]


def test_read_model_is_backtest_only_and_dry_matrix_is_explicit():
    snapshot = productization_snapshot()
    assert snapshot["mode"] == "BACKTEST_TESTER"
    assert snapshot["production_execution_enabled"] is False
    assert snapshot["real_run_count_this_batch"] == 0
    matrix = dry_run_matrix()
    assert set(matrix) == {
        "success", "config_mismatch", "fixture_mismatch", "wrong_terminal",
        "missing_artifact", "ambiguous_artifact", "parse_failure", "timeout",
        "expired_approval", "reused_approval", "stale_target",
    }
    assert all(value == "PASS" for value in matrix.values())
