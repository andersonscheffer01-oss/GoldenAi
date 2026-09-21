"""
Golden AI - Auditoria Determinística

Extraído de golden_ai.py (linhas 3096-4180 + 4467-5787).
Chat determinístico, extração JSON, canonicalização de candidatos.
"""

import os
import re
import json

from .context import CFG, SERVICES


# ============================================================
# CHAMADA DETERMINÍSTICA AO MODELO
# ============================================================

def chat_deterministico(messages, seed):
    """
    Chamada local com parâmetros fixos para reduzir variação.
    V1.9.8.4: top_p=0 + min_p=0 garante geração determinística real.
    """
    from ollama import chat
    from .context import obter_modelo

    return chat(
        model=obter_modelo("CODER"),
        messages=messages,
        options={
            "temperature": 0.0,
            "seed": int(seed),
            "top_p": 0.0,
            "top_k": 1,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
        },
    )


# ============================================================
# EXTRAÇÃO DE JSON DO MODELO
# ============================================================

def extrair_json_modelo(texto):
    """Aceita JSON puro ou JSON dentro de bloco Markdown."""
    if not isinstance(texto, str):
        return None

    t = texto.strip()

    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t).strip()

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


# ============================================================
# CANONICALIZAÇÃO DE CANDIDATOS
# ============================================================

def _norm_identificador(valor):
    """Normaliza identificador para comparação."""
    return re.sub(r"[^a-z0-9_]", "", str(valor or "").lower())


def _intervalo_linhas(valor):
    """Extrai intervalo de linhas (min, max)."""
    numeros = [int(x) for x in re.findall(r"\d+", str(valor or ""))]
    if not numeros:
        return 0, 0
    return min(numeros), max(numeros)


def _categoria_candidato(item):
    """Classifica um candidato em categoria."""
    categorias_validas = {
        "CALCULO_LOTE", "NORMALIZACAO_LOTE", "PRECO_STOP", "TRAILING",
        "BREAK_EVEN", "POSICAO_ORDEM", "SPREAD", "INDICADOR",
        "VALIDACAO_PARAMETRO", "OUTRO",
    }

    categoria = str(item.get("categoria", "")).strip().upper()
    if categoria in categorias_validas:
        return categoria

    texto = " ".join([
        str(item.get("funcao", "")),
        str(item.get("problema", "")),
        str(item.get("evidencia", "")),
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
    if "stop loss" in texto or "take profit" in texto:
        return "PRECO_STOP"
    if "position" in texto or "order" in texto or "posi" in texto:
        return "POSICAO_ORDEM"
    if "ema" in texto or "atr" in texto or "vwap" in texto:
        return "INDICADOR"
    if "valid" in texto or "zero" in texto:
        return "VALIDACAO_PARAMETRO"

    return "OUTRO"


def canonicalizar_candidatos(dados):
    """
    Canonicaliza candidatos sem exigir igualdade textual.
    Identidade primária: função + região de linhas + categoria + símbolo.
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
        problema = " ".join(str(item.get("problema", "")).split()).strip()
        evidencia = " ".join(str(item.get("evidencia", "")).split()).strip()
        simbolo = str(item.get("simbolo_chave", "")).strip()
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
            "evidencia": evidencia,
        })

    return saida


def _intervalos_compativeis(a, b, tolerancia=12):
    """Verifica se dois intervalos de linhas são compatíveis."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    ini_a = a.get("linha_ini", 0)
    fim_a = a.get("linha_fim", 0)
    ini_b = b.get("linha_ini", 0)
    fim_b = b.get("linha_fim", 0)
    return abs(ini_a - ini_b) <= tolerancia and abs(fim_a - fim_b) <= tolerancia


def candidatos_equivalentes(a, b):
    """Verifica se dois candidatos são equivalentes."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False

    # Mesma função e categoria
    if a.get("funcao_norm") != b.get("funcao_norm"):
        return False
    if a.get("categoria") != b.get("categoria"):
        return False

    # Intervalos compatíveis
    if not _intervalos_compativeis(a, b):
        return False

    # Mesmo símbolo-chave (se definido)
    sym_a = a.get("simbolo_norm", "")
    sym_b = b.get("simbolo_norm", "")
    if sym_a and sym_b and sym_a != sym_b:
        return False

    return True


def comparar_e_fundir_candidatos(lista_a, lista_b):
    """Compara duas listas de candidatos e funde equivalentes."""
    if not lista_a:
        return list(lista_b or [])
    if not lista_b:
        return list(lista_a or [])

    fundidos = list(lista_a)
    usados_b = set()

    for b in lista_b:
        encontrou = False
        for i, a in enumerate(fundidos):
            if candidatos_equivalentes(a, b):
                # Mantém o mais detalhado
                if len(b.get("evidencia", "")) > len(a.get("evidencia", "")):
                    fundidos[i] = b
                usados_b.add(id(b))
                encontrou = True
                break
        if not encontrou:
            fundidos.append(b)
            usados_b.add(id(b))

    return fundidos


def assinatura_estrutural(candidatos):
    """Gera assinatura estrutural para comparação."""
    partes = []
    for c in sorted(candidatos, key=lambda x: (x.get("funcao_norm", ""), x.get("linha_ini", 0))):
        partes.append(f"{c.get('funcao_norm')}:{c.get('categoria')}:{c.get('linha_ini')}-{c.get('linha_fim')}")
    return "|".join(partes)


# ============================================================
# VALIDAÇÃO DE VEREDITO
# ============================================================

def canonicalizar_validacao(dados):
    """Canonicaliza dados de validação."""
    if not isinstance(dados, dict):
        return dados

    resultado = dict(dados)

    # Normaliza candidatos
    if "candidatos_confirmados" in resultado:
        resultado["candidatos_confirmados"] = canonicalizar_candidatos(
            {"candidatos": resultado["candidatos_confirmados"]}
        )

    return resultado
