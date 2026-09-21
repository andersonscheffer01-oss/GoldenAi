from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.audit import AuditLogger

from agents.base import AgentContext, AgentResult, AgentTaskStatus, Task
from agents.market_analyst import MarketAnalystAgent
from agents.media_study import MediaStudyAgent
from agents.mql5 import MQL5Agent
from agents.programmer import ProgrammerAgent
from agents.python_quant import PythonQuantAgent
from agents.reviewer import ReviewerAgent
from agents.risk import RiskAgent
from agents.statistician import StatisticianAgent


@dataclass
class AgentTaskRecord:
    task_id: str
    description: str
    status: str = AgentTaskStatus.CREATED.value
    selected_agents: list[str] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentOrchestrator:
    def __init__(self, root: str | Path = r"C:\GoldenAI", context: AgentContext | None = None, audit_logger: AuditLogger | None = None):
        self.root = Path(root)
        self.context = context or AgentContext(root=str(self.root))
        self.audit = audit_logger or AuditLogger(self.root / "logs")
        self.agents = [
            RiskAgent(self.context),
            MQL5Agent(self.context),
            ProgrammerAgent(self.context),
            PythonQuantAgent(self.context),
            MarketAnalystAgent(self.context),
            StatisticianAgent(self.context),
            MediaStudyAgent(self.context),
            ReviewerAgent(self.context),
        ]
        self.reviewer = next(agent for agent in self.agents if agent.name == "ReviewerAgent")
        self.risk = next(agent for agent in self.agents if agent.name == "RiskAgent")
        self.current_task: AgentTaskRecord | None = None
        self.previous_task: AgentTaskRecord | None = None

    def _audit(self, action_type: str, status: str, target: str = "", detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "agents.orchestrator.v1",
            "target": target,
            "result": str(detail or "")[:1000],
            "files_changed": [],
            "commands_executed": [],
        })

    def route(self, description: str, context: dict[str, Any] | None = None) -> AgentTaskRecord:
        task = Task.create(description, context or {})
        record = AgentTaskRecord(task.task_id, description, status=AgentTaskStatus.CREATED.value)
        self._audit("AGENT_TASK_CREATED", "CREATED", task.task_id, description[:300])

        if self._is_subject_change(description):
            self.previous_task = self.current_task
            self.current_task = None
            record.status = AgentTaskStatus.CANCELLED.value
            record.plan = {"reason": "mudanca_de_assunto"}
            return record

        selected = self._select_agents(task)
        record.selected_agents = [agent.name for agent in selected]
        record.status = AgentTaskStatus.ROUTED.value
        record.plan = self._build_plan(task, selected)
        self._audit("AGENT_ROUTED", "ROUTED", task.task_id, ",".join(record.selected_agents) or "general")
        return record

    def execute(self, description: str, context: dict[str, Any] | None = None, review: bool | None = None) -> AgentTaskRecord:
        record = self.route(description, context)
        if record.status == AgentTaskStatus.CANCELLED.value:
            return record
        if not record.selected_agents:
            record.status = AgentTaskStatus.COMPLETED.value
            record.results.append(asdict(AgentResult("GeneralConversation", AgentTaskStatus.COMPLETED.value, "Conversa geral; nenhum agente especializado necessario.")))
            self.current_task = record
            return record

        task = Task(record.task_id, description, context or {}, status=AgentTaskStatus.ROUTED)
        record.status = AgentTaskStatus.RUNNING.value
        self._audit("AGENT_STARTED", "RUNNING", record.task_id, ",".join(record.selected_agents))
        results: list[AgentResult] = []
        for agent in self._agents_by_name(record.selected_agents):
            try:
                result = agent.execute(task)
                results.append(result)
                record.results.append(asdict(result))
                self._audit("AGENT_COMPLETED", result.status, record.task_id, agent.name)
            except Exception as exc:
                failed = AgentResult(agent.name, AgentTaskStatus.FAILED.value, f"{type(exc).__name__}: {exc}")
                results.append(failed)
                record.results.append(asdict(failed))
                self._audit("AGENT_FAILED", "FAILED", record.task_id, f"{agent.name}: {exc}")

        record.conflicts = self._detect_conflicts(results)
        if record.conflicts:
            self._audit("AGENT_CONFLICT", "DETECTED", record.task_id, "; ".join(record.conflicts))

        should_review = bool(review) or self._needs_review(description, results, record.conflicts)
        if should_review:
            reviewed = self.reviewer.review(AgentResult("Orchestrator", AgentTaskStatus.COMPLETED.value, self.consolidate(record), {"results": record.results, "conflicts": record.conflicts}))
            record.results.append(asdict(reviewed))
            self._audit("AGENT_REVIEW_COMPLETED", "COMPLETED", record.task_id, "ReviewerAgent")

        if any(result.status == AgentTaskStatus.WAITING_APPROVAL.value for result in results):
            record.status = AgentTaskStatus.WAITING_APPROVAL.value
        elif any(result.status == AgentTaskStatus.FAILED.value for result in results):
            record.status = AgentTaskStatus.FAILED.value
        else:
            record.status = AgentTaskStatus.COMPLETED.value
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self.previous_task = self.current_task
        self.current_task = record
        return record

    def consolidate(self, record: AgentTaskRecord) -> str:
        if not record.selected_agents:
            return "Conversa geral; nenhum especialista foi necessario."
        lines = []
        if len(record.selected_agents) == 1:
            lines.append(f"Especialista: {record.selected_agents[0]}")
        else:
            lines.append("Especialistas: " + " -> ".join(record.selected_agents))
        for result in record.results:
            evidence = f" [{result.get('evidence_level')}]" if result.get("evidence_level") else ""
            lines.append(f"- {result.get('agent')}: {result.get('summary')}{evidence}")
        if record.conflicts:
            lines.append("Conflitos preservados: " + "; ".join(record.conflicts))
        return "\n".join(lines)

    def _select_agents(self, task: Task) -> list[Any]:
        text = task.description.lower()
        if self._is_general_question(text):
            return []
        selected = []
        risk_result = self.risk.execute(task)
        if risk_result.data.get("blocked"):
            return [self.risk]
        complex_flow = self._is_complex_flow(text)
        for agent in self.agents:
            if agent.name in {"RiskAgent", "ReviewerAgent"}:
                continue
            if agent.can_handle(task):
                selected.append(agent)
        if complex_flow:
            for agent_name in ("MarketAnalystAgent", "PythonQuantAgent", "StatisticianAgent"):
                agent = self._agent_by_name(agent_name)
                if agent and agent not in selected:
                    selected.append(agent)
            if "revis" in text:
                selected.append(self.reviewer)
        elif "revis" in text and not selected:
            selected.append(self.reviewer)
        return self._dedupe_agents(selected)

    def _build_plan(self, task: Task, selected: list[Any]) -> dict[str, Any]:
        if not selected:
            return {"objective": task.description, "agents": [], "steps": [], "risks": []}
        steps = []
        risks = ["permissoes nao sao elevadas pelo orquestrador"]
        tools = []
        for agent in selected:
            steps.extend(agent.plan(task))
            tools.extend(self._tools_for_agent(agent.name))
        return {
            "objective": task.description,
            "agents": [agent.name for agent in selected],
            "tools": sorted(set(tools)),
            "dependencies": ["ToolRegistry", "PermissionManager", "AuditLogger"],
            "steps": self._dedupe_text(steps),
            "risks": risks,
        }

    def _detect_conflicts(self, results: list[AgentResult]) -> list[str]:
        levels = {result.evidence_level for result in results if result.evidence_level}
        conflicts = []
        if "SOURCE_CLAIM" in levels and "TESTED" in levels:
            conflicts.append("SOURCE_CLAIM e TESTED coexistem; nao foram fundidos em VALIDATED.")
        if any(result.data.get("blocked") for result in results) and len(results) > 1:
            conflicts.append("RiskAgent bloqueou acao que outros agentes nao devem executar.")
        return conflicts

    def _needs_review(self, description: str, results: list[AgentResult], conflicts: list[str]) -> bool:
        text = description.lower()
        return bool(conflicts) or "revis" in text or any(result.status == AgentTaskStatus.WAITING_APPROVAL.value for result in results)

    def _is_complex_flow(self, text: str) -> bool:
        return ("analise" in text or "analisa" in text) and ("teste" in text or "backtest" in text) and ("revis" in text or "resultado" in text)

    def _is_general_question(self, text: str) -> bool:
        return any(phrase in text for phrase in ("explique python", "o que e python", "o que é python")) and not any(token in text for token in (".py", "corrija", "analise esse"))

    def _is_subject_change(self, description: str) -> bool:
        text = description.lower()
        return any(phrase in text for phrase in ("vamos falar sobre carros", "nao quero falar", "não quero falar"))

    def _agents_by_name(self, names: list[str]) -> list[Any]:
        return [agent for name in names for agent in self.agents if agent.name == name]

    def _agent_by_name(self, name: str) -> Any | None:
        return next((agent for agent in self.agents if agent.name == name), None)

    def _dedupe_agents(self, agents: list[Any]) -> list[Any]:
        seen = set()
        unique = []
        for agent in agents:
            if agent.name not in seen:
                unique.append(agent)
                seen.add(agent.name)
        return unique

    def _dedupe_text(self, values: list[str]) -> list[str]:
        seen = set()
        out = []
        for value in values:
            if value not in seen:
                out.append(value)
                seen.add(value)
        return out

    def _tools_for_agent(self, name: str) -> list[str]:
        return {
            "ProgrammerAgent": ["CodingService"],
            "MQL5Agent": ["ler_arquivo", "compilar_mql5", "CodingService"],
            "PythonQuantAgent": ["quant_run_backtest", "quant_get_metrics", "quant_compare_experiments"],
            "MarketAnalystAgent": ["market_analyze_dataset", "market_get_analysis"],
            "StatisticianAgent": ["quant_get_metrics", "memory_search_knowledge"],
            "MediaStudyAgent": ["media_ingest_source", "media_study_source", "media_search_source"],
            "ReviewerAgent": ["CodingService", "AuditLogger"],
            "RiskAgent": ["PermissionManager", "AuditLogger"],
        }.get(name, [])
