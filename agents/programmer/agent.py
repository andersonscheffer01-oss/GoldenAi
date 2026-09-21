from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class ProgrammerAgent(BaseAgent):
    name = "ProgrammerAgent"
    role = "Proposes safe code changes for review."

    def can_handle(self, task: Task) -> bool:
        text = task.description.lower()
        return any(word in text for word in ("code", "codigo", "código", ".py", "python", "corrija", "alterar", "modifique"))

    def plan(self, task: Task) -> list[str]:
        return ["mapear arquivo", "analisar pedido", "usar Coding V1 quando houver alteracao", "aguardar aprovacao para escrita"]

    def execute(self, task: Task) -> AgentResult:
        text = self._text(task)
        change_requested = any(word in text for word in ("corrija", "corrigir", "alterar", "altere", "modifique", "modificar"))
        if change_requested:
            return AgentResult(
                self.name,
                AgentTaskStatus.WAITING_APPROVAL.value,
                "Pedido de alteracao roteado para Coding V1; nenhuma escrita deve ocorrer sem aprovacao.",
                {"coding_v1_required": True, "approval_required": True},
                warnings=["WRITE continua bloqueado ate aprovacao valida do Coding V1."],
            )
        return AgentResult(
            self.name,
            AgentTaskStatus.COMPLETED.value,
            "Analise de codigo em modo somente leitura preparada.",
            {"coding_v1_required": False, "read_only": True},
        )
