"""
Golden AI - Main Loop

Extraído de golden_ai.py (linhas 8800-9842).
Loop principal de conversação com roteamento de intenção.
"""

import os
import re
import json

from .context import CFG, SESSION, init_core
from .utils import normalizar_texto_intencao, extrair_studio_context_path
from .intent import (
    classificar_intencao_usuario, pergunta_pede_contexto_tecnico,
    pergunta_pede_ferramenta_local, pergunta_pede_market,
    pergunta_pede_quant, pergunta_pede_memoria, pergunta_pede_media,
    pergunta_pede_orquestrador, pergunta_pede_internet,
)
from .files import caminho_seguro
from .panel import executar_painel
from .internet import responder_internet_chat
from .market_chat import responder_market_chat
from .memory_chat import responder_memoria_chat
from .media_chat import responder_media_chat
from .quant_chat import responder_quant_chat


def executar_agente_normal(pergunta, permitir_ferramentas=True):
    """Executa o agente normal com Ollama."""
    from ollama import chat
    from .context import obter_modelo

    modelo = obter_modelo("CODER")

    messages = [{"role": "user", "content": pergunta}]

    try:
        response = chat(model=modelo, messages=messages)
        resposta = response.get("message", {}).get("content", "")

        SESSION.historico.append({"role": "user", "content": pergunta})
        SESSION.historico.append({"role": "assistant", "content": resposta})

        print()
        print("Golden AI:")
        print(resposta)
        print()

        return resposta

    except Exception as erro:
        print(f"Erro ao executar agente: {erro}")
        return f"Erro: {erro}"


def loop_principal():
    """Loop principal de conversação."""
    print("=" * 76)
    print("GOLDEN AI - AGENTE V1.9.8.3")
    print("MT5 REAL SOMENTE LEITURA | AUTOCORRECAO TESTE | METAEDITOR | ROLLBACK")
    print("=" * 76)
    print()
    print("Digite 'sair' para encerrar.")
    print("Digite 'painel' para ver todos os comandos disponiveis.")
    print()

    # Restaura estado anterior
    from .report import carregar_estado_alvo_auditoria, interpretar_veredito_final
    SESSION.arquivo_alvo_atual, SESSION.ultimo_veredito_auditoria = carregar_estado_alvo_auditoria()

    if SESSION.arquivo_alvo_atual:
        print("[GoldenAI V1.9.8.3] Estado anterior restaurado.")
        print(f"Arquivo alvo: {SESSION.arquivo_alvo_atual.get('caminho')}")

        if SESSION.ultimo_veredito_auditoria:
            autorizado, quantidade = interpretar_veredito_final(
                SESSION.ultimo_veredito_auditoria.get("veredito", "")
            )
            SESSION.ultimo_veredito_auditoria["autorizado"] = autorizado
            SESSION.ultimo_veredito_auditoria["quantidade"] = quantidade
            print(f"Veredito restaurado: {'AUTORIZADO' if autorizado else 'NAO AUTORIZADO'}")
            print(f"Bugs confirmados restaurados: {quantidade}")
        print()

    while True:
        pergunta = input("Voce: ").strip()

        if pergunta.lower() == "sair":
            print()
            print("Golden AI encerrada.")
            break

        if not pergunta:
            continue

        pergunta_lower = pergunta.lower()

        # Painel de comandos
        if executar_painel(pergunta, SESSION.arquivo_alvo_atual, SESSION.ultimo_veredito_auditoria):
            continue

        # Roteamento por intenção
        if pergunta_pede_market(pergunta):
            responder_market_chat(pergunta, SESSION.historico, None)
            continue

        if pergunta_pede_quant(pergunta):
            responder_quant_chat(pergunta, SESSION.historico, None)
            continue

        if pergunta_pede_media(pergunta):
            responder_media_chat(pergunta, SESSION.historico, None)
            continue

        if pergunta_pede_orquestrador(pergunta):
            responder_orquestrador_chat(pergunta)
            continue

        if pergunta_pede_memoria(pergunta):
            responder_memoria_chat(pergunta, SESSION.historico, None)
            continue

        if pergunta_pede_internet(pergunta):
            responder_internet_chat(pergunta, SESSION.historico, None)
            continue

        # Agente normal
        executar_agente_normal(pergunta)


def responder_orquestrador_chat(pergunta):
    """Delega tarefa a agentes especializados."""
    print()
    print("[GoldenAI] Delegando para agente orquestrador...")
    executar_agente_normal(pergunta)
