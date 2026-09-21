from __future__ import annotations

import shutil
import uuid
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.execution import ExecutionService, PermissionMode
from core.permissions import PermissionManager
from core.permissions.external_access import ExternalAccessService


ROOT = Path(r"C:\GoldenAI")
EXTERNAL = ROOT / "_external_access_fixture"


def reset_external_fixture() -> None:
    if EXTERNAL.exists():
        shutil.rmtree(EXTERNAL)
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    (EXTERNAL / "Teoria Dos Ciclos.mq5").write_text("#property strict\nvoid OnTick(){}\n", encoding="utf-8")
    (EXTERNAL / "Outro.mq5").write_text("#property strict\nvoid OnInit(){}\n", encoding="utf-8")


class ExternalAccessApprovalV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        reset_external_fixture()
        self.execution = ExecutionService(ROOT)
        self.execution.set_mode(PermissionMode.ASK)
        self.service = ExternalAccessService(ROOT)
        self.task_id = "external-access-test-" + str(uuid.uuid4())
        self.path = EXTERNAL / "Teoria Dos Ciclos.mq5"

    def tearDown(self):
        reset_external_fixture()

    def test_01_external_file_blocked_initially(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.request_id)

    def test_02_approval_request_appears(self):
        decision = self.service.check_read(self.task_id, self.path)
        requests = self.execution.latest_requests(limit=5)
        self.assertTrue(any(row["request_id"] == decision.request_id for row in requests))

    def test_03_content_not_read_before_approval(self):
        self.service.check_read(self.task_id, self.path)
        with self.assertRaises(PermissionError):
            self.service.read_text_after_approval(self.task_id, self.path)

    def test_04_allow_once_reads_file(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.grant_once(decision.request_id)
        before_read = self.service.check_read(self.task_id, self.path)
        self.assertTrue(before_read.allowed)
        text = self.service.read_text_after_approval(self.task_id, self.path)
        self.assertIn("OnTick", text)

    def test_05_original_request_can_continue_in_studio(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._set_context_path(self.path, "teste externo")
        win._ensure_engine_process = lambda: True
        win.chat_input.setText("Analise esse robô.")
        win._send_chat()
        self.assertTrue(win.pending_external_prompts)
        self.assertEqual(win.external_access_chat_status, "AWAITING_APPROVAL")
        req_id = next(iter(win.pending_external_prompts))
        self.execution.grant_once(req_id)
        win._continue_pending_external_prompt(req_id)
        self.assertFalse(win.pending_external_prompts)
        self.assertTrue(win.engine_prompt_queue)
        self.assertIn("[SELECTED_FILE_CONTENT]", win.engine_prompt_queue[-1])
        win.close()

    def test_06_grant_expires(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.grant_once(decision.request_id)
        self.service.read_text_after_approval(self.task_id, self.path)
        again = self.service.check_read(self.task_id, self.path)
        self.assertFalse(again.allowed)

    def test_07_second_file_still_blocked(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.grant_once(decision.request_id)
        self.service.read_text_after_approval(self.task_id, self.path)
        other = self.service.check_read(self.task_id, EXTERNAL / "Outro.mq5")
        self.assertFalse(other.allowed)

    def test_08_allow_for_task(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.grant_for_task(decision.request_id)
        self.assertIn("OnTick", self.service.read_text_after_approval(self.task_id, self.path))
        self.assertTrue(self.service.check_read(self.task_id, self.path).allowed)

    def test_09_deny(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.deny(decision.request_id)
        with self.assertRaises(PermissionError):
            self.service.read_text_after_approval(self.task_id, self.path)

    def test_10_read_only_allows_read_request(self):
        self.execution.set_mode(PermissionMode.READ_ONLY)
        decision = self.service.check_read(self.task_id, self.path)
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.request_id)

    def test_11_read_only_write_blocked(self):
        self.execution.set_mode(PermissionMode.READ_ONLY)
        decision = PermissionManager().can_write(self.path, explicit_authorization=False)
        self.assertFalse(decision.allowed)

    def test_12_ask_mode_requests(self):
        self.execution.set_mode(PermissionMode.ASK)
        self.assertFalse(self.service.check_read(self.task_id, self.path).allowed)

    def test_13_auto_safe_still_requests_external(self):
        self.execution.set_mode(PermissionMode.AUTO_SAFE)
        self.assertFalse(self.service.check_read(self.task_id, self.path).allowed)

    def test_14_full_still_not_unrestricted(self):
        self.execution.set_mode(PermissionMode.FULL)
        self.assertFalse(self.service.check_read(self.task_id, self.path).allowed)

    def test_15_read_does_not_become_write(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.grant_for_task(decision.request_id)
        write = PermissionManager().can_write(self.path, explicit_authorization=False)
        self.assertFalse(write.allowed)

    def test_16_path_traversal_blocked_by_exact_path(self):
        decision = self.service.check_read(self.task_id, self.path)
        self.execution.grant_for_task(decision.request_id)
        traversal = EXTERNAL / ".." / "_external_access_fixture" / "Outro.mq5"
        self.assertFalse(self.service.check_read(self.task_id, traversal).allowed)

    def test_17_symlink_junction_safe_when_available(self):
        link = EXTERNAL / "link.mq5"
        try:
            link.symlink_to(self.path)
        except OSError:
            self.skipTest("symlink indisponivel neste ambiente")
        decision = self.service.check_read(self.task_id, link)
        self.assertFalse(decision.allowed)

    def test_18_real_phrase_creates_approval_in_studio(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._set_context_path(self.path, "teste externo")
        win.chat_input.setText("me fala qual estrutura e oque esse robo faz")
        win._send_chat()
        self.assertTrue(win.pending_external_prompts)
        self.assertEqual(win.external_access_chat_status, "AWAITING_APPROVAL")
        self.assertFalse(win.engine_prompt_queue)
        win.close()

    def test_18b_real_large_external_file_is_injected_after_grant(self):
        real_path = Path(r"C:\Users\Anderson\Desktop\Meus\MEU ROBO\Bot Ciclos EA.mq5")
        if not real_path.exists():
            self.skipTest("arquivo real informado nao existe neste ambiente")
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._ensure_engine_process = lambda: True
        win._set_context_path(real_path, "real externo")
        win.chat_input.setText("me fala qual estrutura e o que esse robô faz")
        win._send_chat()
        self.assertTrue(win.pending_external_prompts)
        req_id = next(iter(win.pending_external_prompts))
        self.execution.grant_once(req_id)
        win._continue_pending_external_prompt(req_id)
        self.assertTrue(win.engine_prompt_queue)
        prompt = win.engine_prompt_queue[-1]
        self.assertIn("[SELECTED_FILE_CONTENT]", prompt)
        self.assertIn("ENUM_CYCLE_MODE", prompt)
        self.assertIn("ModoDoCiclo", prompt)
        self.assertIn("LoteFixo", prompt)
        self.assertEqual(win.external_access_chat_status, "RUNNING")
        win._append_assistant_message("O robo usa ENUM_CYCLE_MODE, ModoDoCiclo e LoteFixo.")
        self.assertEqual(win.external_access_chat_status, "COMPLETED")
        win.close()

    def test_19_new_question_after_grant_once_requests_again(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._ensure_engine_process = lambda: True
        win._set_context_path(self.path, "teste externo")
        win.chat_input.setText("me fala qual estrutura e oque esse robo faz")
        win._send_chat()
        req_id = next(iter(win.pending_external_prompts))
        self.execution.grant_once(req_id)
        win._continue_pending_external_prompt(req_id)
        win.engine_prompt_queue.clear()
        win.chat_input.setText("e quais entradas ele usa?")
        win._send_chat()
        self.assertTrue(win.pending_external_prompts)
        self.assertEqual(win.external_access_chat_status, "AWAITING_APPROVAL")
        win.close()

    def test_20_permission_help_uses_real_approval(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._set_context_path(self.path, "teste externo")
        win.chat_input.setText("como faço para dar permissao para voce")
        win._send_chat()
        self.assertTrue(win.pending_external_prompts)
        last = win.current_conversation[-1]["text"]
        self.assertIn("Aprovacoes", last)
        self.assertNotIn("Permitted Paths", last)
        win.close()

    def test_20b_pode_acessar_agr_uses_real_state(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._set_context_path(self.path, "teste externo")
        win.chat_input.setText("pode acessar agr")
        win._send_chat()
        self.assertTrue(win.pending_external_prompts)
        self.assertIn("precisa de autorizacao", win.current_conversation[-1]["text"])
        req_id = next(iter(win.pending_external_prompts))
        self.execution.grant_for_task(req_id)
        win._ensure_engine_process = lambda: True
        win.chat_input.setText("pode acessar agr")
        win._send_chat()
        self.assertTrue(win.engine_prompt_queue)
        self.assertIn("[SELECTED_FILE_CONTENT]", win.engine_prompt_queue[-1])
        all_text = "\n".join(msg.get("text", "") for msg in win.current_conversation)
        self.assertIn("autorizado", all_text)
        self.assertNotIn("nao tenho", all_text.lower())
        win.close()

    def test_21_deny_does_not_read(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._set_context_path(self.path, "teste externo")
        win.chat_input.setText("me fala qual estrutura e oque esse robo faz")
        win._send_chat()
        req_id = next(iter(win.pending_external_prompts))
        self.execution.deny(req_id)
        win.pending_external_prompts.pop(req_id, None)
        win._append_assistant_message("Acesso externo negado. Nao li o arquivo selecionado.")
        self.assertFalse(win.engine_prompt_queue)
        self.assertIn("negado", win.current_conversation[-1]["text"])
        win.close()

    def test_22_read_grant_does_not_authorize_coding_write(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        win._ensure_engine_process = lambda: True
        win._set_context_path(self.path, "teste externo")
        win.chat_input.setText("me fala qual estrutura e oque esse robo faz")
        win._send_chat()
        req_id = next(iter(win.pending_external_prompts))
        self.execution.grant_for_task(req_id)
        win._continue_pending_external_prompt(req_id)
        win.chat_input.setText("corrija esse robo")
        win._send_chat()
        write = PermissionManager().can_write(self.path, explicit_authorization=False)
        self.assertFalse(write.allowed)
        win.close()


if __name__ == "__main__":
    unittest.main()
