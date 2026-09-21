"""
Golden AI - Painel de Comandos

Extraído de golden_ai.py (linhas 8855-9300).
Interface de comandos do Golden AI (CLI).
"""

import os
import re

from .context import CFG
from .utils import normalizar_texto_intencao, extrair_nome_mq5
from .mt5 import listar_eas_mt5, compilar_mql5
from .files import listar_projetos, ler_arquivo, arquivo_metadados


# ============================================================
# PAINEL DE COMANDOS
# ============================================================

def mostrar_painel_comandos():
    """Retorna o texto do painel de comandos."""
    return "\n".join([
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
        "- Pesquise na internet <query> -> busca web.",
        "- Memorize <texto> -> grava na memoria semantica.",
        "- Busque na memoria <query> -> busca na memoria vetorial.",
        "",
        "AGENTS:",
        "- market: analise de mercado com datasets CSV.",
        "- quant: backtesting de estrategias.",
        "- media: ingestao e analise de midia.",
        "- memory: armazenamento de conhecimento.",
        "- orquestrador: delega tarefas a agentes especializados.",
        "",
        "ATALHOS:",
        "- Ctrl+Enter: enviar mensagem no Studio Web.",
        "- Ctrl+N: nova conversa.",
        "- Ctrl+K: buscar no historico.",
        "",
        "DMCA: Este software e protegido por direitos autorais.",
        "=" * 70,
    ])


def listar_robos_painel():
    """Lista todos os robôs disponíveis (MT5 + projetos)."""
    linhas = ["ROBOS DISPONIVEIS:"]

    # MT5 real
    mt5_list = listar_eas_mt5()
    if not mt5_list.startswith("Pasta real") and not mt5_list.startswith("Nenhum"):
        linhas.append("")
        linhas.append("MT5 REAL (somente leitura):")
        for l in mt5_list.splitlines()[:30]:
            linhas.append(f"  {l}")

    # Projetos
    projetos = listar_projetos()
    if not projetos.startswith("A pasta") and not projetos.startswith("Nenhum"):
        linhas.append("")
        linhas.append("PROJETOS (editaveis com copia de teste):")
        mq5_files = [l for l in projetos.splitlines() if l.endswith((".mq5", ".mqh"))]
        for l in mq5_files[:30]:
            linhas.append(f"  {l}")

    return "\n".join(linhas)


def resolver_robo_por_nome(pergunta):
    """
    Tenta resolver o nome de um robô mencionado na pergunta.
    Retorna dict com ok, tipo, caminho, nome, etc.
    """
    texto = normalizar_texto_intencao(pergunta)

    # Extrai nome do robô da pergunta
    match = re.search(
        r"(?:robo|robô|ea|expert|bot)\s+([\w\s\-\.]+?)(?:\s*:|\s*$)",
        texto,
        re.IGNORECASE,
    )

    if not match:
        # Tenta extrair .mq5
        nome_mq5 = extrair_nome_mq5(pergunta)
        if nome_mq5:
            caminho = os.path.join(CFG.PASTA_PROJETOS, nome_mq5)
            if os.path.isfile(caminho):
                return {
                    "ok": True,
                    "tipo": "PROJETO_TESTE",
                    "caminho": os.path.abspath(caminho),
                    "nome": os.path.basename(caminho),
                }
        return {"ok": False}

    nome_candidato = match.group(1).strip()

    # Busca em projetos
    if os.path.isdir(CFG.PASTA_PROJETOS):
        for raiz, _, nomes in os.walk(CFG.PASTA_PROJETOS):
            for nome in nomes:
                if nome_candidato.lower() in nome.lower():
                    caminho = os.path.join(raiz, nome)
                    return {
                        "ok": True,
                        "tipo": "PROJETO_TESTE",
                        "caminho": os.path.abspath(caminho),
                        "nome": nome,
                    }

    # Busca no MT5 real
    if os.path.isdir(CFG.PASTA_MT5_EXPERTS):
        for raiz, _, nomes in os.walk(CFG.PASTA_MT5_EXPERTS):
            for nome in nomes:
                if nome_candidato.lower() in nome.lower():
                    caminho = os.path.join(raiz, nome)
                    relativo = os.path.relpath(caminho, CFG.PASTA_MT5_EXPERTS)
                    return {
                        "ok": True,
                        "tipo": "MT5_REAL",
                        "caminho": os.path.abspath(caminho),
                        "nome": nome,
                        "relativo_mt5": relativo,
                    }

    return {"ok": False}


def mostrar_codigo_alvo_numerado(alvo):
    """Mostra o código do alvo numerado por linha."""
    if not alvo or not alvo.get("ok") or not alvo.get("caminho"):
        return False

    caminho = alvo["caminho"]
    if not os.path.isfile(caminho):
        print("Arquivo nao encontrado.")
        return False

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            linhas = f.read().splitlines()

        print(f"\n{'=' * 60}")
        print(f"ARQUIVO: {alvo.get('nome', caminho)}")
        print(f"TIPO: {alvo.get('tipo', 'DESCONHECIDO')}")
        print(f"LINHAS: {len(linhas)}")
        print(f"{'=' * 60}")

        for i, linha in enumerate(linhas, 1):
            print(f"{i:4d} | {linha}")

        print(f"{'=' * 60}\n")
        return True

    except Exception as e:
        print(f"Erro ao ler arquivo: {e}")
        return False


def executar_painel(pergunta, arquivo_alvo_atual, ultimo_veredito_auditoria):
    """
    Despacho determinístico do painel de comandos.
    Retorna True se o comando foi tratado.
    """
    p_lower = str(pergunta or "").lower()

    # Menu/Ajuda
    if any(t in p_lower for t in ["painel", "menu de comandos", "ajuda", "help", "como usar"]):
        print("Golden AI:")
        print(mostrar_painel_comandos())
        print()
        return True

    # Listar robôs
    if any(t in p_lower for t in ["listar robos", "lista de robos", "quais robos"]):
        print("Golden AI:")
        print(listar_robos_painel())
        print()
        return True

    # Abrir código
    if any(t in p_lower for t in ["abrir o codigo", "abra o codigo", "mostre o codigo", "abrir codigo"]):
        alvo = resolver_robo_por_nome(pergunta)
        if not alvo.get("ok"):
            print("Golden AI:")
            print("Nao encontrei o robo citado. Digite 'listar robos' para ver os disponiveis.")
            print()
            return True
        mostrar_codigo_alvo_numerado(alvo)
        return True

    # Compilar
    if any(t in p_lower for t in ["compilar", "compile", "compilacao"]):
        nome_mq5 = extrair_nome_mq5(pergunta)
        if nome_mq5:
            resultado = compilar_mql5(nome_mq5)
            print("Golden AI:")
            print(f"Compilacao: errors={resultado.get('errors', '?')} warnings={resultado.get('warnings', '?')}")
            print(resultado.get("log", resultado.get("erro", "")))
            print()
            return True

    return False
