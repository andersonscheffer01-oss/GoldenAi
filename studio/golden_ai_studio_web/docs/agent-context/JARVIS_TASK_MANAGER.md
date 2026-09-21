# Golden Jarvis Task Manager Core

## Escopo

Núcleo persistente integrado ao CentralOrchestrator por `JarvisRuntimeCoordinator`. O Planner
gera um plano tipado e o Task Manager executa cada etapa somente via `JarvisService`, preservando
SecurityManager, Registry e AuditLog.

## Componentes

- `TaskPlan`: título, descrição, `PlanStep[]`, classificação, metadata e timeout global.
- `Planner`: usa o perfil DEEP do ModelRouter, recebe somente as tools da skill e exige JSON.
- `PlannerContracts`: valida IDs, limite de 50 etapas, dependências existentes e DAG sem ciclos.
- `TaskDatabase`: SQLite versionado, tarefas, etapas e eventos.
- `BackgroundJobRunner`: execução assíncrona com dependências e até oito workers configuráveis.
- `TaskManager`: fachada para criar, iniciar, cancelar, consultar, listar e encerrar o runner.

## Persistência

Banco: `jarvis/golden_tasks.db`. Schema: versão 1. Cada operação abre e fecha sua conexão,
usa WAL, rollback, busy timeout e queries parametrizadas. Eventos não guardam payloads completos.

Ao reiniciar, tarefas `RUNNING` ou `CANCEL_REQUESTED` tornam-se `INTERRUPTED`. Etapas em
execução também ficam `INTERRUPTED`. Uma retomada executa somente etapas incompletas e preserva
resultados já concluídos.

## Estados

Tarefa: `QUEUED`, `RUNNING`, `WAITING_CONFIRMATION`, `COMPLETED`, `FAILED`,
`CANCEL_REQUESTED`, `CANCELLED`, `INTERRUPTED`.

Etapa: `PENDING`, `RUNNING`, `WAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, `CANCELLED`,
`INTERRUPTED`, `BLOCKED`.

## Cancelamento e timeout

Tarefa em fila é cancelada imediatamente. Tarefa ativa recebe `CancellationToken`; executores
devem consultá-lo para interrupção rápida. O timeout é global para o plano. Threads bloqueadas
em chamadas do sistema não podem ser encerradas à força; o resultado tardio é ignorado.

## Segurança

Planos `SECRET`, argumentos com nomes de segredo, binários, data URI e textos acima de 8.000
caracteres são rejeitados. Credenciais futuras deverão ser passadas por referência segura.
O Task Manager não executa tools sozinho e não contorna SecurityManager.

## Testes

17 testes diretos cobrem contratos, ciclos, persistência, eventos, dependências, background,
falha, cancelamento, confirmação, recovery, shadow e integração multi-step segura.
