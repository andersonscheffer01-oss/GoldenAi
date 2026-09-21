"""Políticas P0 de resposta e ACK; sem IA e sem heurística por texto."""
import time

ACK_THRESHOLD_MS = 1000


def ack_for_decision(decision, registry):
    if decision.requires_planning:
        return {"emitted": True, "message": "Recebi. Vou analisar isso.",
                "reason": "planner", "emitted_at": time.time()}
    for step in decision.steps:
        tool = registry.get(step.tool) if step.tool else None
        if tool and (tool.response_policy.value == "BACKGROUND"
                     or tool.expected_latency_ms >= ACK_THRESHOLD_MS):
            return {"emitted": True, "message": "Certo, estou verificando.",
                    "reason": "background", "emitted_at": time.time()}
    return {"emitted": False, "message": "", "reason": "instant", "emitted_at": 0.0}
