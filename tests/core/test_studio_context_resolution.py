from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "studio") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio"))

from PySide6.QtWidgets import QApplication  # noqa: E402
from golden_ai_studio import GoldenAIStudio  # noqa: E402
from core.tools.hashing import sha256_file  # noqa: E402


class StudioContextResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.win = GoldenAIStudio()
        self.path = ROOT / "projetos" / "Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5"
        self.win._set_context_path(self.path, "teste")
        self.app.processEvents()

    def tearDown(self):
        try:
            self.win.activity_service.end_session(self.win.activity_session_id)
            self.win._stop_engine()
        except Exception:
            pass
        self.win.close()
        self.app.processEvents()

    def test_natural_robot_reference_uses_selected_file(self):
        ctx = self.win._context_instruction("O que esse robo faz?")
        self.assertIn(str(self.path), ctx)
        self.assertIn("CURRENT_CONTEXT_NAME=Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5", ctx)
        self.assertNotIn("CURRENT_CONTEXT_PATH=esse", ctx)

    def test_analyze_selected_robot_uses_selected_file(self):
        ctx = self.win._context_instruction("Analise esse robo.")
        self.assertIn(str(self.path), ctx)

    def test_pronoun_continuity_after_robot_context(self):
        self.win._context_instruction("Analise esse robo.")
        ctx = self.win._context_instruction("Qual stop ele usa?")
        self.assertIn(str(self.path), ctx)

    def test_selected_code_problem_read_only_context(self):
        ctx = self.win._context_instruction("Esse codigo tem algum problema?")
        self.assertIn(str(self.path), ctx)
        self.assertIn("READ_ONLY=true", ctx)

    def test_no_change_read_only_does_not_create_coding_task(self):
        self.assertFalse(self.win._is_coding_change_request("Nao altere nada. Apenas analise esse codigo."))
        ctx = self.win._context_instruction("Nao altere nada. Apenas analise esse codigo.")
        self.assertIn(str(self.path), ctx)

    def test_change_request_goes_to_coding_v1_intent(self):
        self.assertTrue(self.win._is_coding_change_request("Corrija esse codigo."))

    def test_file_metadata_intent_uses_selected_file_without_analysis(self):
        ctx = self.win._context_instruction("Quantas linhas tem o codigo desse robo?")
        self.assertIn(str(self.path), ctx)
        self.assertIn("USER_INTENT=FILE_METADATA", ctx)
        self.assertIn("RESPONSE_LANGUAGE=pt", ctx)

    def test_file_metadata_continuity_uses_selected_file(self):
        self.win._context_instruction("O que esse robo faz?")
        ctx = self.win._context_instruction("quantas linhas ele tem?")
        self.assertIn(str(self.path), ctx)
        self.assertIn("USER_INTENT=FILE_METADATA", ctx)

    def test_english_prompt_sets_english_response_language(self):
        ctx = self.win._context_instruction("What does this code do?")
        self.assertIn(str(self.path), ctx)
        self.assertIn("USER_INTENT=FILE_EXPLANATION", ctx)
        self.assertIn("RESPONSE_LANGUAGE=en", ctx)

    def test_explicit_english_request_overrides_portuguese_prompt(self):
        ctx = self.win._context_instruction("Responda em ingles: o que esse codigo faz?")
        self.assertIn(str(self.path), ctx)
        self.assertIn("RESPONSE_LANGUAGE=en", ctx)

    def test_missing_selected_file_asks_for_selection(self):
        self.win._set_context_path(None)
        self.assertTrue(self.win._needs_selected_file_but_missing("O que esse robo faz?"))
        self.win.chat_input.setText("O que esse robo faz?")
        self.win._send_chat()
        self.app.processEvents()
        answers = [m["text"] for m in self.win.current_conversation if m.get("role") == "assistant"]
        self.assertTrue(any("selecione" in answer.lower() for answer in answers))

    def test_missing_selected_file_for_metadata_asks_for_selection(self):
        self.win._set_context_path(None)
        self.assertTrue(self.win._needs_selected_file_but_missing("Quantas linhas tem esse codigo?"))

    def test_general_math_does_not_attach_context(self):
        self.assertEqual(self.win._context_instruction("Quanto e 25 x 4?"), "")

    def test_market_dataset_reference_uses_selected_csv(self):
        dataset = ROOT / "projetos" / "_studio_market_dataset.csv"
        dataset.write_text(
            "timestamp,open,high,low,close\n"
            "2026-01-01T00:00:00+00:00,1,2,1,2\n"
            "2026-01-02T00:00:00+00:00,2,3,2,3\n",
            encoding="utf-8",
        )
        self.win._set_context_path(dataset, "teste")
        ctx = self.win._context_instruction("Analise este dataset de mercado.")
        self.assertIn(str(dataset), ctx)
        self.assertIn("USER_INTENT=MARKET_ANALYSIS", ctx)

    def test_market_general_concept_does_not_attach_context(self):
        self.assertEqual(self.win._context_instruction("O que e tendencia?"), "")

    def test_quant_execution_keeps_selected_csv_context(self):
        dataset = ROOT / "projetos" / "_studio_quant_dataset.csv"
        dataset.write_text(
            "timestamp,open,high,low,close\n"
            "2026-01-01T00:00:00+00:00,1,2,1,2\n"
            "2026-01-02T00:00:00+00:00,2,3,2,3\n",
            encoding="utf-8",
        )
        self.win._set_context_path(dataset, "teste")
        ctx = self.win._context_instruction("Teste essa StrategySpec.")
        self.assertIn(str(dataset), ctx)
        self.assertIn("USER_INTENT=QUANT_EXECUTION", ctx)

    def test_quant_general_concept_does_not_attach_context(self):
        self.assertEqual(self.win._context_instruction("O que e backtest?"), "")

    def test_subject_change_does_not_attach_context(self):
        self.win._context_instruction("Analise esse robo.")
        self.assertEqual(self.win._context_instruction("Nao quero falar de robos. Vamos falar de carros."), "")
        self.assertFalse(self.win.file_context_active)

    def test_returning_to_robot_reattaches_context(self):
        self.win._context_instruction("Nao quero falar de robos. Vamos falar de carros.")
        ctx = self.win._context_instruction("Agora voltando ao robo, qual e a logica de entrada?")
        self.assertIn(str(self.path), ctx)

    def test_context_status_question_uses_real_selected_path(self):
        self.win._answer_context_status_question()
        answers = [m["text"] for m in self.win.current_conversation if m.get("role") == "assistant"]
        self.assertIn(str(self.path), answers[-1])

    def test_switching_selected_file_uses_new_file_without_hardcode(self):
        other = ROOT / "projetos" / "_coding_test" / "context_resolution_other.py"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("def exemplo():\n    return 'novo arquivo'\n", encoding="utf-8")
        before = sha256_file(other)
        self.win._set_context_path(other, "teste")
        ctx = self.win._context_instruction("O que esse arquivo faz?")
        self.assertIn(str(other), ctx)
        self.assertNotIn("Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5", ctx)
        self.assertEqual(sha256_file(other), before)

    def test_gold_black_modules_toggle_without_losing_chat_or_context(self):
        self.win._show_chat_mode()
        self.win.current_conversation = [{"role": "user", "text": "Ola"}]
        self.win._open_module("Quant")
        self.assertFalse(self.win.module_panel.isHidden())
        self.assertTrue(self.win.chat_output.isHidden())
        self.win._open_module("Market")
        self.assertFalse(self.win.module_panel.isHidden())
        self.win._open_module("Chat")
        self.assertFalse(self.win.chat_output.isHidden())
        self.assertEqual(self.win.current_conversation[0]["text"], "Ola")
        self.assertEqual(self.win.selected_context_path, self.path)

    def test_focus_mode_and_layout_settings(self):
        self.win._set_focus_mode(True)
        self.assertTrue(self.win.focus_mode)
        self.assertTrue(self.win.left_panel.isHidden())
        self.win._set_focus_mode(False)
        self.assertFalse(self.win.left_panel.isHidden())
        self.assertFalse(self.win.focus_mode)

    def test_media_memory_and_activity_panels_are_reachable(self):
        for module in ("Media Study", "Memoria", "Perfil", "Terminal"):
            with self.subTest(module=module):
                self.win._open_module(module)
                self.app.processEvents()
        self.assertTrue((not self.win.terminal.isHidden()) or (not self.win.activity_panel.isHidden()) or (not self.win.module_panel.isHidden()))

    def test_agent_indicator_updates_from_specialist_response(self):
        self.win._append_assistant_message("Especialista: Quant\n- Resultado TESTED.")
        self.assertIn("Quant", self.win.agent_indicator.text())


if __name__ == "__main__":
    unittest.main()
