from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class RiskAgent(BaseAgent):
    name = "RiskAgent"
    role = "Checks operational and trading risk."

    def can_handle(self, task: Task) -> bool:
        return "risk" in task.description.lower() or "risco" in task.description.lower()

    def plan(self, task: Task) -> list[str]:
        return ["detectar WRITE sem aprovacao", "detectar path protegido", "bloquear operacao financeira/externa perigosa"]

    def execute(self, task: Task) -> AgentResult:
        text = self._text(task)
        blocked_terms = ("apague", "delete", "remove-item", "ordem", "comprar", "vender", "instale", "internet", "shell irrestrito")
        blocked = [term for term in blocked_terms if term in text]
        status = AgentTaskStatus.FAILED.value if blocked else AgentTaskStatus.COMPLETED.value
        summary = "Risk bloqueou acao proibida." if blocked else "Risk nao detectou acao proibida nesta V1."
        return AgentResult(
            self.name,
            status,
            summary,
            {"blocked": bool(blocked), "blocked_terms": blocked, "permissions_escalated": False},
            warnings=["Nenhum agente recebe permissao adicional."],
        )
