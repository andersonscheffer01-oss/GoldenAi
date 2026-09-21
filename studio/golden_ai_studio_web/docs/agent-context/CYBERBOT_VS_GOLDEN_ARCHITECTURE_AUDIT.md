# CYBERBOT v1.0.27 × GOLDEN JARVIS — Auditoria de Arquitetura e Latência

> SOMENTE ANÁLISE. Nenhum código do Golden ou do CyberBot foi alterado,
> executado ou copiado. Referência read-only: `C:\GoldenAI\references\CyberBot\source`.
> Golden: `C:\GoldenAI\studio\golden_ai_studio_web` (fase: 132/132 testes, Orchestrator SHADOW).
>
> Convenção neste documento: **EVIDÊNCIA** = caminho de código seguido na referência.
> **ESTIMATIVA** = inferência declarada como tal. Números citados vêm de comentários/logs
> do próprio código do CyberBot (medidos pelo autor com o usuário real).

## Implementação P0 (2026-09-13)

- P0.1 concluído: `ResponsePolicy` (`FINAL`, `NEEDS_SYNTHESIS`, `STRUCTURED`,
  `BACKGROUND`), retorno direto de tools finais e contagem de chamadas LLM.
- P0.2 concluído: ACK local/determinístico para Planner e jobs lentos; Voice fala antes
  do processamento, Desktop muda imediatamente para PROCESSANDO e TaskManager permanece background.
- P0.3 concluído: system prompt estático separado do catálogo filtrado/runtime context;
  somente tamanhos são auditados.
- P0.4 concluído: resultados distinguem `success` de `verified`; mercado, processos,
  consultas e operações de arquivo têm verificadores por categoria. Sem pós-condição,
  a resposta usa linguagem cautelosa.

Validação P0: `142 passed, 69 subtests passed`. Smokes reais: calculadora e USD/BRL com
`FINAL`, `verified=true` e zero chamadas LLM.

## Implementação P1 Voice Performance (2026-09-13)

- Whisper comparado em CPU AMD, sem CUDA: `base` foi mais rápido; `small` elevou o acerto
  de roteamento do corpus controlado de 6/10 para 8/10 e foi escolhido por qualidade.
- Warmup assíncrono, `int8`, `beam=1`, prompt PT-BR curto e sem condicionamento no texto anterior.
- Gate adaptativo ao ruído, pre-roll, estado LISTENING após fala real e fim de fala em 550 ms.
- Confiança por segmento, rejeição de silêncio/alucinações e limiar mais estrito para alto risco.
- Backlog antigo descartado; TTS bloqueia autoescuta e invalida captura sobreposta.
- Telemetria por `utterance_id`: captura, fala, silêncio, STT, normalização, TTS e turno total.

Validação automática P1: `154 passed, 72 subtests passed`. Benchmark serial controlado:
`base` P50 656 ms/P95 1153 ms; `small` P50 1760 ms/P95 2021 ms. O tempo estimado entre fim
da fala e transcrição caiu de ~2722 ms para ~2360 ms pela redução do silêncio. Áudio temporário
é apagado. Aprovação final permanece pendente de comando humano no microfone real.

## Implementação P1.1 Voice Conversation (2026-09-13) — PASS

- Perfil `VOICE_FAST` (voz + CONVERSATION simples): Groq `qwen/qwen3.8-27b`,
  fallback `compound-mini`, Ollama local/SECRET. Benchmark: TTFT P50 302 ms.
- Recovery: adapter vencedor volta a `AVAILABLE`; 429 real mantém `RATE_LIMITED`.
- Output modes, runtime voice context, follow-up, 1 Brain + 1 TTS por turno.
- Smoke de microfone real A/B/C/D validado com fala humana.

## Implementação P1.2 STT Robustness (2026-09-13) — PASS

- Mic confirmado: USB Audio Device (MME idx 1, mono, nativo 44100 Hz →
  captura 16000 Hz; resampling único no PortAudio, sem dupla conversão).
- Pre-roll 500 ms validado (onsets intactos em todos os RAWs); configurável
  via `JARVIS_PRE_ROLL_SECONDS`. Calibração com trava anti-contaminação
  (`JARVIS_CALIBRATION_MAX_JUMP=4`): falar durante a calibração não explode o gate.
- End silence 550 ms mantido; variante 700 ms + beam 2 testada em fala real
  sem ganho fora do ruído → default `small/int8, beam=1, best_of=1`,
  `condition_on_previous_text=False`, initial_prompt só vocabulário.
- Clipping/peak por captura (`peak`, `clipped_samples`, `clipping`) + device
  + RAW/NORMALIZED + métricas do decoder no DEV. Sem clipping observado
  (peaks 1600–6700, headroom amplo).
- `LOW_CONFIDENCE` com texto fala "Não entendi bem. Pode repetir?";
  `IGNORED_NOISE` continua silencioso.
- Bateria real 7/7 intents (A–G), wake intacta, STT P50 ~2,0 s/P95 ~2,7 s.
  Suíte: `178 passed, 72 subtests passed`, zero regressão P1.1/fast paths.
- Gap conhecido documentado: adapters cloud registram lazy no 1º chat de
  texto; após restart puro, voz cai no Ollama direto até um chat registrar.
  Workaround operacional aplicado; eager-boot proposto como próximo.

## Implementação P1.3 Startup/Ready (2026-09-13) — PASS

- Gap eliminado: adapters registrados EAGER no boot (4/4 antes da 1ª
  pergunta); Groq validada por models-list (zero token), Ollama por
  /api/tags + modelos presentes sem carregar, STT warm aguardado.
- Readiness SSOT: STARTING→CORE_READY→WARMING→READY|DEGRADED|FAILED
  (core ~0,1 s; full ~6,8 s em background; Desktop mostra no painel + DEV).
- Voz durante WARMING avisa "Estou iniciando..." em vez de executar pela
  metade ou perder silenciosamente. Shutdown limpo (stop da voz).
- Cooldown: transitórios (429/TIMEOUT/DEGRADED) retornam após 60 s;
  AUTH/OFFLINE não. Timeout local 45 s (SECRET/14b-CPU nunca respondia
  em 8 s). VOICE_FAST inalterado.
- Restart frio real com voz: 1º turno VOICE_FAST/groq sem fallback
  (TTFT 347 ms = aquecido); fast paths e dólar imediatos; SECRET só
  local (ok em 11,8 s com modelo residente).
- Suíte: `199 passed, 72 subtests passed`, zero regressão.

---

## 1. Executive Summary

O CyberBot parece rápido por **uma razão dominante + quatro coadjuvantes**:

1. **Quase nada chega ao LLM.** Portas determinísticas ("redes") resolvem abrir/fechar
   programas e pastas, hora/data, vídeo (detecção), confirmações sim/não, desfazer,
   digitar, parar, vision-control e ativação do computer use — 0 chamadas de IA,
   resposta em milissegundos (EVIDÊNCIA: `main.py:_rede_de_abrir`, `_rede_de_fechar`,
   `_rede_do_relogio`, `_redes_do_pc`, `_rede_do_video`, `_rede_vision_local`).
2. **Quando chama IA, chama UMA vez e barata.** Cérebro padrão: Gemini flash do cliente
   (0,7–1,9 s medidos) com Codex-na-VPS como rede (1,4 s direto). Sem segunda volta ao
   modelo quando a tool já devolve texto final (EVIDÊNCIA: `screen_process` retorna texto;
   `_responder_curto`; relógio em molde; `_linha_do_relogio` injetada sem tool call).
3. **Percebida > real.** ACK falado imediato com tempos REAIS por tipo de job
   (`_aviso_de_demora`: imagem 1–2 min, site 6–8 min, leads 3–5 min), HUD com estado por
   ferramenta (`_tool_task_state`), chat escrito junto ao primeiro som (`ao_primeiro_som`),
   voz aquecida em paralelo ao pensamento.
4. **Trabalho pesado é local e em background.** Vídeo: LLM (VPS) só PLANEJA (JSON de
   operações); ffmpeg local executa em thread, 1 job, prioridade baixa, progresso a cada
   20%, cancelamento, TTS ao concluir (EVIDÊNCIA: `actions/editar_video.py`).
5. **Tudo pré-aquecido.** Saudação fala antes de carregar whisper/Kokoro/cérebro
   (12,3 s → paralelo); whisper fica carregado entre falas; conexão de voz pré-aberta
   (1,20 s → 0,65 s); STT especulativo durante o rabicho de silêncio (~0,5 s ganhos).

**Quanto é modelo vs engenharia (julgamento com base nas evidências):** o modelo
responde por uma fração pequena (trocaram OpenRouter-grátis 10–16 s por Gemini 0,7–1,9 s
= ~10×, mas isso é custo, não arquitetura). A maior parte da fluidez vem de **roteamento
(0 IA), skip-second-brain, background e ACK** — tudo copiável sem trocar de modelo.

**Golden hoje (para comparação):** fast paths determinísticos já existem para SYSTEM,
MARKET_DATA, WINDOWS e CLARIFY (0 IA, ~0,1 s); conversation usa ModelRouter cloud-first
(Groq → OpenRouter → Gemini → Ollama, timeout 8 s/tentativa); TaskManager com background,
cancelamento e recovery; VoiceService único com estados e evento por comando; sem
computer use/browser/WhatsApp/imagem/vídeo; STT faster-whisper base CPU; TTS edge-tts + SAPI.

---

## 2. CyberBot Architecture

Entrypoint: `source/main.py` → `main()` (linha 9637). UI: `ui.py` (PyQt, HUD central +
rails laterais). Núcleo: classe `JarvisLive` (linhas 1974–9591).

```
MIC (sounddevice callback, backlog com descarte) ─┐
TEXTO DIGITADO (chat) ────────────────────────────┤
ARQUIVOS ARRASTADOS ([FILE_UPLOADED]) ─────────────┤
                                                  ▼
                                   PORTAS DETERMINÍSTICAS (0 IA)
                                   vocativo→ relógio → webcam → abrir/fechar →
                                   vídeo → desfazer → digitar → parar →
                                   computer-use gates → desenhar
                                                  │ (nenhuma casou)
                                                  ▼
                                   CÉREBRO: Codex VPS → Gemini → OpenAI
                                   (loop ≤3 rodadas, executa tools pedidas)
                                                  ▼
                                   TOOL (28 declarações; executor único
                                   _executar_ferramenta_local)
                                                  ▼
                                   RESPOSTA FINAL (texto da tool; sem 2ª IA)
                                                  ▼
                                   TTS (Kokoro/OpenAI-stream/Charon)
                                   + chat escrito no 1º som + diário
```

Paralelismo estrutural: captura de áudio nunca bloqueia (thread por fala:
`_pipeline_local`); greeting × loading; boca × pensamento (`_aquecer_boca`);
whisper × rabicho; describir imagens em threads; TTS em fluxo.

---

## 3. Golden Architecture atual

```
VOZ (VoiceService daemon) / TEXTO (chat)
      ↓  (voz: wake strip → mesmo brain)
CentralOrchestrator → SkillsRouter → ModelRouter
      ↓ (determinístico LOW-RISK: sem LLM)
fast path: SYSTEM / MARKET_DATA / WINDOWS / CLARIFY (~0,1 s)
      ↓ (precisa de LLM)
ModelRouter: Groq qwen3.8-27b → OpenRouter → Gemini → Ollama
      (timeout 8 s/tentativa, retry ≤1, SECRET local-only)
      ↓
Planner → TaskManager → JarvisService → SecurityManager → ToolRegistry → AuditLog
      ↓
TTS existente (edge-tts/SAPI) + Desktop PySide6 (polling)
```

Gaps vs CyberBot: sem computer use/browser/WhatsApp/imagem/vídeo; sem ACK imediato;
sem skip-second-brain explícito em tools verbosas; STT base CPU; sem pré-aquecimento
orquestrado; sem telemetria de latência por fase.

---

## 4. Voice comparison

### 4.1 CyberBot — dois caminhos

**A) Gemini Live (primário, nativo em áudio):** websocket full-duplex, PCM 16 kHz in /
24 kHz out, pacotes de 40 ms (`MIC_CHUNK_SIZE=640`); portão de silêncio (piso medido
80, medido por sala — NÃO chutar); backlog com descarte de chunks velhos; VAD por
janela de 30 s pós-ativação; `NO_INTERRUPTION`; interrupção do usuário em ~50 ms
(chunks); cancelamento de resposta com limpeza de estado; sessão de texto paralela
para o chat digitado (sem custo de áudio). EVIDÊNCIA: `main.py` linhas 2113–2310,
4786–4835, 6419–6427, 8223–8335.

**B) Modo local (whisper→Codex/Kokoro):** microfone selecionado por TESTE real
(`audio_dispositivos`: WASAPI > DirectSound > MME, dedup por nome, teste de blocos
reais com prazo — "abrir sem erro NÃO significa que funciona"); gravação até silêncio;
whisper `small` CPU int8 / `large-v3` GPU float16 (0,39 s vs 1,59 s medidos);
`beam_size` 5 GPU / 1 CPU; `initial_prompt` com vocabulário da casa; `vad_filter`
DESLIGADO (cortava fala junto); `condition_on_previous_text=False`; normalização de
ganho pelo pico (teto 20×); faixa de resgate 0,045–0,09 decidida por confiança
(`no_speech_prob` ≤ 0,50, `avg_logprob` ≥ −1,6; curta exige mais); anti-alucinação
(lista de fechamentos de legenda + eco de vocabulário + fantasmas colados);
corretor fonético pós-STT (0,5 ms); vocativo cortado no início E no fim
(`_tira_vocativo`, `_passa_pelo_nome`, janela de 30 s, "só o nome" responde sem IA);
STT especulativo durante o rabicho (economiza ~0,5 s). EVIDÊNCIA: `main.py`
5890–6014, 6076–6205; `core/audio_dispositivos.py`, `core/corretor_fala.py`.

**Traço de "Jarvis, abra a calculadora":** mic → portão → whisper (~0,4–1,6 s) →
filtros → vocativo removido → `_rede_de_abrir` casa → `open_app(calc)` → frase molde
falada + escrita. **Chamadas de IA: 0.**

### 4.2 Golden — caminho atual

Mic → `VoiceService` (janela 6 s, RMS) → Whisper base → wake strip → MESMO
`brain.interpret` do digitado → Orchestrator → fast path (calculadora: 0 IA) ou
ModelRouter → tool → `last_event` → mirror no Desktop → TTS existente.
"Jarvis, abra a calculadora": **0 IA** (após fase fast-path). Antes: 1 (Ollama).

### 4.3 Oportunidades Golden (voz)

- STT: subir para `small`, `initial_prompt` com vocabulário, beam 1 CPU, gates de
  confiança (custo: +~1 s/fala, −80 s de alucinação perseguida — tradeoff medido por eles).
- Portão de áudio medido por sala + descarte de backlog (barato, local).
- `listen_more` (wake sozinha) já existe; falta teste de mic na UI (config).
- Manter: mesmo brain para voz/texto (paridade já conquistada).

---

## 5. Brain/provider comparison

| # | CyberBot (ordem real) | Modelo/papel | Latência medida | Timeout/retry | Fallback |
|---|---|---|---|---|---|
| 1 | Codex CLI na VPS (relay privado) | agente geral, sem cota | 1,4 s direto; 4,5–5,4 s escada; 12–19 s CLI sandbox | diag por texto de erro; sem sleep longo | Gemini |
| 2 | Gemini do cliente | rápido do dia a dia | 0,7–1,9 s; papo sem tools 1,39 s vs 2,73 s | 429/min→45 s, /dia→24 h, `retryDelay` respeitado | OpenAI |
| 3 | OpenAI (se houver chave) | reserva | primeiro som stream ~1,1 s (voz) | — | Codex chat |
| 4 | OpenRouter :free (removido 05/09) | legado | 10–16 s; 68 s sob 429 em cascata | fila removida | — |

Golden: Groq qwen3.8-27b → OpenRouter → Gemini → Ollama qwen2.5-coder:14b, 8 s/tentativa,
retry ≤1, SECRET local. Papel equivalente com custo zero e sem VPS privada.

---

## 6. Fast paths

| Comando | CyberBot (função, 0 IA?) | Golden atual |
|---|---|---|
| abrir programa/pasta | `_rede_de_abrir` (~40 programas, match por palavras, verifica janela) — NÃO | WINDOWS (3 programas) — NÃO |
| fechar programa | `_rede_de_fechar` — NÃO | Conversation/LLM — **SIM (gap)** |
| hora/data | `_rede_do_relogio` (molde, 0,001 s; era 5,75 s/2 voltas) — NÃO | SYSTEM get_time — NÃO |
| cotação | regra textual p/ tool? Não evidenciado (vai ao modelo) | MARKET_DATA determinístico — NÃO (Golden na frente) |
| parar/cancelar | `_PARAR_PC`, `_PARAR_COMPUTER_USE`, freio ESC, failsafe — NÃO | parcial (cancel desktop; sem ESC) |
| sim/não exclusão | `_delete_confirmation_decision` local — NÃO | SecurityManager (fluxo) |
| desfazer | direto se recente — NÃO | NÃO existe |
| digitar na tela | thread direta — NÃO | NÃO existe |
| "já terminou?/para" (vídeo) | `acao=status/cancelar` sem aviso — NÃO | TaskManager tem estados (falta UX) |
| chegada de arquivo | `_anotar_chegada` confirma sem modelo — NÃO | "não implementado" (gap) |
| capacidade ("você edita vídeo?") | responde, não executa — NÃO | LLM |
| papo curto | `_e_papo` (sem as 36 tools: 2,73 s→1,39 s) — 1 IA barata | Conversation, sempre 1 IA full |

**TOOL_RESULT_POLICY (recomendação, não implementar):** se a tool devolve texto final
pronto para fala/chat, retornar direto sem segunda chamada ao Brain. Exceções: quando
o resultado precisa fusão com contexto, ou quando for status/progresso que exige fraseo.
Golden já faz isso nos fast paths; estender a tools de leitura (status, consulta).

---

## 7. LLM call count (A–J)

| Cenário | CyberBot (IAs) | Golden atual (IAs) |
|---|---|---|
| A "abra a calculadora" | 0 | 0 |
| B "que horas são?" | 0 (+0; era 2) | 0 |
| C "explique inflação" | 1 (Codex/Gemini) | 1 (Groq/OR/Ollama) |
| D "olhe minha tela" | 1 (visão; texto final falado direto) | 1–2 (visão + possível formulação) |
| E "clique em Configurações" | 1 visão (+loop de correção) | N/A (sem computer use) |
| F "crie imagem de casa" | 1 (job VPS; ACK antes) | N/A |
| G "edite esta imagem" | 1–2 (descrever em threads + job) | N/A |
| H "edite vídeo..." | 1 plano (VPS) + 0 (ffmpeg local) | N/A |
| I "leia este PDF" | 1 (Gemini summarize) | 1 (LLM c/ texto extraído) |
| J "envie pelo WhatsApp" | 1 (decisão) + 0 (bridge) | N/A (skill não implementada) |

Conclusão: onde ambos existem, o placar de IAs é igual (0/1). A diferença está no
**custo e no tempo de cada chamada**, não na quantidade.

---

## 8. Vision

CyberBot: `mss` → thumbnail → JPEG q52 (câmera q82) → Gemini do cliente
(`gemini-3.6-flash`) com cooldown de cota inteligente → fallback Codex-na-VPS
(sem cota). `screen_process` devolve **texto final** (1 IA, sem 2ª volta; sessão de
áudio recebe só texto). Confirmação de câmera, anti-duplo-stream, pergunta manda mais
que campo. EVIDÊNCIA: `actions/screen_processor.py`.

Golden: `qwen2.5vl:7b` local, 30–60 s por análise. Pipeline mais privado, porém
~10–30× mais lento. Recomendação: manter local como padrão privado; documentar
atalho cloud opcional (mesmo padrão Gemini→fallback) sem mudar default.

---

## 9. Screen result fast path

Evidenciado em `screen_process` (retorna `answer: str`, falado/escrito direto) e no
fluxo Live (tool result vira fala sem nova inferência). Golden: adotar
TOOL_RESULT_POLICY nas tools de leitura.

---

## 10. Computer Use

Ordem real (`actions/usar_computador.py` + `tela_visao.py`):
1. **Porta de ativação** ("ativar computador" → espera tarefa 45 s, máx. 2 repetições;
   eco tem 12 s de carência; tarefa fraca não toma a tela).
2. **Localizar:** UIA nativo (COM por thread, cache de propriedades, `achar_por_nome`,
   `acionar` por Invoke/Select/Toggle, `rolar_ate_ver`, `esperar_elemento`) — sem IA.
3. **Visão como fallback:** `olhar()` espera tela parar (assinatura de imagem,
   anti-clique-em-tela-velha), foto + elementos numerados → Codex responde
   "elemento 12" → clique no CENTRO (visão nunca chuta pixel).
4. **Executar:** pyautogui com FAILSAFE=False + verificações próprias (canto é posição
   comum), arrasto em passos, digitação sem roubar clipboard, teclas validadas.
5. **Segurança:** UAC não automatizado (pede confirmação); famílias de risco
   (compra/contratação/cancelamento); confirmação sim/não com filtro anti-TV;
   freio ESC (polling 20 Hz) + "para" no laço + failsafe de canto; narrador avisa
   antes de tomar o mouse; correção mid-task ("não, o de baixo") vale mais que o pedido.
6. Golden: não tem. Recomendação P2: porta de ativação + UIA-first + visão numerada
   como fallback — copiar a ORDEM, não o código.

---

## 11. Browser

Híbrido: navegação simples (`go_to/search/new_tab`) abre no **navegador real do usuário**
(reuso de janela, sem segundo perfil); automação (click/type/DOM) via **Playwright com
o perfil REAL** (User Data do Chrome/Edge, canais por SO). Valida o plano futuro do
Golden: mesma divisão. EVIDÊNCIA: `actions/browser_control.py:493–546, 1013–1043`.

---

## 12. Image (geração)

`remote_codex_job(kind=image)`: descrição → **job na VPS privada** (timeout 960 s) →
arquivo aberto localmente; estados no HUD (CREATING_IMAGE); ACK com tempo real
("1 a 2 minutos"). **Arquitetura copiável:** job assíncrono + ACK + abrir resultado.
**Serviço privado:** a VPS/gateway Codex (chave não sai de lá). Golden não tem
provedor de imagem → classe C (precisa de provider externo).

---

## 13. Image Edit

Arraste vira `[FILE_UPLOADED]`; programa (não modelo) confirma chegada; imagens da
edição identificadas por **visão paralela em threads** (OpenAI, `_descrever_imagens`);
edição roda como job assíncrono (`asyncio.create_task(_editar_imagem_falada`).
Otimizações de velocidade copiáveis: PNG sem `optimize`, `draft()` no decode JPEG q88,
resize LANCZOS, threads por imagem com prazo. EVIDÊNCIA: `codex_remote.py:43–90, 702–713`.

---

## 14. Video

**LLM NÃO edita vídeo.** LLM (VPS) produz **plano JSON** de operações do cardápio
(`_plano_por_palavras` local cobre os comuns sem IA); executor determinístico ffmpeg
6.1 bundled faz o trabalho. Operações reais: formato 9:16/16:9/1:1/4:5 (blur/fill/
barras), cortar_silêncio por envelope RMS (nunca por intervalos do whisper),
trim, legenda TikTok/simples, texto, overlay/logo, música com ducking, speed/slow,
mirror, join, efeitos (P&B/vintage/zoom/tremor), transições, qualidade leve/Full HD,
salvar em pasta (padrão: ao lado do original + "(editado)"). **1 job por vez**,
thread dedicada, ffmpeg em prioridade baixa (voz não engasga), progresso via
`-progress pipe:1` com avisos a cada 20%, cancelamento cooperativo checado entre
etapas, TTS ao concluir + abrir arquivo. EVIDÊNCIA: `actions/editar_video.py`.

---

## 15. Background video

Job dict (`fase/pct/cancelar/proc`), `_em_andamento()`, `acao=status/cancelar`,
`_trabalho` em thread, `_vigia` de progresso, TTS final. Golden TaskManager já tem
primitivas equivalentes (estados, cancelamento cooperativo, recovery) — falta a
superfície (status/andamento no Desktop) e 1-job-com-fila por categoria.

---

## 16. Multi-arquivo

Todos os paths do arraste chegam (`path=` + `extra=`); janela guarda 12 recentes
(1 h); vídeo preferido por extensão; imagens da edição resolvidas por visão
("a de cima/baixo" via descrição, não por ordem de chegada); pedido pode vir ANTES
do arquivo (fica pendente e dispara na chegada). Copiável: confirmação programática
de chegada + memória de contexto por 1 h. EVIDÊNCIA: `_rede_do_video`, `_anotar_chegada`.

---

## 17. Parallelism (catálogo)

| Área | CyberBot | Golden |
|---|---|---|
| captura × pensamento | mic callback + thread por fala | VoiceService thread (1 fala por vez; sem backlog) |
| STT × silêncio | whisper durante o rabicho | serial (6 s + whisper) |
| boca × cérebro | `_aquecer_boca` em paralelo | serial (resposta → TTS) |
| startup | saudação × whisper/Kokoro/cérebro/relay/voz | serial sob demanda |
| imagens | threads por imagem | — |
| TTS | streaming em chunks (~50 ms p/ interrupção) | bloco único (edge→mp3→play) |
| vídeo | 1 job + progresso (não paralelo interno) | TaskManager até 8 workers |
| brain | 1 por vez (`_local_ocupado`) | 1 por vez |

---

## 18. Files/PDF

Por tipo, com Gemini direto (`gemini-3.6-flash`): imagem (describe/OCR/analyze/resize/
convert/compress/crop), PDF (pdfplumber→50k chars→summarize/extract/info), texto/doc/
dados/código/áudio/vídeo(readonly)/pptx. **1 IA por arquivo**, sem chunking visível,
sem cache. Golden tem extração (docling) mas sem fluxo equivalente.

---

## 19. WhatsApp

Bridge Node+Baileys **local** (sessão QR local, `server.js` próprio, runtime Node
bundled, auto-instalação de deps com status em arquivo, limpeza de órfãos só do
próprio server.js). Ações: connect/status/send_text/send_file/recent/transcribe/
find_contact/groups/watch/schedule/agent_*. Envio = decisão do modelo (1 IA) + bridge
(0 IA). Golden: skill NÃO implementada — Bridge local é o padrão copiável (classe A
para infra, C para execução que exige pareamento do usuário).

---

## 20. Memory

`long_term.json` (fatos: quem o dono é, para sempre) + `diario.jsonl` (episódios com
hora, append-only, por sessão; antigas só sob pergunta do passado) + reset de conversa
a cada abertura + anotação dos DOIS lados (dono e respostas) + "fez" (ferramentas
executadas). Golden Memory (SQLite versionado, episodic/semantic/embeddings) é
tecnicamente superior; faltam: diario de ações executadas e filtro de sessão.

---

## 21. STT

| Parâmetro | CyberBot | Golden atual |
|---|---|---|
| engine/modelo | faster-whisper `large-v3` GPU fp16 / `small` CPU int8 (bundled) | faster-whisper `base` CPU |
| beam/best_of | 5 GPU / 1 CPU; best_of — | defaults (a auditar) |
| vad | filter OFF + confiança | n/a |
| condition_on_previous | False | — |
| idioma | `pt` fixo | — |
| initial_prompt | vocabulário da casa | não |
| normalização | ganho pelo pico (teto 20×) | não |
| gates | volume calibrado + no_speech/logprob + anti-alucinação (3 listas) | RMS fixo |
| latência | 0,39 s GPU / ~1,6 s CPU / 0,7 s base | medir |

Para o hardware (Ryzen 5600X, 32 GB, RX 9060 XT 16 GB — **AMD, sem CUDA**):
`small` int8 CPU é o teto honesto hoje (large-v3 CPU seria ~5–10 s); DirectML/ROCm
exigem validação antes de qualquer promessa. Nada a instalar nesta missão.

---

## 22. TTS

Ordem CyberBot: **Kokoro local** (padrão, ~330 MB, GPU ~10×; primeiro som rápido com
conexão pré-aquecida) → OpenAI streaming (~1,1 s 1º som, por personagem) → Charon/
Gemini Live (3,7 s) → Edge?/estúdio via VPS → SAPI?/fallback. Chat escrito **no
primeiro som** (`ao_primeiro_som`), nunca antes; diário anota respostas; mic fecha
pelo tempo da fala + folga (anti-eco). Golden: edge-tts (rede, 5–12 s medidos) →
SAPI. Quick win: pré-aquecer conexão + escrever no chat no 1º som + fechar mic por
duração (padrões, não motores).

---

## 23. Background

CyberBot: threads por fala/tarefa + jobs com estado/progresso/cancelamento (vídeo,
WhatsApp watchers, alertas, silencios) + `asyncio` p/ Live + relay. Golden TaskManager:
SQLite, DAG, 8 workers, timeout global, cancelamento cooperativo, recovery — modelo
mais rigoroso; usar como base e copiar a superfície (status/andamento/cancelar por voz).

---

## 24. Local vs Server

| Função | CyberBot | Golden (alvo) |
|---|---|---|
| Brain | VPS Codex / Gemini cliente (B) | cloud Groq/OR (A); Ollama local |
| STT | local whisper (A) | local whisper (A) |
| TTS | local Kokoro (A) | edge (C); SAPI local |
| Vision | Gemini/VPS (B) | Ollama local (A, lento) |
| Computer Use | local UIA+visão (A) | — |
| Image/Edit | VPS privada (B) | — (C) |
| Video | plano VPS + ffmpeg local (B+A) | — |
| WhatsApp | bridge local (A) | — |
| Browser | real + Playwright local (A) | (playwright futuro = A) |
| Memory | arquivos locais (A) | SQLite local (A) |

A= reimplementável · B= depende de serviço privado · C= precisa provider externo.

---

## 25. MCP

**CYBERBOT NÃO USA MCP** (zero ocorrências em 70 arquivos). Integração por chamadas
diretas de função e bridge local. Avaliação: MCP agregaria pouco ao Golden hoje —
o gargalo é latência de roteamento, não descoberta de tools. Reavaliar quando houver
providers externos plugáveis. (Não implementar.)

---

## 26. Latency (tabela)

| Provider/modelo/papel | Latência observada (código) | Timeout | Fallback |
|---|---|---|---|
| Codex VPS direto | 1,4 s | diag textual | Gemini |
| Gemini flash (conversa) | 0,7–1,9 s; papo 1,39 s | 429: 45 s/24 h/`retryDelay` | OpenAI/Codex |
| OpenAI stream (voz) | 1º som ~1,1 s | — | Kokoro |
| Kokoro local | < edge; 0,65 s c/ conexão | — | — |
| Charon Live (voz) | 1º som 3,7 s; sessão 6,1 s | reconexão | Kokoro |
| Whisper large-v3 GPU | 0,39 s/frase | — | small CPU 1,6 s |
| Imagem (VPS) | 75–92 s | 960 s | — |
| Site/leads (VPS) | 6–8 min / 3–5 min | 960/1200 s | — |
| Vídeo (ffmpeg local) | variável; 1 job | cancel cooperativo | — |
| Golden Groq | s (rápido) | 8 s/tent. | OpenRouter |
| Golden Ollama | ~21 s trivial; 45 s+ | 45 s | — |

Golden vs CyberBot por área e timeouts: equivalentes em brain; CyberBot vence em
voz (Live/streaming), visão (cloud) e TTS (local); Golden vence em gestão de
background (TaskManager) e privacidade local.

---

## 27. Top 10 Quick Wins (só comprovados)

**#1 Resposta final da tool sem 2ª IA** — Alto/Baixo/Baixo — `screen_process`,
`_responder_curto` — Golden: estender fast-path a tools de leitura.
**#2 ACK com tempo real por job** — Alto/Baixo/Baixo — `_aviso_de_demora`,
`_TEMPOS_DO_TRABALHO` — Golden: avisar na TaskManager com tempos medidos.
**#3 Chat escrito no 1º som do TTS** — Médio/Baixo/Baixo — `ao_primeiro_som` —
Golden: callback no início do play.
**#4 Papo sem tools no modelo** — Médio/Baixo/Baixo — `_e_papo` (2,73 s→1,39 s) —
Golden: CONVERSATION com catálogo vazio quando sem verbo de ação.
**#5 Relógio/consulta fora do prompt de sistema** — Médio/Baixo/Baixo — cache 99% —
Golden: não colocar valores mutáveis no system prompt.
**#6 STT: small + initial_prompt + gates** — Alto/Médio/Baixo — 0,4 s vs 80 s de
alucinação — Golden: mesmo padrão (CPU).
**#7 Pré-aquecer em paralelo à saudação** — Alto/Baixo/Baixo — 12,3 s→fala imediata —
Golden: warmup de clientes no boot do Desktop.
**#8 Boca × cérebro em paralelo** — Médio/Baixo/Baixo — TLS some do relógio —
Golden: pré-resolver TTS enquanto o LLM gera.
**#9 Fechar/abrir: verificar, não afirmar** — Médio/Baixo/Baixo — checagem de janela —
Golden: confirmar efeito antes de responder (onde barato).
**#10 Portão de áudio medido + backlog com descarte** — Médio/Baixo/Baixo — piso por
sala — Golden: calibrar SILENCE_RMS por ambiente + descartar backlog.

---

## 28. P0/P1/P2/P3 Roadmap

**P0 (enorme/baixo risco):** #1, #2, #5, #9. **P1 (alto ganho):** #3, #4, #6, #7, #8,
#10, superfície status/cancelar do TaskManager no Desktop/voz. **P2 (capacidades):**
browser híbrido (real + Playwright com perfil), bridge WhatsApp local, file pipeline
por tipo, computer use (porta + UIA-first + visão numerada), visão cloud opcional.
**P3 (acabamento):** diário de ações, teste de mic na config, diario de voz,
variedade de resposta, personas na voz.

---

## 29. Do Not Copy

Só o evidenciado: **(a)** credenciais/chaves embutidas ou saindo do servidor
(o deles não sai da VPS — não replicar atalho); **(b)** auto-instalação em runtime
(npm/pip dentro do fluxo — separar em setup); **(c)** clique por coordenada chutada
pelo modelo (usar UIA/semântica primeiro); **(d)** assumir NVIDIA/CUDA (quebra na AMD);
**(e)** espera de tarefa sem fim e sem contador (laco 1.0.25); **(f)** voz que se
auto-escuta sem guarda pós-fala; **(g)** sessão/QR/estado sem expiração; **(h)** tomar
tela/áudio sem porta de ativação e sem narrar.

---

## 30. Matriz de modelos (tarefa × CyberBot × Golden × recomendação)

| Tarefa | CyberBot | Golden | Recomendação |
|---|---|---|---|
| routing | regex+regras (0 IA) | Orchestrator regex (0 IA) | manter; importar lista de programas/comandos |
| conversation | Gemini→Codex VPS | Groq→OR→Ollama | manter; adicionar modo papo-sem-tools |
| planning | Codex VPS | Planner+TaskManager | manter (Golden mais rigoroso) |
| vision | Gemini/VPS | qwen2.5vl local | manter local; avaliar atalho cloud opcional |
| STT | large-v3/small | base | **small** + initial_prompt + gates |
| TTS | Kokoro/OpenAI/Charon | edge/SAPI | pré-aquecer; 1º-som→chat; avaliar Kokoro CPU depois |
| coding | Codex VPS | Groq qwen3 | manter |
| image/video plan | VPS | — | provider externo quando houver fase própria |

---

## 31. O que é copiável (A/B/C/D)

A (reimplementável já): fast-paths extras (fechar, desfazer, chegada de arquivo,
capacidade), TOOL_RESULT_POLICY, ACK com tempos, 1º-som→chat, papo-sem-tools,
valores fora do system prompt, STT small+vocab+gates, warmup paralelo, boca×cérebro,
verificar-antes-de-afirmar, portão de áudio medido, UIA-first, bridge-WhatsApp-local
(infra), diário de ações, janela de ativação 30 s, cooldown de cota por código.
B (serviço privado): Codex VPS, vozes de estúdio/OpenAI via relay, visão via VPS.
C (provider externo): imagem/edição, TTS neural alternativo, visão cloud.
D (não recomendado): itens da seção 29.

---

## 32. Velocidade: modelo vs engenharia (resposta explícita)

- **Modelo:** ~10× no caso medido (OR-grátis 10–16 s vs Gemini 0,7–1,9 s), mas é custo
  de fila/cota, não técnica.
- **Roteamento/fast path:** de 5–29 s para ~0 s em abrir/fechar; 5,75 s→0,001 s no
  relógio. Maior ganho absoluto.
- **Skip second Brain:** −1 volta (~2 s) por leitura; −50% no relógio com tool.
- **Paralelismo:** −0,5 s/fala (whisper×rabicho); −1,2 s na 1ª frase (TLS); −9 s no boot.
- **Background:** jobs longos somem do caminho crítico (imagem/vídeo/site).
- **Preload:** whisper/Kokoro/cérebro/voz prontos antes da 1ª fala.
- **UX percebida:** ACK imediato + HUD por ferramenta + texto no 1º som fazem
  75 s–8 min parecerem instantâneos.
- Sem evidência para percentuais globais — acima estão os números do código.

---

## 33. Recommended Golden Architecture (alvo, não implementar)

Manter o núcleo (Orchestrator→ModelRouter→TaskManager→Service→Security→Audit,
SHADOW) e adicionar: camada de portas determinísticas antes do Brain (fechar,
desfazer, chegada de arquivo, capacidade, papo); TOOL_RESULT_POLICY; ACK com tempos
reais + HUD por tool; chat-no-1º-som; STT small+vocabulário+gates; warmup paralelo;
superfície de jobs (status/cancelar por voz e Desktop); diário de ações; depois,
capacidades P2 na ordem browser → arquivos → WhatsApp → visão cloud opcional →
computer use → imagem/vídeo com provider próprio.
