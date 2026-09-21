"""
Golden AI - Correção Automática

Extraído de golden_ai.py (linhas 5787-7062).
Correção semântica autorizada, geração de patches cirúrgicos.
"""

import os
import re
import json

from .context import CFG, SERVICES


# ============================================================
# GERAÇÃO DE CONTRATO DE CORREÇÃO
# ============================================================

def _gerar_contrato_correcao(bug, funcao_real, funcao_antes, contexto, revalidacoes):
    """Gera contrato estruturado para correção de bug."""
    contrato = {
        "bug_id": bug.get("id", ""),
        "funcao": funcao_real,
        "categoria": bug.get("categoria", ""),
        "problema": bug.get("problema", ""),
        "evidencia": bug.get("evidencia", ""),
        "restricoes": [
            "NAO alterar assinatura da funcao",
            "NAO remover variaveis existentes",
            "MANTER logica de fallback existente",
            "MANTER formatacao do codigo original",
        ],
        "revalidacoes": revalidacoes or [],
    }

    # Restrições por categoria
    cat = contrato["categoria"]
    if cat == "CALCULO_LOTE":
        contrato["restricoes"].append("MANTER NormaliseLots como funcao auxiliar")
        contrato["restricoes"].append("MANTER logica de risk_pct como fallback")
    elif cat == "PRECO_STOP":
        contrato["restricoes"].append("MANTER validacao de stop_loss > 0")
    elif cat == "TRAILING":
        contrato["restricoes"].append("MANTER verificacao de trailing_ativo")

    return contrato


def _validar_patch_contra_contrato(bug, contrato, funcao_antes, funcao_depois, resultado_compilacao):
    """Valida se o patch respeita o contrato."""
    erros = []

    # Verifica se a assinatura da função não mudou
    sig_antes = re.search(r"(void|int|double|bool|string)\s+\w+\s*\(", funcao_antes)
    sig_depois = re.search(r"(void|int|double|bool|string)\s+\w+\s*\(", funcao_depois)

    if sig_antes and sig_depois:
        if sig_antes.group(0) != sig_depois.group(0):
            erros.append("Assinatura da funcao alterada")

    # Verifica se compilou
    if resultado_compilacao and resultado_compilacao.get("errors", 0) > 0:
        erros.append(f"Erros de compilacao: {resultado_compilacao.get('errors')}")

    return {
        "valido": len(erros) == 0,
        "erros": erros,
    }


# ============================================================
# GERAÇÃO DE PATCH CIRÚRGICO
# ============================================================

def _extrair_funcao_por_intervalo(codigo, intervalo):
    """Extrai função por intervalo de linhas."""
    linhas = codigo.splitlines()
    if not intervalo:
        return ""

    ini = max(0, intervalo[0] - 1)
    fim = min(len(linhas), intervalo[1])

    return "\n".join(linhas[ini:fim])


def _contexto_funcao(codigo, intervalo, margem=45):
    """Retorna contexto ao redor da função."""
    linhas = codigo.splitlines()
    if not intervalo:
        return ""

    ini = max(0, intervalo[0] - margem)
    fim = min(len(linhas), intervalo[1] + margem)

    return "\n".join(linhas[ini:fim])


def _normalizar_substituicao_funcao(texto_funcao, nome_funcao):
    """Normaliza substituição de função."""
    if not texto_funcao:
        return texto_funcao

    # Remove comentários de bloco no início
    texto_funcao = re.sub(r"^\s*/\*.*?\*/\s*", "", texto_funcao, flags=re.DOTALL)

    return texto_funcao.strip()


def _montar_patch_cirurgico(codigo_original, intervalo, nova_funcao):
    """Monta patch cirúrgico substituindo apenas a função alvo."""
    linhas = codigo_original.splitlines()

    if not intervalo:
        return codigo_original

    ini = max(0, intervalo[0] - 1)
    fim = min(len(linhas), intervalo[1])

    novas_linhas = nova_funcao.splitlines()

    resultado = linhas[:ini] + novas_linhas + linhas[fim:]

    return "\n".join(resultado)


# ============================================================
# VALIDAÇÃO PÓS-COMPILAÇÃO
# ============================================================

def _validar_invariantes_patch_cirurgico(codigo_original, candidato, intervalo, nome_funcao):
    """Valida invariantes do patch cirúrgico."""
    erros = []

    # Verifica se a função ainda existe
    if nome_funcao and nome_funcao not in candidato:
        erros.append(f"Funcao {nome_funcao} removida pelo patch")

    # Verifica se o tamanho é razoável (não dobrou nem reduziu pela metade)
    linhas_antes = len(codigo_original.splitlines())
    linhas_depois = len(candidato.splitlines())

    if linhas_depois > linhas_antes * 2:
        erros.append("Codigo dobrou de tamanho")
    elif linhas_depois < linhas_antes * 0.5:
        erros.append("Codigo reduziu pela metade")

    return {
        "valido": len(erros) == 0,
        "erros": erros,
    }


def _validar_funcao_pos_compilacao_cirurgica(bug, funcao_antes, funcao_depois, resultado_compilacao):
    """Valida função após compilação cirúrgica."""
    if not resultado_compilacao:
        return {"valido": True, "erros": []}

    erros = []
    if resultado_compilacao.get("errors", 0) > 0:
        erros.append(f"Erros de compilacao: {resultado_compilacao.get('errors')}")

    return {
        "valido": len(erros) == 0,
        "erros": erros,
    }


# ============================================================
# PATCH CIRÚRGICO VIA OPENCODE
# ============================================================

def _preflight_mql5_funcao(funcao_texto):
    """Pré-flight check de função MQL5."""
    if not funcao_texto:
        return {"ok": False, "erro": "Funcao vazia"}

    # Verifica se tem retorno
    if "return" not in funcao_texto and "void" not in funcao_texto:
        return {"ok": False, "erro": "Funcao sem return e nao e void"}

    # Verifica balanceamento de chaves
    abertas = funcao_texto.count("{")
    fechadas = funcao_texto.count("}")
    if abertas != fechadas:
        return {"ok": False, "erro": f"Chaves desbalanceadas: {abertas} abertas, {fechadas} fechadas"}

    return {"ok": True}


def _revalidar_bug_antes_de_corrigir(bug, funcao_real, funcao_antes, contexto):
    """Revalida se o bug ainda existe antes de corrigir."""
    # Verificação básica: se a função mudou, o bug pode ter sido corrigido
    if funcao_antes and funcao_real != funcao_antes:
        return {
            "ainda_presente": False,
            "motivo": "Funcao foi alterada desde a auditoria",
        }

    return {
        "ainda_presente": True,
        "motivo": "Funcao inalterada, bug ainda presente",
    }


def _gerar_patch_cirurgico_opencode(bug, contrato, funcao_real, funcao_antes, contexto, rejeicoes_txt, bug_id, caminho):
    """Gera patch cirúrgico via OpenCode."""
    # Por enquanto, retorna indicação de que precisa de intervenção manual
    return {
        "ok": False,
        "erro": "Patch cirurgico requer intervencao manual ou OpenCode",
        "bug_id": bug_id,
        "funcao": funcao_real,
    }


# ============================================================
# SELEÇÃO DE BUGS PARA CORREÇÃO
# ============================================================

def selecionar_bugs_para_correcao(veredito_salvo, pergunta):
    """Seleciona bugs para correção baseado no veredito e pergunta."""
    import re as _re

    if not veredito_salvo:
        return [], []

    texto_veredito = veredito_salvo.get("veredito", "")
    candidatos = veredito_salvo.get("candidatos_confirmados", [])

    if not candidatos:
        return [], []

    # Extrai IDs mencionados na pergunta
    ids_mencionados = set(_re.findall(r"\bC\d+\b", pergunta.upper()))

    # Se mencionou IDs específicos, seleciona esses
    if ids_mencionados:
        selecionados = [
            c for c in candidatos
            if c.get("id", "").upper() in ids_mencionados
        ]
    else:
        # Seleciona todos os confirmados
        selecionados = list(candidatos)

    ids = [c.get("id", "") for c in selecionados]

    return selecionados, ids
