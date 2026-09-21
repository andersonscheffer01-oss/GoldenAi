"""Semantic research-level classification for the existing orchestrator."""

import re
import time
from dataclasses import dataclass
from enum import Enum

from .models import DataClassification, Route


class ResearchLevel(str, Enum):
    NO_RESEARCH = "NO_RESEARCH"
    ASSISTED_RESEARCH = "ASSISTED_RESEARCH"
    DEEP_RESEARCH = "DEEP_RESEARCH"


class ResearchReason(str, Enum):
    CURRENT_INFORMATION_REQUIRED = "CURRENT_INFORMATION_REQUIRED"
    EXTERNAL_DOCUMENTATION_REQUIRED = "EXTERNAL_DOCUMENTATION_REQUIRED"
    LOCAL_DATA_SUFFICIENT = "LOCAL_DATA_SUFFICIENT"
    USER_EXPLICITLY_REQUESTED_RESEARCH = "USER_EXPLICITLY_REQUESTED_RESEARCH"
    MULTI_SOURCE_COMPARISON_REQUIRED = "MULTI_SOURCE_COMPARISON_REQUIRED"
    GENERAL_KNOWLEDGE_SUFFICIENT = "GENERAL_KNOWLEDGE_SUFFICIENT"
    SECRET_LOCAL_ONLY = "SECRET_LOCAL_ONLY"


@dataclass(frozen=True)
class ResearchDecision:
    level: ResearchLevel
    reason: ResearchReason
    latency_ms: int = 0

    @property
    def required(self):
        return self.level != ResearchLevel.NO_RESEARCH


class IntelligentResearchRouter:
    """Classify need for research; it never executes tools or providers."""

    _DEEP = re.compile(
        r"\b(pesquise tudo|pesquisa completa|an[aá]lise completa|relat[oó]rio completo|"
        r"an[aá]lise profunda|compare (?:as )?(?:melhores|principais)|m[uú]ltiplas fontes|"
        r"melhor arquitetura atual|decis[oõ]es do fed|bancos centrais)\b", re.I)
    _EXPLICIT = re.compile(
        r"\b(pesquise|pesquisar|procure na internet|veja fontes|confira online|"
        r"verifique na web|veja na web|documenta[cç][aã]o atual)\b", re.I)
    _CURRENT = re.compile(
        r"\b(agora|atual|atuais|hoje|recente|recentes|[uú]ltim[ao]s?|not[ií]cias|"
        r"cota[cç][aã]o|pre[cç]o|calend[aá]rio|vers[aã]o mais nova|vulnerabilidade|"
        r"regulamenta[cç][aã]o|compatibilidade)\b", re.I)
    _EXTERNAL_DOCS = re.compile(
        r"\b(documenta[cç][aã]o|recomenda[cç][oõ]es?|fabricante|vendor|microsoft|amd|"
        r"nvidia|python docs|standard|especifica[cç][aã]o|driver)\b", re.I)
    _LOCAL = re.compile(
        r"\b(meu|minha|neste|nesse|nosso|pc|computador|m[aá]quina|sistema|gpu|"
        r"placa|temperatura|mem[oó]ria|ram|disco|processos?)\b", re.I)
    _LOCAL_DIAGNOSTIC = re.compile(
        r"\b(pesad[oa]|lent[oa]|travando|status|sa[uú]de|diagn[oó]stico|"
        r"temperatura|uso|consumindo|espa[cç]o livre)\b", re.I)
    _LOCAL_NEEDS_REFERENCE = re.compile(
        r"\b(temperatura|driver|erro|falha)\b.*\b(normal|segur[ao]|recomendad[ao]|"
        r"significa|limite)|\b(normal|segur[ao]|recomendad[ao]|limite)\b.*"
        r"\b(temperatura|driver)\b", re.I)

    def decide(self, text, classification=DataClassification.INTERNAL):
        started = time.perf_counter()
        value = str(text or "").strip()
        if classification == DataClassification.SECRET:
            level, reason = ResearchLevel.NO_RESEARCH, ResearchReason.SECRET_LOCAL_ONLY
        elif self._DEEP.search(value):
            level, reason = (ResearchLevel.DEEP_RESEARCH,
                             ResearchReason.MULTI_SOURCE_COMPARISON_REQUIRED)
        elif self._EXPLICIT.search(value):
            level, reason = (ResearchLevel.ASSISTED_RESEARCH,
                             ResearchReason.USER_EXPLICITLY_REQUESTED_RESEARCH)
        elif self._LOCAL.search(value) and self._LOCAL_NEEDS_REFERENCE.search(value):
            level, reason = (ResearchLevel.ASSISTED_RESEARCH,
                             ResearchReason.EXTERNAL_DOCUMENTATION_REQUIRED)
        elif self._LOCAL.search(value) and self._LOCAL_DIAGNOSTIC.search(value) \
                and not self._EXTERNAL_DOCS.search(value):
            level, reason = (ResearchLevel.NO_RESEARCH,
                             ResearchReason.LOCAL_DATA_SUFFICIENT)
        elif self._CURRENT.search(value):
            level, reason = (ResearchLevel.ASSISTED_RESEARCH,
                             ResearchReason.CURRENT_INFORMATION_REQUIRED)
        elif self._EXTERNAL_DOCS.search(value):
            level, reason = (ResearchLevel.ASSISTED_RESEARCH,
                             ResearchReason.EXTERNAL_DOCUMENTATION_REQUIRED)
        else:
            level, reason = (ResearchLevel.NO_RESEARCH,
                             ResearchReason.GENERAL_KNOWLEDGE_SUFFICIENT)
        return ResearchDecision(level, reason,
                                int((time.perf_counter() - started) * 1000))

    @staticmethod
    def answer_route(route, steps, decision):
        tools = [step.tool for step in steps if step.tool]
        research = any(tool in {"web_research", "web_research_learn"} for tool in tools)
        local = any(tool not in {"web_research", "web_research_learn"} for tool in tools)
        if decision.level == ResearchLevel.DEEP_RESEARCH:
            return "DEEP_RESEARCH"
        if research and local:
            return "TOOL_PLUS_RESEARCH"
        if research:
            return "ASSISTED_RESEARCH"
        if tools:
            return "TOOL_ONLY"
        return "LLM_ONLY" if route == Route.CONVERSATION else "DIRECT"
