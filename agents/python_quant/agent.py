from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class PythonQuantAgent(BaseAgent):
    name = "PythonQuantAgent"
    role = "Works on Python quantitative research contracts."

    def can_handle(self, task: Task) -> bool:
        text = task.description.lower()
        return any(word in text for word in ("quant", "backtest", "strategyspec", "experimento", "profit factor", "drawdown"))

    def plan(self, task: Task) -> list[str]:
        return ["verificar pedido explicito", "usar Quant V1", "preservar TESTED vs VALIDATED", "registrar metricas"]

    def execute(self, task: Task) -> AgentResult:
        text = self._text(task)
        explicit = any(word in text for word in ("teste", "testar", "backtest", "rode", "execute", "valide estatisticamente"))
        if not explicit:
            return AgentResult(
                self.name,
                AgentTaskStatus.COMPLETED.value,
                "Quant identificado, mas nenhum backtest foi executado sem pedido explicito.",
                {"quant_auto_executed": False, "explicit_required": True},
                evidence_level="HYPOTHESIS",
            )
        return AgentResult(
            self.name,
            AgentTaskStatus.COMPLETED.value,
            "Pedido explicito pode usar Quant V1 pelas tools existentes; resultado sera TESTED, nao VALIDATED.",
            {"quant_tool": "quant_run_backtest", "quant_auto_executed": False, "permission_path": "ToolRegistry"},
            evidence_level="TESTED",
        )
