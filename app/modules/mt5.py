"""
Golden AI - Operações MT5

Extraído de golden_ai.py (linhas 315-389 + 1785-1930 + 2765-3412).
Operações de leitura segura do MetaTrader 5.
"""

import os
import subprocess
from datetime import datetime

from .context import CFG


# ============================================================
# MT5 REAL - MODO SEGURO (SOMENTE LEITURA)
# ============================================================

def caminho_seguro_mt5(relativo):
    """Valida se o caminho está dentro da pasta MT5 autorizada."""
    if not isinstance(relativo, str) or not relativo.strip():
        return None

    caminho = os.path.abspath(
        os.path.join(CFG.PASTA_MT5_EXPERTS, relativo.strip())
    )
    pasta = os.path.abspath(CFG.PASTA_MT5_EXPERTS)

    try:
        comum = os.path.commonpath([caminho, pasta])
    except ValueError:
        return None

    if comum != pasta:
        return None

    return caminho


def listar_eas_mt5():
    """Lista todos os arquivos .mq5/.mqh na pasta Experts do MT5."""
    if not os.path.isdir(CFG.PASTA_MT5_EXPERTS):
        return (
            "Pasta real de Experts do MT5 nao encontrada:\n"
            f"{CFG.PASTA_MT5_EXPERTS}"
        )

    arquivos = []

    for raiz, _, nomes in os.walk(CFG.PASTA_MT5_EXPERTS):
        for nome in nomes:
            if nome.lower().endswith((".mq5", ".mqh")):
                completo = os.path.join(raiz, nome)
                relativo = os.path.relpath(completo, CFG.PASTA_MT5_EXPERTS)
                arquivos.append(relativo)

    if not arquivos:
        return "Nenhum arquivo .mq5 ou .mqh encontrado no MT5 real."

    arquivos.sort()
    return "\n".join(arquivos)


def ler_arquivo_mt5(relativo):
    """Lê o conteúdo de um arquivo .mq5/.mqh do MT5."""
    caminho = caminho_seguro_mt5(relativo)

    if caminho is None:
        return "Acesso negado ou caminho MT5 invalido."

    if not os.path.isfile(caminho):
        return f"Arquivo MT5 nao encontrado: {relativo}"

    if not caminho.lower().endswith((".mq5", ".mqh")):
        return "Leitura MT5 permitida somente para arquivos .mq5 e .mqh."

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as erro:
        return f"Erro ao ler arquivo MT5: {erro}"


# ============================================================
# METAEDITOR - COMPILAÇÃO
# ============================================================

def ler_log(caminho):
    """Lê log de compilação do MetaEditor."""
    if not os.path.isfile(caminho):
        return ""

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def compilar_mql5(nome):
    """
    Compila um arquivo .mq5 usando o MetaEditor.
    Retorna dict com status, errors, warnings, log.
    """
    caminho = os.path.abspath(
        os.path.join(CFG.PASTA_PROJETOS, nome.strip())
    )

    if not os.path.isfile(caminho):
        return {"ok": False, "erro": f"Arquivo nao encontrado: {nome}"}

    if not os.path.isfile(CFG.METAEDITOR):
        return {"ok": False, "erro": "MetaEditor nao encontrado."}

    log_path = os.path.join(CFG.PASTA_LOGS, f"compile_{nome}.log")

    try:
        os.makedirs(CFG.PASTA_LOGS, exist_ok=True)

        cmd = [
            CFG.METAEDITOR,
            "/compile",
            caminho,
            "/include:" + CFG.PASTA_MT5_MQL5,
            "/log:" + log_path,
        ]

        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )

        log = ler_log(log_path)

        errors = 0
        warnings = 0

        for linha in log.splitlines():
            lower = linha.lower()
            if "error" in lower:
                errors += 1
            elif "warning" in lower:
                warnings += 1

        return {
            "ok": True,
            "errors": errors,
            "warnings": warnings,
            "log": log,
            "arquivo": nome,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "erro": "Compilacao excedeu timeout (120s)."}
    except Exception as erro:
        return {"ok": False, "erro": f"Erro na compilacao: {erro}"}


# ============================================================
# ANÁLISE DE ARQUIVO MT5 REAL
# ============================================================

def analisar_arquivo_mt5_real(pergunta):
    """
    Analisa um arquivo MT5 real (somente leitura).
    Retorna dict com resultado da análise.
    """
    from .utils import normalizar_texto_intencao

    texto = normalizar_texto_intencao(pergunta)

    # Tenta extrair caminho da pergunta
    import re
    match = re.search(r'(?i)([A-Za-z0-9_\-\\.\/\\]+\.mq5)', pergunta)
    if not match:
        return {"ok": False, "erro": "Arquivo .mq5 nao identificado na pergunta."}

    nome = match.group(1).strip()

    # Se for caminho absoluto, converte para relativo
    if os.path.isabs(nome):
        try:
            pasta = os.path.abspath(CFG.PASTA_MT5_EXPERTS)
            if os.path.commonpath([os.path.abspath(nome), pasta]) == pasta:
                nome = os.path.relpath(os.path.abspath(nome), pasta)
            else:
                return {"ok": False, "erro": "Caminho fora da pasta MT5 autorizada."}
        except ValueError:
            return {"ok": False, "erro": "Caminho invalido."}

    # Lê o conteúdo
    conteudo = ler_arquivo_mt5(nome)
    if conteudo.startswith("Acesso negado") or conteudo.startswith("Arquivo MT5 nao"):
        return {"ok": False, "erro": conteudo}

    # Análise básica
    linhas = conteudo.splitlines()
    num_linhas = len(linhas)
    num_funcoes = sum(1 for l in linhas if l.strip().startswith("void ") or l.strip().startswith("int ") or l.strip().startswith("double ") or l.strip().startswith("bool ") or l.strip().startswith("string "))

    return {
        "ok": True,
        "arquivo": nome,
        "linhas": num_linhas,
        "funcoes": num_funcoes,
        "tamanho": len(conteudo),
        "conteudo_preview": conteudo[:2000],
    }
