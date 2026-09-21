# Handoff — Desktop Interação (input + voz espelhada + workers)

## Estado

V3 visual preservado. Interação corrigida sem tocar backend, Brain,
Orchestrator, TaskManager, providers, endpoints ou segurança.

## Root causes

- **Chat sem resposta (intermitente):** `ApiWorker` com sinal próprio era
  destruído pelo GC / condição de corrida no `QThreadPool`
  (`Signal source has been deleted`); o `finished` nunca chegava, HUD
  travava em PENSANDO. Corrigido com `Dispatcher` permanente (dono =
  MainWindow) + retenção por token + `setAutoDelete(False)`.
  Suíte de 116 testes sem nenhuma linha de erro de worker.
- **Voz sem resposta na tela:** VoiceService (backend) já executa o comando
  pelo fluxo central e fala via TTS sozinho; o Desktop nunca lia
  `last_heard`/`last_response`. Agora espelha ambos nas bolhas (baseline
  na 1ª leitura; sem reenvio → sem dupla execução).

## Mudanças (só desktop)

- `workers.py`: `Dispatcher` + token; `main_window.py`: `_run`/`_on_worker_done`,
  `submit_message(text, source)` como única porta de envio, foco no input
  ao mostrar CHAT/abrir, `_mirror_voice`, erro amigável de timeout.
- Decorativos já eram transparentes ao mouse; drag só na TitleBar
  (MainWindow sem `mousePressEvent`/`mouseMoveEvent`) — coberto por teste.
- `tests/test_jarvis_desktop_interaction.py` (7 testes: foco, digitação,
  Enter, clique SEND fim-a-fim, overlay, retenção, espelho de voz sem
  reenvio, noop vazio).

## Validação

- **116/116 OK**, zero regressão, zero erros de worker no log.
- E2E real (backend vivo, offscreen): usuário aparece, PENSANDO, entrega,
  HUD CONCLUÍDO/ERRO, sem vazamento de workers.
- Backend + app V3 corrigido relançados e vivos.
- Ollama lento no momento (~21s p/ prompt trivial; chats longos estouram
  45s — ambiental, pré-existente, fora de escopo desta fase que proíbe
  tocar backend/Brain). App trata com mensagem amigável sem congelar.
- "abra ele": rota determinística `CLARIFY conf 0.2 SHADOW` verificada;
  nada executa.

## Próximo

V4 visual. Nada iniciado.
