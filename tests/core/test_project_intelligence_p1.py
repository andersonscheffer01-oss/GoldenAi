from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.coding import CodingProjectService
from core.execution import ExecutionService, PermissionMode
from core.project_intelligence import ProjectIntelligenceService
from core.tools.hashing import sha256_file
from tests.core.test_coding_project_v2 import FIXTURE, PROTECTED_MQ5, ROOT, reset_fixture


class ProjectIntelligenceP1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        reset_fixture()
        ExecutionService(ROOT).set_mode(PermissionMode.ASK)
        self.service = ProjectIntelligenceService(ROOT)

    def tearDown(self):
        reset_fixture()

    def test_01_project_list(self):
        files = self.service.project_list(FIXTURE)
        self.assertTrue(any(item.path == "audit_app/pricing.py" for item in files))

    def test_02_project_list_filter(self):
        files = self.service.project_list(FIXTURE, "*.py")
        self.assertTrue(files)
        self.assertTrue(all(item.extension == ".py" for item in files))

    def test_03_root_protection(self):
        with self.assertRaises(PermissionError):
            self.service.project_list(Path(r"C:\Windows"))

    def test_04_project_search(self):
        result = self.service.project_search(FIXTURE, "validate_discount")
        self.assertGreaterEqual(result["total"], 2)

    def test_05_fallback_search(self):
        result = self.service.project_search(FIXTURE, "validate_discount", use_rg=False)
        self.assertEqual(result["backend"], "python")
        self.assertGreaterEqual(result["total"], 2)

    def test_06_symbol_python_function(self):
        symbols = self.service.project_find_symbol(FIXTURE, "subtotal")
        self.assertTrue(any(s.symbol_type == "function" for s in symbols))

    def test_07_symbol_python_class(self):
        symbols = self.service.project_find_symbol(FIXTURE, "Order")
        self.assertTrue(any(s.symbol_type == "class" for s in symbols))

    def test_08_symbol_import_assignment(self):
        imports = self.service.project_find_symbol(FIXTURE, "DEFAULT_TAX_RATE")
        self.assertTrue(any(s.symbol_type in {"import", "assignment", "text"} for s in imports))

    def test_09_read_range(self):
        read = self.service.project_read_range(FIXTURE, "audit_app/pricing.py", 1, 3)
        self.assertLessEqual(read.end_line, 3)
        self.assertIn("DEFAULT_TAX_RATE", read.text)

    def test_10_read_file_metadata(self):
        info = self.service.project_file_metadata(FIXTURE, "audit_app/pricing.py")
        self.assertGreater(info.line_count, 5)
        self.assertTrue(info.sha256)

    def test_11_find_references(self):
        refs = self.service.project_find_references(FIXTURE, "run_order")
        self.assertGreaterEqual(refs["total"], 2)

    def test_12_dependency_graph(self):
        graph = self.service.project_dependency_graph(FIXTURE)
        self.assertTrue(any(edge.source == "audit_app/pipeline.py" and edge.target == "audit_app/pricing.py" for edge in graph.edges))

    def test_13_relative_import(self):
        graph = self.service.project_dependency_graph(FIXTURE)
        edge = next(e for e in graph.edges if e.source == "audit_app/pipeline.py" and e.target == "audit_app/inventory.py")
        self.assertTrue(edge.resolved)

    def test_14_reverse_dependencies(self):
        reverse = self.service.project_reverse_dependencies(FIXTURE, "audit_app/pricing.py")
        self.assertTrue(any(edge.source == "audit_app/pipeline.py" for edge in reverse))

    def test_15_dependencies_of(self):
        deps = self.service.project_dependencies_of(FIXTURE, "audit_app/pipeline.py")
        self.assertTrue(any(edge.target == "audit_app/pricing.py" for edge in deps))

    def test_16_related_files(self):
        related = self.service.project_related_files(FIXTURE, seed_path="audit_app/pipeline.py", symbol="validate_discount")
        paths = [row["path"] for row in related]
        self.assertIn("audit_app/pricing.py", paths)

    def test_17_test_relationship(self):
        related = self.service.project_related_files(FIXTURE, seed_path="audit_app/pipeline.py")
        self.assertTrue(any(row["path"].startswith("tests/") for row in related))

    def test_18_coding_v2_uses_project_intelligence(self):
        coding = CodingProjectService(ROOT)
        mapped = coding.map_project(FIXTURE)
        self.assertIn("audit_app/pricing.py", mapped.imports["audit_app/pipeline.py"])

    def test_19_feed_receives_search(self):
        self.service.project_search(FIXTURE, "subtotal", use_rg=False)
        events = ExecutionService(ROOT).latest_events("project-intelligence", limit=20)
        self.assertTrue(any(e["action"] == "PROJECT_SEARCH" for e in events))

    def test_20_feed_receives_read(self):
        self.service.project_read_range(FIXTURE, "audit_app/pricing.py", 1, 2)
        events = ExecutionService(ROOT).latest_events("project-intelligence", limit=20)
        self.assertTrue(any(e["action"] == "PROJECT_READ_RANGE" for e in events))

    def test_21_general_chat_does_not_trigger_project_tools(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        self.assertFalse(win._is_project_tool_request("Quanto e 25 x 4?"))
        self.assertFalse(win._is_project_tool_request("O que e uma funcao Python?"))
        win.close()

    def test_22_project_tool_request_detection(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        self.assertTrue(win._is_project_tool_request("Procure onde validate_discount e usado."))
        win.close()

    def test_23_result_continuity(self):
        self.service.project_search(FIXTURE, "validate_discount", use_rg=False)
        self.assertIn("project_search", self.service.last_results)

    def test_24_diff_viewer_support_data(self):
        coding = CodingProjectService(ROOT)
        task = coding.create_task("Analise este projeto e prepare todas as correcoes.", FIXTURE)
        task = coding.prepare_full_fix(task.task_id)
        self.assertTrue(task.diff_hashes)
        self.assertTrue(task.manifest_json)

    def test_25_approval_manifest_real(self):
        coding = CodingProjectService(ROOT)
        task = coding.create_task("Analise este projeto e prepare todas as correcoes.", FIXTURE)
        task = coding.prepare_full_fix(task.task_id)
        self.assertTrue(task.approval_manifest_hash)

    def test_26_read_only_ui_state(self):
        from studio.golden_ai_studio import GoldenAIStudio

        ExecutionService(ROOT).set_mode(PermissionMode.READ_ONLY)
        win = GoldenAIStudio()
        self.assertFalse(win._can_apply_coding_task())
        win.close()

    def test_27_ask_ui_state(self):
        from studio.golden_ai_studio import GoldenAIStudio

        ExecutionService(ROOT).set_mode(PermissionMode.ASK)
        win = GoldenAIStudio()
        self.assertTrue(win._approval_required_for_coding_task())
        win.close()

    def test_28_coding_v1_preserved(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        self.assertTrue(win._is_coding_change_request("corrija este arquivo"))
        win.close()

    def test_29_coding_v2_preserved(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        self.assertTrue(win._is_project_coding_request("corrija o projeto e rode testes"))
        win.close()

    def test_30_conpty_and_mq5_preserved(self):
        self.service.project_search(FIXTURE, "subtotal", use_rg=False)
        self.assertEqual(sha256_file(PROTECTED_MQ5).upper(), "9216C5053F9D19F4C99D28C73EC91E4D722C5B86E4E637A23C3D5C33786D06B7")
        self.assertTrue((ROOT / "studio" / "golden_ai_pty_bridge.py").exists())


if __name__ == "__main__":
    unittest.main()
