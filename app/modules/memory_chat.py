"""
Golden AI - Chat de Memória Científica

Extraído de golden_ai.py (linhas 402-607).
Armazenamento e busca de conhecimento.
"""

import re

from .context import CFG, SERVICES
from .utils import normalizar_texto_intencao


# ============================================================
# SERVICE WRAPPERS
# ============================================================

def _memory_service():
    try:
        from core.memory import ScientificMemoryService
        return ScientificMemoryService(r"C:\GoldenAI")
    except Exception:
        raise RuntimeError("Memoria cientifica indisponivel.")


def _memory_audit(action_type, status, target="", detail=""):
    if not SERVICES.AUDIT_LOGGER:
        return
    try:
        SERVICES.AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CFG.SESSION_ID,
            "agent": "golden_ai.memory_chat.v1",
            "target": str(target or ""),
            "result": str(detail)[:600] if detail else "",
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


# ============================================================
# MEMORY OPERATIONS
# ============================================================

def memory_store_knowledge(topic="", statement="", evidence_level="SOURCE_CLAIM",
                           source_type="USER_NOTE", source_id="", source_location="",
                           confidence=0.5, validation_status="", tags=None, metadata=None,
                           supersedes_id=None):
    item = _memory_service().store_knowledge(
        topic=topic, statement=statement, evidence_level=evidence_level,
        source_type=source_type, source_id=source_id, source_location=source_location,
        confidence=float(confidence), validation_status=validation_status,
        tags=tags or [], metadata=metadata or {}, supersedes_id=supersedes_id,
    )
    return item.__dict__


def memory_search_knowledge(topic="", text="", tags=None, source_type="",
                            evidence_level="", experiment_id="", symbol="",
                            timeframe="", limit=20):
    return _memory_service().search_knowledge(
        topic=topic, text=text, tags=tags or [], source_type=source_type,
        evidence_level=evidence_level, experiment_id=experiment_id,
        symbol=symbol, timeframe=timeframe, limit=int(limit),
    )


def memory_get_knowledge(knowledge_id=""):
    return _memory_service().get_knowledge(knowledge_id) or {"ok": False, "erro": "KnowledgeItem nao encontrado"}


def memory_find_related_experiments(query="", symbol="", timeframe="", limit=10):
    return _memory_service().find_related_experiments(query=query, symbol=symbol, timeframe=timeframe, limit=int(limit))


def memory_get_topic_summary(topic="", limit=10):
    return _memory_service().get_topic_summary(topic=topic, limit=int(limit))


def memory_link_experiment(knowledge_id="", experiment_id="", relationship="supports", metadata=None):
    return _memory_service().link_experiment(knowledge_id, experiment_id, relationship, metadata or {})


def _memory_store_quant_experiment(experiment_id, backtest_spec, result, artifact_dir=""):
    try:
        item = _memory_service().store_quant_experiment(experiment_id, backtest_spec, result, artifact_dir)
        return item.knowledge_id
    except Exception as erro:
        _memory_audit("MEMORY_ITEM_CREATE_FAILED", "FAILED", experiment_id, erro)
        return ""


# ============================================================
# CHAT RESponder
# ============================================================

def pergunta_pede_memoria(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    termos = (
        "memoria cientifica", "guarde isso", "guardar isso", "salve isso",
        "ja testamos", "ja foi testado", "algo parecido", "o que sabemos",
        "de onde veio", "qual experimento", "qual estrategia ja foi reprovada",
        "foi realmente validado", "so apareceu num backtest", "descartamos",
        "resultados tivemos", "resultado tivemos",
    )
    return any(t in texto for t in termos)


def _extrair_texto_para_memoria(pergunta):
    texto = re.sub(r"(?is)\[STUDIO_CONTEXT\].*?\[/STUDIO_CONTEXT\]", "", str(pergunta or "")).strip()
    padroes = [
        r"(?is)guarde isso na memoria cientifica[:\s]*(.+)",
        r"(?is)guarde isso[:\s]*(.+)",
        r"(?is)salve isso[:\s]*(.+)",
        r"(?is)guardar isso[:\s]*(.+)",
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            return match.group(1).strip()
    return texto


def _consulta_memoria_limpa(pergunta):
    texto = _extrair_texto_para_memoria(pergunta)
    texto = re.sub(r"(?i)\b(o que sabemos sobre|ja testamos algo parecido com|ja testamos|qual experimento testou|de onde veio|essa informacao|isso|sobre)\b", " ", texto)
    texto = re.sub(r"[?.!,;:]+", " ", texto)
    texto = " ".join(texto.split())
    return texto or _extrair_texto_para_memoria(pergunta)


def _formatar_memoria_resposta(payload):
    if isinstance(payload, dict) and "items" in payload:
        itens = payload.get("items") or []
        conflitos = payload.get("conflicts") or []
    elif isinstance(payload, list):
        itens = payload
        conflitos = []
    else:
        return str(payload)
    if not itens:
        return "Nao encontrei memoria cientifica relacionada."
    linhas = ["Memoria cientifica encontrada:"]
    if conflitos:
        linhas.append("Ha resultados conflitantes registrados.")
    for item in itens[:8]:
        meta = item.get("metadata") or {}
        dataset = meta.get("dataset") or {}
        linhas.append(
            f"- {item.get('statement')} "
            f"[{item.get('evidence_level')}; fonte={item.get('source_type')}; data={item.get('created_at')}]"
        )
        if dataset:
            linhas.append(f"  Dataset: {dataset.get('source')} ({dataset.get('start')} -> {dataset.get('end')})")
    return "\n".join(linhas)


def responder_memoria_chat(pergunta, historico, executar_tool_core_fn):
    """Responde a pergunta de memória."""
    if not pergunta_pede_memoria(pergunta):
        return False

    texto = normalizar_texto_intencao(pergunta)

    if any(t in texto for t in ("guarde isso", "guardar isso", "salve isso")):
        statement = _extrair_texto_para_memoria(pergunta)
        resultado = executar_tool_core_fn("memory_store_knowledge", {
            "topic": statement[:80] or "nota_usuario",
            "statement": statement,
            "evidence_level": "SOURCE_CLAIM",
            "source_type": "USER_NOTE",
            "source_id": CFG.SESSION_ID,
            "source_location": "chat",
            "confidence": 0.4,
            "validation_status": "SOURCE_CLAIM",
            "tags": ["user_note"],
            "metadata": {"origin": "explicit_chat_request"},
        })
        resposta = f"Registrei na memoria cientifica. Knowledge ID: {resultado.get('knowledge_id') if isinstance(resultado, dict) else resultado}"
    elif "ja testamos" in texto or "algo parecido" in texto:
        consulta = _consulta_memoria_limpa(pergunta)
        resultado = executar_tool_core_fn("memory_find_related_experiments", {"query": consulta, "limit": 10})
        resposta = _formatar_memoria_resposta(resultado)
    else:
        consulta = _consulta_memoria_limpa(pergunta)
        resultado = executar_tool_core_fn("memory_get_topic_summary", {"topic": consulta, "limit": 10})
        resposta = _formatar_memoria_resposta(resultado)

    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True
