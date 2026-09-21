from __future__ import annotations

import builtins
import contextlib
import io
import json
import runpy
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_motor_globals():
    original_input = builtins.input
    builtins.input = lambda prompt="": "sair"
    try:
        return runpy.run_path(str(ROOT / "app" / "golden_ai.py"))
    finally:
        builtins.input = original_input


class MotorCoreIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = load_motor_globals()

    def audit_text(self) -> str:
        path = ROOT / "logs" / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def market_csv(self) -> Path:
        path = ROOT / "projetos" / "_market_chat_test.csv"
        rows = [
            "timestamp,open,high,low,close",
            "2026-01-01T00:00:00+00:00,100,100.5,99.5,100",
            "2026-01-02T00:00:00+00:00,100,102.5,99.5,102",
            "2026-01-03T00:00:00+00:00,102,104.5,101.5,104",
            "2026-01-04T00:00:00+00:00,104,106.5,103.5,106",
            "2026-01-05T00:00:00+00:00,106,108.5,105.5,108",
            "2026-01-06T00:00:00+00:00,108,110.5,107.5,110",
        ]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return path

    def test_listar_projetos_allowed(self):
        result = self.motor["executar_tool_core"]("listar_projetos", {})
        self.assertIn("Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5", str(result))

    def test_ler_arquivo_inside_projects_allowed(self):
        content, error = self.motor["executar_tool_core"]("ler_arquivo", {"nome": "robo_teste.mq5"})
        self.assertIsNone(error)
        self.assertTrue(content)

    def test_file_metadata_tool_counts_selected_robot_lines(self):
        result = self.motor["executar_tool_core"]("arquivo_metadados", {"nome": "Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["nome"], "Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5")
        self.assertEqual(result["linhas"], 903)
        self.assertEqual(result["extensao"], ".mq5")
        self.assertGreater(result["tamanho_bytes"], 0)

    def test_file_metadata_intent_returns_objective_portuguese_answer(self):
        pergunta = (
            "Quantas linhas tem o codigo desse robo?\n\n"
            "[STUDIO_CONTEXT]\n"
            "CURRENT_CONTEXT_PATH=C:\\GoldenAI\\projetos\\Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5\n"
            "CURRENT_CONTEXT_NAME=Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5\n"
            "USER_INTENT=FILE_METADATA\n"
            "RESPONSE_LANGUAGE=pt\n"
            "READ_ONLY=true\n"
            "[/STUDIO_CONTEXT]"
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.motor["executar_agente_normal"](pergunta, permitir_ferramentas=True)
        text = out.getvalue()
        self.assertIn("[GoldenAI usando ferramenta: arquivo_metadados]", text)
        self.assertIn("O arquivo Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5 possui 903 linhas.", text)

    def test_file_metadata_without_context_asks_for_selection(self):
        globals_ = self.motor["responder_metadados_arquivo"].__globals__
        original = globals_.get("arquivo_alvo_atual")
        globals_["arquivo_alvo_atual"] = None
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.motor["executar_agente_normal"]("Quantas linhas tem esse codigo?", permitir_ferramentas=False)
            self.assertIn("selecione ou indique o arquivo", out.getvalue().lower())
        finally:
            globals_["arquivo_alvo_atual"] = original

    def test_market_tool_analyzes_authorized_csv(self):
        csv_path = self.market_csv()
        result = self.motor["executar_tool_core"](
            "market_analyze_dataset",
            {"nome": csv_path.name, "symbol": "TEST", "timeframe": "H1"},
        )
        self.assertIn("analysis_id", result)
        self.assertEqual(result["inferred"][0]["regime"], "TREND_UP")
        self.assertEqual(result["multi_timeframe"]["alignment"], "TREND_UP")

    def test_market_chat_routes_dataset_and_followups(self):
        csv_path = self.market_csv()
        pergunta = (
            "Analise este dataset de mercado.\n\n"
            "[STUDIO_CONTEXT]\n"
            f"CURRENT_CONTEXT_PATH={csv_path}\n"
            f"CURRENT_CONTEXT_NAME={csv_path.name}\n"
            "USER_INTENT=MARKET_ANALYSIS\n"
            "RESPONSE_LANGUAGE=pt\n"
            "READ_ONLY=true\n"
            "[/STUDIO_CONTEXT]"
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.motor["responder_market_chat"](pergunta)
        self.assertIn("Analise Market concluida", out.getvalue())
        for prompt, expected in [
            ("Qual o regime desse periodo?", "TREND_UP"),
            ("Os timeframes estao alinhados?", "alinhamento"),
            ("Quais estruturas foram detectadas?", "Estrutura detectada"),
            ("Quais observacoes foram encontradas?", "Observado"),
            ("Existe sinal de compra?", "nao validado por Quant"),
            ("Isso esta validado?", "Nao."),
            ("Voltando a analise, qual era o regime?", "TREND_UP"),
        ]:
            with self.subTest(prompt=prompt):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.motor["responder_market_chat"](prompt)
                self.assertIn(expected, out.getvalue())

    def test_market_strategy_spec_bridge_does_not_backtest(self):
        csv_path = self.market_csv()
        self.motor["executar_tool_core"]("market_analyze_dataset", {"nome": csv_path.name, "symbol": "TEST", "timeframe": "H1"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.motor["responder_market_chat"]("Transforme essa hipotese em StrategySpec.")
        text = out.getvalue()
        self.assertIn("market_context_placeholder", text)
        self.assertIn("NOT_BACKTESTED", text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.motor["responder_market_chat"]("Teste essa StrategySpec.")
        self.assertIn("Nao rodei backtest pelo Market", out.getvalue())

    def test_quant_explicit_backtest_and_followups(self):
        csv_path = self.market_csv()
        self.motor["executar_tool_core"]("market_analyze_dataset", {"nome": csv_path.name, "symbol": "TEST", "timeframe": "H1"})
        with contextlib.redirect_stdout(io.StringIO()):
            self.motor["responder_market_chat"]("Transforme essa hipotese em StrategySpec.")
        pergunta = (
            "Teste essa StrategySpec.\n\n"
            "[STUDIO_CONTEXT]\n"
            f"CURRENT_CONTEXT_PATH={csv_path}\n"
            f"CURRENT_CONTEXT_NAME={csv_path.name}\n"
            "USER_INTENT=QUANT_EXECUTION\n"
            "RESPONSE_LANGUAGE=pt\n"
            "READ_ONLY=true\n"
            "[/STUDIO_CONTEXT]"
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.motor["responder_quant_chat"](pergunta)
        text = out.getvalue()
        self.assertIn("Experimento Quant concluido", text)
        self.assertIn("Experiment ID:", text)
        self.assertIn("Status: TESTED", text)
        self.assertNotIn("VALIDATED", text.split("Status: TESTED")[0])
        for prompt, expected in [
            ("Quantas operacoes teve?", "operacoes"),
            ("Qual foi o drawdown?", "Max drawdown"),
            ("Mostre os piores trades.", "Piores trades"),
            ("Isso esta validado?", "nao e VALIDATED"),
            ("Voltando ao teste, qual foi o profit factor?", "Profit factor"),
        ]:
            with self.subTest(prompt=prompt):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.motor["responder_quant_chat"](prompt)
                self.assertIn(expected, out.getvalue())

    def test_quant_strategy_without_dataset_does_not_execute(self):
        globals_ = self.motor["responder_quant_chat"].__globals__
        original_dataset = globals_.get("QUANT_LAST_DATASET_PATH")
        original_spec = globals_.get("QUANT_LAST_STRATEGY_SPEC")
        globals_["QUANT_LAST_DATASET_PATH"] = None
        globals_["QUANT_LAST_STRATEGY_SPEC"] = {"name": "x", "entry_logic_identifier": "close_above_open", "parameters": {"hold_bars": 1}}
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.motor["responder_quant_chat"]("Teste essa StrategySpec.")
            self.assertIn("Preciso que voce selecione", out.getvalue())
        finally:
            globals_["QUANT_LAST_DATASET_PATH"] = original_dataset
            globals_["QUANT_LAST_STRATEGY_SPEC"] = original_spec

    def test_quant_compare_two_experiments(self):
        csv_path = self.market_csv()
        spec = {"name": "A", "entry_logic_identifier": "close_above_open", "parameters": {"hold_bars": 1}, "symbol": "TEST", "timeframe": "H1"}
        self.motor["executar_tool_core"]("quant_run_backtest", {"nome": csv_path.name, "strategy_spec": spec, "initial_capital": 10000, "quantity": 1, "spread": 0, "commission": 0, "slippage": 0})
        spec_b = {"name": "B", "entry_logic_identifier": "always_long", "parameters": {"hold_bars": 1}, "symbol": "TEST", "timeframe": "H1"}
        self.motor["executar_tool_core"]("quant_run_backtest", {"nome": csv_path.name, "strategy_spec": spec_b, "initial_capital": 10000, "quantity": 1, "spread": 0, "commission": 0, "slippage": 0})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.motor["responder_quant_chat"]("Compare com outro experimento.")
        self.assertIn("comparison_id", out.getvalue())

    def test_quant_does_not_route_general_or_weak_intent(self):
        self.assertFalse(self.motor["pergunta_pede_quant"]("O que e backtest?"))
        self.assertFalse(self.motor["pergunta_pede_quant"]("Esse regime parece interessante."))
        self.assertFalse(self.motor["pergunta_pede_quant"]("Agora vamos falar de carros."))

    def test_quant_blocks_arbitrary_disk_read(self):
        result = self.motor["executar_tool_core"](
            "quant_run_backtest",
            {"nome": r"..\..\Windows\System32\drivers\etc\hosts", "strategy_spec": {"entry_logic_identifier": "always_long"}, "initial_capital": 10000, "quantity": 1, "spread": 0, "commission": 0, "slippage": 0},
        )
        self.assertTrue("outside" in str(result).lower() or "bloque" in str(result).lower())

    def test_market_does_not_route_general_conversation(self):
        self.assertFalse(self.motor["pergunta_pede_market"]("O que e tendencia?"))
        self.assertFalse(self.motor["pergunta_pede_market"]("Quanto e 25 x 4?"))

    def test_market_without_dataset_does_not_invent_path(self):
        globals_ = self.motor["responder_market_chat"].__globals__
        original = globals_.get("MARKET_LAST_ANALYSIS_ID")
        globals_["MARKET_LAST_ANALYSIS_ID"] = None
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.motor["responder_market_chat"]("Analise este dataset.")
            self.assertIn("Nao vou inventar um dataset", out.getvalue())
        finally:
            globals_["MARKET_LAST_ANALYSIS_ID"] = original

    def test_market_blocks_arbitrary_disk_read(self):
        result = self.motor["executar_tool_core"](
            "market_analyze_dataset",
            {"nome": r"..\..\Windows\System32\drivers\etc\hosts", "symbol": "TEST", "timeframe": "H1"},
        )
        self.assertTrue("outside" in str(result).lower() or "bloque" in str(result).lower())

    def test_read_outside_goldenai_blocked(self):
        result = self.motor["executar_tool_core"](
            "ler_arquivo",
            {"nome": r"..\..\Windows\System32\drivers\etc\hosts"},
        )
        self.assertIn("outside", str(result).lower())

    def test_path_traversal_blocked(self):
        result = self.motor["executar_tool_core"]("ler_arquivo", {"nome": r"..\app\golden_ai.py"})
        self.assertTrue("outside" in str(result).lower() or "bloque" in str(result).lower())

    def test_escrever_arquivo_blocked(self):
        result = self.motor["executar_tool_core"](
            "escrever_arquivo",
            {"nome": "robo_teste.mq5", "conteudo": "nao gravar"},
        )
        self.assertIn("BLOQUEADA", str(result).upper())

    def test_compilar_mql5_permission_checked(self):
        allowed, reason, permission_class, target = self.motor["check_tool_permission"](
            "compilar_mql5",
            {"nome": "robo_teste.mq5"},
        )
        self.assertTrue(allowed)
        self.assertEqual(permission_class, "EXECUTE")
        self.assertTrue(str(target).lower().endswith(".mq5"))

    def test_allowed_call_generates_audit_log(self):
        self.motor["executar_tool_core"]("listar_projetos", {})
        text = self.audit_text()
        self.assertIn("TOOL_ALLOWED", text)
        self.assertIn("TOOL_COMPLETED", text)

    def test_blocked_call_generates_audit_log(self):
        self.motor["executar_tool_core"]("escrever_arquivo", {"nome": "robo_teste.mq5", "conteudo": "x"})
        text = self.audit_text()
        self.assertIn("TOOL_DENIED", text)

    def test_handler_exception_generates_tool_failed(self):
        registry = self.motor["CORE_TOOL_REGISTRY"]
        tool_definition = self.motor["ToolDefinition"]
        original = registry.get("listar_projetos")
        def fail():
            raise RuntimeError("falha controlada")
        registry.register(tool_definition("listar_projetos", "falha", {}, "READ", fail, "read"))
        try:
            result = self.motor["executar_tool_core"]("listar_projetos", {})
            self.assertIn("Erro ao executar", str(result))
            self.assertIn("TOOL_FAILED", self.audit_text())
        finally:
            registry.register(original)

    def test_unknown_tool_is_not_executed(self):
        with self.assertRaises(Exception):
            self.motor["executar_tool_core"]("ferramenta_inexistente", {})

    def test_delete_backup_blocked_without_deleting(self):
        result = self.motor["executar_tool_core"](
            "excluir_backup",
            {"backup": str(ROOT / "backups" / "qualquer.py")},
        )
        self.assertIn("BLOQUEADA", str(result).upper())


if __name__ == "__main__":
    unittest.main()
