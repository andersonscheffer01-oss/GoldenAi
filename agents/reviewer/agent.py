from agents.base import AgentResult, AgentTaskStatus, BaseAgent, Task


class ReviewerAgent(BaseAgent):
    name = "ReviewerAgent"
    role = "Reviews proposals, diffs, evidence, and risk."

    def can_handle(self, task: Task) -> bool:
        return "review" in task.description.lower() or "revis" in task.description.lower()

    def plan(self, task: Task) -> list[str]:
        return ["revisar diff/resultado", "avaliar riscos", "confirmar testes", "nao aplicar alteracoes"]

    def execute(self, task: Task) -> AgentResult:
        return AgentResult(
            self.name,
            AgentTaskStatus.COMPLETED.value,
            "Reviewer concluiu revisao inicial sem aplicar alteracoes.",
            {"applies_changes": False, "review_scope": ["diff", "risk", "tests", "affected_files"]},
        )

    def review(self, result: AgentResult) -> AgentResult:
        result.data["reviewed_by"] = self.name
        result.data["review_applied_changes"] = False
        return result
