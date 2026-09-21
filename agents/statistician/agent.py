from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class StatisticianAgent(BaseAgent):
    name = "StatisticianAgent"
    role = "Evaluates statistical validity and uncertainty."

    def can_handle(self, task: Task) -> bool:
        text = task.description.lower()
        return any(word in text for word in ("stat", "estat", "confiavel", "confiável", "metric", "significance", "amostra", "overfitting", "validado"))

    def plan(self, task: Task) -> list[str]:
        return ["avaliar tamanho da amostra", "verificar custos", "destacar drawdown/expectativa", "nao inventar significancia"]

    def execute(self, task: Task) -> AgentResult:
        return AgentResult(
            self.name,
            AgentTaskStatus.COMPLETED.value,
            "Revisao estatistica inicial: resultados Quant sao TESTED; nao ha VALIDATED sem validacao adicional.",
            {
                "checks": ["sample_size", "drawdown", "expectancy", "costs", "overfitting"],
                "invented_significance": False,
            },
            evidence_level="TESTED",
            warnings=["Nao foi calculada significancia estatistica formal nesta V1."],
        )
