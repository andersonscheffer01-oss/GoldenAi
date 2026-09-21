from dataclasses import replace
import json
import inspect

from ..orchestrator.models import OrchestratorDecision, PlanStep
from .models import TaskPlan


class PlanValidationError(ValueError):
    pass


class PlannerContracts:
    MAX_STEPS = 50

    @classmethod
    def from_decision(cls, decision: OrchestratorDecision, title: str) -> TaskPlan:
        return cls.validate(TaskPlan(title=title, steps=tuple(decision.steps),
            data_classification=decision.data_classification))

    @classmethod
    def validate(cls, plan: TaskPlan) -> TaskPlan:
        if not plan.title.strip():
            raise PlanValidationError("Título da tarefa é obrigatório.")
        if not plan.steps:
            raise PlanValidationError("O plano precisa ter ao menos uma etapa.")
        if len(plan.steps) > cls.MAX_STEPS:
            raise PlanValidationError("O plano excede o limite de etapas.")
        if not 0 < float(plan.timeout_seconds) <= 3600:
            raise PlanValidationError("Timeout da tarefa fora do limite.")
        ids = [step.id for step in plan.steps]
        if any(not step_id.strip() for step_id in ids) or len(ids) != len(set(ids)):
            raise PlanValidationError("IDs de etapas devem ser únicos e não vazios.")
        known = set(ids)
        for step in plan.steps:
            if step.id in step.dependencies or any(dep not in known for dep in step.dependencies):
                raise PlanValidationError(f"Dependência inválida na etapa {step.id}.")
        cls._assert_acyclic(plan.steps)
        return replace(plan, title=plan.title.strip(), description=plan.description.strip())

    @staticmethod
    def _assert_acyclic(steps: tuple[PlanStep, ...]):
        graph = {step.id: set(step.dependencies) for step in steps}
        visiting, visited = set(), set()

        def visit(node):
            if node in visiting:
                raise PlanValidationError("O plano contém dependência cíclica.")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)


class Planner:
    """Planner estruturado. Usa ModelRouter; nunca chama provider diretamente."""
    def __init__(self, model_router, registry, skills_router):
        self.model_router = model_router
        self.registry = registry
        self.skills_router = skills_router

    def plan(self, decision: OrchestratorDecision, request: str) -> TaskPlan:
        tools = self.skills_router.llm_tools(decision.preferred_skill)
        payload = [{"role": "system", "content":
            "Produza SOMENTE JSON: {title,goal,risk,requires_confirmation,steps:[{id,intent,tool,args,dependencies}]}. "
            "Use apenas tools fornecidas: " + json.dumps(tools, ensure_ascii=False)},
            {"role": "user", "content": request}]
        result = self.model_router.execute(payload, profile=decision.preferred_model_profile,
                                           classification=decision.data_classification)
        if not result.ok:
            raise PlanValidationError("Planner indisponível: " + result.error)
        try:
            raw = result.output if isinstance(result.output, dict) else json.loads(
                str(result.output).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            steps = []
            allowed = set(decision.allowed_tools)
            for index, item in enumerate(raw.get("steps", [])):
                tool_name = str(item.get("tool") or "")
                tool = self.registry.get(tool_name)
                if not tool or tool_name not in allowed:
                    raise PlanValidationError("Tool inexistente ou fora da skill.")
                args = item.get("args", {})
                if not isinstance(args, dict) or set(args) - set(tool.parameters):
                    raise PlanValidationError("Argumentos inválidos no plano.")
                signature = inspect.signature(tool.handler)
                for name, expected in tool.parameters.items():
                    parameter = signature.parameters.get(name)
                    if name not in args and parameter and parameter.default is inspect.Parameter.empty:
                        raise PlanValidationError("Argumento obrigatório ausente no plano.")
                    if name in args and (isinstance(args[name], bool) and expected is int
                                         or not isinstance(args[name], expected)):
                        raise PlanValidationError("Tipo de argumento inválido no plano.")
                steps.append(PlanStep(str(item.get("id") or f"step-{index + 1}"),
                    str(item.get("intent") or tool_name), decision.route, tool_name, args,
                    tuple(str(dep) for dep in (item.get("dependencies") or ())),
                    "PENDING", True, True))
            plan = TaskPlan(str(raw.get("title") or request[:80]), tuple(steps),
                data_classification=decision.data_classification,
                goal=str(raw.get("goal") or request), risk=str(raw.get("risk") or "LOW"),
                requires_confirmation=bool(raw.get("requires_confirmation")))
            return PlannerContracts.validate(plan)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, PlanValidationError):
                raise
            raise PlanValidationError("Saída estruturada inválida do Planner.") from exc
