"""
Golden AI - Operações MT5 Avançadas

Extraído de golden_ai.py (linhas 2471-2916).
Cópia segura, resolução de alvos, rotas determinísticas MT5.
"""

import os
import re
import shutil
import hashlib

from .context import CFG
from .utils import normalizar_texto_intencao
from .mt5 import caminho_seguro_mt5, ler_arquivo_mt5
from .files import caminho_seguro, criar_backup


# ============================================================
# LOCALIZAÇÃO DE ARQUIVOS MT5
# ============================================================

def extrair_nome_mt5_real(pergunta):
    """Extrai nome de arquivo .mq5/.mqh da pergunta."""
    match = re.search(r'(?i)([A-Za-z0-9_\-.\\\/]+\.mq5)', pergunta)
    if not match:
        return None
    return match.group(1).strip()


def localizar_mt5_real_por_nome(nome):
    """Localiza arquivo no MT5 real por nome parcial."""
    if not os.path.isdir(CFG.PASTA_MT5_EXPERTS):
        return None

    nome_lower = nome.lower().strip()

    for raiz, _, nomes in os.walk(CFG.PASTA_MT5_EXPERTS):
        for nome_arquivo in nomes:
            if nome_lower in nome_arquivo.lower():
                completo = os.path.join(raiz, nome_arquivo)
                return os.path.relpath(completo, CFG.PASTA_MT5_EXPERTS)

    return None


# ============================================================
# CÓPIA SEGURA MT5 → PROJETOS
# ============================================================

def copiar_ea_mt5_para_teste(nome, sufixo="_TESTE"):
    """
    Copia um .mq5/.mqh REAL do MT5 para C:\\GoldenAI\\projetos.
    Nunca altera o original.
    """
    relativo = localizar_mt5_real_por_nome(nome)

    if not relativo:
        return {"ok": False, "mensagem": f"Arquivo nao encontrado no MT5 real: {nome}"}

    origem = caminho_seguro_mt5(relativo)
    if origem is None or not os.path.isfile(origem):
        return {"ok": False, "mensagem": f"Origem invalida ou inexistente: {relativo}"}

    base = os.path.basename(origem)
    raiz, extensao = os.path.splitext(base)

    if extensao.lower() not in (".mq5", ".mqh"):
        return {"ok": False, "mensagem": "Somente arquivos .mq5 ou .mqh podem ser copiados."}

    destino_nome = f"{raiz}{sufixo}{extensao}"
    destino = caminho_seguro(destino_nome)

    if destino is None:
        return {"ok": False, "mensagem": "Destino de teste invalido."}

    try:
        os.makedirs(CFG.PASTA_PROJETOS, exist_ok=True)

        backup_existente = None
        if os.path.isfile(destino):
            backup_existente, erro_backup = criar_backup(destino_nome)
            if erro_backup:
                return {"ok": False, "mensagem": f"Falha ao criar backup: {erro_backup}"}

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
            return {"ok": False, "mensagem": "Falha de verificacao: hash da copia difere do original."}

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
                f"COPIA DE TESTE CRIADA E VERIFICADA.\n"
                f"Original MT5: {origem}\n"
                f"Copia teste: {destino}\n"
                f"SHA256 origem: {hash_origem}\n"
                f"SHA256 copia:  {hash_destino}\n"
                "CONFIRMACAO: o arquivo original do MetaTrader 5 nao foi alterado."
            ),
        }

    except Exception as erro:
        return {"ok": False, "mensagem": f"Erro ao copiar arquivo para testes: {erro}"}


# ============================================================
# EXTRAÇÃO DE CAMINHO MQL EXPLÍCITO
# ============================================================

def extrair_caminho_mql_explicito(pergunta):
    """Extrai caminho absoluto ou relativo de arquivo MQL da pergunta."""
    match = re.search(
        r'(?i)([A-Za-z]:\\[^"\'<>|]+\.mq5)',
        pergunta
    )
    if match:
        return match.group(1).strip()

    match = re.search(
        r'(?i)([A-Za-z0-9_\-\\.\/]+\.mq5)',
        pergunta
    )
    if match:
        return match.group(1).strip()

    return None


def classificar_alvo_mql(caminho):
    """Classifica um caminho MQL como MT5_REAL ou PROJETO_TESTE."""
    if not caminho:
        return {"ok": False, "tipo": "DESCONHECIDO"}

    caminho_abs = os.path.abspath(caminho)

    # Verifica se é MT5 real
    pasta_mt5 = os.path.abspath(CFG.PASTA_MT5_EXPERTS)
    try:
        if os.path.commonpath([caminho_abs, pasta_mt5]) == pasta_mt5:
            relativo = os.path.relpath(caminho_abs, pasta_mt5)
            return {"ok": True, "tipo": "MT5_REAL", "caminho": caminho_abs, "relativo_mt5": relativo}
    except ValueError:
        pass

    # Verifica se é projeto
    pasta_proj = os.path.abspath(CFG.PASTA_PROJETOS)
    try:
        if os.path.commonpath([caminho_abs, pasta_proj]) == pasta_proj:
            return {"ok": True, "tipo": "PROJETO_TESTE", "caminho": caminho_abs}
    except ValueError:
        pass

    return {"ok": False, "tipo": "FORA_DAS_AREAS_AUTORIZADAS"}


def resolver_alvo_mql(pergunta):
    """Resolve o alvo MQL mencionado na pergunta."""
    caminho = extrair_caminho_mql_explicito(pergunta)
    if not caminho:
        return {"ok": False}

    # Se é caminho absoluto
    if os.path.isabs(caminho):
        if os.path.isfile(caminho):
            return classificar_alvo_mql(caminho)
        return {"ok": False}

    # Se é nome relativo, busca no MT5 e em projetos
    # MT5
    relativo = localizar_mt5_real_por_nome(os.path.basename(caminho))
    if relativo:
        completo = caminho_seguro_mt5(relativo)
        if completo and os.path.isfile(completo):
            return {
                "ok": True,
                "tipo": "MT5_REAL",
                "caminho": completo,
                "relativo_mt5": relativo,
            }

    # Projetos
    seguro = caminho_seguro(caminho)
    if seguro and os.path.isfile(seguro):
        return {
            "ok": True,
            "tipo": "PROJETO_TESTE",
            "caminho": seguro,
        }

    return {"ok": False}


def confirmar_alvo_na_tela(alvo, operacao):
    """Confirma o alvo na tela (imprime informações)."""
    print()
    print("=" * 60)
    print(f"ALVO: {operacao}")
    print("=" * 60)
    print(f"Tipo: {alvo.get('tipo', '?')}")
    print(f"Arquivo: {alvo.get('nome', os.path.basename(alvo.get('caminho', '?')))}")
    print(f"Caminho: {alvo.get('caminho', '?')}")
    if alvo.get("tipo") == "MT5_REAL":
        print("PROTECAO: somente leitura no MT5 real.")
    elif alvo.get("tipo") == "PROJETO_TESTE":
        print("PROTECAO: edicao permitida apenas nesta copia.")
    print("=" * 60)
    print()


def ler_alvo_resolvido(alvo):
    """Lê o conteúdo de um alvo resolvido."""
    if not alvo or not alvo.get("ok") or not alvo.get("caminho"):
        return None, "Alvo invalido."

    caminho = alvo["caminho"]
    if not os.path.isfile(caminho):
        return None, f"Arquivo nao encontrado: {caminho}"

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except Exception as erro:
        return None, f"Erro ao ler: {erro}"
