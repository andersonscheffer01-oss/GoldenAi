"""
Golden AI - Operações de Arquivo

Extraído de golden_ai.py (linhas 390-565 + 1681-1785).
Listagem, leitura, escrita, backup e metadados de arquivos.
"""

import os
import shutil
from datetime import datetime

from .context import CFG
from .utils import (
    caminho_seguro,
    detectar_idioma_resposta,
    normalizar_texto_intencao,
    classificar_intencao_conversacional,
    extrair_studio_context_path,
)


def nome_para_projetos(caminho_ou_nome):
    """Converte caminho absoluto para relativo à pasta de projetos."""
    texto = str(caminho_ou_nome or "").strip()
    if not texto:
        return ""
    if os.path.isabs(texto):
        pasta = os.path.abspath(CFG.PASTA_PROJETOS)
        caminho = os.path.abspath(texto)
        try:
            if os.path.commonpath([caminho, pasta]) == pasta:
                return os.path.relpath(caminho, pasta)
        except ValueError:
            return texto
    return texto


# ============================================================
# LISTAGEM E LEITURA
# ============================================================

def listar_projetos():
    """Lista todos os arquivos na pasta de projetos."""
    if not os.path.exists(CFG.PASTA_PROJETOS):
        return "A pasta de projetos nao existe."

    arquivos = []

    for raiz, _, nomes in os.walk(CFG.PASTA_PROJETOS):
        for nome in nomes:
            completo = os.path.join(raiz, nome)
            relativo = os.path.relpath(completo, CFG.PASTA_PROJETOS)
            arquivos.append(relativo)

    if not arquivos:
        return "Nenhum arquivo encontrado."

    arquivos.sort()
    return "\n".join(arquivos)


def ler_arquivo(nome):
    """Lê o conteúdo de um arquivo autorizado. Retorna (conteudo, erro)."""
    caminho = caminho_seguro(nome)

    if caminho is None:
        return None, "Acesso negado ou nome de arquivo invalido."

    if not os.path.isfile(caminho):
        return None, f"Arquivo nao encontrado: {nome}"

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except Exception as erro:
        return None, f"Erro ao ler arquivo: {erro}"


# ============================================================
# METADADOS
# ============================================================

def arquivo_metadados(nome):
    """Obtém metadados de um arquivo (linhas, tamanho, extensão, etc)."""
    caminho = caminho_seguro(nome)

    if caminho is None:
        return {"ok": False, "erro": "Arquivo fora da pasta autorizada ou nome invalido."}

    if not os.path.exists(caminho) or not os.path.isfile(caminho):
        return {"ok": False, "erro": "Arquivo nao encontrado.", "caminho": caminho}

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            linhas = f.read().splitlines()
        stat = os.stat(caminho)
        return {
            "ok": True,
            "nome": os.path.basename(caminho),
            "caminho": caminho,
            "extensao": os.path.splitext(caminho)[1],
            "tamanho_bytes": stat.st_size,
            "linhas": len(linhas),
            "linhas_nao_vazias": sum(1 for l in linhas if l.strip()),
            "modificado_em": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
    except Exception as erro:
        return {"ok": False, "erro": f"Erro ao obter metadados: {erro}", "caminho": caminho}


def formatar_resposta_metadados(pergunta, metadados):
    """Formata a resposta de metadados de acordo com a pergunta."""
    idioma = detectar_idioma_resposta(pergunta)
    texto = normalizar_texto_intencao(pergunta)

    if not isinstance(metadados, dict) or not metadados.get("ok"):
        erro = metadados.get("erro", "nao consegui obter metadados") if isinstance(metadados, dict) else str(metadados)
        if idioma == "en":
            return f"I could not read the selected file metadata: {erro}"
        return f"Nao consegui ler os metadados do arquivo selecionado: {erro}"

    nome = metadados.get("nome")

    if any(t in texto for t in ("quantas linhas", "numero de linhas", "contar linhas", "linhas tem", "how many lines")):
        return f"O arquivo {nome} possui {metadados.get('linhas')} linhas." if idioma == "pt" else f"The file {nome} has {metadados.get('linhas')} lines."

    if any(t in texto for t in ("linhas nao vazias", "non-empty")):
        return f"O arquivo {nome} possui {metadados.get('linhas_nao_vazias')} linhas nao vazias." if idioma == "pt" else f"The file {nome} has {metadados.get('linhas_nao_vazias')} non-empty lines."

    if any(t in texto for t in ("extensao", "extension")):
        return f"A extensao do arquivo e {metadados.get('extensao')}." if idioma == "pt" else f"The file extension is {metadados.get('extensao')}."

    if any(t in texto for t in ("tamanho", "size", "bytes")):
        return f"O arquivo {nome} tem {metadados.get('tamanho_bytes')} bytes." if idioma == "pt" else f"The file {nome} is {metadados.get('tamanho_bytes')} bytes."

    if idioma == "en":
        return f"File {nome}: {metadados.get('linhas')} lines, {metadados.get('tamanho_bytes')} bytes, extension {metadados.get('extensao')}."

    return f"Arquivo {nome}: {metadados.get('linhas')} linhas, {metadados.get('tamanho_bytes')} bytes, extensao {metadados.get('extensao')}."


# ============================================================
# BACKUP E ESCRITA
# ============================================================

def criar_backup(nome):
    """Cria backup de um arquivo antes de modificar."""
    caminho = caminho_seguro(nome)

    if caminho is None:
        return None, "Acesso negado."

    if not os.path.isfile(caminho):
        return None, f"Arquivo nao encontrado: {nome}"

    try:
        os.makedirs(CFG.PASTA_BACKUPS, exist_ok=True)

        base = os.path.basename(caminho)
        raiz, extensao = os.path.splitext(base)
        horario = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destino = os.path.join(CFG.PASTA_BACKUPS, f"{raiz}_BACKUP_{horario}{extensao}")

        shutil.copy2(caminho, destino)
        return destino, None

    except Exception as erro:
        return None, f"Erro ao criar backup: {erro}"


def restaurar_backup(nome, backup):
    """Restaura um arquivo a partir de um backup."""
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
    """Escreve conteúdo em um arquivo, criando backup automático."""
    caminho = caminho_seguro(nome)

    if caminho is None:
        return False, None, "Acesso negado."

    if not isinstance(conteudo, str):
        return False, None, "Conteudo invalido."

    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)

        atual = None
        if os.path.isfile(caminho):
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                atual = f.read()
            if atual == conteudo:
                return False, None, "SEM ALTERACAO"

        backup = None
        if atual is not None:
            backup, erro_backup = criar_backup(nome)
            if erro_backup:
                return False, None, erro_backup

        with open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)

        return True, backup, f"Arquivo salvo: {caminho}"

    except Exception as erro:
        return False, None, f"Erro ao escrever: {erro}"
