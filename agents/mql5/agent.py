from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class MQL5Agent(BaseAgent):
    name = "MQL5Agent"
    role = "Analyzes MQL5 files in read-only mode by default."

    def can_handle(self, task: Task) -> bool:
        text = task.description.lower()
        return "mql5" in text or ".mq5" in text or ".mqh" in text or "ea " in text or "robo" in text or "robô" in text

    def plan(self, task: Task) -> list[str]:
        return ["identificar arquivo MQL5", "analisar read-only", "usar compilacao existente se pedido", "usar Coding V1 para alteracao"]

    def execute(self, task: Task) -> AgentResult:
        text = self._text(task)
        change_requested = any(word in text for word in ("corrija", "alterar", "altere", "modifique", "modificar"))
        if change_requested:
            return AgentResult(
                self.name,
                AgentTaskStatus.WAITING_APPROVAL.value,
                "Alteracao MQL5 exige Coding V1 e aprovacao; agente nao modifica .mq5 diretamente.",
                {"coding_v1_required": True, "approval_required": True, "mql5_write_direct": False},
                warnings=["Nenhum arquivo .mq5 foi alterado pelo agente."],
            )
        return AgentResult(
            self.name,
            AgentTaskStatus.COMPLETED.value,
            "Analise MQL5 em modo somente leitura; sem operacao MT5 real.",
            {"read_only": True, "mt5_orders": False},
            evidence_level="SOURCE_CLAIM",
        )
