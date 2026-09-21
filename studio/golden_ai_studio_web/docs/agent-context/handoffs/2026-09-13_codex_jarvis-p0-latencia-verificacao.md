# Handoff - Golden Jarvis P0

## Estado

Os quatro itens P0 da auditoria CyberBot × Golden foram implementados sem alterar modelos,
riscos, rotas, trading ou arquitetura. Orchestrator continua `shadow`.

## P0.1 - Resultado final

`Tool` agora declara `ResponsePolicy`: `FINAL`, `NEEDS_SYNTHESIS`, `STRUCTURED` ou
`BACKGROUND`. Fast paths WINDOWS, SYSTEM e MARKET_DATA entregam o resultado estruturado
diretamente, sem segunda LLM. A telemetria por request contém request_id, rota, skill,
tool e chamadas LLM antes/depois da tool.

## P0.2 - ACK

Planner e tools lentas recebem ACK local, determinístico e sem afirmação de conclusão.
Voice fala o ACK antes de processar; Desktop mostra PROCESSANDO imediatamente; jobs continuam
no TaskManager. Teste controlado: ACK abaixo de 50 ms, job RUNNING e conclusão verificada.

## P0.3 - Prompt estável

`JarvisBrain._system_prompt()` contém somente identidade, regras e contrato estáveis. Catálogo
de tools filtrado e memória recuperada ficam no runtime context. AuditLog guarda somente
`static_prompt_size`, `runtime_context_size` e `tool_catalog_size`, nunca o conteúdo.

## P0.4 - Verify before claim

Todo resultado central contém `success`, `verified`, `verification` e `response_policy`.
Existem pós-condições específicas para cotação/provider, consultas, processo Windows e
operações de arquivo. Sucesso sem verificação gera mensagem cautelosa. Dry-run confirma apenas
a simulação, mantendo a palavra `SIMULAÇÃO`. Task estruturada não conclui se uma etapa real
com policy declarada não estiver verificada.

## Validação

- Suíte completa: `142 passed, 69 subtests passed`.
- Compilação: todos os Python alterados passaram em `py_compile`.
- Smoke calculadora: WINDOWS, FINAL, process_lookup, verified, 0 LLM.
- Smoke dólar: MARKET_DATA, AwesomeAPI, FINAL, provider_payload, verified, 0 LLM.
- Falha e sucesso não verificado cobertos; nenhuma mensagem falsa de conclusão.
- Backend recarregado na porta 8765.

## Limitações

Algumas ações Windows não oferecem pós-condição confiável; nesses casos a linguagem é
deliberadamente cautelosa. ACK HTTP não é streaming: no Desktop ele é mostrado localmente antes
da chamada, e na voz é falado pelo VoiceService. Nenhuma mudança P1 foi iniciada.

## Próximo

P1 Voice Performance, somente após autorização explícita.
