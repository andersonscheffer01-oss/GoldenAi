# Golden AI - Codex Capability Audit V1

Data: 2026-08-13

Escopo auditado: Golden AI local em `C:\GoldenAI`, baseline Gold & Black V2 + Core V3 + Central de Execucao/Permissoes V1.

## Evidencias Executadas

- Baseline confirmada por SHA256 antes da fase.
- Regressao Core apos Parte A: `198 tests`, `OK`.
- Projeto seguro criado: `C:\GoldenAI\projetos\_capability_audit`.
- Mapeamento real de arquivos: `Get-ChildItem -Recurse`.
- Busca real de simbolos/texto: `rg -n "def |class |import |from |MAX_DISCOUNT|reserve|total_with_tax|OnInit|OnTick|input"`.
- Validacao Python real: `py_compile` em `pricing.py`, `inventory.py`, `pipeline.py`: OK.
- Teste real do fixture: `python -m unittest discover -s tests -v`: 3 falhas.
- CodingTask real em sandbox para `pricing.py`: criada, analisada, diff preparado, status `AWAITING_APPROVAL`.
- MQL5 fixture lido/inspecionado: `mql5_fixture\AuditFixture.mq5`, com `input`, `OnInit`, `OnTick`; sem Strategy Tester real.

## Matriz De Capacidades

| CAPACIDADE | STATUS | EVIDENCIA | TESTE EXECUTADO | LIMITACAO | RISCO | PROXIMA ACAO |
|---|---|---|---|---|---|---|
| Entender pedido de programacao | SUPPORTED | CodingTask criou analise/plano | `CodingService.create_task/analyze_and_plan` | Heuristica local, sem LLM tool planner completo | MEDIUM | Expandir analisador multi-arquivo |
| Mapear estrutura de projeto | SUPPORTED | 12 itens listados no fixture | `Get-ChildItem -Recurse` | Ainda nao exposto como tool conversacional rica | LOW | Criar tool `project_map` |
| Listar arquivos | SUPPORTED | Lista real do fixture | `Get-ChildItem -Recurse` | Interface usa Projetos visualmente | LOW | Conectar ao feed por tool |
| Procurar texto/simbolo | SUPPORTED | `rg` encontrou funcoes/imports/OnTick | `rg -n` | Motor ainda nao tem wrapper rg completo | LOW | ToolRegistry para search |
| Ler arquivos relevantes | SUPPORTED | Arquivos do fixture e MQL5 lidos | leitura local autorizada | Sem leitura por intervalo no chat | LOW | Tool `read_lines` |
| Seguir fluxo multi-arquivo | PARTIAL | Falhas envolvem `pipeline -> inventory/pricing/config` | unittest + rg | Coding V1 prepara 1 arquivo por tarefa | MEDIUM | Orquestrador de patch multi-arquivo |
| Entender imports/dependencias | PARTIAL | imports detectados por rg | rg/import scan | Sem grafo persistido de dependencias | LOW | Construir grafo Python |
| Identificar configs/build scripts/testes | SUPPORTED | `pyproject.toml`, `tests/test_pipeline.py` detectados | listagem + rg | Sem parser dedicado de pyproject | LOW | Tool de manifestos |
| Reproduzir erro | SUPPORTED | 3 testes falharam | `unittest discover -v` | Depende de comando permitido/local | MEDIUM | Registrar saida completa no feed |
| Ler saida/stack trace | SUPPORTED | Saida unittest lida e resumida | terminal/test output | Feed guarda resumo curto | LOW | Artefato de logs por task |
| Diagnostico tecnico | PARTIAL | Falhas identificadas: subtotal, reserva exata, desconto maximo | unittest + codigo | Diagnostico automatico ainda limitado | MEDIUM | Agente Reviewer/Programmer com search tools |
| Preparar correcao | PARTIAL | Diff parcial preparado para `pricing.py` | `CodingService.replace_working_text` | Nao resolve todos os bugs sozinho | MEDIUM | Multi-file patch planner |
| Criar patch/diff | SUPPORTED | Diff real em sandbox | CodingTask `AWAITING_APPROVAL` | Um arquivo por fluxo atual | MEDIUM | Diff multi-arquivo |
| Trabalhar em sandbox | SUPPORTED | `C:\GoldenAI\workspace\<task>\working` | CodingWorkspace | Sandbox sem suite test integrada por projeto | LOW | Runner por projeto |
| Pedir aprovacao | SUPPORTED | ApprovalRequest generico + CodingTask approval | testes Parte A + CodingTask | Modal visual basico | MEDIUM | UX de diff integrado |
| Aplicar alteracao aprovada | SUPPORTED | Coding V1 existente validado por regressao | 198 tests OK | Nao aplicado no fixture por escopo de auditoria | MEDIUM | Aplicar apenas em tarefas futuras aprovadas |
| Executar validacoes | SUPPORTED | `py_compile` OK | py_compile | Sem matriz por linguagem ampla | MEDIUM | Runner configuravel |
| Rodar testes | SUPPORTED | unittest fixture e regressao Core | unittest | pytest apenas se instalado/projeto tiver | MEDIUM | Detectar runners automaticamente |
| Build/compile permitido | PARTIAL | py_compile; MQL5 estrutural por validator | py_compile; leitura MQL5 | MetaEditor nao exercitado nesta auditoria | MEDIUM | Integrar compile MQL5 seguro se autorizado |
| Detectar regressao | SUPPORTED | Regressao Core 198 OK; fixture 3 FAIL | unittest | Sem comparador historico de baseline por task | MEDIUM | Relatorio de regressao por task |
| Iterar se patch falhar | PARTIAL | Arquitetura suporta nova tarefa; nao tem loop automatico | CodingTask + testes | Nao ha autocorrecao multi-pass segura | MEDIUM | Loop controlado com aprovacao |
| Rollback | SUPPORTED | CodingService tem checkpoint/rollback; regressao cobre | testes existentes | Nao disparado no fixture | HIGH | Teste dedicado por projeto multi-arquivo |
| Preservar alteracoes do usuario | SUPPORTED | Source hash validado antes de apply | CodingService | Um arquivo por task | HIGH | Hash set multi-arquivo |
| Nao sobrescrever trabalho externo | SUPPORTED | Hash original/diff hash checados | CodingService | Granularidade por arquivo | HIGH | Lock/manifest por task |
| Resumir feito/limitacoes | SUPPORTED | Relatorio final + docs | esta auditoria | Manual nesta fase | LOW | Gerador automatico de relatorio |
| Internet research | NOT_IMPLEMENTED | Nenhuma tool habilitada | politica da fase | Nao implementar nesta fase | HIGH | Documentar, nao ativar |
| Downloads automaticos | NOT_IMPLEMENTED | Sem capability | politica da fase | Nao implementar nesta fase | HIGH | Documentar, nao ativar |
| PowerShell/CMD irrestrito | BLOCKED_BY_POLICY | PermissionMode nao cria run-any-command | testes FULL/capability inexistente | Execucao generica bloqueada | HIGH | Manter allowlist |
| Real MT5 trading | BLOCKED_BY_POLICY | CRITICAL bloqueado | teste CRITICAL | Sem ordens reais | CRITICAL | Manter bloqueado |

## Scores Por Area

| Area | Score | Evidencia |
|---|---:|---|
| Project Understanding | 3 | Fixture mapeado, configs/testes localizados |
| Code Search | 3 | `rg` real executado com resultados |
| Code Reading | 3 | Arquivos Python e MQL5 lidos |
| Debugging | 2 | Falhas reproduzidas e localizadas, diagnostico ainda parcial |
| Editing | 3 | Sandbox/diff real em CodingTask |
| Validation | 3 | `py_compile` e validacao Coding V1 |
| Testing | 3 | `unittest` do fixture e regressao Core |
| Multi-file Work | 2 | Fluxo analisado, patch atual e de 1 arquivo |
| MQL5 | 2 | Leitura/estrutura OK; sem compile MetaEditor nesta auditoria |
| Python | 3 | py_compile, unittest e CodingTask |
| Quant | 3 | Regressao preservada; Quant module reachable |
| Safety | 4 | READ_ONLY/ASK/AUTO_SAFE/FULL testados; CRITICAL bloqueado |
| Permissions | 4 | 30 testes da Parte A OK |
| Auditability | 4 | AuditLogger + execution_events + approvals persistidos |
| Autonomy | 2 | Prepara diff, mas nao tem loop autonomo multi-arquivo seguro |

## Resultado Do Fixture

Falhas reais encontradas:

1. `subtotal()` soma quantidade e preco em vez de multiplicar.
2. `reserve()` rejeita estoque exato por usar `<=`.
3. `validate_discount()` ignora `MAX_DISCOUNT`.
4. `total_with_tax()` retorna apenas imposto, nao total com imposto.

Patch preparado em sandbox nesta auditoria:

- `pricing.py`: `return order.quantity + order.unit_price` -> `return order.quantity * order.unit_price`.
- Status: `AWAITING_APPROVAL`.
- Observacao: patch propositalmente parcial; nao resolve todos os testes.

## Capacidades Nao Inventadas

- Internet irrestrita: `NOT_IMPLEMENTED`.
- Downloads automaticos: `NOT_IMPLEMENTED`.
- Browser automation: `NOT_IMPLEMENTED`.
- Instalacao automatica: `NOT_IMPLEMENTED`.
- PowerShell/CMD irrestrito: `BLOCKED_BY_POLICY`.
- Acesso arbitrario ao disco: `BLOCKED_BY_POLICY`.
- Credenciais: `BLOCKED_BY_POLICY`.
- Ordens MT5 reais: `BLOCKED_BY_POLICY`.
