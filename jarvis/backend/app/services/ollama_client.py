from __future__ import annotations

import httpx

from ..config import Settings


SYSTEM_PROMPT = """Voce e o Golden Jarvis, assistente pessoal do Anderson.

Responda em portugues brasileiro, com clareza e objetividade.

Nesta versao, voce ainda nao possui acesso real a bancos, gastos, arquivos, MT5 ou comandos do computador.
Nao invente saldos, faturas, valores, datas ou informacoes financeiras.
Quando uma funcao ainda nao estiver implementada, informe isso claramente.
Nao diga que executou uma acao se ela nao foi realmente executada.
Nao envie ordens de compra ou venda. Nao faca pagamentos. Nao solicite senhas bancarias.
Se o usuario perguntar sobre o Golden Scanner ou MT5 nesta etapa, informe que a integracao sera adicionada posteriormente.
Se o usuario enviar um comprovante, apenas informe que a leitura automatica sera ativada na proxima etapa.
Utilize o historico recente da conversa para manter o contexto."""


class OllamaError(Exception):
    code = "OLLAMA_UNAVAILABLE"
    public_message = "O servico de inteligencia esta temporariamente indisponivel. Verifique se o Ollama esta funcionando no computador."


class OllamaTimeout(OllamaError):
    code = "OLLAMA_TIMEOUT"
    public_message = "O servico de inteligencia demorou demais para responder. Tente novamente."


class OllamaInvalidResponse(OllamaError):
    code = "OLLAMA_INVALID_RESPONSE"
    public_message = "O servico de inteligencia retornou uma resposta invalida. Tente novamente."


async def chat_with_ollama(messages: list[dict[str, str]], settings: Settings) -> tuple[str, int | None]:
    payload = {"model": settings.ollama_model, "messages": messages, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            response = await client.post(f"{settings.safe_ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise OllamaTimeout() from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaError() from exc

    message = data.get("message") if isinstance(data, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise OllamaInvalidResponse()
    return content.strip(), data.get("eval_count") if isinstance(data.get("eval_count"), int) else None
