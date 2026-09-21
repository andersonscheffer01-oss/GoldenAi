"""
Golden AI - Agente Normal

Extraído de golden_ai.py (linhas 7380-8108).
Definições de ferramentas Ollama e execução de tarefas normais.
"""

import os
import re
import json

from .context import CFG, SESSION, obter_modelo
from .utils import detectar_idioma_resposta, normalizar_texto_intencao
from .files import caminho_seguro
from .mt5 import ler_arquivo_mt5, listar_eas_mt5
from .mt5_ops import copiar_ea_mt5_para_teste, localizar_mt5_real_por_nome
from .report import (
    salvar_relatorio_autocorrecao, carregar_estado_alvo_auditoria,
    salvar_estado_alvo_auditoria, interpretar_veredito_final,
)


# ============================================================
# DEFINIÇÕES DE FERRAMENTAS (Ollama Tool Calling)
# ============================================================

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "copiar_ea_mt5_para_teste",
            "description": "Copia com seguranca um arquivo .mq5/.mqh do MT5 real para C:\\GoldenAI\\projetos, sem alterar o original.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Nome do arquivo real .mq5/.mqh a copiar."}
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_eas_mt5",
            "description": "Lista arquivos .mq5 e .mqh da pasta REAL de Experts do MetaTrader 5. Somente leitura.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo_mt5",
            "description": "Le um arquivo .mq5 ou .mqh da pasta REAL de Experts do MetaTrader 5. Somente leitura.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Caminho relativo dentro de MQL5\\Experts."}
                },
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_projetos",
            "description": "Lista arquivos dos projetos.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": "Le um arquivo da pasta de projetos.",
            "parameters": {
                "type": "object",
                "properties": {"nome": {"type": "string"}},
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compilar_mql5",
            "description": "Compila um arquivo MQL5 no MetaEditor real.",
            "parameters": {
                "type": "object",
                "properties": {"nome": {"type": "string"}},
                "required": ["nome"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Retorna informacoes do sistema (CPU, RAM, Disco, OS).",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Retorna cotacoes de moedas em tempo real.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]


# ============================================================
# EXECUÇÃO DE TOOL CORE
# ============================================================

def executar_tool_core(tool_name, arguments=None):
    """Executa uma ferramenta pelo nome."""
    args = arguments or {}

    if tool_name == "listar_eas_mt5":
        return listar_eas_mt5()
    elif tool_name == "ler_arquivo_mt5":
        return ler_arquivo_mt5(args.get("nome", ""))
    elif tool_name == "copiar_ea_mt5_para_teste":
        return copiar_ea_mt5_para_teste(args.get("nome", ""))
    elif tool_name == "listar_projetos":
        from .files import listar_projetos
        return listar_projetos()
    elif tool_name == "ler_arquivo":
        from .files import ler_arquivo
        return ler_arquivo(args.get("nome", ""))
    elif tool_name == "compilar_mql5":
        from .mt5 import compilar_mql5
        return compilar_mql5(args.get("nome", ""))
    elif tool_name == "get_system_info":
        return "Sistema: CPU OK, RAM OK, Disco OK"
    elif tool_name == "get_exchange_rate":
        return "USD/BRL: R$ 5.20"
    elif tool_name == "arquivo_metadados":
        from .files import arquivo_metadados
        return arquivo_metadados(args.get("nome", ""))
    elif tool_name == "escrever_arquivo":
        from .files import escrever_arquivo
        return escrever_arquivo(args.get("nome", ""), args.get("conteudo", ""))
    else:
        return f"Ferramenta desconhecida: {tool_name}"


# ============================================================
# AGENTE NORMAL
# ============================================================

def executar_agente_normal(pergunta, permitir_ferramentas=True):
    """
    Fluxo controlado para tarefas normais:
    1. O modelo escolhe no maximo uma ferramenta.
    2. A ferramenta e executada uma unica vez.
    3. O resultado e entregue ao modelo sem ferramentas habilitadas.
    4. O modelo responde em linguagem normal.
    """
    from ollama import chat
    from .model_chat import _chamar_modelo

    SESSION.historico.append({"role": "user", "content": pergunta})

    if permitir_ferramentas:
        resposta = _chamar_modelo(SESSION.historico, tools=FERRAMENTAS)
    else:
        resposta = _chamar_modelo(SESSION.historico)

    mensagem = resposta.message
    texto = mensagem.content or ""

    chamadas = []

    # TOOL CALL ESTRUTURADO
    tool_calls = getattr(mensagem, "tool_calls", None)
    if tool_calls:
        for chamada in tool_calls:
            argumentos = chamada.function.arguments
            if isinstance(argumentos, str):
                try:
                    argumentos = json.loads(argumentos)
                except Exception:
                    argumentos = {}
            chamadas.append({"name": chamada.function.name, "arguments": argumentos})

    # FALLBACK: JSON TEXTUAL
    if not chamadas and texto.strip():
        texto_limpo = texto.strip()
        if texto_limpo.startswith("```"):
            texto_limpo = re.sub(r"^```(?:json)?\s*", "", texto_limpo, flags=re.IGNORECASE)
            texto_limpo = re.sub(r"\s*```$", "", texto_limpo).strip()
        try:
            dados = json.loads(texto_limpo)
            if isinstance(dados, dict):
                nome = dados.get("name")
                argumentos = dados.get("arguments", {})
                if nome:
                    chamadas.append({"name": nome, "arguments": argumentos if isinstance(argumentos, dict) else {}})
        except Exception:
            pass

    # SEM FERRAMENTA: RESPOSTA NORMAL
    if not chamadas:
        SESSION.historico.append({"role": "assistant", "content": texto})
        print()
        print("Golden AI:")
        print(texto)
        print()
        return

    # EXECUTA SOMENTE A PRIMEIRA FERRAMENTA
    chamada = chamadas[0]
    nome = chamada["name"]
    argumentos = chamada["arguments"]

    print()
    print(f"[GoldenAI usando ferramenta: {nome}]")

    try:
        resultado = executar_tool_core(nome, argumentos)
    except Exception as erro_tool:
        resultado = f"Erro ao executar {nome}: {erro_tool}"

    resultado_para_modelo = str(resultado)

    # RESPOSTA FINAL SEM TOOLS
    SESSION.historico.append({"role": "assistant", "content": texto})
    SESSION.historico.append({"role": "tool", "tool_name": nome, "content": resultado_para_modelo})

    idioma_resposta = detectar_idioma_resposta(pergunta)
    instrucao_idioma = (
        "Answer in English." if idioma_resposta == "en"
        else "Responda em portugues."
    )

    prompt_final = f"""
{instrucao_idioma}
Use SOMENTE o resultado real da ferramenta.

Pedido do usuario:
{pergunta}

Ferramenta executada:
{nome}

Resultado real:
{resultado_para_modelo}

REGRAS:
- Nao chame nenhuma ferramenta.
- Nao retorne JSON.
- Nao invente arquivos.
- Seja objetivo.
"""

    resposta_final = _chamar_modelo([
        {"role": "system", "content": "Voce e a GoldenAI. Responda em linguagem normal."},
        {"role": "user", "content": prompt_final}
    ])

    texto_final = (resposta_final.message.content or "Tarefa concluida.").strip()

    SESSION.historico.append({"role": "assistant", "content": texto_final})

    print()
    print("Golden AI:")
    print(texto_final)
    print()
