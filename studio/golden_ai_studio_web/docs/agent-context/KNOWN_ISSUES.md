# Problemas Conhecidos

- O diretório atual não possui metadados Git.
- O handoff e os relatórios mencionados na entrada da fase 6.6 não existiam; foram criados nesta fase.
- Cancelamento de operação já entregue ao sistema operacional é apenas cooperativo.
- A captura de janela específica ainda usa captura de tela inteira.
- O endpoint Voice está operacional, mas `faster-whisper` não está disponível no Python 3.13 atual.
- Havia dois servidores na porta 8765; a instância antiga foi encerrada e somente o backend atualizado permanece.
- O diretório da aplicação continua sem metadados Git, portanto `git status/diff` não está disponível.
- O plugin opcional `system_info.py` requer `psutil`; sua ausência não afeta o Memory Core.
- O helper auxiliar de CUA do Codex não inicializou nesta sessão; a validação real foi executada pelo próprio `JarvisService` usando o caminho UIA/pywinauto do produto.
- A resolução nativa de Known Folder depende de Windows; em ambientes não-Windows o helper usa o diretório Documents do perfil para manter os testes portáveis.
- Computer Use 4D.1 depends on browser-controlled external state: Google may show anti-bot
  verification and Bing may retain a cookie-consent state after a safe reject attempt. The
  executor detects and audits these states, never solves CAPTCHA or bypasses anti-bot, and
  falls back only to the next bounded provider in the same visible Chrome session. Real
  OpenAI and Python missions completed through DuckDuckGo with three structured results.
- Computer Use 6D validation was partial at the Save As boundary. The mission paused and
  resumed durably, completed Python and Ollama research, and verified the Notepad summary.
  The later 6D.1 continuation received authorization for the exact target, but external desktop
  state closed/disappeared Notepad before the recovered document could be written, so
  `C:\Users\Anderson\Documents\resumo_pesquisa.txt` remains absent.
- The Codex CUA helper failed to initialize in this session because its kernel asset path was
  unavailable; the product mission was nevertheless validated through the canonical
  `JarvisService` UIA/Playwright path.
- Computer Use 6D.1 real recovery remains blocked by external desktop state: the Notepad
  process/window disappears when `TslGame.exe` (PUBG) retakes the foreground. The executor
  classifies the change, invalidates stale targets, preserves the verified MissionContext and
  fails closed before typing or saving. No `resumo_pesquisa.txt` was created.
- Computer Use 6D.2 intentionally pauses when an external application owns the foreground
  during recent human input. The real guard test returned `USER_EXTERNAL_APP` with
  `last_user_input_age_ms: 0`, created a durable pause checkpoint, and sent no focus or
  keyboard action. Explicit resume is required after the user releases the desktop.
- The current 6D.2 implementation is not CLOSED: the previous long mission has no active
  in-memory instance in the current service process, and the authorized
  `resumo_pesquisa.txt` has not been written.
- Computer Use 6D.3 structural persistence is implemented and tested, but its new real
  long-mission validation is intentionally deferred while the user is active on the desktop.
  Do not open applications, focus windows, send input, or reuse the old authorization until
  `REAL_USER_SESSION_REQUIRED` is cleared by explicit user authorization.
- The prior real 6D mission remains historical state only. A future validation must create a
  new mission from zero, research Python and Ollama again, persist the Python checkpoint,
  reconstruct through a new executor, and revalidate the exact authorized target before Save As.

## Computer Use 7D

- No remaining 7D condition-trigger issue is known. The historical failed condition task is
  retained in the canonical database for audit evidence and is terminal/non-redispatching.
- Legacy schema-v1 task databases under other runtime/work directories remain present but are
  non-active; the service uses the schema-v2 canonical store.

## Computer Use 8D.1

- The read-only Background Control Center is implemented and validated. It intentionally does
  not provide pause, resume, cancel, retry, schedule editing, notifications, or dashboard UI;
  those belong to later 8D stages.
- The control center bounds aggregate reads to the existing canonical task/run/approval schema.
  It does not migrate or modify legacy databases and does not touch `device_registry.json`.

## Computer Use 8D.2

- Safe task controls are implemented over the canonical scheduler. Pause blocks future
  dispatches and resume restores scheduler eligibility without direct dispatch; neither
  operation interrupts an active process.
- Cancel is terminal for future dispatches and requires a scoped single-use SecurityManager
  confirmation. Existing active approvals are preserved rather than consumed or deleted.
- The background task schema is now version 3 with an additive `paused_from_status` column;
  legacy task/run databases are not consolidated or deleted.
- Three historical `test_jarvis_hardening.py` cases can fail during Windows temporary-directory
  teardown because their `JarvisService` fixture is not closed. The assertions pass; the
  failure is a SQLite file lock outside the 8D.2 control path and remains intentionally
  unmodified in this phase.

## Computer Use 8D.3

- Task-run provenance is now schema version 4. The migration is additive and preserves
  legacy v3 task/run data; only `task_runs` receives retry/recovery relationship fields.
- Retry is explicit and bounded by `trigger_config.retry_budget` (default one). It creates
  a new `TaskRun` and never reopens the failed source run. A repeated request for the same
  source is idempotently blocked/identified rather than creating another child.
- Computer Use runs with a valid checkpoint and verified action receipts are recovery-only;
  they must resume through the existing mission path. `ACTION_IN_FLIGHT_UNKNOWN` and
  `SIDE_EFFECT_UNCERTAIN` are blocked and are never blindly replayed.
- A pending retry/recovery does not bypass a pause or cancellation. Cancellation marks
  pending retry/recovery attempts cancelled; pause leaves them pending but undispatchable.
- No real desktop validation is part of 8D.3. Existing Windows SQLite teardown failures in
  `test_jarvis_hardening.py` remain unrelated and were not changed.

## Computer Use 8D.4

- The notification foundation is derived and channel-neutral. It does not persist read or
  dismiss state yet; `NEW` is an observation status and dismiss is not task resolution.
- Schema v5 is required only because the existing `task_approvals` row had no durable
  approval/denial decision state. The migration is additive; no second approval database
  or notification engine exists.
- Legacy direct consumers may still consume an active pending approval through the existing
  scoped `consume_task_approval` contract. New approval-center decisions additionally block
  denied/stale rows and expose `APPROVED` state for the existing consumer path. Approval
  itself never dispatches a task or bypasses pause/cancel controls.
- Full-suite execution remains incomplete because the earlier live/integration collection
  stalled; focused 8D.4 plus 8D.1-8D.3 regression coverage passed.

## Computer Use 8D.5

- Scheduler health has no persisted heartbeat. `last_task_evaluation` is therefore `None`;
  `last_activity`, dispatch, and completion timestamps are derived only from existing task/run
  timestamps. An unbound control center reports `UNKNOWN`, never a fabricated healthy state.
- Health is diagnostic only. Stale claims and recovery eligibility are reported using the
  existing lease/recovery semantics, but health never calls recovery, retry, claim, dispatch,
  approval, or repair operations.
- A controlled full-suite attempt collected `1760` tests and failed after `51.58s` at
  `tests/live_smoke_test.py::test_streaming` during setup because fixture `question` is absent.
  This is a pre-existing live/integration test issue; no stall, deadlock, SQLite lock, or
  8D.5 resource leak was observed. It remains outside this phase.

## Computer Use 8D Closure

- `COMPUTER_USE_8D` is closed after the temporary-DB E2E/closure gate passed. The gate does
  not claim the unrelated full suite is green: the latest collection is `1763`, while the
  controlled run fails at live smoke setup because fixture `question` is missing.
- No automatic dismissal state was added. `DISMISS_PERSISTENCE: DEFERRED` remains an explicit
  product decision and does not affect approval, task, run, scheduler, or audit correctness.
- Existing general service lifecycle code contains pre-existing process-control paths used by
  restart/shutdown. The 8D task controls remain cooperative and introduced no unsafe process
  kill path.
# Computer Use 7D.1

- Internal background scheduling infrastructure is implemented and structurally
  validated, but no real scheduled Windows mission was started in this phase.
- Real foreground, keyboard, mouse, Chrome, Notepad, file-save, and user-idle
  validation must wait for an explicit stable user session. Stop marker:
  `REAL_USER_SESSION_REQUIRED`.
- Scheduled mission execution is intentionally routed through the existing
  `JarvisService.run_computer_mission` and `SecurityManager`; the scheduler never
  grants approvals or bypasses foreground/user-activity guards.
- Runtime SQLite files, build/dist artifacts, logs, uploads, and `device_registry.json`
  remain outside the 7D.1 commit scope.
