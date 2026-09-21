from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    confidence: float
    execution_requested: bool
    target: str = ""
    negated: bool = False
    future_reference: bool = False
    question_only: bool = False
    reason_code: str = "GENERAL_CONVERSATION"


class IntentRouter:
    def classify_coding_change(self, prompt: str, active_coding_task: bool = False) -> IntentDecision:
        text = self._normalize(prompt)
        if not text.strip():
            return IntentDecision("GENERAL_CONVERSATION", 0.0, False, reason_code="EMPTY")

        if self._is_negated(text):
            return IntentDecision("GENERAL_CONVERSATION", 0.98, False, negated=True, reason_code="NEGATED_CHANGE")
        if self._is_read_only(text):
            return IntentDecision("GENERAL_CONVERSATION", 0.96, False, reason_code="READ_ONLY_REQUEST")
        if self._is_question_only(text):
            return IntentDecision("GENERAL_CONVERSATION", 0.9, False, question_only=True, reason_code="QUESTION_ONLY")
        if self._is_self_or_future_statement(text):
            return IntentDecision("GENERAL_CONVERSATION", 0.92, False, future_reference=True, reason_code="FUTURE_OR_SELF_STATEMENT")
        if self._is_coding_continuation(text):
            if active_coding_task:
                return IntentDecision("CODING_CHANGE", 0.82, True, target="ACTIVE_TASK", reason_code="ACTIVE_TASK_CONTINUATION")
            return IntentDecision("GENERAL_CONVERSATION", 0.72, False, reason_code="CONTINUATION_WITHOUT_ACTIVE_TASK")
        if self._is_explicit_change_request(text):
            return IntentDecision("CODING_CHANGE", 0.9, True, target=self._target_for(text), reason_code="EXPLICIT_CHANGE_REQUEST")
        if self._is_discussion_about_problem(text):
            return IntentDecision("GENERAL_CONVERSATION", 0.72, False, reason_code="DISCUSSION_ONLY")
        return IntentDecision("GENERAL_CONVERSATION", 0.62, False, reason_code="NO_EXECUTION_REQUEST")

    def _normalize(self, prompt: str) -> str:
        text = str(prompt or "").lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", text).strip()

    def _is_negated(self, text: str) -> bool:
        return bool(re.search(r"\b(nao|nunca|jamais)\s+(?:altere|alterar|modifique|modificar|mexa|corrija|corrigir|arrume|arrumar|edite|editar)\b", text)) or any(
            term in text for term in ("sem alterar", "sem modificar", "nao mexa", "nao corrija")
        )

    def _is_read_only(self, text: str) -> bool:
        return any(term in text for term in ("apenas analise", "somente analise", "so analise", "somente leia", "apenas leia", "somente leitura", "sem editar"))

    def _is_question_only(self, text: str) -> bool:
        return "?" in text or bool(re.search(r"\b(voce consegue|consegue|pode|da para|seria possivel)\s+(?:corrigir|alterar|arrumar|modificar|editar)\b", text))

    def _is_self_or_future_statement(self, text: str) -> bool:
        if re.search(r"\b(eu|nos|a gente)\s+(?:vou|vamos|irei|iremos|posso|podemos)\s+(?:corrigir|alterar|arrumar|melhorar|modificar|ajustar|criar)\b", text):
            return True
        if re.search(r"\b(?:depois|futuramente|quando|mais tarde|amanha)\b.*\b(?:corrigir|alterar|arrumar|melhorar|modificar|ajustar)\b", text):
            return True
        if re.search(r"\b(?:precisa|deve|deveria|tera que|tem que)\s+ser\s+(?:corrigido|alterado|arrumado|melhorado)\b", text):
            return True
        if "estou criando voce" in text or "criando voce" in text:
            return True
        return False

    def _is_coding_continuation(self, text: str) -> bool:
        return bool(re.search(r"\b(e tambem|tambem|alem disso)\s+(?:ajuste|corrija|altere|arrume|modifique)\b", text))

    def _is_explicit_change_request(self, text: str) -> bool:
        imperative = (
            r"\b(corrija|arrume|altere|modifique|edite|implemente|refatore|ajuste|melhore)\b"
            r".*\b(esse|este|esta|essa|codigo|arquivo|funcao|classe|modulo|projeto|robo|teste|testes|erro|bug|selecionado)\b"
        )
        object_first = (
            r"\b(codigo|arquivo|funcao|classe|modulo|projeto|robo|teste|testes|erro|bug)\b"
            r".*\b(corrija|arrume|altere|modifique|edite|implemente|refatore|ajuste)\b"
        )
        direct_file = r"\b(corrija|arrume|altere|modifique|edite|implemente|refatore|ajuste)\b.*\.(py|mq5|mqh|json|csv|md|txt)\b"
        return bool(re.search(imperative, text) or re.search(object_first, text) or re.search(direct_file, text))

    def _is_discussion_about_problem(self, text: str) -> bool:
        return any(term in text for term in ("precisa ser", "depois vamos", "quando terminarmos", "estou criando", "vou corrigir"))

    def _target_for(self, text: str) -> str:
        if "projeto" in text or "testes" in text:
            return "PROJECT"
        if "arquivo" in text or "selecionado" in text or "codigo" in text:
            return "FILE"
        return "UNSPECIFIED"
