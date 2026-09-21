# MASTER CAPABILITY MAP - GOLDEN/JARVIS

> Canonical reference for Jarvis PC capabilities.
> Updated: 2026-09-19 | Status: VALIDATED & NORMALIZED

---

## ARCHITECTURE INVARIANTS

`
1 JarvisService | 1 ToolRegistry (64 tools) | 1 SecurityManager
1 Brain | 1 ModelRouter | 1 Orchestrator | 1 Gateway
`

No duplicate systems. No second Jarvis.

---

## STATUS DEFINITIONS

| Status | Meaning |
|--------|---------|
| WORKING_NOW | Connected to ToolRegistry, has tests or runtime evidence |
| CONNECTED_NOT_RUNTIME_TESTED | Wired to ToolRegistry but no test or recent validation |
| CODE_EXISTS_NOT_CONNECTED | In codebase but NOT in ToolRegistry |
| LEGACY_AVAILABLE | In server_agent.py only, can be migrated |
| PARTIAL | Some components exist but incomplete |
| MISSING | No implementation found |
| UNSAFE_DO_NOT_MIGRATE | Security risk, should NOT be exposed to LLM |
| OBSOLETE | Superseded by newer implementation |

---

## INCONSISTENCIES FIXED

| Item | Was | Corrected To | Reason |
|------|-----|-------------|--------|
| Golden Scanner | WORKING_NOW | CODE_EXISTS_NOT_CONNECTED | Not in ToolRegistry, only HTTP API |
| Golden Risk Engine | WORKING_NOW | CODE_EXISTS_NOT_CONNECTED | Not in ToolRegistry, only HTTP API |
| Golden Strategy | WORKING_NOW | CODE_EXISTS_NOT_CONNECTED | Not in ToolRegistry, only HTTP API |
| MT5 Connector | WORKING_NOW | CODE_EXISTS_NOT_CONNECTED | Not in ToolRegistry, only HTTP API |
| MT5 Trader | WORKING_NOW | CODE_EXISTS_NOT_CONNECTED | Not in ToolRegistry, only HTTP API |
| MT5 Backtest | WORKING_NOW | CODE_EXISTS_NOT_CONNECTED | Not in ToolRegistry, only HTTP API |
| Voice wake word | WORKING_NOW | PARTIAL | Daemon thread not started at construction |
| Voice barge-in | WORKING_NOW | PARTIAL | Disabled by default (JARVIS_BARGE_IN=0) |
| Voice streaming | WORKING_NOW | PARTIAL | Disabled by default (JARVIS_STREAMING_VOICE=0) |
| run_command | LEGACY_AVAILABLE | UNSAFE_DO_NOT_MIGRATE | shell=True with LLM input |
| read_file | MISSING | LEGACY_AVAILABLE | Exists in server_agent.py |
| write_file | MISSING | LEGACY_AVAILABLE | Exists in server_agent.py |
| clean_cache | MISSING | LEGACY_AVAILABLE | Exists in server_agent.py |
| clean_temp | MISSING | LEGACY_AVAILABLE | Exists in server_agent.py |
| find_programs | MISSING | LEGACY_AVAILABLE | Exists in server_agent.py |
| PDF tools | MISSING | LEGACY_AVAILABLE | read/write/edit/create PDF in server_agent.py |
| code analysis | MISSING | LEGACY_AVAILABLE | analyze/edit/repair code in server_agent.py |
| GPU monitoring | MISSING | CODE_EXISTS_NOT_CONNECTED | jarvis_desktop/gpu.py exists, not in ToolRegistry |

---

## RAW SHELL SAFETY AUDIT

| Item | File | Severity | Status |
|------|------|----------|--------|
| run_command (shell=True + LLM input) | server_agent.py:1210 | CRITICAL | UNSAFE_DO_NOT_MIGRATE |
| PowerShell URI interpolation | voice_service.py:1014 | CRITICAL | UNSAFE_DO_NOT_MIGRATE |
| _open_any_exe (any path) | service.py:1192 | HIGH | WORKING_NOW (dynamic_risk=True) |
| shutil.rmtree (LLM path) | server_agent.py:1228 | HIGH | UNSAFE_DO_NOT_MIGRATE |
| MetaEditor PS escaping | server_agent.py:1458 | HIGH | UNSAFE_DO_NOT_MIGRATE |
| os.system in tests | test_phase6_2a_*.py | MEDIUM | LOW (test only) |
| PowerShell audio playback | audio_player.py:66 | MEDIUM | CONNECTED_NOT_RUNTIME_TESTED |
| eval/exec in Python | NONE found | N/A | CLEAN |

---

## CAPABILITY MATRIX BY CATEGORY

### CAT 1: WINDOWS / PROGRAMAS (20 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Abrir programa autorizado | open_program | WORKING_NOW | LOW | NO |
| Fechar programa | close_program | WORKING_NOW | MEDIUM | NO |
| Abrir qualquer exe | open_any_exe | WORKING_NOW | HIGH | DYNAMIC |
| Minimizar todas janelas | minimize_all | WORKING_NOW | LOW | NO |
| Mostrar desktop | show_desktop | WORKING_NOW | LOW | NO |
| Centro de acoes | open_control_center | WORKING_NOW | LOW | NO |
| Janela ativa atual | get_active_window | WORKING_NOW | LOW | NO |
| Fechar janela ativa | close_active_window | WORKING_NOW | MEDIUM | NO |
| Maximizar janela | maximize_window | WORKING_NOW | LOW | NO |
| Minimizar janela | minimize_window | WORKING_NOW | LOW | NO |
| Alternar janela | switch_window | WORKING_NOW | LOW | NO |
| Processos em execucao | list_processes | WORKING_NOW | LOW | NO |
| Encerrar processo | kill_process | WORKING_NOW | HIGH | YES |
| Verificar se programa aberto | is_running | WORKING_NOW | LOW | NO |
| Listar programas instalados | - | LEGACY_AVAILABLE | - | - |
| Procurar programa | - | LEGACY_AVAILABLE | - | - |
| Desinstalar programa | - | LEGACY_AVAILABLE | - | - |
| Servicos Windows | - | MISSING | - | - |
| Inicializacao Windows | - | MISSING | - | - |
| System tray | - | MISSING | - | - |

### CAT 2: ARQUIVOS / PASTAS (16 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Listar pasta | list_folder | WORKING_NOW | LOW | NO |
| Abrir arquivo | open_file | WORKING_NOW | LOW | NO |
| Abrir pasta | open_folder | WORKING_NOW | LOW | NO |
| Abrir qualquer caminho | open_path | WORKING_NOW | LOW | NO |
| Buscar arquivos | search_files | WORKING_NOW | MEDIUM | NO |
| Arquivos recentes | get_recent_files | WORKING_NOW | LOW | NO |
| Copiar arquivo | copy_file | WORKING_NOW | MEDIUM | NO |
| Mover arquivo | move_file | WORKING_NOW | MEDIUM | NO |
| Renomear arquivo | rename_file | WORKING_NOW | MEDIUM | NO |
| Excluir arquivo | delete_file | WORKING_NOW | HIGH | YES |
| Criar pasta | create_folder | WORKING_NOW | LOW | NO |
| Lixeira consultar | recycle_bin_status | WORKING_NOW | LOW | NO |
| Lixeira esvaziar | empty_recycle_bin | WORKING_NOW | CRITICAL | YES |
| Ler arquivo | - | LEGACY_AVAILABLE | - | - |
| Escrever arquivo | - | LEGACY_AVAILABLE | - | - |
| Compactar/ZIP | - | MISSING | - | - |

### CAT 3: CLIPBOARD / INPUT (6 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Ler clipboard | - | MISSING | - | - |
| Escrever clipboard | - | MISSING | - | - |
| Historico clipboard | - | MISSING | - | - |
| Teclado controlado | - | MISSING | - | - |
| Mouse controlado | - | MISSING | - | - |
| Hotkeys | - | MISSING | - | - |

### CAT 4: SISTEMA / HARDWARE (14 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| CPU/RAM/Disco | system_status | WORKING_NOW | LOW | NO |
| Hora atual | get_time | WORKING_NOW | LOW | NO |
| Data atual | get_date | WORKING_NOW | LOW | NO |
| Endereco IP | get_ip | WORKING_NOW | LOW | NO |
| Usuario Windows | get_username | WORKING_NOW | LOW | NO |
| Bateria | get_battery | WORKING_NOW | LOW | NO |
| Informacoes de rede | get_network | WORKING_NOW | LOW | NO |
| GPU/VRAM | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Temperaturas | - | MISSING | - | - |
| Monitores/resolucao | - | MISSING | - | - |
| Dispositivos USB | - | MISSING | - | - |
| Bluetooth/Wi-Fi | - | MISSING | - | - |
| Impressoras | - | MISSING | - | - |
| Portas/conexoes | - | MISSING | - | - |

### CAT 5: ENERGIA (6 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Bloquear Windows | lock_windows | WORKING_NOW | MEDIUM | YES |
| Desligar | shutdown | WORKING_NOW | CRITICAL | YES |
| Reiniciar | restart | WORKING_NOW | CRITICAL | YES |
| Sleep | - | MISSING | - | - |
| Hibernar | - | MISSING | - | - |
| Logoff | - | MISSING | - | - |

### CAT 6: MANUTENCAO (4 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Lixeira (CROSS-REF CAT 2 — counted once globally) | recycle_bin_status/empty | WORKING_NOW | LOW/CRITICAL | YES(empty) |
| Limpar cache | - | LEGACY_AVAILABLE | - | - |
| Limpar temp | - | LEGACY_AVAILABLE | - | - |
| Startup apps | - | MISSING | - | - |

### CAT 7: GAMING MODE (10 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Detectar jogo | - | MISSING | - | - |
| Abrir jogo | open_program | PARTIAL | - | - |
| Fechar apps desnecessarios | kill_process | PARTIAL | - | - |
| Mudar plano de energia | - | MISSING | - | - |
| Monitorar temperatura | - | MISSING | - | - |
| Reduzir processos background | - | MISSING | - | - |
| Silenciar notificacoes | - | MISSING | - | - |
| Ajustar volume | volume_set | WORKING_NOW | LOW | NO |
| Restaurar depois do jogo | - | MISSING | - | - |
| Perfil por jogo | - | MISSING | - | - |

### CAT 8: BROWSER (14 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Iniciar navegador | browser_open | WORKING_NOW | LOW | NO |
| Navegar para URL | browser_navigate | WORKING_NOW | MEDIUM | NO |
| Ler pagina | browser_read_page | WORKING_NOW | LOW | NO |
| Info da pagina | browser_get_page_info | WORKING_NOW | LOW | NO |
| Listar elementos | browser_get_elements | WORKING_NOW | LOW | NO |
| Clicar elemento | browser_click | WORKING_NOW | MEDIUM | NO |
| Digitar texto | browser_type | WORKING_NOW | LOW | NO |
| Rolar pagina | browser_scroll | WORKING_NOW | LOW | NO |
| Voltar/Avancar | browser_back/forward | WORKING_NOW | LOW | NO |
| Screenshot pagina | browser_screenshot | WORKING_NOW | LOW | NO |
| Health navegador | browser_health | WORKING_NOW | LOW | NO |
| Fechar navegador | browser_close | WORKING_NOW | LOW | NO |
| Download controlado | - | MISSING | - | - |
| Upload | - | MISSING | - | - |

### CAT 9: PESQUISA (3 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Pesquisa web | web_research | WORKING_NOW | LOW | NO |
| Pesquisa + memorizar | web_research_learn | WORKING_NOW | MEDIUM | NO |
| Cotacao moedas | get_exchange_rate | WORKING_NOW | LOW | NO |

### CAT 10: DOCUMENTOS (8 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Ler PDF | - | LEGACY_AVAILABLE | - | - |
| Buscar palavra em PDF | - | LEGACY_AVAILABLE | - | - |
| Editar PDF | - | LEGACY_AVAILABLE | - | - |
| Criar PDF | - | LEGACY_AVAILABLE | - | - |
| Ler TXT/MD | - | MISSING | - | - |
| Criar/editar TXT | - | MISSING | - | - |
| CSV/Excel | - | MISSING | - | - |
| OCR | - | PARTIAL | - | - |

### CAT 11: PROGRAMACAO (8 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Analisar codigo | - | LEGACY_AVAILABLE | - | - |
| Editar codigo | - | LEGACY_AVAILABLE | - | - |
| Reparar MQL5 | - | LEGACY_AVAILABLE | - | - |
| Claude Code Review | - | LEGACY_AVAILABLE | - | - |
| OpenCode Integration | - | PLANNED | - | - |
| Executar testes | - | MISSING | - | - |
| Git | - | MISSING | - | - |
| Lint/Build | - | MISSING | - | - |

### CAT 12: GOLDEN (12 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Golden Scanner | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| 47 Trading Setups | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Risk Engine | - | CODE_EXISTS_NOT_CONNECTED | CRITICAL | - |
| Strategy Engine | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Analysis Engines | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Monitor Service | - | CODE_EXISTS_NOT_CONNECTED | LOW | - |
| AI Radar | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Dashboard | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Config/API Keys | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Status Golden | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Iniciar/Parar componentes | - | MISSING | - | - |
| Perguntar ao Golden | - | MISSING | - | - |

NOTE: All Golden modules exist in code but are NOT registered in ToolRegistry.
Accessible only via server_agent.py HTTP API endpoints.

### CAT 13: MT5 / TRADING (16 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Conectar MT5 | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Status MT5 | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Cotacoes/Simbolos | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Posicoes abertas | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Enviar ordem | - | CODE_EXISTS_NOT_CONNECTED | CRITICAL | YES |
| Fechar posicao | - | CODE_EXISTS_NOT_CONNECTED | CRITICAL | YES |
| Backtest Python | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Backtest nativo MQL5 | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Listar EAs/Robos | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Analisar EA | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Comparar estrategias | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Otimizar SL/TP | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Chart Analysis | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Position Manager | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Trade Journal | - | CODE_EXISTS_NOT_CONNECTED | - | - |
| Compilar EA | - | CODE_EXISTS_NOT_CONNECTED | - | - |

NOTE: All MT5 modules exist in code but are NOT registered in ToolRegistry.
Skills router declares Route.MT5 and Route.TRADING but with empty tool tuples.

### CAT 14: VOZ (12 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| STT (Whisper) | voice.py | PARTIAL | - | - |
| TTS (Edge TTS) | voice.py | PARTIAL | - | - |
| TTS fallback (SAPI) | voice.py | PARTIAL | - | - |
| Wake word "Jarvis" | voice.py | PARTIAL | - | - |
| Conversa continua | voice_service.py | PARTIAL | - | - |
| Barge-in (Silero VAD) | voice_service.py | PARTIAL | - | - |
| Streaming voice | streaming/ | PARTIAL | - | - |
| Sentence chunker | streaming/ | PARTIAL | - | - |
| Turn manager | streaming/ | PARTIAL | - | - |
| Microfone recording | voice.py | PARTIAL | - | - |
| Selecao de voz | - | MISSING | - | - |
| Audio desktop/mobile | - | MISSING | - | - |

NOTE: Voice system fully coded but daemon thread not started at construction.
Requires explicit start(). Barge-in disabled by default.
Streaming disabled by default.

### CAT 15: VISAO (5 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Screenshot | take_screenshot | WORKING_NOW | LOW | NO |
| Screenshot janela | take_screenshot_window | WORKING_NOW | LOW | NO |
| Analisar tela (IA) | analyze_screen | WORKING_NOW | LOW | NO |
| Analisar imagem (base64) | vision.py | WORKING_NOW | LOW | NO |
| Computer Use | - | MISSING | - | - |

### CAT 16: MEMORIA (10 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Buscar memorias | memory_search | WORKING_NOW | LOW | NO |
| Guardar informacao | memory_remember | WORKING_NOW | MEDIUM | NO |
| Memorias recentes | memory_recent | WORKING_NOW | LOW | NO |
| V1 Legacy Memory | GoldenMemoryManager | WORKING_NOW | - | - |
| V2 Memory Engine | GoldenMemoryEngine | WORKING_NOW | - | - |
| Knowledge Graph | V2 Engine | WORKING_NOW | - | - |
| Obsidian Vault | V2 Vault | WORKING_NOW | - | - |
| Hybrid Retrieval | V2 Retriever | WORKING_NOW | - | - |
| Research + Learn | V2 Research | WORKING_NOW | - | - |
| Project Memory | V2 ProjectMemory | WORKING_NOW | - | - |

### CAT 17: AUTOMACOES (2 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| Multi-tool sequencia | - | MISSING | - | - |
| Workflows agendados | - | MISSING | - | - |

### CAT 18: MOBILE / REMOTE (10 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| WebSocket Gateway | gateway.py | WORKING_NOW | - | - |
| Device Pairing | device_pairing.py | WORKING_NOW | - | - |
| Per-device Tokens | auth.py | WORKING_NOW | - | - |
| Device Management | gateway.py | WORKING_NOW | - | - |
| Session Resume | sessions.py | WORKING_NOW | - | - |
| LAN Dual-bind | gateway.py | WORKING_NOW | - | - |
| SSL/WSS | gateway.py | WORKING_NOW | - | - |
| CORS | cors.py | WORKING_NOW | - | - |
| Idempotency | gateway.py | WORKING_NOW | - | - |
| Rate Limiting | auth.py | WORKING_NOW | - | - |

### CAT 19: SEGURANCA (8 capabilities)

| Capability | Current Tool | Status | Risk | Confirm |
|------------|-------------|--------|------|---------|
| SecurityManager | security.py | WORKING_NOW | - | - |
| ToolRegistry Gate | registry.py | WORKING_NOW | - | - |
| Confirmation Flow | security.py + gateway | WORKING_NOW | - | - |
| Audit Log | audit.py | WORKING_NOW | - | - |
| Risk Engine (trading) (CROSS-REF CAT 12 — counted once globally) | risk_engine.py | CODE_EXISTS_NOT_CONNECTED | - | - |
| Kill Switch | golden_scanner.py | CODE_EXISTS_NOT_CONNECTED | - | - |
| Data Classification | models.py | WORKING_NOW | - | - |
| Secret Local-Only | orchestrator | WORKING_NOW | - | - |

---

## FINAL COUNTS (RECALCULATED FROM MATRIX ROWS)

Method: each capability row in the 19-category matrix counted exactly once.
Raw matrix rows: 184. Cross-listed duplicates removed: 2 (Lixeira CAT 6 → counted in CAT 2; Risk Engine CAT 19 → counted in CAT 12).

| Status | Count |
|--------|-------|
| WORKING_NOW | 83 |
| CONNECTED_NOT_RUNTIME_TESTED | 0 |
| CODE_EXISTS_NOT_CONNECTED | 28 |
| LEGACY_AVAILABLE | 15 |
| PARTIAL | 13 |
| MISSING | 43 |
| UNSAFE_DO_NOT_MIGRATE | 0 |
| OBSOLETE | 0 |
| TOTAL_UNIQUE_CAPABILITIES | 182 |

Check: 83 + 0 + 28 + 15 + 13 + 43 + 0 + 0 = 182 = TOTAL_UNIQUE_CAPABILITIES.

Per-status breakdown (by category):
- WORKING_NOW (83): CAT 1 (14) + CAT 2 (13) + CAT 4 (7) + CAT 5 (3) + CAT 7 (1) + CAT 8 (12) + CAT 9 (3) + CAT 15 (4) + CAT 16 (10) + CAT 18 (10) + CAT 19 (6)
- CODE_EXISTS_NOT_CONNECTED (28): CAT 4 GPU (1) + CAT 12 (10) + CAT 13 (16) + CAT 19 Kill Switch (1)
- LEGACY_AVAILABLE (15): CAT 1 (3) + CAT 2 (2) + CAT 6 (2) + CAT 10 PDF (4) + CAT 11 code (4)
- PARTIAL (13): CAT 7 gaming (2) + CAT 10 OCR (1) + CAT 14 Voice (10)
- MISSING (43): CAT 1 (3) + CAT 2 (1) + CAT 3 (6) + CAT 4 (6) + CAT 5 (3) + CAT 6 (1) + CAT 7 (7) + CAT 8 (2) + CAT 10 (3) + CAT 11 (4) + CAT 12 (2) + CAT 14 (2) + CAT 15 (1) + CAT 17 (2)
- CONNECTED_NOT_RUNTIME_TESTED (0): audio_player.py appears only in RAW SHELL AUDIT, not as a capability row

Normalization decisions (documented, not invented):
- "OpenCode Integration" (CAT 11) was PLANNED — PLANNED is not a defined status; normalized to MISSING (no implementation)
- "Monitorar temperatura" (CAT 7) kept DISTINCT from "Temperaturas" (CAT 4): gaming version implies a continuous watch/alert loop, a different capability from a one-shot read
- The 4 UNSAFE items (run_command shell=True, PowerShell URI interpolation, shutil.rmtree LLM path, MetaEditor PS escaping) are RAW SHELL AUDIT entries, not capability rows — they do not enter the capability total and are never to be migrated

---

## READINESS BY CATEGORY

| Category | Working | Total | Readiness |
|----------|---------|-------|-----------|
| CAT 1 Windows/Programas | 14 | 20 | READY_CORE |
| CAT 2 Arquivos/Pastas | 13 | 16 | READY_CORE |
| CAT 3 Clipboard/Input | 0 | 6 | MAJOR_GAPS |
| CAT 4 Sistema/Hardware | 7 | 14 | PARTIAL |
| CAT 5 Energia | 3 | 6 | PARTIAL |
| CAT 6 Manutencao | 2 | 4 | PARTIAL |
| CAT 7 Gaming Mode | 2 | 10 | MAJOR_GAPS |
| CAT 8 Browser | 12 | 14 | READY_CORE |
| CAT 9 Pesquisa | 3 | 3 | READY_FULL |
| CAT 10 Documentos | 0 | 8 | MAJOR_GAPS |
| CAT 11 Programacao | 0 | 8 | MAJOR_GAPS |
| CAT 12 Golden | 0 | 12 | NOT_CONNECTED |
| CAT 13 MT5/Trading | 0 | 16 | NOT_CONNECTED |
| CAT 14 Voz | 0 | 12 | PARTIAL (coded, not runtime-proven) |
| CAT 15 Visao | 4 | 5 | READY_CORE |
| CAT 16 Memoria | 10 | 10 | READY_FULL |
| CAT 17 Automacoes | 0 | 2 | MAJOR_GAPS |
| CAT 18 Mobile/Remote | 10 | 10 | READY_FULL |
| CAT 19 Seguranca | 6 | 8 | READY_CORE |

---

## IMPLEMENTATION PHASES

### Phase A - Essential PC Control (NEXT, highest value)
- read_file / write_file (migrate from server_agent.py, with path validation)
- clipboard read / write (PowerShell Get-Clipboard / Set-Clipboard)
- GPU monitoring (connect jarvis_desktop/gpu.py to ToolRegistry)
- Temperatures (WMI MSAcpi_ThermalZoneTemperature or LibreHardwareMonitor)
- Sleep / hibernate (rundll32 / shutdown /h)

### Phase B - Golden/MT5 Integration (highest strategic value)
- Golden scanner/status tools registered in ToolRegistry (HTTP bridge to server_agent.py)
- MT5 status/quotes/positions tools (read-only first, Risk.LOW)
- MT5 order send / close position (Risk.CRITICAL, confirmation=True)
- Skills router: fill Route.MT5 / Route.TRADING empty tool tuples

### Phase C - Productivity
- Document tools: TXT/MD read/write, CSV/Excel
- ZIP compact/decompress
- Browser download/upload
- Executar testes / Git / Lint

### Phase D - Gaming Mode
- Game detection + profiles
- Power plan switch, notification suppression, background process reduction
- Temperature watch loop

### Phase E - Voice Activation
- Auto-start voice daemon after construction
- Enable barge-in (JARVIS_BARGE_IN=1) when validated
- Enable streaming voice (JARVIS_STREAMING_VOICE=1) when validated

### Deferred / Not planned
- UNSAFE items: never migrate run_command shell=True, PowerShell URI interpolation, shutil.rmtree without guard
- Computer Use, OCR full, automation workflows: reassess later

---

## VALIDATION STATE

- Tests: 126 passed / 0 failed
  - test_tool_aware_llm.py: 73
  - test_security_confirmation_fail_closed.py: 25
  - test_security_gate.py: 20
  - test_gateway.py: 8
- ToolRegistry: 64 tools (incl. recycle_bin_status, empty_recycle_bin)
- Security confirmation fail-closed: FIXED and tested
- Conceptual routing bypass: FIXED and tested
- Lixeira false-match guard: FIXED and tested

---

## END OF MAP
