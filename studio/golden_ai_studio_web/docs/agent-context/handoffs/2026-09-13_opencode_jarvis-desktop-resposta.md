# Handoff — Desktop Resposta JARVIS (causa raiz + correção)

## Causa raiz exata

Duas causas combinadas, nenhuma no pipeline de render:

1. **Voz — YOU sem JARVIS (principal):** o Desktop espelhava todo
   `last_heard` novo como YOU, mas o VoiceService grava `last_heard`
   ANTES do filtro de wake word; fragmentos de ruído ambiente
   (ex.: ouvido real "Eu não quero que não coileva") são IGNORADOS pelo
   serviço (sem execução, sem `last_response`). Resultado: várias bolhas
   YOU sem nenhuma JARVIS. Correção: só vira conversa o que GEROU
   resposta — espelha o par quando `stats.commands`/`stats.errors`
   aumenta ou `last_response` muda; ruído ignorado nunca polui.
2. **Digitado lento parecia morto:** Ollama degradado (~21s p/ trivial;
   geração longa estoura 45s). Respostas levam minutos ou viram erro
   amigável — screenshot no meio do voo mostra YOU sem resposta.
   Pipeline provado funcionando ao vivo (HTTP→callback→append→render).

Pipeline digitado verificado ao vivo: `CHAT_HTTP_RESPONSE ok:true` →
`APPEND_ROLE=jarvis` → bolha renderizada → HUD CONCLUÍDO → scroll no fim.
Auto-scroll comprovado (value==maximum após 30 pares).

## Mudanças (só desktop)

- `main_window.py`: `_mirror_voice` por par executado + `_norm` p/ dedup.
- `widgets/chat_view.py`: `_reveal()` (cursor no fim) após cada append.
- `tests/test_jarvis_desktop_interaction.py`: +`test_request_to_response_appends_jarvis`
  (request→JARVIS+HUD+scroll+sem vazamento); mirror cobre ruído ignorado.
- Ambiente: limpo p/ 1 backend (1 listener :8765) + 1 app.

## Validação

- **117/117 OK**, zero regressão, zero erros de worker.
- E2E ao vivo: TYPED YOU+JARVIS(hora) ✓, baseline silenciosa ✓,
  scroll ✓, HUD CONCLUÍDO ✓.
- Rota `CLARIFY 0.2 SHADOW` p/ "abra ele" (nada executa); formulação
  depende do Ollama, hoje lento (ambiental, backend intocado por regra).
- TTS segue no VoiceService existente (desktop não fala por conta própria).

## Próximo

V4 visual. Nada iniciado.
