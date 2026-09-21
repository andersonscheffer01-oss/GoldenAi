# Golden AI - Capability Gaps V1

Data: 2026-08-13

## P0 - Fundamental

### Orquestrador de correcao multi-arquivo

- O que falta: Coding V1 prepara bem uma tarefa por arquivo, mas nao gera patch coordenado entre varios arquivos.
- Por que importa: bugs reais do fixture exigem `pricing.py`, `inventory.py` e possivelmente testes/config.
- Risco: aplicar correcao parcial e deixar regressao.
- Dependencias: project map, dependency graph, test runner por task, approval manifest multi-file.
- Sugestao: criar `CodingProjectTask` com lista de arquivos, hashes originais, diffs por arquivo e aprovacao atomica.
- Testes: fixture `_capability_audit` deve passar apos patch multi-arquivo aprovado.

### Runner de testes por projeto

- O que falta: detectar comando de teste do projeto e associar saida completa ao task_id.
- Por que importa: sem isso a Golden nao fecha ciclo diagnostico -> patch -> teste.
- Risco: validar apenas `py_compile` quando os testes funcionais ainda falham.
- Dependencias: leitura de `pyproject.toml`, allowlist de comandos, ExecutionService.
- Sugestao: `ProjectTestRunner` com comandos permitidos e timeout.
- Testes: unittest/pytest quando presentes, falha e sucesso registrados no feed.

## P1 - Importante

### Search/Read tools conversacionais

- O que falta: wrappers formais para listar arquivos, rg, ler intervalo e metadados via ToolRegistry.
- Por que importa: agentes precisam evidenciar busca/leitura sem depender de heuristicas internas.
- Risco: respostas menos rastreaveis.
- Dependencias: PermissionManager, ExecutionService.
- Sugestao: tools READ: `project_list`, `project_search`, `read_file_range`.
- Testes: eventos READ/SEARCH no feed e bloqueio de caminhos externos.

### Diff viewer e aprovacao com escopo

- O que falta: modal visual com botao Ver diff e escopos claramente ligados ao task_id.
- Por que importa: o usuario precisa aprovar com contexto.
- Risco: aprovar acao errada.
- Dependencias: approval_requests, CodingTask diff.
- Sugestao: painel Gold & Black dedicado de aprovacao.
- Testes: permitir uma vez, permitir tarefa, negar, reiniciar sem aprovacao permanente.

### Grafo de dependencias Python

- O que falta: extrair imports locais e fluxo entre modulos.
- Por que importa: multi-file reasoning depende disso.
- Risco: diagnostico incompleto.
- Dependencias: ast, project map.
- Sugestao: parser AST read-only.
- Testes: fixture deve mapear `pipeline -> inventory/pricing/config/models`.

## P2 - Melhoria

### Relatorio automatico de auditoria

- O que falta: gerar matriz e scores automaticamente a partir de eventos.
- Por que importa: reduz trabalho manual e aumenta reprodutibilidade.
- Risco: relatorio inconsistente se feito manualmente.
- Dependencias: execution_events, test_results.
- Sugestao: `CapabilityAuditService`.
- Testes: Markdown deterministico com evidencias.

### MQL5 compile seguro

- O que falta: fluxo MetaEditor mais rastreavel para fixtures autorizados.
- Por que importa: MQL5 e central no projeto.
- Risco: tocar MT5 real por engano.
- Dependencias: allowlist, fixture copy, PermissionMode.
- Sugestao: compilar somente arquivo em `projetos/_capability_audit` ou sandbox.
- Testes: compile bloqueado fora do escopo, sem Strategy Tester real.

### UI do feed com detalhes copiaveis

- O que falta: expandir evento individual, copiar detalhes, abrir diff/test output.
- Por que importa: UX de execucao moderna.
- Risco: detalhes ficarem escondidos no terminal.
- Dependencias: ExecutionService metadata.
- Sugestao: painel lateral/drawer de evento.
- Testes: expandir/recolher/copiar.

## P3 - Opcional

### Browser/internet controlados

- O que falta: nao implementado nesta fase.
- Por que importa: pesquisa externa futura.
- Risco: alto se liberado sem sandbox.
- Dependencias: politica de rede, allowlist, auditoria.
- Sugestao: documentar antes de implementar.
- Testes: bloqueio por padrao.

### Instalacao automatica

- O que falta: nao implementado.
- Por que importa: algumas stacks precisam dependencias.
- Risco: alto.
- Dependencias: approval HIGH, lockfile, rollback.
- Sugestao: manter bloqueado ate politica dedicada.
- Testes: instaladores sempre exigem aprovacao ou bloqueio.
