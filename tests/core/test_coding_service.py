from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coding import CodingService  # noqa: E402
from core.coding.models import ValidationResult, now_iso  # noqa: E402
from core.tools.hashing import sha256_file  # noqa: E402


class AlwaysFailPostValidator:
    def validate(self, path, phase="pre_apply"):
        if phase == "post_apply":
            return ValidationResult(False, phase, "FAILED", "falha pos-aplicacao controlada")
        return ValidationResult(True, phase, "PASSED", "")


class CodingServiceTests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "projetos").mkdir(parents=True)
        (root / "app").mkdir()
        (root / "core").mkdir()
        (root / "studio").mkdir()
        service = CodingService(root)
        self.addCleanup(tmp.cleanup)
        return service, root

    def write_python(self, root: Path, name: str = "calc.py") -> Path:
        path = root / "projetos" / name
        path.write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")
        return path

    def prepare_python_task(self):
        service, root = self.make_service()
        source = self.write_python(root)
        original_hash = sha256_file(source)
        task = service.create_task("Altere a funcao soma para aceitar tres numeros.", source)
        task = service.analyze_and_plan(task.task_id)
        task = service.apply_controlled_python_change(task.task_id)
        return service, root, source, original_hash, task

    def test_create_coding_task_and_workspace_isolated(self):
        service, _, source, original_hash, task = self.prepare_python_task()
        self.assertEqual(sha256_file(source), original_hash)
        self.assertEqual(task.status, "AWAITING_APPROVAL")
        self.assertTrue((Path(task.workspace_path) / "original" / source.name).exists())
        self.assertTrue((Path(task.workspace_path) / "working" / source.name).exists())

    def test_working_copy_can_change_original_intact(self):
        _, _, source, original_hash, task = self.prepare_python_task()
        working = Path(task.workspace_path) / "working" / source.name
        self.assertIn("def soma(a, b, c):", working.read_text(encoding="utf-8"))
        self.assertEqual(sha256_file(source), original_hash)

    def test_diff_is_real_unified_diff(self):
        _, _, _, _, task = self.prepare_python_task()
        self.assertIn("---", task.diff)
        self.assertIn("+++", task.diff)
        self.assertIn("-def soma(a, b):", task.diff)
        self.assertIn("+def soma(a, b, c):", task.diff)

    def test_missing_approval_blocks_write(self):
        service, _, source, original_hash, task = self.prepare_python_task()
        task.status = "APPROVED"
        task.updated_at = now_iso()
        service.repo.save_task(task)
        applied = service.apply_approved(task.task_id)
        self.assertEqual(applied.status, "FAILED")
        self.assertEqual(sha256_file(source), original_hash)

    def test_approval_from_other_task_does_not_apply(self):
        service, root, source, original_hash, task = self.prepare_python_task()
        other_source = self.write_python(root, "other.py")
        other = service.create_task("Altere a funcao soma para aceitar tres numeros.", other_source)
        service.repo.add_approval(other.task_id, task.source_path, task.source_hash, task.diff_hash, "x", "GRANTED")
        task.status = "APPROVED"
        service.repo.save_task(task)
        applied = service.apply_approved(task.task_id)
        self.assertEqual(applied.status, "FAILED")
        self.assertEqual(sha256_file(source), original_hash)

    def test_diff_change_invalidates_approval(self):
        service, _, source, original_hash, task = self.prepare_python_task()
        task = service.approve(task.task_id)
        working = Path(task.workspace_path) / "working" / source.name
        working.write_text("def soma(a, b, c):\n    return a + b + c + 1\n", encoding="utf-8")
        applied = service.apply_approved(task.task_id)
        self.assertEqual(applied.status, "FAILED")
        self.assertEqual(sha256_file(source), original_hash)

    def test_source_hash_change_blocks_apply(self):
        service, _, source, _, task = self.prepare_python_task()
        task = service.approve(task.task_id)
        source.write_text("def soma(a, b):\n    return a - b\n", encoding="utf-8")
        applied = service.apply_approved(task.task_id)
        self.assertEqual(applied.status, "FAILED")
        self.assertIn("hash", applied.result.lower())

    def test_approved_apply_creates_checkpoint_and_validates(self):
        service, _, source, _, task = self.prepare_python_task()
        task = service.approve(task.task_id)
        applied = service.apply_approved(task.task_id)
        self.assertEqual(applied.status, "COMPLETED")
        self.assertTrue(applied.checkpoint_id)
        self.assertIn("def soma(a, b, c):", source.read_text(encoding="utf-8"))

    def test_post_apply_failure_rolls_back(self):
        service, _, source, original_hash, task = self.prepare_python_task()
        service.validator = AlwaysFailPostValidator()
        task = service.approve(task.task_id)
        applied = service.apply_approved(task.task_id)
        self.assertEqual(applied.status, "ROLLED_BACK")
        self.assertEqual(applied.rollback_status, "COMPLETED")
        self.assertEqual(sha256_file(source), original_hash)

    def test_cancel_blocks_write(self):
        service, _, source, original_hash, task = self.prepare_python_task()
        cancelled = service.cancel(task.task_id)
        self.assertEqual(cancelled.status, "CANCELLED")
        with self.assertRaises(ValueError):
            service.approve(task.task_id)
        self.assertEqual(sha256_file(source), original_hash)

    def test_recover_after_restart_keeps_awaiting_approval(self):
        service, root, _, _, task = self.prepare_python_task()
        recovered_service = CodingService(root)
        recovered = recovered_service.recover_open_tasks()
        self.assertTrue(any(item.task_id == task.task_id and item.status == "AWAITING_APPROVAL" for item in recovered))

    def test_recover_applying_enters_safe_failed_state(self):
        service, root, _, _, task = self.prepare_python_task()
        task.status = "APPLYING"
        service.repo.save_task(task)
        recovered_service = CodingService(root)
        recovered = recovered_service.recover_open_tasks()
        self.assertTrue(any(item.task_id == task.task_id and item.status == "FAILED" for item in recovered))

    def test_file_outside_projects_is_blocked(self):
        service, root = self.make_service()
        outside = root / "outside.py"
        outside.write_text("x=1\n", encoding="utf-8")
        with self.assertRaises(PermissionError):
            service.create_task("Altere este arquivo", outside)

    def test_internal_golden_file_is_blocked(self):
        service, root = self.make_service()
        internal = root / "core" / "x.py"
        internal.write_text("x=1\n", encoding="utf-8")
        with self.assertRaises(PermissionError):
            service.create_task("Altere este arquivo", internal)

    def test_mq5_real_terminal_path_is_blocked(self):
        service, root = self.make_service()
        fake_mt5 = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "_golden_ai_test_block.mq5"
        self.assertFalse(service.workspace.is_authorized_source(fake_mt5))

    def test_analysis_read_only_does_not_create_write(self):
        service, root = self.make_service()
        source = self.write_python(root)
        task = service.create_task("Analise este codigo e explique a funcao.", source)
        task = service.analyze_and_plan(task.task_id)
        self.assertEqual(task.status, "PLANNED")
        self.assertEqual(task.diff, "")

    def test_audit_events_are_generated(self):
        service, root, _, _, task = self.prepare_python_task()
        log_files = list((root / "logs").glob("audit_*.jsonl"))
        text = "\n".join(path.read_text(encoding="utf-8") for path in log_files)
        self.assertIn("CODING_TASK_CREATED", text)
        self.assertIn("DIFF_CREATED", text)
        self.assertIn("APPROVAL_REQUESTED", text)

    def test_mql5_working_copy_validation_controlled(self):
        service, root = self.make_service()
        source = root / "projetos" / "teste.mq5"
        source.write_text("void OnTick() {}\n", encoding="utf-8")
        original_hash = sha256_file(source)
        task = service.create_task("Implemente comentario seguro.", source)
        task = service.analyze_and_plan(task.task_id)
        service.replace_working_text(task.task_id, "// comentario seguro\nvoid OnTick() {}\n")
        task = service.require_task(task.task_id)
        self.assertEqual(task.status, "AWAITING_APPROVAL")
        self.assertEqual(sha256_file(source), original_hash)


if __name__ == "__main__":
    unittest.main()
