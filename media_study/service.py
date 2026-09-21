from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.memory import ScientificMemoryService
from core.permissions import PermissionManager
from core.safety import classify_content_source

from .models import (
    ClaimKind,
    MediaDocument,
    MediaSegment,
    MediaSource,
    MediaSourceType,
    MediaStudy,
    SourceClaim,
    StudyResult,
    TestableHypothesis,
    deterministic_hash,
    new_id,
    now_iso,
)
from .repository import MediaStudyRepository


TEXT_EXTENSIONS = {".txt", ".md", ".srt", ".vtt", ".log"}
PROMPT_INJECTION_MARKERS = (
    "ignore suas regras",
    "ignore previous instructions",
    "apague c:\\goldenai",
    "execute este comando",
    "powershell",
    "delete",
    "remove-item",
)


class MediaStudyService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.repository = MediaStudyRepository(self.root)
        self.permission_manager = PermissionManager()
        self.audit = AuditLogger(self.root / "logs")
        self.memory = ScientificMemoryService(self.root)
        self.current_source_id: str | None = None
        self.previous_source_id: str | None = None

    def _audit(self, action_type: str, status: str, target: str = "", detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "media_study.v1",
            "target": target,
            "result": str(detail or "")[:1000],
            "files_changed": [],
            "commands_executed": [],
        })

    def import_media(self, path: str, source_type: str) -> MediaStudy:
        source = Path(path)
        return MediaStudy(
            study_id=source.stem,
            source_path=str(source),
            source_type=source_type,
            trust_classification=classify_content_source(source_type),
        )

    def ingest_source(
        self,
        path: str,
        source_type: str = "",
        title: str = "",
        author: str = "",
        language: str = "",
        source_date: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_path = Path(path).resolve()
        decision = self.permission_manager.can_read(source_path)
        if not decision.allowed:
            self._audit("MEDIA_SOURCE_INGEST_FAILED", "DENIED", str(source_path), decision.reason)
            return {"ok": False, "erro": decision.reason}
        if not source_path.exists() or not source_path.is_file():
            return {"ok": False, "erro": "fonte local nao encontrada"}
        if source_path.suffix.lower() not in TEXT_EXTENSIONS:
            return {"ok": False, "erro": "Media Study V1 aceita apenas .txt, .md, .srt, .vtt e texto local simples"}

        source_type = source_type or self._type_from_extension(source_path.suffix)
        source_hash = self._hash_file(source_path)
        duplicate = self.repository.find_source_by_hash(source_hash, str(source_path))
        if duplicate:
            self.previous_source_id = self.current_source_id
            self.current_source_id = duplicate["source_id"]
            return {"ok": True, "duplicate": True, "source": duplicate, "segments": self.repository.get_segments(duplicate["source_id"])}

        text = source_path.read_text(encoding="utf-8-sig", errors="replace")
        source = MediaSource(
            source_id=new_id("media_source"),
            source_type=source_type,
            title=title or source_path.stem,
            origin=str(source_path),
            author=author,
            source_date=source_date,
            language=language,
            source_hash=source_hash,
            metadata=metadata or {},
        )
        document = MediaDocument(
            document_id=new_id("media_document"),
            source_id=source.source_id,
            content_hash=deterministic_hash(text),
            text_length=len(text),
            line_count=len(text.splitlines()),
            metadata={"extension": source_path.suffix.lower()},
        )
        segments = self._segment_text(source.source_id, text, source_path.suffix.lower())
        self.repository.save_source(source, document, segments)
        self.previous_source_id = self.current_source_id
        self.current_source_id = source.source_id
        self._audit("MEDIA_SOURCE_INGESTED", "COMPLETED", source.source_id, f"segments={len(segments)}; hash={source_hash}")
        return {"ok": True, "duplicate": False, "source": asdict(source), "segments": [asdict(item) for item in segments]}

    def get_source(self, source_id: str = "") -> dict[str, Any] | None:
        source_id = source_id or self.current_source_id or ""
        return self.repository.get_source(source_id) if source_id else None

    def list_sources(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.repository.list_sources(limit)

    def get_segments(self, source_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
        source_id = source_id or self.current_source_id or ""
        return self.repository.get_segments(source_id, limit) if source_id else []

    def search_source(self, query: str, source_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        source_id = source_id or self.current_source_id or ""
        rows = self.repository.search_segments(source_id, query, limit)
        self._audit("MEDIA_SOURCE_SEARCHED", "COMPLETED", source_id, f"query={query}; count={len(rows)}")
        return rows

    def extract_claims(self, source_id: str = "") -> list[dict[str, Any]]:
        source_id = source_id or self.current_source_id or ""
        if not source_id:
            return []
        segments = self.repository.get_segments(source_id)
        claims: list[SourceClaim] = []
        for segment in segments:
            claims.extend(self._claims_from_segment(segment))
        self.repository.save_claims(claims)
        for claim in claims:
            self._audit("MEDIA_CLAIM_CREATED", "CREATED", claim.claim_id, claim.claim_kind)
        return [asdict(item) for item in claims]

    def get_claims(self, source_id: str = "", claim_id: str = "") -> list[dict[str, Any]]:
        source_id = source_id or self.current_source_id or ""
        return self.repository.get_claims(source_id, claim_id)

    def study_source(self, source_id: str = "") -> dict[str, Any]:
        source_id = source_id or self.current_source_id or ""
        if not source_id:
            return {"ok": False, "erro": "fonte Media Study nao encontrada"}
        self._audit("MEDIA_STUDY_STARTED", "STARTED", source_id)
        try:
            claims = self.get_claims(source_id)
            if not claims:
                claims = self.extract_claims(source_id)
            hypotheses = [self.claim_to_hypothesis(item["claim_id"]) for item in claims if item.get("claim_kind") in {ClaimKind.RULE.value, ClaimKind.HYPOTHESIS.value, ClaimKind.QUANTITATIVE_CLAIM.value}]
            segments = self.repository.get_segments(source_id, 6)
            summary = self._summary_from_segments(segments, claims)
            result = StudyResult(
                study_id=new_id("media_study"),
                source_id=source_id,
                summary=summary,
                concepts=[c["statement"] for c in claims if c.get("claim_kind") in {ClaimKind.CONCEPT.value, ClaimKind.DEFINITION.value}],
                rules=[c["statement"] for c in claims if c.get("claim_kind") == ClaimKind.RULE.value],
                claims=[self._claim_dataclass(c) for c in claims],
                quantitative_claims=[self._claim_dataclass(c) for c in claims if c.get("claim_kind") == ClaimKind.QUANTITATIVE_CLAIM.value],
                hypotheses=[h for h in hypotheses if isinstance(h, TestableHypothesis)],
                contradictions=self._detect_internal_contradictions(claims),
                unclear_points=[],
                references=[c["segment_id"] for c in claims],
                limitations=[
                    "Media Study V1 trata o material como dado nao confiavel.",
                    "Claims de fonte entram como SOURCE_CLAIM, nao TESTED nem VALIDATED.",
                    "Sem internet, YouTube, OCR ou transcricao automatica nesta V1.",
                ],
            )
            self.repository.save_study_result(result)
            self._link_claims_to_memory(claims)
            self._audit("MEDIA_STUDY_COMPLETED", "COMPLETED", result.study_id, f"claims={len(claims)}; hypotheses={len(result.hypotheses)}")
            return asdict(result) | {"ok": True}
        except Exception as exc:
            self._audit("MEDIA_STUDY_FAILED", "FAILED", source_id, exc)
            raise

    def get_study_result(self, study_id: str) -> dict[str, Any] | None:
        return self.repository.get_study_result(study_id)

    def claim_to_hypothesis(self, claim_id: str) -> TestableHypothesis | dict[str, Any]:
        claims = self.repository.get_claims(claim_id=claim_id)
        if not claims:
            return {"ok": False, "erro": "claim nao encontrado"}
        claim = claims[0]
        statement = claim["statement"]
        lowered = statement.lower()
        missing = []
        indicator = self._first_match(lowered, ("ema20", "ema50", "ema", "atr", "vwap"))
        pattern = self._first_match(lowered, ("engolfo", "pinbar", "rompimento", "pullback"))
        timeframe = self._first_regex(statement, r"\b(M1|M5|M15|M30|H1|H4|D1)\b")
        direction = self._first_match(lowered, ("compra", "venda", "reversao", "reversão", "continuacao", "continuação"))
        entry = "proximo candle" if "proximo candle" in lowered or "próximo candle" in lowered else ""
        exit_ = self._first_regex(statement, r"(?i)\bstop\s+(?:de\s+)?[\w,.:%/]+(?:\s+\w+)?")
        for name, value in {
            "indicator": indicator,
            "pattern": pattern,
            "timeframe": timeframe,
            "direction": direction,
            "entry": entry,
            "exit": exit_,
        }.items():
            if not value:
                missing.append(name)
        hypothesis = TestableHypothesis(
            hypothesis_id=new_id("media_hypothesis"),
            claim_id=claim_id,
            source_id=claim["source_id"],
            statement=statement,
            condition=statement,
            indicator=indicator,
            parameter=self._first_regex(statement, r"\b\d+(?:[,.]\d+)?\s*(?:%|pontos?|pts?|:1)\b"),
            pattern=pattern,
            direction=direction,
            entry=entry,
            exit=exit_,
            timeframe=timeframe,
            missing_fields=missing,
            status="NOT_TESTED",
            metadata={"quant_auto_executed": False},
        )
        self.repository.save_hypothesis(hypothesis)
        self._audit("MEDIA_HYPOTHESIS_CREATED", "CREATED", hypothesis.hypothesis_id, "NOT_TESTED")
        return hypothesis

    def get_claim_origin(self, claim_id: str) -> dict[str, Any]:
        claims = self.repository.get_claims(claim_id=claim_id)
        if not claims:
            return {"ok": False, "erro": "claim nao encontrado"}
        claim = claims[0]
        source = self.repository.get_source(claim["source_id"])
        segment = [s for s in self.repository.get_segments(claim["source_id"]) if s["segment_id"] == claim["segment_id"]]
        return {"claim": claim, "source": source, "segment": segment[0] if segment else None}

    def abandon_current_context(self) -> None:
        self.previous_source_id = self.current_source_id
        self.current_source_id = None

    def restore_previous_context(self) -> str | None:
        if self.previous_source_id:
            self.current_source_id = self.previous_source_id
        return self.current_source_id

    def transcribe(self, study_id: str):
        raise NotImplementedError("Transcription is planned but not enabled in Media Study V1.")

    def analyze_visuals(self, study_id: str):
        raise NotImplementedError("Visual analysis is planned but not enabled in Media Study V1.")

    def fuse_timeline(self, study_id: str):
        raise NotImplementedError("Timeline fusion is planned but not enabled in Media Study V1.")

    def extract_knowledge(self, study_id: str):
        return self.study_source(study_id)

    def validate_claims(self, study_id: str):
        raise NotImplementedError("Claim validation is planned but not enabled in Media Study V1.")

    def save_to_memory(self, study_id: str):
        return self.study_source(study_id)

    def search_knowledge(self, query: str):
        return self.search_source(query)

    def build_strategy_spec(self, study_id: str):
        raise NotImplementedError("StrategySpec bridge is conceptual in Media Study V1 and does not run Quant automatically.")

    def _type_from_extension(self, suffix: str) -> str:
        return {
            ".txt": MediaSourceType.TEXT.value,
            ".md": MediaSourceType.DOCUMENT.value,
            ".srt": MediaSourceType.SRT.value,
            ".vtt": MediaSourceType.VTT.value,
        }.get(suffix.lower(), MediaSourceType.TEXT.value)

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().upper()

    def _segment_text(self, source_id: str, text: str, suffix: str) -> list[MediaSegment]:
        if suffix == ".srt":
            return self._segments_from_srt(source_id, text)
        if suffix == ".vtt":
            return self._segments_from_vtt(source_id, text)
        return self._segments_from_plain_text(source_id, text)

    def _segments_from_plain_text(self, source_id: str, text: str) -> list[MediaSegment]:
        lines = text.splitlines()
        segments: list[MediaSegment] = []
        chunk: list[str] = []
        start_line = 1
        order = 0
        for index, line in enumerate(lines, start=1):
            if not chunk:
                start_line = index
            chunk.append(line)
            joined = "\n".join(chunk).strip()
            if len(joined) >= 900 or len(chunk) >= 12:
                if joined:
                    segments.append(self._segment(source_id, order, joined, line_start=start_line, line_end=index))
                    order += 1
                chunk = []
        joined = "\n".join(chunk).strip()
        if joined or not segments:
            segments.append(self._segment(source_id, order, joined, line_start=start_line, line_end=len(lines) or 1))
        return segments

    def _segments_from_srt(self, source_id: str, text: str) -> list[MediaSegment]:
        blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
        segments: list[MediaSegment] = []
        for order, block in enumerate(blocks):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            time_line = next((line for line in lines if "-->" in line), "")
            body = "\n".join(line for line in lines if line != time_line and not line.isdigit()).strip()
            start, end = self._parse_time_range(time_line)
            segments.append(self._segment(source_id, order, body, start_time=start, end_time=end, metadata={"format": "srt"}))
        return segments

    def _segments_from_vtt(self, source_id: str, text: str) -> list[MediaSegment]:
        clean = re.sub(r"^\ufeff?WEBVTT.*?\n", "", text.replace("\r\n", "\n"), count=1, flags=re.I | re.S).strip()
        blocks = re.split(r"\n\s*\n", clean)
        segments: list[MediaSegment] = []
        for order, block in enumerate(blocks):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            time_line = next((line for line in lines if "-->" in line), "")
            body = "\n".join(line for line in lines if line != time_line).strip()
            start, end = self._parse_time_range(time_line)
            segments.append(self._segment(source_id, order, body, start_time=start, end_time=end, metadata={"format": "vtt"}))
        return segments

    def _segment(self, source_id: str, order: int, text: str, start_time: str = "", end_time: str = "", line_start: int | None = None, line_end: int | None = None, metadata: dict[str, Any] | None = None) -> MediaSegment:
        return MediaSegment(
            segment_id=new_id("media_segment"),
            source_id=source_id,
            order_index=order,
            text=text,
            start_time=start_time,
            end_time=end_time,
            line_start=line_start,
            line_end=line_end,
            segment_hash=deterministic_hash({"source_id": source_id, "order": order, "text": text, "start": start_time, "end": end_time, "line_start": line_start, "line_end": line_end}),
            metadata=metadata or {},
        )

    def _parse_time_range(self, text: str) -> tuple[str, str]:
        if "-->" not in text:
            return "", ""
        left, right = text.split("-->", 1)
        return left.strip(), right.split()[0].strip()

    def _claims_from_segment(self, segment: dict[str, Any]) -> list[SourceClaim]:
        pieces = re.split(r"(?<=[.!?])\s+|\n+", segment.get("text", ""))
        claims = []
        for piece in pieces:
            statement = piece.strip(" -\t")
            if len(statement) < 12:
                continue
            kind = self._classify_claim(statement)
            if not kind:
                continue
            numbers = re.findall(r"\b\d+(?:[,.]\d+)?\s*(?:%|pontos?|pts?|:1)?", statement, flags=re.I)
            units = [u for u in ("%", "pontos", "pts", "RR", "EMA20", "EMA50", "M15", "M5", "H1") if u.lower() in statement.lower()]
            tags = self._claim_tags(statement, kind)
            claims.append(SourceClaim(
                claim_id=new_id("media_claim"),
                source_id=segment["source_id"],
                segment_id=segment["segment_id"],
                statement=statement,
                claim_kind=kind.value,
                timestamp_start=segment.get("start_time", ""),
                timestamp_end=segment.get("end_time", ""),
                line_start=segment.get("line_start"),
                line_end=segment.get("line_end"),
                confidence=0.55,
                numbers=numbers,
                units=units,
                tags=tags,
                metadata={"untrusted_source_content": True, "prompt_injection_like": self._contains_prompt_injection(statement)},
            ))
        return claims

    def _classify_claim(self, statement: str) -> ClaimKind | None:
        text = statement.lower()
        if any(token in text for token in PROMPT_INJECTION_MARKERS):
            return ClaimKind.PROCEDURE
        if re.search(r"\b\d+(?:[,.]\d+)?\s*(?:%|pontos?|pts?|:1)\b", statement, flags=re.I):
            return ClaimKind.QUANTITATIVE_CLAIM
        if any(token in text for token in ("quando", "entrar", "entrada", "stop", "alvo", "buscar", "usar", "regra")):
            return ClaimKind.RULE
        if any(token in text for token in ("afirma", "funciona", "ganha", "melhor", "possui", "alta taxa")):
            return ClaimKind.HYPOTHESIS
        if any(token in text for token in ("define", "significa", "e um", "é um")):
            return ClaimKind.DEFINITION
        return None

    def _claim_tags(self, statement: str, kind: ClaimKind) -> list[str]:
        text = statement.lower()
        tags = [kind.value.lower()]
        for token in ("ema20", "ema50", "ema", "atr", "vwap", "engolfo", "stop", "rr", "m15", "m5", "h1"):
            if token in text:
                tags.append(token)
        return sorted(set(tags))

    def _contains_prompt_injection(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in PROMPT_INJECTION_MARKERS)

    def _summary_from_segments(self, segments: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
        return f"Fonte estudada com {len(segments)} segmentos iniciais carregados e {len(claims)} claims estruturados. Conteudo tratado como dado nao confiavel."

    def _claim_dataclass(self, data: dict[str, Any]) -> SourceClaim:
        return SourceClaim(
            claim_id=data["claim_id"],
            source_id=data["source_id"],
            segment_id=data["segment_id"],
            statement=data["statement"],
            claim_kind=data["claim_kind"],
            evidence_level=data["evidence_level"],
            timestamp_start=data.get("timestamp_start", ""),
            timestamp_end=data.get("timestamp_end", ""),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            confidence=data.get("confidence", 0.5),
            numbers=data.get("numbers", []),
            units=data.get("units", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", now_iso()),
        )

    def _link_claims_to_memory(self, claims: list[dict[str, Any]]) -> None:
        for claim in claims:
            item = self.memory.store_knowledge(
                topic=claim["statement"][:80],
                statement=claim["statement"],
                evidence_level="SOURCE_CLAIM",
                source_type="MEDIA",
                source_id=claim["source_id"],
                source_location=claim["segment_id"],
                confidence=claim.get("confidence", 0.5),
                validation_status="SOURCE_CLAIM",
                tags=claim.get("tags", []),
                metadata={
                    "claim_id": claim["claim_id"],
                    "segment_id": claim["segment_id"],
                    "timestamp_start": claim.get("timestamp_start", ""),
                    "timestamp_end": claim.get("timestamp_end", ""),
                    "line_start": claim.get("line_start"),
                    "line_end": claim.get("line_end"),
                    "numbers": claim.get("numbers", []),
                    "units": claim.get("units", []),
                    "untrusted_source_content": True,
                },
            )
            self._audit("MEDIA_MEMORY_LINKED", "COMPLETED", claim["claim_id"], item.knowledge_id)

    def _detect_internal_contradictions(self, claims: list[dict[str, Any]]) -> list[str]:
        all_claims = self.repository.get_claims()
        statements = " ".join(c.get("statement", "") for c in [*all_claims, *claims]).lower()
        contradictions = []
        if "ema20" in statements and "ema50" in statements and "melhor" in statements:
            contradictions.append("Ha claims potencialmente conflitantes sobre EMA20/EMA50; nao foi escolhido vencedor.")
        return contradictions

    def _first_match(self, text: str, options: tuple[str, ...]) -> str:
        for option in options:
            if option in text:
                return option.upper() if option.startswith("ema") or option in {"atr", "vwap"} else option
        return ""

    def _first_regex(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text, flags=re.I)
        return match.group(0) if match else ""
