"""
Golden AI - Chat de Mídia

Extraído de golden_ai.py (linhas 609-795).
Ingestão, análise e estudos de mídia.
"""

import os
from pathlib import Path

from .context import CFG, SERVICES
from .utils import normalizar_texto_intencao, extrair_studio_context_path
from .files import caminho_seguro

# Estado de sessão
MEDIA_LAST_SOURCE_ID = None
MEDIA_PREVIOUS_SOURCE_ID = None


# ============================================================
# SERVICE WRAPPERS
# ============================================================

def _media_service():
    try:
        from media_study import MediaStudyService
        return MediaStudyService(r"C:\GoldenAI")
    except Exception:
        raise RuntimeError("Media Study V1 indisponivel.")


def _media_audit(action_type, status, target="", detail=""):
    if not SERVICES.AUDIT_LOGGER:
        return
    try:
        SERVICES.AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CFG.SESSION_ID,
            "agent": "golden_ai.media_chat.v1",
            "target": str(target or ""),
            "result": str(detail)[:600] if detail else "",
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


def _media_abs_path_autorizado(nome=""):
    caminho = extrair_studio_context_path(str(nome or "")) or str(nome or "")
    caminho = caminho.strip()
    if not caminho:
        raise ValueError("fonte Media nao indicada")
    if os.path.isabs(caminho):
        path = Path(caminho)
        if not path.exists():
            raise FileNotFoundError("fonte Media nao encontrada")
        return str(path)
    seguro = caminho_seguro(caminho)
    if seguro is None:
        raise ValueError("fonte Media fora da pasta autorizada ou nome invalido")
    return seguro


# ============================================================
# MEDIA OPERATIONS
# ============================================================

def media_ingest_source(nome="", source_type="", title="", author="", language=""):
    global MEDIA_LAST_SOURCE_ID, MEDIA_PREVIOUS_SOURCE_ID
    caminho = _media_abs_path_autorizado(nome)
    result = _media_service().ingest_source(caminho, source_type, title, author, language)
    if isinstance(result, dict) and result.get("ok"):
        source = result.get("source") or {}
        MEDIA_PREVIOUS_SOURCE_ID = MEDIA_LAST_SOURCE_ID
        MEDIA_LAST_SOURCE_ID = source.get("source_id")
    return result


def media_get_source(source_id=""):
    return _media_service().get_source(source_id or MEDIA_LAST_SOURCE_ID or "") or {"ok": False, "erro": "fonte Media nao encontrada"}


def media_list_sources(limit=20):
    return _media_service().list_sources(int(limit))


def media_get_segments(source_id="", limit=200):
    return _media_service().get_segments(source_id or MEDIA_LAST_SOURCE_ID or "", int(limit))


def media_search_source(query="", source_id="", limit=20):
    return _media_service().search_source(query, source_id or MEDIA_LAST_SOURCE_ID or "", int(limit))


def media_extract_claims(source_id=""):
    return _media_service().extract_claims(source_id or MEDIA_LAST_SOURCE_ID or "")


def media_get_claims(source_id="", claim_id=""):
    return _media_service().get_claims(source_id or MEDIA_LAST_SOURCE_ID or "", claim_id)


def media_study_source(source_id=""):
    return _media_service().study_source(source_id or MEDIA_LAST_SOURCE_ID or "")


def media_get_study_result(study_id=""):
    return _media_service().get_study_result(study_id) or {"ok": False, "erro": "estudo Media nao encontrado"}


def media_claim_to_hypothesis(claim_id=""):
    result = _media_service().claim_to_hypothesis(claim_id)
    return result.__dict__ if hasattr(result, "__dict__") else result


def media_get_claim_origin(claim_id=""):
    return _media_service().get_claim_origin(claim_id)


# ============================================================
# CHAT RESponder
# ============================================================

def pergunta_pede_media(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("agora vamos falar sobre carros", "nao quero falar do material")):
        return False
    termos = (
        "media study", "estude esta transcricao", "estude essa transcricao",
        "estude este arquivo", "estude esse arquivo", "fonte media",
        "ingest", "ingira", "transcricao", "segments", "claims",
        "claim", "hipotese do material", "origem do claim",
    )
    return any(t in texto for t in termos)


def _formatar_media_result(result):
    """Formata resultado de operação de mídia."""
    if isinstance(result, dict) and result.get("ok"):
        return str(result)
    return str(result.get("erro", result)) if isinstance(result, dict) else str(result)


def responder_media_chat(pergunta, historico, executar_tool_core_fn):
    """Responde a pergunta de mídia."""
    global MEDIA_LAST_SOURCE_ID

    if not pergunta_pede_media(pergunta):
        return False

    texto = normalizar_texto_intencao(pergunta)

    if "ingest" in texto or "ingira" in texto:
        resultado = executar_tool_core_fn("media_ingest_source", {"nome": ""})
        resposta = _formatar_media_result(resultado)
    elif "estude" in texto:
        resultado = executar_tool_core_fn("media_study_source", {"source_id": ""})
        resposta = _formatar_media_result(resultado)
    elif "claim" in texto and "origem" in texto:
        resultado = executar_tool_core_fn("media_get_claim_origin", {"claim_id": ""})
        resposta = _formatar_media_result(resultado)
    elif "hipotese" in texto:
        resultado = executar_tool_core_fn("media_claim_to_hypothesis", {"claim_id": ""})
        resposta = _formatar_media_result(resultado)
    elif "segments" in texto:
        resultado = executar_tool_core_fn("media_get_segments", {"source_id": "", "limit": 50})
        resposta = _formatar_media_result(resultado)
    else:
        resultado = executar_tool_core_fn("media_get_source", {"source_id": ""})
        resposta = _formatar_media_result(resultado)

    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True
