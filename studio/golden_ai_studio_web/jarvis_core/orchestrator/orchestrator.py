import os
import re
import time
from dataclasses import asdict, replace

from .models import (DataClassification, ModelProfile, OrchestratorDecision,
                     PlanStep, Route)
from .policies import SECRET_MARKERS
from .skills_router import SkillsRouter
from .model_router import ModelRouter
from .research_router import IntelligentResearchRouter, ResearchLevel


# ═══════════════════════════════════════════════════════════════
# SHARED CONCEPTUAL CLASSIFIER
# Single source of truth used by service._parse() AND orchestrator._route()
# ═══════════════════════════════════════════════════════════════
_CONCEPTUAL_RE = re.compile(
    r"(?:me\s+)?(?:explique|explica|explicar|descreva|descrever|defina|definir|entenda|entender)\s|"
    r"(?:o\s+)?(?:que\s+(?:é|e|significa|representa|quer\s+dizer))\s|"
    r"(?:como\s+(?:funciona|funcionam|se\s+us[ao]| opera))\s|"
    r"(?:para\s+(?:que\s+serve|que\s+servem))\s|"
    r"(?:qual\s+(?:é|e)\s+(?:a\s+)?(?:fun[çc][aã]o|diferen[çc]a|objetivo|papel|vantagem|utilidade))\s|"
    r"(?:qual\s+a\s+diferen[çc]a)\s",
    re.IGNORECASE,
)
_OPERATIONAL_RE = re.compile(
    r"(?:quanto\s+(?:de|está|esta|tem|uso|consome)|"
    r"como\s+(?:está|esta|vai|está\s+sendo|esta\s+sendo)|"
    r"verifique|verifica|checque|checa|monitore|monitora|"
    r"status|saúde|saude|diagnóstico|diagnostico|"
    r"liste|listar|mostre|mostre|exiba|exibir|"
    r"abrir|abra|abre|fechar|feche|fechar|"
    r"execute|executar| rode|iniciar|inicia|"
    r"desligar|desligue|desliga|reiniciar|reinicia|"
    r"agora|atual|imediatamente|hoje|agora\s+mesmo|"
    r"est[áa]|usa[dn]?o|consumindo|rodando|"
    r"aberto|dispon[íi]vel|n[úu]mero|"
    r"check|informe|mostrar|qual\s+o)",
    re.IGNORECASE,
)


def is_conceptual_query(text):
    """Return True if text is a conceptual/explanatory question (not operational).

    Shared classifier used by both JarvisService._parse() and
    CentralOrchestrator._route() to avoid duplication.

    Examples:
        "me explique o que significa CPU" → True  (conceptual)
        "qual o uso da CPU agora?"       → False (operational)
        "para que serve RAM?"            → True  (conceptual)
        "quanto de RAM estou usando?"    → False (operational)
    """
    low = str(text or "").lower().strip()
    if not low:
        return False
    if _CONCEPTUAL_RE.search(low) and not _OPERATIONAL_RE.search(low):
        return True
    return False


class CentralOrchestrator:
    VALID_MODES = {"off", "shadow", "on"}

    def __init__(self, registry, audit=None, mode=None, model_router=None):
        selected = str(mode or os.getenv("JARVIS_ORCHESTRATOR_V2", "shadow")).lower()
        self.mode = selected if selected in self.VALID_MODES else "shadow"
        self.skills = SkillsRouter(registry)
        self.models = model_router or ModelRouter()
        self.audit = audit
        self.last_decision = None
        self.research_router = IntelligentResearchRouter()

    def decide(self, user_instruction, external_content="", classification=None,
               source="text", voice_capture=False):
        started = time.perf_counter()
        text = str(user_instruction or "").strip()
        data_class = classification or self.classify_data(text)
        research = self.research_router.decide(text, data_class)
        decision = self._route(text, data_class, source=source)
        decision = self._apply_research_decision(text, decision, research)
        self.last_decision = decision
        self._audit(decision, int((time.perf_counter() - started) * 1000))
        return decision

    def _apply_research_decision(self, text, decision, research):
        steps = list(decision.steps)
        if (not steps and research.required and re.search(
                r"\b(gpu|placa(?: de v[ií]deo)?)\b.*\b(temperatura|graus|normal|hotspot)\b|"
                r"\b(temperatura|graus|hotspot)\b.*\b(gpu|placa(?: de v[ií]deo)?)\b",
                text, re.I)):
            steps.append(PlanStep("step-1", "local_hardware_status", Route.SYSTEM,
                                  "system_status", {}))
        has_research = any(step.tool in {"web_research", "web_research_learn"}
                           for step in steps)
        current_data_tool = any(step.tool == "get_exchange_rate" for step in steps)
        if research.required and not has_research and not current_data_tool:
            original_steps = bool(steps)
            query = self._extract_research_query(text)
            steps.append(PlanStep(
                "step-%d" % (len(steps) + 1), "intelligent_research", Route.WEB,
                "web_research", {"query": query,
                                 "limit": 10 if research.level == ResearchLevel.DEEP_RESEARCH else 5,
                                 "privacy": decision.data_classification.value}))
            decision = replace(decision, route=decision.route if original_steps else Route.WEB,
                               requires_ai=False,
                               preferred_model_profile=(ModelProfile.DEEP
                                                        if research.level == ResearchLevel.DEEP_RESEARCH
                                                        else decision.preferred_model_profile),
                               steps=tuple(steps))
        if (any(step.tool in {"web_research", "web_research_learn"} for step in decision.steps)
                and research.level == ResearchLevel.DEEP_RESEARCH):
            steps = list(decision.steps)
            steps = [replace(step, args={**step.args, "limit": 5})
                     if step.tool in {"web_research", "web_research_learn"} else step
                     for step in steps]
            research_steps = [step for step in steps if step.tool == "web_research"]
            if len(research_steps) == 1:
                base_query = str(research_steps[0].args.get("query") or text).strip()
                complementary = (base_query + " documentação oficial fontes primárias").strip()
                if complementary.casefold() != base_query.casefold():
                    steps.append(PlanStep(
                        "step-%d" % (len(steps) + 1), "deep_research_official",
                        Route.WEB, "web_research",
                        {"query": complementary, "limit": 5,
                         "privacy": decision.data_classification.value}))
            decision = replace(decision, preferred_model_profile=ModelProfile.DEEP,
                               steps=tuple(steps))
        answer_route = self.research_router.answer_route(
            decision.route, decision.steps, research)
        return replace(decision, research_level=research.level.value,
                       research_reason=research.reason.value,
                       router_decision_ms=research.latency_ms,
                       answer_route=answer_route)

    def _route(self, text, classification, source="text"):
        low = text.casefold()
        if not text or re.fullmatch(r"(abra|abre|feche|fecha)\s+(ele|ela|isso|aquilo)[.!?]?", low):
            return self._decision("ambiguous_reference", Route.CLARIFY, .2, "conversation",
                                  ModelProfile.FAST, classification, clarification=True)

        # ═══════════════════════════════════════════════════════════════
        # CONCEPTUAL INTENT PRECEDENCE
        # Uses shared is_conceptual_query() classifier.
        # "o que é CPU?" → LLM conversation (NO system_status)
        # "qual o uso da CPU?" → operational (system_status)
        # ═══════════════════════════════════════════════════════════════
        if is_conceptual_query(text):
            return self._decision("conceptual_question", Route.CONVERSATION, .85,
                                  "conversation", ModelProfile.GENERAL, classification,
                                  ai=True, steps=())
        if re.search(r"\b(abra|abre|abrir)\s+(a\s+)?calculadora\b", low):
            step = PlanStep("step-1", "open_calculator", Route.WINDOWS,
                            "open_program", {"name": "calculadora"})
            return self._decision("open_calculator", Route.WINDOWS, 1.0, "windows",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        if re.search(r"\b(abra|abre|abrir)\s+(o\s+)?gerenciador de tarefas?\b", low):
            step = PlanStep("step-1", "open_task_manager", Route.WINDOWS,
                            "open_program", {"name": "gerenciador de tarefas"})
            return self._decision("open_task_manager", Route.WINDOWS, 1.0, "windows",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        if re.search(r"\b(abra|abre|abrir)\s+(o\s+)?bloco de notas\b", low):
            step = PlanStep("step-1", "open_notepad", Route.WINDOWS,
                            "open_program", {"name": "bloco de notas"})
            return self._decision("open_notepad", Route.WINDOWS, 1.0, "windows",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        if re.search(r"\b(que horas|qual (é|e) a hora|hora atual)\b", low):
            step = PlanStep("step-1", "get_time", Route.SYSTEM, "get_time", {})
            return self._decision("get_time", Route.SYSTEM, 1.0, "system",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        # Cotacao deterministica: moeda detectada pelos aliases canonicos,
        # sem LLM generativo (resposta vem da tool + provider real).
        if re.search(r"\bcota[cç][aã]o\b", low):
            base = self._detect_currency(low)
            if base:
                step = PlanStep("step-1", "exchange_rate", Route.MARKET_DATA,
                                "get_exchange_rate", {"base": base, "quote": "BRL"})
                return self._decision("exchange_rate", Route.MARKET_DATA, .97, "market_data",
                                      ModelProfile.FAST, classification, ai=False, steps=(step,))
        rules = (
            (r"cota[cç][aã]o do d[oó]lar", "exchange_rate", Route.MARKET_DATA, "market_data", ModelProfile.FAST),
            (r"eurusd.*corretora|corretora.*eurusd", "broker_quote", Route.MT5, "mt5", ModelProfile.GENERAL),
            (r"pesquis(e|ar)|procure na internet|verifique na web|not[ií]cias",
             "web_research", Route.WEB, "web", ModelProfile.GENERAL),
            (r"mem[oó]ria|o que (voc[eê] )?lembra|procure na mem[oó]ria", "memory_lookup", Route.MEMORY, "memory", ModelProfile.GENERAL),
            (r"olhe minha tela|veja minha tela", "screen_analysis", Route.VISION, "vision", ModelProfile.VISION),
            (r"corrija.*\bea\b|corrigir.*\bea\b", "code_correction", Route.CODING, "coding", ModelProfile.CODING),
            (r"crie.*imagem|criar.*imagem", "image_creation", Route.IMAGE, "image", ModelProfile.GENERAL),
            (r"edite.*v[ií]deo|editar.*v[ií]deo", "video_edit", Route.VIDEO, "video", ModelProfile.DEEP),
            (r"whatsapp", "whatsapp_send", Route.WHATSAPP, "whatsapp", ModelProfile.GENERAL),
            (r"\bradar\b", "radar_view", Route.RADAR, "radar", ModelProfile.GENERAL),
            (r"analise.*ouro|ouro.*estrat[eé]gia", "trading_analysis", Route.TRADING, "trading", ModelProfile.DEEP),
            (r"prepare meu ambiente", "prepare_environment", Route.TASK, "task", ModelProfile.DEEP),
        )
        for pattern, intent, route, skill, profile in rules:
            if re.search(pattern, low):
                if route == Route.WEB:
                    learn = bool(re.search(
                        r"\b(aprenda|aprender|aprenda o que|memorize|guarde)\b", low))
                    tool = "web_research_learn" if learn else "web_research"
                    query = self._extract_research_query(text)
                    step = PlanStep("step-1", intent, Route.WEB, tool,
                                    {"query": query, "limit": 5,
                                     "privacy": classification.value})
                    return self._decision(intent, route, .96, skill, profile,
                                          classification, ai=False, steps=(step,))
                return self._decision(intent, route, .94, skill, profile, classification,
                                      planning=route == Route.TASK)
        # ── PROCESS LISTING (imperative + infinitive forms) ──
        if re.search(r"\b(liste|listar|mostre|mostre|exiba|exibir)\b.*\b(processos?|programas?|aplicativos?)\b", low):
            step = PlanStep("step-1", "list_processes", Route.SYSTEM,
                            "list_processes", {})
            return self._decision("list_processes", Route.SYSTEM, 1.0, "system",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        if re.search(r"\b(processos?\s+abertos?|quais\s+processos?|o\s+que\s+(est[aá]\s+)?rodando|programas?\s+abertos?)\b", low):
            step = PlanStep("step-1", "list_processes", Route.SYSTEM,
                            "list_processes", {})
            return self._decision("list_processes", Route.SYSTEM, 1.0, "system",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        # Diagnóstico de desempenho exige pressão geral e evidência por processo.
        diagnostic_subject = r"(?:computador|pc|m[aá]quina|sistema)"
        diagnostic_symptom = r"(?:pesad[oa]|lent[oa]|travando|consumindo|sobrecarregad[oa])"
        diagnostic_actor = r"(?:programa|processo|aplicativo).*(?:pesando|consumindo|lentid[aã]o|lento)"
        diagnostic_incomplete = r"o\s+que\s+est[aá]\s+deixando\s+(?:meu\s+)?(?:computador|pc|m[aá]quina)\s*[?!.]*$"
        if re.search(rf"(?:{diagnostic_subject}.*{diagnostic_symptom}|"
                     rf"{diagnostic_symptom}.*{diagnostic_subject}|{diagnostic_actor}|"
                     rf"{diagnostic_incomplete})", low):
            steps = (
                PlanStep("step-1", "performance_status", Route.SYSTEM,
                         "system_status", {}),
                PlanStep("step-2", "performance_processes", Route.SYSTEM,
                         "list_processes", {}),
            )
            return self._decision("performance_diagnosis", Route.SYSTEM, .98, "system",
                                  ModelProfile.GENERAL, classification, ai=False,
                                  planning=False, steps=steps)
        # ── SYSTEM STATUS (natural language) ──
        if re.search(r"\b(como\s+(est[aá]|esta)|status|sa[uú]de|diagn[oó]stico|telemetria|sensores)\b.*"
                     r"\b(computador|pc|m[aá]quina|sistema|dispositivo)?\b", low):
            step = PlanStep("step-1", "system_status", Route.SYSTEM,
                            "system_status", {})
            return self._decision("system_status", Route.SYSTEM, 0.9, "system",
                                  ModelProfile.FAST, classification, ai=False, steps=(step,))
        profile = ModelProfile.GENERAL
        if source == "voice":
            complex_request = re.search(
                r"\b(an[aá]lise profunda|analise profundamente|monte cen[aá]rios|"
                r"compare detalhadamente|estudo completo|passo a passo detalhado)\b", low)
            action_request = re.search(
                r"\b(abra|abre|abrir|feche|fecha|fechar|execute|crie|envie|mande)\b", low)
            profile = (ModelProfile.DEEP if complex_request else
                       ModelProfile.GENERAL if action_request else ModelProfile.VOICE_FAST)
        return self._decision("conversation", Route.CONVERSATION, .65, "conversation",
                              profile, classification)

    def _decision(self, intent, route, confidence, skill, profile, classification,
                  ai=True, planning=False, clarification=False, steps=()):
        definition = self.skills.get(skill)
        return OrchestratorDecision(intent, route, confidence, ai, planning,
            bool(definition and definition.risk_profile in {"HIGH", "CRITICAL"}),
            clarification, skill, profile, tuple(steps),
            "LOW_CONFIDENCE_CLARIFY" if clarification else "ROUTE_MATCH",
            self.skills.tool_names(skill), classification)

    @staticmethod
    def _detect_currency(text):
        """Detecta moeda pelos aliases canonicos do JarvisService.

        Import tardio: service importa este pacote no topo (sem ciclo).
        """
        try:
            from ..service import JarvisService
            aliases = JarvisService.CURRENCY_ALIASES
        except Exception:
            return ""
        low = str(text or "").casefold()
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in low and aliases[alias] != "BRL":
                return aliases[alias]
        return ""

    @staticmethod
    def _extract_research_query(text):
        value = str(text or "").strip()
        value = re.sub(
            r"(?i)\b(pesquise|pesquisar|procure na internet|verifique na web|"
            r"veja na web|procure|not[ií]cias sobre|not[ií]cias de|aprenda|"
            r"aprender|o que for confi[aá]vel|memorize|guarde)\b", " ", value)
        value = re.sub(r"(?i)\b(sobre|na internet|na web|e)\b", " ", value)
        return re.sub(r"\s+", " ", value).strip(" .,:;!?") or str(text or "").strip()

    @staticmethod
    def classify_data(text):
        words = set(re.findall(r"[a-zA-Z_]+", str(text).lower()))
        return DataClassification.SECRET if words & SECRET_MARKERS else DataClassification.INTERNAL

    def _audit(self, decision, latency_ms):
        if not self.audit:
            return
        provider, _ = ("", "")
        candidates = self.models.select(decision.preferred_model_profile,
                                        decision.data_classification)
        if candidates:
            provider = candidates[0][0].name
        self.audit.add(task_id="orchestrator", command="route", tool="orchestrator_v2",
            arguments={"route": decision.route.value, "confidence": decision.confidence,
                       "skill": decision.preferred_skill,
                       "model_profile": decision.preferred_model_profile.value,
                       "provider": provider, "fallback": not bool(provider)},
            risk="LOW", status=self.mode, result="decisão estrutural", elapsed_ms=latency_ms)

    def status(self):
        return {"mode": self.mode, "last_decision": asdict(self.last_decision) if self.last_decision else None}
