from ollama import chat
import urllib.request
import urllib.error
import os
import re
import json
import shutil
import subprocess
import hashlib
import sys
import time
import uuid
import unicodedata
from datetime import datetime
from pathlib import Path

# Saida em UTF-8 para nao quebrar com caracteres do modelo
try:
    if sys.stdout and getattr(sys.stdout, "reconfigure", None):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_GOLDENAI = r"C:\GoldenAI"
if ROOT_GOLDENAI not in sys.path:
    sys.path.insert(0, ROOT_GOLDENAI)

# ============================================================
# MÓDULOS EXTRAÍDOS (app/modules/)
# ============================================================
from app.modules.context import CFG, SERVICES, SESSION, init_core, obter_modelo
from app.modules.utils import (
    caminho_seguro, normalizar_texto_intencao, detectar_idioma_resposta,
    classificar_intencao_conversacional, extrair_studio_context_path,
    hash_texto, extrair_codigo, extrair_nome_mq5, normalizar_texto_v110,
    extrair_query_busca, _formatar_bytes, _weekday_pt,
)
from app.modules.mt5 import (
    caminho_seguro_mt5, listar_eas_mt5, ler_arquivo_mt5, compilar_mql5,
    analisar_arquivo_mt5_real,
)
from app.modules.files import (
    listar_projetos, ler_arquivo, arquivo_metadados, nome_para_projetos,
    formatar_resposta_metadados, criar_backup, restaurar_backup, escrever_arquivo,
)
from app.modules.intent import (
    classificar_intencao_usuario, pedido_proibe_escrita,
    normalizar_intencao_conversa, usuario_mudou_para_conversa_geral,
    pergunta_pede_contexto_tecnico, pergunta_pede_ferramenta_local,
    pergunta_pede_memoria, pergunta_pede_market, pergunta_pede_quant,
    pergunta_pede_orquestrador,
)
from app.modules.internet import (
    internet_search, internet_fetch, internet_download,
    pergunta_pede_internet, formatar_internet_search_result,
)
from app.modules.browser import (
    browser_search, browser_fetch, document_extract, audio_transcribe,
    video_analyze, vision_analyze_image, memory_vector_store,
    memory_vector_search, status_modulos_v110,
)
from app.modules.panel import (
    mostrar_painel_comandos, listar_robos_painel, resolver_robo_por_nome,
    mostrar_codigo_alvo_numerado, executar_painel,
)
from app.modules.market_chat import (
    market_analyze_dataset, market_get_analysis, market_list_analyses,
    market_get_snapshot, market_get_regime, market_get_multitimeframe_context,
    market_get_structure, market_get_observations, market_get_signals,
    market_hypothesis_to_strategy_spec, pergunta_pede_market,
    responder_market_chat, MARKET_LAST_ANALYSIS_ID,
)
from app.modules.memory_chat import (
    memory_store_knowledge, memory_search_knowledge, memory_get_knowledge,
    memory_find_related_experiments, memory_get_topic_summary,
    memory_link_experiment, _memory_store_quant_experiment,
    pergunta_pede_memoria, responder_memoria_chat,
)
from app.modules.media_chat import (
    media_ingest_source, media_get_source, media_list_sources,
    media_get_segments, media_search_source, media_extract_claims,
    media_get_claims, media_study_source, media_get_study_result,
    media_claim_to_hypothesis, media_get_claim_origin,
    pergunta_pede_media, responder_media_chat,
)
from app.modules.quant_chat import (
    quant_run_backtest, quant_get_experiment, quant_get_metrics,
    quant_get_trades, quant_get_equity, quant_list_experiments,
    quant_compare_experiments, pergunta_pede_quant,
    responder_quant_chat,
)
from app.modules.report import (
    salvar_relatorio_autocorrecao, carregar_relatorio_autocorrecao,
    imprimir_relatorio_autocorrecao, interpretar_veredito_final,
    resumo_veredito_persistente, salvar_estado_alvo_auditoria,
    carregar_estado_alvo_auditoria, invalidar_veredito_persistente,
    salvar_auditoria_deterministica, carregar_auditoria_deterministica,
)
from app.modules.audit_deterministic import (
    chat_deterministico, extrair_json_modelo, canonicalizar_candidatos,
    candidatos_equivalentes, comparar_e_fundir_candidatos,
    assinatura_estrutural, canonicalizar_validacao,
)
from app.modules.auto_fix import (
    _gerar_contrato_correcao, _validar_patch_contra_contrato,
    _extrair_funcao_por_intervalo, _contexto_funcao,
    _montar_patch_cirurgico, _validar_invariantes_patch_cirurgico,
    _validar_funcao_pos_compilacao_cirurgica, _preflight_mql5_funcao,
    _revalidar_bug_antes_de_corrigir, _gerar_patch_cirurgico_opencode,
    selecionar_bugs_para_correcao,
)
from app.modules.mt5_ops import (
    copiar_ea_mt5_para_teste, extrair_caminho_mql_explicito,
    classificar_alvo_mql, resolver_alvo_mql, confirmar_alvo_na_tela,
    ler_alvo_resolvido, extrair_nome_mt5_real, localizar_mt5_real_por_nome,
)
from app.modules.model_chat import (
    chat_texto_com_timeout, _chamar_modelo, _normalizar_tool_calls,
    extrair_confirmados_do_texto_veredito, validar_identidade_bugs_selecionados,
    localizar_intervalo_por_linha, resolver_intervalo_bug,
    _FuncaoChamada, _ChamadaFerramenta, _MensagemModelo, _RespostaModelo,
)
from app.modules.agent_normal import (
    executar_agente_normal, executar_tool_core, FERRAMENTAS,
)

# ============================================================
# CORE V3 (imports diretos que ainda são necessários)
# ============================================================
try:
    from core.audit import AuditEvent, AuditLogger
    from core.config import load_settings
    from core.permissions import PermissionManager
    from core.tools import ToolDefinition, ToolRegistry
    from core.memory import ScientificMemoryService
    from core.safety import EvidenceLevel
    from core.computer import (
        find_installed_app, find_mt5_installations, get_current_datetime,
        get_disk_usage, get_mt5_status, get_system_info, launch_allowed_app,
        list_mt5_eas, list_mt5_terminals, list_processes, open_folder,
        read_mt5_file, detect_all_mt5_installations, get_mt5_installation_by_id,
        list_mt5_experts_for_terminal, list_mt5_indicators_for_terminal,
        list_mt5_scripts_for_terminal, find_mt5_file_by_name,
        find_mt5_ex5_by_name, get_mt5_file_metadata, deploy_to_mt5,
        list_mt5_ex5_files,
    )
except Exception:
    AuditEvent = None
    AuditLogger = None
    PermissionManager = None
    ToolDefinition = None
    ToolRegistry = None
    ScientificMemoryService = None
    EvidenceLevel = None
    load_settings = None

try:
    from market import LocalCsvMarketDataAdapter, MarketAnalysisService, SyntheticMarketDataAdapter
except Exception:
    LocalCsvMarketDataAdapter = None
    MarketAnalysisService = None
    SyntheticMarketDataAdapter = None

try:
    from quant import CostModel, QuantService, StrategySpec, build_backtest_spec
except Exception:
    CostModel = None
    QuantService = None
    StrategySpec = None
    build_backtest_spec = None

try:
    from media_study import MediaStudyService
except Exception:
    MediaStudyService = None

try:
    from agents import AgentOrchestrator
except Exception:
    AgentOrchestrator = None

try:
    from core.models import ModelRouter, ModelProfile
    CORE_SETTINGS = load_settings() if load_settings else None
    _MODEL_ROUTER = ModelRouter(settings=CORE_SETTINGS) if CORE_SETTINGS else None
except Exception:
    ModelRouter = None
    ModelProfile = None
    _MODEL_ROUTER = None


# ============================================================
# CONFIGURACAO (via context.py)
# ============================================================

MODELO = CFG.MODELO
_obter_modelo = obter_modelo  # Alias para compatibilidade

PASTA_APP = CFG.PASTA_APP
PASTA_PROJETOS = CFG.PASTA_PROJETOS
PASTA_BACKUPS = CFG.PASTA_BACKUPS
PASTA_LOGS = CFG.PASTA_LOGS

METAEDITOR = CFG.METAEDITOR

PASTA_MT5_DADOS = CFG.PASTA_MT5_DADOS
PASTA_MT5_MQL5 = CFG.PASTA_MT5_MQL5
PASTA_MT5_EXPERTS = CFG.PASTA_MT5_EXPERTS

MAX_CORRECOES = CFG.MAX_CORRECOES

CORE_SESSION_ID = CFG.SESSION_ID
CORE_SETTINGS = SERVICES.SETTINGS
CORE_PERMISSION_MANAGER = SERVICES.PERMISSION_MANAGER
CORE_AUDIT_LOGGER = SERVICES.AUDIT_LOGGER
CORE_TOOL_REGISTRY = SERVICES.TOOL_REGISTRY

# Inicializa core services
init_core()


# ============================================================
# UTILIDADES - Importadas de app/modules/utils.py
# ============================================================
# caminho_seguro, normalizar_texto_intencao, detectar_idioma_resposta,
# classificar_intencao_conversacional, extrair_studio_context_path,
# hash_texto, extrair_codigo, extrair_nome_mq5, normalizar_texto_v110,
# extrair_query_busca, _formatar_bytes, _weekday_pt



# ============================================================
# MT5 REAL - Importado de app/modules/mt5.py
# ============================================================
# caminho_seguro_mt5, listar_eas_mt5, ler_arquivo_mt5,
# compilar_mql5, analisar_arquivo_mt5_real


# ============================================================
# ARQUIVOS - Importado de app/modules/files.py
# ============================================================
# listar_projetos, ler_arquivo, arquivo_metadados, nome_para_projetos,
# formatar_resposta_metadados, criar_backup, restaurar_backup, escrever_arquivo


def responder_metadados_arquivo(pergunta):
    if classificar_intencao_conversacional(pergunta) != "FILE_METADATA":
        return False

    caminho_contexto = extrair_studio_context_path(pergunta)
    if not caminho_contexto and arquivo_alvo_atual and arquivo_alvo_atual.get("ok"):
        caminho_contexto = arquivo_alvo_atual.get("caminho")

    if not caminho_contexto:
        idioma = detectar_idioma_resposta(pergunta)
        resposta = (
            "Please select or provide the file first. I will not invent a path."
            if idioma == "en"
            else "Preciso que voce selecione ou indique o arquivo primeiro. Nao vou inventar um caminho."
        )
        historico.append({"role": "user", "content": pergunta})
        historico.append({"role": "assistant", "content": resposta})
        print()
        print("Golden AI:")
        print(resposta)
        print()
        return True

    nome = nome_para_projetos(caminho_contexto)
    print()
    print("[GoldenAI usando ferramenta: arquivo_metadados]")
    resultado = executar_tool_core("arquivo_metadados", {"nome": nome})
    resposta = formatar_resposta_metadados(pergunta, resultado)
    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print(resultado)
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


def responder_programador_opencode(pergunta):
    """
    Despacho deterministico: pedido de CODING_CHANGE em arquivo de codigo
    (corrigir, ajustar, alterar, implementar) e delegado ao agente OpenCode
    via executar_opencode, com cadeia Free -> Qwen local. Golden supervisiona.
    """
    if classificar_intencao_conversacional(pergunta) != "CODING_CHANGE":
        return False

    nome = extrair_nome_mq5(pergunta)
    if not nome:
        if arquivo_alvo_atual and arquivo_alvo_atual.get("ok"):
            nome = nome_para_projetos(arquivo_alvo_atual.get("caminho", ""))
        if not nome:
            return False

    caminho = nome_para_projetos(nome)
    caminho_abs = os.path.abspath(os.path.join(PASTA_PROJETOS, caminho))
    if not os.path.isfile(caminho_abs):
        resposta = (
            f"Preciso do caminho do arquivo para delegar ao OpenCode. "
            f"Nao encontrei o arquivo: {caminho}"
        )
        historico.append({"role": "user", "content": pergunta})
        historico.append({"role": "assistant", "content": resposta})
        print()
        print("Golden AI:")
        print(resposta)
        print()
        return True

    tarefa = (
        f"Arquivo alvo (trabalhe neste caminho exato): {caminho_abs}\n"
        f"Pedido do usuario: {pergunta}\n"
        "Execute o pedido DIRETAMENTE no arquivo: edite, salve e depois "
        "confirme as alteracoes. NAO faca perguntas de esclarecimento e "
        "nao responda apenas lendo o arquivo: aplique as correcoes e "
        "ajustes necessarios para o codigo ficar 100% correto, consistente "
        "e compilavel em MQL5. Ao final, relate EXATAMENTE o que foi "
        "alterado (funcoes e linhas). Se de fato nada precisar mudar, "
        "explique objetivamente por que."
    )

    print()
    print(f"[GoldenAI usando ferramenta: executar_opencode | arquivo: {caminho}]")
    resultado = executar_opencode(tarefa, diretorio=PASTA_PROJETOS, arquivo_alvo=caminho_abs)

    if resultado.get("ok"):
        texto = resultado.get("texto") or ""
        modelo = resultado.get("modelo", "")
        resposta = (
            f"Trabalho concluido pelo agente OpenCode (modelo: {modelo}).\n\n{texto}"
        )
    else:
        print()
        print(
            "OpenCode (modelos Free) nao concluiu o trabalho. "
            "Usando o motor local Qwen do Golden."
        )
        historico.append({"role": "user", "content": pergunta})
        corrigir_mql5_automatico(caminho, pergunta)
        historico.append(
            {
                "role": "assistant",
                "content": (
                    "Os modelos Free do OpenCode nao concluiram o trabalho; "
                    "o motor local Qwen do Golden foi acionado como fallback."
                ),
            }
        )
        return True

    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


MARKET_LAST_ANALYSIS_ID = None


def _market_service():
    if not MarketAnalysisService:
        raise RuntimeError("Market V1 indisponivel.")
    return MarketAnalysisService(ROOT_GOLDENAI)


def _market_audit(action_type, status, target="", detail=""):
    if not CORE_AUDIT_LOGGER:
        return
    try:
        CORE_AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CORE_SESSION_ID,
            "agent": "golden_ai.market_chat.v1",
            "target": str(target or ""),
            "result": _core_resumir(detail),
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


def _market_synthetic_rows(direction="up"):
    closes = [100, 102, 104, 106, 108, 110] if direction != "down" else [110, 108, 106, 104, 102, 100]
    rows = []
    anterior = closes[0]
    for indice, close in enumerate(closes, start=1):
        rows.append({
            "timestamp": f"2026-01-{indice:02d}T00:00:00+00:00",
            "open": anterior,
            "high": max(anterior, close) + 0.5,
            "low": min(anterior, close) - 0.5,
            "close": close,
        })
        anterior = close
    return rows


def market_analyze_dataset(nome="", symbol="DATASET", timeframe="H1", synthetic=""):
    global MARKET_LAST_ANALYSIS_ID
    _market_audit("MARKET_ANALYSIS_STARTED", "STARTED", nome or synthetic, f"symbol={symbol}; timeframe={timeframe}")
    try:
        service = _market_service()
        if synthetic:
            rows = _market_synthetic_rows(synthetic)
            adapter = SyntheticMarketDataAdapter({timeframe: rows})
            source = f"synthetic:{synthetic}"
        else:
            caminho = caminho_seguro(nome)
            if caminho is None:
                raise ValueError("dataset fora da pasta autorizada ou nome invalido")
            if not os.path.isfile(caminho):
                raise FileNotFoundError("dataset nao encontrado")
            if os.path.splitext(caminho)[1].lower() != ".csv":
                raise ValueError("Market V1 aceita apenas CSV local autorizado nesta rota")
            adapter = LocalCsvMarketDataAdapter(caminho, timeframe)
            source = f"csv:{os.path.basename(caminho)}"
        result = service.analyze(symbol or "DATASET", adapter, source=source)
        MARKET_LAST_ANALYSIS_ID = result.analysis_id
        _market_audit("MARKET_ANALYSIS_COMPLETED", "COMPLETED", result.analysis_id, result.result_hash)
        payload = result.report | {"analysis_id": result.analysis_id, "result_hash": result.result_hash}
        _memory_store_market_result(payload)
        return payload
    except Exception as erro:
        _market_audit("MARKET_ANALYSIS_FAILED", "FAILED", nome or synthetic, str(erro))
        return {"ok": False, "erro": str(erro)}


def market_get_analysis(analysis_id=""):
    service = _market_service()
    data = service.repository.get_analysis(analysis_id) if analysis_id else service.repository.get_latest_analysis()
    _market_audit("MARKET_RESULT_READ", "COMPLETED" if data else "FAILED", analysis_id or "latest", "analysis")
    return data or {"ok": False, "erro": "analise de mercado nao encontrada"}


def market_list_analyses(limit=10):
    data = _market_service().repository.list_analyses(int(limit))
    _market_audit("MARKET_RESULT_READ", "COMPLETED", "market_list_analyses", f"count={len(data)}")
    return data


def _market_report_from_tool_result(resultado):
    if isinstance(resultado, dict) and "report" in resultado and isinstance(resultado["report"], dict):
        if "report" in resultado["report"] and isinstance(resultado["report"]["report"], dict):
            return resultado["report"]["report"]
        return resultado["report"]
    if isinstance(resultado, dict) and "symbol" in resultado and "inferred" in resultado:
        return resultado
    return None


def _memory_service():
    if not ScientificMemoryService:
        raise RuntimeError("Memoria cientifica indisponivel.")
    return ScientificMemoryService(ROOT_GOLDENAI)


def _memory_audit(action_type, status, target="", detail=""):
    if not CORE_AUDIT_LOGGER:
        return
    try:
        CORE_AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CORE_SESSION_ID,
            "agent": "golden_ai.memory_chat.v1",
            "target": str(target or ""),
            "result": _core_resumir(detail),
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


def memory_store_knowledge(topic="", statement="", evidence_level="SOURCE_CLAIM", source_type="USER_NOTE", source_id="", source_location="", confidence=0.5, validation_status="", tags=None, metadata=None, supersedes_id=None):
    item = _memory_service().store_knowledge(
        topic=topic,
        statement=statement,
        evidence_level=evidence_level,
        source_type=source_type,
        source_id=source_id,
        source_location=source_location,
        confidence=float(confidence),
        validation_status=validation_status,
        tags=tags or [],
        metadata=metadata or {},
        supersedes_id=supersedes_id,
    )
    return item.__dict__


def memory_search_knowledge(topic="", text="", tags=None, source_type="", evidence_level="", experiment_id="", symbol="", timeframe="", limit=20):
    return _memory_service().search_knowledge(
        topic=topic,
        text=text,
        tags=tags or [],
        source_type=source_type,
        evidence_level=evidence_level,
        experiment_id=experiment_id,
        symbol=symbol,
        timeframe=timeframe,
        limit=int(limit),
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


def _memory_store_market_result(resultado):
    try:
        report = _market_report_from_tool_result(resultado)
        analysis_id = _market_analysis_id_from_result(resultado)
        if not report or not analysis_id:
            return []
        items = _memory_service().store_market_analysis(report, analysis_id)
        return [item.knowledge_id for item in items]
    except Exception as erro:
        _memory_audit("MEMORY_ITEM_CREATE_FAILED", "FAILED", "market", erro)
        return []


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
    texto = re.sub(r"(?i)\b(o que sabemos sobre|ja testamos algo parecido com|ja testamos|qual experimento testou|de onde veio|essa informacao|essa informação|isso|sobre)\b", " ", texto)
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
        return "Nao encontrei memoria cientifica relacionada. Isso nao prova que nunca foi testado; apenas nao ha registro estruturado encontrado."
    linhas = ["Memoria cientifica encontrada:"]
    if conflitos:
        linhas.append("Ha resultados conflitantes registrados; nao vou escolher um arbitrariamente.")
    for item in itens[:8]:
        meta = item.get("metadata") or {}
        dataset = meta.get("dataset") or {}
        linhas.append(
            f"- {item.get('statement')} "
            f"[{item.get('evidence_level')}; fonte={item.get('source_type')}; source_id={item.get('source_id')}; data={item.get('created_at')}]"
        )
        if dataset:
            linhas.append(f"  Dataset: {dataset.get('source')} ({dataset.get('start')} -> {dataset.get('end')}); timeframe={dataset.get('timeframe')}")
        limitations = meta.get("limitations") or []
        if limitations:
            linhas.append(f"  Limitacoes: {'; '.join(str(x) for x in limitations[:2])}")
    return "\n".join(linhas)


def responder_memoria_chat(pergunta):
    if not pergunta_pede_memoria(pergunta):
        return False
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("guarde isso", "guardar isso", "salve isso")):
        statement = _extrair_texto_para_memoria(pergunta)
        resultado = executar_tool_core("memory_store_knowledge", {
            "topic": statement[:80] or "nota_usuario",
            "statement": statement,
            "evidence_level": "SOURCE_CLAIM",
            "source_type": "USER_NOTE",
            "source_id": CORE_SESSION_ID,
            "source_location": "chat",
            "confidence": 0.4,
            "validation_status": "SOURCE_CLAIM",
            "tags": ["user_note"],
            "metadata": {"origin": "explicit_chat_request"},
        })
        resposta = (
            "Registrei na memoria cientifica como SOURCE_CLAIM/USER_NOTE, nao como VALIDATED.\n"
            f"Knowledge ID: {resultado.get('knowledge_id') if isinstance(resultado, dict) else resultado}"
        )
    elif "ja testamos" in texto or "algo parecido" in texto or "qual experimento" in texto:
        consulta = _consulta_memoria_limpa(pergunta)
        resultado = executar_tool_core("memory_find_related_experiments", {"query": consulta, "limit": 10})
        resposta = _formatar_memoria_resposta(resultado)
    else:
        consulta = _consulta_memoria_limpa(pergunta)
        resultado = executar_tool_core("memory_get_topic_summary", {"topic": consulta, "limit": 10})
        if "o que sabemos" in texto and isinstance(resultado, dict):
            relacionados = executar_tool_core("memory_find_related_experiments", {"query": consulta, "limit": 5})
            vistos = {item.get("knowledge_id") for item in resultado.get("items", []) if isinstance(item, dict)}
            for item in relacionados if isinstance(relacionados, list) else []:
                if item.get("knowledge_id") not in vistos:
                    resultado.setdefault("items", []).append(item)
                    vistos.add(item.get("knowledge_id"))
        resposta = _formatar_memoria_resposta(resultado)
    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


MEDIA_LAST_SOURCE_ID = None
MEDIA_PREVIOUS_SOURCE_ID = None


def _media_service():
    if not MediaStudyService:
        raise RuntimeError("Media Study V1 indisponivel.")
    return MediaStudyService(ROOT_GOLDENAI)


def _media_audit(action_type, status, target="", detail=""):
    if not CORE_AUDIT_LOGGER:
        return
    try:
        CORE_AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CORE_SESSION_ID,
            "agent": "golden_ai.media_chat.v1",
            "target": str(target or ""),
            "result": _core_resumir(detail),
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


def pergunta_pede_media(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("agora vamos falar sobre carros", "vamos falar sobre carros", "nao quero falar do material")):
        globals()["MEDIA_PREVIOUS_SOURCE_ID"] = globals().get("MEDIA_LAST_SOURCE_ID")
        globals()["MEDIA_LAST_SOURCE_ID"] = None
        return False
    termos = (
        "media study", "estude esta transcricao", "estude essa transcricao", "estude este arquivo",
        "resuma este material", "resuma esse material", "quais regras esse autor ensinou",
        "ele falou", "em que momento", "de onde veio essa afirmacao", "de onde veio essa afirmação",
        "voltando ao material", "essa fonte", "transcricao", "transcrição", ".srt", ".vtt", ".md", ".txt",
        "converta essa regra em hipotese", "hipotese testavel", "hipótese testável",
    )
    return any(t in texto for t in termos)


def _formatar_media_study_result(result):
    if not isinstance(result, dict):
        return str(result)
    if not result.get("ok", True):
        return result.get("erro", str(result))
    claims = result.get("claims") or []
    hypotheses = result.get("hypotheses") or []
    quantitative = result.get("quantitative_claims") or []
    linhas = [
        "Media Study concluido.",
        "",
        result.get("summary", ""),
        f"Claims: {len(claims)}",
        f"Claims quantitativos: {len(quantitative)}",
        f"Hipoteses testaveis: {len(hypotheses)}",
        "Evidencia: SOURCE_CLAIM; nao VALIDATED.",
    ]
    for claim in claims[:6]:
        linhas.append(f"- {claim.get('statement')} [{claim.get('timestamp_start') or claim.get('line_start')}; {claim.get('claim_kind')}]")
    return "\n".join(linhas)


def _formatar_media_busca(rows):
    if not rows:
        return "Nao encontrei trecho relacionado na fonte Media atual."
    linhas = ["Trechos encontrados:"]
    for row in rows[:8]:
        location = row.get("start_time") or f"linhas {row.get('line_start')}-{row.get('line_end')}"
        linhas.append(f"- {location}: {row.get('text')}")
    return "\n".join(linhas)


def responder_media_chat(pergunta):
    if not pergunta_pede_media(pergunta):
        return False
    texto = normalizar_texto_intencao(pergunta)
    caminho_contexto = extrair_studio_context_path(pergunta)
    if "voltando ao material" in texto and not MEDIA_LAST_SOURCE_ID and MEDIA_PREVIOUS_SOURCE_ID:
        globals()["MEDIA_LAST_SOURCE_ID"] = MEDIA_PREVIOUS_SOURCE_ID
    if any(t in texto for t in ("estude esta transcricao", "estude essa transcricao", "estude este arquivo", ".srt", ".vtt", ".md", ".txt")):
        if not caminho_contexto:
            resposta = "Preciso que voce selecione ou indique um arquivo textual autorizado para o Media Study."
        else:
            nome = caminho_contexto
            print()
            print("[GoldenAI usando ferramenta: media_ingest_source]")
            ingest = executar_tool_core("media_ingest_source", {"nome": nome})
            if isinstance(ingest, dict) and ingest.get("ok"):
                print("[GoldenAI usando ferramenta: media_study_source]")
                result = executar_tool_core("media_study_source", {"source_id": (ingest.get("source") or {}).get("source_id", "")})
                resposta = _formatar_media_study_result(result)
            else:
                resposta = str(ingest)
    elif "hipotese" in texto or "hipótese" in texto:
        claims = media_get_claims()
        candidate = next(
            (
                claim for claim in claims
                if claim.get("claim_kind") in ("RULE", "HYPOTHESIS", "QUANTITATIVE_CLAIM")
                and not (claim.get("metadata") or {}).get("prompt_injection_like")
            ),
            claims[0] if claims else {},
        )
        claim_id = candidate.get("claim_id", "")
        result = executar_tool_core("media_claim_to_hypothesis", {"claim_id": claim_id})
        resposta = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        query = re.sub(r"(?i)(ele falou alguma coisa sobre|em que momento ele falou da|em que momento|quais regras esse autor ensinou|resuma este material|resuma esse material|voltando ao material|de onde veio essa afirmacao|de onde veio essa afirmação)", "", pergunta)
        query = re.sub(r"(?is)\[STUDIO_CONTEXT\].*?\[/STUDIO_CONTEXT\]", "", query).strip(" ?.:\n") or "stop entrada regra ema20"
        rows = executar_tool_core("media_search_source", {"query": query, "source_id": MEDIA_LAST_SOURCE_ID or "", "limit": 10})
        resposta = _formatar_media_busca(rows)
    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


def _agent_orchestrator():
    if not AgentOrchestrator:
        raise RuntimeError("AgentOrchestrator indisponivel.")
    return AgentOrchestrator(ROOT_GOLDENAI, audit_logger=CORE_AUDIT_LOGGER)


def agent_orchestrate(description="", context=None, review=False):
    record = _agent_orchestrator().execute(description, context or {}, review=bool(review))
    return record.__dict__


def pergunta_pede_orquestrador(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("explique python", "o que e python", "o que é python")):
        return False
    termos = (
        "orquestre", "orquestrador", "agente", "especialista",
        "analise essa estrategia, teste e revise", "analise essa estrategia teste e revise",
        "revise essa alteracao", "revise essa alteração", "resultado estatisticamente confiavel",
        "resultado estatisticamente confiável",
    )
    return any(t in texto for t in termos)


def _formatar_agent_record(record):
    if not isinstance(record, dict):
        return str(record)
    selected = record.get("selected_agents") or []
    results = record.get("results") or []
    if not selected:
        return "Conversa geral; nenhum especialista foi necessario."
    linhas = []
    if len(selected) == 1:
        linhas.append(f"Especialista: {selected[0]}")
    else:
        linhas.append("Especialistas: " + " -> ".join(selected))
    for result in results:
        evidence = f" ({result.get('evidence_level')})" if result.get("evidence_level") else ""
        linhas.append(f"- {result.get('agent')}: {result.get('summary')}{evidence}")
    if record.get("conflicts"):
        linhas.append("Conflitos preservados: " + "; ".join(record.get("conflicts")))
    status = record.get("status")
    if status:
        linhas.append(f"Status: {status}")
    return "\n".join(linhas)


def responder_orquestrador_chat(pergunta):
    if not pergunta_pede_orquestrador(pergunta):
        return False
    result = executar_tool_core("agent_orchestrate", {"description": pergunta, "context": {}, "review": "revis" in normalizar_texto_intencao(pergunta)})
    resposta = _formatar_agent_record(result)
    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


def _market_analysis_id_from_result(resultado):
    if isinstance(resultado, dict):
        return resultado.get("analysis_id") or resultado.get("report", {}).get("analysis_id")
    return None


def _market_part(part, analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    if not report:
        return data
    return report.get(part)


def market_get_snapshot(analysis_id=""):
    return _market_part("snapshots", analysis_id)


def market_get_regime(analysis_id=""):
    return _market_part("inferred", analysis_id)


def market_get_multitimeframe_context(analysis_id=""):
    return _market_part("multi_timeframe", analysis_id)


def market_get_structure(analysis_id=""):
    return _market_part("structure", analysis_id)


def market_get_observations(analysis_id=""):
    return _market_part("observed", analysis_id)


def market_get_signals(analysis_id=""):
    return _market_part("hypotheses", analysis_id)


def market_hypothesis_to_strategy_spec(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    if not report:
        return data
    hipoteses = report.get("hypotheses") or []
    sinal = hipoteses[0] if hipoteses else {}
    spec = {
        "name": "Market hypothesis",
        "version": "1.0",
        "description": "Hipotese conceitual gerada a partir de Market V1; exige validacao Quant antes de qualquer conclusao.",
        "symbol": report.get("symbol"),
        "timeframe": sinal.get("timeframe", ""),
        "entry_logic_identifier": "market_context_placeholder",
        "exit_logic_identifier": "hold_bars",
        "parameters": {
            "market_analysis_id": data.get("analysis_id") if isinstance(data, dict) else analysis_id,
            "alignment": (report.get("multi_timeframe") or {}).get("alignment"),
            "signal": sinal.get("signal", "NO_DIRECTIONAL_CONTEXT"),
        },
        "unknowns": {
            "validation_status": "NOT_BACKTESTED",
            "permission_required": "quant_backtest_before_use",
        },
    }
    _market_audit("MARKET_RESULT_READ", "COMPLETED", "market_hypothesis_to_strategy_spec", "NOT_BACKTESTED")
    return spec


def pergunta_pede_market(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("nao quero falar de mercado", "nao vamos falar de mercado", "vamos falar sobre carros")):
        return False
    if any(t in texto for t in ("o que e tendencia", "o que significa volatilidade", "me explique suporte", "me explique resistencia")):
        return False
    termos_dataset = ("este dataset", "esse dataset", "dataset de mercado", "estes dados", "esses dados", ".csv")
    termos_market = (
        "regime desse periodo", "regime da analise", "tendencia ou range",
        "timeframes estao alinhados", "timeframes estavam alinhados", "estruturas foram detectadas",
        "observacoes", "sinal de compra", "sinal potencial", "analise de mercado",
        "ultima analise de mercado", "analise anterior", "voltando a analise",
        "transforme essa hipotese", "strategysp", "strategy spec", "validado", "validated",
    )
    return any(t in texto for t in termos_dataset) or any(t in texto for t in termos_market)


def _resposta_market_sem_dataset(pergunta):
    idioma = detectar_idioma_resposta(pergunta)
    return (
        "Please select or provide an authorized CSV market dataset first. I will not invent a dataset."
        if idioma == "en"
        else "Preciso que voce selecione ou indique um dataset CSV de mercado autorizado primeiro. Nao vou inventar um dataset."
    )


def _formatar_lista_regimes(regimes):
    if not regimes:
        return "Regime: nao encontrado."
    linhas = []
    for item in regimes:
        linhas.append(f"- {item.get('timeframe')}: {item.get('regime')} ({_evidence_text(item.get('evidence_level'))}, confianca {item.get('confidence')})")
    return "Regime\n" + "\n".join(linhas)


def _evidence_text(value):
    texto = str(value or "")
    if "." in texto:
        return texto.rsplit(".", 1)[-1]
    return texto


def _formatar_market_resposta(pergunta, resultado):
    texto = normalizar_texto_intencao(pergunta)
    report = _market_report_from_tool_result(resultado)
    if not report:
        return str(resultado.get("erro", resultado)) if isinstance(resultado, dict) else str(resultado)
    regimes = report.get("inferred") or []
    mtf = report.get("multi_timeframe") or {}
    estruturas = report.get("structure") or []
    observados = report.get("observed") or []
    hipoteses = report.get("hypotheses") or []
    limites = report.get("limitations") or []
    if "regime" in texto and "analise" not in texto:
        return _formatar_lista_regimes(regimes)
    if "timeframe" in texto or "alinhad" in texto:
        return f"Multi-timeframe: alinhamento {mtf.get('alignment')}. Conflitos: {', '.join(mtf.get('conflicts') or []) or 'nenhum'}."
    if "estrutura" in texto:
        partes = [f"- {e.get('timeframe')}: tendencia basica {e.get('basic_trend')}, suporte {e.get('support')}, resistencia {e.get('resistance')}" for e in estruturas]
        return "Estrutura detectada\n" + "\n".join(partes)
    if "observa" in texto:
        return "Observado\n" + "\n".join(f"- {o.get('timeframe')}: {o.get('statement')}" for o in observados[:8])
    if "sinal" in texto or "compra" in texto:
        return "Hipoteses/sinais\n" + "\n".join(f"- {h.get('timeframe')}: {h.get('signal')} ({_evidence_text(h.get('evidence_level'))}; nao validado por Quant)" for h in hipoteses)
    if "validado" in texto or "validated" in texto:
        return "Nao. Esta analise Market gera observacoes, inferencias e hipoteses. Nenhum sinal foi marcado como VALIDATED sem teste Quant correspondente."
    if ("strategysp" in texto or "strategy spec" in texto) and any(t in texto for t in ("teste", "testar", "backtest")):
        return "Nao rodei backtest pelo Market. Para testar estatisticamente, use o fluxo Quant explicitamente; Market apenas prepara a hipotese/StrategySpec."
    if "strategysp" in texto or "strategy spec" in texto or "transforme essa hipotese" in texto:
        return "StrategySpec preparado para teste Quant posterior:\n" + json.dumps(market_hypothesis_to_strategy_spec(), ensure_ascii=False, indent=2)
    return (
        f"Analise Market concluida: {report.get('symbol')}.\n\n"
        f"{_formatar_lista_regimes(regimes)}\n\n"
        f"Multi-timeframe: alinhamento {mtf.get('alignment')}.\n\n"
        "Estrutura\n"
        + "\n".join(f"- {e.get('timeframe')}: {e.get('basic_trend')}, suporte {e.get('support')}, resistencia {e.get('resistance')}" for e in estruturas)
        + "\n\nObservado\n"
        + "\n".join(f"- {o.get('timeframe')}: {o.get('statement')}" for o in observados[:6])
        + "\n\nHipoteses/sinais\n"
        + "\n".join(f"- {h.get('timeframe')}: {h.get('signal')} ({_evidence_text(h.get('evidence_level'))}; nao validado)" for h in hipoteses)
        + "\n\nLimitacoes\n"
        + "\n".join(f"- {l}" for l in limites[:4])
    )


def responder_market_chat(pergunta):
    if not pergunta_pede_market(pergunta):
        return False
    texto = normalizar_texto_intencao(pergunta)
    caminho_contexto = extrair_studio_context_path(pergunta)
    analysis_id = MARKET_LAST_ANALYSIS_ID
    if ("strategysp" in texto or "strategy spec" in texto) and any(t in texto for t in ("teste", "testar", "backtest")):
        resposta = "Nao rodei backtest pelo Market. Para testar estatisticamente, use o fluxo Quant explicitamente; Market apenas prepara a hipotese/StrategySpec."
        historico.append({"role": "user", "content": pergunta})
        historico.append({"role": "assistant", "content": resposta})
        print()
        print("Golden AI:")
        print(resposta)
        print()
        return True
    if "strategysp" in texto or "strategy spec" in texto or "transforme essa hipotese" in texto:
        resultado = market_hypothesis_to_strategy_spec(analysis_id or "")
        globals()["QUANT_LAST_STRATEGY_SPEC"] = resultado if isinstance(resultado, dict) and not resultado.get("erro") else None
        resposta = "StrategySpec preparado para teste Quant posterior:\n" + json.dumps(resultado, ensure_ascii=False, indent=2)
        historico.append({"role": "user", "content": pergunta})
        historico.append({"role": "assistant", "content": resposta})
        print()
        print("Golden AI:")
        print(resposta)
        print()
        return True
    if "ultima analise" in texto or "analise anterior" in texto or "voltando a analise" in texto:
        resultado = market_get_analysis(analysis_id or "")
    elif any(t in texto for t in ("regime", "timeframe", "alinhad", "estrutura", "observa", "sinal", "validado")) and analysis_id:
        resultado = market_get_analysis(analysis_id)
    else:
        if not caminho_contexto:
            print()
            print("Golden AI:")
            print(_resposta_market_sem_dataset(pergunta))
            print()
            return True
        nome = nome_para_projetos(caminho_contexto)
        print()
        print("[GoldenAI usando ferramenta: market_analyze_dataset]")
        resultado = executar_tool_core("market_analyze_dataset", {"nome": nome, "symbol": "DATASET", "timeframe": "H1"})
    resposta = _formatar_market_resposta(pergunta, resultado)
    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


QUANT_LAST_EXPERIMENT_ID = None
QUANT_PREVIOUS_EXPERIMENT_ID = None
QUANT_LAST_STRATEGY_SPEC = None
QUANT_LAST_DATASET_PATH = None


def _quant_service():
    if not QuantService:
        raise RuntimeError("Quant V1 indisponivel.")
    return QuantService(ROOT_GOLDENAI)


def _quant_audit(action_type, status, target="", detail=""):
    if not CORE_AUDIT_LOGGER:
        return
    try:
        CORE_AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CORE_SESSION_ID,
            "agent": "golden_ai.quant_chat.v1",
            "target": str(target or ""),
            "result": _core_resumir(detail),
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


def _csv_rows_autorizado(nome):
    caminho = caminho_seguro(nome)
    if caminho is None:
        raise ValueError("dataset fora da pasta autorizada ou nome invalido")
    if not os.path.isfile(caminho):
        raise FileNotFoundError("dataset nao encontrado")
    if os.path.splitext(caminho)[1].lower() != ".csv":
        raise ValueError("Quant Chat V1 aceita apenas CSV local autorizado nesta rota")
    if LocalCsvMarketDataAdapter is None:
        raise RuntimeError("Adaptador CSV indisponivel")
    return LocalCsvMarketDataAdapter(caminho, "H1").load()["H1"], caminho


def _strategy_spec_from_dict(data):
    if isinstance(data, StrategySpec):
        return data
    data = dict(data or {})
    if data.get("entry_logic_identifier") == "market_context_placeholder":
        signal = str((data.get("parameters") or {}).get("signal", ""))
        if "SHORT" in signal:
            entry = "close_below_open"
        elif "LONG" in signal:
            entry = "close_above_open"
        else:
            entry = "never"
    else:
        entry = data.get("entry_logic_identifier") or "never"
    params = dict(data.get("parameters") or {})
    params.setdefault("hold_bars", 1)
    return StrategySpec(
        strategy_id=data.get("strategy_id", ""),
        name=data.get("name", "Chat StrategySpec"),
        version=data.get("version", "1.0"),
        description=data.get("description", "StrategySpec executada explicitamente via Quant Chat V1."),
        parameters=params,
        entry_logic_identifier=entry,
        exit_logic_identifier=data.get("exit_logic_identifier", "hold_bars"),
        created_at=data.get("created_at", ""),
        symbol=data.get("symbol", "DATASET"),
        timeframe=data.get("timeframe", "H1") or "H1",
        unknowns=data.get("unknowns", {}),
    )


def quant_run_backtest(nome="", strategy_spec=None, initial_capital=10000.0, quantity=1.0, spread=0.0, commission=0.0, slippage=0.0):
    global QUANT_LAST_EXPERIMENT_ID, QUANT_PREVIOUS_EXPERIMENT_ID, QUANT_LAST_STRATEGY_SPEC, QUANT_LAST_DATASET_PATH
    _quant_audit("QUANT_EXPERIMENT_REQUESTED", "REQUESTED", nome, "run_backtest")
    try:
        rows, caminho = _csv_rows_autorizado(nome)
        service = _quant_service()
        spec_obj = _strategy_spec_from_dict(strategy_spec or QUANT_LAST_STRATEGY_SPEC)
        dataset = service.dataset_from_rows(rows, f"csv:{os.path.basename(caminho)}", spec_obj.symbol or "DATASET", spec_obj.timeframe or "H1")
        cost_model = CostModel(spread=float(spread), commission=float(commission), slippage=float(slippage))
        backtest_spec = build_backtest_spec(
            spec_obj,
            dataset,
            initial_capital=float(initial_capital),
            quantity=float(quantity),
            cost_model=cost_model,
            seed=1,
        )
        _quant_audit("QUANT_EXPERIMENT_STARTED", "RUNNING", dataset.dataset_id, backtest_spec.config_hash())
        experiment_id, payload = service.run_backtest(backtest_spec, rows)
        QUANT_PREVIOUS_EXPERIMENT_ID = QUANT_LAST_EXPERIMENT_ID
        QUANT_LAST_EXPERIMENT_ID = experiment_id
        QUANT_LAST_STRATEGY_SPEC = strategy_spec or QUANT_LAST_STRATEGY_SPEC
        QUANT_LAST_DATASET_PATH = caminho
        result = payload["result"]
        _quant_audit("QUANT_EXPERIMENT_COMPLETED", "COMPLETED", experiment_id, payload.get("result_hash", ""))
        memory_id = _memory_store_quant_experiment(experiment_id, backtest_spec, result, payload.get("artifact_dir", ""))
        return {
            "ok": True,
            "experiment_id": experiment_id,
            "knowledge_id": memory_id,
            "status": "TESTED",
            "metrics": result.metrics.__dict__,
            "trades": [trade.__dict__ for trade in result.trades],
            "equity_curve": result.equity_curve,
            "dataset": dataset.__dict__,
            "costs": cost_model.__dict__,
            "initial_capital": backtest_spec.initial_capital,
            "position_sizing": backtest_spec.position_sizing,
            "artifact_dir": payload.get("artifact_dir"),
            "result_hash": payload.get("result_hash"),
            "limitations": result.limitations,
        }
    except Exception as erro:
        _quant_audit("QUANT_EXPERIMENT_FAILED", "FAILED", nome, str(erro))
        return {"ok": False, "erro": str(erro)}


def quant_get_experiment(experiment_id=""):
    experiment_id = experiment_id or QUANT_LAST_EXPERIMENT_ID
    if not experiment_id:
        return {"ok": False, "erro": "experimento Quant nao encontrado"}
    data = _quant_service().repo.get_backtest(experiment_id)
    _quant_audit("QUANT_RESULT_READ", "COMPLETED" if data else "FAILED", experiment_id, "experiment")
    return data or {"ok": False, "erro": "experimento Quant nao encontrado"}


def _quant_metrics_from_experiment(experiment_id=""):
    data = quant_get_experiment(experiment_id)
    if isinstance(data, dict) and data.get("metrics_json"):
        return json.loads(data["metrics_json"])
    return data


def quant_get_metrics(experiment_id=""):
    return _quant_metrics_from_experiment(experiment_id)


def quant_get_trades(experiment_id=""):
    data = quant_get_experiment(experiment_id)
    return data.get("trades", []) if isinstance(data, dict) else data


def quant_get_equity(experiment_id=""):
    data = quant_get_experiment(experiment_id)
    if not isinstance(data, dict) or not data.get("experiment_id"):
        return data
    artifact = Path(ROOT_GOLDENAI) / "data" / "experiments" / data["experiment_id"] / "equity.csv"
    if not artifact.exists():
        return []
    linhas = artifact.read_text(encoding="utf-8").splitlines()
    return linhas[:50]


def quant_list_experiments(limit=10):
    service = _quant_service()
    con = service.repo.connect()
    try:
        rows = con.execute(
            """
            SELECT experiment_id, strategy_hash, dataset_hash, backtest_hash, status, created_at
            FROM quant_backtests
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        _quant_audit("QUANT_RESULT_READ", "COMPLETED", "quant_list_experiments", f"count={len(rows)}")
        return [dict(row) for row in rows]
    finally:
        con.close()


def quant_compare_experiments(experiment_a="", experiment_b=""):
    global QUANT_PREVIOUS_EXPERIMENT_ID
    a = experiment_a or QUANT_PREVIOUS_EXPERIMENT_ID
    b = experiment_b or QUANT_LAST_EXPERIMENT_ID
    _quant_audit("QUANT_COMPARISON_REQUESTED", "REQUESTED", f"{a} vs {b}", "")
    if not a or not b or a == b:
        return {"ok": False, "erro": "comparacao exige dois experimentos distintos"}
    comparison = _quant_service().compare(a, b)
    return comparison.__dict__


def pergunta_pede_quant(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("agora vamos falar de carros", "vamos falar sobre carros", "nao quero falar de teste")):
        return False
    if any(t in texto for t in ("o que e backtest", "o que significa backtest")):
        return False
    if any(t in texto for t in ("esse regime parece interessante", "interessante", "parece bom", "gostei")):
        return False
    termos_execucao = ("teste essa strategy", "teste essa strategyspec", "rode o backtest", "faca um backtest", "faça um backtest", "execute essa strategyspec", "valide estatisticamente")
    termos_leitura = ("ultimo experimento", "resultado do ultimo experimento", "quantas operacoes", "quantas operações", "drawdown", "piores trades", "profit factor", "compare com", "validado", "validated")
    return any(t in texto for t in termos_execucao) or any(t in texto for t in termos_leitura)


def _formatar_quant_result(resultado):
    if not isinstance(resultado, dict):
        return str(resultado)
    if not resultado.get("ok", True):
        return resultado.get("erro", str(resultado))
    metrics = resultado.get("metrics") or {}
    dataset = resultado.get("dataset") or {}
    costs = resultado.get("costs") or {}
    return (
        "Experimento Quant concluido.\n\n"
        f"Experiment ID: {resultado.get('experiment_id')}\n"
        "Status: TESTED\n"
        f"Trades: {metrics.get('total_trades')}\n"
        f"Resultado liquido: {metrics.get('net_profit')}\n"
        f"Win rate: {metrics.get('win_rate')}\n"
        f"Expectancy: {metrics.get('expectancy')}\n"
        f"Profit factor: {metrics.get('profit_factor')}\n"
        f"Max drawdown: {metrics.get('max_drawdown_abs')}\n"
        f"Dataset: {dataset.get('source')} ({dataset.get('start')} -> {dataset.get('end')})\n"
        f"Custos: spread={costs.get('spread')}, commission={costs.get('commission')}, slippage={costs.get('slippage')}\n"
        f"Capital inicial: {resultado.get('initial_capital')}; position sizing: {resultado.get('position_sizing')}\n\n"
        "Resultado de backtest e evidencia TESTED, nao VALIDATED."
    )


def responder_quant_chat(pergunta):
    if not pergunta_pede_quant(pergunta):
        return False
    texto = normalizar_texto_intencao(pergunta)
    caminho_contexto = extrair_studio_context_path(pergunta)
    if any(t in texto for t in ("teste essa strategy", "teste essa strategyspec", "rode o backtest", "faca um backtest", "faça um backtest", "execute essa strategyspec", "valide estatisticamente")):
        if QUANT_LAST_STRATEGY_SPEC is None:
            spec = market_hypothesis_to_strategy_spec()
            if isinstance(spec, dict) and not spec.get("erro"):
                globals()["QUANT_LAST_STRATEGY_SPEC"] = spec
        if not caminho_contexto and not QUANT_LAST_DATASET_PATH:
            resposta = "Preciso que voce selecione ou indique um dataset CSV autorizado antes de rodar Quant. Nao vou inventar dataset nem parametros."
        else:
            nome = nome_para_projetos(caminho_contexto or QUANT_LAST_DATASET_PATH)
            print()
            print("[GoldenAI usando ferramenta: quant_run_backtest]")
            resultado = executar_tool_core("quant_run_backtest", {
                "nome": nome,
                "strategy_spec": QUANT_LAST_STRATEGY_SPEC,
                "initial_capital": 10000.0,
                "quantity": 1.0,
                "spread": 0.0,
                "commission": 0.0,
                "slippage": 0.0,
            })
            resposta = _formatar_quant_result(resultado)
    elif "quantas operacoes" in texto or "quantas operações" in texto:
        metrics = quant_get_metrics()
        resposta = f"O experimento atual teve {metrics.get('total_trades')} operacoes."
    elif "drawdown" in texto:
        metrics = quant_get_metrics()
        resposta = f"Max drawdown do experimento atual: {metrics.get('max_drawdown_abs')}."
    elif "piores trades" in texto:
        trades = quant_get_trades()
        piores = sorted(trades, key=lambda item: item.get("net_pnl", 0))[:5] if isinstance(trades, list) else []
        resposta = "Piores trades\n" + "\n".join(f"- {t.get('trade_id')}: net_pnl={t.get('net_pnl')}, entrada={t.get('entry_time')}, saida={t.get('exit_time')}" for t in piores)
    elif "validado" in texto:
        resposta = "Nao. O experimento atual esta TESTED por backtest local, mas isso nao e VALIDATED nem garantia futura."
    elif "profit factor" in texto:
        metrics = quant_get_metrics()
        resposta = f"Profit factor do experimento atual: {metrics.get('profit_factor')}."
    elif "compare com" in texto:
        resposta = json.dumps(quant_compare_experiments(), ensure_ascii=False, indent=2)
    else:
        resposta = json.dumps(quant_get_experiment(), ensure_ascii=False, indent=2)
    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True


def criar_backup(nome):
    caminho = caminho_seguro(nome)

    if caminho is None:
        return None, "Acesso negado."

    if not os.path.isfile(caminho):
        return None, f"Arquivo nao encontrado: {nome}"

    try:
        os.makedirs(PASTA_BACKUPS, exist_ok=True)

        base = os.path.basename(caminho)
        raiz, extensao = os.path.splitext(base)

        horario = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        destino = os.path.join(
            PASTA_BACKUPS,
            f"{raiz}_BACKUP_{horario}{extensao}"
        )

        shutil.copy2(caminho, destino)

        return destino, None

    except Exception as erro:
        return None, f"Erro ao criar backup: {erro}"


def restaurar_backup(nome, backup):
    caminho = caminho_seguro(nome)

    if caminho is None:
        return False, "Acesso negado."

    if not backup or not os.path.isfile(backup):
        return False, "Backup nao encontrado."

    try:
        shutil.copy2(backup, caminho)
        return True, f"Rollback concluido: {backup}"

    except Exception as erro:
        return False, f"Erro no rollback: {erro}"


def escrever_arquivo(nome, conteudo):
    caminho = caminho_seguro(nome)

    if caminho is None:
        return False, None, "Acesso negado."

    if not isinstance(conteudo, str):
        return False, None, "Conteudo invalido."

    try:
        os.makedirs(
            os.path.dirname(caminho),
            exist_ok=True
        )

        atual = None

        if os.path.isfile(caminho):
            with open(
                caminho,
                "r",
                encoding="utf-8",
                errors="replace"
            ) as arquivo:
                atual = arquivo.read()

            if atual == conteudo:
                return False, None, "SEM ALTERACAO"

        backup = None

        if atual is not None:
            backup, erro_backup = criar_backup(nome)

            if erro_backup:
                return False, None, erro_backup

        with open(
            caminho,
            "w",
            encoding="utf-8",
            newline=""
        ) as arquivo:
            arquivo.write(conteudo)

        return (
            True,
            backup,
            f"Arquivo salvo: {caminho}"
        )

    except Exception as erro:
        return False, None, f"Erro ao escrever: {erro}"


# ============================================================
# METAEDITOR
# ============================================================

def ler_log(caminho):
    if not os.path.isfile(caminho):
        return "Log nao encontrado."

    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read()

        if (
            dados.startswith(b"\xff\xfe")
            or dados.startswith(b"\xfe\xff")
        ):
            return dados.decode(
                "utf-16",
                errors="replace"
            ).strip()

        try:
            return dados.decode("utf-8").strip()

        except UnicodeDecodeError:
            return dados.decode(
                "cp1252",
                errors="replace"
            ).strip()

    except Exception as erro:
        return f"Erro ao ler log: {erro}"


def compilar_mql5(nome):
    caminho = caminho_seguro(nome)

    if caminho is None:
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": "Acesso negado.",
            "caminho_log": None
        }

    if not os.path.isfile(caminho):
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": f"Arquivo nao encontrado: {nome}",
            "caminho_log": None
        }

    if not caminho.lower().endswith(".mq5"):
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": "Somente .mq5 pode ser compilado.",
            "caminho_log": None
        }

    if not os.path.isfile(METAEDITOR):
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": f"MetaEditor nao encontrado: {METAEDITOR}",
            "caminho_log": None
        }

    try:
        os.makedirs(PASTA_LOGS, exist_ok=True)

        base = os.path.splitext(
            os.path.basename(caminho)
        )[0]

        horario = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        caminho_log = os.path.join(
            PASTA_LOGS,
            f"COMPILACAO_{base}_{horario}.log"
        )

        comando = [
            METAEDITOR,
            f"/compile:{caminho}",
            f"/log:{caminho_log}"
        ]

        subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=60
        )

        log = ler_log(caminho_log)

        match = re.search(
            r"Result:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?",
            log,
            re.IGNORECASE
        )

        if match:
            errors = int(match.group(1))
            warnings = int(match.group(2))
        else:
            errors = -1
            warnings = -1

        return {
            "ok": errors == 0 and warnings == 0,
            "errors": errors,
            "warnings": warnings,
            "log": log,
            "caminho_log": caminho_log
        }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": "Compilacao excedeu 60 segundos.",
            "caminho_log": None
        }

    except Exception as erro:
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": f"Erro ao compilar: {erro}",
            "caminho_log": None
        }


def _core_resumir(valor, limite=600):
    texto = str(valor)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) > limite:
        return texto[:limite] + "...[truncado]"
    return texto


def _core_tool_target(tool_name, arguments):
    args = arguments or {}
    if tool_name in ("get_current_datetime", "get_system_info", "list_processes"):
        return ""
    if tool_name == "get_disk_usage":
        return str(args.get("path", r"C:\GoldenAI"))
    if tool_name in ("find_installed_app", "launch_allowed_app"):
        return str(args.get("name", ""))
    if tool_name == "open_folder":
        return str(args.get("path", ""))
    if tool_name in ("find_mt5_installations", "get_mt5_status", "list_mt5_terminals", "list_mt5_eas"):
        return str(Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal")
    if tool_name == "read_mt5_file":
        return str(args.get("path", ""))
    if tool_name == "listar_projetos":
        return PASTA_PROJETOS
    if tool_name in ("ler_arquivo", "arquivo_metadados", "market_analyze_dataset", "escrever_arquivo", "compilar_mql5"):
        return caminho_seguro(args.get("nome", "")) or str(args.get("nome", ""))
    if tool_name.startswith("market_"):
        return ""
    if tool_name == "quant_run_backtest":
        return caminho_seguro(args.get("nome", "")) or str(args.get("nome", ""))
    if tool_name.startswith("quant_"):
        return ""
    if tool_name.startswith("memory_"):
        return ""
    if tool_name == "media_ingest_source":
        return extrair_studio_context_path(str(args.get("nome", ""))) or str(args.get("nome", ""))
    if tool_name.startswith("media_"):
        return ""
    if tool_name.startswith("agent_"):
        return ""
    if tool_name in ("listar_eas_mt5", "ler_arquivo_mt5", "copiar_ea_mt5_para_teste"):
        return PASTA_MT5_EXPERTS
    if tool_name == "excluir_backup":
        return str(args.get("backup", PASTA_BACKUPS))
    if tool_name in ("document_extract", "audio_transcribe", "video_analyze"):
        return caminho_seguro(args.get("nome", "")) or str(args.get("nome", ""))
    if tool_name == "vision_analyze_image":
        return caminho_seguro(args.get("imagem", "")) or str(args.get("imagem", ""))
    if tool_name in ("browser_search", "browser_fetch", "memory_vector_store", "memory_vector_search"):
        return ""
    return ""


def _core_tool_permission_class(tool_name):
    classes = {
        "listar_projetos": "READ",
        "ler_arquivo": "READ",
        "arquivo_metadados": "READ",
        "market_analyze_dataset": "READ",
        "market_get_snapshot": "READ",
        "market_get_regime": "READ",
        "market_get_multitimeframe_context": "READ",
        "market_get_structure": "READ",
        "market_get_observations": "READ",
        "market_get_signals": "READ",
        "market_get_analysis": "READ",
        "market_list_analyses": "READ",
        "market_hypothesis_to_strategy_spec": "READ",
        "quant_run_backtest": "READ",
        "quant_get_experiment": "READ",
        "quant_get_metrics": "READ",
        "quant_get_trades": "READ",
        "quant_get_equity": "READ",
        "quant_compare_experiments": "READ",
        "quant_list_experiments": "READ",
        "memory_store_knowledge": "READ",
        "memory_search_knowledge": "READ",
        "memory_get_knowledge": "READ",
        "memory_find_related_experiments": "READ",
        "memory_get_topic_summary": "READ",
        "memory_link_experiment": "READ",
        "media_ingest_source": "READ",
        "media_get_source": "READ",
        "media_list_sources": "READ",
        "media_get_segments": "READ",
        "media_search_source": "READ",
        "media_extract_claims": "READ",
        "media_get_claims": "READ",
        "media_study_source": "READ",
        "media_get_study_result": "READ",
        "media_claim_to_hypothesis": "READ",
        "media_get_claim_origin": "READ",
        "agent_orchestrate": "READ",
        "listar_eas_mt5": "READ",
        "ler_arquivo_mt5": "READ",
        "copiar_ea_mt5_para_teste": "WRITE",
        "escrever_arquivo": "WRITE",
        "compilar_mql5": "EXECUTE",
        "excluir_backup": "CRITICAL",
        "get_current_datetime": "READ",
        "get_system_info": "READ_EXTERNAL_SAFE",
        "get_disk_usage": "READ_EXTERNAL_SAFE",
        "list_processes": "READ_EXTERNAL_SAFE",
        "find_installed_app": "READ_EXTERNAL_SAFE",
        "find_mt5_installations": "READ_EXTERNAL_SAFE",
        "get_mt5_status": "READ_EXTERNAL_SAFE",
        "list_mt5_terminals": "READ_EXTERNAL_SAFE",
        "list_mt5_eas": "READ_EXTERNAL_SAFE",
        "read_mt5_file": "READ_EXTERNAL_SAFE",
        "launch_allowed_app": "EXECUTE",
        "open_folder": "EXECUTE",
        "internet_search": "READ",
        "internet_fetch": "READ",
        "internet_download": "WRITE",
        "browser_search": "READ",
        "browser_fetch": "READ",
        "document_extract": "READ",
        "audio_transcribe": "READ",
        "video_analyze": "READ",
        "memory_vector_store": "READ",
        "memory_vector_search": "READ",
        "vision_analyze_image": "READ",
        "executar_opencode": "EXECUTE",
    }
    return classes.get(tool_name, "CRITICAL")


def _core_audit(action_type, tool_name, permission_class, target, status, arguments=None, result="", error="", duration_ms=None):
    if not CORE_AUDIT_LOGGER:
        return
    try:
        CORE_AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CORE_SESSION_ID,
            "agent": "golden_ai.py",
            "tool": tool_name,
            "permission_class": permission_class,
            "target": str(target or ""),
            "input_summary": _core_resumir(arguments or {}),
            "result": _core_resumir(result),
            "error": _core_resumir(error),
            "duration_ms": duration_ms,
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


def check_tool_permission(tool_name, arguments=None):
    permission_class = _core_tool_permission_class(tool_name)
    target = _core_tool_target(tool_name, arguments or {})

    if not CORE_PERMISSION_MANAGER:
        return True, "Core V3 indisponivel; compatibilidade legada ativa.", permission_class, target

    if permission_class == "READ":
        if not target:
            return True, "READ permitido para consulta local sem caminho.", permission_class, target
        decision = CORE_PERMISSION_MANAGER.can_read(target)
        return decision.allowed, decision.reason, permission_class, target

    if permission_class == "READ_EXTERNAL_SAFE":
        purpose_by_tool = {
            "get_system_info": "system_info",
            "get_disk_usage": "disk_usage",
            "list_processes": "process_list",
            "find_installed_app": "find_installed_app",
            "find_mt5_installations": "find_installed_app",
            "get_mt5_status": "mt5_status",
            "list_mt5_terminals": "mt5_read",
            "list_mt5_eas": "mt5_read",
            "read_mt5_file": "mt5_read",
        }
        purpose = purpose_by_tool.get(tool_name, "")
        caminho = target or None
        if tool_name in ("get_system_info", "list_processes", "find_installed_app", "get_mt5_status", "find_mt5_installations"):
            caminho = None
        decision = CORE_PERMISSION_MANAGER.can_read_external_safe(purpose, caminho)
        return decision.allowed, decision.reason, permission_class, target

    if permission_class == "WRITE":
        # Delega ao PermissionManager que consulto o ExecutionService;
        # o modo READ_ONLY continua bloqueando, mas AUTO_SAFE/FULL podem
        # autorizar conforme o risco classificado.
        if tool_name == "internet_download":
            url = (arguments or {}).get("url", "")
            dest = (arguments or {}).get("dest_dir", "")
            decision = CORE_PERMISSION_MANAGER.can_internet_download(url, dest)
        else:
            decision = CORE_PERMISSION_MANAGER.can_write(target, explicit_authorization=False)
        return decision.allowed, decision.reason, permission_class, target

    if permission_class == "CRITICAL":
        return False, "ACAO BLOQUEADA: operacao critica nao permitida.", permission_class, target

    if permission_class == "EXECUTE":
        args = arguments or {}
        if tool_name == "launch_allowed_app":
            decision = CORE_PERMISSION_MANAGER.can_launch_allowed_app(args.get("name", ""))
            return decision.allowed, decision.reason, permission_class, target
        if tool_name == "open_folder":
            decision = CORE_PERMISSION_MANAGER.can_open_folder(args.get("path", ""))
            return decision.allowed, decision.reason, permission_class, target
        caminho = str(target or "")
        read_decision = CORE_PERMISSION_MANAGER.can_read(caminho)
        if not read_decision.allowed:
            return False, read_decision.reason, permission_class, target
        if tool_name == "compilar_mql5" and caminho.lower().endswith(".mq5"):
            return True, "EXECUTE permitido somente para compilacao MQL5 existente.", permission_class, target
        return False, "EXECUTE bloqueado por politica.", permission_class, target

    return False, "Classe de permissao desconhecida.", permission_class, target


def executar_tool_core(tool_name, arguments=None):
    args = arguments or {}
    inicio = time.time()
    permission_class = _core_tool_permission_class(tool_name)
    target = _core_tool_target(tool_name, args)
    _core_audit("TOOL_REQUESTED", tool_name, permission_class, target, "REQUESTED", args)
    if str(tool_name).startswith("market_"):
        _market_audit("MARKET_TOOL_REQUESTED", "REQUESTED", target, tool_name)
    if str(tool_name).startswith("quant_"):
        _quant_audit("QUANT_TOOL_REQUESTED", "REQUESTED", target, tool_name)
    if str(tool_name).startswith("memory_"):
        _memory_audit("MEMORY_TOOL_REQUESTED", "REQUESTED", target, tool_name)
    if str(tool_name).startswith("media_"):
        _media_audit("MEDIA_TOOL_REQUESTED", "REQUESTED", target, tool_name)

    if not CORE_TOOL_REGISTRY:
        _core_audit("TOOL_FAILED", tool_name, permission_class, target, "FAILED", args, error="Core ToolRegistry indisponivel")
        raise RuntimeError("Core ToolRegistry indisponivel")

    try:
        tool = CORE_TOOL_REGISTRY.get(tool_name)
    except Exception as erro:
        _core_audit("TOOL_FAILED", tool_name, permission_class, target, "FAILED", args, error=erro)
        raise

    allowed, reason, permission_class, target = check_tool_permission(tool_name, args)
    if not allowed:
        _core_audit("TOOL_DENIED", tool_name, permission_class, target, "DENIED", args, error=reason)
        return f"{reason}"

    _core_audit("TOOL_ALLOWED", tool_name, permission_class, target, "ALLOWED", args, result=reason)
    if str(tool_name).startswith("market_"):
        _market_audit("MARKET_TOOL_ALLOWED", "ALLOWED", target, tool_name)
    if str(tool_name).startswith("quant_"):
        _quant_audit("QUANT_TOOL_ALLOWED", "ALLOWED", target, tool_name)
    if str(tool_name).startswith("memory_"):
        _memory_audit("MEMORY_TOOL_ALLOWED", "ALLOWED", target, tool_name)
    if str(tool_name).startswith("media_"):
        _media_audit("MEDIA_TOOL_ALLOWED", "ALLOWED", target, tool_name)

    try:
        resultado = tool.handler(**args)
        duracao = int((time.time() - inicio) * 1000)
        detalhe = resultado
        if tool_name == "compilar_mql5" and isinstance(resultado, dict):
            detalhe = {
                "ok": resultado.get("ok"),
                "errors": resultado.get("errors"),
                "warnings": resultado.get("warnings"),
                "caminho_log": resultado.get("caminho_log"),
                "metaeditor": METAEDITOR,
            }
        _core_audit("TOOL_COMPLETED", tool_name, permission_class, target, "COMPLETED", args, result=detalhe, duration_ms=duracao)
        return resultado
    except Exception as erro:
        duracao = int((time.time() - inicio) * 1000)
        _core_audit("TOOL_FAILED", tool_name, permission_class, target, "FAILED", args, error=erro, duration_ms=duracao)
        return f"Erro ao executar ferramenta {tool_name}: {erro}"


def _executar_opencode_cli(modelo, tarefa, diretorio, timeout_segundos):
    """Invoca o CLI do OpenCode em modo headless e captura a saida JSON-lines."""
    cmd_path = None
    if CORE_SETTINGS is not None:
        try:
            cmd_path = getattr(CORE_SETTINGS, "opencode_cmd", "") or None
        except Exception:
            cmd_path = None
    if not cmd_path or not os.path.isfile(cmd_path):
        return {
            "ok": False,
            "erro": f"CLI do OpenCode nao encontrado: {cmd_path}",
            "texto": "",
            "modelo": modelo,
            "duracao_segundos": 0.0,
        }

    os.makedirs(diretorio, exist_ok=True)

    # Tarefa grande vai por ARQUIVO (evita o limite de linha de comando do
    # Windows, ~8191 chars via cmd). O CLI recebe apenas um ponteiro curto.
    arquivo_tarefa = os.path.join(diretorio, "tarefa_golden.txt")
    try:
        with open(arquivo_tarefa, "w", encoding="utf-8", newline="") as f:
            f.write(tarefa)
    except Exception as exc:
        return {
            "ok": False,
            "erro": f"Falha ao gravar tarefa para OpenCode: {type(exc).__name__}: {exc}",
            "texto": "",
            "modelo": modelo,
            "duracao_segundos": 0.0,
        }

    mensagem = (
        "Execute a tarefa de programacao descrita no arquivo "
        "tarefa_golden.txt deste diretorio. Ao terminar, relate o resultado."
    )

    args = ["cmd", "/c", cmd_path, "run", "--format", "json", "--auto",
            "--model", modelo, "--dir", diretorio, mensagem]

    inicio = datetime.now()
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_segundos,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "erro": f"Timeout apos {timeout_segundos}s",
            "texto": "",
            "modelo": modelo,
            "duracao_segundos": (datetime.now() - inicio).total_seconds(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "erro": f"{type(exc).__name__}: {exc}",
            "texto": "",
            "modelo": modelo,
            "duracao_segundos": (datetime.now() - inicio).total_seconds(),
        }

    duracao = (datetime.now() - inicio).total_seconds()

    texto = ""
    erro = None
    terminou = None
    for linha in (proc.stdout or "").splitlines():
        try:
            evt = json.loads(linha)
        except Exception:
            continue
        tipo = evt.get("type")
        if tipo == "text":
            parte = evt.get("part", {})
            t = parte.get("text")
            if isinstance(t, str) and t.strip():
                texto = (texto + "\n" if texto else "") + t.strip()
        elif tipo == "error":
            err = evt.get("error", {})
            erro = err.get("message") or str(err.get("data", "")) or "Erro do OpenCode"
        elif tipo == "step_finish":
            terminou = evt.get("part", {}).get("reason")

    if proc.returncode != 0:
        stderr_txt = (proc.stderr or "").strip()
        erro = (erro or f"Exit code {proc.returncode}")
        if stderr_txt:
            erro += " | " + stderr_txt[:300]

    ok = proc.returncode == 0 and not erro and terminou == "stop" and bool(texto.strip())

    return {
        "ok": bool(ok),
        "erro": None if ok else (erro or "Resposta vazia ou nao concluida."),
        "texto": texto,
        "modelo": modelo,
        "duracao_segundos": round(duracao, 2),
    }


def _modelos_opencode():
    if CORE_SETTINGS is not None:
        try:
            lista = getattr(CORE_SETTINGS, "opencode_models", None)
            if lista:
                return [m for m in lista if m]
        except Exception:
            pass
    return [
        "opencode/deepseek-v4-flash-free",
        "opencode/hy3-free",
        "opencode/nemotron-3.5-lightning-free",
    ]


def executar_opencode(tarefa, diretorio="", modelo="", arquivo_alvo=""):
    """
    Ferramenta: delega tarefa de programacao ao OpenCode (agente externo).
    Tenta os modelos Free configurados; se todos falharem, cai para o
    modelo local (Qwen via Ollama) com o pipeline interno do Golden.

    Se arquivo_alvo for informado, o arquivo e comparado por hash antes e
    depois: um agente que respondeu sem aplicar nenhuma alteracao no arquivo
    (ex.: devolveu pergunta de esclarecimento) e tratado como NAO concluido,
    disparando o proximo modelo da cadeia.
    """
    if not isinstance(tarefa, str) or not tarefa.strip():
        return {"ok": False, "erro": "Tarefa vazia.", "texto": "", "modelo": "", "duracao_segundos": 0.0}

    if CORE_SETTINGS is not None and not getattr(CORE_SETTINGS, "opencode_enabled", True):
        return {"ok": False, "erro": "OpenCode desabilitado na config.", "texto": "", "modelo": "", "duracao_segundos": 0.0}

    if not diretorio:
        try:
            diretorio = getattr(CORE_SETTINGS, "opencode_work_dir", r"C:\GoldenAI\sandbox\opencode")
        except Exception:
            diretorio = r"C:\GoldenAI\sandbox\opencode"

    timeout = int(getattr(CORE_SETTINGS, "opencode_timeout_seconds", 900) if CORE_SETTINGS is not None else 900)

    modelos = [modelo] if modelo else _modelos_opencode()

    hash_antes = None
    if arquivo_alvo and os.path.isfile(arquivo_alvo):
        try:
            hash_antes = hash_texto(open(arquivo_alvo, encoding="utf-8", errors="replace").read())
        except Exception:
            hash_antes = None

    erros = []
    for mod in modelos:
        resultado = _executar_opencode_cli(mod, tarefa, diretorio, timeout)
        if resultado.get("ok") and hash_antes is not None:
            try:
                hash_depois = hash_texto(open(arquivo_alvo, encoding="utf-8", errors="replace").read())
            except Exception:
                hash_depois = None
            if hash_depois == hash_antes:
                texto_resp = (resultado.get("texto") or "").lower()
                conclusao_sem_mudanca = any(
                    k in texto_resp
                    for k in (
                        "nada", "nao ha", "nenhuma altera", "sem altera",
                        "nao foi alterado", "sem mudanca", "nada a fazer",
                        "nao identifiquei", "no changes", "nothing", "nothing to fix",
                        "nothing to change", "no fix"
                    )
                )
                if not conclusao_sem_mudanca:
                    resultado["ok"] = False
                    resultado["erro"] = (
                        (resultado.get("erro") or "Resposta sem efeito.")
                        + " | Agente nao aplicou alteracoes no arquivo alvo."
                    )
        if resultado.get("ok"):
            resultado["fallback"] = "opencode"
            return resultado
        erros.append(f"{mod}: {resultado.get('erro') or 'falhou'}")
        print(f"OpenCode [{mod}] falhou: {resultado.get('erro')}")

    return {
        "ok": False,
        "erro": "Nenhum modelo Free do OpenCode concluiu a tarefa.",
        "texto": "",
        "modelo": "",
        "duracao_segundos": 0.0,
        "fallback": "nenhum",
        "erros_opencode": erros,
    }


def registrar_ferramentas_core():
    if not CORE_TOOL_REGISTRY or not ToolDefinition:
        return
    ferramentas = [
        ToolDefinition("listar_projetos", "Lista arquivos dos projetos.", {}, "READ", lambda: listar_projetos(), "read"),
        ToolDefinition("ler_arquivo", "Le um arquivo da pasta de projetos.", {"nome": "string"}, "READ", lambda nome: ler_arquivo(nome), "read"),
        ToolDefinition("arquivo_metadados", "Retorna metadados objetivos de arquivo em modo somente leitura.", {"nome": "string"}, "READ", lambda nome: arquivo_metadados(nome), "read"),
        ToolDefinition("market_analyze_dataset", "Analisa dataset CSV local autorizado com Market V1.", {"nome": "string", "symbol": "string", "timeframe": "string"}, "READ", lambda nome="", symbol="DATASET", timeframe="H1": market_analyze_dataset(nome, symbol, timeframe), "read"),
        ToolDefinition("market_get_snapshot", "Consulta snapshots da analise Market persistida.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_snapshot(analysis_id), "read"),
        ToolDefinition("market_get_regime", "Consulta regimes da analise Market persistida.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_regime(analysis_id), "read"),
        ToolDefinition("market_get_multitimeframe_context", "Consulta contexto multi-timeframe Market persistido.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_multitimeframe_context(analysis_id), "read"),
        ToolDefinition("market_get_structure", "Consulta estruturas Market persistidas.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_structure(analysis_id), "read"),
        ToolDefinition("market_get_observations", "Consulta observacoes Market persistidas.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_observations(analysis_id), "read"),
        ToolDefinition("market_get_signals", "Consulta hipoteses/sinais Market persistidos.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_signals(analysis_id), "read"),
        ToolDefinition("market_get_analysis", "Consulta uma analise Market persistida ou a ultima.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_get_analysis(analysis_id), "read"),
        ToolDefinition("market_list_analyses", "Lista analises Market persistidas.", {"limit": "integer"}, "READ", lambda limit=10: market_list_analyses(int(limit)), "read"),
        ToolDefinition("market_hypothesis_to_strategy_spec", "Prepara StrategySpec conceitual a partir de hipotese Market sem rodar backtest.", {"analysis_id": "string"}, "READ", lambda analysis_id="": market_hypothesis_to_strategy_spec(analysis_id), "read"),
        ToolDefinition("quant_run_backtest", "Executa backtest Quant V1 somente com pedido explicito e CSV local autorizado.", {"nome": "string", "strategy_spec": "object", "initial_capital": "number", "quantity": "number", "spread": "number", "commission": "number", "slippage": "number"}, "READ", lambda nome, strategy_spec=None, initial_capital=10000.0, quantity=1.0, spread=0.0, commission=0.0, slippage=0.0: quant_run_backtest(nome, strategy_spec, initial_capital, quantity, spread, commission, slippage), "read"),
        ToolDefinition("quant_get_experiment", "Consulta experimento Quant persistido.", {"experiment_id": "string"}, "READ", lambda experiment_id="": quant_get_experiment(experiment_id), "read"),
        ToolDefinition("quant_get_metrics", "Consulta metricas Quant persistidas.", {"experiment_id": "string"}, "READ", lambda experiment_id="": quant_get_metrics(experiment_id), "read"),
        ToolDefinition("quant_get_trades", "Consulta trades Quant persistidos.", {"experiment_id": "string"}, "READ", lambda experiment_id="": quant_get_trades(experiment_id), "read"),
        ToolDefinition("quant_get_equity", "Consulta curva de equity Quant persistida.", {"experiment_id": "string"}, "READ", lambda experiment_id="": quant_get_equity(experiment_id), "read"),
        ToolDefinition("quant_compare_experiments", "Compara dois experimentos Quant persistidos.", {"experiment_a": "string", "experiment_b": "string"}, "READ", lambda experiment_a="", experiment_b="": quant_compare_experiments(experiment_a, experiment_b), "read"),
        ToolDefinition("quant_list_experiments", "Lista experimentos Quant persistidos.", {"limit": "integer"}, "READ", lambda limit=10: quant_list_experiments(int(limit)), "read"),
        ToolDefinition("memory_store_knowledge", "Registra KnowledgeItem rastreavel no banco interno da memoria cientifica.", {"topic": "string", "statement": "string", "evidence_level": "string", "source_type": "string"}, "READ", lambda topic="", statement="", evidence_level="SOURCE_CLAIM", source_type="USER_NOTE", source_id="", source_location="", confidence=0.5, validation_status="", tags=None, metadata=None, supersedes_id=None: memory_store_knowledge(topic, statement, evidence_level, source_type, source_id, source_location, confidence, validation_status, tags, metadata, supersedes_id), "read"),
        ToolDefinition("memory_search_knowledge", "Busca memoria cientifica persistida por filtros estruturados.", {"topic": "string", "text": "string", "tags": "array", "source_type": "string", "evidence_level": "string", "experiment_id": "string", "symbol": "string", "timeframe": "string", "limit": "integer"}, "READ", lambda topic="", text="", tags=None, source_type="", evidence_level="", experiment_id="", symbol="", timeframe="", limit=20: memory_search_knowledge(topic, text, tags, source_type, evidence_level, experiment_id, symbol, timeframe, limit), "read"),
        ToolDefinition("memory_get_knowledge", "Recupera KnowledgeItem por ID.", {"knowledge_id": "string"}, "READ", lambda knowledge_id="": memory_get_knowledge(knowledge_id), "read"),
        ToolDefinition("memory_find_related_experiments", "Busca experimentos Quant relacionados na memoria cientifica.", {"query": "string", "symbol": "string", "timeframe": "string", "limit": "integer"}, "READ", lambda query="", symbol="", timeframe="", limit=10: memory_find_related_experiments(query, symbol, timeframe, limit), "read"),
        ToolDefinition("memory_get_topic_summary", "Resume conhecimento cientifico rastreavel por topico.", {"topic": "string", "limit": "integer"}, "READ", lambda topic="", limit=10: memory_get_topic_summary(topic, limit), "read"),
        ToolDefinition("memory_link_experiment", "Liga KnowledgeItem a experimento Quant preservando rastreabilidade.", {"knowledge_id": "string", "experiment_id": "string", "relationship": "string", "metadata": "object"}, "READ", lambda knowledge_id="", experiment_id="", relationship="supports", metadata=None: memory_link_experiment(knowledge_id, experiment_id, relationship, metadata), "read"),
        ToolDefinition("media_ingest_source", "Ingere fonte textual local autorizada para Media Study V1.", {"nome": "string", "source_type": "string", "title": "string", "author": "string", "language": "string"}, "READ", lambda nome="", source_type="", title="", author="", language="": media_ingest_source(nome, source_type, title, author, language), "read"),
        ToolDefinition("media_get_source", "Consulta fonte Media persistida.", {"source_id": "string"}, "READ", lambda source_id="": media_get_source(source_id), "read"),
        ToolDefinition("media_list_sources", "Lista fontes Media persistidas.", {"limit": "integer"}, "READ", lambda limit=20: media_list_sources(int(limit)), "read"),
        ToolDefinition("media_get_segments", "Consulta segmentos rastreaveis de fonte Media.", {"source_id": "string", "limit": "integer"}, "READ", lambda source_id="", limit=200: media_get_segments(source_id, int(limit)), "read"),
        ToolDefinition("media_search_source", "Busca texto em fonte Media atual ou indicada.", {"query": "string", "source_id": "string", "limit": "integer"}, "READ", lambda query="", source_id="", limit=20: media_search_source(query, source_id, int(limit)), "read"),
        ToolDefinition("media_extract_claims", "Extrai claims estruturados SOURCE_CLAIM de fonte Media.", {"source_id": "string"}, "READ", lambda source_id="": media_extract_claims(source_id), "read"),
        ToolDefinition("media_get_claims", "Lista claims de fonte Media ou claim especifico.", {"source_id": "string", "claim_id": "string"}, "READ", lambda source_id="", claim_id="": media_get_claims(source_id, claim_id), "read"),
        ToolDefinition("media_study_source", "Estuda fonte Media e integra claims relevantes com memoria cientifica.", {"source_id": "string"}, "READ", lambda source_id="": media_study_source(source_id), "read"),
        ToolDefinition("media_get_study_result", "Consulta resultado de estudo Media persistido.", {"study_id": "string"}, "READ", lambda study_id="": media_get_study_result(study_id), "read"),
        ToolDefinition("media_claim_to_hypothesis", "Converte claim Media em hipotese testavel sem rodar Quant.", {"claim_id": "string"}, "READ", lambda claim_id="": media_claim_to_hypothesis(claim_id), "read"),
        ToolDefinition("media_get_claim_origin", "Localiza fonte, segmento e timestamp de claim Media.", {"claim_id": "string"}, "READ", lambda claim_id="": media_get_claim_origin(claim_id), "read"),
        ToolDefinition("agent_orchestrate", "Roteia tarefa para agentes especializados sem elevar permissoes.", {"description": "string", "context": "object", "review": "boolean"}, "READ", lambda description="", context=None, review=False: agent_orchestrate(description, context or {}, review), "read"),
        ToolDefinition("escrever_arquivo", "Bloqueado em modo somente leitura.", {"nome": "string", "conteudo": "string"}, "WRITE", lambda nome, conteudo: escrever_arquivo(nome, conteudo), "write"),
        ToolDefinition("compilar_mql5", "Compila .mq5 existente.", {"nome": "string"}, "EXECUTE", lambda nome: compilar_mql5(nome), "execute"),
        ToolDefinition("executar_opencode", "Delega tarefa de programacao ao agente OpenCode (modelos Free com fallback automatico para Qwen local).", {"tarefa": "string", "diretorio": "string", "modelo": "string"}, "EXECUTE", lambda tarefa, diretorio="", modelo="": executar_opencode(tarefa, diretorio, modelo), "execute"),
        ToolDefinition("listar_eas_mt5", "Lista EAs MT5 reais.", {}, "READ", lambda: listar_eas_mt5(), "read"),
        ToolDefinition("ler_arquivo_mt5", "Le arquivo MT5 real.", {"nome": "string"}, "READ", lambda nome: ler_arquivo_mt5(nome), "read"),
        ToolDefinition("copiar_ea_mt5_para_teste", "Bloqueado em modo somente leitura.", {"nome": "string"}, "WRITE", lambda nome: copiar_ea_mt5_para_teste(nome), "write"),
        ToolDefinition("excluir_backup", "Bloqueado: operacao critica.", {"backup": "string"}, "CRITICAL", lambda backup: "BLOQUEADO", "write"),
        ToolDefinition("get_current_datetime", "Consulta data e hora locais reais.", {}, "READ", lambda: get_current_datetime(), "read"),
        ToolDefinition("get_system_info", "Consulta informacoes seguras do Windows.", {}, "READ_EXTERNAL_SAFE", lambda: get_system_info(), "read"),
        ToolDefinition("get_disk_usage", "Consulta uso de disco em caminho permitido.", {"path": "string"}, "READ_EXTERNAL_SAFE", lambda path=r"C:\GoldenAI": get_disk_usage(path), "read"),
        ToolDefinition("list_processes", "Lista processos sem linha de comando.", {"filter_name": "string", "limit": "integer"}, "READ_EXTERNAL_SAFE", lambda filter_name="", limit=80: list_processes(filter_name, int(limit)), "read"),
        ToolDefinition("find_installed_app", "Procura aplicativo conhecido sem executar.", {"name": "string"}, "READ_EXTERNAL_SAFE", lambda name: find_installed_app(name), "read"),
        ToolDefinition("find_mt5_installations", "Procura instalacoes conhecidas do MetaTrader 5.", {}, "READ_EXTERNAL_SAFE", lambda: find_mt5_installations(), "read"),
        ToolDefinition("get_mt5_status", "Consulta se MetaTrader 5/MetaEditor parecem abertos.", {}, "READ_EXTERNAL_SAFE", lambda: get_mt5_status(), "read"),
        ToolDefinition("list_mt5_terminals", "Lista terminais MT5 em AppData permitido.", {}, "READ_EXTERNAL_SAFE", lambda: list_mt5_terminals(), "read"),
        ToolDefinition("list_mt5_eas", "Lista EAs MT5 em modo somente leitura.", {}, "READ_EXTERNAL_SAFE", lambda: list_mt5_eas(), "read"),
        ToolDefinition("read_mt5_file", "Le .mq5/.mqh do MT5 em caminho permitido.", {"path": "string", "max_bytes": "integer"}, "READ_EXTERNAL_SAFE", lambda path, max_bytes=120000: read_mt5_file(path, int(max_bytes)), "read"),
        ToolDefinition("launch_allowed_app", "Abre somente aplicativos da allowlist.", {"name": "string"}, "EXECUTE", lambda name: launch_allowed_app(name), "execute"),
        ToolDefinition("open_folder", "Abre somente pastas da allowlist.", {"path": "string"}, "EXECUTE", lambda path: open_folder(path), "execute"),
        ToolDefinition("internet_search", "Pesquisa na Internet via DuckDuckGo.", {"query": "string", "max_results": "integer"}, "READ", lambda query=None, max_results=5: internet_search(query, max_results), "read"),
        ToolDefinition("internet_fetch", "Consulta pagina web em modo somente leitura.", {"url": "string"}, "READ", lambda url=None: internet_fetch(url), "read"),
        ToolDefinition("internet_download", "Download controlado de arquivo nao-executavel.", {"url": "string", "dest_dir": "string"}, "WRITE", lambda url=None, dest_dir=None: internet_download(url, dest_dir), "write"),
        ToolDefinition("browser_search", "Pesquisa na Internet renderizada (DuckDuckGo/Bing).", {"query": "string", "max_results": "integer"}, "READ", lambda query=None, max_results=5: browser_search(query, max_results), "read"),
        ToolDefinition("browser_fetch", "Abre pagina web em navegador real e extrai texto renderizado.", {"url": "string", "screenshot": "boolean"}, "READ", lambda url=None, screenshot=False: browser_fetch(url, screenshot), "read"),
        ToolDefinition("document_extract", "Extrai texto estruturado de PDF/DOCX/PPTX via Docling.", {"nome": "string"}, "READ", lambda nome=None: document_extract(nome), "read"),
        ToolDefinition("audio_transcribe", "Transcreve audio/voz local via faster-whisper.", {"nome": "string", "language": "string"}, "READ", lambda nome=None, language=None: audio_transcribe(nome, language), "read"),
        ToolDefinition("video_analyze", "Analisa video: transcricao (whisper) + descricao de cenas (vision).", {"nome": "string", "max_frames": "integer"}, "READ", lambda nome=None, max_frames=6: video_analyze(nome, max_frames), "read"),
        ToolDefinition("memory_vector_store", "Indexa texto na memoria semantica vetorial (Qdrant local).", {"texto": "string", "fonte": "string", "tipo": "string", "tags": "array"}, "READ", lambda texto=None, fonte="", tipo="nota", tags=None: memory_vector_store(texto, fonte, tipo, tags), "read"),
        ToolDefinition("memory_vector_search", "Busca semantica por similaridade na memoria vetorial (Qdrant).", {"consulta": "string", "limite": "integer", "tipo": "string"}, "READ", lambda consulta=None, limite=5, tipo=None: memory_vector_search(consulta, limite, tipo), "read"),
        ToolDefinition("vision_analyze_image", "Analisa imagem local com modelo multimodal (Ollama qwen2.5vl).", {"imagem": "string", "pergunta": "string"}, "READ", lambda imagem=None, pergunta=None: vision_analyze_image(imagem, pergunta), "read"),
    ]
    for ferramenta in ferramentas:
        CORE_TOOL_REGISTRY.register(ferramenta)


def score_compilacao(resultado):
    if (
        resultado["errors"] < 0
        or resultado["warnings"] < 0
    ):
        return None

    return (
        resultado["errors"] * 1000
        + resultado["warnings"]
    )


def mostrar_compilacao(resultado):
    print(
        f"Erros: {resultado['errors']} | "
        f"Warnings: {resultado['warnings']}"
    )

    print()
    print(resultado["log"])


# ============================================================
# MOTOR DETERMINISTICO DE AUTOCORRECAO
# ============================================================

def corrigir_mql5_automatico(nome, pedido_usuario):
    print()
    print("=" * 70)
    print(f"AUTOCORRECAO MQL5: {nome}")
    print("=" * 70)

    codigo_atual, erro = ler_arquivo(nome)

    if erro:
        print(erro)
        return

    print()
    print("[1] Arquivo lido.")

    resultado_atual = compilar_mql5(nome)

    print()
    print("[2] Compilacao inicial.")
    mostrar_compilacao(resultado_atual)

    if resultado_atual["ok"]:
        print()
        print("SUCESSO: 0 errors e 0 warnings.")
        print("Nenhuma alteracao foi necessaria.")
        return

    if resultado_atual["errors"] < 0:
        print()
        print(
            "Nao foi possivel obter um resultado valido "
            "do MetaEditor. Autocorrecao cancelada."
        )
        return

    melhor_codigo = codigo_atual
    melhor_resultado = resultado_atual
    melhor_score = score_compilacao(resultado_atual)

    rejeitados = set()

    for tentativa in range(1, MAX_CORRECOES + 1):
        print()
        print("-" * 70)
        print(f"TENTATIVA DE CORRECAO {tentativa}/{MAX_CORRECOES}")
        print("-" * 70)

        rejeitados_texto = (
            "\n".join(sorted(rejeitados))
            if rejeitados
            else "Nenhum."
        )

        prompt_sistema = """
Voce e um programador especialista em MQL5 e MetaTrader 5.

Sua tarefa e corrigir o codigo MQL5 usando SOMENTE:
1. o codigo atual fornecido;
2. os erros reais fornecidos pelo MetaEditor;
3. o pedido original do usuario.

REGRAS ABSOLUTAS:
- Retorne SOMENTE o conteudo COMPLETO do arquivo .mq5 corrigido.
- Nao use Markdown.
- Nao use ``` nem explicacoes.
- Preserve tudo que nao precisa ser alterado.
- Nao invente funcionalidades que o usuario nao pediu.
- Corrija primeiro os erros reais do compilador.
- O codigo retornado deve ser MQL5, nao MQL4.
- Nao repita uma tentativa que ja foi rejeitada.
"""

        prompt_usuario = f"""
PEDIDO ORIGINAL:
{pedido_usuario}

ARQUIVO:
{nome}

CODIGO ATUAL:
--- INICIO CODIGO ---
{melhor_codigo}
--- FIM CODIGO ---

RESULTADO REAL DA COMPILACAO:
Erros: {melhor_resultado['errors']}
Warnings: {melhor_resultado['warnings']}

LOG REAL DO METAEDITOR:
--- INICIO LOG ---
{melhor_resultado['log']}
--- FIM LOG ---

HASHES DE CANDIDATOS JA REJEITADOS:
{rejeitados_texto}

Gere agora uma versao COMPLETA corrigida do arquivo.
"""

        resposta = _chamar_modelo(
            [
                {
                    "role": "system",
                    "content": prompt_sistema
                },
                {
                    "role": "user",
                    "content": prompt_usuario
                }
            ]
        )

        candidato = extrair_codigo(
            resposta.message.content or ""
        )

        if not candidato:
            print(
                "O modelo nao retornou codigo valido. "
                "Tentando novamente."
            )
            continue

        hash_candidato = hash_texto(candidato)

        if hash_candidato == hash_texto(melhor_codigo):
            print(
                "Candidato identico ao codigo atual. "
                "Rejeitado."
            )
            rejeitados.add(hash_candidato)
            continue

        if hash_candidato in rejeitados:
            print(
                "Candidato ja rejeitado anteriormente. "
                "Ignorado."
            )
            continue

        ok_escrita, backup, mensagem = escrever_arquivo(
            nome,
            candidato
        )

        print(mensagem)

        if not ok_escrita:
            rejeitados.add(hash_candidato)
            continue

        resultado_novo = compilar_mql5(nome)

        print()
        print("[Compilacao da nova tentativa]")
        mostrar_compilacao(resultado_novo)

        if resultado_novo["ok"]:
            print()
            print("=" * 70)
            print(
                "SUCESSO: METAEDITOR CONFIRMOU "
                "0 ERRORS E 0 WARNINGS"
            )
            print("=" * 70)
            print(f"Correcao concluida na tentativa {tentativa}.")
            print(f"Backup anterior: {backup}")
            return

        score_novo = score_compilacao(
            resultado_novo
        )

        # Resultado invalido: rollback.
        if score_novo is None:
            print()
            print(
                "Resultado de compilacao invalido. "
                "Executando rollback."
            )

            restaurar_backup(nome, backup)
            rejeitados.add(hash_candidato)
            continue

        # Se piorou, restaura imediatamente.
        if (
            melhor_score is not None
            and score_novo > melhor_score
        ):
            print()
            print(
                "A correcao PIOROU a compilacao. "
                "Rollback automatico."
            )

            ok_rb, msg_rb = restaurar_backup(
                nome,
                backup
            )
            print(msg_rb)

            rejeitados.add(hash_candidato)

            # Continua usando a melhor versao anterior.
            continue

        # Se ficou igual mas com codigo diferente, aceita como base
        # somente se nao houver regressao; o novo log pode ajudar.
        melhor_codigo = candidato
        melhor_resultado = resultado_novo
        melhor_score = score_novo

        print()
        print(
            "A tentativa nao piorou a compilacao. "
            "Ela sera usada como base para a proxima correcao."
        )

    print()
    print("=" * 70)
    print("AUTOCORRECAO ENCERRADA")
    print("=" * 70)
    print(
        f"Nao foi possivel chegar a 0 errors / 0 warnings "
        f"em {MAX_CORRECOES} tentativas."
    )

    # Garante que o arquivo final seja a melhor versao conhecida.
    codigo_no_disco, _ = ler_arquivo(nome)

    if codigo_no_disco != melhor_codigo:
        print(
            "Restaurando a melhor versao encontrada "
            "durante o processo."
        )

        caminho = caminho_seguro(nome)

        with open(
            caminho,
            "w",
            encoding="utf-8",
            newline=""
        ) as arquivo:
            arquivo.write(melhor_codigo)

    print()
    print(
        f"Melhor resultado obtido: "
        f"{melhor_resultado['errors']} errors e "
        f"{melhor_resultado['warnings']} warnings."
    )



# ============================================================
# ROTAS DETERMINISTICAS PARA O MT5 REAL
# ============================================================

def extrair_nome_mt5_real(pergunta):
    if not isinstance(pergunta, str):
        return None

    # Primeiro procura um caminho absoluto terminado em .mq5/.mqh.
    match_abs = re.search(
        r'(?i)([A-Za-z]:\\[^"\r\n,;]+?\.(?:mq5|mqh))',
        pergunta
    )

    if match_abs:
        return match_abs.group(1).strip()

    # Caso normal: pega SOMENTE o nome final do arquivo,
    # sem capturar palavras anteriores da frase.
    match = re.search(
        r'(?i)([A-Za-z0-9_.-]+\.(?:mq5|mqh))',
        pergunta
    )

    if not match:
        return None

    return match.group(1).strip()


def localizar_mt5_real_por_nome(nome):
    if not nome:
        return None

    if not os.path.isdir(PASTA_MT5_EXPERTS):
        return None

    nome_alvo = nome.lower().strip()

    candidatos = []

    for raiz, _, arquivos in os.walk(PASTA_MT5_EXPERTS):
        for arquivo in arquivos:
            if not arquivo.lower().endswith((".mq5", ".mqh")):
                continue

            completo = os.path.join(raiz, arquivo)
            relativo = os.path.relpath(
                completo,
                PASTA_MT5_EXPERTS
            )

            if relativo.lower() == nome_alvo:
                return relativo

            if arquivo.lower() == nome_alvo:
                candidatos.append(relativo)

    if len(candidatos) == 1:
        return candidatos[0]

    if candidatos:
        # Prefere a pasta Meus Robos quando houver duplicidade.
        for candidato in candidatos:
            if candidato.lower().startswith("meus robos\\"):
                return candidato

        return candidatos[0]

    return None


def analisar_arquivo_mt5_real(pergunta):
    nome_citado = extrair_nome_mt5_real(pergunta)

    if not nome_citado:
        return False

    relativo = localizar_mt5_real_por_nome(
        nome_citado
    )

    if not relativo:
        print()
        print("Golden AI:")
        print(
            f"Nao encontrei '{nome_citado}' na pasta real "
            "MQL5\\Experts do MetaTrader 5."
        )
        print()
        return True

    print()
    print(
        "[GoldenAI usando ferramenta: ler_arquivo_mt5]"
    )
    print(f"Arquivo localizado: {relativo}")

    codigo = ler_arquivo_mt5(
        relativo
    )

    if (
        not isinstance(codigo, str)
        or codigo.startswith("Erro")
        or codigo.startswith("Acesso negado")
        or codigo.startswith("Arquivo MT5 nao encontrado")
    ):
        print()
        print("Golden AI:")
        print(codigo)
        print()
        return True

    print(
        f"Leitura concluida: {len(codigo)} caracteres."
    )

    # Numera o codigo para que a auditoria consiga citar evidencias concretas.
    codigo_numerado = "\n".join(
        f"{i:05d}: {linha}"
        for i, linha in enumerate(codigo.splitlines(), 1)
    )

    prompt = f"""
Voce e a GoldenAI, AUDITORA TECNICA DE MQL5 para MetaTrader 5.

O conteudo abaixo e CODIGO-FONTE MQL5 REAL. NUNCA o classifique como
Pine Script, Python, MQL4 ou outra linguagem.

PEDIDO DO USUARIO:
{pergunta}

ARQUIVO REAL DO MT5:
{relativo}

CODIGO MQL5 REAL COM NUMEROS DE LINHA:
--- INICIO DO CODIGO ---
{codigo_numerado}
--- FIM DO CODIGO ---

OBJETIVO:
Faca exatamente o que o pedido do usuario solicita. Se ele pediu auditoria,
nao entregue apenas um resumo do robo: investigue problemas concretos no codigo.

METODO OBRIGATORIO DE AUDITORIA POR FLUXO:
Para CADA possivel problema, antes de classifica-lo como confirmado, rastreie:
1. Onde a variavel/parametro/estado e declarado.
2. Qual valor inicial/default ele recebe.
3. Onde esse valor pode ser alterado.
4. Quem chama a funcao envolvida.
5. Quais validacoes acontecem ANTES da chamada.
6. Quais valores realmente podem chegar a funcao.
7. Qual efeito real ocorre DEPOIS da funcao.
8. Se existe outro trecho do codigo que neutraliza, corrige ou impede o problema.

Uma funcao isolada NAO e evidencia suficiente para confirmar um bug ou risco.
Se a cadeia completa nao puder ser demonstrada no codigo, classifique como:
"NAO CONFIRMADO PELO CODIGO".

REGRAS DE EVIDENCIA:
1. Baseie cada conclusao SOMENTE no codigo fornecido.
2. Nao invente indicadores, regras, funcoes, variaveis, resultados ou significados.
3. Antes de afirmar um problema, identifique a funcao/rotina e as linhas que o sustentam.
4. Cite linhas no formato "linhas 123-137" e, quando util, um trecho curto do codigo.
5. Para classificar algo como CONFIRMADO, apresente uma CADEIA DE EVIDENCIAS contendo:
   declaracao -> origem do valor -> chamada -> validacoes anteriores -> efeito real.
6. Se faltar QUALQUER elo essencial da cadeia, escreva:
   "NAO CONFIRMADO PELO CODIGO".
7. Nao transforme ausencia de validacao local em bug se houver validacao anterior no fluxo.
8. Nao trate um valor teoricamente invalido como problema confirmado sem provar que ele
   pode realmente chegar aquele ponto do codigo.
9. Nao confunda nomes de variaveis com conceitos financeiros que nao estejam definidos.
10. Diferencie comportamento intencional de defeito comprovado.
11. Diferencie "pode acontecer em teoria" de "o codigo permite que aconteca".
12. Nao prometa compilacao nem diga que compilou se nenhuma compilacao foi executada.
13. Nao altere, reescreva ou salve o arquivo neste modo.
14. Prefira menos problemas bem provados a muitos falsos positivos.

CLASSIFICACAO DA AUDITORIA:
- ERRO DE COMPILACAO: somente se o proprio codigo mostrar um problema sintatico/tipo
  claramente demonstravel; sem compilacao real, identifique como "possivel" quando houver duvida.
- BUG: implementacao que contradiz claramente a logica pretendida pelo proprio codigo.
- RISCO LOGICO: comportamento valido em MQL5, mas que pode produzir decisao incorreta,
  estado inconsistente ou efeito nao pretendido.
- RISCO OPERACIONAL: risco relacionado a ordens, lote, SL/TP, spread, posicoes,
  normalizacao, retcodes, falhas de execucao ou protecoes.
- MELHORIA: robustez/manutencao/desempenho; nao apresente melhoria como bug.

FORMATO DA RESPOSTA:
Comece com:
"LINGUAGEM: MQL5"
"ARQUIVO: {relativo}"
"MODO: SOMENTE LEITURA - NENHUMA ALTERACAO REALIZADA"

Depois apresente:
1. RESUMO DO QUE O ROBO REALMENTE FAZ
2. PROBLEMAS CONFIRMADOS
   Para cada item:
   - Severidade: CRITICA / ALTA / MEDIA / BAIXA
   - Categoria
   - Funcao/rotina
   - Linhas
   - Cadeia de evidencia:
       a) Declaracao/origem
       b) Caminho ate a funcao
       c) Validacoes anteriores
       d) Efeito observado no codigo
   - Por que e CONFIRMADO
   - Impacto
   - Como corrigiria (sem modificar)
3. HIPOTESES NAO CONFIRMADAS
   Para cada item, explique exatamente qual elo da cadeia de evidencia esta faltando.
4. PONTOS QUE EXIGEM VALIDACAO
5. MELHORIAS NAO OBRIGATORIAS
6. CONCLUSAO
   Informe quantos problemas realmente confirmados encontrou por categoria.
   Se nenhum foi confirmado, diga explicitamente que a auditoria nao encontrou
   evidencia suficiente para afirmar bugs/riscos confirmados.

Se nao encontrar problemas confirmados em uma categoria, diga explicitamente
"Nenhum problema confirmado pelo codigo nesta categoria."

Responda em portugues, de forma tecnica, objetiva e fiel ao codigo.
"""
    resposta = _chamar_modelo(
        [
            {
                "role": "system",
                "content": (
                    "Voce e uma auditora tecnica estrita de codigo MQL5 real. "
                    "O codigo fornecido e MQL5 para MetaTrader 5. "
                    "Audite por fluxo completo, nao por funcao isolada. "
                    "So confirme um problema quando houver cadeia de evidencia no codigo. "
                    "Toda afirmacao tecnica deve ser sustentada pelo codigo. "
                    "Prefira dizer NAO CONFIRMADO PELO CODIGO a inventar um risco. "
                    "Nao invente informacoes, nao confunda a linguagem e nao altere arquivos."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    texto_final = (
        resposta.message.content
        or "Nao foi possivel gerar a analise."
    ).strip()

    # V1.9.2: segunda passagem obrigatoria antes de considerar
    # qualquer achado como candidato a autocorrecao.
    prompt_verificacao = f"""
Voce e a GoldenAI, REVISORA CONSERVADORA DE MQL5.

ARQUIVO ALVO:
{alvo.get('caminho')}

CODIGO REAL:
--- INICIO ---
{codigo_numerado}
--- FIM ---

PRIMEIRA AUDITORIA:
--- INICIO ---
{texto_final}
--- FIM ---

TAREFA:
Revise criticamente CADA problema que a primeira auditoria chamou de
PROBLEMA CONFIRMADO.

Para cada achado:
1. identifique a funcao e as linhas;
2. mostre a condicao exata que dispara o comportamento;
3. siga a cadeia chamada -> validacoes -> efeito;
4. verifique se o comportamento pode ser INTENCIONAL por configuracao;
5. diferencie bug real de regra de negocio/estrategia;
6. nao considere como bug apenas porque uma funcao pode retornar sem alterar algo;
7. nao considere como bug o uso de lote fixo quando UsarRiscoPercentual=false,
   a menos que o proprio codigo prove que isso contradiz a configuracao;
8. nao proponha mudanca de estrategia, parametros ou regras operacionais;
9. se a evidencia nao for suficiente, REBAIXE para NAO CONFIRMADO.

Classifique cada achado somente como:
- CONFIRMADO PARA CORRECAO
- NAO CONFIRMADO
- COMPORTAMENTO INTENCIONAL

No final escreva:
AUTOCORRECAO AUTORIZADA: SIM ou NAO
QUANTIDADE DE BUGS CONFIRMADOS: N

AUTOCORRECAO AUTORIZADA so pode ser SIM se existir pelo menos um bug
com cadeia de evidencia completa no codigo.
Nao altere nenhum arquivo.
Responda em portugues.
"""

    revisao = _chamar_modelo(
        [
            {
                "role": "system",
                "content": (
                    "Seja conservador. Sua funcao e impedir falsos positivos "
                    "antes de qualquer autocorrecao de codigo MQL5."
                )
            },
            {"role": "user", "content": prompt_verificacao}
        ]
    )

    texto_revisao = (
        revisao.message.content
        or "Nao foi possivel executar a segunda verificacao."
    ).strip()

    print()
    print("Golden AI:")
    print("============================================================")
    print("AUDITORIA INICIAL")
    print("============================================================")
    print(texto_final)
    print()
    print("============================================================")
    print("SEGUNDA VERIFICACAO CONSERVADORA - V1.9.2")
    print("============================================================")
    print(texto_revisao)
    print()

    return True



# ============================================================
# COPIA SEGURA DO MT5 REAL PARA AREA DE TESTES
# ============================================================

def copiar_ea_mt5_para_teste(nome, sufixo="_TESTE"):
    """
    Copia um .mq5/.mqh REAL do MT5 para C:\\GoldenAI\\projetos.
    Nunca altera o original.
    Retorna informacoes verificadas sobre origem, destino e hashes.
    """

    relativo = localizar_mt5_real_por_nome(nome)

    if not relativo:
        return {
            "ok": False,
            "mensagem": f"Arquivo nao encontrado no MT5 real: {nome}"
        }

    origem = caminho_seguro_mt5(relativo)

    if origem is None or not os.path.isfile(origem):
        return {
            "ok": False,
            "mensagem": f"Origem invalida ou inexistente: {relativo}"
        }

    base = os.path.basename(origem)
    raiz, extensao = os.path.splitext(base)

    if extensao.lower() not in (".mq5", ".mqh"):
        return {
            "ok": False,
            "mensagem": "Somente arquivos .mq5 ou .mqh podem ser copiados."
        }

    destino_nome = f"{raiz}{sufixo}{extensao}"
    destino = caminho_seguro(destino_nome)

    if destino is None:
        return {
            "ok": False,
            "mensagem": "Destino de teste invalido."
        }

    try:
        os.makedirs(PASTA_PROJETOS, exist_ok=True)

        # Se ja existir, cria backup antes de sobrescrever.
        backup_existente = None
        if os.path.isfile(destino):
            backup_existente, erro_backup = criar_backup(destino_nome)
            if erro_backup:
                return {
                    "ok": False,
                    "mensagem": f"Falha ao criar backup da copia existente: {erro_backup}"
                }

        shutil.copy2(origem, destino)

        def sha256_arquivo(caminho):
            h = hashlib.sha256()
            with open(caminho, "rb") as f:
                for bloco in iter(lambda: f.read(65536), b""):
                    h.update(bloco)
            return h.hexdigest()

        hash_origem = sha256_arquivo(origem)
        hash_destino = sha256_arquivo(destino)

        if hash_origem != hash_destino:
            try:
                os.remove(destino)
            except Exception:
                pass

            return {
                "ok": False,
                "mensagem": (
                    "Falha de verificacao: hash da copia difere do original. "
                    "A copia de teste foi removida."
                )
            }

        return {
            "ok": True,
            "origem_relativa": relativo,
            "origem": origem,
            "destino_nome": destino_nome,
            "destino": destino,
            "hash_origem": hash_origem,
            "hash_destino": hash_destino,
            "backup_copia_anterior": backup_existente,
            "mensagem": (
                "COPIA DE TESTE CRIADA E VERIFICADA.\n"
                f"Original MT5: {origem}\n"
                f"Copia teste: {destino}\n"
                f"SHA256 origem: {hash_origem}\n"
                f"SHA256 copia:  {hash_destino}\n"
                "CONFIRMACAO: o arquivo original do MetaTrader 5 nao foi alterado."
            )
        }

    except Exception as erro:
        return {
            "ok": False,
            "mensagem": f"Erro ao copiar arquivo para testes: {erro}"
        }



# ============================================================
# ALVO DETERMINISTICO - V1.9.0
# ============================================================

def extrair_caminho_mql_explicito(pergunta):
    r"""
    Extrai um caminho Windows explicito terminado em .mq5/.mqh.
    Exemplo:
    C:\GoldenAI\projetos\Robo_TESTE.mq5
    """
    if not isinstance(pergunta, str):
        return None

    match = re.search(
        r'(?i)([A-Za-z]:\\[^"\r\n|<>*?]+?\.(?:mq5|mqh))',
        pergunta
    )

    if not match:
        return None

    return os.path.normpath(match.group(1).strip())


def classificar_alvo_mql(caminho):
    """
    Classifica o caminho em:
    - PROJETO_TESTE
    - MT5_REAL
    - FORA_DAS_AREAS_AUTORIZADAS
    """
    if not caminho:
        return "INVALIDO"

    alvo = os.path.abspath(caminho)
    pasta_teste = os.path.abspath(PASTA_PROJETOS)
    pasta_mt5 = os.path.abspath(PASTA_MT5_EXPERTS)

    try:
        if os.path.commonpath([alvo, pasta_teste]) == pasta_teste:
            return "PROJETO_TESTE"
    except ValueError:
        pass

    try:
        if os.path.commonpath([alvo, pasta_mt5]) == pasta_mt5:
            return "MT5_REAL"
    except ValueError:
        pass

    return "FORA_DAS_AREAS_AUTORIZADAS"


def resolver_alvo_mql(pergunta):
    """
    Resolve o arquivo alvo sem deixar o modelo trocar silenciosamente de arquivo.

    Prioridade:
    1. Caminho completo informado pelo usuario.
    2. Nome de arquivo citado na pasta de projetos.
    3. Nome de arquivo citado no MT5 real.
    """
    caminho_explicito = extrair_caminho_mql_explicito(pergunta)

    if caminho_explicito:
        tipo = classificar_alvo_mql(caminho_explicito)

        return {
            "ok": os.path.isfile(caminho_explicito),
            "tipo": tipo,
            "caminho": caminho_explicito,
            "nome": os.path.basename(caminho_explicito),
            "origem_resolucao": "CAMINHO_EXPLICITO"
        }

    nome = extrair_nome_mt5_real(pergunta)

    if not nome:
        nome = extrair_nome_mq5(pergunta)

    if not nome:
        return {
            "ok": False,
            "tipo": "INVALIDO",
            "caminho": None,
            "nome": None,
            "origem_resolucao": "NAO_IDENTIFICADO"
        }

    # Primeiro procura na area de projetos/testes.
    caminho_teste = caminho_seguro(nome)

    if caminho_teste and os.path.isfile(caminho_teste):
        return {
            "ok": True,
            "tipo": "PROJETO_TESTE",
            "caminho": os.path.abspath(caminho_teste),
            "nome": os.path.basename(caminho_teste),
            "origem_resolucao": "PASTA_PROJETOS"
        }

    # Depois procura no MT5 real.
    relativo = localizar_mt5_real_por_nome(nome)

    if relativo:
        caminho_mt5 = caminho_seguro_mt5(relativo)

        if caminho_mt5 and os.path.isfile(caminho_mt5):
            return {
                "ok": True,
                "tipo": "MT5_REAL",
                "caminho": os.path.abspath(caminho_mt5),
                "nome": os.path.basename(caminho_mt5),
                "relativo_mt5": relativo,
                "origem_resolucao": "MT5_REAL"
            }

    return {
        "ok": False,
        "tipo": "NAO_ENCONTRADO",
        "caminho": None,
        "nome": nome,
        "origem_resolucao": "NOME_SEM_CORRESPONDENCIA"
    }


def confirmar_alvo_na_tela(alvo, operacao):
    print()
    print("=" * 70)
    print("ARQUIVO ALVO CONFIRMADO")
    print("=" * 70)
    print(f"Operacao: {operacao}")
    print(f"Tipo: {alvo.get('tipo')}")
    print(f"Arquivo: {alvo.get('nome')}")
    print(f"Caminho: {alvo.get('caminho')}")

    if alvo.get("tipo") == "MT5_REAL":
        print("Protecao: MT5 REAL permanece SOMENTE LEITURA.")

    elif alvo.get("tipo") == "PROJETO_TESTE":
        print("Protecao: alteracoes permitidas somente nesta copia de teste.")

    print("=" * 70)
    print()


def ler_alvo_resolvido(alvo):
    if not alvo.get("ok"):
        return None, "Arquivo alvo nao encontrado."

    caminho = alvo.get("caminho")

    try:
        with open(
            caminho,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as f:
            return f.read(), None
    except Exception as erro:
        return None, f"Erro ao ler arquivo alvo: {erro}"


def compilar_alvo_resolvido(alvo):
    """
    Compila somente arquivos que estejam na pasta de projetos/teste.
    O MT5 real nao e compilado por esta rota de edicao segura.
    """
    if not alvo.get("ok"):
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": "Arquivo alvo nao encontrado."
        }

    if alvo.get("tipo") != "PROJETO_TESTE":
        return {
            "ok": False,
            "errors": -1,
            "warnings": -1,
            "log": (
                "Compilacao de edicao bloqueada: o alvo nao esta "
                "na pasta C:\\GoldenAI\\projetos."
            )
        }

    return compilar_mql5(
        alvo.get("nome")
    )



# ============================================================
# MEMORIA DO ARQUIVO ALVO - V1.9.2
# ============================================================


# ============================================================
# AUDITORIA DETERMINISTICA / CONSENSO - V1.9.6.1
# ============================================================

ARQUIVO_AUDITORIA_DETERMINISTICA = os.path.join(
    PASTA_APP,
    "ultima_auditoria_deterministica.json"
)


def chat_deterministico(messages, seed):
    """
    Chamada local com parametros fixos para reduzir variacao entre execucoes.
    V1.9.8.4: top_p=0 + min_p=0 garante geracao deterministica real no Ollama
    (top_p=0.1 + min_p default ainda permitia variacao em geracoes longas).
    """
    return chat(
        model=_obter_modelo("CODER"),
        messages=messages,
        options={
            "temperature": 0.0,
            "seed": int(seed),
            "top_p": 0.0,
            "top_k": 1,
            "min_p": 0.0,
            "repeat_penalty": 1.0
        }
    )


def extrair_json_modelo(texto):
    """
    Aceita JSON puro ou JSON dentro de bloco Markdown.
    """
    if not isinstance(texto, str):
        return None

    t = texto.strip()

    if t.startswith("```"):
        t = re.sub(
            r"^```(?:json)?\s*",
            "",
            t,
            flags=re.IGNORECASE
        )
        t = re.sub(
            r"\s*```$",
            "",
            t
        ).strip()

    try:
        return json.loads(t)
    except Exception:
        pass

    ini = t.find("{")
    fim = t.rfind("}")

    if ini >= 0 and fim > ini:
        try:
            return json.loads(t[ini:fim + 1])
        except Exception:
            return None

    return None


def _norm_identificador(valor):
    return re.sub(
        r"[^a-z0-9_]",
        "",
        str(valor or "").lower()
    )


def _intervalo_linhas(valor):
    numeros = [
        int(x)
        for x in re.findall(r"\d+", str(valor or ""))
    ]

    if not numeros:
        return 0, 0

    return min(numeros), max(numeros)


def _categoria_candidato(item):
    categorias_validas = {
        "CALCULO_LOTE",
        "NORMALIZACAO_LOTE",
        "PRECO_STOP",
        "TRAILING",
        "BREAK_EVEN",
        "POSICAO_ORDEM",
        "SPREAD",
        "INDICADOR",
        "VALIDACAO_PARAMETRO",
        "OUTRO"
    }

    categoria = str(
        item.get("categoria", "")
    ).strip().upper()

    if categoria in categorias_validas:
        return categoria

    texto = " ".join([
        str(item.get("funcao", "")),
        str(item.get("problema", "")),
        str(item.get("evidencia", ""))
    ]).lower()

    if "normaliz" in texto and "lot" in texto:
        return "NORMALIZACAO_LOTE"
    if "lote" in texto or "lot" in texto or "volume" in texto:
        return "CALCULO_LOTE"
    if "trailing" in texto:
        return "TRAILING"
    if "break" in texto and "even" in texto:
        return "BREAK_EVEN"
    if "spread" in texto:
        return "SPREAD"
    if (
        "stop loss" in texto
        or "take profit" in texto
        or " sl " in f" {texto} "
        or " tp " in f" {texto} "
    ):
        return "PRECO_STOP"
    if "position" in texto or "order" in texto or "posi" in texto or "ordem" in texto:
        return "POSICAO_ORDEM"
    if "ema" in texto or "atr" in texto or "vwap" in texto or "indicador" in texto:
        return "INDICADOR"
    if "valid" in texto or "zero" in texto or "limite" in texto:
        return "VALIDACAO_PARAMETRO"

    return "OUTRO"


def canonicalizar_candidatos(dados):
    """
    Canonicaliza sem exigir igualdade textual.
    A identidade primária passa a ser estrutural:
    função + região de linhas + categoria + símbolo-chave.
    """
    if not isinstance(dados, dict):
        return []

    candidatos = dados.get("candidatos", [])
    if not isinstance(candidatos, list):
        return []

    saida = []

    for item in candidatos:
        if not isinstance(item, dict):
            continue

        funcao = str(item.get("funcao", "")).strip()
        linhas = str(item.get("linhas", "")).strip()
        problema = " ".join(
            str(item.get("problema", "")).split()
        ).strip()
        evidencia = " ".join(
            str(item.get("evidencia", "")).split()
        ).strip()
        simbolo = str(
            item.get("simbolo_chave", "")
        ).strip()
        categoria = _categoria_candidato(item)

        if not funcao or not problema:
            continue

        ini, fim = _intervalo_linhas(linhas)

        saida.append({
            "id_original": str(item.get("id", "")).strip().upper(),
            "funcao": funcao,
            "funcao_norm": _norm_identificador(funcao),
            "linhas": linhas,
            "linha_ini": ini,
            "linha_fim": fim,
            "categoria": categoria,
            "simbolo_chave": simbolo,
            "simbolo_norm": _norm_identificador(simbolo),
            "problema": problema,
            "evidencia": evidencia
        })

    saida.sort(
        key=lambda x: (
            x["funcao_norm"],
            x["linha_ini"],
            x["linha_fim"],
            x["categoria"],
            x["simbolo_norm"]
        )
    )

    return saida


def _intervalos_compativeis(a, b, tolerancia=12):
    ai, af = a["linha_ini"], a["linha_fim"]
    bi, bf = b["linha_ini"], b["linha_fim"]

    if ai == 0 or bi == 0:
        return True

    # Sobreposição real.
    if max(ai, bi) <= min(af, bf):
        return True

    # Pequena diferença de referência de linha.
    if abs(ai - bi) <= tolerancia:
        return True

    if abs(af - bf) <= tolerancia:
        return True

    return False


def candidatos_equivalentes(a, b):
    if a["funcao_norm"] != b["funcao_norm"]:
        return False

    if not _intervalos_compativeis(a, b):
        return False

    # Categorias diferentes são sinal de diferença semântica,
    # exceto quando uma das respostas caiu em OUTRO.
    if (
        a["categoria"] != b["categoria"]
        and "OUTRO" not in {a["categoria"], b["categoria"]}
    ):
        return False

    # Se ambos identificaram explicitamente um símbolo-chave,
    # ele deve coincidir.
    if (
        a["simbolo_norm"]
        and b["simbolo_norm"]
        and a["simbolo_norm"] != b["simbolo_norm"]
    ):
        return False

    return True


def comparar_e_fundir_candidatos(lista_a, lista_b):
    """
    Faz matching estrutural 1:1.
    Não compara redação de problema/evidência.
    """
    if len(lista_a) != len(lista_b):
        return False, [], {
            "motivo": "quantidade_diferente",
            "nao_casados_a": lista_a,
            "nao_casados_b": lista_b
        }

    usados_b = set()
    pares = []
    nao_casados_a = []

    for a in lista_a:
        melhor_j = None
        melhor_dist = None

        for j, b in enumerate(lista_b):
            if j in usados_b:
                continue

            if not candidatos_equivalentes(a, b):
                continue

            dist = abs(a["linha_ini"] - b["linha_ini"])

            if melhor_j is None or dist < melhor_dist:
                melhor_j = j
                melhor_dist = dist

        if melhor_j is None:
            nao_casados_a.append(a)
            continue

        usados_b.add(melhor_j)
        pares.append((a, lista_b[melhor_j]))

    nao_casados_b = [
        b
        for j, b in enumerate(lista_b)
        if j not in usados_b
    ]

    if nao_casados_a or nao_casados_b:
        return False, [], {
            "motivo": "estrutura_diferente",
            "nao_casados_a": nao_casados_a,
            "nao_casados_b": nao_casados_b
        }

    fundidos = []

    for idx, (a, b) in enumerate(
        sorted(
            pares,
            key=lambda par: (
                par[0]["funcao_norm"],
                par[0]["linha_ini"],
                par[0]["categoria"]
            )
        ),
        start=1
    ):
        categoria = (
            a["categoria"]
            if a["categoria"] != "OUTRO"
            else b["categoria"]
        )

        simbolo = (
            a["simbolo_chave"]
            if a["simbolo_chave"]
            else b["simbolo_chave"]
        )

        ini_vals = [
            v for v in [a["linha_ini"], b["linha_ini"]]
            if v > 0
        ]
        fim_vals = [
            v for v in [a["linha_fim"], b["linha_fim"]]
            if v > 0
        ]

        ini = min(ini_vals) if ini_vals else 0
        fim = max(fim_vals) if fim_vals else 0
        linhas = (
            f"{ini}-{fim}"
            if ini and fim and ini != fim
            else str(ini or fim or "")
        )

        fundidos.append({
            "id": f"C{idx}",
            "funcao": a["funcao"],
            "linhas": linhas,
            "categoria": categoria,
            "simbolo_chave": simbolo,
            # Mantemos as duas descrições para os validadores,
            # mas elas não participam da equivalência.
            "problema": a["problema"],
            "problema_b": b["problema"],
            "evidencia": a["evidencia"],
            "evidencia_b": b["evidencia"]
        })

    return True, fundidos, {
        "motivo": "equivalencia_estrutural_aprovada",
        "pares": len(fundidos)
    }


def assinatura_estrutural(candidatos):
    chaves = []

    for item in candidatos:
        chaves.append({
            "funcao": _norm_identificador(item.get("funcao")),
            "linha_ini": _intervalo_linhas(item.get("linhas"))[0],
            "linha_fim": _intervalo_linhas(item.get("linhas"))[1],
            "categoria": str(item.get("categoria", "OUTRO")).upper(),
            "simbolo": _norm_identificador(item.get("simbolo_chave"))
        })

    chaves.sort(
        key=lambda x: (
            x["funcao"],
            x["linha_ini"],
            x["linha_fim"],
            x["categoria"],
            x["simbolo"]
        )
    )

    return hash_texto(
        json.dumps(
            chaves,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":")
        )
    )



def canonicalizar_validacao(dados):
    if not isinstance(dados, dict):
        return {}

    itens = dados.get("itens", [])
    if not isinstance(itens, list):
        return {}

    saida = {}

    for item in itens:
        if not isinstance(item, dict):
            continue

        cid = str(item.get("id", "")).strip().upper()
        status = str(item.get("status", "")).strip().upper()
        motivo = " ".join(
            str(item.get("motivo", "")).split()
        ).strip()

        if status not in {
            "CONFIRMADO",
            "NAO_CONFIRMADO",
            "COMPORTAMENTO_INTENCIONAL"
        }:
            status = "NAO_CONFIRMADO"

        if cid:
            saida[cid] = {
                "status": status,
                "motivo": motivo
            }

    return saida


def salvar_auditoria_deterministica(dados):
    try:
        with open(
            ARQUIVO_AUDITORIA_DETERMINISTICA,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                dados,
                f,
                ensure_ascii=False,
                indent=2
            )
        return True
    except Exception as erro:
        print(
            "[AVISO] Nao foi possivel salvar a auditoria "
            f"deterministica: {erro}"
        )
        return False


def analisar_alvo_projeto(alvo, pergunta):
    """
    V1.9.6 - Auditoria deterministica com gate de repetibilidade.

    Fluxo:
    0. Confirma SHA256 e compilacao-base.
    1. Descoberta deterministica A.
    2. Repete a mesma descoberta com o MESMO seed.
    3. So continua se as duas descobertas forem identicas.
    4. Dois validadores independentes, com seeds fixos diferentes.
    5. Um bug so e confirmado se AMBOS os validadores confirmarem.
    6. A decisao final e calculada localmente em Python.
    """

    if not alvo or not alvo.get("ok"):
        print()
        print("Golden AI:")
        print("Nenhum arquivo alvo valido esta definido.")
        print()
        return None

    if alvo.get("tipo") != "PROJETO_TESTE":
        print()
        print("Golden AI:")
        print(
            "Auditoria deterministica bloqueada: "
            "o alvo precisa ser uma copia PROJETO_TESTE."
        )
        print()
        return None

    confirmar_alvo_na_tela(
        alvo,
        "AUDITORIA DETERMINISTICA SOMENTE LEITURA"
    )

    codigo, erro = ler_alvo_resolvido(alvo)

    if erro:
        print("Golden AI:")
        print(erro)
        print()
        return None

    caminho = alvo.get("caminho")
    nome = alvo.get("nome")
    sha_inicial = hash_texto(codigo)

    print()
    print("=" * 70)
    print("GATE 0/4 - IDENTIDADE E COMPILACAO-BASE")
    print("=" * 70)
    print(f"SHA256 do codigo: {sha_inicial}")

    resultado_base = compilar_mql5(nome)
    mostrar_compilacao(resultado_base)

    if not resultado_base.get("ok"):
        print()
        print(
            "AUDITORIA BLOQUEADA: o arquivo nao esta em "
            "0 errors / 0 warnings antes da analise logica."
        )
        print()
        return {
            "arquivo": caminho,
            "nome": nome,
            "tipo": alvo.get("tipo"),
            "autorizado": False,
            "quantidade": 0,
            "veredito": (
                "AUTOCORRECAO AUTORIZADA: NAO\n"
                "QUANTIDADE DE BUGS CONFIRMADOS: 0\n"
                "MOTIVO: compilacao-base invalida."
            ),
            "deterministico_aprovado": False,
            "sha256_codigo": sha_inicial
        }

    codigo_numerado = "\n".join(
        f"{i:05d}: {linha}"
        for i, linha in enumerate(codigo.splitlines(), 1)
    )

    prompt_descoberta = f"""
Voce e uma AUDITORA TECNICA CONSERVADORA DE MQL5.

ARQUIVO FIXO:
{caminho}

SHA256 DO CODIGO:
{sha_inicial}

CODIGO REAL NUMERADO:
--- INICIO ---
{codigo_numerado}
--- FIM ---

TAREFA:
Descubra SOMENTE candidatos a bugs reais de logica/risco operacional
que estejam demonstrados pelo codigo.

REGRAS:
- Nao altere nada.
- Nao invente chamadas ou estados.
- Um candidato precisa indicar funcao, linhas, problema e evidencia.
- Nao trate melhoria, estilo, ausencia de log ou preferencia de estrategia como bug.
- Nao trate configuracao intencional como bug.
- Nao trate "pode", "talvez", "se" ou "presumivelmente" como prova.
- Se a cadeia declaracao -> chamada -> validacao -> efeito nao estiver visivel,
  nao crie candidato.
- Mantenha no maximo 8 candidatos.
- IDs devem ser C1, C2, C3... em ordem.
- categoria deve ser EXATAMENTE uma destas:
  CALCULO_LOTE, NORMALIZACAO_LOTE, PRECO_STOP, TRAILING,
  BREAK_EVEN, POSICAO_ORDEM, SPREAD, INDICADOR,
  VALIDACAO_PARAMETRO, OUTRO.
- simbolo_chave deve ser a variavel, chamada ou identificador principal
  diretamente ligado ao candidato, quando houver.
- Responda SOMENTE JSON valido, sem Markdown.

FORMATO EXATO:
{{
  "candidatos": [
    {{
      "id": "C1",
      "funcao": "NomeDaFuncao",
      "linhas": "100-120",
      "categoria": "CALCULO_LOTE",
      "simbolo_chave": "distanciaStop",
      "problema": "descricao curta e objetiva",
      "evidencia": "cadeia objetiva observada no codigo"
    }}
  ]
}}
"""

    print()
    print("=" * 70)
    print("GATE 1/4 - DESCOBERTA REPETIDA COM MESMO SEED")
    print("=" * 70)

    # Warm-up: a primeira inferencia apos o load do modelo no Ollama pode
    # divergir (KV/compute state frio) mesmo com seed fixo. Uma chamada
    # descartavel com o mesmo prompt garante que A e B rodem 'quentes' e
    # produzam saida identica.
    chat_deterministico(
        [
            {
                "role": "system",
                "content": (
                    "Analise apenas o MQL5 fornecido. "
                    "Retorne somente JSON valido."
                )
            },
            {
                "role": "user",
                "content": prompt_descoberta
            }
        ],
        seed=19601
    )

    resposta_a = chat_deterministico(
        [
            {
                "role": "system",
                "content": (
                    "Analise apenas o MQL5 fornecido. "
                    "Retorne somente JSON valido."
                )
            },
            {
                "role": "user",
                "content": prompt_descoberta
            }
        ],
        seed=19601
    )

    resposta_b = chat_deterministico(
        [
            {
                "role": "system",
                "content": (
                    "Analise apenas o MQL5 fornecido. "
                    "Retorne somente JSON valido."
                )
            },
            {
                "role": "user",
                "content": prompt_descoberta
            }
        ],
        seed=19601
    )

    dados_a = extrair_json_modelo(
        resposta_a.message.content or ""
    )
    dados_b = extrair_json_modelo(
        resposta_b.message.content or ""
    )

    candidatos_a = canonicalizar_candidatos(dados_a)
    candidatos_b = canonicalizar_candidatos(dados_b)

    assinatura_textual_a = hash_texto(
        json.dumps(
            candidatos_a,
            ensure_ascii=False,
            sort_keys=True
        )
    )
    assinatura_textual_b = hash_texto(
        json.dumps(
            candidatos_b,
            ensure_ascii=False,
            sort_keys=True
        )
    )

    repetivel, candidatos_consenso, diagnostico = (
        comparar_e_fundir_candidatos(
            candidatos_a,
            candidatos_b
        )
    )

    assinatura_estrut_a = assinatura_estrutural(candidatos_a)
    assinatura_estrut_b = assinatura_estrutural(candidatos_b)

    print(f"Assinatura textual A: {assinatura_textual_a}")
    print(f"Assinatura textual B: {assinatura_textual_b}")
    print(f"Assinatura estrutural A: {assinatura_estrut_a}")
    print(f"Assinatura estrutural B: {assinatura_estrut_b}")
    print(f"Candidatos A: {len(candidatos_a)}")
    print(f"Candidatos B: {len(candidatos_b)}")

    if assinatura_textual_a != assinatura_textual_b:
        print(
            "OBSERVACAO: houve variacao de redacao entre as duas "
            "descobertas. A V1.9.6.1 ignora somente diferencas textuais."
        )

    if not repetivel:
        print()
        print("=" * 70)
        print("AUDITORIA BLOQUEADA POR DIFERENCA SEMANTICA/ESTRUTURAL")
        print("=" * 70)
        print(
            "As duas descobertas nao puderam ser pareadas 1:1 por "
            "funcao, regiao de linhas, categoria e simbolo-chave."
        )
        print(f"Motivo tecnico: {diagnostico.get('motivo')}")
        print("AUTOCORRECAO AUTORIZADA: NAO")
        print("QUANTIDADE DE BUGS CONFIRMADOS: 0")
        print()

        registro = {
            "arquivo": caminho,
            "sha256_codigo": sha_inicial,
            "repetibilidade_descoberta": False,
            "assinatura_textual_a": assinatura_textual_a,
            "assinatura_textual_b": assinatura_textual_b,
            "assinatura_estrutural_a": assinatura_estrut_a,
            "assinatura_estrutural_b": assinatura_estrut_b,
            "diagnostico": diagnostico,
            "candidatos_a": candidatos_a,
            "candidatos_b": candidatos_b,
            "confirmados": []
        }
        salvar_auditoria_deterministica(registro)

        return {
            "arquivo": caminho,
            "nome": nome,
            "tipo": alvo.get("tipo"),
            "autorizado": False,
            "quantidade": 0,
            "veredito": (
                "VEREDITO FINAL\n"
                f"ARQUIVO: {caminho}\n"
                "AUTOCORRECAO AUTORIZADA: NAO\n"
                "QUANTIDADE DE BUGS CONFIRMADOS: 0\n"
                "MOTIVO: descobertas semanticamente diferentes."
            ),
            "deterministico_aprovado": False,
            "sha256_codigo": sha_inicial
        }

    candidatos_a = candidatos_consenso
    assinatura_a = assinatura_estrutural(candidatos_a)

    print(
        "REPETIBILIDADE SEMANTICA/ESTRUTURAL DA DESCOBERTA: APROVADA"
    )
    print(f"Candidatos pareados 1:1: {len(candidatos_a)}")

    if not candidatos_a:
        print()
        print("=" * 70)
        print("VEREDITO DETERMINISTICO FINAL")
        print("=" * 70)
        print("Nenhum candidato passou pela descoberta conservadora.")
        print("AUTOCORRECAO AUTORIZADA: NAO")
        print("QUANTIDADE DE BUGS CONFIRMADOS: 0")
        print()

        registro = {
            "arquivo": caminho,
            "sha256_codigo": sha_inicial,
            "repetibilidade_descoberta": True,
            "modo_repetibilidade": "SEMANTICO_ESTRUTURAL",
            "assinatura_descoberta": assinatura_a,
            "candidatos": [],
            "confirmados": [],
            "assinatura_final": hash_texto("SEM_BUGS")
        }
        salvar_auditoria_deterministica(registro)

        return {
            "arquivo": caminho,
            "nome": nome,
            "tipo": alvo.get("tipo"),
            "autorizado": False,
            "quantidade": 0,
            "veredito": (
                "VEREDITO FINAL\n"
                f"ARQUIVO: {caminho}\n"
                "CONFIRMADOS PARA CORRECAO\n"
                "- Nenhum\n"
                "AUTOCORRECAO AUTORIZADA: NAO\n"
                "QUANTIDADE DE BUGS CONFIRMADOS: 0"
            ),
            "deterministico_aprovado": True,
            "sha256_codigo": sha_inicial,
            "assinatura_final": registro["assinatura_final"]
        }

    candidatos_json = json.dumps(
        candidatos_a,
        ensure_ascii=False,
        indent=2
    )

    prompt_validador = f"""
Voce e um VALIDADOR INDEPENDENTE E CONSERVADOR DE MQL5.

ARQUIVO:
{caminho}

SHA256:
{sha_inicial}

CODIGO REAL:
--- INICIO ---
{codigo_numerado}
--- FIM ---

CANDIDATOS FIXOS:
{candidatos_json}

TAREFA:
Avalie EXATAMENTE cada candidato recebido. Nao crie candidatos novos.

Para marcar CONFIRMADO:
- a condicao precisa estar demonstrada no codigo;
- a chamada/uso relevante precisa estar demonstrada;
- as validacoes anteriores precisam ter sido consideradas;
- o efeito precisa ser inevitavel ou concretamente alcancavel pela cadeia mostrada;
- nao pode depender apenas de suposicao;
- nao pode ser comportamento configuravel/intencional.

STATUS PERMITIDOS:
CONFIRMADO
NAO_CONFIRMADO
COMPORTAMENTO_INTENCIONAL

Responda SOMENTE JSON valido:
{{
  "itens": [
    {{
      "id": "C1",
      "status": "CONFIRMADO",
      "motivo": "justificativa objetiva baseada no codigo"
    }}
  ]
}}
"""

    print()
    print("=" * 70)
    print("GATE 2/4 - DOIS VALIDADORES INDEPENDENTES")
    print("=" * 70)

    val_a_resp = chat_deterministico(
        [
            {
                "role": "system",
                "content": (
                    "Valide apenas os candidatos fornecidos. "
                    "Se houver duvida, marque NAO_CONFIRMADO. "
                    "Retorne somente JSON."
                )
            },
            {
                "role": "user",
                "content": prompt_validador
            }
        ],
        seed=19602
    )

    val_b_resp = chat_deterministico(
        [
            {
                "role": "system",
                "content": (
                    "Valide apenas os candidatos fornecidos. "
                    "Se houver duvida, marque NAO_CONFIRMADO. "
                    "Retorne somente JSON."
                )
            },
            {
                "role": "user",
                "content": prompt_validador
            }
        ],
        seed=19603
    )

    val_a = canonicalizar_validacao(
        extrair_json_modelo(
            val_a_resp.message.content or ""
        )
    )
    val_b = canonicalizar_validacao(
        extrair_json_modelo(
            val_b_resp.message.content or ""
        )
    )

    confirmados = []
    rejeitados = []

    for candidato in candidatos_a:
        cid = candidato["id"]
        a = val_a.get(
            cid,
            {
                "status": "NAO_CONFIRMADO",
                "motivo": "Validador A nao retornou classificacao valida."
            }
        )
        b = val_b.get(
            cid,
            {
                "status": "NAO_CONFIRMADO",
                "motivo": "Validador B nao retornou classificacao valida."
            }
        )

        if (
            a["status"] == "CONFIRMADO"
            and b["status"] == "CONFIRMADO"
        ):
            item = dict(candidato)
            item["validador_a"] = a["motivo"]
            item["validador_b"] = b["motivo"]
            confirmados.append(item)
        else:
            rejeitados.append({
                **candidato,
                "status_a": a["status"],
                "status_b": b["status"],
                "motivo_a": a["motivo"],
                "motivo_b": b["motivo"]
            })

    print(f"Candidatos avaliados: {len(candidatos_a)}")
    print(f"Confirmados por unanimidade: {len(confirmados)}")
    print(f"Rejeitados/nao unanimes: {len(rejeitados)}")

    print()
    print("=" * 70)
    print("GATE 3/4 - VERIFICACAO DE IMUTABILIDADE DO ARQUIVO")
    print("=" * 70)

    codigo_final, erro_final = ler_alvo_resolvido(alvo)

    if erro_final:
        print("Nao foi possivel reler o arquivo ao final da auditoria.")
        return None

    sha_final_codigo = hash_texto(codigo_final)
    print(f"SHA256 inicial: {sha_inicial}")
    print(f"SHA256 final:   {sha_final_codigo}")

    imutavel = sha_inicial == sha_final_codigo

    if not imutavel:
        print("FALHA: o arquivo mudou durante uma auditoria somente leitura.")
        print("AUTOCORRECAO AUTORIZADA: NAO")
        print()

        return {
            "arquivo": caminho,
            "nome": nome,
            "tipo": alvo.get("tipo"),
            "autorizado": False,
            "quantidade": 0,
            "veredito": (
                "VEREDITO FINAL\n"
                f"ARQUIVO: {caminho}\n"
                "AUTOCORRECAO AUTORIZADA: NAO\n"
                "QUANTIDADE DE BUGS CONFIRMADOS: 0\n"
                "MOTIVO: arquivo mudou durante auditoria."
            ),
            "deterministico_aprovado": False,
            "sha256_codigo": sha_inicial
        }

    print("IMUTABILIDADE: APROVADA")

    assinatura_final = hash_texto(
        json.dumps(
            confirmados,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":")
        )
    )

    print()
    print("=" * 70)
    print("GATE 4/4 - VEREDITO DETERMINISTICO FINAL")
    print("=" * 70)
    print(f"Assinatura final: {assinatura_final}")
    print()

    linhas_veredito = [
        "VEREDITO FINAL",
        f"ARQUIVO: {caminho}",
        f"SHA256 CODIGO: {sha_inicial}",
        "MODO: AUDITORIA DETERMINISTICA SEMANTICA V1.9.6.1",
        "",
        "CONFIRMADOS PARA CORRECAO"
    ]

    if confirmados:
        for item in confirmados:
            linhas_veredito.append(
                f"- {item['id']} | Funcao {item['funcao']} | "
                f"Linhas {item['linhas']} | {item['problema']}"
            )
    else:
        linhas_veredito.append("- Nenhum")

    linhas_veredito.extend([
        "",
        "REJEITADOS / NAO CONFIRMADOS"
    ])

    if rejeitados:
        for item in rejeitados:
            linhas_veredito.append(
                f"- {item['id']} | Funcao {item['funcao']} | "
                f"A={item['status_a']} | B={item['status_b']}"
            )
    else:
        linhas_veredito.append("- Nenhum")

    autorizado = len(confirmados) > 0

    linhas_veredito.extend([
        "",
        "REPETIBILIDADE SEMANTICA/ESTRUTURAL: APROVADA",
        "DOIS VALIDADORES: CONCLUIDOS",
        "IMUTABILIDADE DO ARQUIVO: APROVADA",
        f"AUTOCORRECAO AUTORIZADA: {'SIM' if autorizado else 'NAO'}",
        f"QUANTIDADE DE BUGS CONFIRMADOS: {len(confirmados)}",
        f"ASSINATURA FINAL: {assinatura_final}"
    ])

    veredito_texto = "\n".join(linhas_veredito)

    print(veredito_texto)
    print()

    registro = {
        "arquivo": caminho,
        "sha256_codigo": sha_inicial,
        "repetibilidade_descoberta": True,
        "assinatura_descoberta": assinatura_a,
        "candidatos": candidatos_a,
        "validador_a": val_a,
        "validador_b": val_b,
        "confirmados": confirmados,
        "rejeitados": rejeitados,
        "assinatura_final": assinatura_final,
        "autorizado": autorizado
    }

    salvar_auditoria_deterministica(registro)

    return {
        "arquivo": caminho,
        "nome": nome,
        "tipo": alvo.get("tipo"),
        "autorizado": autorizado,
        "quantidade": len(confirmados),
        "veredito": veredito_texto,
        "deterministico_aprovado": True,
        "sha256_codigo": sha_inicial,
        "assinatura_final": assinatura_final,
        "confirmados": confirmados,
        "rejeitados": rejeitados
    }




# ============================================================
# TIMEOUT REAL + IDENTIDADE DO BUG - V1.9.6.3
# ============================================================

TIMEOUT_MODELO_SEGUNDOS = 120


def chat_texto_com_timeout(messages, timeout_segundos=TIMEOUT_MODELO_SEGUNDOS, options=None):
    """
    Chama o modelo com timeout real de socket e fallback NVIDIA -> Ollama.
    Retorna (texto, erro). Nao deixa o CMD esperando indefinidamente.
    """
    modelo = _obter_modelo("CODER")

    if _MODEL_ROUTER is not None:
        try:
            resultado = _MODEL_ROUTER.chat(
                modelo,
                messages,
                timeout=timeout_segundos,
                options=options,
            )
            if resultado.error:
                return "", resultado.error
            return (resultado.text or ""), None
        except Exception as erro:
            return "", f"{type(erro).__name__}: {erro}"

    payload = {
        "model": modelo,
        "messages": messages,
        "stream": False
    }

    if options:
        payload["options"] = options

    dados = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=dados,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=float(timeout_segundos)
        ) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(bruto)
            return (
                str(
                    (obj.get("message") or {}).get("content", "")
                ),
                None
            )
    except Exception as erro:
        nome = type(erro).__name__
        return "", f"{nome}: {erro}"


# ============================================================
# CHAMADA UNIFICADA AO MODELO (fallback NVIDIA -> Ollama)
# ============================================================

class _FuncaoChamada:
    def __init__(self, name="", arguments=None):
        self.name = name
        self.arguments = arguments


class _ChamadaFerramenta:
    def __init__(self, function):
        self.function = function


class _MensagemModelo:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _RespostaModelo:
    def __init__(self, content="", tool_calls=None):
        self.message = _MensagemModelo(content, tool_calls)


def _normalizar_tool_calls(tool_calls):
    """Converte tool_calls (Ollama/NVIDIA/OpenAI) no estilo SDK do cliente ollama."""
    normalizadas = []
    for chamada in (tool_calls or []):
        if not isinstance(chamada, dict):
            normalizadas.append(chamada)
            continue
        funcao = chamada.get("function")
        if not isinstance(funcao, dict):
            continue
        nome = funcao.get("name", "")
        argumentos = funcao.get("arguments", "")
        if argumentos is None:
            argumentos = ""
        if not isinstance(argumentos, (str, dict)):
            try:
                argumentos = json.dumps(argumentos)
            except Exception:
                argumentos = str(argumentos)
        normalizadas.append(
            _ChamadaFerramenta(_FuncaoChamada(nome, argumentos))
        )
    return normalizadas


def _chamar_modelo(messages, tools=None, timeout_segundos=TIMEOUT_MODELO_SEGUNDOS, options=None, perfil="CODER"):
    """
    Chamada unificada ao modelo com fallback NVIDIA -> Ollama via ModelRouter.
    Retorna objeto com .message.content e .message.tool_calls (estilo SDK).
    Se tudo falhar, tenta o SDK local como ultimo recurso.
    """
    modelo = _obter_modelo(perfil)

    if _MODEL_ROUTER is not None:
        try:
            resultado = _MODEL_ROUTER.chat(
                modelo,
                messages,
                timeout=timeout_segundos,
                options=options,
                tools=tools,
            )
            if not resultado.error:
                return _RespostaModelo(
                    content=resultado.text or "",
                    tool_calls=_normalizar_tool_calls(resultado.tool_calls),
                )
            erro_router = resultado.error
        except Exception as erro:
            erro_router = f"{type(erro).__name__}: {erro}"

        try:
            return chat(model=modelo, messages=messages, tools=tools)
        except Exception as erro_sdk:
            return _RespostaModelo(
                content=(
                    "[GoldenAI ERRO DE MODELO] Fallback externo/local falhou: "
                    f"{erro_router} | SDK: {type(erro_sdk).__name__}: {erro_sdk}"
                )
            )

    return chat(model=modelo, messages=messages, tools=tools)


def extrair_confirmados_do_texto_veredito(veredito_texto):
    """
    Reconstrói a identidade C1/C2... diretamente do VEREDITO FINAL textual.
    Usado como segunda fonte para impedir que um C1 vire outro bug por
    inconsistência de estado estruturado.
    """
    saida = {}
    if not isinstance(veredito_texto, str):
        return saida

    padrao = re.compile(
        r"^\s*-\s*(C\d+)\s*\|\s*Funcao\s+([^|]+?)\s*\|\s*"
        r"Linhas\s+([^|]+?)\s*\|\s*(.+?)\s*$",
        flags=re.IGNORECASE
    )

    for linha in veredito_texto.splitlines():
        m = padrao.match(linha)
        if not m:
            continue

        cid = m.group(1).upper()
        saida[cid] = {
            "id": cid,
            "funcao": m.group(2).strip(),
            "linhas": m.group(3).strip(),
            "problema": m.group(4).strip()
        }

    return saida


def validar_identidade_bugs_selecionados(veredito_salvo, bugs):
    """
    Exige concordância entre o estado estruturado e o texto final salvo.
    """
    pelo_texto = extrair_confirmados_do_texto_veredito(
        veredito_salvo.get("veredito", "")
    )

    if not pelo_texto:
        return False, "Nao foi possivel reconstruir IDs do veredito textual."

    for bug in bugs:
        cid = str(bug.get("id", "")).upper()
        esperado = pelo_texto.get(cid)

        if not esperado:
            return False, f"{cid} nao existe no veredito textual salvo."

        func_a = _norm_identificador(bug.get("funcao"))
        func_b = _norm_identificador(esperado.get("funcao"))

        if func_a != func_b:
            return False, (
                f"INCONSISTENCIA DE IDENTIDADE: {cid} no estado estruturado "
                f"aponta para '{bug.get('funcao')}', mas no veredito textual "
                f"aponta para '{esperado.get('funcao')}'."
            )

    return True, "Identidade dos bugs confirmada pelo veredito textual."


def localizar_intervalo_por_linha(codigo, linhas_referencia):
    """
    Fallback seguro: usa a linha auditada para localizar a função MQL5
    que a contém, sem depender do nome fornecido pelo modelo.
    """
    linhas = codigo.splitlines()
    nums = [int(x) for x in re.findall(r"\d+", str(linhas_referencia or ""))]
    if not nums:
        return None

    alvo = max(1, min(nums)) - 1
    alvo = min(alvo, max(0, len(linhas) - 1))

    # Procura assinaturas candidatas para trás, até 180 linhas.
    for idx in range(alvo, max(-1, alvo - 180), -1):
        trecho = linhas[idx].strip()

        # Assinatura típica: tipo NomeFuncao(...), não if/for/while/switch.
        if "(" not in trecho:
            continue
        if re.match(r"^(if|for|while|switch|return)\b", trecho, flags=re.I):
            continue

        m = re.search(
            r"\b([A-Za-z_]\w*)\s*\(",
            trecho
        )
        if not m:
            continue

        nome = m.group(1)
        intervalo = localizar_intervalo_funcao(codigo, nome)
        if not intervalo:
            continue

        ini, fim = intervalo
        if ini <= alvo + 1 <= fim:
            return intervalo, nome

    return None


def resolver_intervalo_bug(codigo, bug):
    """
    1) tenta o nome exato;
    2) se o nome auditado não for uma função real, usa a linha auditada;
    3) retorna também o nome real da função encontrada.
    """
    funcao_auditada = str(bug.get("funcao", "")).strip()

    intervalo = localizar_intervalo_funcao(
        codigo,
        funcao_auditada
    )

    if intervalo:
        return intervalo, funcao_auditada, "NOME_EXATO"

    fallback = localizar_intervalo_por_linha(
        codigo,
        bug.get("linhas", "")
    )

    if fallback:
        intervalo_real, nome_real = fallback
        return intervalo_real, nome_real, "LINHA_AUDITADA"

    return None, None, "NAO_LOCALIZADO"


# ============================================================
# AUTOCORRECAO AUTONOMA POR BUG - V1.9.6.3
# ============================================================


def classificar_intencao_usuario(pergunta):
    """
    V1.9.8.1 - roteador de intenção explícita.

    Prioridade:
    1) PROIBICOES/LEITURA: investigar, analisar, diagnosticar, revalidar, mostrar,
       sem alterar, nao altere, nao execute autocorrecao, somente leitura.
    2) ESCRITA: corrigir, autocorrigir, executar autocorrecao, aplicar patch etc.

    Regra fundamental: uma ordem explícita de NÃO ESCREVER prevalece sobre
    qualquer veredito salvo ou palavra "bug".
    """
    p = str(pergunta or "").lower()

    termos_leitura = [
        "investigue", "investigar",
        "analise", "analisar",
        "diagnostique", "diagnosticar",
        "revalide", "revalidar", "revalidação", "revalidacao",
        "mostre", "mostrar",
        "somente leitura",
        "sem alterar", "não alterar", "nao alterar",
        "não altere", "nao altere",
        "não execute autocorreção", "nao execute autocorrecao",
        "não executar autocorreção", "nao executar autocorrecao",
        "proibido alterar",
        "proibido gerar patch",
        "proibido executar autocorreção", "proibido executar autocorrecao",
        "não gere patch", "nao gere patch",
        "não corrija", "nao corrija",
        "não modificar", "nao modificar",
        "não modifique", "nao modifique",
    ]

    termos_escrita = [
        "execute a autocorreção", "execute a autocorrecao",
        "executar autocorreção", "executar autocorrecao",
        "autocorrija", "autocorrigir",
        "corrija", "corrigir",
        "aplique patch", "aplicar patch",
        "altere o arquivo", "alterar o arquivo",
        "faça a correção", "faca a correcao",
        "implemente a correção", "implemente a correcao",
    ]

    leitura = any(t in p for t in termos_leitura)
    escrita = any(t in p for t in termos_escrita)

    # Proibições explícitas vencem.
    if leitura:
        return "LEITURA"
    if escrita:
        return "ESCRITA"
    return "NEUTRA"


def pedido_proibe_escrita(pergunta):
    return classificar_intencao_usuario(pergunta) == "LEITURA"


def normalizar_intencao_conversa(pergunta):
    texto = str(pergunta or "").lower()
    substituicoes = {
        "ã¡": "a", "á": "a", "à": "a", "â": "a", "ã": "a",
        "ã©": "e", "é": "e", "ê": "e",
        "ã­": "i", "í": "i",
        "ã³": "o", "ó": "o", "ô": "o", "õ": "o",
        "ãº": "u", "ú": "u",
        "ã§": "c", "ç": "c",
    }
    for antigo, novo in substituicoes.items():
        texto = texto.replace(antigo, novo)
    return texto


def usuario_mudou_para_conversa_geral(pergunta):
    texto = normalizar_intencao_conversa(pergunta)
    marcadores = [
        "nao quero falar",
        "nao vamos falar",
        "esqueca o robo",
        "esqueca robos",
        "mudar de assunto",
        "vamos falar sobre",
        "quero falar sobre",
        "quero conversar sobre",
        "falar de carros",
        "falar sobre carros",
    ]
    return any(marcador in texto for marcador in marcadores)


def pergunta_pede_contexto_tecnico(pergunta):
    texto = normalizar_intencao_conversa(pergunta)
    if usuario_mudou_para_conversa_geral(texto):
        return False
    if pergunta_pede_market(pergunta):
        return True

    referencias = [
        "arquivo selecionado", "arquivo atual", "este arquivo", "desse arquivo",
        "arquivo alvo", "alvo atual", "projeto selecionado", "meu projeto",
        "este projeto", "codigo selecionado", "este codigo", "desse codigo",
        "robo selecionado", "este robo", "desse robo", "meu robo",
        "voltando ao robo", "voltar ao robo", "voltando ao arquivo",
        "break-even", "break even", "breakeven", "breakevenpreco",
        ".mq5", ".mqh", "mql5",
    ]
    acoes = [
        "analise", "analisar", "explique", "explicar", "veja", "verifique",
        "audite", "revise", "compile", "compilar", "corrija", "corrigir",
        "erro", "bug", "funcao", "função", "codigo", "o que", "qual",
    ]
    return any(ref in texto for ref in referencias) and any(acao in texto for acao in acoes)


def pergunta_pede_ferramenta_local(pergunta):
    texto = normalizar_intencao_conversa(pergunta)
    if usuario_mudou_para_conversa_geral(texto):
        return False

    grupos = [
        ["que dia", "dia da semana", "data atual", "hora atual", "que horas", "horas sao", "horas são"],
        ["memoria", "memória", "ram", "cpu", "processador", "windows", "computador", "meu pc"],
        ["espaco livre", "espaço livre", "uso de disco", "disco", "armazenamento"],
        ["processo", "processos", "rodando", "aberto", "aberta"],
        ["metatrader", "meta trader", "mt5", "metaeditor"],
        ["abrir pasta", "abra a pasta", "abrir notepad", "abra o notepad", "abrir explorer", "abra o explorer"],
    ]
    return any(any(termo in texto for termo in grupo) for grupo in grupos)


def _formatar_bytes(valor):
    try:
        numero = float(valor)
    except Exception:
        return str(valor)
    unidades = ["B", "KB", "MB", "GB", "TB"]
    indice = 0
    while numero >= 1024 and indice < len(unidades) - 1:
        numero /= 1024
        indice += 1
    return f"{numero:.2f} {unidades[indice]}"


def _weekday_pt(nome):
    mapa = {
        "Monday": "segunda-feira",
        "Tuesday": "terca-feira",
        "Wednesday": "quarta-feira",
        "Thursday": "quinta-feira",
        "Friday": "sexta-feira",
        "Saturday": "sabado",
        "Sunday": "domingo",
    }
    return mapa.get(str(nome), str(nome))


def responder_consulta_local(pergunta):
    texto = normalizar_intencao_conversa(pergunta)
    if not pergunta_pede_ferramenta_local(pergunta):
        return False

    nome = None
    argumentos = {}

    if any(termo in texto for termo in ["metatrader", "meta trader", "mt5", "metaeditor"]):
        nome = "get_mt5_status"
    elif any(termo in texto for termo in ["que dia", "dia da semana", "data atual", "hora atual", "que horas", "horas sao", "horas são"]):
        nome = "get_current_datetime"
    elif any(termo in texto for termo in ["memoria", "memória", "ram", "cpu", "processador", "windows", "computador", "meu pc"]):
        nome = "get_system_info"
    elif any(termo in texto for termo in ["espaco livre", "espaço livre", "uso de disco", "disco", "armazenamento"]):
        nome = "get_disk_usage"
        argumentos = {"path": r"C:\GoldenAI"}
    elif any(termo in texto for termo in ["processo", "processos", "rodando"]):
        nome = "list_processes"
        argumentos = {"filter_name": "", "limit": 25}
    elif any(termo in texto for termo in ["abrir notepad", "abra o notepad"]):
        nome = "launch_allowed_app"
        argumentos = {"name": "notepad"}
    elif any(termo in texto for termo in ["abrir explorer", "abra o explorer"]):
        nome = "launch_allowed_app"
        argumentos = {"name": "explorer"}
    elif any(termo in texto for termo in ["abrir pasta", "abra a pasta"]):
        nome = "open_folder"
        argumentos = {"path": ROOT_GOLDENAI}

    if not nome:
        return False

    print()
    print(f"[GoldenAI usando ferramenta: {nome}]")
    resultado = executar_tool_core(nome, argumentos)

    if nome == "get_current_datetime" and isinstance(resultado, dict):
        resposta = (
            f"Hoje e {resultado.get('date')} ({_weekday_pt(resultado.get('weekday'))}). "
            f"A hora local e {resultado.get('time')} ({resultado.get('timezone')})."
        )
    elif nome == "get_system_info" and isinstance(resultado, dict):
        resposta = (
            "Informacoes seguras do computador:\n"
            f"- Windows: {resultado.get('windows_version')}\n"
            f"- CPU: {resultado.get('cpu_model')}\n"
            f"- Nucleos logicos: {resultado.get('logical_cpus')}\n"
            f"- RAM total: {_formatar_bytes(resultado.get('ram_total_bytes'))}\n"
            f"- RAM disponivel: {_formatar_bytes(resultado.get('ram_available_bytes'))}"
        )
    elif nome == "get_disk_usage" and isinstance(resultado, dict):
        if resultado.get("ok") is False:
            resposta = f"Nao consegui consultar o disco: {resultado.get('error')}"
        else:
            resposta = (
                f"Uso de disco em {resultado.get('path')}:\n"
                f"- Total: {_formatar_bytes(resultado.get('total_bytes'))}\n"
                f"- Usado: {_formatar_bytes(resultado.get('used_bytes'))}\n"
                f"- Livre: {_formatar_bytes(resultado.get('free_bytes'))}"
            )
    elif nome == "get_mt5_status" and isinstance(resultado, dict):
        linhas = [
            "Status do MetaTrader 5:\n",
            f"- MT5 aberto: {'sim' if resultado.get('mt5_running') else 'nao'}",
            f"- MetaEditor aberto: {'sim' if resultado.get('metaeditor_running') else 'nao'}",
            f"- Instalacoes encontradas: {len(resultado.get('installations') or [])}",
        ]

        for inst_info in (resultado.get('installations') or []):
            inst_name = inst_info.get('name', '')
            inst_path = inst_info.get('path', '')
            linhas.append(f"\nInstalacao: {inst_name}")
            linhas.append(f"  Caminho: {inst_path}")

        try:
            instalacoes = detect_all_mt5_installations()
            for inst in instalacoes:
                linhas.append(f"\nTerminal ID: {inst.terminal_id}")
                if inst.terminal_exe:
                    linhas.append(f"  Terminal: {inst.terminal_exe}")
                if inst.metaeditor_exe:
                    linhas.append(f"  MetaEditor: {inst.metaeditor_exe}")
                if inst.mql5_path:
                    linhas.append(f"  Pasta MQL5: {inst.mql5_path}")
                if inst.experts_path:
                    linhas.append(f"  Pasta Experts: {inst.experts_path}")
                if inst.indicators_path:
                    linhas.append(f"  Pasta Indicators: {inst.indicators_path}")
                if inst.scripts_path:
                    linhas.append(f"  Pasta Scripts: {inst.scripts_path}")
                linhas.append(f"  Rodando: {'sim' if inst.is_running else 'nao'}")
        except Exception as e:
            linhas.append(f"\n(Detalhes de instalacao indisponiveis: {e})")

        try:
            eas = list_mt5_eas()
            linhas.append(f"\nTotal de EAs (.mq5/.mqh): {len(eas)}")
            if eas:
                for ea in eas[:5]:
                    linhas.append(f"  - {os.path.basename(ea)}")
                if len(eas) > 5:
                    linhas.append(f"  ... e mais {len(eas) - 5} arquivos")
        except Exception as e:
            linhas.append(f"\n(Listagem de EAs indisponivel: {e})")

        resposta = "\n".join(linhas)
    elif nome == "list_processes" and isinstance(resultado, list):
        linhas = [
            f"- {proc.get('image_name')} (PID {proc.get('pid')})"
            for proc in resultado[:25]
        ]
        resposta = "Processos visiveis:\n" + "\n".join(linhas) if linhas else "Nenhum processo encontrado."
    else:
        resposta = str(resultado)

    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True



def _extrair_argumentos_chamada(linha, nome_funcao):
    """
    Extrator simples e conservador de argumentos de uma chamada em uma linha.
    Retorna [] se nao conseguir provar a estrutura.
    """
    s = str(linha or "")
    m = re.search(rf"\b{re.escape(nome_funcao)}\s*\(", s, flags=re.IGNORECASE)
    if not m:
        return []

    i = m.end()
    nivel = 1
    atual = []
    args = []
    em_string = False
    escape = False

    while i < len(s):
        ch = s[i]

        if em_string:
            atual.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                em_string = False
            i += 1
            continue

        if ch == '"':
            em_string = True
            atual.append(ch)
        elif ch == "(":
            nivel += 1
            atual.append(ch)
        elif ch == ")":
            nivel -= 1
            if nivel == 0:
                if "".join(atual).strip():
                    args.append("".join(atual).strip())
                return args
            atual.append(ch)
        elif ch == "," and nivel == 1:
            args.append("".join(atual).strip())
            atual = []
        else:
            atual.append(ch)

        i += 1

    return []


def _lhs_da_chamada(linha, nome_funcao):
    """
    Detecta a variavel que recebe o retorno:
    double novoSL = BreakEvenPreco(...);
    novoSL = BreakEvenPreco(...);
    """
    s = str(linha or "")
    if not re.search(rf"\b{re.escape(nome_funcao)}\s*\(", s, flags=re.IGNORECASE):
        return None

    esquerda = s.split("=", 1)[0].strip() if "=" in s else ""
    if not esquerda:
        return None

    tokens = re.findall(r"\b[A-Za-z_]\w*\b", esquerda)
    if not tokens:
        return None

    return tokens[-1]


def _funcao_que_contem_linha(codigo, linha_num):
    achado = localizar_intervalo_por_linha(codigo, str(int(linha_num)))
    if not achado:
        return None, None
    intervalo, nome = achado
    return intervalo, nome


def _rastrear_definicoes_variavel(codigo, linha_chamada, nome_variavel, limite=12):
    """
    Procura definicoes/atribuicoes da variavel antes da chamada,
    preferencialmente dentro da mesma funcao.
    """
    var = str(nome_variavel or "").strip()
    if not re.fullmatch(r"[A-Za-z_]\w*", var):
        return []

    linhas = codigo.splitlines()
    intervalo_func, nome_func = _funcao_que_contem_linha(codigo, linha_chamada)

    if intervalo_func:
        ini = intervalo_func[0]
    else:
        ini = max(1, linha_chamada - 220)

    resultados = []
    rx = re.compile(rf"\b{re.escape(var)}\b")

    for n in range(linha_chamada - 1, ini - 1, -1):
        linha = linhas[n - 1]
        if not rx.search(linha):
            continue

        # Definicao, parametro, atribuicao ou alteracao.
        eh_interessante = (
            "=" in linha
            or re.search(rf"\b(?:double|int|long|ulong|bool|ENUM_[A-Z_]+)\s+{re.escape(var)}\b", linha)
            or ("(" in linha and ")" in linha)
        )

        if eh_interessante:
            resultados.append({
                "linha": n,
                "texto": linha.strip(),
                "funcao_contexto": nome_func
            })

        if len(resultados) >= limite:
            break

    return resultados


def _rastrear_usos_variavel_depois(codigo, linha_chamada, nome_variavel, limite=18):
    """
    Procura usos do valor retornado depois da chamada dentro da mesma funcao.
    """
    var = str(nome_variavel or "").strip()
    if not var or not re.fullmatch(r"[A-Za-z_]\w*", var):
        return []

    linhas = codigo.splitlines()
    intervalo_func, nome_func = _funcao_que_contem_linha(codigo, linha_chamada)

    fim = intervalo_func[1] if intervalo_func else min(len(linhas), linha_chamada + 220)
    rx = re.compile(rf"\b{re.escape(var)}\b")
    resultados = []

    for n in range(linha_chamada + 1, fim + 1):
        linha = linhas[n - 1]
        if rx.search(linha):
            resultados.append({
                "linha": n,
                "texto": linha.strip(),
                "funcao_contexto": nome_func
            })
        if len(resultados) >= limite:
            break

    return resultados


def _buscar_simbolo_no_codigo(codigo, simbolo, limite=20):
    """
    Busca declaracoes/usos relevantes de um simbolo no arquivo inteiro.
    """
    s = str(simbolo or "").strip()
    if not s:
        return []

    linhas = codigo.splitlines()
    rx = re.compile(rf"\b{re.escape(s)}\b")
    resultados = []

    for n, linha in enumerate(linhas, start=1):
        if rx.search(linha):
            resultados.append({
                "linha": n,
                "texto": linha.strip()
            })
        if len(resultados) >= limite:
            break

    return resultados


def _coletar_dependencias_profunda(codigo, funcao_real, intervalo, chamadas):
    """
    Coleta evidencias interprocedurais para a investigacao:
    - argumentos de cada chamada;
    - origem das variaveis passadas;
    - funcao chamadora;
    - variavel que recebe o retorno;
    - usos posteriores do retorno;
    - simbolos operacionais usados dentro da funcao alvo;
    - funcoes auxiliares chamadas pela funcao alvo.
    """
    linhas = codigo.splitlines()
    funcao_alvo = _extrair_funcao_por_intervalo(codigo, intervalo)

    relatorio = {
        "chamadas": [],
        "simbolos": {},
        "funcoes_auxiliares": {}
    }

    # Identificadores especiais/relevantes presentes na funcao alvo.
    candidatos_simbolos = [
        "BreakEvenOffsetPontos",
        "_Point",
        "_Digits",
        "SYMBOL_BID",
        "SYMBOL_ASK",
        "SYMBOL_TRADE_STOPS_LEVEL",
        "SYMBOL_TRADE_FREEZE_LEVEL"
    ]

    for simbolo in candidatos_simbolos:
        if re.search(rf"\b{re.escape(simbolo)}\b", funcao_alvo):
            relatorio["simbolos"][simbolo] = _buscar_simbolo_no_codigo(
                codigo,
                simbolo,
                limite=30
            )

    # Funcoes chamadas de dentro da funcao alvo.
    palavras_ignoradas = {
        "if", "for", "while", "switch", "return",
        funcao_real.lower()
    }
    nomes_chamados = []
    for nome in re.findall(r"\b([A-Za-z_]\w*)\s*\(", funcao_alvo):
        if nome.lower() in palavras_ignoradas:
            continue
        if nome not in nomes_chamados:
            nomes_chamados.append(nome)

    for nome in nomes_chamados[:20]:
        inter = localizar_intervalo_funcao(codigo, nome)
        if inter:
            relatorio["funcoes_auxiliares"][nome] = {
                "intervalo": list(inter),
                "codigo": _extrair_funcao_por_intervalo(codigo, inter)
            }

    # Cada chamada real.
    for linha_num, linha_txt in chamadas:
        # Ignora a propria assinatura/definicao da funcao alvo.
        if intervalo[0] <= linha_num <= intervalo[1]:
            continue

        args = _extrair_argumentos_chamada(linha_txt, funcao_real)
        lhs = _lhs_da_chamada(linha_txt, funcao_real)
        intervalo_chamadora, nome_chamadora = _funcao_que_contem_linha(
            codigo,
            linha_num
        )

        item = {
            "linha": linha_num,
            "texto": linha_txt,
            "funcao_chamadora": nome_chamadora,
            "intervalo_chamadora": list(intervalo_chamadora) if intervalo_chamadora else None,
            "argumentos": [],
            "lhs_retorno": lhs,
            "usos_retorno_depois": _rastrear_usos_variavel_depois(
                codigo,
                linha_num,
                lhs
            ) if lhs else []
        }

        for arg in args:
            arg_item = {
                "expressao": arg,
                "definicoes_anteriores": []
            }

            # Se for variavel simples, rastreia origem.
            if re.fullmatch(r"[A-Za-z_]\w*", arg):
                arg_item["definicoes_anteriores"] = _rastrear_definicoes_variavel(
                    codigo,
                    linha_num,
                    arg
                )

            item["argumentos"].append(arg_item)

        # Inclui pequeno contexto da funcao chamadora.
        if intervalo_chamadora:
            ini, fim = intervalo_chamadora
            a = max(ini, linha_num - 24)
            b = min(fim, linha_num + 35)
            item["contexto_chamada"] = "\n".join(
                f"{n:05d}: {linhas[n-1]}"
                for n in range(a, b + 1)
            )
        else:
            item["contexto_chamada"] = ""

        relatorio["chamadas"].append(item)

    return relatorio


def executar_investigacao_somente_leitura(alvo, veredito_salvo, pergunta):
    """
    V1.9.8.2 - Investigacao profunda SOMENTE LEITURA.

    Alem de localizar a funcao, segue dependencias:
    chamadas -> argumentos -> definicoes -> retorno -> usos posteriores ->
    auxiliares/simbolos usados pela funcao alvo.

    Nunca escreve arquivo, nunca executa autocorrecao e nunca altera veredito.
    """
    print()
    print("=" * 76)
    print("ROTA SOMENTE LEITURA - INVESTIGACAO PROFUNDA / DATA-FLOW")
    print("=" * 76)

    if not alvo or not alvo.get("ok"):
        print("BLOQUEADO: nenhum arquivo alvo valido.")
        print()
        return

    if not veredito_salvo:
        print("BLOQUEADO: nao existe veredito salvo para contextualizar a investigacao.")
        print()
        return

    codigo, erro = ler_alvo_resolvido(alvo)
    if erro:
        print("BLOQUEADO: " + str(erro))
        print()
        return

    bugs, ids = selecionar_bugs_para_correcao(veredito_salvo, pergunta)
    if not bugs:
        print("Nenhum bug do veredito corresponde ao pedido.")
        print()
        return

    bug = bugs[0]
    bug_id = str(bug.get("id", "")).upper()
    intervalo, funcao_real, metodo = resolver_intervalo_bug(codigo, bug)

    print(f"BUG EM INVESTIGACAO: {bug_id}")
    print(f"FUNCAO ASSOCIADA: {funcao_real or 'NAO_LOCALIZADA'}")
    print("MODO: SOMENTE LEITURA")
    print("AUTOCORRECAO: BLOQUEADA")
    print("ESCRITA EM ARQUIVO: BLOQUEADA")
    print("VEREDITO SALVO: IMUTAVEL")
    print()

    if not intervalo or not funcao_real:
        print("Nao foi possivel localizar a funcao com seguranca.")
        print()
        return

    funcao = _extrair_funcao_por_intervalo(codigo, intervalo)
    contexto = _contexto_funcao(codigo, intervalo, margem=120)

    # V1.9.8.3 - envia a implementação alvo de forma explícita e numerada.
    linhas_codigo = codigo.splitlines()
    funcao_numerada = "\n".join(
        f"{n:05d}: {linhas_codigo[n-1]}"
        for n in range(intervalo[0], intervalo[1] + 1)
    )

    chamadas = []
    padrao = re.compile(rf"\b{re.escape(funcao_real)}\s*\(", flags=re.IGNORECASE)
    for n, linha in enumerate(codigo.splitlines(), start=1):
        if padrao.search(linha):
            chamadas.append((n, linha.strip()))

    dependencias = _coletar_dependencias_profunda(
        codigo,
        funcao_real,
        intervalo,
        chamadas
    )

    # Funções auxiliares completas + numeradas.
    auxiliares_explicitas = {}
    for nome_aux, info_aux in (dependencias.get("funcoes_auxiliares") or {}).items():
        inter_aux = info_aux.get("intervalo")
        if inter_aux and len(inter_aux) == 2:
            aux_num = "\n".join(
                f"{n:05d}: {linhas_codigo[n-1]}"
                for n in range(int(inter_aux[0]), int(inter_aux[1]) + 1)
            )
            auxiliares_explicitas[nome_aux] = {
                "intervalo": inter_aux,
                "codigo_numerado": aux_num
            }

    chamadas_reais = [
        x for x in dependencias["chamadas"]
    ]

    pacote_evidencias = {
        "bug_id": bug_id,
        "funcao_alvo": funcao_real,
        "intervalo_funcao_alvo": list(intervalo),
        "funcao_alvo_codigo_numerado": funcao_numerada,
        "chamadas_e_dataflow": dependencias.get("chamadas", []),
        "simbolos_e_configuracoes": dependencias.get("simbolos", {}),
        "funcoes_auxiliares_completas": auxiliares_explicitas
    }

    print(f"INTERVALO DA FUNCAO: linhas {intervalo[0]}-{intervalo[1]} ({metodo})")
    print()
    print("IMPLEMENTACAO COMPLETA DA FUNCAO ALVO:")
    print(funcao_numerada)
    print()
    print(f"CHAMADAS REAIS ANALISADAS: {len(chamadas_reais)}")

    for item in chamadas_reais:
        print(
            f"  linha {item['linha']} em "
            f"{item.get('funcao_chamadora') or 'CONTEXTO_DESCONHECIDO'}:"
        )
        print(f"    {item['texto']}")
        if item.get("argumentos"):
            for idx_arg, arg in enumerate(item["argumentos"], start=1):
                print(f"    arg{idx_arg}: {arg.get('expressao')}")
                for d in arg.get("definicoes_anteriores", [])[:5]:
                    print(f"      origem linha {d['linha']}: {d['texto']}")
        if item.get("lhs_retorno"):
            print(f"    retorno recebido por: {item['lhs_retorno']}")
            for u in item.get("usos_retorno_depois", [])[:8]:
                print(f"      uso linha {u['linha']}: {u['texto']}")
    print()

    if dependencias.get("simbolos"):
        print("SIMBOLOS/CONFIGURACOES RASTREADOS:")
        for simbolo, ocorrencias in dependencias["simbolos"].items():
            print(f"  {simbolo}:")
            for o in ocorrencias[:8]:
                print(f"    linha {o['linha']}: {o['texto']}")
        print()

    if auxiliares_explicitas:
        print("FUNCOES AUXILIARES COMPLETAS:")
        for nome, info in auxiliares_explicitas.items():
            inter = info.get("intervalo") or []
            print(
                f"  {nome}: linhas "
                f"{inter[0] if inter else '?'}-{inter[1] if inter else '?'}"
            )
            print(info.get("codigo_numerado", ""))
            print()

    schema = {
        "type": "object",
        "properties": {
            "diagnostico": {
                "type": "string",
                "enum": ["CONFIRMADO", "FALSO_POSITIVO", "INCONCLUSIVO"]
            },
            "evidencia_concreta": {"type": "string"},
            "caminho_execucao": {"type": "string"},
            "calculo_ou_regra": {"type": "string"},
            "informacao_faltante": {"type": "string"},
            "informacao_faltante_existe_no_codigo_fornecido": {"type": "boolean"},
            "observacoes": {"type": "string"}
        },
        "required": [
            "diagnostico",
            "evidencia_concreta",
            "caminho_execucao",
            "calculo_ou_regra",
            "informacao_faltante",
            "informacao_faltante_existe_no_codigo_fornecido",
            "observacoes"
        ],
        "additionalProperties": False
    }

    bug_json = json.dumps(bug, ensure_ascii=False, indent=2)
    deps_json = json.dumps(dependencias, ensure_ascii=False, indent=2)
    pacote_json = json.dumps(pacote_evidencias, ensure_ascii=False, indent=2)

    prompt = f"""
Voce esta em MODO FORENSE MQL5 SOMENTE LEITURA.

BUG DO VEREDITO:
{bug_json}

FUNCAO REAL:
{funcao_real}

IMPLEMENTACAO COMPLETA E NUMERADA DA FUNCAO ALVO:
--- INICIO FUNCAO ALVO ---
{funcao_numerada}
--- FIM FUNCAO ALVO ---

CONTEXTO AMPLO:
--- INICIO CONTEXTO ---
{contexto}
--- FIM CONTEXTO ---

PACOTE EXPLICITO DE EVIDENCIAS:
{pacote_json}

RASTREAMENTO AUTOMATICO DE DEPENDENCIAS E DATA-FLOW:
{deps_json}

TAREFA:
1. Siga cada chamada real da funcao.
2. Analise de onde vem cada argumento.
3. Analise configuracoes/simbolos usados dentro da funcao.
4. Analise funcoes auxiliares localizadas.
5. Siga o valor retornado ate seus usos posteriores.
6. Para CONFIRMADO, mostre um caminho concreto de execucao e a regra objetiva
   que torna o resultado incorreto.
7. Possibilidade teorica nao basta.
8. A IMPLEMENTACAO COMPLETA DA FUNCAO ALVO FOI FORNECIDA ACIMA.
   E proibido responder que "falta a implementacao de {funcao_real}".
9. As funcoes auxiliares localizadas tambem foram fornecidas completas e numeradas.
   Se NormalizarPreco estiver no pacote, e proibido alegar que sua implementacao nao foi fornecida.
10. Se o rastreamento fornecido ja contem a informacao que voce diria estar faltando,
    voce DEVE usa-la; nao responda INCONCLUSIVO por nao ter procurado.
11. FALSO_POSITIVO se o codigo atual nao demonstra o problema.
12. INCONCLUSIVO somente se faltar informacao indispensavel que realmente nao esteja
    no codigo/fluxo fornecido. Diga exatamente qual dado EXTERNO AO ARQUIVO falta.
13. Nao proponha patch. Nao mude estrategia. Nao altere veredito.
"""

    respostas = []
    for seed in (19921, 19922):
        obj, erro = _chat_json_estruturado_timeout(
            [
                {
                    "role": "system",
                    "content": (
                        "Investigue profundamente o fluxo de dados. "
                        "Somente leitura. Nao proponha correcao."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            schema,
            timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
            options={
                "temperature": 0.0,
                "top_p": 0.1,
                "top_k": 1,
                "seed": seed
            }
        )

        if erro or not isinstance(obj, dict):
            obj = {
                "diagnostico": "INCONCLUSIVO",
                "evidencia_concreta": "",
                "caminho_execucao": "",
                "calculo_ou_regra": "",
                "informacao_faltante": erro or "Resposta invalida do revisor.",
                "informacao_faltante_existe_no_codigo_fornecido": False,
                "observacoes": ""
            }

        respostas.append(obj)

    # Segunda passada automatica se o revisor disser que falta algo que ja existe
    # no pacote de evidencias fornecido.
    termos_impossiveis = [
        "implementacao da funcao",
        "implementação da função",
        "breakEvenPreco".lower(),
        "normalizarpreco"
    ]

    def _alega_falta_que_ja_foi_fornecida(resposta):
        falta = str(resposta.get("informacao_faltante", "")).lower()
        evidencia = str(resposta.get("evidencia_concreta", "")).lower()
        combinado = falta + " " + evidencia

        if resposta.get("informacao_faltante_existe_no_codigo_fornecido") is True:
            return True

        if "implementa" in combinado and (
            funcao_real.lower() in combinado
            or "normalizarpreco" in combinado
        ):
            return True

        return False

    precisa_segunda_passada = any(
        str(r.get("diagnostico", "")).upper() == "INCONCLUSIVO"
        and _alega_falta_que_ja_foi_fornecida(r)
        for r in respostas
    )

    if precisa_segunda_passada:
        print("SEGUNDA PASSADA FORENSE: reavaliando informacao ja presente no codigo...")
        respostas2 = []

        for idx_rev, r_anterior in enumerate(respostas, start=1):
            prompt2 = prompt + f"""

O revisor anterior respondeu:
{json.dumps(r_anterior, ensure_ascii=False, indent=2)}

A IMPLEMENTACAO COMPLETA DE {funcao_real} foi fornecida nas linhas
{intervalo[0]}-{intervalo[1]} e esta reproduzida integralmente no prompt.
As funcoes auxiliares localizadas tambem foram fornecidas completas.

Se a resposta anterior alegou falta dessa implementacao, essa alegacao e INVALIDA.
REANALISE O MATERIAL JA ENTREGUE e produza diagnostico final.
Nao use INCONCLUSIVO por falta de informacao que esta explicitamente no pacote.
INCONCLUSIVO so e permitido para dado realmente externo ao arquivo alvo.
"""
            obj2, erro2 = _chat_json_estruturado_timeout(
                [
                    {
                        "role": "system",
                        "content": (
                            "Segunda passada. Use obrigatoriamente as evidencias "
                            "interprocedurais ja fornecidas."
                        )
                    },
                    {"role": "user", "content": prompt2}
                ],
                schema,
                timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
                options={
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "top_k": 1,
                    "seed": 19930 + idx_rev
                }
            )

            if erro2 or not isinstance(obj2, dict):
                obj2 = r_anterior

            respostas2.append(obj2)

        respostas = respostas2

    print()
    print("RESULTADO DA INVESTIGACAO PROFUNDA")
    print("-" * 76)

    for i, r in enumerate(respostas, start=1):
        print(f"Revisor {i}: {r.get('diagnostico')}")
        print("  Evidencia: " + str(r.get("evidencia_concreta", "")))
        print("  Caminho: " + str(r.get("caminho_execucao", "")))
        print("  Regra/calculo: " + str(r.get("calculo_ou_regra", "")))
        if r.get("informacao_faltante"):
            print("  Falta: " + str(r.get("informacao_faltante", "")))
        print()

    statuses = [
        str(r.get("diagnostico", "")).upper()
        for r in respostas
    ]

    if statuses == ["CONFIRMADO", "CONFIRMADO"]:
        final = "CONFIRMADO"
    elif statuses == ["FALSO_POSITIVO", "FALSO_POSITIVO"]:
        final = "FALSO_POSITIVO"
    else:
        final = "INCONCLUSIVO"

    print("=" * 76)
    print("DIAGNOSTICO FINAL: " + final)
    print("NENHUM ARQUIVO FOI ALTERADO.")
    print("AUTOCORRECAO NAO FOI EXECUTADA.")
    print("VEREDITO SALVO NAO FOI MODIFICADO.")
    print("=" * 76)
    print()
    return


def extrair_ids_solicitados(pergunta):
    """
    Extrai apenas IDs POSITIVAMENTE autorizados pelo usuario.

    Regra V1.9.6.6:
    - pedidos exclusivos como "somente C1", "somente do bug C1" ou
      "autorize exclusivamente o ID C1" prevalecem;
    - IDs citados apenas em frases negativas como
      "nao corrija C2, C3..." nao viram autorizacao.
    """
    texto = str(pergunta or "")
    texto_lower = texto.lower()

    padroes_exclusivos = [
        r"(?:autorize|autorizar)\s+exclusivamente\s+(?:o\s+)?(?:id\s+)?C(\d+)",
        r"(?:exclusivamente)\s+(?:o\s+)?(?:id\s+)?C(\d+)",
        r"(?:somente|apenas)\s+(?:do\s+)?(?:bug\s+|id\s+)?C(\d+)",
        r"(?:corrija|corrigir|correcao|autocorrecao)\s+(?:somente|apenas)\s+(?:do\s+)?(?:bug\s+|id\s+)?C(\d+)",
    ]

    exclusivos = []
    for padrao in padroes_exclusivos:
        for n in re.findall(padrao, texto, flags=re.IGNORECASE):
            cid = f"C{int(n)}"
            if cid not in exclusivos:
                exclusivos.append(cid)

    if exclusivos:
        return exclusivos

    # Remove trechos explicitamente negativos antes do fallback.
    texto_positivo = re.sub(
        r"(?i)\bnao\s+(?:corrija|corrigir|autorize|altere|inclua)\b[^.\n;]*",
        " ",
        texto
    )

    ids = re.findall(
        r"\bC(\d+)\b",
        texto_positivo,
        flags=re.IGNORECASE
    )

    resultado = []
    for n in ids:
        cid = f"C{int(n)}"
        if cid not in resultado:
            resultado.append(cid)
    return resultado


def selecionar_bugs_para_correcao(veredito_salvo, pergunta):
    confirmados = veredito_salvo.get("confirmados", []) or []
    if not isinstance(confirmados, list):
        confirmados = []

    ids_pedidos = extrair_ids_solicitados(pergunta)
    pergunta_lower = str(pergunta or "").lower()

    if ids_pedidos:
        selecionados = [
            item for item in confirmados
            if str(item.get("id", "")).upper() in ids_pedidos
        ]
        return selecionados, ids_pedidos

    um_por_vez = any(
        termo in pergunta_lower
        for termo in [
            "1 bug por vez",
            "um bug por vez",
            "somente 1 bug",
            "apenas 1 bug",
            "corrija um bug",
            "corrigir um bug"
        ]
    )

    if um_por_vez and confirmados:
        primeiro = sorted(
            confirmados,
            key=lambda x: int(
                re.sub(r"\D", "", str(x.get("id", "9999"))) or 9999
            )
        )[0]
        return [primeiro], [str(primeiro.get("id", "")).upper()]

    return confirmados, [
        str(item.get("id", "")).upper()
        for item in confirmados
    ]


def localizar_intervalo_funcao(codigo, nome_funcao):
    """
    Localiza uma funcao MQL5 por assinatura + balanceamento de chaves.
    Retorna (linha_inicio, linha_fim) 1-based.
    """
    linhas = codigo.splitlines()
    alvo = re.escape(str(nome_funcao or "").strip())

    if not alvo:
        return None

    padrao = re.compile(
        rf"\b{alvo}\s*\(",
        flags=re.IGNORECASE
    )

    for idx, linha in enumerate(linhas):
        if not padrao.search(linha):
            continue

        # Evita chamadas simples: procura a chave de abertura na mesma
        # linha ou nas proximas poucas linhas da assinatura.
        inicio_chave = None
        for j in range(idx, min(idx + 8, len(linhas))):
            if "{" in linhas[j]:
                inicio_chave = j
                break
            if ";" in linhas[j]:
                break

        if inicio_chave is None:
            continue

        saldo = 0
        entrou = False

        for j in range(inicio_chave, len(linhas)):
            for ch in linhas[j]:
                if ch == "{":
                    saldo += 1
                    entrou = True
                elif ch == "}":
                    saldo -= 1

            if entrou and saldo == 0:
                return idx + 1, j + 1

    return None


def validar_escopo_diff(codigo_antes, codigo_depois, bugs):
    """
    Rejeita candidato que altere qualquer trecho fora das funcoes
    explicitamente autorizadas.
    """
    import difflib

    intervalos = []
    funcoes = []

    for bug in bugs:
        funcao = str(bug.get("funcao", "")).strip()

        intervalo, funcao_real, metodo = resolver_intervalo_bug(
            codigo_antes,
            bug
        )

        if not intervalo:
            return False, (
                f"Nao foi possivel localizar o escopo do bug "
                f"{bug.get('id')} ('{funcao}') nem pelo nome nem "
                f"pelas linhas {bug.get('linhas')}."
            ), []

        intervalos.append(intervalo)
        funcoes.append(
            f"{funcao_real} [{metodo}]"
        )

    def permitido(indice_zero_based):
        linha = indice_zero_based + 1
        return any(
            ini <= linha <= fim
            for ini, fim in intervalos
        )

    antes = codigo_antes.splitlines()
    depois = codigo_depois.splitlines()
    sm = difflib.SequenceMatcher(
        a=antes,
        b=depois,
        autojunk=False
    )

    alteracoes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue

        # Para insercao pura, ancora na linha anterior/seguinte do original.
        indices_old = list(range(i1, i2))
        if not indices_old:
            ancora = max(0, min(i1, max(0, len(antes) - 1)))
            indices_old = [ancora]

        if not all(permitido(i) for i in indices_old):
            return False, (
                "Candidato tentou alterar codigo fora das funcoes "
                f"autorizadas: {', '.join(funcoes)}."
            ), alteracoes

        alteracoes.append({
            "tipo": tag,
            "antes_linhas": [i1 + 1, i2],
            "depois_linhas": [j1 + 1, j2]
        })

    if not alteracoes:
        return False, "Candidato nao produziu alteracao real.", []

    return True, "Escopo de alteracao aprovado.", alteracoes


def validar_correcao_pos_compilacao(
    codigo_antes,
    codigo_depois,
    bugs
):
    """
    Dois revisores determinísticos verificam somente:
    1) se cada bug alvo foi realmente corrigido;
    2) se a estrategia/parametros fora do alvo não foram alterados.
    A decisão final é local: ambos precisam aprovar.
    """
    bugs_json = json.dumps(
        bugs,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
Voce e um REVISOR DE PATCH MQL5 extremamente conservador.

BUGS AUTORIZADOS:
{bugs_json}

CODIGO ANTES:
--- INICIO ANTES ---
{codigo_antes}
--- FIM ANTES ---

CODIGO DEPOIS:
--- INICIO DEPOIS ---
{codigo_depois}
--- FIM DEPOIS ---

TAREFA:
Avalie SOMENTE se o patch corrigiu os bugs autorizados.

REGRAS:
- Todos os bugs autorizados precisam estar resolvidos.
- Nao aceite se a estrategia de entrada/saida foi alterada.
- Nao aceite se parametros operacionais/defaults foram alterados.
- Nao aceite se houve mudanca funcional fora das funcoes alvo.
- Nao aceite apenas porque compila.
- Na duvida, REPROVADO.

Responda SOMENTE JSON:
{{
  "status": "APROVADO" ou "REPROVADO",
  "bugs_resolvidos": ["C1"],
  "motivo": "justificativa objetiva"
}}
"""

    respostas = []

    for seed in [19621, 19622]:
        texto_val, erro_val = chat_texto_com_timeout(
            [
                {
                    "role": "system",
                    "content": (
                        "Revise o patch de forma conservadora. "
                        "Retorne somente JSON."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
            options={
                "temperature": 0.0,
                "seed": seed,
                "top_p": 0.1,
                "top_k": 1,
                "repeat_penalty": 1.0
            }
        )

        if erro_val:
            respostas.append({
                "status": "REPROVADO",
                "bugs_resolvidos": [],
                "motivo": (
                    "Validador pos-correcao excedeu timeout ou falhou: "
                    + erro_val
                )
            })
            continue

        dados = extrair_json_modelo(
            texto_val
        )

        if not isinstance(dados, dict):
            respostas.append({
                "status": "REPROVADO",
                "bugs_resolvidos": [],
                "motivo": "Resposta do validador nao foi JSON valido."
            })
            continue

        status = str(
            dados.get("status", "REPROVADO")
        ).strip().upper()

        if status != "APROVADO":
            status = "REPROVADO"

        resolvidos = [
            str(x).strip().upper()
            for x in (
                dados.get("bugs_resolvidos", [])
                if isinstance(dados.get("bugs_resolvidos", []), list)
                else []
            )
        ]

        respostas.append({
            "status": status,
            "bugs_resolvidos": resolvidos,
            "motivo": " ".join(
                str(dados.get("motivo", "")).split()
            )
        })

    ids_esperados = {
        str(item.get("id", "")).upper()
        for item in bugs
    }

    aprovado = all(
        r["status"] == "APROVADO"
        and ids_esperados.issubset(set(r["bugs_resolvidos"]))
        for r in respostas
    )

    return aprovado, respostas


# ============================================================
# AUTOCORRECAO SEMANTICA AUTORIZADA - V1.9.5
# ============================================================


def _chat_json_estruturado_timeout(messages, schema, timeout_segundos=TIMEOUT_MODELO_SEGUNDOS, options=None):
    """
    Chama o modelo exigindo JSON estruturado quando suportado (fallback
    NVIDIA -> Ollama via ModelRouter). Se nenhum provider aceitar 'format'
    como JSON Schema, faz fallback para resposta JSON textual, sem relaxar
    as validacoes locais.
    """
    payload = {
        "model": _obter_modelo("CODER"),
        "messages": messages,
        "stream": False,
        "format": schema
    }
    if options:
        payload["options"] = options

    def _executar(payload_local):
        if _MODEL_ROUTER is not None:
            resultado = _MODEL_ROUTER.chat(
                payload_local["model"],
                payload_local["messages"],
                timeout=timeout_segundos,
                options=payload_local.get("options"),
                format_schema=payload_local.get("format"),
            )
            if resultado.error:
                raise RuntimeError(resultado.error)
            return resultado.text or ""
        dados = json.dumps(payload_local).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=dados,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(
            req,
            timeout=float(timeout_segundos)
        ) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(bruto)
            return str((obj.get("message") or {}).get("content", ""))

    try:
        conteudo = _executar(payload)
    except Exception as erro_schema:
        # Fallback compatível com instalações Ollama mais antigas.
        payload_fallback = dict(payload)
        payload_fallback.pop("format", None)
        mensagens_fb = list(messages)
        mensagens_fb.append({
            "role": "system",
            "content": (
                "RESPONDA SOMENTE JSON VALIDO, sem Markdown e sem texto fora do JSON. "
                "Obedeca exatamente ao formato solicitado."
            )
        })
        payload_fallback["messages"] = mensagens_fb
        try:
            conteudo = _executar(payload_fallback)
        except Exception as erro:
            return None, f"{type(erro).__name__}: {erro}"

    conteudo = (conteudo or "").strip()
    if conteudo.startswith("```"):
        conteudo = re.sub(r"^```(?:json)?\s*", "", conteudo, flags=re.I)
        conteudo = re.sub(r"\s*```$", "", conteudo)

    try:
        return json.loads(conteudo), None
    except Exception as erro:
        return None, f"JSON_INVALIDO: {erro}"


def _extrair_funcao_por_intervalo(codigo, intervalo):
    if not intervalo:
        return ""
    ini, fim = intervalo
    linhas = codigo.splitlines(keepends=True)
    return "".join(linhas[ini - 1:fim])


def _contexto_funcao(codigo, intervalo, margem=45):
    ini, fim = intervalo
    linhas = codigo.splitlines()
    a = max(0, ini - 1 - margem)
    b = min(len(linhas), fim + margem)
    return "\n".join(
        f"{idx + 1:05d}: {linhas[idx]}"
        for idx in range(a, b)
    )


def _normalizar_substituicao_funcao(texto_funcao, nome_funcao):
    """
    Aceita somente uma funcao MQL5 isolada.
    Nao permite texto/codigo antes ou depois da funcao alvo.
    """
    bruto = str(texto_funcao or "").strip()
    if not bruto:
        return None, "FUNCAO_VAZIA"

    if "```" in bruto:
        return None, "MARKDOWN_NAO_PERMITIDO"

    intervalo = localizar_intervalo_funcao(bruto, nome_funcao)
    if not intervalo:
        return None, f"FUNCAO_ALVO_NAO_LOCALIZADA: {nome_funcao}"

    linhas = bruto.splitlines()
    ini, fim = intervalo

    antes = "\n".join(linhas[:ini - 1]).strip()
    depois = "\n".join(linhas[fim:]).strip()

    if antes or depois:
        return None, "RESPOSTA_CONTEM_CODIGO_FORA_DA_FUNCAO_ALVO"

    funcao = "\n".join(linhas[ini - 1:fim]).strip()
    return funcao, None


def _montar_patch_cirurgico(codigo_original, intervalo, nova_funcao):
    """
    Substitui SOMENTE o intervalo autorizado.
    Prefixo e sufixo sao reaproveitados diretamente do original.
    """
    ini, fim = intervalo
    linhas = codigo_original.splitlines(keepends=True)

    prefixo = "".join(linhas[:ini - 1])
    trecho_original = "".join(linhas[ini - 1:fim])
    sufixo = "".join(linhas[fim:])

    # Detecta newline dominante do arquivo.
    newline = "\r\n" if "\r\n" in codigo_original else "\n"
    nova = str(nova_funcao).replace("\r\n", "\n").replace("\r", "\n")
    nova = nova.strip("\n").replace("\n", newline)

    # Se o trecho original terminava com newline, mantem.
    if trecho_original.endswith(("\n", "\r")):
        nova += newline

    candidato = prefixo + nova + sufixo
    return candidato, prefixo, sufixo, trecho_original, nova


def _validar_invariantes_patch_cirurgico(codigo_original, candidato, intervalo, nome_funcao):
    """
    Prova localmente que nada fora da funcao alvo mudou.
    """
    ini, fim = intervalo

    linhas_o = codigo_original.splitlines(keepends=True)
    prefixo_o = "".join(linhas_o[:ini - 1])
    sufixo_o = "".join(linhas_o[fim:])

    intervalo_novo = localizar_intervalo_funcao(candidato, nome_funcao)
    if not intervalo_novo:
        return False, "FUNCAO_ALVO_DESAPARECEU_APOS_PATCH", {}

    ini_n, fim_n = intervalo_novo
    linhas_n = candidato.splitlines(keepends=True)
    prefixo_n = "".join(linhas_n[:ini_n - 1])
    sufixo_n = "".join(linhas_n[fim_n:])

    detalhes = {
        "funcao": nome_funcao,
        "intervalo_antes": [ini, fim],
        "intervalo_depois": [ini_n, fim_n],
        "hash_prefixo_antes": hash_texto(prefixo_o),
        "hash_prefixo_depois": hash_texto(prefixo_n),
        "hash_sufixo_antes": hash_texto(sufixo_o),
        "hash_sufixo_depois": hash_texto(sufixo_n),
    }

    if prefixo_o != prefixo_n:
        return False, "PREFIXO_FORA_DA_FUNCAO_FOI_ALTERADO", detalhes
    if sufixo_o != sufixo_n:
        return False, "SUFIXO_FORA_DA_FUNCAO_FOI_ALTERADO", detalhes

    if codigo_original == candidato:
        return False, "CANDIDATO_IDENTICO_AO_ORIGINAL", detalhes

    return True, "ESCOPO_CIRURGICO_APROVADO", detalhes


def _validar_funcao_pos_compilacao_cirurgica(bug, funcao_antes, funcao_depois, resultado_compilacao):
    """
    Dois revisores independentes recebem apenas o bug e a funcao alterada.
    O resto do arquivo ja foi provado imutavel por hash/prefixo/sufixo.
    """
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["APROVADO", "REPROVADO"]},
            "bug_resolvido": {"type": "boolean"},
            "motivo": {"type": "string"}
        },
        "required": ["status", "bug_resolvido", "motivo"],
        "additionalProperties": False
    }

    bug_json = json.dumps(bug, ensure_ascii=False, indent=2)

    base = f"""
Voce e um REVISOR DE PATCH MQL5 extremamente conservador.

BUG AUTORIZADO:
{bug_json}

FUNCAO ANTES:
--- INICIO ---
{funcao_antes}
--- FIM ---

FUNCAO DEPOIS:
--- INICIO ---
{funcao_depois}
--- FIM ---

COMPILACAO REAL:
errors={resultado_compilacao.get('errors')}
warnings={resultado_compilacao.get('warnings')}

TAREFA:
Decida se a mudanca resolve o bug autorizado sem mudar a finalidade da funcao.
Avalie a validade do preco NO MOMENTO em que a funcao e usada/retornada.
NAO reprove por imaginar que o mercado pode mudar no futuro: qualquer preco pode se tornar
invalido depois que Bid/Ask se moverem, e isso nao prova defeito na funcao atual.
NAO invente exigencias que nao estejam no bug autorizado, no codigo antes/depois ou nas regras MQL5.
Considere relevante: normalizacao do preco, lado BUY/SELL, Bid/Ask atual e protecoes presentes no codigo.
Nao aprove apenas porque compila.
Na duvida baseada em evidencia real do codigo, REPROVADO.
"""

    respostas = []
    for idx, seed in enumerate((19701, 19702), start=1):
        obj, erro = _chat_json_estruturado_timeout(
            [
                {"role": "system", "content": "Revise somente o patch autorizado. Seja conservador."},
                {"role": "user", "content": base}
            ],
            schema,
            timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
            options={"temperature": 0.0, "top_p": 0.1, "top_k": 1, "seed": seed}
        )

        if erro or not isinstance(obj, dict):
            respostas.append({
                "status": "REPROVADO",
                "bug_resolvido": False,
                "motivo": erro or "Resposta invalida do revisor."
            })
            continue

        respostas.append(obj)

    ok = all(
        str(r.get("status", "")).upper() == "APROVADO"
        and r.get("bug_resolvido") is True
        for r in respostas
    )
    return ok, respostas



def _preflight_mql5_funcao(funcao_texto):
    """
    Gate local barato antes de chamar MetaEditor.
    Nao tenta substituir o compilador; apenas bloqueia erros MQL4/MQL5
    muito conhecidos que ja apareceram nas tentativas anteriores.
    """
    codigo = str(funcao_texto or "")

    problemas = []

    # Em MQL5, Bid/Ask nus no estilo MQL4 sao um erro frequente.
    # SymbolInfoDouble(..., SYMBOL_BID/SYMBOL_ASK) e interfaces CSymbolInfo
    # sao formas validas e nao devem ser bloqueadas.
    sem_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', codigo)
    sem_comentarios = re.sub(r'//.*', '', sem_strings)

    if re.search(r'(?<![\w.])Bid(?!\s*\()', sem_comentarios):
        problemas.append(
            "Identificador legado/nao declarado 'Bid'. "
            "Em MQL5, use uma API valida do simbolo quando isso realmente fizer parte do bug."
        )
    if re.search(r'(?<![\w.])Ask(?!\s*\()', sem_comentarios):
        problemas.append(
            "Identificador legado/nao declarado 'Ask'. "
            "Em MQL5, use uma API valida do simbolo quando isso realmente fizer parte do bug."
        )

    return (len(problemas) == 0), problemas


def _revalidar_bug_antes_de_corrigir(bug, funcao_real, funcao_antes, contexto):
    """
    Reabre a pergunta fundamental antes de corrigir:
    'o bug confirmado continua demonstrado pelo codigo atual?'

    Dois revisores independentes podem:
    - CONFIRMADO: ha evidencia suficiente para corrigir;
    - NAO_DEMONSTRADO: o veredito anterior extrapolou o codigo;
    - INCONCLUSIVO: falta evidencia; bloqueia por seguranca.

    Isso evita tentar 'consertar' um falso positivo indefinidamente.
    """
    schema = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["CONFIRMADO", "NAO_DEMONSTRADO", "INCONCLUSIVO"]
            },
            "evidencia": {"type": "string"},
            "condicao_exata_que_falha": {"type": "string"},
            "mudanca_minima_necessaria": {"type": "string"}
        },
        "required": [
            "status",
            "evidencia",
            "condicao_exata_que_falha",
            "mudanca_minima_necessaria"
        ],
        "additionalProperties": False
    }

    bug_json = json.dumps(bug, ensure_ascii=False, indent=2)

    prompt = f"""
Voce e um REVISOR FORENSE DE MQL5. Antes de permitir qualquer alteracao,
reavalie se o bug abaixo esta REALMENTE demonstrado pelo codigo atual.

BUG DO VEREDITO:
{bug_json}

FUNCAO REAL:
{funcao_real}

FUNCAO ATUAL:
--- INICIO ---
{funcao_antes}
--- FIM ---

CONTEXTO DE LEITURA:
--- INICIO ---
{contexto}
--- FIM ---

REGRAS:
- Nao assuma que o veredito anterior esta certo.
- Nao invente cenarios futuros, configuracoes ou chamadas ausentes.
- Um bug so e CONFIRMADO se houver um caminho concreto no codigo que produza o efeito descrito.
- Se a funcao ja possui a protecao necessaria, responda NAO_DEMONSTRADO.
- Ausencia de melhoria, estilo, logging ou validacao extra nao e bug automaticamente.
- Se faltar informacao para provar, responda INCONCLUSIVO.
- 'mudanca_minima_necessaria' deve ser objetiva e nao pode ampliar a finalidade da funcao.
"""

    respostas = []
    for seed in (19801, 19802):
        obj, erro = _chat_json_estruturado_timeout(
            [
                {"role": "system", "content": "Seja conservador e baseado somente em evidencia do codigo."},
                {"role": "user", "content": prompt}
            ],
            schema,
            timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
            options={"temperature": 0.0, "top_p": 0.1, "top_k": 1, "seed": seed}
        )
        if erro or not isinstance(obj, dict):
            respostas.append({
                "status": "INCONCLUSIVO",
                "evidencia": erro or "Resposta invalida.",
                "condicao_exata_que_falha": "",
                "mudanca_minima_necessaria": ""
            })
        else:
            respostas.append(obj)

    statuses = [str(r.get("status", "")).upper() for r in respostas]

    if statuses == ["CONFIRMADO", "CONFIRMADO"]:
        return "CONFIRMADO", respostas

    if statuses == ["NAO_DEMONSTRADO", "NAO_DEMONSTRADO"]:
        return "NAO_DEMONSTRADO", respostas

    return "INCONCLUSIVO", respostas


def _gerar_contrato_correcao(bug, funcao_real, funcao_antes, contexto, revalidacoes):
    """
    Antes do patch, transforma o bug em contrato verificavel.
    O gerador nao recebe liberdade para 'melhorar' a estrategia.
    """
    schema = {
        "type": "object",
        "properties": {
            "bug_id": {"type": "string"},
            "funcao": {"type": "string"},
            "objetivo": {"type": "string"},
            "deve_preservar": {
                "type": "array",
                "items": {"type": "string"}
            },
            "nao_pode_fazer": {
                "type": "array",
                "items": {"type": "string"}
            },
            "criterios_aceitacao": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": [
            "bug_id",
            "funcao",
            "objetivo",
            "deve_preservar",
            "nao_pode_fazer",
            "criterios_aceitacao"
        ],
        "additionalProperties": False
    }

    prompt = f"""
Crie um CONTRATO MINIMO DE CORRECAO MQL5.

BUG:
{json.dumps(bug, ensure_ascii=False, indent=2)}

FUNCAO:
{funcao_real}

CODIGO ATUAL:
--- INICIO ---
{funcao_antes}
--- FIM ---

CONTEXTO:
--- INICIO ---
{contexto}
--- FIM ---

REVALIDACAO:
{json.dumps(revalidacoes, ensure_ascii=False, indent=2)}

REGRAS:
- O contrato deve resolver SOMENTE o bug confirmado.
- Nao adicione filtros de mercado, regras de estrategia ou protecoes nao exigidas pelo bug.
- Preserve assinatura, direcao BUY/SELL, defaults e semantica nao relacionada.
- Criterios de aceitacao devem ser verificaveis olhando codigo e compilacao.
"""

    obj, erro = _chat_json_estruturado_timeout(
        [
            {"role": "system", "content": "Produza um contrato minimo e verificavel; sem melhorias opcionais."},
            {"role": "user", "content": prompt}
        ],
        schema,
        timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
        options={"temperature": 0.0, "top_p": 0.1, "top_k": 1, "seed": 19810}
    )

    if erro or not isinstance(obj, dict):
        return None, erro or "Contrato invalido."

    return obj, None


def _validar_patch_contra_contrato(bug, contrato, funcao_antes, funcao_depois, resultado_compilacao):
    """
    Revisores julgam o PATCH contra um contrato previamente congelado.
    Eles nao podem criar novos requisitos durante a avaliacao.
    """
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["APROVADO", "REPROVADO"]},
            "criterios_atendidos": {
                "type": "array",
                "items": {"type": "string"}
            },
            "criterios_violados": {
                "type": "array",
                "items": {"type": "string"}
            },
            "motivo": {"type": "string"}
        },
        "required": [
            "status",
            "criterios_atendidos",
            "criterios_violados",
            "motivo"
        ],
        "additionalProperties": False
    }

    prompt = f"""
Voce e um REVISOR DE PATCH MQL5.

BUG:
{json.dumps(bug, ensure_ascii=False, indent=2)}

CONTRATO CONGELADO:
{json.dumps(contrato, ensure_ascii=False, indent=2)}

FUNCAO ANTES:
--- INICIO ---
{funcao_antes}
--- FIM ---

FUNCAO DEPOIS:
--- INICIO ---
{funcao_depois}
--- FIM ---

COMPILACAO:
errors={resultado_compilacao.get('errors')}
warnings={resultado_compilacao.get('warnings')}

REGRAS ABSOLUTAS:
- Julgue SOMENTE pelos criterios do contrato congelado.
- Nao crie requisito novo.
- Nao reprove por hipotese futura nao demonstrada.
- Se o patch amplia a finalidade da funcao alem do contrato, REPROVADO.
- Se compila e cumpre todos os criterios do contrato sem violacoes, APROVADO.
"""

    respostas = []
    for seed in (19821, 19822):
        obj, erro = _chat_json_estruturado_timeout(
            [
                {"role": "system", "content": "Nao invente requisitos fora do contrato."},
                {"role": "user", "content": prompt}
            ],
            schema,
            timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
            options={"temperature": 0.0, "top_p": 0.1, "top_k": 1, "seed": seed}
        )
        if erro or not isinstance(obj, dict):
            respostas.append({
                "status": "REPROVADO",
                "criterios_atendidos": [],
                "criterios_violados": ["resposta_invalida"],
                "motivo": erro or "Resposta invalida."
            })
        else:
            respostas.append(obj)

    ok = all(str(r.get("status", "")).upper() == "APROVADO" for r in respostas)
    return ok, respostas


def _gerar_patch_cirurgico_opencode(bug, contrato, funcao_real, funcao_antes, contexto, rejeicoes_txt, bug_id, caminho):
    """
    Gera a replacement_function via OpenCode (modelos Free) com tarefa CONCRETA
    de patch cirurgico. Retorna (obj, erro). Nao edita o arquivo: o agente
    retorna somente o JSON com a funcao corrigida.
    """
    schema_texto = (
        '{"bug_id": "' + bug_id + '", "funcao": "' + funcao_real + '", '
        '"replacement_function": "<funcao MQL5 COMPLETA corrigida>"}'
    )
    bug_json = json.dumps(bug, ensure_ascii=False, indent=2)
    contrato_json = json.dumps(contrato, ensure_ascii=False, indent=2)

    tarefa = f"""Arquivo alvo (SOMENTE LEITURA - nao altere o arquivo em disco): {caminho}

Voce e um engenheiro senior de MQL5 em modo PATCH CIRURGICO.

REGRAS ABSOLUTAS:
- Corrija SOMENTE o bug autorizado.
- Altere SOMENTE a funcao autorizada.
- NAO altere o arquivo em disco: apenas leia e retorne o JSON pedido.
- Nao crie funcoes auxiliares fora da funcao autorizada.
- Nao mude assinaturas, inputs, parametros globais, estrategia ou defaults.
- Preserve a finalidade e o comportamento nao relacionado ao bug.
- Faca a menor correcao necessaria.
- NAO responda com perguntas nem analise longa. Retorne SOMENTE o JSON.

BUG AUTORIZADO:
{bug_json}

CONTRATO DE CORRECAO CONGELADO:
{contrato_json}

FUNCAO REAL AUTORIZADA:
{funcao_real}

FUNCAO ORIGINAL:
--- INICIO FUNCAO ---
{funcao_antes}
--- FIM FUNCAO ---

CONTEXTO SOMENTE PARA LEITURA (NAO PODE SER ALTERADO):
--- INICIO CONTEXTO ---
{contexto}
--- FIM CONTEXTO ---

REJEICOES DE TENTATIVAS ANTERIORES:
{rejeicoes_txt}

IMPORTANTE:
- Se uma tentativa anterior foi reprovada, produza uma solucao MATERIALMENTE
  diferente que responda apenas aos motivos tecnicos validos da reprovacao.
- Nao devolva exatamente a mesma funcao de uma tentativa rejeitada.
- Nao altere nada fora da funcao autorizada.
- Obedeca literalmente ao CONTRATO DE CORRECAO CONGELADO.
- replacement_function deve conter a funcao MQL5 COMPLETA, e somente ela.

Retorne exatamente este JSON (sem markdown):
{schema_texto}
"""

    resultado = executar_opencode(tarefa, diretorio=PASTA_PROJETOS)
    if not resultado.get("ok"):
        return None, resultado.get("erro") or "OpenCode nao gerou o patch."

    obj = extrair_json_modelo(resultado.get("texto") or "")
    if not isinstance(obj, dict):
        return None, "JSON invalido retornado pelo OpenCode."
    return obj, None


def corrigir_bugs_confirmados_alvo(alvo, veredito_salvo, pedido_usuario):
    if pedido_proibe_escrita(pedido_usuario):
        print()
        print("BLOQUEADO: o pedido atual proibe escrita/autocorrecao.")
        print("Use a rota SOMENTE LEITURA para investigar.")
        print()
        return {
            "status": "BLOQUEADA_POR_INTENCAO_LEITURA",
            "original_mt5_alterado": False,
            "rollback_executado": False
        }
    """
    V1.9.7.0 - EDICAO CIRURGICA POR FUNCAO.

    Principio:
    - uma execucao corrige exatamente 1 bug confirmado;
    - localiza a funcao real autorizada;
    - envia ao modelo somente a funcao + contexto de leitura;
    - o modelo devolve somente a funcao substituta em JSON;
    - a GoldenAI monta o arquivo final localmente;
    - prefixo e sufixo fora da funcao precisam permanecer byte-a-byte iguais;
    - compila no MetaEditor;
    - dois revisores aprovam a funcao;
    - qualquer falha gera rollback.
    """
    import difflib

    print()
    print("=" * 72)
    print("AUTOCORRECAO CIRURGICA POR FUNCAO - V1.9.8.0")
    print("=" * 72)

    relatorio_path = globals().get(
        "ARQUIVO_RELATORIO_AUTOCORRECAO",
        os.path.join(PASTA_APP, "ultima_autocorrecao.json")
    )

    relatorio = {
        "data_hora": datetime.now().isoformat(timespec="seconds"),
        "relatorio_path": relatorio_path,
        "modo": "EDICAO_CIRURGICA_FUNCAO",
        "status": "BLOQUEADA",
        "arquivo": None,
        "caminho": None,
        "backup": None,
        "bugs_autorizados": 0,
        "ids_autorizados": [],
        "funcao_autorizada": None,
        "intervalo_autorizado": None,
        "sha256_antes": None,
        "sha256_depois": None,
        "compilacao": {},
        "invariantes_escopo": {},
        "alteracoes": [],
        "rollback_executado": False,
        "original_mt5_alterado": False,
        "tentativas": [],
        "observacao": ""
    }

    def bloquear(msg, status="BLOQUEADA"):
        relatorio["status"] = status
        relatorio["observacao"] = msg
        salvar_relatorio_autocorrecao(relatorio)
        print("BLOQUEADO: " + msg)
        print()
        return relatorio

    if not alvo or not alvo.get("ok"):
        return bloquear("Nenhum arquivo alvo valido.")
    if alvo.get("tipo") != "PROJETO_TESTE":
        return bloquear("Somente PROJETO_TESTE pode ser alterado.")
    if not veredito_salvo:
        return bloquear("Nao existe veredito salvo.")
    if os.path.abspath(veredito_salvo.get("arquivo", "")) != os.path.abspath(alvo.get("caminho", "")):
        return bloquear("O veredito salvo pertence a outro arquivo.")
    if not veredito_salvo.get("deterministico_aprovado"):
        return bloquear("O veredito nao possui gate deterministico aprovado.")
    if not veredito_salvo.get("autorizado"):
        return bloquear("O veredito nao autorizou autocorrecao.")

    confirmar_alvo_na_tela(alvo, "AUTOCORRECAO CIRURGICA")

    nome = alvo.get("nome")
    caminho = alvo.get("caminho")
    relatorio["arquivo"] = nome
    relatorio["caminho"] = caminho

    bugs_selecionados, ids_solicitados = selecionar_bugs_para_correcao(
        veredito_salvo,
        pedido_usuario
    )

    # Segurança deliberada: um bug por execução.
    if len(bugs_selecionados) != 1:
        return bloquear(
            f"A edicao cirurgica exige exatamente 1 bug por execucao; recebidos {len(bugs_selecionados)}.",
            "BLOQUEADA_QUANTIDADE_BUGS"
        )

    bug = bugs_selecionados[0]
    bug_id = str(bug.get("id", "")).upper()

    identidade_ok, motivo_identidade = validar_identidade_bugs_selecionados(
        veredito_salvo,
        [bug]
    )
    if not identidade_ok:
        return bloquear(motivo_identidade, "BLOQUEADA_IDENTIDADE_BUG")

    codigo_original, erro = ler_alvo_resolvido(alvo)
    if erro:
        return bloquear(erro)

    intervalo, funcao_real, metodo = resolver_intervalo_bug(
        codigo_original,
        bug
    )
    if not intervalo or not funcao_real:
        return bloquear(
            f"Nao foi possivel localizar com seguranca a funcao do {bug_id}.",
            "BLOQUEADA_FUNCAO_NAO_LOCALIZADA"
        )

    relatorio["bugs_autorizados"] = 1
    relatorio["ids_autorizados"] = [bug_id]
    relatorio["funcao_autorizada"] = funcao_real
    relatorio["intervalo_autorizado"] = list(intervalo)
    relatorio["sha256_antes"] = hash_texto(codigo_original)

    funcao_antes = _extrair_funcao_por_intervalo(codigo_original, intervalo)
    contexto = _contexto_funcao(codigo_original, intervalo, margem=45)

    print("IDENTIDADE DO BUG: APROVADA")
    print(f"BUG AUTORIZADO: {bug_id}")
    print(f"FUNCAO AUTORIZADA: {funcao_real}")
    print(f"INTERVALO AUTORIZADO: linhas {intervalo[0]}-{intervalo[1]} ({metodo})")
    print("REGRA: nenhuma linha fora desta funcao podera ser modificada.")
    print()

    print("[0A] Revalidacao forense do bug antes de qualquer alteracao.")
    status_bug, revisores_bug = _revalidar_bug_antes_de_corrigir(
        bug,
        funcao_real,
        funcao_antes,
        contexto
    )
    relatorio["revalidacao_bug"] = {
        "status": status_bug,
        "revisores": revisores_bug
    }

    for i, rv in enumerate(revisores_bug, start=1):
        print(
            f"Revisor de evidencia {i}: "
            f"{rv.get('status')} - {rv.get('evidencia')}"
        )

    if status_bug == "NAO_DEMONSTRADO":
        relatorio["status"] = "BUG_NAO_DEMONSTRADO"
        relatorio["observacao"] = (
            f"O bug {bug_id} foi revogado pela revalidacao forense: "
            "dois revisores independentes nao encontraram evidencia suficiente no codigo atual."
        )
        relatorio["rollback_executado"] = False
        relatorio["original_mt5_alterado"] = False
        salvar_relatorio_autocorrecao(relatorio)
        print()
        print("=" * 72)
        print("BUG NAO DEMONSTRADO - NENHUMA CORRECAO SERA APLICADA")
        print("=" * 72)
        print("O veredito anterior foi tratado como falso positivo para esta execucao.")
        print("Nenhum arquivo foi alterado.")
        print()
        return relatorio

    if status_bug != "CONFIRMADO":
        relatorio["status"] = "BUG_INCONCLUSIVO"
        relatorio["observacao"] = (
            f"Nao houve unanimidade suficiente para confirmar o bug {bug_id}. "
            "Autocorrecao bloqueada por seguranca."
        )
        salvar_relatorio_autocorrecao(relatorio)
        print()
        print("BUG INCONCLUSIVO: autocorrecao bloqueada sem alterar arquivo.")
        print()
        return relatorio

    print()
    print("[0B] Gerando contrato minimo de correcao.")
    contrato, erro_contrato = _gerar_contrato_correcao(
        bug,
        funcao_real,
        funcao_antes,
        contexto,
        revisores_bug
    )
    if erro_contrato or not contrato:
        return bloquear(
            "Nao foi possivel congelar um contrato seguro de correcao: "
            + str(erro_contrato),
            "BLOQUEADA_CONTRATO"
        )

    relatorio["contrato_correcao"] = contrato
    print("Contrato congelado.")
    print("Objetivo: " + str(contrato.get("objetivo", "")))
    print()

    print("[1] Compilacao de referencia.")
    resultado_base = compilar_mql5(nome)
    mostrar_compilacao(resultado_base)

    if not resultado_base.get("ok"):
        relatorio["compilacao"] = {
            "errors": resultado_base.get("errors"),
            "warnings": resultado_base.get("warnings")
        }
        return bloquear(
            "A copia de teste nao esta em 0 errors / 0 warnings antes da correcao.",
            "BLOQUEADA_COMPILACAO_BASE"
        )

    backup, erro_backup = criar_backup(nome)
    if erro_backup:
        return bloquear(
            f"Falha ao criar backup: {erro_backup}",
            "BLOQUEADA_BACKUP"
        )

    relatorio["backup"] = backup
    print()
    print(f"[2] Backup mestre criado: {backup}")

    schema_patch = {
        "type": "object",
        "properties": {
            "bug_id": {"type": "string"},
            "funcao": {"type": "string"},
            "replacement_function": {"type": "string"},
            "resumo": {"type": "string"}
        },
        "required": ["bug_id", "funcao", "replacement_function", "resumo"],
        "additionalProperties": False
    }

    historico_rejeicoes = []
    hashes_rejeitados = set()
    max_tentativas = 3

    for tentativa in range(1, max_tentativas + 1):
        print()
        print("-" * 72)
        print(f"TENTATIVA CIRURGICA {tentativa}/{max_tentativas}")
        print("-" * 72)

        rejeicoes_txt = (
            "\n".join(f"- {x}" for x in historico_rejeicoes[-6:])
            if historico_rejeicoes
            else "Nenhuma."
        )

        bug_json = json.dumps(bug, ensure_ascii=False, indent=2)

        prompt_sistema = """
Voce e um engenheiro senior de MQL5 trabalhando em modo PATCH CIRURGICO.

REGRAS ABSOLUTAS:
- Corrija SOMENTE o bug autorizado.
- Altere SOMENTE a funcao autorizada.
- Nao retorne o arquivo completo.
- Nao crie funcoes auxiliares fora da funcao autorizada.
- Nao mude assinaturas, inputs, parametros globais, estrategia ou defaults.
- Preserve a finalidade e o comportamento nao relacionado ao bug.
- Retorne JSON conforme o schema.
- replacement_function deve conter a funcao MQL5 COMPLETA, e somente ela.
- Faca a menor correcao necessaria.
"""

        prompt_usuario = f"""
BUG AUTORIZADO:
{bug_json}

CONTRATO DE CORRECAO CONGELADO:
{json.dumps(contrato, ensure_ascii=False, indent=2)}

FUNCAO REAL AUTORIZADA:
{funcao_real}

FUNCAO ORIGINAL:
--- INICIO FUNCAO ---
{funcao_antes}
--- FIM FUNCAO ---

CONTEXTO SOMENTE PARA LEITURA (NAO PODE SER ALTERADO):
--- INICIO CONTEXTO ---
{contexto}
--- FIM CONTEXTO ---

REJEICOES DE TENTATIVAS ANTERIORES:
{rejeicoes_txt}

IMPORTANTE:
- Se uma tentativa anterior foi reprovada, produza uma solucao MATERIALMENTE diferente que responda
  apenas aos motivos tecnicos validos da reprovacao.
- Nao tente garantir "validade futura" do preco; valide somente o estado atual observavel.
- Nao devolva exatamente a mesma funcao de uma tentativa rejeitada.
- Nao altere nada fora da funcao autorizada.
- Obedeca literalmente ao CONTRATO DE CORRECAO CONGELADO.
- Nao adicione validacao de Bid/Ask, filtros de mercado ou novas regras se o contrato nao exigir.
- Nao use identificadores MQL4 legados como Bid/Ask nus.

Gere replacement_function corrigindo apenas o bug {bug_id}.
"""

        print(
            f"Gerando somente a funcao {funcao_real} "
            f"(timeout {TIMEOUT_MODELO_SEGUNDOS}s)..."
        )

        obj = None
        erro_modelo = None
        if CORE_SETTINGS is not None and getattr(CORE_SETTINGS, "opencode_enabled", True):
            obj, erro_modelo = _gerar_patch_cirurgico_opencode(
                bug,
                contrato,
                funcao_real,
                funcao_antes,
                contexto,
                rejeicoes_txt,
                bug_id,
                caminho
            )
        if erro_modelo or not isinstance(obj, dict):
            obj, erro_modelo = _chat_json_estruturado_timeout(
                [
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario}
                ],
                schema_patch,
                timeout_segundos=TIMEOUT_MODELO_SEGUNDOS,
                options={
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "top_k": 1,
                    "seed": 19700 + (tentativa * 101)
                }
            )

        if erro_modelo or not isinstance(obj, dict):
            motivo = erro_modelo or "Resposta estruturada invalida."
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "ERRO_MODELO_OU_JSON",
                "motivo": motivo
            })
            historico_rejeicoes.append(motivo)
            print("Tentativa rejeitada: " + motivo)
            continue

        if str(obj.get("bug_id", "")).upper() != bug_id:
            motivo = f"ID retornado nao confere: {obj.get('bug_id')}"
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "IDENTIDADE_REJEITADA",
                "motivo": motivo
            })
            historico_rejeicoes.append(motivo)
            print("Tentativa rejeitada: " + motivo)
            continue

        if str(obj.get("funcao", "")).strip().lower() != funcao_real.lower():
            motivo = f"Funcao retornada nao confere: {obj.get('funcao')}"
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "IDENTIDADE_REJEITADA",
                "motivo": motivo
            })
            historico_rejeicoes.append(motivo)
            print("Tentativa rejeitada: " + motivo)
            continue

        nova_funcao, erro_funcao = _normalizar_substituicao_funcao(
            obj.get("replacement_function", ""),
            funcao_real
        )
        if erro_funcao:
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "FUNCAO_REJEITADA",
                "motivo": erro_funcao
            })
            historico_rejeicoes.append(erro_funcao)
            print("Tentativa rejeitada: " + erro_funcao)
            continue

        preflight_ok, preflight_problemas = _preflight_mql5_funcao(nova_funcao)
        if not preflight_ok:
            motivo = "PREFLIGHT_MQL5: " + " | ".join(preflight_problemas)
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "PREFLIGHT_REJEITADO",
                "motivo": motivo
            })
            historico_rejeicoes.append(motivo)
            print("Tentativa rejeitada antes do MetaEditor: " + motivo)
            continue

        candidato, prefixo, sufixo, trecho_original, trecho_novo = _montar_patch_cirurgico(
            codigo_original,
            intervalo,
            nova_funcao
        )

        hash_candidato = hash_texto(candidato)
        if hash_candidato in hashes_rejeitados:
            motivo = "CANDIDATO_REPETIDO"
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": motivo,
                "sha256": hash_candidato
            })
            historico_rejeicoes.append(motivo)
            print("Tentativa rejeitada: candidato repetido.")
            continue

        escopo_ok, motivo_escopo, detalhes_escopo = _validar_invariantes_patch_cirurgico(
            codigo_original,
            candidato,
            intervalo,
            funcao_real
        )

        if not escopo_ok:
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "ESCOPO_REJEITADO",
                "sha256": hash_candidato,
                "motivo": motivo_escopo,
                "invariantes": detalhes_escopo
            })
            hashes_rejeitados.add(hash_candidato)
            historico_rejeicoes.append(motivo_escopo)
            print("Tentativa rejeitada antes de gravar: " + motivo_escopo)
            continue

        print("[3] Escopo cirurgico aprovado: prefixo e sufixo intactos.")

        try:
            with open(caminho, "w", encoding="utf-8", newline="") as f:
                f.write(candidato)
        except Exception as e:
            motivo = f"Falha ao gravar candidato: {e}"
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "FALHA_ESCRITA",
                "motivo": motivo
            })
            historico_rejeicoes.append(motivo)
            print(motivo)
            continue

        print("[4] Patch gravado somente na copia PROJETO_TESTE.")
        resultado = compilar_mql5(nome)

        print()
        print("[5] Compilacao real no MetaEditor.")
        mostrar_compilacao(resultado)

        if not resultado.get("ok"):
            motivo = (
                f"Compilacao rejeitada: errors={resultado.get('errors')} "
                f"warnings={resultado.get('warnings')}"
            )
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "COMPILACAO_REJEITADA",
                "sha256": hash_candidato,
                "motivo": motivo,
                "errors": resultado.get("errors"),
                "warnings": resultado.get("warnings")
            })

            restaurar_backup(nome, backup)
            relatorio["rollback_executado"] = True
            hashes_rejeitados.add(hash_candidato)
            historico_rejeicoes.append(motivo)
            print("Rollback executado. Nova tentativa usara o original.")
            continue

        funcao_depois_intervalo = localizar_intervalo_funcao(candidato, funcao_real)
        funcao_depois = _extrair_funcao_por_intervalo(
            candidato,
            funcao_depois_intervalo
        )

        print()
        print("[6] Dois revisores independentes da funcao corrigida.")
        pos_ok, revisores = _validar_patch_contra_contrato(
            bug,
            contrato,
            funcao_antes,
            funcao_depois,
            resultado
        )

        for i, r in enumerate(revisores, start=1):
            print(
                f"Revisor {i}: {r.get('status')} - {r.get('motivo')}"
            )

        if not pos_ok:
            motivo = "VALIDACAO_POS_REPROVADA"
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": motivo,
                "sha256": hash_candidato,
                "revisores": revisores
            })
            restaurar_backup(nome, backup)
            relatorio["rollback_executado"] = True
            hashes_rejeitados.add(hash_candidato)
            historico_rejeicoes.append(
                motivo + ": " + " | ".join(str(r.get("motivo", "")) for r in revisores)
            )
            print("Rollback executado por reprovacao dos revisores.")
            continue

        # Auditoria final de imutabilidade fora da funcao.
        escopo_final_ok, escopo_final_motivo, detalhes_final = _validar_invariantes_patch_cirurgico(
            codigo_original,
            candidato,
            intervalo,
            funcao_real
        )
        if not escopo_final_ok:
            relatorio["tentativas"].append({
                "tentativa": tentativa,
                "status": "IMUTABILIDADE_FINAL_REJEITADA",
                "motivo": escopo_final_motivo,
                "invariantes": detalhes_final
            })
            restaurar_backup(nome, backup)
            relatorio["rollback_executado"] = True
            hashes_rejeitados.add(hash_candidato)
            historico_rejeicoes.append(escopo_final_motivo)
            print("Rollback executado: imutabilidade final falhou.")
            continue

        diff = list(difflib.unified_diff(
            codigo_original.splitlines(),
            candidato.splitlines(),
            fromfile="ANTES",
            tofile="DEPOIS",
            lineterm=""
        ))
        linhas_alteradas = [
            x for x in diff
            if (x.startswith("+") or x.startswith("-"))
            and not x.startswith("+++")
            and not x.startswith("---")
        ]

        relatorio["tentativas"].append({
            "tentativa": tentativa,
            "status": "ACEITA",
            "sha256": hash_candidato,
            "resumo_modelo": obj.get("resumo", ""),
            "revisores": revisores
        })
        relatorio["status"] = "SUCESSO"
        relatorio["sha256_depois"] = hash_candidato
        relatorio["compilacao"] = {
            "errors": resultado.get("errors"),
            "warnings": resultado.get("warnings")
        }
        relatorio["invariantes_escopo"] = detalhes_final
        relatorio["alteracoes"] = linhas_alteradas
        relatorio["rollback_executado"] = False
        relatorio["original_mt5_alterado"] = False
        relatorio["observacao"] = (
            f"{bug_id} corrigido por substituicao cirurgica exclusiva da funcao {funcao_real}; "
            "prefixo e sufixo permaneceram identicos."
        )

        salvar_relatorio_autocorrecao(relatorio)

        print()
        print("=" * 72)
        print("SUCESSO: CORRECAO CIRURGICA VALIDADA")
        print("=" * 72)
        print(f"Bug corrigido: {bug_id}")
        print(f"Funcao alterada: {funcao_real}")
        print("MetaEditor: 0 errors / 0 warnings")
        print("Imutabilidade fora da funcao: APROVADA")
        print("Dois revisores: APROVADOS")
        print(f"Backup mestre: {backup}")
        print(f"Arquivo de teste: {caminho}")
        print("MT5 real: NAO ALTERADO")
        relatorio_path = globals().get(
            "ARQUIVO_RELATORIO_AUTOCORRECAO",
            os.path.join(PASTA_APP, "ultima_autocorrecao.json")
        )
        print(
            "RELATORIO: "
            + relatorio_path
        )
        print()
        return relatorio

    print()
    print("Nenhum patch cirurgico foi aceito nas 3 tentativas.")
    print("Restaurando backup mestre.")

    ok_rb, msg_rb = restaurar_backup(nome, backup)
    print(msg_rb)

    relatorio["status"] = "ROLLBACK_FINAL"
    relatorio["sha256_depois"] = relatorio["sha256_antes"]
    relatorio["compilacao"] = {
        "errors": resultado_base.get("errors"),
        "warnings": resultado_base.get("warnings")
    }
    relatorio["rollback_executado"] = True
    relatorio["original_mt5_alterado"] = False
    relatorio["observacao"] = (
        "Nenhum patch cirurgico foi aceito; backup mestre restaurado."
    )
    salvar_relatorio_autocorrecao(relatorio)

    print()
    print(
        "RELATORIO ESTRUTURADO SALVO EM: "
        + globals().get(
            "ARQUIVO_RELATORIO_AUTOCORRECAO",
            os.path.join(PASTA_APP, "ultima_autocorrecao.json")
        )
    )
    print("VEREDITO MANTIDO: arquivo restaurado ao estado anterior.")
    print()
    return relatorio

# ============================================================
# RELATORIO ESTRUTURADO - DEFINICAO ANTECIPADA V1.9.8.0
# ============================================================
ARQUIVO_RELATORIO_AUTOCORRECAO = os.path.join(
    PASTA_APP,
    "ultima_autocorrecao.json"
)


def salvar_relatorio_autocorrecao(relatorio):
    if not isinstance(relatorio, dict):
        return False

    caminho_relatorio = globals().get(
        "ARQUIVO_RELATORIO_AUTOCORRECAO",
        os.path.join(PASTA_APP, "ultima_autocorrecao.json")
    )

    try:
        with open(
            caminho_relatorio,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                relatorio,
                f,
                ensure_ascii=False,
                indent=2
            )
        return True
    except Exception as erro:
        print(
            f"[AVISO] Nao foi possivel salvar o relatorio "
            f"da autocorrecao: {erro}"
        )
        return False


def carregar_relatorio_autocorrecao():
    caminho_relatorio = globals().get(
        "ARQUIVO_RELATORIO_AUTOCORRECAO",
        os.path.join(PASTA_APP, "ultima_autocorrecao.json")
    )

    if not os.path.isfile(caminho_relatorio):
        return None

    try:
        with open(
            caminho_relatorio,
            "r",
            encoding="utf-8"
        ) as f:
            dados = json.load(f)

        if not isinstance(dados, dict):
            return None

        return dados
    except Exception:
        return None


def imprimir_relatorio_autocorrecao(relatorio):
    print()
    print("=" * 70)
    print("RELATORIO DA ULTIMA AUTOCORRECAO")
    print("=" * 70)

    if not relatorio:
        print("Nenhuma autocorrecao registrada.")
        print("=" * 70)
        print()
        return

    print(f"Data/hora: {relatorio.get('data_hora', 'nao informado')}")
    print(f"Status: {relatorio.get('status', 'nao informado')}")
    print(f"Arquivo: {relatorio.get('arquivo', 'nao informado')}")
    print(f"Caminho: {relatorio.get('caminho', 'nao informado')}")
    print(f"Backup: {relatorio.get('backup', 'nao informado')}")
    print(f"Funcao/bugs autorizados: {relatorio.get('bugs_autorizados', 'nao informado')}")
    print(f"SHA256 antes: {relatorio.get('sha256_antes', 'nao informado')}")
    print(f"SHA256 depois: {relatorio.get('sha256_depois', 'nao informado')}")
    print(f"Rollback executado: {relatorio.get('rollback_executado', False)}")
    print(f"Original MT5 alterado: {relatorio.get('original_mt5_alterado', False)}")

    comp = relatorio.get("compilacao", {}) or {}
    print(
        "Compilacao: "
        f"errors={comp.get('errors', 'n/a')} "
        f"warnings={comp.get('warnings', 'n/a')}"
    )

    tentativas = relatorio.get("tentativas", []) or []

    print()
    print("TENTATIVAS DE AUTOCORRECAO:")
    if not tentativas:
        print("- Nenhuma tentativa detalhada registrada.")
    else:
        for item in tentativas:
            texto = (
                f"- Tentativa {item.get('tentativa')}: "
                f"{item.get('status')}"
            )
            if "errors" in item or "warnings" in item:
                texto += (
                    f" | errors={item.get('errors')} "
                    f"warnings={item.get('warnings')}"
                )
            print(texto)

    alteracoes = relatorio.get("alteracoes", []) or []

    print()
    print("ALTERACOES REGISTRADAS:")
    if not alteracoes:
        print("- Nenhuma alteracao registrada.")
    else:
        for linha in alteracoes[:120]:
            print(linha)

        if len(alteracoes) > 120:
            print(
                f"... {len(alteracoes) - 120} linha(s) adicionais omitidas."
            )

    print("=" * 70)
    print()


# ============================================================
# PARSER ROBUSTO DO VEREDITO - V1.9.5.2
# ============================================================

def interpretar_veredito_final(texto_veredito):
    """
    Extrai autorizacao e quantidade mesmo quando o modelo usa Markdown,
    por exemplo:
    **AUTOCORRECAO AUTORIZADA:** SIM
    **QUANTIDADE DE BUGS CONFIRMADOS:** 2
    """
    if not isinstance(texto_veredito, str):
        return False, 0

    # Remove marcadores Markdown que atrapalhavam o parser anterior.
    limpo = texto_veredito.replace("*", "")
    limpo = limpo.replace("`", "")

    m_aut = re.search(
        r"AUTOCORRECAO\s+AUTORIZADA\s*:\s*(SIM|NAO|NÃO)",
        limpo,
        flags=re.IGNORECASE
    )

    m_qtd = re.search(
        r"QUANTIDADE\s+DE\s+BUGS\s+CONFIRMADOS\s*:\s*(\d+)",
        limpo,
        flags=re.IGNORECASE
    )

    quantidade = int(m_qtd.group(1)) if m_qtd else 0

    autorizado_texto = (
        bool(m_aut)
        and m_aut.group(1).upper() == "SIM"
    )

    autorizado = autorizado_texto and quantidade > 0

    return autorizado, quantidade


def resumo_veredito_persistente(veredito):
    if not veredito:
        return "Nenhum veredito de auditoria salvo."

    texto = veredito.get("veredito", "")
    autorizado, quantidade = interpretar_veredito_final(texto)

    status = "SIM" if autorizado else "NAO"

    return (
        f"Autocorrecao autorizada: {status}\n"
        f"Quantidade de bugs confirmados: {quantidade}"
    )


# ============================================================
# ESTADO PERSISTENTE DO ALVO E VEREDITO - V1.9.5.3
# ============================================================

ARQUIVO_ESTADO_SESSAO = os.path.join(
    PASTA_APP,
    "estado_alvo_auditoria.json"
)


def salvar_estado_alvo_auditoria(alvo, veredito):
    dados = {
        "arquivo_alvo": alvo,
        "ultimo_veredito": veredito
    }

    try:
        with open(
            ARQUIVO_ESTADO_SESSAO,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                dados,
                f,
                ensure_ascii=False,
                indent=2
            )
        return True
    except Exception as erro:
        print(
            f"[AVISO] Nao foi possivel salvar o estado "
            f"do arquivo alvo: {erro}"
        )
        return False


def carregar_estado_alvo_auditoria():
    if not os.path.isfile(ARQUIVO_ESTADO_SESSAO):
        return None, None

    try:
        with open(
            ARQUIVO_ESTADO_SESSAO,
            "r",
            encoding="utf-8"
        ) as f:
            dados = json.load(f)

        alvo = dados.get("arquivo_alvo")
        veredito = dados.get("ultimo_veredito")

        # Revalida o arquivo fisicamente antes de confiar no estado.
        if (
            alvo
            and alvo.get("caminho")
            and os.path.isfile(alvo.get("caminho"))
        ):
            alvo["ok"] = True
        else:
            alvo = None
            veredito = None

        # Um veredito so e valido se pertencer exatamente ao alvo carregado.
        if alvo and veredito:
            if os.path.abspath(
                veredito.get("arquivo", "")
            ) != os.path.abspath(
                alvo.get("caminho", "")
            ):
                veredito = None
            else:
                # Recalcula autorizacao e quantidade a partir do texto bruto.
                # Isso corrige estados gravados por versoes anteriores cujo
                # parser falhou por causa de Markdown.
                autorizado, quantidade = interpretar_veredito_final(
                    veredito.get("veredito", "")
                )
                veredito["autorizado"] = autorizado
                veredito["quantidade"] = quantidade

        return alvo, veredito

    except Exception as erro:
        print(
            f"[AVISO] Estado anterior ignorado: {erro}"
        )
        return None, None


def invalidar_veredito_persistente(alvo):
    salvar_estado_alvo_auditoria(
        alvo,
        None
    )


# ============================================================
# AGENTE NORMAL
# ============================================================

registrar_ferramentas_core()

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "copiar_ea_mt5_para_teste",
            "description": (
                "Copia com seguranca um arquivo .mq5/.mqh do MT5 real para "
                "C:\\GoldenAI\\projetos, sem alterar o original."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string",
                        "description": "Nome do arquivo real .mq5/.mqh a copiar."
                    }
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_eas_mt5",
            "description": (
                "Lista arquivos .mq5 e .mqh da pasta REAL de Experts "
                "do MetaTrader 5 ativo. Esta ferramenta e somente leitura."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo_mt5",
            "description": (
                "Le um arquivo .mq5 ou .mqh da pasta REAL de Experts "
                "do MetaTrader 5 ativo. Esta ferramenta e somente leitura."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string",
                        "description": (
                            "Caminho relativo dentro de MQL5\\Experts."
                        )
                    }
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_projetos",
            "description": "Lista arquivos dos projetos.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": "Le um arquivo da pasta de projetos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string"
                    }
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compilar_mql5",
            "description": (
                "Compila um arquivo MQL5 no MetaEditor real."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string"
                    }
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "executar_opencode",
            "description": (
                "Delega uma tarefa de programacao ao agente OpenCode. "
                "O OpenCode le, ajusta e corrige arquivos de codigo ate "
                "ficar 100%. Tenta os modelos Free configurados; se todos "
                "falharem, cai automaticamente para o modelo local Qwen. "
                "Use quando o usuario pedir para ler/ajustar/corrigir codigo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tarefa": {
                        "type": "string",
                        "description": (
                            "Descricao objetiva do trabalho de programacao "
                            "a ser executado pelo OpenCode."
                        )
                    },
                    "diretorio": {
                        "type": "string",
                        "description": (
                            "Pasta onde o OpenCode deve trabalhar. "
                            "Vazio usa a pasta padrao de trabalho."
                        )
                    },
                    "modelo": {
                        "type": "string",
                        "description": (
                            "Modelo especifico (formato provider/model). "
                            "Vazio usa a cadeia Free configurada."
                        )
                    }
                },
                "required": ["tarefa"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "arquivo_metadados",
            "description": (
                "Retorna metadados objetivos de um arquivo da pasta de projetos: "
                "linhas, linhas nao vazias, tamanho em bytes, extensao, nome, caminho e data de modificacao. "
                "Use para perguntas como quantidade de linhas, tamanho ou extensao."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string"
                    }
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "market_analyze_dataset",
            "description": "Analisa um CSV local autorizado com Market V1 em modo READ/ANALYSIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"}
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_analysis",
            "description": "Consulta uma analise Market persistida, ou a ultima quando analysis_id estiver vazio.",
            "parameters": {
                "type": "object",
                "properties": {"analysis_id": {"type": "string"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_regime",
            "description": "Consulta o regime de uma analise Market persistida.",
            "parameters": {
                "type": "object",
                "properties": {"analysis_id": {"type": "string"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "quant_run_backtest",
            "description": "Executa backtest Quant V1 somente quando o usuario pedir explicitamente teste/backtest e houver CSV local autorizado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "strategy_spec": {"type": "object"},
                    "initial_capital": {"type": "number"},
                    "quantity": {"type": "number"},
                    "spread": {"type": "number"},
                    "commission": {"type": "number"},
                    "slippage": {"type": "number"}
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Consulta a data, hora, dia da semana e timezone locais reais.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Consulta informacoes seguras do Windows, CPU e RAM, sem expor segredos.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_usage",
            "description": "Consulta uso de disco apenas em caminhos permitidos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Caminho permitido. Padrao: C:\\GoldenAI."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "Lista processos por nome sem ler linha de comando nem argumentos sensiveis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_name": {
                        "type": "string"
                    },
                    "limit": {
                        "type": "integer"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_installed_app",
            "description": "Procura aplicativos conhecidos em locais seguros, sem executar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome conhecido, como notepad, explorer, MetaTrader 5 ou MetaEditor."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "launch_allowed_app",
            "description": "Abre somente aplicativos explicitamente permitidos pela allowlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Abre somente pastas permitidas da GoldenAI ou MetaQuotes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mt5_status",
            "description": "Verifica se MetaTrader 5 ou MetaEditor estao abertos e lista instalacoes conhecidas.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_mt5_terminals",
            "description": "Lista terminais MT5 em AppData\\Roaming\\MetaQuotes\\Terminal, somente leitura.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_mt5_eas",
            "description": "Lista arquivos .mq5/.mqh do MT5 em modo somente leitura.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_mt5_file",
            "description": "Le somente arquivos .mq5/.mqh em caminho MT5 permitido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    },
                    "max_bytes": {
                        "type": "integer"
                    }
                },
                "required": ["path"]
            }
        }
    }
]


historico = [
    {
        "role": "system",
        "content": """
Voce e a GoldenAI.

Voce conversa de forma natural sobre assuntos gerais quando o usuario fizer uma pergunta geral.
O contexto de trading, MetaTrader, MQL5, robos e projetos fica disponivel somente quando a intencao do usuario for claramente tecnica ou relacionada a projeto/arquivo/codigo.
Nao puxe automaticamente o arquivo atual para conversas gerais, mudancas de assunto, calculos comuns, mensagens, ideias de negocio, carros ou explicacoes gerais.
Responda por padrao no mesmo idioma predominante da mensagem do usuario, salvo se o usuario pedir explicitamente outro idioma.
Preserve nomes tecnicos, funcoes, APIs e codigo no idioma original quando necessario.
O contexto selecionado define QUAL arquivo esta em foco; a pergunta original do usuario define O QUE fazer com esse arquivo.

Voce possui ferramentas reais para tarefas tecnicas quando elas forem explicitamente relevantes:
- listar projetos de teste da GoldenAI;
- ler projetos de teste;
- obter metadados objetivos de arquivo selecionado ou projeto de teste;
- compilar MQL5;
- listar os EAs reais do MetaTrader 5;
- ler arquivos .mq5 e .mqh do MT5 real;
- consultar data/hora locais reais;
- consultar informacoes seguras do Windows, RAM, disco, processos e status do MT5;
- executar_opencode: delega trabalho de programacao ao agente OpenCode (ler, ajustar e corrigir arquivos de codigo ate ficar 100%). Use SEMPRE quando o usuario pedir para ler/ajustar/corrigir um codigo fonte, mesmo que a resposta dependa de tool calls internas do agente.

IMPORTANTE:
A pasta REAL do MetaTrader 5 esta em modo SOMENTE LEITURA.
Nao tente modificar, apagar, mover ou sobrescrever arquivos do MT5 real.
Para alteracoes, use apenas a pasta de testes C:\\GoldenAI\\projetos.
Nao use ferramentas locais para conversa geral, calculos comuns ou mudancas de assunto.

REGRA DE IDENTIDADE DO ARQUIVO:
- Nunca troque silenciosamente o arquivo solicitado por outro.
- Se o usuario fornecer caminho completo, use EXATAMENTE esse caminho.
- Se o arquivo nao existir, diga que nao existe.
- Nunca substitua por robo_teste.mq5, TradingRobot_v1.mq5 ou qualquer outro exemplo.
- Antes de qualquer operacao de escrita, o ARQUIVO ALVO deve estar confirmado.

Nunca invente que executou uma ferramenta.
Nunca invente resultado de compilacao.
"""
    }
]


def executar_agente_normal(pergunta, permitir_ferramentas=True):
    """
    Fluxo controlado para tarefas normais:
    1. O modelo escolhe no maximo uma ferramenta.
    2. A ferramenta e executada uma unica vez.
    3. O resultado e entregue ao modelo sem ferramentas habilitadas.
    4. O modelo responde em linguagem normal e a tarefa termina.
    
    V1.9.8.4 - Permite perguntas gerais sobre MT5 sem selecionar arquivo.
    """

    if responder_metadados_arquivo(pergunta):
        return

    if responder_programador_opencode(pergunta):
        return

    historico.append({
        "role": "user",
        "content": pergunta
    })

    # Detecta se a pergunta e sobre MT5/computador sem depender de arquivo especifico
    pergunta_lower = pergunta.lower()
    e_pergunta_mt5_geral = (
        ("metatrader" in pergunta_lower or "meta trader" in pergunta_lower or "mt5" in pergunta_lower)
        and not cita_arquivo_mql
        and not any(t in pergunta_lower for t in ["mq5", ".mq5", ".mqh", "robô", "robo", "robôs", "robos"])
    )
    e_pergunta_computador = (
        any(t in pergunta_lower for t in ["computador", "pc", "sistema", "windows", "processos", "memoria", "disco", "cpu", "ram"])
        and not cita_arquivo_mql
    )

    if permitir_ferramentas:
        resposta = _chamar_modelo(
            historico,
            tools=FERRAMENTAS
        )
    else:
        resposta = _chamar_modelo(
            historico
        )

    mensagem = resposta.message
    texto = mensagem.content or ""

    chamadas = []

    # --------------------------------------------------------
    # TOOL CALL ESTRUTURADO
    # --------------------------------------------------------

    tool_calls = getattr(
        mensagem,
        "tool_calls",
        None
    )

    if tool_calls:
        for chamada in tool_calls:
            argumentos = chamada.function.arguments

            if isinstance(argumentos, str):
                try:
                    argumentos = json.loads(argumentos)
                except Exception:
                    argumentos = {}

            chamadas.append({
                "name": chamada.function.name,
                "arguments": argumentos
            })

    # --------------------------------------------------------
    # FALLBACK: JSON TEXTUAL
    # --------------------------------------------------------

    if not chamadas and texto.strip():
        texto_limpo = texto.strip()

        if texto_limpo.startswith("```"):
            texto_limpo = re.sub(
                r"^```(?:json)?\s*",
                "",
                texto_limpo,
                flags=re.IGNORECASE
            )
            texto_limpo = re.sub(
                r"\s*```$",
                "",
                texto_limpo
            ).strip()

        try:
            dados = json.loads(texto_limpo)

            if isinstance(dados, dict):
                nome = dados.get("name")
                argumentos = dados.get("arguments", {})

                if nome:
                    if not isinstance(argumentos, dict):
                        argumentos = {}

                    chamadas.append({
                        "name": nome,
                        "arguments": argumentos
                    })

        except Exception:
            pass

    # --------------------------------------------------------
    # SEM FERRAMENTA: RESPOSTA NORMAL
    # --------------------------------------------------------

    if not chamadas:
        historico.append({
            "role": "assistant",
            "content": texto
        })

        print()
        print("Golden AI:")
        print(texto)
        print()
        return

    # --------------------------------------------------------
    # EXECUTA SOMENTE A PRIMEIRA FERRAMENTA
    # --------------------------------------------------------

    chamada = chamadas[0]
    nome = chamada["name"]
    argumentos = chamada["arguments"]

    pergunta_lower = pergunta.lower()

    # Corrige automaticamente a rota quando o usuario fala do MT5 real.
    if nome == "listar_projetos" and (
        "metatrader" in pergunta_lower
        or "meta trader" in pergunta_lower
        or "mt5" in pergunta_lower
    ):
        nome = "listar_eas_mt5"
        argumentos = {}

    print()
    print(
        f"[GoldenAI usando ferramenta: {nome}]"
    )

    try:
        resultado = executar_tool_core(nome, argumentos)
    except Exception as erro_tool:
        resultado = f"Ferramenta desconhecida: {nome}. Erro: {erro_tool}"

    if nome == "compilar_mql5" and isinstance(resultado, dict):
        resultado = (
            f"Erros: {resultado.get('errors')}\n"
            f"Warnings: {resultado.get('warnings')}\n\n"
            f"{resultado.get('log')}"
        )

    # Mostra um preview controlado para nao poluir a tela.
    if nome == "listar_eas_mt5":
        linhas = str(resultado).splitlines()

        print(
            f"Arquivos encontrados no MT5 real: {len(linhas)}"
        )

        # Mostra somente a pasta Meus Robos, se existir.
        meus_robos = [
            linha for linha in linhas
            if linha.lower().startswith("meus robos\\")
        ]

        if meus_robos:
            print()
            print("Meus Robos:")
            for linha in meus_robos:
                print(linha)
        else:
            print()
            print(
                "Nenhum arquivo em 'Meus Robos' foi identificado."
            )

        resultado_para_modelo = (
            f"TOTAL DE ARQUIVOS .mq5/.mqh NO MT5 REAL: {len(linhas)}\n\n"
            f"LISTA COMPLETA:\n{resultado}"
        )

    else:
        if isinstance(resultado, tuple) and len(resultado) == 2:
            conteudo, erro_resultado = resultado
            if conteudo is not None:
                print(conteudo if isinstance(conteudo, str) else str(conteudo))
                resultado_para_modelo = str(conteudo)
            else:
                print(erro_resultado)
                resultado_para_modelo = str(erro_resultado)
        else:
            print(resultado)
            resultado_para_modelo = str(resultado)

    # --------------------------------------------------------
    # RESPOSTA FINAL SEM TOOLS
    # --------------------------------------------------------

    historico.append({
        "role": "assistant",
        "content": texto
    })

    historico.append({
        "role": "tool",
        "tool_name": nome,
        "content": resultado_para_modelo
    })

    idioma_resposta = detectar_idioma_resposta(pergunta)
    instrucao_idioma = (
        "Answer in the predominant language of the user's request, unless the user explicitly requested another language."
        if idioma_resposta == "en"
        else "Responda no idioma predominante do pedido do usuario, salvo se ele pediu explicitamente outro idioma."
    )

    prompt_final = f"""
{instrucao_idioma}
Use SOMENTE o resultado real da ferramenta.

Pedido do usuario:
{pergunta}

Ferramenta executada:
{nome}

Resultado real:
{resultado_para_modelo}

REGRAS:
- Nao chame nenhuma ferramenta.
- Nao retorne JSON.
- Nao invente arquivos.
- Seja objetivo.
- Se a ferramenta foi listar_eas_mt5, destaque primeiro os arquivos da pasta
  'Meus Robos' e diga o total encontrado.
- Nao despeje a lista inteira se houver muitos arquivos; resuma e ofereca
  detalhes somente se necessario.
"""

    resposta_final = _chamar_modelo(
        [
            {
                "role": "system",
                "content": (
                    "Voce e a GoldenAI. Responda somente em linguagem normal. "
                    "Use apenas os dados fornecidos no resultado da ferramenta. "
                    "Preserve nomes tecnicos, funcoes, APIs e codigo no idioma original."
                )
            },
            {
                "role": "user",
                "content": prompt_final
            }
        ]
    )

    texto_final = (
        resposta_final.message.content
        or "Tarefa concluida."
    ).strip()

    historico.append({
        "role": "assistant",
        "content": texto_final
    })

    print()
    print("Golden AI:")
    print(texto_final)
    print()


# ============================================================
# INTERFACE
# ============================================================

print("=" * 76)
print("GOLDEN AI - AGENTE V1.9.8.3")
print("MT5 REAL SOMENTE LEITURA | AUTOCORRECAO TESTE | METAEDITOR | ROLLBACK")
print("=" * 76)
print()
# ============================================================
# INTERNET - Importado de app/modules/internet.py
# ============================================================
# internet_search, internet_fetch, internet_download,
# pergunta_pede_internet, formatar_internet_search_result

# ============================================================
# MODULOS V1.10 - Importado de app/modules/browser.py
# ============================================================
# browser_search, browser_fetch, document_extract, audio_transcribe,
# video_analyze, vision_analyze_image, memory_vector_store,
# memory_vector_search, status_modulos_v110

# ============================================================
# ============================================================
# V1.10 ROUTER - Importado de app/modules/internet.py e utils.py
# ============================================================

def normalizar_texto_v110(texto):
    import unicodedata as _u
    return _u.normalize('NFKD', (texto or '').lower()).encode('ascii', 'ignore').decode('ascii')

def _detectar_extensoes_v110(texto):
    """Retorna lista de (tipo, extensao/url) encontrados na pergunta."""
    texto = (texto or '').lower()
    tipos = []
    padrões = [
        ('.pdf', 'pdf'), ('.docx', 'docx'), ('.doc', 'doc'), ('.pptx', 'pptx'),
        ('.xlsx', 'xlsx'), ('.txt', 'txt'), ('.md', 'md'),
        ('.mp3', 'audio'), ('.wav', 'audio'), ('.m4a', 'audio'), ('.ogg', 'audio'),
        ('.flac', 'audio'), ('.aac', 'audio'), ('.opus', 'audio'),
        ('.mp4', 'video'), ('.mkv', 'video'), ('.avi', 'video'), ('.mov', 'video'),
        ('.webm', 'video'), ('.flv', 'video'), ('.wmv', 'video'), ('.m4v', 'video'), ('.ts', 'video'),
        ('.png', 'imagem'), ('.jpg', 'imagem'), ('.jpeg', 'imagem'), ('.gif', 'imagem'), ('.bmp', 'imagem'), ('.webp', 'imagem'),
    ]
    for ext, tipo in padrões:
        if ext in texto:
            tipos.append((tipo, ext))
    # Formatos mencionados sem ponto (ex: "video mp4", "um pdf")
    palavras = set(re.findall(r'\b\w+\b', texto))
    mapa_sem_ponto = {
        'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx', 'xlsx': 'xlsx',
        'mp3': 'audio', 'wav': 'audio', 'm4a': 'audio', 'ogg': 'audio',
        'mp4': 'video', 'mkv': 'video', 'avi': 'video', 'mov': 'video', 'webm': 'video',
        'png': 'imagem', 'jpg': 'imagem', 'jpeg': 'imagem', 'webp': 'imagem',
    }
    for pal, tipo in mapa_sem_ponto.items():
        if pal in palavras and not any(t == tipo for t, _ in tipos):
            tipos.append((tipo, pal))
    return tipos

def _extrair_caminho_arquivo(pergunta):
    """Tenta extrair um caminho absoluto ou nome de arquivo citado na pergunta."""
    import re
    caminhos = re.findall(r'[A-Za-z]:\\[^\s"\'<>|]+|/[^/\s]+\.[A-Za-z0-9]{1,5}', pergunta)
    if caminhos:
        return caminhos[0]
    nome = re.search(r'\b[\w\-\u00C0-\uFFFF]+\.[A-Za-z0-9]{1,5}\b', pergunta)
    if nome:
        candidato = nome.group(0)
        if not candidato.lower().endswith(('.mq5', '.mqh', '.py', '.json', '.yaml', '.yml', '.ini')):
            return candidato
    return None

def _resolver_arquivo_v110(arquivo):
    """Resolve arquivo: se so nome, procura em C:\\GoldenAI\\sandbox e C:\\GoldenAI\\projetos."""
    import os
    if not arquivo:
        return None
    caminho = os.path.abspath(arquivo)
    if os.path.isfile(caminho):
        return caminho
    for base in (r'C:\GoldenAI\sandbox', r'C:\GoldenAI\projetos', r'C:\GoldenAI\media', r'C:\GoldenAI\data'):
        cand = os.path.join(base, arquivo)
        if os.path.isfile(cand):
            return cand
    return None

def classificar_tarefa_v110(pergunta):
    """Classifica a tarefa e devolve a ferramenta + argumento + rota."""
    texto = normalizar_texto_v110(pergunta)
    extensoes = _detectar_extensoes_v110(pergunta)
    arquivo = _extrair_caminho_arquivo(pergunta)
    caminho = _resolver_arquivo_v110(arquivo) if arquivo else None

    # 1) Imagem -> vision
    if any(t == 'imagem' for t, _ in extensoes) or any(palavra in texto for palavra in
            ('veja a imagem', 'olhe a imagem', 'analise a imagem', 'imagem em anexo', 'print da tela', 'captura de tela', 'analise esse print', 'analise essa captura', 'olhe o grafico', 'veja o grafico')):
        alvo = caminho or arquivo or ''
        return dict(rota='vision', ferramenta='vision_analyze_image', alvo=alvo)

    # 2) Video -> ffmpeg + whisper + vision
    if any(t == 'video' for t, _ in extensoes):
        return dict(rota='video', ferramenta='video_analyze', alvo=caminho or arquivo or '')

    # 3) Audio -> whisper
    if any(t == 'audio' for t, _ in extensoes):
        return dict(rota='audio', ferramenta='audio_transcribe', alvo=caminho or arquivo or '')

    # 4) Documento -> docling
    if any(t in ('pdf', 'docx', 'doc', 'pptx', 'xlsx', 'txt', 'md') for t, _ in extensoes):
        return dict(rota='document', ferramenta='document_extract', alvo=caminho or arquivo or '')

    # 5) URL explicita -> browser_fetch (tem prioridade sobre texto de busca)
    if ('http://' in texto or 'https://' in texto or 'www.' in texto):
        import re
        url = re.search(r'(https?://[^\s"\'<>]+|www\.[^\s"\'<>]+)', pergunta)
        if url:
            return dict(rota='browser', ferramenta='browser_fetch', alvo=url.group(0).rstrip('.,;:'))

    # 6) Internet / navegacao
    if any(palavra in texto for palavra in (
            'pesquise na internet', 'pesquise na web', 'pesquise online', 'busque na internet',
            'busque na web', 'buscar na web', 'search the web', 'pesquise esse erro', 'pesquise este erro',
            'abre o site', 'abra o site', 'acesse o site', 'abrir o site', 'entre no site',
            'consulte o site', 'ver o site', 'abre a pagina', 'abra a pagina', 'noticia recente',
            'cotacao atual', 'ultima noticia', 'procure no google', 'procure na internet')):
        return dict(rota='browser', ferramenta='browser_search', alvo=None)

    # 7) Memoria semantica
    if any(palavra in texto for palavra in
            ('memorize', 'grave na memoria', 'lembre disso', 'guarde na memoria', 'indexe na memoria',
             'busque na memoria semantica', 'procure na memoria semantica', 'pesquise na memoria vetorial',
             'similar a', 'mais proximo na memoria', 'lembre do que falamos')):
        if any(palavra in texto for palavra in ('grave', 'memorize', 'indexe', 'guarde', 'lembre disso')):
            return dict(rota='memory', ferramenta='memory_vector_store', alvo=None)
        return dict(rota='memory', ferramenta='memory_vector_search', alvo=None)

    return None

def _texto_memoria_para_store(pergunta):
    """Remove verbos de comando e devolve o conteudo a memorizar."""
    texto = pergunta.strip()
    for prefixo in ('memorize isso: ', 'memorize: ', 'grave na memoria: ', 'lembre disso: ',
                    'guarde na memoria: ', 'indexe na memoria: '):
        if texto.lower().startswith(prefixo):
            return texto[len(prefixo):]
    return texto

def _extensa_do_arquivo(alvo):
    import os
    return os.path.splitext(alvo)[1].lower() if alvo else ''

def responder_modulos_v110(pergunta):
    """Router automatico V1.10: decide a ferramenta pelo tipo de tarefa e executa."""
    tarefa = classificar_tarefa_v110(pergunta)
    if not tarefa:
        return False

    rota = tarefa['rota']
    ferramenta = tarefa['ferramenta']
    alvo = tarefa['alvo']

    print()
    print(f'[GoldenAI usando router V1.10] rota={rota} | ferramenta={ferramenta}')

    if rota == 'browser':
        if ferramenta == 'browser_search':
            query = _extrair_query_busca(pergunta)
            resultado = executar_tool_core('browser_search', dict(query=query, max_results=5))
            resposta = _formatar_internet_search_result(resultado)
        else:
            resultado = executar_tool_core('browser_fetch', dict(url=alvo))
            if isinstance(resultado, dict) and resultado.get('ok'):
                resposta = f"[Pagina: {resultado.get('title','')}]\n{resultado.get('content','')[:8000]}"
            else:
                resposta = 'Nao foi possivel abrir a pagina. ' + str(resultado)
        historico.append(dict(role='user', content=pergunta))
        historico.append(dict(role='assistant', content=resposta))
        print()
        print('Golden AI:')
        print(resposta[:4000])
        print()
        return True

    if rota == 'vision':
        if not alvo:
            resposta = ('Preciso do caminho da imagem para analisar. '
                        'Ex.: analise a imagem C:\\GoldenAI\\sandbox\\captura.png')
            historico.append(dict(role='user', content=pergunta))
            historico.append(dict(role='assistant', content=resposta))
            print()
            print('Golden AI:')
            print(resposta)
            print()
            return True
        resultado = executar_tool_core('vision_analyze_image', dict(imagem=alvo, pergunta=pergunta))
        if isinstance(resultado, dict) and resultado.get('ok'):
            resposta = resultado.get('texto', '')
        else:
            resposta = 'Nao foi possivel analisar a imagem. ' + str(resultado)
        historico.append(dict(role='user', content=pergunta))
        historico.append(dict(role='assistant', content=resposta))
        print()
        print('Golden AI:')
        print(resposta[:4000])
        print()
        return True

    if rota in ('document', 'audio', 'video'):
        if not alvo:
            mapa_ext = {'document': 'PDF/DOCX', 'audio': 'audio', 'video': 'video'}
            resposta = (f'Preciso do caminho do arquivo {mapa_ext.get(rota, "")} para processar. '
                        'Ex.: leia o PDF C:\\GoldenAI\\sandbox\\documento.pdf')
            historico.append(dict(role='user', content=pergunta))
            historico.append(dict(role='assistant', content=resposta))
            print()
            print('Golden AI:')
            print(resposta)
            print()
            return True
        resultado = executar_tool_core(ferramenta, dict(nome=alvo))
        if isinstance(resultado, dict) and resultado.get('ok'):
            if rota == 'document':
                resposta = f"[Documento: {resultado.get('title','')} | {resultado.get('file_type','')} | {resultado.get('page_count',0)} paginas]\n{resultado.get('content','')[:12000]}"
            elif rota == 'audio':
                resposta = f"[Transcricao | {resultado.get('language','')}]\n{resultado.get('text','')[:12000]}"
            else:
                resposta = f"[Analise de video | {resultado.get('duration_sec',0)}s]\n{resultado.get('text','')[:12000]}"
        else:
            resposta = 'Nao foi possivel processar o arquivo. ' + str(resultado)
        historico.append(dict(role='user', content=pergunta))
        historico.append(dict(role='assistant', content=resposta))
        print()
        print('Golden AI:')
        print(resposta[:4000])
        print()
        return True

    if rota == 'memory':
        if ferramenta == 'memory_vector_store':
            conteudo = _texto_memoria_para_store(pergunta)
            resultado = executar_tool_core('memory_vector_store', dict(texto=conteudo, fonte='chat', tipo='nota'))
            resposta = ('Memorizado com sucesso.' if isinstance(resultado, dict) and resultado.get('ok')
                        else 'Nao foi possivel memorizar. ' + str(resultado))
        else:
            resultado = executar_tool_core('memory_vector_search', dict(consulta=pergunta, limite=5))
            if isinstance(resultado, dict) and resultado.get('ok'):
                linhas = ['Resultados da memoria semantica:']
                for m in resultado.get('results', []):
                    linhas.append(f"- [{m.get('score', 0):.2f}] {m.get('text','')[:200]}")
                resposta = chr(10).join(linhas)
            else:
                resposta = 'Nao foi possivel buscar na memoria. ' + str(resultado)
        historico.append(dict(role='user', content=pergunta))
        historico.append(dict(role='assistant', content=resposta))
        print()
        print('Golden AI:')
        print(resposta[:4000])
        print()
        return True

    return False


# ============================================================
# PAINEL DE COMANDOS DO GOLDEN - V1.9.9.1
# ============================================================

def mostrar_painel_comandos():
    return chr(10).join([
        "=" * 70,
        "PAINEL DE COMANDOS DO GOLDEN",
        "=" * 70,
        "1. listar robos",
        "   -> lista todos os robos disponiveis (projetos/teste e MT5 real).",
        "",
        "2. abrir <robo>",
        "   -> mostra o codigo-fonte do robo numerado por linha.",
        "   ex: abrir Robo_XAUUSD_EMA_ATR_VWAP_TESTE",
        "",
        "3. analisar <robo>",
        "   -> explica o que o robo faz (funcionamento).",
        "   ex: analisar Robo_XAUUSD_EMA_ATR_VWAP_TESTE",
        "",
        "4. auditar <robo>",
        "   -> auditoria deterministica: procura erros e bugs confirmados.",
        "   ex: auditar Robo_XAUUSD_EMA_ATR_VWAP_TESTE",
        "",
        "5. corrigir <robo>: <pedido especifico>",
        "   -> corrige algo especifico que voce pedir.",
        "   ex: corrigir Robo_XAUUSD_EMA_ATR_VWAP_TESTE: aumente o stop loss",
        "",
        "6. compilar <robo>",
        "   -> compila o robo no MetaEditor.",
        "   ex: compilar Robo_XAUUSD_EMA_ATR_VWAP_TESTE",
        "",
        "7. estado",
        "   -> mostra o arquivo alvo atual e o ultimo veredito.",
        "",
        "8. painel | menu | ajuda",
        "   -> mostra este painel de comandos.",
        "",
        "9. sair",
        "   -> encerra o Golden.",
        "",
        "MODULOS V1.10 (arquivos e internet):",
        "- Leia o PDF/DOCX <arquivo>  -> extrai texto via Docling.",
        "- Transcreva o audio <arquivo> -> transcricao via faster-whisper.",
        "- Analise o video <arquivo>  -> transcricao + cenas via FFmpeg/Whisper/vision.",
        "- Analise a imagem <arquivo> -> descricao via modelo multimodal local.",
        "- Pesquise na internet <termo> -> busca web (DuckDuckGo/Bing).",
        "- Abra o site <url>           -> extrai texto renderizado da pagina.",
        "- Memorize isso: <texto>      -> indexa na memoria semantica (Qdrant).",
        "- Busque na memoria semantica <termo> -> busca vetorial por similaridade.",
        "",
        "DICAS:",
        "- Nomes podem ser digitados com ou sem .mq5.",
        "- Analise e auditoria sao SOMENTE LEITURA (nao alteram o arquivo).",
        "- Correcao so acontece em copia PROJETO_TESTE, com backup e rollback.",
        "- Em duvida, comece com: listar robos",
    ])


def listar_robos_painel():
    internos = {
        "_attachment_fixture", "_capability_audit", "_coding_test",
        "__pycache__", "_market_chat_smoke", "_quant_chat_smoke",
        "_studio_market_dataset", "_studio_quant_dataset",
    }

    def _mq5_de_pasta(pasta):
        achados = []
        if not os.path.isdir(pasta):
            return achados
        for raiz, _, nomes in os.walk(pasta):
            partes = raiz.replace("\\", "/").split("/")
            if any(p in internos for p in partes):
                continue
            for nome in nomes:
                if nome.lower().endswith((".mq5", ".mqh")):
                    completo = os.path.join(raiz, nome)
                    rel = os.path.relpath(completo, pasta)
                    achados.append(rel)
        achados.sort()
        return achados

    def _robos_do_usuario_mt5():
        """Somente robos do usuario: raiz de Experts e pasta 'Meus Robos'."""
        achados = []
        if not os.path.isdir(PASTA_MT5_EXPERTS):
            return achados
        para_excluir = {
            "advisors", "examples", "free robots", "indicators",
            "scripts", "translations", "include", "includes",
            "position sizer", "templates",
        }
        for raiz, _, nomes in os.walk(PASTA_MT5_EXPERTS):
            rel_dir = os.path.relpath(raiz, PASTA_MT5_EXPERTS)
            partes = [p.lower() for p in rel_dir.replace("\\", "/").split("/") if p]
            if any(p in para_excluir for p in partes):
                continue
            for nome in nomes:
                if not nome.lower().endswith(".mq5"):
                    continue
                completo = os.path.join(raiz, nome)
                rel = os.path.relpath(completo, PASTA_MT5_EXPERTS)
                achados.append(rel)
        achados.sort()
        return achados

    linhas = []
    linhas.append("ROBOS DISPONIVEIS")
    linhas.append("=" * 70)
    linhas.append("[PROJETOS / COPIA DE TESTE - editaveis]")
    projetos = _mq5_de_pasta(PASTA_PROJETOS)
    linhas.append("\n".join(projetos) if projetos else "Nenhum.")
    linhas.append("")
    linhas.append("[MT5 REAL - somente leitura]")
    eas = _robos_do_usuario_mt5()
    linhas.append("\n".join(eas) if eas else "Nenhum.")
    return chr(10).join(linhas)


def resolver_robo_por_nome(pergunta):
    """
    Resolve um robo pelo NOME citado (com ou sem .mq5), procurando primeiro
    na pasta de projetos/teste e depois no MT5 real. Retorna o dict alvo no
    mesmo formato de resolver_alvo_mql, ou {"ok": False}.
    """
    alvo = resolver_alvo_mql(pergunta)
    if alvo.get("ok"):
        return alvo

    p_lower = str(pergunta or "").lower()

    def _procurar_por_base(pasta):
        achados = []
        if not os.path.isdir(pasta):
            return achados
        for raiz, _, nomes in os.walk(pasta):
            for nome in nomes:
                if not nome.lower().endswith((".mq5", ".mqh")):
                    continue
                base = os.path.splitext(nome)[0].lower()
                if base and base in p_lower:
                    achados.append(os.path.join(raiz, nome))
        return achados

    candidatos_projetos = _procurar_por_base(PASTA_PROJETOS)
    if len(candidatos_projetos) == 1:
        caminho = os.path.abspath(candidatos_projetos[0])
        return {
            "ok": True,
            "tipo": "PROJETO_TESTE",
            "caminho": caminho,
            "nome": os.path.basename(caminho),
            "origem_resolucao": "PAINEL_NOME_PROJETOS",
        }

    candidatos_mt5 = _procurar_por_base(PASTA_MT5_EXPERTS)
    if len(candidatos_mt5) == 1:
        caminho = os.path.abspath(candidatos_mt5[0])
        return {
            "ok": True,
            "tipo": "MT5_REAL",
            "caminho": caminho,
            "nome": os.path.basename(caminho),
            "relativo_mt5": os.path.relpath(caminho, PASTA_MT5_EXPERTS),
            "origem_resolucao": "PAINEL_NOME_MT5",
        }

    return {
        "ok": False,
        "tipo": "INVALIDO",
        "caminho": None,
        "nome": None,
        "origem_resolucao": "PAINEL_NAO_RESOLVIDO",
    }


def mostrar_codigo_alvo_numerado(alvo):
    codigo, erro = ler_alvo_resolvido(alvo)
    if erro:
        print("Golden AI:")
        print(erro)
        print()
        return True
    linhas = codigo.splitlines()
    print()
    print("Golden AI:")
    print(
        f"CODIGO DE {alvo.get('nome')} "
        f"({len(linhas)} linhas) - {alvo.get('caminho')}"
    )
    print("-" * 72)
    for i, linha in enumerate(linhas, 1):
        print(f"{i:05d}: {linha}")
    print("-" * 72)
    print()
    return True


def executar_painel(pergunta):
    """
    Despacho determinístico do PAINEL DE COMANDOS.
    Retorna True se o comando foi tratado (o loop deve continuar).
    Retorna False para deixar o roteamento normal por intencao atuar.
    """
    global arquivo_alvo_atual, ultimo_veredito_auditoria

    p_lower = str(pergunta or "").lower()

    e_menu = any(
        termo in p_lower
        for termo in [
            "painel", "menu de comandos", "comandos disponiveis",
            "o que voce pode fazer", "o que voce sabe fazer",
            "ajuda", "ajude", "help", "tutorial", "como usar",
            "como posso usar", "o que sei fazer",
        ]
    )
    if e_menu:
        print("Golden AI:")
        print(mostrar_painel_comandos())
        print()
        return True

    e_listar = any(
        termo in p_lower
        for termo in [
            "listar robos", "lista de robos", "liste os robos",
            "quais robos", "quais robos existem", "mostrar robos",
            "mostre os robos", "robos disponiveis", "robos existentes",
            "listar eas", "lista de eas", "quais eas",
        ]
    )
    if e_listar:
        print("Golden AI:")
        print(listar_robos_painel())
        print()
        return True

    e_status = any(
        termo in p_lower
        for termo in [
            "status dos modulos", "estado dos modulos", "modulos disponiveis",
            "quais modulos", "situacao dos modulos", "o que esta instalado",
            "status modulos", "estado modulos", "modulos v1.10",
        ]
    )
    if e_status:
        print("Golden AI:")
        print("MODULOS V1.10")
        print(_status_modulos_v110())
        print()
        return True

    e_abrir = any(
        termo in p_lower
        for termo in [
            "abrir o codigo", "abra o codigo", "abrir codigo",
            "abra codigo", "mostre o codigo", "mostrar o codigo",
            "mostre o conteudo", "ver o codigo", "ver o conteudo",
            "mostra o codigo", "abrir o arquivo", "abra o arquivo",
        ]
    )
    if not e_abrir:
        e_abrir = (
            p_lower.startswith(("abrir ", "abra ", "abrir o ", "abra o "))
            and not p_lower.startswith(("abrir o painel", "abra o painel"))
        )
    if e_abrir:
        if extrair_nome_mq5(pergunta):
            return False
        alvo = resolver_robo_por_nome(pergunta)
        if not alvo.get("ok"):
            print("Golden AI:")
            print(
                "Nao encontrei o robo citado. "
                "Digite 'listar robos' para ver os disponiveis."
            )
            print()
            return True
        confirmar_alvo_na_tela(alvo, "ABRIR CODIGO")
        arquivo_alvo_atual = dict(alvo)
        return mostrar_codigo_alvo_numerado(alvo)

    e_analisar = any(
        termo in p_lower
        for termo in [
            "analisar", "analise", "analise o", "o que o robo faz",
            "o que esse robo faz", "o que este robo faz", "explicar o",
            "explique o", "como funciona o", "o que o codigo faz",
        ]
    )
    if e_analisar and not extrair_nome_mq5(pergunta):
        alvo = resolver_robo_por_nome(pergunta)
        if not alvo.get("ok"):
            return False
        if alvo.get("tipo") == "MT5_REAL" and alvo.get("relativo_mt5"):
            pergunta_expandida = (
                f"{pergunta}\nArquivo exato: {alvo.get('relativo_mt5')}"
            )
            analisar_arquivo_mt5_real(pergunta_expandida)
            return True
        pergunta_expandida = (
            f"{pergunta}\n"
            f"ARQUIVO ALVO ATUAL: {alvo.get('caminho')}"
        )
        arquivo_alvo_atual = dict(alvo)
        executar_agente_normal(
            pergunta_expandida,
            permitir_ferramentas=True
        )
        return True

    e_corrigir = any(
        termo in p_lower
        for termo in [
            "corrija", "corrigir", "conserte", "consertar",
            "ajuste", "ajustar", "modifique", "modificar",
            "implemente", "implementar", "altere a", "altere o",
        ]
    )
    if e_corrigir and not extrair_nome_mq5(pergunta):
        alvo = resolver_robo_por_nome(pergunta)
        if not alvo.get("ok"):
            return False
        if alvo.get("tipo") != "PROJETO_TESTE":
            print("Golden AI:")
            print(
                "Correcao so e permitida em copia PROJETO_TESTE. "
                "O arquivo do MT5 real permanece somente leitura. "
                "Crie uma copia de teste primeiro."
            )
            print()
            return True
        confirmar_alvo_na_tela(alvo, "CORRECAO DE CODIGO")
        pergunta_reescrita = (
            f"{pergunta} {alvo.get('caminho')}"
        )
        if responder_programador_opencode(pergunta_reescrita):
            return True
        nome = extrair_nome_mq5(pergunta_reescrita)
        if nome:
            corrigir_mql5_automatico(nome, pergunta_reescrita)
            return True
        print("Golden AI:")
        print(
            "Nao consegui iniciar a correcao deste arquivo. "
            "Tente: corrigir <nome>: <o que fazer>"
        )
        print()
        return True

    e_auditar = any(
        termo in p_lower
        for termo in [
            "auditar", "auditoria", "audite o", "verificar erros",
            "verifique erros", "tem erros", "procure erros", "ache erros",
            "auditoria do", "auditar o",
        ]
    )
    if e_auditar:
        if extrair_nome_mq5(pergunta):
            return False
        alvo = resolver_robo_por_nome(pergunta)
        if not alvo.get("ok"):
            print("Golden AI:")
            print(
                "Nao encontrei o robo citado para auditar. "
                "Digite 'listar robos' para ver os disponiveis."
            )
            print()
            return True
        if alvo.get("tipo") != "PROJETO_TESTE":
            print("Golden AI:")
            print(
                "Auditoria deterministica exige uma copia PROJETO_TESTE. "
                "O arquivo do MT5 real permanece somente leitura. "
                "Use o comando de copia para criar uma copia em projetos."
            )
            print()
            return True
        arquivo_alvo_atual = dict(alvo)
        ultimo_veredito_auditoria = analisar_alvo_projeto(
            arquivo_alvo_atual,
            pergunta
        )
        salvar_estado_alvo_auditoria(
            arquivo_alvo_atual,
            ultimo_veredito_auditoria
        )
        if ultimo_veredito_auditoria:
            print(
                "MEMORIA DA AUDITORIA: veredito salvo para este arquivo alvo."
            )
            print()
        return True

    return False


print("Digite 'sair' para encerrar.")
print("Digite 'painel' para ver todos os comandos disponiveis.")
print()


# Memoria persistente durante esta sessao + restauracao segura
# do ultimo alvo/veredito da versao anterior.
arquivo_alvo_atual, ultimo_veredito_auditoria = carregar_estado_alvo_auditoria()

if arquivo_alvo_atual:
    print()
    print("[GoldenAI V1.9.8.3] Estado anterior restaurado.")
    print(f"Arquivo alvo: {arquivo_alvo_atual.get('caminho')}")

    if ultimo_veredito_auditoria:
        autorizado, quantidade = interpretar_veredito_final(
            ultimo_veredito_auditoria.get("veredito", "")
        )

        ultimo_veredito_auditoria["autorizado"] = autorizado
        ultimo_veredito_auditoria["quantidade"] = quantidade

        print(
            "Veredito restaurado: "
            + ("AUTORIZADO" if autorizado else "NAO AUTORIZADO")
        )
        print(f"Bugs confirmados restaurados: {quantidade}")
    else:
        print("Nenhum veredito de auditoria restaurado.")

    print()

# Internet inicializada ANTES do loop principal (V1.9.8.4 fix).
CORE_INTERNET_SERVICE = None

try:
    from core.internet import InternetService
    CORE_INTERNET_SERVICE = InternetService(ROOT_GOLDENAI)
except Exception as erro_internet:
    print(f'[Internet V1] Integracao desativada: {erro_internet}')

# =========================================================
# MODULOS V1.10 - Browser, Documentos, Audio, Video, Qdrant
# =========================================================
CORE_BROWSER_SERVICE = None
CORE_DOCUMENT_SERVICE = None
CORE_AUDIO_SERVICE = None
CORE_VIDEO_SERVICE = None
CORE_VECTOR_MEMORY = None

try:
    from core.browser import BrowserService
    CORE_BROWSER_SERVICE = BrowserService(ROOT_GOLDENAI)
except Exception as erro_browser:
    print(f'[Browser] Integracao desativada: {erro_browser}')

try:
    from core.documents import DocumentService
    CORE_DOCUMENT_SERVICE = DocumentService(ROOT_GOLDENAI)
except Exception as erro_document:
    print(f'[Documentos] Integracao desativada: {erro_document}')

try:
    from core.audio import AudioService
    CORE_AUDIO_SERVICE = AudioService(ROOT_GOLDENAI)
except Exception as erro_audio:
    print(f'[Audio] Integracao desativada: {erro_audio}')

try:
    from core.video import VideoService
    CORE_VIDEO_SERVICE = VideoService(ROOT_GOLDENAI)
except Exception as erro_video:
    print(f'[Video] Integracao desativada: {erro_video}')

try:
    from core.memory import VectorMemoryService
    CORE_VECTOR_MEMORY = VectorMemoryService(ROOT_GOLDENAI)
except Exception as erro_qdrant:
    print(f'[Qdrant] Integracao desativada: {erro_qdrant}')

if __name__ == "__main__":
    while True:
        pergunta = input("Voce: ").strip()

        if pergunta.lower() == "sair":
            print()
            print("Golden AI encerrada.")
            break

        if not pergunta:
            continue

        pergunta_lower = pergunta.lower()

        # =========================================================
        # PAINEL DE COMANDOS - V1.9.9.1
        # Comandos diretos de painel (menu, listar, abrir, analisar,
        # corrigir, auditar) sao resolvidos deterministicamente ANTES
        # do roteamento por intencao conversacional.
        # =========================================================
        if executar_painel(pergunta):
            continue

        if responder_modulos_v110(pergunta):
            continue

        if "[studio_context]" in pergunta_lower and pergunta_pede_contexto_tecnico(pergunta):
            if responder_quant_chat(pergunta):
                continue
            if responder_market_chat(pergunta):
                continue
            if responder_media_chat(pergunta):
                continue
            if responder_orquestrador_chat(pergunta):
                continue
            if responder_memoria_chat(pergunta):
                continue
            executar_agente_normal(
                pergunta,
                permitir_ferramentas=True
            )
            continue

        if responder_quant_chat(pergunta):
            continue

        if responder_market_chat(pergunta):
            continue

        if responder_media_chat(pergunta):
            continue

        if responder_orquestrador_chat(pergunta):
            continue

        if responder_memoria_chat(pergunta):
            continue

        if responder_internet_chat(pergunta):
            continue

        if responder_consulta_local(pergunta):
            continue

        # =========================================================
        # ROTEAMENTO DE INTENCAO
        # =========================================================
        # Regra principal:
        # - pedidos de leitura/analise/revisao SEM alteracao -> MT5 real somente leitura
        # - pedidos explicitos de edicao/correcao -> modo de alteracao
        # - "nao altere", "somente analise", etc. tem prioridade absoluta

        termos_bloqueio_escrita = [
            "nao altere",
            "não altere",
            "nao modifique",
            "não modifique",
            "nao mexa",
            "não mexa",
            "somente analise",
            "apenas analise",
            "somente leia",
            "apenas leia",
            "sem alterar",
            "sem modificar"
        ]

        termos_leitura_analise = [
            "leia",
            "ler",
            "analise",
            "analisar",
            "revise",
            "revisar",
            "verifique",
            "verificar",
            "explique",
            "explicar",
            "audite",
            "auditar",
            "bug",
            "bugs",
            "erro",
            "erros",
            "problema",
            "problemas",
            "risco",
            "riscos",
            "o que esse robo faz",
            "o que este robo faz"
        ]

        termos_edicao = [
            "corrija",
            "corrigir",
            "conserte",
            "consertar",
            "modifique",
            "modificar",
            "altere",
            "alterar",
            "adicione",
            "adicionar",
            "remova",
            "remover",
            "substitua",
            "substituir",
            "reescreva",
            "reescrever",
            "implemente",
            "implementar",
            "0 errors",
            "0 warnings",
            "sem erros",
            "sem warnings"
        ]

        bloqueio_escrita = any(
            termo in pergunta_lower
            for termo in termos_bloqueio_escrita
        )

        intencao_leitura = any(
            termo in pergunta_lower
            for termo in termos_leitura_analise
        )

        intencao_edicao = any(
            termo in pergunta_lower
            for termo in termos_edicao
        )

        cita_arquivo_mql = (
            ".mq5" in pergunta_lower
            or ".mqh" in pergunta_lower
        )

        # =========================================================
        # NOVA AUDITORIA EXPLICITA - V1.9.5.5
        # =========================================================
        pedido_nova_auditoria = any(
            termo in pergunta_lower
            for termo in [
                "nova auditoria",
                "auditoria completa",
                "audite novamente",
                "auditar novamente",
                "analise novamente",
                "analisar novamente"
            ]
        )

        if pedido_nova_auditoria:
            if not arquivo_alvo_atual or not arquivo_alvo_atual.get("ok"):
                print()
                print("Golden AI:")
                print("Nenhum arquivo alvo valido esta definido.")
                print()
                continue

            if arquivo_alvo_atual.get("tipo") != "PROJETO_TESTE":
                print()
                print("Golden AI:")
                print("A nova auditoria automatica exige um PROJETO_TESTE.")
                print()
                continue

            ultimo_veredito_auditoria = analisar_alvo_projeto(
                arquivo_alvo_atual,
                pergunta
            )

            if ultimo_veredito_auditoria:
                salvar_estado_alvo_auditoria(
                    arquivo_alvo_atual,
                    ultimo_veredito_auditoria
                )
                print(
                    "MEMORIA DA AUDITORIA: novo veredito salvo para este arquivo alvo."
                )
                print()

            continue

        # =========================================================
        # RELATORIO DA ULTIMA AUTOCORRECAO - V1.9.5.5
        # =========================================================
        pedido_relatorio_autocorrecao = (
            any(
                termo in pergunta_lower
                for termo in [
                    "ultima autocorrecao",
                    "última autocorreção"
                ]
            )
            and any(
                termo in pergunta_lower
                for termo in [
                    "mostre",
                    "mostrar",
                    "relatorio",
                    "relatório",
                    "resultado",
                    "detalhes",
                    "informe"
                ]
            )
            and not any(
                termo in pergunta_lower
                for termo in [
                    "nova auditoria",
                    "auditoria completa",
                    "audite",
                    "auditar",
                    "analise novamente",
                    "analisar novamente"
                ]
            )
        )

        if pedido_relatorio_autocorrecao:
            relatorio = carregar_relatorio_autocorrecao()

            print()
            print("Golden AI:")
            imprimir_relatorio_autocorrecao(
                relatorio
            )

            continue

        # =========================================================
        # AUTOCORRECAO DIRETA PELO VEREDITO SALVO - V1.9.5.3
        # =========================================================
        # V1.9.6.4 - rota deterministica robusta para autocorrecao.
        # Nao depende mais de frases exatas como "execute a autocorrecao".
        # Ex.: "execute agora a autocorrecao somente do C1" entra aqui
        # antes de qualquer roteamento por ferramentas/modelo.
        tem_autocorrecao = any(
            termo in pergunta_lower
            for termo in ["autocorrecao", "autocorreção"]
        )

        tem_acao_autocorrecao = any(
            termo in pergunta_lower
            for termo in [
                "execute",
                "executar",
                "corrija",
                "corrigir",
                "aplique",
                "aplicar"
            ]
        )

        # V1.9.8.1 - INTENCAO ATUAL DO USUARIO TEM PRIORIDADE SOBRE VEREDITO SALVO.
        intencao_atual = classificar_intencao_usuario(pergunta)

        if intencao_atual == "LEITURA":
            executar_investigacao_somente_leitura(
                arquivo_alvo_atual,
                ultimo_veredito_auditoria,
                pergunta
            )
            continue

        contexto_bug_confirmado = (
            bool(re.search(r"\bC\d+\b", pergunta, flags=re.IGNORECASE))
            or "bug confirmado" in pergunta_lower
            or "bugs confirmados" in pergunta_lower
            or "correcao autorizada" in pergunta_lower
            or "correção autorizada" in pergunta_lower
        )

        # V1.9.6.7 - PREPARACAO/VALIDACAO DETERMINISTICA.
        # Um pedido para "preparar" a autocorrecao NAO vai ao modelo e NAO escreve arquivo.
        # A validacao usa diretamente a lista retornada pelo seletor, evitando a contradicao
        # observada na V1.9.6.6: ["C1"] + quantidade 1 sendo rejeitado.
        pedido_preparar_autocorrecao = (
            tem_autocorrecao
            and contexto_bug_confirmado
            and any(
                termo in pergunta_lower
                for termo in ["prepare", "preparar", "preparacao", "preparação"]
            )
            and not tem_acao_autocorrecao
        )

        if pedido_preparar_autocorrecao:
            if not ultimo_veredito_auditoria:
                print()
                print("Golden AI:")
                print("PREPARACAO BLOQUEADA: nao existe veredito salvo.")
                print()
                continue

            bugs_preview, ids_preview = selecionar_bugs_para_correcao(
                ultimo_veredito_auditoria,
                pergunta
            )
            ids_confirmados_preview = [
                str(item.get("id", "")).upper()
                for item in bugs_preview
                if isinstance(item, dict)
            ]
            quantidade_preview = len(bugs_preview)

            print()
            print("Golden AI:")
            print(f"IDs selecionados para esta execucao: {ids_preview}")
            print(f"Quantidade de bugs autorizados: {quantidade_preview}")

            selecao_valida = (
                len(ids_preview) == 1
                and quantidade_preview == 1
                and len(ids_confirmados_preview) == 1
                and ids_preview[0] == ids_confirmados_preview[0]
            )

            if selecao_valida:
                print("VALIDACAO: APROVADA.")
                print(
                    "Nenhum arquivo foi alterado. A autocorrecao ainda NAO foi executada."
                )
            else:
                print("VALIDACAO: REJEITADA.")
                print(
                    "Nenhum arquivo foi alterado. Interrompendo antes da autocorrecao."
                )
            print()
            continue

        # V1.9.6.6: selecao exclusiva ignora IDs citados apenas em ordens negativas.
        # Frases como "corrija C1; nao corrija C2...C8" NAO podem bloquear C1.
        bloqueio_execucao_autocorrecao = any(
            termo in pergunta_lower
            for termo in [
                "nao execute a autocorrecao",
                "não execute a autocorreção",
                "nao execute nenhuma autocorrecao",
                "não execute nenhuma autocorreção",
                "nao corrija nenhum",
                "não corrija nenhum",
                "nao aplique nenhuma correcao",
                "não aplique nenhuma correção"
            ]
        )

        pedido_corrigir_confirmados = (
            tem_autocorrecao
            and tem_acao_autocorrecao
            and contexto_bug_confirmado
            and not bloqueio_execucao_autocorrecao
        )

        if pedido_corrigir_confirmados:
            if not arquivo_alvo_atual or not arquivo_alvo_atual.get("ok"):
                print()
                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: nenhum arquivo alvo valido "
                    "esta definido."
                )
                print()
                continue

            if arquivo_alvo_atual.get("tipo") != "PROJETO_TESTE":
                print()
                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: o alvo atual nao e "
                    "uma copia PROJETO_TESTE."
                )
                print()
                continue

            if not ultimo_veredito_auditoria:
                print()
                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: nao existe veredito final "
                    "salvo para o arquivo alvo."
                )
                print()
                continue

            if not ultimo_veredito_auditoria.get("deterministico_aprovado"):
                print()
                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: o veredito salvo nao passou "
                    "pelo gate deterministico V1.9.6."
                )
                print(
                    "Execute: Faca uma nova auditoria completa do arquivo alvo."
                )
                print()
                continue

            if not ultimo_veredito_auditoria.get("autorizado"):
                print()
                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: o ultimo veredito nao "
                    "autorizou correcao."
                )
                print()
                continue

            if os.path.abspath(
                ultimo_veredito_auditoria.get("arquivo", "")
            ) != os.path.abspath(
                arquivo_alvo_atual.get("caminho", "")
            ):
                print()
                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: o veredito salvo pertence "
                    "a outro arquivo."
                )
                print()
                continue

            print()
            print("[ROTA DETERMINISTICA] AUTOCORRECAO AUTORIZADA PELO VEREDITO SALVO")
            print()
            print("=" * 70)
            print("ARQUIVO QUE SERA ALTERADO")
            print("=" * 70)
            print(f"Tipo: {arquivo_alvo_atual.get('tipo')}")
            print(f"Arquivo: {arquivo_alvo_atual.get('nome')}")
            print(f"Caminho: {arquivo_alvo_atual.get('caminho')}")
            bugs_alvo_preview, ids_preview = selecionar_bugs_para_correcao(
                ultimo_veredito_auditoria,
                pergunta
            )
            print(
                f"Bugs confirmados no veredito: "
                f"{ultimo_veredito_auditoria.get('quantidade', 0)}"
            )
            print(
                "Bugs selecionados para ESTA execucao: "
                + (
                    ", ".join(ids_preview)
                    if ids_preview
                    else "nenhum"
                )
            )
            print("MT5 REAL: BLOQUEADO PARA ESCRITA")
            print("=" * 70)
            print()

            relatorio_correcao = corrigir_bugs_confirmados_alvo(
                arquivo_alvo_atual,
                ultimo_veredito_auditoria,
                pergunta
            )

            if (
                isinstance(relatorio_correcao, dict)
                and relatorio_correcao.get("status") == "SUCESSO"
            ):
                ultimo_veredito_auditoria = None
                invalidar_veredito_persistente(
                    arquivo_alvo_atual
                )
                print(
                    "VEREDITO INVALIDADO: o codigo foi alterado com sucesso. "
                    "Execute uma nova auditoria antes de qualquer nova autocorrecao."
                )
                print()
            else:
                salvar_estado_alvo_auditoria(
                    arquivo_alvo_atual,
                    ultimo_veredito_auditoria
                )
                print(
                    "VEREDITO MANTIDO: a correcao nao foi aceita e o arquivo "
                    "foi restaurado ao estado anterior."
                )
                print()

            continue

        # =========================================================
        # MEMORIA DO ARQUIVO ALVO
        # =========================================================
        referencia_alvo = any(
            termo in pergunta_lower
            for termo in [
                "arquivo alvo",
                "alvo atual",
                "arquivo selecionado",
                "arquivo que acabei de definir",
                "arquivo definido",
                "essa copia",
                "esta copia"
            ]
        )

        if referencia_alvo and pergunta_pede_contexto_tecnico(pergunta) and not cita_arquivo_mql:
            if not arquivo_alvo_atual or not arquivo_alvo_atual.get("ok"):
                print()
                print("Golden AI:")
                print(
                    "Nenhum arquivo alvo esta definido nesta sessao. "
                    "Informe um caminho ou selecione uma copia primeiro."
                )
                print()
                continue

            # Confirma sempre o alvo real antes da operacao.
            confirmar_alvo_na_tela(
                arquivo_alvo_atual,
                "USAR MEMORIA DO ARQUIVO ALVO"
            )

            # Comandos de consulta do alvo.
            if any(
                termo in pergunta_lower
                for termo in [
                    "qual e o arquivo alvo",
                    "qual é o arquivo alvo",
                    "mostre o arquivo alvo",
                    "caminho do arquivo alvo",
                    "ultimo veredito",
                    "último veredito"
                ]
            ):
                print("Golden AI:")
                print("ESTADO ATUAL DO PROJETO")
                print(f"Nome: {arquivo_alvo_atual.get('nome')}")
                print(f"Caminho: {arquivo_alvo_atual.get('caminho')}")
                print(f"Tipo: {arquivo_alvo_atual.get('tipo')}")

                if arquivo_alvo_atual.get("tipo") == "PROJETO_TESTE":
                    print("Protecao: edicao permitida somente nesta copia de teste.")
                    print("MT5 real: bloqueado para escrita.")
                else:
                    print("Protecao: somente leitura.")

                print()
                print("ULTIMO VEREDITO SALVO:")

                if ultimo_veredito_auditoria:
                    autorizado, quantidade = interpretar_veredito_final(
                        ultimo_veredito_auditoria.get("veredito", "")
                    )

                    print(
                        "Autocorrecao autorizada: "
                        + ("SIM" if autorizado else "NAO")
                    )
                    print(f"Quantidade de bugs confirmados: {quantidade}")

                    texto_veredito = ultimo_veredito_auditoria.get(
                        "veredito",
                        ""
                    )

                    # Mostra apenas a secao final relevante, sem rodar nova IA.
                    secao = texto_veredito
                    pos = texto_veredito.upper().find(
                        "CONFIRMADOS PARA CORRECAO"
                    )
                    if pos >= 0:
                        secao = texto_veredito[pos:]

                    print()
                    print(secao[:5000])
                else:
                    print("Nenhum veredito de auditoria salvo.")

                print()
                continue

            # Leitura / auditoria do alvo atual.
            if (
                bloqueio_escrita
                or intencao_leitura
            ) and not (
                intencao_edicao and not bloqueio_escrita
            ):
                if arquivo_alvo_atual.get("tipo") == "PROJETO_TESTE":
                    ultimo_veredito_auditoria = analisar_alvo_projeto(
                        arquivo_alvo_atual,
                        pergunta
                    )

                    if ultimo_veredito_auditoria:
                        salvar_estado_alvo_auditoria(
                            arquivo_alvo_atual,
                            ultimo_veredito_auditoria
                        )

                        print(
                            "MEMORIA DA AUDITORIA: veredito final salvo "
                            "para este arquivo alvo."
                        )
                        print(
                            "ESTADO PERSISTENTE: alvo e veredito foram "
                            "gravados para sobreviver ao reinicio da GoldenAI."
                        )
                        print()

                    continue

                if arquivo_alvo_atual.get("tipo") == "MT5_REAL":
                    relativo = arquivo_alvo_atual.get("relativo_mt5")

                    if relativo:
                        pergunta_expandida = (
                            f"{pergunta}\n"
                            f"Arquivo exato: {relativo}"
                        )
                        analisar_arquivo_mt5_real(
                            pergunta_expandida
                        )
                        continue

            # Compilacao explicita do alvo atual.
            if any(
                termo in pergunta_lower
                for termo in [
                    "compile",
                    "compilar",
                    "compilacao",
                    "compilação"
                ]
            ) and not intencao_edicao:
                resultado_comp = compilar_alvo_resolvido(
                    arquivo_alvo_atual
                )

                print("Golden AI:")
                print(
                    f"Compilacao do alvo: errors={resultado_comp.get('errors')} "
                    f"warnings={resultado_comp.get('warnings')}"
                )
                print(resultado_comp.get("log", ""))
                print()
                continue

            # Edicao/autocorrecao somente na copia de teste.
            if intencao_edicao and not bloqueio_escrita:
                if not any(
                    termo in pergunta_lower
                    for termo in [
                        "confirmado para correcao",
                        "confirmados para correcao",
                        "bugs confirmados",
                        "problemas confirmados"
                    ]
                ):
                    print("Golden AI:")
                    print(
                        "AUTOCORRECAO BLOQUEADA PELA V1.9.2: "
                        "primeiro execute a auditoria conservadora e depois "
                        "peca explicitamente para corrigir somente os bugs "
                        "CONFIRMADOS PARA CORRECAO."
                    )
                    print()
                    continue
                if arquivo_alvo_atual.get("tipo") != "PROJETO_TESTE":
                    print("Golden AI:")
                    print(
                        "Edicao bloqueada: o arquivo alvo atual esta no MT5 REAL. "
                        "Crie ou selecione uma copia em C:\\GoldenAI\\projetos."
                    )
                    print()
                    continue

                if (
                    ultimo_veredito_auditoria
                    and ultimo_veredito_auditoria.get("autorizado")
                    and os.path.abspath(
                        ultimo_veredito_auditoria.get("arquivo", "")
                    ) == os.path.abspath(
                        arquivo_alvo_atual.get("caminho", "")
                    )
                ):
                    corrigir_bugs_confirmados_alvo(
                        arquivo_alvo_atual,
                        ultimo_veredito_auditoria,
                        pergunta
                    )
                    continue

                print("Golden AI:")
                print(
                    "AUTOCORRECAO BLOQUEADA: nao existe um veredito final "
                    "autorizado e salvo para este arquivo alvo."
                )
                print()
                continue

            print("Golden AI:")
            print(
                "Arquivo alvo reconhecido, mas nao identifiquei uma operacao "
                "de leitura, analise, compilacao ou edicao."
            )
            print()
            continue

        # ---------------------------------------------------------
        # PRIORIDADE 1: COPIA SEGURA MT5 -> TESTES
        # ---------------------------------------------------------
        # Pedido de copia tem prioridade ABSOLUTA sobre leitura,
        # analise e bloqueio de escrita do original.
        termos_copia_teste = [
            "crie uma copia de teste",
            "criar uma copia de teste",
            "copie para teste",
            "copiar para teste",
            "copia de teste",
            "trabalhe somente nessa copia",
            "trabalhar somente nessa copia",
            "não altere o arquivo original",
            "nao altere o arquivo original"
        ]

        pedido_copia = (
            cita_arquivo_mql
            and any(
                termo in pergunta_lower
                for termo in termos_copia_teste
            )
        )

        if pedido_copia:
            nome_real = extrair_nome_mt5_real(
                pergunta
            )

            if not nome_real:
                print()
                print("Golden AI:")
                print(
                    "Nao consegui identificar o arquivo "
                    ".mq5/.mqh para copiar."
                )
                print()
                continue

            resultado_copia = copiar_ea_mt5_para_teste(
                nome_real
            )

            print()
            print(
                "[GoldenAI usando ferramenta: "
                "copiar_ea_mt5_para_teste]"
            )
            print(
                resultado_copia.get(
                    "mensagem",
                    resultado_copia
                )
            )

            if resultado_copia.get("ok"):
                arquivo_alvo_atual = {
                    "ok": True,
                    "tipo": "PROJETO_TESTE",
                    "caminho": os.path.abspath(
                        resultado_copia.get("destino")
                    ),
                    "nome": resultado_copia.get("destino_nome"),
                    "origem_resolucao": "COPIA_MT5_PARA_TESTE"
                }
                ultimo_veredito_auditoria = None
                salvar_estado_alvo_auditoria(
                    arquivo_alvo_atual,
                    None
                )

                print()
                print(
                    "MEMORIA DO ALVO: a copia criada passou a ser "
                    "o arquivo alvo atual."
                )

            print()
            continue

        # ---------------------------------------------------------
        # PRIORIDADE 2: SOMENTE LEITURA / ANALISE
        # ---------------------------------------------------------
        # "Nao altere" bloqueia escrita, EXCETO quando o pedido
        # principal e criar uma copia de teste, tratado acima.
        if (
            cita_arquivo_mql
            and (
                bloqueio_escrita
                or (intencao_leitura and not intencao_edicao)
            )
            and not extrair_caminho_mql_explicito(pergunta)
        ):
            tratado = analisar_arquivo_mt5_real(
                pergunta
            )

            if tratado:
                continue

        # ---------------------------------------------------------
        # PRIORIDADE 3: EDICAO / AUTOCORRECAO
        # ---------------------------------------------------------
        # V1.9.9: edicao/correcao de codigo e delegada ao agente OpenCode
        # (executar_opencode) com cadeia de modelos Free -> Qwen local.
        # Golden define o trabalho e supervisiona o resultado.
        if (
            cita_arquivo_mql
            and intencao_edicao
            and not bloqueio_escrita
        ):
            if responder_programador_opencode(pergunta):
                continue

            nome = extrair_nome_mq5(
                pergunta
            )

            if not nome:
                print()
                print("Golden AI:")
                print(
                    "Nao consegui identificar o arquivo .mq5 "
                    "na sua ordem. Informe o nome do arquivo."
                )
                print()
                continue

            corrigir_mql5_automatico(
                nome,
                pergunta
            )

            continue

        # ---------------------------------------------------------
        # PRIORIDADE 4: CAMINHO/ALVO EXPLICITO
        # ---------------------------------------------------------
        # Se o usuario informar um caminho completo ou citar uma copia
        # existente em C:\GoldenAI\projetos, resolvemos deterministicamente.
        alvo_resolvido = resolver_alvo_mql(
            pergunta
        )

        caminho_explicito = extrair_caminho_mql_explicito(
            pergunta
        )

        pedido_trabalhar_copia = any(
            termo in pergunta_lower
            for termo in [
                "use a copia",
                "usar a copia",
                "trabalhe na copia",
                "trabalhar na copia",
                "somente na copia",
                "copia robo_",
                "_teste.mq5",
                "_teste.mqh"
            ]
        )

        if (
            caminho_explicito
            or (
                alvo_resolvido.get("ok")
                and alvo_resolvido.get("tipo") == "PROJETO_TESTE"
                and pedido_trabalhar_copia
            )
        ):
            if not alvo_resolvido.get("ok"):
                print()
                print("Golden AI:")
                print(
                    "O caminho/arquivo informado nao foi encontrado. "
                    "Nenhum outro arquivo sera usado no lugar dele."
                )
                print()
                continue

            if alvo_resolvido.get("tipo") == "FORA_DAS_AREAS_AUTORIZADAS":
                print()
                print("Golden AI:")
                print(
                    "O caminho informado esta fora das areas autorizadas. "
                    "Nenhum arquivo foi aberto ou alterado."
                )
                print()
                continue

            confirmar_alvo_na_tela(
                alvo_resolvido,
                "TRABALHAR NO ARQUIVO INFORMADO"
            )

            arquivo_alvo_atual = dict(alvo_resolvido)
            ultimo_veredito_auditoria = None
            salvar_estado_alvo_auditoria(
                arquivo_alvo_atual,
                None
            )

            print(
                "MEMORIA DO ALVO: este arquivo permanecera selecionado "
                "nas proximas operacoes desta sessao."
            )
            print()

            # Apenas confirma o alvo neste momento.
            # O modelo nao pode substituir por outro nome.
            if intencao_edicao and alvo_resolvido.get("tipo") == "MT5_REAL":
                print("Golden AI:")
                print(
                    "Edicao bloqueada: o arquivo alvo esta no MT5 REAL. "
                    "Crie ou use uma copia em C:\\GoldenAI\\projetos."
                )
                print()
                continue

            # Se for apenas referencia ao alvo, informa que esta pronto.
            if not intencao_edicao and not intencao_leitura:
                print("Golden AI:")
                print(
                    "Arquivo alvo definido com sucesso. "
                    "Vou usar exatamente este arquivo nas proximas operacoes."
                )
                print()
                continue

            # Leitura/analise de copia de teste: usa exatamente o caminho resolvido.
            if intencao_leitura and alvo_resolvido.get("tipo") == "PROJETO_TESTE":
                codigo_alvo, erro_alvo = ler_alvo_resolvido(
                    alvo_resolvido
                )

                if erro_alvo:
                    print("Golden AI:")
                    print(erro_alvo)
                    print()
                    continue

                print("Golden AI:")
                print(
                    f"Arquivo de teste lido com sucesso: "
                    f"{alvo_resolvido.get('caminho')}"
                )
                print(
                    f"Tamanho: {len(codigo_alvo)} caracteres."
                )
                print()
                continue

        # ---------------------------------------------------------
        # PRIORIDADE 5: perguntas normais
        # ---------------------------------------------------------
        # Se houver um alvo MQL selecionado, informa isso ao agente,
        # mas proibe qualquer substituicao por .bat, .py ou outro arquivo.
        intencao_tecnica_para_agente = pergunta_pede_contexto_tecnico(pergunta)
        intencao_ferramenta_local = pergunta_pede_ferramenta_local(pergunta)

        if (
            intencao_tecnica_para_agente
            and arquivo_alvo_atual
            and arquivo_alvo_atual.get("ok")
        ):
            pergunta_agente = (
                pergunta
                + "\n\nCONTEXTO DETERMINISTICO DA GOLDENAI:"
                + f"\nARQUIVO ALVO ATUAL: {arquivo_alvo_atual.get('caminho')}"
                + "\nNAO substitua este arquivo por nenhum .bat, .py, exemplo "
                  "ou outro arquivo."
            )
        else:
            pergunta_agente = pergunta

        executar_agente_normal(
            pergunta_agente,
            permitir_ferramentas=(intencao_tecnica_para_agente or intencao_ferramenta_local)
        )
