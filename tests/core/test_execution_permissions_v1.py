from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.coding import CodingService
from core.config import GoldenAISettings
from core.execution import ExecutionService, PermissionMode, RiskLevel
from core.permissions import PermissionManager

from studio.golden_ai_studio import GoldenAIStudio


ROOT = Path(r"C:\GoldenAI")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest().upper()


class ExecutionPermissionsV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "GoldenAI"
        self.projects = self.root / "projetos"
        self.projects.mkdir(parents=True)
        (self.root / "logs").mkdir()
        (self.root / "data").mkdir()
        self.file = self.projects / "sample.py"
        self.file.write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")
        self.service = ExecutionService(self.root)
        self.service.set_mode(PermissionMode.READ_ONLY)
        self.settings = GoldenAISettings(
            root=self.root,
            projects_dir=self.projects,
            backups_dir=self.root / "backups",
            logs_dir=self.root / "logs",
            sandbox_dir=self.root / "sandbox",
            data_dir=self.root / "data",
            allowed_paths=(self.projects, self.root / "sandbox", self.root / "data", self.root / "logs"),
            protected_paths=(self.root / "app", self.root / "core", self.root / "studio", self.root / "backups"),
            read_only=True,
            write_enabled=False,
            command_execution_enabled=True,
        )
        self.manager = PermissionManager(self.settings)

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_read_only_allows_authorized_read(self):
        decision = self.manager.can_read(self.file)
        self.assertTrue(decision.allowed)

    def test_02_read_only_blocks_write(self):
        decision = self.manager.can_write(self.file)
        self.assertFalse(decision.allowed)

    def test_03_ask_creates_approval_request(self):
        self.service.set_mode(PermissionMode.ASK)
        result = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "WAITING_APPROVAL")
        self.assertTrue(result.request_id)

    def test_04_ask_does_not_execute_before_approval(self):
        self.service.set_mode(PermissionMode.ASK)
        result = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertFalse(result.allowed)

    def test_05_grant_once_releases_only_that_action(self):
        self.service.set_mode(PermissionMode.ASK)
        first = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.service.grant_once(first.request_id)
        second = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertTrue(second.allowed)

    def test_06_equivalent_second_action_asks_again_after_once_consumed(self):
        self.service.set_mode(PermissionMode.ASK)
        first = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.service.grant_once(first.request_id)
        self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        third = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertFalse(third.allowed)
        self.assertEqual(third.status, "WAITING_APPROVAL")

    def test_07_grant_for_task_works_inside_task(self):
        self.service.set_mode(PermissionMode.ASK)
        request = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.service.grant_for_task(request.request_id)
        result = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertTrue(result.allowed)

    def test_08_other_task_does_not_inherit_task_authorization(self):
        self.service.set_mode(PermissionMode.ASK)
        request = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.service.grant_for_task(request.request_id)
        result = self.service.authorize_action("t2", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertFalse(result.allowed)

    def test_09_deny_blocks_action(self):
        self.service.set_mode(PermissionMode.ASK)
        request = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.service.deny(request.request_id)
        result = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.assertFalse(result.allowed)

    def test_10_auto_safe_executes_low_automatically(self):
        self.service.set_mode(PermissionMode.AUTO_SAFE)
        result = self.service.authorize_action("t1", "TOOL", "search", str(self.file), risk_level=RiskLevel.LOW)
        self.assertTrue(result.allowed)

    def test_11_auto_safe_asks_for_high(self):
        self.service.set_mode(PermissionMode.AUTO_SAFE)
        result = self.service.authorize_action("t1", "WRITE", "external_write", r"C:\outside.txt", risk_level=RiskLevel.HIGH)
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "WAITING_APPROVAL")

    def test_12_full_does_not_release_missing_capability(self):
        self.service.set_mode(PermissionMode.FULL)
        result = self.service.authorize_action("t1", "EXECUTE", "internet_download", "", risk_level=RiskLevel.HIGH, capability_exists=False)
        self.assertFalse(result.allowed)
        self.assertIn("Capability", result.reason)

    def test_13_critical_remains_blocked(self):
        self.service.set_mode(PermissionMode.FULL)
        result = self.service.authorize_action("t1", "CRITICAL", "real_trade", "MT5", risk_level=RiskLevel.CRITICAL)
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "BLOCKED")

    def test_14_mode_change_is_audited(self):
        self.service.set_mode(PermissionMode.ASK)
        log = next((self.root / "logs").glob("audit_*.jsonl"))
        self.assertIn("PERMISSION_MODE_CHANGED", log.read_text(encoding="utf-8"))

    def test_15_approval_is_audited(self):
        self.service.set_mode(PermissionMode.ASK)
        request = self.service.authorize_action("t1", "WRITE", "edit", str(self.file), risk_level=RiskLevel.MEDIUM)
        self.service.grant_once(request.request_id)
        log = next((self.root / "logs").glob("audit_*.jsonl"))
        self.assertIn("APPROVAL_GRANTED_ONCE", log.read_text(encoding="utf-8"))

    def test_16_feed_receives_real_tool_event(self):
        self.service.record_event(category="TOOL", action="rg", status="COMPLETED", summary="Busca executada", tool_name="rg")
        events = self.service.latest_events(limit=1)
        self.assertEqual(events[0]["action"], "rg")

    def test_17_feed_receives_real_test_result(self):
        self.service.record_event(category="TEST", action="unittest", status="COMPLETED", summary="168 testes passaram")
        self.assertIn("168 testes passaram", self.service.latest_events(limit=1)[0]["summary"])

    def test_18_feed_does_not_show_chain_of_thought_details(self):
        self.service.record_event(category="TASK", action="x", status="COMPLETED", summary="Resumo publico", details="chain-of-thought privado")
        win = GoldenAIStudio()
        win.execution_service = self.service
        html = win._execution_feed_html(collapsed=False)
        win.close()
        self.assertNotIn("chain-of-thought", html)

    def test_19_feed_can_be_collapsed(self):
        win = GoldenAIStudio()
        win.execution_service = self.service
        win.execution_feed_collapsed = False
        win._toggle_execution_feed()
        self.assertTrue(win.execution_feed_collapsed)
        win.close()

    def test_20_restart_studio_restores_permission_mode(self):
        root_service = ExecutionService(ROOT)
        old = root_service.get_mode()
        root_service.set_mode(PermissionMode.AUTO_SAFE)
        win = GoldenAIStudio()
        self.assertEqual(win.execution_service.get_mode(), PermissionMode.AUTO_SAFE)
        win.close()
        root_service.set_mode(old)

    def test_21_coding_v1_still_creates_controlled_task(self):
        service = CodingService(self.root)
        task = service.create_task("altere soma para receber 3 parametros", self.file)
        task = service.analyze_and_plan(task.task_id)
        self.assertEqual(task.status, "PLANNED")

    def test_22_quant_module_still_reachable(self):
        win = GoldenAIStudio()
        win._open_module("Quant")
        self.assertFalse(win.quant_page.isHidden())
        win.close()

    def test_23_market_module_still_reachable(self):
        win = GoldenAIStudio()
        win._open_module("Market")
        self.assertFalse(win.market_page.isHidden())
        win.close()

    def test_24_memory_module_still_reachable(self):
        win = GoldenAIStudio()
        win._open_module("Memoria")
        self.assertFalse(win.memory_page.isHidden())
        win.close()

    def test_25_media_module_still_reachable(self):
        win = GoldenAIStudio()
        win._open_module("Media Study")
        self.assertFalse(win.media_page.isHidden())
        win.close()

    def test_26_agent_orchestrator_import_still_works(self):
        from agents import AgentOrchestrator

        self.assertIsNotNone(AgentOrchestrator)

    def test_27_normal_conversation_rendering_still_works(self):
        win = GoldenAIStudio()
        win._render_user_message("Ola")
        win._render_assistant_message("Oi")
        self.assertIn("Golden AI", win.chat_output.toHtml())
        win.close()

    def test_28_file_context_still_works(self):
        win = GoldenAIStudio()
        win._set_context_path(ROOT / "projetos" / "Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5", "teste")
        ctx = win._context_instruction("O que esse arquivo faz?")
        self.assertIn("Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5", ctx)
        win.close()

    def test_29_recent_history_still_works(self):
        win = GoldenAIStudio()
        win.current_conversation = [{"role": "user", "text": "Nova conversa teste"}]
        win._persist_current_conversation()
        win._refresh_recent_list()
        self.assertGreaterEqual(win.recent_list.count(), 1)
        win.close()

    def test_30_conpty_bridge_preserved(self):
        bridge = ROOT / "studio" / "golden_ai_pty_bridge.py"
        self.assertEqual(sha256(bridge), "30D5864513FA8BA2FB6C4ECCF2C856196BF8FBF9C6F8E22CA737B51861421A43")


if __name__ == "__main__":
    unittest.main()
