# Decisões

## 2026-09-11 — Registry como fonte única

O `ToolRegistry` é a única fonte de definição das ferramentas do Golden Jarvis.
O Brain não mantém catálogo independente. Toda ferramenta nova deve ser registrada uma vez
e sua representação para o LLM deve ser gerada por `get_llm_tools()`.

## 2026-09-11 — Execução fail-closed

Qualquer falha de JSON, schema, lookup ou tipo encerra o fluxo sem execução.
`open_any_exe` não é exposta ao modelo.

## 2026-09-23 — Computer Use usa Known Folder e recuperação fail-closed

Missões de arquivo não montam `C:\\Users\\<nome>\\Documents`. No Windows, o destino usa o Known Folder nativo de Documents; falhas `PATH_NOT_FOUND` são auditadas, re-resolvidas de forma limitada e não permitem prosseguir cegamente.

## 2026-09-11 — Memória é contexto não confiável

Memórias recuperadas nunca recebem autoridade de system prompt. O Brain recebe apenas Top-K
limitado e rotulado como dado não confiável. Sem `nomic-embed-text`, o fallback é busca lexical
declarada como degradada; vetores artificiais não representam busca semântica.

## 2026-09-23 — Browser Use 4D permanece controlado e fail-closed

Browser Use reutiliza a sessão Playwright visível e o mesmo `JarvisService`,
`ToolRegistry`, `SecurityManager`, `AuditLog`, `ComputerMissionPlanner` e
`ComputerMissionExecutor`. Grounding usa elementos DOM/ARIA e o executor valida janela,
estado de página e referências stale antes de agir. Consentimento de cookies, CAPTCHA e
verificação anti-bot não são aceitos, resolvidos nem contornados; esses estados terminam em
`USER_CONFIRMATION_REQUIRED`. A missão real de busca OpenAI ficou bloqueada por esse estado
externo, então a fase não é marcada como CLOSED.

## 2026-09-24 — Computer Use 6D usa checkpoints lógicos duráveis

Workflows longos reutilizam o `TaskDatabase` existente para `mission_checkpoints` e
`mission_action_receipts`. Checkpoints persistem apenas estado lógico seguro, com schema version,
integrity hash e context revision; coordenadas, screenshots, cookies, tokens e handles não são
persistidos. O resume exige token explícito, revalida o mundo e evita repetir efeitos já
verificados. Estado externo desconhecido é recuperado por verificação antes de qualquer retry.

## 2026-09-24 — 6D real permanece PARTIAL na confirmação de Save As

A missão real pausou em `CHECKPOINT_PYTHON_DONE`, retomou sem reexecutar Python, concluiu a
pesquisa de Ollama e a transferência para o Notepad, e parou em `open-save-dialog` porque a
escrita de `resumo_pesquisa.txt` não foi autorizada. O caminho não foi criado; qualquer
continuação requer autorização explícita para o alvo exato.

## 2026-09-24 — 6D.1 recupera estado externo sem reutilizar alvos

O fechamento inesperado do aplicativo é classificado antes de qualquer retry. Quando contexto,
proveniência e alvo autorizado continuam válidos, a recuperação invalida handles/documentos
anteriores, abre uma nova superfície UIA pertencente à missão e reconstrói o conteúdo a partir
do `MissionContext`; pesquisa web não é executada novamente. A escrita usa `ui_type_editor`,
uma ação única, confirmada e protegida pelo `SecurityManager`, para evitar a corrida entre foco
e teclado. A validação real desta sessão permaneceu BLOCKED porque o Notepad desapareceu quando
o PUBG retomou o foreground; nenhum arquivo foi criado.

## 2026-09-24 — 6D.2 pausa diante de atividade humana

Foreground é arbitrado por estado de processo, janela, foco, dono do foreground e idade
operacional do último input. `GetLastInputInfo` não captura nem persiste conteúdo de teclado
ou mouse. Com `USER_EXTERNAL_APP` e input recente, a missão cria checkpoint, registra
`USER_ACTIVITY_DETECTED` e pausa; não tenta minimizar, fechar, focar ou digitar no aplicativo
externo. Recuperação automática é limitada a dois focos e resume somente por comando explícito.
`ui_type_editor` rejeita input quando HWND ou `foreground_epoch` mudam antes da escrita.
