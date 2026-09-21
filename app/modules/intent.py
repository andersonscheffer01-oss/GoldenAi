"""
Golden AI - Classificação de Intenção

Extraído de golden_ai.py (linhas 4781-5070).
Determina o tipo de operação que o usuário quer realizar.
"""

import os
import re

from .context import CFG
from .utils import normalizar_texto_intencao


# ============================================================
# CLASSIFICAÇÃO DE INTENÇÃO DO USUÁRIO
# ============================================================

def classificar_intencao_usuario(pergunta):
    """
    Classifica a intenção do usuário como LEITURA, ESCRITA ou CONVERSA.
    Usado pelo roteador principal para decidir o caminho.
    """
    texto = normalizar_texto_intencao(pergunta)

    # Bloqueio explícito de escrita
    termos_bloqueio = (
        "nao altere", "não altere", "nao modifique", "não modifique",
        "nao mexa", "não mexa", "somente analise", "apenas analise",
        "somente leia", "apenas leia", "sem alterar", "sem modificar",
    )
    bloqueio_escrita = any(t in texto for t in termos_bloqueio)

    # Intenção de leitura
    termos_leitura = (
        "leia", "ler", "analise", "analisar", "revise", "revisar",
        "verifique", "verificar", "explique", "explicar", "audite",
        "auditar", "bug", "bugs", "erro", "erros", "problema", "problemas",
        "risco", "riscos", "o que esse robo faz", "o que este robo faz",
    )
    intencao_leitura = any(t in texto for t in termos_leitura)

    # Intenção de edição
    termos_edicao = (
        "corrija", "corrigir", "conserte", "consertar", "modifique",
        "modificar", "altere", "alterar", "adicione", "adicionar",
        "remova", "remover", "substitua", "substituir", "reescreva",
        "reescrever", "implemente", "implementar",
    )
    intencao_edicao = any(t in texto for t in termos_edicao)

    if bloqueio_escrita:
        return "LEITURA"
    if intencao_edicao and not bloqueio_escrita:
        return "ESCRITA"
    if intencao_leitura:
        return "LEITURA"

    return "CONVERSA"


def pedido_proibe_escrita(pergunta):
    """Verifica se o pedido proibe explicitamente escrita."""
    texto = normalizar_texto_intencao(pergunta)
    return any(t in texto for t in (
        "nao altere", "não altere", "nao modifique", "não modifique",
        "somente analise", "apenas analise", "sem alterar",
    ))


def normalizar_intencao_conversa(pergunta):
    """Normaliza a intenção para uso no roteamento de conversa."""
    return classificar_intencao_usuario(pergunta)


def usuario_mudou_para_conversa_geral(pergunta):
    """Detecta se o usuário mudou para uma pergunta de conversa geral."""
    texto = normalizar_texto_intencao(pergunta)

    termos_conversa = (
        "explique", "o que e", "o que é", "como funciona", "qual a diferenca",
        "me fale sobre", "conte sobre", "me explique", "sobre o que",
    )

    return any(t in texto for t in termos_conversa)


def pergunta_pede_contexto_tecnico(pergunta):
    """Verifica se a pergunta pede contexto técnico (arquivo, código, etc)."""
    texto = normalizar_texto_intencao(pergunta)

    termos_tecnicos = (
        "arquivo", "codigo", "funcao", "classe", "metodo", "variavel",
        "linha", "compilar", "compilacao", "erro", "bug", "robo",
        "mq5", "mqh", "python", "script", "modulo", "import",
        "parametro", "argumento", "retorna", "loop", "if", "while",
        "for", "switch", "case", "struct", "enum",
    )

    return any(t in texto for t in termos_tecnicos)


def pergunta_pede_ferramenta_local(pergunta):
    """Verifica se a pergunta pede uma ferramenta local (listar, ler, etc)."""
    texto = normalizar_texto_intencao(pergunta)

    termos_ferramenta = (
        "liste", "listar", "abra", "abrir", "leia", "ler",
        "mostre", "mostrar", "exiba", "exibir", "execute",
        "buque", "buscar", "encontre", "encontrar", "delete",
        "deletar", "remova", "remover",
    )

    return any(t in texto for t in termos_ferramenta)


def pergunta_pede_memoria(pergunta):
    """Verifica se a pergunta pede uso da memória científica."""
    texto = normalizar_texto_intencao(pergunta)

    termos_memoria = (
        "memoria", "memorize", "grave na memoria", "lembre disso",
        "guarde na memoria", "conhecimento", "evidencia", "fonte",
        "experimento", "hipotese", "teoria",
    )

    return any(t in texto for t in termos_memoria)


def pergunta_pede_market(pergunta):
    """Verifica se a pergunta pede análise de mercado."""
    texto = normalizar_texto_intencao(pergunta)

    termos_market = (
        "mercado", "analise de mercado", "tendencia", "suporte",
        "resistencia", "volume", "indicador", "regime", "sinal",
        "backtest", "estrategia", "symbol", "timeframe",
    )

    return any(t in texto for t in termos_market)


def pergunta_pede_quant(pergunta):
    """Verifica se a pergunta pede operações quant."""
    texto = normalizar_texto_intencao(pergunta)

    termos_quant = (
        "backtest", "equity", "drawdown", "sharpe", "retorno",
        "rentabilidade", "metricas", "trade", "trades", "operacao",
        "operacoes", "capital", "posicao",
    )

    return any(t in texto for t in termos_quant)


def pergunta_pede_orquestrador(pergunta):
    """Verifica se a pergunta pede orquestração de agentes."""
    texto = normalizar_texto_intencao(pergunta)

    termos_orq = (
        "orquestr", "agente", "tarefa", "delegar", "executar tarefa",
    )

    return any(t in texto for t in termos_orq)
