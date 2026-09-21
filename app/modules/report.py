"""
Golden AI - Relatórios, Parser de Veredito e Estado Persistente

Extraído de golden_ai.py (linhas 7063-7348).
Relatórios de autocorreção, parser de veredito, estado de sessão.
"""

import os
import json

from .context import CFG


# ============================================================
# ARQUIVOS DE ESTADO
# ============================================================

ARQUIVO_RELATORIO_AUTOCORRECAO = os.path.join(CFG.PASTA_APP, "ultima_autocorrecao.json")
ARQUIVO_ESTADO_SESSAO = os.path.join(CFG.PASTA_APP, "estado_alvo_auditoria.json")
ARQUIVO_AUDITORIA = os.path.join(CFG.PASTA_APP, "ultima_auditoria_deterministica.json")


# ============================================================
# RELATORIO DE AUTOCORRECAO
# ============================================================

def salvar_relatorio_autocorrecao(relatorio):
    """Salva relatório de autocorreção em JSON."""
    if not isinstance(relatorio, dict):
        return False
    try:
        with open(ARQUIVO_RELATORIO_AUTOCORRECAO, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        return True
    except Exception as erro:
        print(f"[AVISO] Nao foi possivel salvar o relatorio: {erro}")
        return False


def carregar_relatorio_autocorrecao():
    """Carrega relatório de autocorreção do JSON."""
    if not os.path.isfile(ARQUIVO_RELATORIO_AUTOCORRECAO):
        return None
    try:
        with open(ARQUIVO_RELATORIO_AUTOCORRECAO, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else None
    except Exception:
        return None


def imprimir_relatorio_autocorrecao(relatorio):
    """Imprime relatório de autocorreção formatado."""
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
    print(f"Compilacao: errors={comp.get('errors', 'n/a')} warnings={comp.get('warnings', 'n/a')}")

    tentativas = relatorio.get("tentativas", []) or []
    print()
    print("TENTATIVAS DE AUTOCORRECAO:")
    if not tentativas:
        print("- Nenhuma tentativa detalhada registrada.")
    else:
        for item in tentativas:
            texto = f"- Tentativa {item.get('tentativa')}: {item.get('status')}"
            if "errors" in item or "warnings" in item:
                texto += f" | errors={item.get('errors')} warnings={item.get('warnings')}"
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
            print(f"... {len(alteracoes) - 120} linha(s) adicionais omitidas.")

    print("=" * 70)
    print()


# ============================================================
# PARSER DE VEREDITO
# ============================================================

def interpretar_veredito_final(texto_veredito):
    """
    Extrai autorização e quantidade de bugs do veredito.
    Funciona mesmo com Markdown misturado.
    """
    if not isinstance(texto_veredito, str):
        return False, 0

    # Remove marcadores Markdown
    limpo = texto_veredito.replace("*", "").replace("`", "")

    m_aut = re.search(
        r"AUTOCORRECAO\s+AUTORIZADA\s*:\s*(SIM|NAO|NÃO)",
        limpo, flags=re.IGNORECASE
    )

    m_qtd = re.search(
        r"QUANTIDADE\s+DE\s+BUGS\s+CONFIRMADOS\s*:\s*(\d+)",
        limpo, flags=re.IGNORECASE
    )

    quantidade = int(m_qtd.group(1)) if m_qtd else 0
    autorizado_texto = bool(m_aut) and m_aut.group(1).upper() == "SIM"
    autorizado = autorizado_texto and quantidade > 0

    return autorizado, quantidade


def resumo_veredito_persistente(veredito):
    """Retorna resumo textual do veredito."""
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
# ESTADO PERSISTENTE
# ============================================================

def salvar_estado_alvo_auditoria(alvo, veredito):
    """Salva estado do arquivo alvo e veredito."""
    dados = {
        "arquivo_alvo": alvo,
        "ultimo_veredito": veredito
    }
    try:
        with open(ARQUIVO_ESTADO_SESSAO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        return True
    except Exception as erro:
        print(f"[AVISO] Nao foi possivel salvar o estado: {erro}")
        return False


def carregar_estado_alvo_auditoria():
    """Carrega estado do arquivo alvo e veredito."""
    if not os.path.isfile(ARQUIVO_ESTADO_SESSAO):
        return None, None

    try:
        with open(ARQUIVO_ESTADO_SESSAO, "r", encoding="utf-8") as f:
            dados = json.load(f)

        alvo = dados.get("arquivo_alvo")
        veredito = dados.get("ultimo_veredito")

        # Revalida o arquivo fisicamente
        if alvo and alvo.get("caminho") and os.path.isfile(alvo.get("caminho")):
            alvo["ok"] = True
        else:
            alvo = None
            veredito = None

        # Um veredito só é válido se pertence ao alvo carregado
        if alvo and veredito:
            if os.path.abspath(veredito.get("arquivo", "")) != os.path.abspath(alvo.get("caminho", "")):
                veredito = None
            else:
                autorizado, quantidade = interpretar_veredito_final(veredito.get("veredito", ""))
                veredito["autorizado"] = autorizado
                veredito["quantidade"] = quantidade

        return alvo, veredito

    except Exception as erro:
        print(f"[AVISO] Estado anterior ignorado: {erro}")
        return None, None


def invalidar_veredito_persistente(alvo):
    """Invalida veredito (após correção bem-sucedida)."""
    salvar_estado_alvo_auditoria(alvo, None)


def salvar_auditoria_deterministica(dados):
    """Salva resultado da auditoria determinística."""
    try:
        with open(ARQUIVO_AUDITORIA, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def carregar_auditoria_deterministica():
    """Carrega última auditoria determinística."""
    if not os.path.isfile(ARQUIVO_AUDITORIA):
        return None
    try:
        with open(ARQUIVO_AUDITORIA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
