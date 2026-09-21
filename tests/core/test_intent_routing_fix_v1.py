from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from core.intent import IntentRouter


class IntentRoutingFixV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.router = IntentRouter()

    def assert_coding(self, text: str):
        decision = self.router.classify_coding_change(text)
        self.assertTrue(decision.execution_requested, decision)
        self.assertEqual(decision.intent, "CODING_CHANGE")

    def assert_general(self, text: str):
        decision = self.router.classify_coding_change(text)
        self.assertFalse(decision.execution_requested, decision)
        self.assertEqual(decision.intent, "GENERAL_CONVERSATION")

    def test_01_corrija_esse_codigo(self):
        self.assert_coding("Corrija esse código.")

    def test_02_corrija_arquivo_selecionado(self):
        self.assert_coding("Corrija o arquivo selecionado.")

    def test_03_arrume_esse_erro(self):
        self.assert_coding("Arrume esse erro.")

    def test_04_altere_essa_funcao(self):
        self.assert_coding("Altere essa função.")

    def test_05_eu_vou_corrigir_isso(self):
        self.assert_general("Eu vou corrigir isso.")

    def test_06_vou_corrigir_voce_depois(self):
        self.assert_general("Vou corrigir você depois.")

    def test_07_precisa_ser_corrigido(self):
        self.assert_general("Isso precisa ser corrigido.")

    def test_08_depois_vamos_melhorar(self):
        self.assert_general("Depois vamos melhorar isso.")

    def test_09_estou_criando_voce(self):
        self.assert_general("Eu estou criando você.")

    def test_10_nao_corrija_nada(self):
        self.assert_general("Não corrija nada.")

    def test_11_apenas_analise(self):
        self.assert_general("Apenas analise.")

    def test_12_pergunta_sobre_corrigir(self):
        self.assert_general("Você consegue corrigir isso?")

    def test_13_matematica(self):
        self.assert_general("Quanto é 25 x 4?")

    def test_14_conversa_programacao(self):
        self.assert_general("Uma função Python pode receber parâmetros?")

    def test_15_coding_task_real_continua(self):
        from studio.golden_ai_studio import GoldenAIStudio

        win = GoldenAIStudio()
        self.assertTrue(win._is_coding_change_request("Corrija esse código."))
        self.assertFalse(win._is_coding_change_request("Certo vou corrigir isso porque eu estou criando você"))
        win.close()

    def test_16_continuation_requires_active_task(self):
        self.assertFalse(self.router.classify_coding_change("E também ajuste os testes.").execution_requested)
        self.assertTrue(self.router.classify_coding_change("E também ajuste os testes.", active_coding_task=True).execution_requested)


if __name__ == "__main__":
    unittest.main()
