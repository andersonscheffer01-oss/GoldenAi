from __future__ import annotations

import json
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.coding import CodingProjectService
from core.execution import ExecutionService, PermissionMode, RiskLevel
from core.tools.hashing import sha256_file


ROOT = Path(r"C:\GoldenAI")
FIXTURE = ROOT / "projetos" / "_capability_audit"
PROTECTED_MQ5 = ROOT / "projetos" / "Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5"


def reset_fixture() -> None:
    (FIXTURE / "audit_app").mkdir(parents=True, exist_ok=True)
    (FIXTURE / "tests").mkdir(parents=True, exist_ok=True)
    (FIXTURE / "mql5_fixture").mkdir(parents=True, exist_ok=True)
    (FIXTURE / "README.md").write_text("# Capability Audit Fixture\n", encoding="utf-8")
    (FIXTURE / "pyproject.toml").write_text("[tool.capability_audit]\ntest_command='python -m unittest discover -s tests'\n", encoding="utf-8")
    (FIXTURE / "audit_app" / "__init__.py").write_text("from .pipeline import run_order\n", encoding="utf-8")
    (FIXTURE / "audit_app" / "config.py").write_text("DEFAULT_TAX_RATE = 0.10\nMAX_DISCOUNT = 0.25\n", encoding="utf-8")
    (FIXTURE / "audit_app" / "models.py").write_text(
        "from dataclasses import dataclass\n\n@dataclass\nclass Order:\n    sku: str\n    quantity: int\n    unit_price: float\n    discount: float = 0.0\n",
        encoding="utf-8",
    )
    (FIXTURE / "audit_app" / "pricing.py").write_text(
        "from .config import DEFAULT_TAX_RATE, MAX_DISCOUNT\nfrom .models import Order\n\n\ndef subtotal(order: Order) -> float:\n    return order.quantity + order.unit_price\n\n\ndef validate_discount(discount: float) -> None:\n    if discount > 1:\n        raise ValueError(\"discount cannot exceed 100%\")\n\n\ndef total_with_tax(order: Order) -> float:\n    validate_discount(order.discount)\n    base = subtotal(order)\n    discounted = base * (1 - order.discount)\n    return round(discounted * DEFAULT_TAX_RATE, 2)\n",
        encoding="utf-8",
    )
    (FIXTURE / "audit_app" / "inventory.py").write_text(
        "STOCK = {\n    \"XAU\": 10,\n    \"EUR\": 3,\n}\n\n\ndef reserve(sku: str, quantity: int) -> bool:\n    available = STOCK.get(sku, 0)\n    if available <= quantity:\n        return False\n    STOCK[sku] = available - quantity\n    return True\n",
        encoding="utf-8",
    )
    (FIXTURE / "audit_app" / "pipeline.py").write_text(
        "from .inventory import reserve\nfrom .pricing import total_with_tax\n\n\ndef run_order(order):\n    if not reserve(order.sku, order.quantity):\n        return {\"status\": \"rejected\", \"total\": 0}\n    return {\"status\": \"ok\", \"total\": total_with_tax(order)}\n",
        encoding="utf-8",
    )
    (FIXTURE / "tests" / "test_pipeline.py").write_text(
        "import unittest\n\nfrom audit_app.models import Order\nfrom audit_app.pipeline import run_order\nfrom audit_app.pricing import validate_discount\n\n\nclass PipelineTests(unittest.TestCase):\n    def test_total_uses_quantity_price_discount_and_tax(self):\n        result = run_order(Order(\"XAU\", 2, 100.0, discount=0.10))\n        self.assertEqual(result[\"status\"], \"ok\")\n        self.assertEqual(result[\"total\"], 198.0)\n\n    def test_can_reserve_exact_stock(self):\n        result = run_order(Order(\"EUR\", 3, 10.0))\n        self.assertEqual(result[\"status\"], \"ok\")\n\n    def test_discount_above_max_is_rejected(self):\n        with self.assertRaises(ValueError):\n            validate_discount(0.50)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n",
        encoding="utf-8",
    )
    (FIXTURE / "mql5_fixture" / "AuditFixture.mq5").write_text(
        "#property strict\ninput double Lots = 0.10;\nint OnInit(){ return(INIT_SUCCEEDED); }\nvoid OnTick(){}\n",
        encoding="utf-8",
    )


class CodingProjectV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        reset_fixture()
        self.protected_hash = sha256_file(PROTECTED_MQ5)
        self.service = CodingProjectService(ROOT)
        ExecutionService(ROOT).set_mode(PermissionMode.ASK)
        self.task = self.service.create_task("Analise este projeto e prepare todas as correcoes.", FIXTURE)

    def tearDown(self):
        reset_fixture()

    def prepared(self):
        return self.service.prepare_full_fix(self.task.task_id)

    def test_01_project_task_created(self):
        self.assertEqual(self.task.status, "CREATED")

    def test_02_project_map(self):
        m = self.service.map_project(FIXTURE)
        self.assertIn("audit_app/pricing.py", m.files)

    def test_03_runner_detected(self):
        runner, cmd = self.service.runner.detect(FIXTURE)
        self.assertEqual(runner, "unittest")
        self.assertIn("unittest", cmd)

    def test_04_baseline_test_captured(self):
        result = self.service.runner.run(FIXTURE, self.task.task_id, "baseline_test", ROOT / "workspace" / self.task.task_id / "reports")
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.failures, 3)

    def test_05_stdout_stderr_persisted(self):
        result = self.service.runner.run(FIXTURE, self.task.task_id, "baseline_test", ROOT / "workspace" / self.task.task_id / "reports")
        self.assertTrue(Path(result.output_path).exists())

    def test_06_multi_file_scope(self):
        task = self.prepared()
        self.assertGreaterEqual(len(task.affected_files), 3)

    def test_07_dependency_scan(self):
        m = self.service.map_project(FIXTURE)
        self.assertIn("audit_app.pricing", m.imports["audit_app/pipeline.py"])

    def test_08_workspace_multi_file(self):
        task = self.prepared()
        self.assertTrue((Path(task.workspace_path) / "working" / "audit_app" / "pricing.py").exists())

    def test_09_original_intact_before_approval(self):
        before = sha256_file(FIXTURE / "audit_app" / "pricing.py")
        self.prepared()
        self.assertEqual(sha256_file(FIXTURE / "audit_app" / "pricing.py"), before)

    def test_10_diff_per_file(self):
        task = self.prepared()
        self.assertIn("audit_app/pricing.py", task.diff_hashes)

    def test_11_manifest(self):
        task = self.prepared()
        self.assertTrue((Path(task.workspace_path) / "manifest.json").exists())

    def test_12_approval_required(self):
        task = self.prepared()
        self.assertEqual(task.status, "AWAITING_APPROVAL")

    def test_13_approval_hash(self):
        task = self.prepared()
        self.assertTrue(task.approval_manifest_hash)

    def test_14_approval_invalidated_by_new_diff(self):
        task = self.prepared()
        working = Path(task.workspace_path) / "working" / "audit_app" / "pricing.py"
        working.write_text(working.read_text(encoding="utf-8") + "\n# changed after approval manifest\n", encoding="utf-8")
        task = self.service.approve(task.task_id)
        self.assertEqual(task.status, "FAILED")

    def test_15_source_hash_mismatch(self):
        task = self.prepared()
        task = self.service.approve(task.task_id)
        (FIXTURE / "audit_app" / "pricing.py").write_text("# external change\n", encoding="utf-8")
        task = self.service.apply_approved(task.task_id)
        self.assertEqual(task.status, "FAILED")
        self.assertIn("mudou", task.result)

    def test_16_checkpoint_set(self):
        task = self.prepared()
        ExecutionService(ROOT).set_mode(PermissionMode.FULL)
        task = self.service.approve(task.task_id)
        task = self.service.apply_approved(task.task_id)
        self.assertTrue(task.checkpoint_ids)

    def test_17_apply_multi_file(self):
        task = self.prepared()
        ExecutionService(ROOT).set_mode(PermissionMode.FULL)
        task = self.service.approve(task.task_id)
        task = self.service.apply_approved(task.task_id)
        self.assertEqual(task.status, "COMPLETED")

    def test_18_all_or_nothing(self):
        hashes = {p: sha256_file(FIXTURE / p) for p in ["audit_app/pricing.py", "audit_app/inventory.py"]}
        task = self.prepared()
        ExecutionService(ROOT).set_mode(PermissionMode.FULL)
        task = self.service.approve(task.task_id)
        self.service.apply_approved(task.task_id, simulate_post_failure=True)
        self.assertEqual(sha256_file(FIXTURE / "audit_app/pricing.py"), hashes["audit_app/pricing.py"])
        self.assertEqual(sha256_file(FIXTURE / "audit_app/inventory.py"), hashes["audit_app/inventory.py"])

    def test_19_post_validation(self):
        task = self.prepared()
        ExecutionService(ROOT).set_mode(PermissionMode.FULL)
        task = self.service.approve(task.task_id)
        task = self.service.apply_approved(task.task_id)
        self.assertEqual(task.test_status, "PASSED")

    def test_20_rollback_complete(self):
        task = self.prepared()
        ExecutionService(ROOT).set_mode(PermissionMode.FULL)
        task = self.service.approve(task.task_id)
        task = self.service.apply_approved(task.task_id, simulate_post_failure=True)
        self.assertEqual(task.rollback_status, "COMPLETED")

    def test_21_iteration_count(self):
        task = self.prepared()
        self.assertGreaterEqual(task.iteration_count, 2)

    def test_22_max_iterations(self):
        task = self.service.prepare_full_fix(self.task.task_id, max_iterations=3)
        self.assertLessEqual(task.iteration_count, 3)

    def test_23_partial_patch_not_success(self):
        task = self.service.require_task(self.task.task_id)
        m = self.service.map_project(FIXTURE)
        self.service.create_workspace(task, m.related_files)
        task.project_map_json = json.dumps(m.__dict__)
        task.affected_files = self.service._affected_files(m)
        task.source_hashes = {p: sha256_file(FIXTURE / p) for p in m.files}
        self.service._apply_fixture_iteration(task, 1)
        self.service._write_manifest_and_diffs(task)
        result = self.service.runner.run(Path(task.workspace_path) / "working", task.task_id, "partial", Path(task.workspace_path) / "reports")
        self.assertNotEqual(result.status, "PASSED")

    def test_24_reviewer(self):
        task = self.prepared()
        events = self.service.repo.fetchone("SELECT * FROM coding_project_events WHERE task_id=? AND event_type='REVIEWER_COMPLETED'", (task.task_id,))
        self.assertIsNotNone(events)

    def test_25_risk(self):
        task = self.prepared()
        events = self.service.repo.fetchone("SELECT * FROM coding_project_events WHERE task_id=? AND event_type='RISK_COMPLETED'", (task.task_id,))
        self.assertIsNotNone(events)

    def test_26_execution_feed(self):
        task = self.prepared()
        events = ExecutionService(ROOT).latest_events(task.task_id, limit=20)
        self.assertTrue(any(e["action"] == "PROJECT_MAPPED" for e in events))

    def test_27_permission_ask(self):
        task = self.prepared()
        self.assertEqual(task.approval_status, "PENDING")

    def test_28_permission_auto_safe_still_asks_write(self):
        ExecutionService(ROOT).set_mode(PermissionMode.AUTO_SAFE)
        task = self.prepared()
        self.assertEqual(task.status, "AWAITING_APPROVAL")

    def test_29_full_no_bypass_missing_capability(self):
        result = ExecutionService(ROOT).authorize_action("x", "EXECUTE", "download", "", risk_level=RiskLevel.HIGH, capability_exists=False)
        self.assertFalse(result.allowed)

    def test_30_critical_blocked(self):
        result = ExecutionService(ROOT).authorize_action("x", "CRITICAL", "real_trade", "MT5", risk_level=RiskLevel.CRITICAL)
        self.assertFalse(result.allowed)

    def test_31_general_chat_does_not_create_task(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        self.assertFalse(win._is_coding_change_request("Ola vamos conversar"))
        win.close()

    def test_32_review_only_does_not_edit(self):
        before = sha256_file(FIXTURE / "audit_app" / "pricing.py")
        self.service.map_project(FIXTURE)
        self.assertEqual(sha256_file(FIXTURE / "audit_app" / "pricing.py"), before)

    def test_33_outside_root_blocked(self):
        with self.assertRaises(PermissionError):
            self.service.create_task("corrija", ROOT / "app")

    def test_34_protected_mq5_intact(self):
        self.prepared()
        self.assertEqual(sha256_file(PROTECTED_MQ5), self.protected_hash)

    def test_35_recovery_after_restart(self):
        task = self.prepared()
        new_service = CodingProjectService(ROOT)
        recovered = new_service.repo.latest_open_task()
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.task_id, task.task_id)


if __name__ == "__main__":
    unittest.main()
