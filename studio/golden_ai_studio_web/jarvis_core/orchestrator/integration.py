"""Ponte única Orchestrator -> Planner -> TaskManager -> JarvisService."""
from ..task_manager import ConfirmationRequired, Planner, TaskManager
from .models import Route
from ..response_policy import ack_for_decision


class JarvisRuntimeCoordinator:
    def __init__(self, orchestrator, service, task_manager=None, planner=None):
        self.orchestrator = orchestrator
        self.service = service
        self.task_manager = task_manager or TaskManager(service.audit.path.parent)
        self.planner = planner or Planner(orchestrator.models, service.registry, orchestrator.skills)
        self.active_task_id = None

    def process(self, request, decision=None):
        decision = decision or self.orchestrator.decide(request)
        ack = ack_for_decision(decision, self.service.registry)
        if decision.requires_clarification:
            return {"ok": True, "clarification_required": True,
                    "message": "Preciso de mais contexto.", "decision": decision}
        if not (decision.requires_planning or decision.route == Route.TASK):
            return {"ok": True, "planned": False, "decision": decision}
        plan = self.planner.plan(decision, request)
        task_id = self.task_manager.create(plan)
        self.active_task_id = task_id
        if self.orchestrator.mode == "shadow":
            return {"ok": True, "planned": True, "shadow": True,
                    "executed": False, "task_id": task_id, "plan": plan, "ack": ack}
        future = self.task_manager.start(task_id, self._execute_step)
        return {"ok": True, "planned": True, "shadow": False,
                "executed": True, "task_id": task_id, "future": future,
                "plan": plan, "ack": ack}

    def _execute_step(self, step, cancellation):
        if cancellation.is_cancelled():
            return {"ok": False, "cancelled": True}
        result = self.service.execute_tool(step.tool, step.args,
            command=f"task:{step.intent}", task_id=self.active_task_id)
        if result.get("confirmation_required"):
            raise ConfirmationRequired(result.get("token"))
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "Falha na etapa")
        return result

    def cancel_active_task(self):
        return bool(self.active_task_id and self.task_manager.cancel(self.active_task_id))
