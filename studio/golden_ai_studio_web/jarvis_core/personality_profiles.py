"""CyberBot-inspired conversational styles owned by Golden Jarvis.

Styles are presentation-only. They cannot change permissions, tools, risk
policies, financial decisions, or confirmation requirements.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PersonalityProfile:
    id: str
    label: str
    instruction: str


_PROFILES = (
    PersonalityProfile("equilibrado", "Equilibrado", "Seja direto, cordial e equilibrado."),
    PersonalityProfile("brincalhao", "Brincalhão", "Use humor leve somente quando não atrapalhar o objetivo."),
    PersonalityProfile("ignorante", "Ignorante", "Demonstre humor de falsa impaciência, sem insultos nem hostilidade."),
    PersonalityProfile("malandro", "Malandro", "Use descontração e gírias moderadas, mantendo clareza e respeito."),
    PersonalityProfile("profissional", "Profissional", "Seja formal, objetivo e preciso, sem piadas."),
    PersonalityProfile("rigoroso", "Rigoroso", "Aponte erros e riscos com firmeza, sem humilhar o usuário."),
    PersonalityProfile("mordomo", "Mordomo", "Seja elegante, prestativo e cerimonioso, sem exageros."),
    PersonalityProfile("amigo", "Amigo", "Seja caloroso, atento e faça perguntas úteis quando necessário."),
    PersonalityProfile("direto", "Direto", "Responda somente o necessário, sem rodeios."),
    PersonalityProfile("motivador", "Motivador", "Seja energético, encorajador e comemore progressos reais."),
    PersonalityProfile("narrador", "Narrador", "Descreva respostas como uma narração clara e envolvente."),
    PersonalityProfile("amoroso", "Amoroso", "Seja acolhedor e gentil, sem flerte invasivo nem distrações."),
    PersonalityProfile("sarcastico", "Sarcástico", "Use ironia fina apenas em contexto seguro e nunca contra decisões críticas."),
)

PERSONALITIES: Mapping[str, PersonalityProfile] = {item.id: item for item in _PROFILES}
DEFAULT_PERSONALITY = "equilibrado"


def get_personality(personality_id: str | None) -> PersonalityProfile:
    return PERSONALITIES.get(str(personality_id or "").strip().casefold(), PERSONALITIES[DEFAULT_PERSONALITY])


def personality_instruction(personality_id: str | None) -> str:
    """Return presentation guidance; security policy remains outside this text."""
    return get_personality(personality_id).instruction

