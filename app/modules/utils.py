"""
Golden AI - Funções Utilitárias

Extraído de golden_ai.py (linhas 151-314).
Funções de normalização, idioma, hashing e extração de código.
"""

import os
import re
import hashlib
import unicodedata

from .context import CFG


# ============================================================
# CAMINHO SEGURO
# ============================================================

def caminho_seguro(nome):
    """Valida se o nome está dentro da pasta autorizada (PASTA_PROJETOS)."""
    if not isinstance(nome, str) or not nome.strip():
        return None

    caminho = os.path.abspath(
        os.path.join(CFG.PASTA_PROJETOS, nome.strip())
    )
    pasta = os.path.abspath(CFG.PASTA_PROJETOS)

    try:
        comum = os.path.commonpath([caminho, pasta])
    except ValueError:
        return None

    if comum != pasta:
        return None

    return caminho


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

def normalizar_texto_intencao(texto):
    """Remove acentos e normaliza para minúsculas."""
    texto = str(texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return texto


def detectar_idioma_resposta(pergunta):
    """Detecta se a resposta deve ser em PT ou EN."""
    texto = normalizar_texto_intencao(pergunta)

    if any(m in texto for m in ("responda em ingles", "responder em ingles", "answer in english", "in english")):
        return "en"
    if any(m in texto for m in ("responda em portugues", "responder em portugues", "em portugues", "in portuguese")):
        return "pt"

    termos_pt = (
        "quantas", "linhas", "codigo", "robo", "arquivo", "qual", "tamanho",
        "extensao", "nao", "altere", "procure", "possiveis", "problemas",
        "o que", "faz", "explique", "analise", "detalhadamente",
    )
    termos_en = (
        "what", "does", "this", "code", "file", "how many", "lines", "size",
        "extension", "explain", "analyze", "do not change",
    )

    pt_score = sum(1 for t in termos_pt if t in texto)
    en_score = sum(1 for t in termos_en if t in texto)
    return "en" if en_score > pt_score else "pt"


def normalizar_texto_v110(texto):
    """Normalização para o router V1.10."""
    return unicodedata.normalize(
        "NFKD", (texto or "").lower()
    ).encode("ascii", "ignore").decode("ascii")


# ============================================================
# CLASSIFICAÇÃO DE INTENÇÃO CONVERSACIONAL
# ============================================================

def classificar_intencao_conversacional(pergunta):
    """Classifica a intenção do usuário em categorias."""
    texto = normalizar_texto_intencao(pergunta)

    if any(t in texto for t in ("corrija", "corrigir", "conserte", "modifique", "altere", "implemente", "apply patch", "fix this code")):
        if any(t in texto for t in ("nao altere", "nao modifique", "do not change", "sem alterar")):
            return "FILE_ANALYSIS"
        return "CODING_CHANGE"

    if any(t in texto for t in ("quantas linhas", "numero de linhas", "contar linhas", "linhas tem", "tamanho desse arquivo", "tamanho do arquivo", "qual o tamanho", "extensao", "extension", "file size", "how many lines")):
        return "FILE_METADATA"

    if any(t in texto for t in ("analise", "analisar", "audite", "revise", "procure possiveis problemas", "possiveis problemas", "bug", "bugs", "problema", "problemas")):
        return "FILE_ANALYSIS"

    if any(t in texto for t in ("o que esse", "o que este", "what does this", "explique", "explicar", "faz", "funciona")):
        return "FILE_EXPLANATION"

    if any(t in texto for t in ("leia", "ler", "mostre o conteudo", "show content")):
        return "FILE_READ"

    return "GENERAL_CONVERSATION"


# ============================================================
# EXTRAÇÃO DE CONTEXTO STUDIO
# ============================================================

def extrair_studio_context_path(pergunta):
    """Extrai o caminho do contexto do Studio da mensagem."""
    match = re.search(r"(?is)CURRENT_CONTEXT_PATH=(.+)", str(pergunta or ""))
    if not match:
        return None

    valor = match.group(1)
    for marcador in (
        "\nCURRENT_CONTEXT_NAME=", "\rCURRENT_CONTEXT_NAME=",
        " CURRENT_CONTEXT_NAME=", "CURRENT_CONTEXT_NAME=",
        "\nUSER_INTENT=", " USER_INTENT=", "USER_INTENT=",
        "\nRESPONSE_LANGUAGE=", " RESPONSE_LANGUAGE=", "RESPONSE_LANGUAGE=",
        "\nREAD_ONLY=", " READ_ONLY=", "READ_ONLY=",
        "[/STUDIO_CONTEXT]",
    ):
        pos = valor.find(marcador)
        if pos >= 0:
            valor = valor[:pos]

    return valor.strip()


# ============================================================
# HASHING E EXTRAÇÃO DE CÓDIGO
# ============================================================

def hash_texto(texto):
    """Gera hash SHA-256 de um texto."""
    return hashlib.sha256(
        texto.encode("utf-8", errors="replace")
    ).hexdigest()


def extrair_codigo(texto):
    """Extrai código de um bloco Markdown."""
    if not texto:
        return ""

    texto = texto.strip()

    match = re.search(
        r"```(?:mql5|mq5|cpp|c\+\+|python|py|javascript|js|java|csharp|cs|ruby|go|rust|php|html|css|sql|json|yaml|sh|bash|powershell|ps1)?\s*([\s\S]*?)```",
        texto,
        re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    return texto


def extrair_nome_mq5(pergunta):
    """Extrai o nome de um arquivo .mq5 da pergunta."""
    if not isinstance(pergunta, str):
        return None

    match = re.search(
        r'(?i)([A-Za-z0-9_\-.\\\/]+\.mq5)',
        pergunta
    )

    if not match:
        return None

    nome = match.group(1).strip()

    if os.path.isabs(nome):
        caminho = os.path.abspath(nome)
        pasta = os.path.abspath(CFG.PASTA_PROJETOS)

        try:
            comum = os.path.commonpath([caminho, pasta])
        except ValueError:
            return None

        if comum != pasta:
            return None

        nome = os.path.relpath(caminho, pasta)

    return nome


def extrair_query_busca(pergunta):
    """Extrai a query de busca removendo verbos de comando."""
    texto = normalizar_texto_v110(pergunta)
    for palavra in (
        "pesquise na internet", "pesquise na web", "pesquise online",
        "busque na internet", "busque na web", "buscar na web",
        "search the web", "pesquise esse erro", "pesquise este erro",
        "procure no google", "procure na internet", "pesquise", "busque",
        "procure", "sobre", "a respeito de",
    ):
        texto = texto.replace(palavra, "")

    texto = texto.replace("?", "").replace("!", "").strip(" .,;:'\"")
    return texto[:200] or pergunta.strip()[:200]


def _formatar_bytes(valor):
    """Formata bytes para formato legível."""
    if valor < 1024:
        return f"{valor} B"
    elif valor < 1024 * 1024:
        return f"{valor / 1024:.1f} KB"
    elif valor < 1024 * 1024 * 1024:
        return f"{valor / (1024 * 1024):.1f} MB"
    else:
        return f"{valor / (1024 * 1024 * 1024):.1f} GB"


def _weekday_pt(nome):
    """Converte nome do dia para PT."""
    mapa = {
        "Monday": "segunda-feira", "Tuesday": "terça-feira",
        "Wednesday": "quarta-feira", "Thursday": "quinta-feira",
        "Friday": "sexta-feira", "Saturday": "sábado",
        "Sunday": "domingo",
    }
    return mapa.get(nome, nome)
