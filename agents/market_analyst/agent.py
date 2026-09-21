from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class MarketAnalystAgent(BaseAgent):
    name = "MarketAnalystAgent"
    role = "Analyzes market context without live trading."

    def can_handle(self, task: Task) -> bool:
        return any(word in task.description.lower() for word in ("market", "mercado", "regime", "snapshot"))

    def plan(self, task: Task) -> list[str]:
        return ["usar Market V1", "separar OBSERVED/INFERRED/HYPOTHESIS", "nao gerar recomendacao operacional"]

    def execute(self, task: Task) -> AgentResult:
        return AgentResult(
            self.name,
            AgentTaskStatus.COMPLETED.value,
            "Analise Market deve reutilizar Market V1 e preservar niveis OBSERVED, INFERRED e HYPOTHESIS.",
            {"market_v1": True, "operational_signal": False},
            evidence_level="HYPOTHESIS",
        )
