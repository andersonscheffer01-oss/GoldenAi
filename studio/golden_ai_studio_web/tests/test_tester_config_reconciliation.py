from pathlib import Path

import pytest

from jarvis_core.tester_config_reconciliation import (
    MATERIALIZATION_VERSION,
    materialize_config,
    materialized_config_fingerprint,
    reconcile_configs,
)


BASE = """[Experts]
AllowLiveTrading=0
AllowDllImport=0
Enabled=1

[Tester]
Expert=EA\\Robot.ex5
Symbol=XAUUSD
ExpertParameters=Preset.set
Period=M1
Model=4
Optimization=0
UseLocal=1
UseRemote=0
UseCloud=0
Visual=0
ReplaceReport=0
Report=Tester\\Jarvis\\B45\\run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.htm
ShutdownTerminal=1
FromDate=2026.09.01
ToDate=2026.09.05
Deposit=100000
Currency=USD
Leverage=100
ExecutionMode=local
"""

RUN_ID = "run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CAMPAIGN_ID = "campaign_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_report_only_difference_is_deterministically_reconciled(tmp_path: Path):
    runtime = materialize_config(BASE, CAMPAIGN_ID, RUN_ID, tmp_path)
    result = reconcile_configs(BASE, runtime, expected_runtime=runtime)

    assert result.status == "RECONCILED_WITH_DETERMINISTIC_MATERIALIZATION"
    assert [(item.section, item.key, item.classification) for item in result.differences] == [
        ("Tester", "Report", "OUTPUT_ROUTING")
    ]
    assert result.scientific_config_fingerprint == \
        reconcile_configs(BASE, BASE).scientific_config_fingerprint
    assert result.materialized_config_fingerprint == materialized_config_fingerprint(runtime)
    assert result.materialization_version == MATERIALIZATION_VERSION


def test_materialization_is_deterministic_and_run_scoped(tmp_path: Path):
    first = materialize_config(BASE, CAMPAIGN_ID, RUN_ID, tmp_path)
    second = materialize_config(BASE, CAMPAIGN_ID, RUN_ID, tmp_path)
    other = materialize_config(BASE, CAMPAIGN_ID, "run_cccccccccccccccccccccccccccccccc", tmp_path)
    assert first == second
    assert first != other
    assert "Report=Tester\\Jarvis\\run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.htm" in first


@pytest.mark.parametrize("key", [
    "Expert", "ExpertParameters", "Symbol", "Period", "Model",
    "FromDate", "ToDate", "Optimization", "UseRemote", "UseCloud",
    "AllowLiveTrading", "AllowDllImport", "Deposit", "Currency", "Leverage",
    "ExecutionMode", "UseLocal", "Visual", "ShutdownTerminal", "Enabled",
])
def test_semantic_or_security_difference_fails_closed(key: str):
    changed = BASE.replace(f"{key}=", f"{key}=CHANGED_", 1)
    result = reconcile_configs(BASE, changed, expected_runtime=changed)
    assert result.status in {
        "SCIENTIFIC_CONFIG_MISMATCH", "EXECUTION_CONFIG_MISMATCH",
        "SECURITY_CONFIG_MISMATCH",
    }


def test_replace_report_is_output_routing_only():
    changed = BASE.replace("ReplaceReport=0", "ReplaceReport=1")
    result = reconcile_configs(BASE, changed, expected_runtime=changed)
    assert result.status == "RECONCILED_WITH_DETERMINISTIC_MATERIALIZATION"
    assert result.differences[0].classification == "OUTPUT_ROUTING"


def test_unknown_difference_fails_closed():
    changed = BASE + "UnknownFutureKey=1\n"
    result = reconcile_configs(BASE, changed, expected_runtime=changed)
    assert result.status == "UNKNOWN_CONFIG_DIFFERENCE"


def test_unexpected_runtime_mutation_fails_closed():
    expected = materialize_config(BASE, CAMPAIGN_ID, RUN_ID)
    mutated = expected.replace("ReplaceReport=0", "ReplaceReport=1")
    result = reconcile_configs(BASE, mutated, expected_runtime=expected)
    assert result.status == "UNEXPECTED_OPERATIONAL_MUTATION"


def test_materialization_rejects_invalid_identity_and_missing_report(tmp_path: Path):
    with pytest.raises(ValueError, match="TEST_RUN_ID_INVALID"):
        materialize_config(BASE, CAMPAIGN_ID, "run_bad", tmp_path)
    with pytest.raises(ValueError, match="CAMPAIGN_ID_INVALID"):
        materialize_config(BASE, "campaign_bad", RUN_ID, tmp_path)
    with pytest.raises(ValueError, match="REPORT_KEY_REQUIRED"):
        materialize_config(BASE.replace("Report=Tester\\Jarvis\\B45\\run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.htm\n", ""), CAMPAIGN_ID, RUN_ID, tmp_path)
    with pytest.raises(ValueError, match="REPORT_PATH_OUTSIDE_BOUNDARY"):
        materialize_config(BASE.replace("Report=Tester\\Jarvis\\B45\\run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.htm", "Report=..\\..\\outside.htm"), CAMPAIGN_ID, RUN_ID, tmp_path)
