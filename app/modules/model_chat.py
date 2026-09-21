"""
Golden AI - Chamada ao Modelo

Extraído de golden_ai.py (linhas 4200-4486).
Timeout, fallback NVIDIA→Ollama, tool calls, veredito.
"""

import re
import json
import urllib.request

from .context import CFG, SERVICES, obter_modelo


TIMEOUT_MODELO_SEGUNDOS = 120


# ============================================================
# TIMEOUT REAL
# ============================================================

def chat_texto_com_timeout(messages, timeout_segundos=TIMEOUT_MODELO_SEGUNDOS, options=None):
    """
    Chama o modelo com timeout real de socket e fallback NVIDIA -> Ollama.
    Retorna (texto, erro).
    """
    modelo = obter_modelo("CODER")

    if SERVICES.MODEL_ROUTER is not None:
        try:
            resultado = SERVICES.MODEL_ROUTER.chat(
                modelo, messages, timeout=timeout_segundos, options=options,
            )
            if resultado.error:
                return "", resultado.error
            return (resultado.text or ""), None
        except Exception as erro:
            return "", f"{type(erro).__name__}: {erro}"

    payload = {"model": modelo, "messages": messages, "stream": False}
    if options:
        payload["options"] = options

    dados = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=dados,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=float(timeout_segundos)) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(bruto)
            return str((obj.get("message") or {}).get("content", "")), None
    except Exception as erro:
        return "", f"{type(erro).__name__}: {erro}"


# ============================================================
# CHAMADA UNIFICADA AO MODELO
# ============================================================

class _FuncaoChamada:
    def __init__(self, name="", arguments=None):
        self.name = name
        self.arguments = arguments


class _ChamadaFerramenta:
    def __init__(self, function):
        self.function = function


class _MensagemModelo:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _RespostaModelo:
    def __init__(self, content="", tool_calls=None):
        self.message = _MensagemModelo(content, tool_calls)


def _normalizar_tool_calls(tool_calls):
    """Converte tool_calls no estilo SDK do cliente ollama."""
    normalizadas = []
    for chamada in (tool_calls or []):
        if not isinstance(chamada, dict):
            normalizadas.append(chamada)
            continue
        funcao = chamada.get("function")
        if not isinstance(funcao, dict):
            continue
        nome = funcao.get("name", "")
        argumentos = funcao.get("arguments", "")
        if argumentos is None:
            argumentos = ""
        if not isinstance(argumentos, (str, dict)):
            try:
                argumentos = json.dumps(argumentos)
            except Exception:
                argumentos = str(argumentos)
        normalizadas.append(_ChamadaFerramenta(_FuncaoChamada(nome, argumentos)))
    return normalizadas


def _chamar_modelo(messages, tools=None, timeout_segundos=TIMEOUT_MODELO_SEGUNDOS, options=None, perfil="CODER"):
    """
    Chamada unificada ao modelo com fallback NVIDIA -> Ollama.
    Retorna objeto com .message.content e .message.tool_calls.
    """
    from ollama import chat

    modelo = obter_modelo(perfil)

    if SERVICES.MODEL_ROUTER is not None:
        try:
            resultado = SERVICES.MODEL_ROUTER.chat(
                modelo, messages, timeout=timeout_segundos, options=options, tools=tools,
            )
            if not resultado.error:
                return _RespostaModelo(
                    content=resultado.text or "",
                    tool_calls=_normalizar_tool_calls(resultado.tool_calls),
                )
            erro_router = resultado.error
        except Exception as erro:
            erro_router = f"{type(erro).__name__}: {erro}"

        try:
            return chat(model=modelo, messages=messages, tools=tools)
        except Exception as erro_sdk:
            return _RespostaModelo(
                content=f"[GoldenAI ERRO] Fallback falhou: {erro_router} | SDK: {erro_sdk}"
            )

    return chat(model=modelo, messages=messages, tools=tools)


# ============================================================
# VEREDITO E IDENTIDADE DE BUGS
# ============================================================

def extrair_confirmados_do_texto_veredito(veredito_texto):
    """Reconstrói identidade C1/C2... do veredito textual."""
    saida = {}
    if not isinstance(veredito_texto, str):
        return saida

    padrao = re.compile(
        r"^\s*-\s*(C\d+)\s*\|\s*Funcao\s+([^|]+?)\s*\|\s*"
        r"Linhas\s+([^|]+?)\s*\|\s*(.+?)\s*$",
        flags=re.IGNORECASE,
    )

    for linha in veredito_texto.splitlines():
        m = padrao.match(linha)
        if not m:
            continue
        cid = m.group(1).upper()
        saida[cid] = {
            "id": cid,
            "funcao": m.group(2).strip(),
            "linhas": m.group(3).strip(),
            "problema": m.group(4).strip(),
        }

    return saida


def validar_identidade_bugs_selecionados(veredito_salvo, bugs):
    """Exige concordância entre estado estruturado e texto final."""
    from .audit_deterministic import _norm_identificador

    pelo_texto = extrair_confirmados_do_texto_veredito(veredito_salvo.get("veredito", ""))

    if not pelo_texto:
        return False, "Nao foi possivel reconstruir IDs do veredito textual."

    for bug in bugs:
        cid = str(bug.get("id", "")).upper()
        esperado = pelo_texto.get(cid)

        if not esperado:
            return False, f"{cid} nao existe no veredito textual salvo."

        func_a = _norm_identificador(bug.get("funcao"))
        func_b = _norm_identificador(esperado.get("funcao"))

        if func_a != func_b:
            return False, (
                f"INCONSISTENCIA: {cid} aponta para '{bug.get('funcao')}' "
                f"mas no texto aponta para '{esperado.get('funcao')}'."
            )

    return True, "Identidade confirmada."


def localizar_intervalo_por_linha(codigo, linhas_referencia):
    """Fallback: usa linha auditada para localizar função MQL5."""
    linhas = codigo.splitlines()
    nums = [int(x) for x in re.findall(r"\d+", str(linhas_referencia or ""))]
    if not nums:
        return None

    alvo = max(1, min(nums)) - 1
    alvo = min(alvo, max(0, len(linhas) - 1))

    for idx in range(alvo, max(-1, alvo - 180), -1):
        trecho = linhas[idx].strip()
        if "(" not in trecho:
            continue
        if re.match(r"^(if|for|while|switch|return)\b", trecho, flags=re.I):
            continue

        m = re.search(r"\b([A-Za-z_]\w*)\s*\(", trecho)
        if not m:
            continue

        nome = m.group(1)
        # Importa localmente para evitar circular
        from .auto_fix import _extrair_funcao_por_intervalo
        # Tenta encontrar a função
        intervalo = _localizar_intervalo_funcao(codigo, nome)
        if not intervalo:
            continue

        ini, fim = intervalo
        if ini <= alvo + 1 <= fim:
            return intervalo, nome

    return None


def _localizar_intervalo_funcao(codigo, nome_funcao):
    """Localiza intervalo de linhas de uma função."""
    linhas = codigo.splitlines()
    padrao = re.compile(rf"^\s*(?:void|int|double|bool|string|datetime|color)\s+{re.escape(nome_funcao)}\s*\(")

    ini = None
    for i, linha in enumerate(linhas):
        if padrao.match(linha):
            ini = i + 1
            break

    if ini is None:
        return None

    # Conta chaves para encontrar o fim
    profundidade = 0
    for i in range(ini - 1, len(linhas)):
        profundidade += linhas[i].count("{") - linhas[i].count("}")
        if profundidade == 0 and "{" in "".join(linhas[ini - 1:i + 1]):
            return (ini, i + 1)

    return None


def resolver_intervalo_bug(codigo, bug):
    """Resolve intervalo de um bug: nome exato → fallback linha."""
    funcao_auditada = str(bug.get("funcao", "")).strip()

    intervalo = _localizar_intervalo_funcao(codigo, funcao_auditada)
    if intervalo:
        return intervalo, funcao_auditada, "NOME_EXATO"

    fallback = localizar_intervalo_por_linha(codigo, bug.get("linhas", ""))
    if fallback:
        intervalo_real, nome_real = fallback
        return intervalo_real, nome_real, "LINHA_AUDITADA"

    return None, None, "NAO_LOCALIZADO"
