from __future__ import annotations

import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.safety import EvidenceLevel

from .models import EvidenceType, KnowledgeItem, SourceType
from .repository import KnowledgeRepository


def new_memory_id(prefix: str = "knowledge") -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ScientificMemoryService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.repository = KnowledgeRepository(self.root)
        self.audit = AuditLogger(self.root / "logs")

    def _audit(self, action_type: str, status: str, target: str = "", detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "memory.scientific.v1",
            "target": target,
            "result": detail[:1000],
            "files_changed": [],
            "commands_executed": [],
        })

    def store_knowledge(
        self,
        topic: str,
        statement: str,
        evidence_level: EvidenceLevel | str,
        source_type: SourceType | str,
        source_id: str = "",
        source_location: str = "",
        confidence: float = 0.5,
        validation_status: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        supersedes_id: str | None = None,
    ) -> KnowledgeItem:
        level = self._safe_evidence_level(evidence_level, source_type)
        item = KnowledgeItem(
            knowledge_id=new_memory_id(),
            topic=(topic or "sem_topico").strip(),
            statement=(statement or "").strip(),
            evidence_type=self._evidence_type_for(level),
            evidence_level=level,
            source_type=self._source_value(source_type),
            source_id=str(source_id or ""),
            source_location=str(source_location or ""),
            confidence=max(0.0, min(float(confidence), 1.0)),
            validation_status=validation_status or level.value,
            supersedes_id=supersedes_id,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        saved = self.repository.save(item)
        self.repository.add_revision(new_memory_id("revision"), item.knowledge_id, "CREATE", asdict(item), item.created_at)
        self._audit("MEMORY_ITEM_CREATED", "CREATED", item.knowledge_id, f"{item.topic}; {item.normalized_evidence_level()}")
        if supersedes_id:
            self._audit("MEMORY_ITEM_SUPERSEDED", "COMPLETED", item.knowledge_id, supersedes_id)
        self._detect_and_record_conflicts(saved)
        return saved

    def get_knowledge(self, knowledge_id: str) -> dict[str, Any] | None:
        return self.repository.get(knowledge_id)

    def search_knowledge(
        self,
        topic: str = "",
        text: str = "",
        tags: list[str] | None = None,
        source_type: str = "",
        evidence_level: str = "",
        experiment_id: str = "",
        symbol: str = "",
        timeframe: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = self.repository.search(topic, text, tags, source_type, evidence_level, experiment_id, symbol, timeframe, limit)
        self._audit("MEMORY_SEARCH", "COMPLETED", topic or text or experiment_id, f"count={len(rows)}")
        return rows

    def find_related_experiments(self, query: str = "", symbol: str = "", timeframe: str = "", limit: int = 10) -> list[dict[str, Any]]:
        rows = self.search_knowledge(
            text=query,
            source_type=SourceType.QUANT_EXPERIMENT.value,
            evidence_level=EvidenceLevel.TESTED.value,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        if rows or symbol or timeframe:
            return rows
        return self.search_knowledge(
            source_type=SourceType.QUANT_EXPERIMENT.value,
            evidence_level=EvidenceLevel.TESTED.value,
            limit=limit,
        )

    def get_topic_summary(self, topic: str, limit: int = 10) -> dict[str, Any]:
        items = self.search_knowledge(text=topic, limit=limit)
        conflicts = self.repository.conflicts_for_topic(topic)
        return {"topic": topic, "items": items, "conflicts": conflicts}

    def link_experiment(self, knowledge_id: str, experiment_id: str, relationship: str = "supports", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        item = self.get_knowledge(knowledge_id)
        if not item:
            raise KeyError("knowledge item nao encontrado")
        link_id = new_memory_id("knowledge_link")
        self.repository.add_link(link_id, knowledge_id, SourceType.QUANT_EXPERIMENT.value, experiment_id, relationship, metadata or {}, _now_iso())
        self._audit("MEMORY_LINK_CREATED", "CREATED", link_id, f"{knowledge_id}->{experiment_id}")
        return {"link_id": link_id, "knowledge_id": knowledge_id, "experiment_id": experiment_id, "relationship": relationship}

    def store_quant_experiment(self, experiment_id: str, spec: Any, result: Any, artifact_dir: str = "") -> KnowledgeItem:
        metrics = asdict(result.metrics) if hasattr(result, "metrics") else dict((result or {}).get("metrics") or {})
        dataset = asdict(spec.dataset) if hasattr(spec, "dataset") else dict((result or {}).get("dataset") or {})
        strategy = asdict(spec.strategy) if hasattr(spec, "strategy") else dict((result or {}).get("strategy") or {})
        topic = strategy.get("name") or strategy.get("description") or "experimento_quant"
        statement = (
            f"Hipotese Quant testada no experimento {experiment_id}: "
            f"net_profit={metrics.get('net_profit')}, win_rate={metrics.get('win_rate')}, "
            f"trades={metrics.get('total_trades')}."
        )
        return self.store_knowledge(
            topic=topic,
            statement=statement,
            evidence_level=EvidenceLevel.TESTED,
            source_type=SourceType.QUANT_EXPERIMENT,
            source_id=experiment_id,
            source_location=artifact_dir,
            confidence=0.75,
            validation_status=EvidenceLevel.TESTED.value,
            tags=["quant", "backtest", str(dataset.get("symbol") or "").lower(), str(dataset.get("timeframe") or "").lower()],
            metadata={
                "experiment_id": experiment_id,
                "metrics": metrics,
                "dataset": dataset,
                "strategy": strategy,
                "limitations": getattr(result, "limitations", []) if result is not None else [],
            },
        )

    def store_market_analysis(self, report: dict[str, Any], analysis_id: str) -> list[KnowledgeItem]:
        created: list[KnowledgeItem] = []
        symbol = str(report.get("symbol") or "DATASET")
        for item in report.get("observed") or []:
            created.append(self.store_knowledge(
                topic=f"{symbol} market observation",
                statement=item.get("statement", ""),
                evidence_level=EvidenceLevel.OBSERVED,
                source_type=SourceType.MARKET,
                source_id=analysis_id,
                confidence=0.7,
                validation_status=EvidenceLevel.OBSERVED.value,
                tags=["market", "observed", symbol.lower(), str(item.get("timeframe") or "").lower()],
                metadata={"symbol": symbol, "timeframe": item.get("timeframe"), "data_points": item.get("data_points", {})},
            ))
        for item in report.get("inferred") or []:
            created.append(self.store_knowledge(
                topic=f"{symbol} market regime",
                statement=f"Regime inferido: {item.get('regime')}",
                evidence_level=EvidenceLevel.INFERRED,
                source_type=SourceType.MARKET,
                source_id=analysis_id,
                confidence=float(item.get("confidence") or 0.5),
                validation_status=EvidenceLevel.INFERRED.value,
                tags=["market", "inferred", symbol.lower(), str(item.get("timeframe") or "").lower()],
                metadata={"symbol": symbol, "timeframe": item.get("timeframe"), "reasons": item.get("reasons", [])},
            ))
        for item in report.get("hypotheses") or []:
            created.append(self.store_knowledge(
                topic=f"{symbol} market hypothesis",
                statement=f"Hipotese Market: {item.get('signal')}",
                evidence_level=EvidenceLevel.HYPOTHESIS,
                source_type=SourceType.MARKET,
                source_id=analysis_id,
                confidence=0.45,
                validation_status=EvidenceLevel.HYPOTHESIS.value,
                tags=["market", "hypothesis", symbol.lower(), str(item.get("timeframe") or "").lower()],
                metadata={"symbol": symbol, "timeframe": item.get("timeframe"), "reasons": item.get("reasons", []), "risk_notes": item.get("risk_notes", [])},
            ))
        return created

    def _safe_evidence_level(self, evidence_level: EvidenceLevel | str, source_type: SourceType | str) -> EvidenceLevel:
        raw = evidence_level.value if isinstance(evidence_level, EvidenceLevel) else str(evidence_level or "")
        try:
            level = EvidenceLevel(raw)
        except ValueError:
            level = EvidenceLevel.SOURCE_CLAIM
        source = self._source_value(source_type)
        if level == EvidenceLevel.VALIDATED and source in {
            SourceType.CHAT.value,
            SourceType.FILE.value,
            SourceType.MARKET.value,
            SourceType.MEDIA.value,
            SourceType.DOCUMENT.value,
            SourceType.USER_NOTE.value,
        }:
            return EvidenceLevel.SOURCE_CLAIM if source in {SourceType.CHAT.value, SourceType.USER_NOTE.value} else EvidenceLevel.OBSERVED
        if source == SourceType.MARKET.value and level == EvidenceLevel.VALIDATED:
            return EvidenceLevel.HYPOTHESIS
        if source == SourceType.QUANT_EXPERIMENT.value and level == EvidenceLevel.VALIDATED:
            return EvidenceLevel.TESTED
        return level

    def _source_value(self, source_type: SourceType | str) -> str:
        return source_type.value if isinstance(source_type, SourceType) else str(source_type or SourceType.SYSTEM.value)

    def _evidence_type_for(self, level: EvidenceLevel) -> EvidenceType:
        return {
            EvidenceLevel.SOURCE_CLAIM: EvidenceType.SOURCE_CLAIM,
            EvidenceLevel.OBSERVED: EvidenceType.OBSERVATION,
            EvidenceLevel.INFERRED: EvidenceType.INFERENCE,
            EvidenceLevel.HYPOTHESIS: EvidenceType.HYPOTHESIS,
            EvidenceLevel.TESTED: EvidenceType.TEST_RESULT,
            EvidenceLevel.VALIDATED: EvidenceType.VERIFIED_RESULT,
        }[level]

    def _detect_and_record_conflicts(self, item: KnowledgeItem) -> None:
        candidates = self.repository.search(topic=item.topic, limit=50, include_archived=True)
        new_sign = self._statement_sign(item.statement, item.metadata)
        if not new_sign:
            return
        for candidate in candidates:
            if candidate["knowledge_id"] == item.knowledge_id:
                continue
            old_sign = self._statement_sign(candidate.get("statement", ""), candidate.get("metadata", {}))
            if old_sign and old_sign != new_sign:
                self.repository.add_conflict(
                    new_memory_id("conflict"),
                    item.topic,
                    candidate["knowledge_id"],
                    item.knowledge_id,
                    "statements_or_metrics_indicate_opposite_outcomes",
                    _now_iso(),
                )
                self._audit("MEMORY_CONFLICT_DETECTED", "DETECTED", item.topic, f"{candidate['knowledge_id']} vs {item.knowledge_id}")

    def _statement_sign(self, statement: str, metadata: dict[str, Any]) -> str:
        metrics = metadata.get("metrics") if isinstance(metadata, dict) else {}
        if isinstance(metrics, dict) and isinstance(metrics.get("net_profit"), (int, float)):
            if metrics["net_profit"] > 0:
                return "positive"
            if metrics["net_profit"] < 0:
                return "negative"
        text = str(statement or "").lower()
        positive = ("ganha", "positivo", "lucr", "expectativa positiva", "win rate 80", "80%")
        negative = ("perde", "negativo", "preju", "reprov", "expectativa negativa")
        has_pos = any(token in text for token in positive)
        has_neg = any(token in text for token in negative)
        if has_pos and not has_neg:
            return "positive"
        if has_neg and not has_pos:
            return "negative"
        return ""
