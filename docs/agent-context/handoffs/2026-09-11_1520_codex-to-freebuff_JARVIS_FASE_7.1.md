# Handoff — Codex → Freebuff → Concluído

## Tarefa
Golden Jarvis Fase 7.1 — Memória finalizada (smoke test real das APIs incluído)

## Estado Final: CONCLUÍDA ✅
APIs validadas em servidor real (porta 8765, venv Python) em 2026-09-12.

## O que existe
- `jarvis_core/memory/` completo (SQLite versionado, sessions, episodic, semantic, embeddings, retrieval, manager).
- `GoldenMemoryManager` integrado ao JarvisService e Brain.
- 3 tools de memória no Registry: `memory_search`, `memory_remember`, `memory_recent`.
- 4 APIs ativas: `/api/jarvis/memory/status|search|remember|recent`.

## Correções desta rodada final
1. **`_api_jarvis_memory_registry` AttributeError (causa raiz):** a route table
   (`server_agent.py` ~linha 5346) registrava 8 rotas de memória, mas só 4 métodos
   existiam. As 4 extras (`health`, `registry`, `tool`, `clear-cache`) eram referências
   órfãs de edição parcial — sem frontend/testes/docs as citando. **Correção:** removidas
   as 4 rotas órfãs (não foram criados stubs vazios). Também corrigida linha "colada"
   na route table.
2. **Chat intermitente "Tool call inválido":** o LLM às vezes retorna formato abreviado
   `{"memory_remember": {...args}}`. `brain.py::_parse_llm_response` agora normaliza
   esse formato deterministicamente (chave única ≠ tool/args/response/steps, valor dict)
   ANTES da validação fail-closed. Nenhum afrouxamento de segurança: tool/args ainda
   passam pelo `_validate_plan` completo.
3. **psutil:** estava OK no venv (7.2.2, em requirements.txt linha 8). O erro anterior
   era o teste rodando com o Python do sistema (3.13) em vez do venv. Nada instalado.

## Testes (todos passando)
- Memory tests: 13/13
- Hardening tests: 14/14 (zero regressão da Fase 6.6)
- Smoke real das 4 rotas de memória: PASS (status/search/remember/recent + error paths)
- Regressão rotas antigas: chat PASS (5/5), brain/status PASS, voice/status PASS, vision/status PASS
- Semantic search real: OK (nomic-embed-text, fallback=None quando Ollama ativo)
- Deduplicação validada: 5 comandos repetidos de "lembre que..." viraram 1 memória

## Observações
- `memory/status` é leve: não acorda Ollama; mostra `semantic: degraded` honesto quando
  embedding indisponível e vira `ok` após primeiro uso real.
- Registro do `wmic` (obsoleto no Windows) foi documentado como melhoria para
  `list_processes` — não alterado nesta fase (ver JARVIS_TECH_DEBT.md).

## Próximo passo sugerido
Fase 7 está completa.

---

# ✅ FASE 8 CONCLUÍDA (2026-09-12) — Desktop Voice Service

Escuta de voz LOCAL sem navegador implementada e validada:

- **Criado:** `jarvis_core/voice_service.py` (thread daemon; wake word → Whisper →
  Brain → Registry/Tool → TTS nas caixas de som).
- **Auto-start:** `start_server()` inicia a escuta junto com o Golden (padrão RADAR).
  Desativável com `JARVIS_VOICE_SERVICE=0`.
- **APIs:** `/api/jarvis/voice-service/status|start|stop|speak`.
- **TTS:** edge-tts (neural, instalado no venv + requirements.txt) com fallback SAPI
  offline via pywin32.
- **Bug da Fase 3 corrigido:** `voice.py::process_voice_command` marcava interação
  antes do filtro → no daemon, ruído ambiente seria executado como comando.
  Corrigido e coberto por teste.
- **Testes:** 17 novos (mocks, sem microfone/TTS real). Suíte Jarvis completa: 44/44.
- **Smoke real:** serviço transcreveu fala real do microfone, ignorou sem wake word,
  falou nas caixas de som, zero tracebacks, rotas antigas intactas.
- **Documentação:** `docs/agent-context/JARVIS_VOICE_SERVICE.md`.

Próximas fases possíveis: seleção de microfone / wake word dedicada (openWakeWord),
painel de voz no dashboard, ou iniciar especialização trading do Jarvis.

---

# ✅ FASE 8.1 CONCLUÍDA (2026-09-12) — Dados Online / Cotações

Jarvis agora responde perguntas de cotação com dado REAL (nunca inventado):

- **Criado:** `jarvis_core/data/` (`providers.py`, `cache.py`, `market_data.py`) —
  provider trocável, cache TTL 30s, falha honesta com fallback stale marcado.
- **Tool:** `get_exchange_rate` (Risk LOW, llm_enabled) com aliases naturais
  (dólar→USD, euro→EUR, real→BRL, libra→GBP, iene→JPY, bitcoin, ouro...).
- **Provider atual:** AwesomeAPI (sem credencial, timeout 8s, chave uppercase USDBRL).
- **Brain:** system prompt reforçado — valor atual → SEMPRE a tool, nunca invenção.
- **Testes:** 22 novos com mocks; suíte Jarvis completa **66/66 OK**
  (hardening atualizado 46→47 catálogo / 45→46 LLM tools pela nova tool — esperado).
- **Smoke real:** USD/BRL R$ 5.1262 (83ms) · EUR/BRL R$ 5.94 · GBP/BRL R$ 6.93.
  E2E LLM: "qual a cotacao do dolar" → USD/BRL → "R$ 5.13. Fonte: awesomeapi".
- **Servidor live:** validado (`tools_from_registry: 46`, tool responde).
- **Docs:** `docs/agent-context/JARVIS_DATA.md`.

Bugs corrigidos durante a fase: cache deletava entrada expirada (fallback stale
nunca funcionava); singleton do MarketDataService fixava provider na criação
(set_provider não surtia efeito); parser procurava chave minúscula (API usa USDBRL).

Próximas fases possíveis: MT5Provider (cotações internas), notícias econômicas,
painel de cotações no dashboard.

---

# ✅ CORREÇÃO CENTRAL GOLDEN-PC (2026-09-12) — Roteamento para o JarvisBrain

## Causa raiz
A Central (`market.html` → `desktop_center.js`) enviava campo livre e voz para
`/api/desktop/action` → `JarvisService.execute_command()` → parser if/elif antigo
→ "Não entendi o comando. Tente: ...". O Brain (`/api/jarvis/chat`) nunca era
acionado pela Central.

## Correção (desktop_center.js)
- Campo de texto livre e voz do browser → **`askBrain()` → `/api/jarvis/chat`**
  (um só cérebro). Wake word "Jarvis/Golden" é removida antes de enviar.
- Botões rápidos (Notas/Calculadora/Arquivos/MT5) mantêm `/api/desktop/action`
  (determinístico, já passa por Security/Audit).
- Badge ESCUTA agora reflete estado REAL: `ATIVA · PC` (daemon VoiceService),
  `ATIVA · NAVEGADOR` (mic browser) ou `DESLIGADA`.
- Textos atualizados: "Diga Jarvis...", placeholder com exemplos de perguntas.
- `sw.js`: CACHE_NAME v2.1.0 → v2.2.0 (força atualização do JS antigo).

## Ajustes no backend descobertos pelos testes
- `brain.py`: regra de contexto brasileiro no prompt ("euro" sem par = EUR/BRL,
  antes o LLM mandava USD/EUR).
- `service.py`: tool `analyze_screen` com timeout 90s (visão leva 30–60s;
  antes estourava o default de 15s).
- `server_agent.py` (`_api_jarvis_chat`): tools que retornam `items` sem `message`
  (memory_recent) agora geram resposta legível.

## Testes na Central real (preview browser, TODOS PASS)
| Entrada | Resultado |
|---|---|
| "qual é a cotação do dólar" | `[get_exchange_rate] USD: R$ 5.13. Fonte: awesomeapi` |
| "quanto está o euro" | `[get_exchange_rate] EUR: R$ 5.94` |
| "Jarvis qual é a cotação do dólar" (com wake word) | PASS — wake word removida |
| "que horas são" | `[get_time] São 16:08:07.` |
| "abra calculadora" | `[open_program] Calculadora aberto.` |
| "veja minha tela" | `[analyze_screen]` descreveu a tela (timeout 90s OK) |
| "o que você lembra sobre mim" | `[memory_recent] Encontrei 2 memória(s).` |

AuditLog registra `executado` com o comando original em todos os casos.
Suíte Jarvis: **66/66 OK** (zero regressão). VoiceService: daemon ativo,
ouviu 30 falas, 0 erros, TTS tocando nas caixas de som.

## URLs validadas (HTTP 200 real)
- **JARVIS NO PC**: `http://127.0.0.1:8765/dashboard.html` (aba 🤖 Jarvis)
- **CENTRAL GOLDEN-PC**: `http://127.0.0.1:8765/market.html` (botão "Central")
- **LAN/iPhone**: INDISPONÍVEL — servidor faz bind em `127.0.0.1:8765` (somente
  loopback, testado HTTP 000 via 192.168.1.100). Mudar bind/firewall exige
  autorização do usuário (fase Remote Gateway futura).

## Limitações
- Follow-up contextual ("E o euro?" depois da cotação) NÃO é suportado:
  o Brain não mantém histórico entre comandos; cada pergunta é independente.
  O `is_conversation_active` do voice.py só mantém a wake word dispensada
  por 30s. Documentado como dívida (Task Manager/Planner futuro).
- LLM pode exceder 45s quando o Ollama está frio (primeira pergunta após
  muito tempo) — retry resolve.

Próximo passo sugerido (NÃO iniciar automaticamente): suporte a follow-up
contextual ou Remote Gateway para acesso LAN/iPhone.
