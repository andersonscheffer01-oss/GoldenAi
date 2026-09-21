# Golden Memory M1.6 — Obsidian Bidirecional

**Data:** 2026-09-14
**Agente:** opencode
**Status:** CONCLUÍDO

## Resumo

Implementação completa de sincronização bidirecional entre SQLite
(GoldenMemoryEngine) e Vault Markdown (Obsidian), permitindo edição
externa de memórias pelo Obsidian com reconciliação segura.

## Arquitetura

```
Obsidian Editor
    ↓ (edita .md)
FileWatcher (polling, debounce 500ms)
    ↓ (detecta mudança)
SelfWriteToken (previne loops Jarvis)
    ↓ (confirma é edição externa)
VaultImporter
    ↓ (parse YAML, valida campos protegidos)
GoldenMemoryEngine.update()
    ↓ (atualiza SQLite canônico)
Re-projeta Vault (SYNCED)
    ↓
Vector/Graph reindex (derivado)
```

## Arquivos Criados

| Arquivo | Linhas | Função |
|---------|--------|--------|
| `jarvis_core/memory/v2/watcher.py` | 220 | FileWatcher polling + debounce + SelfWriteToken |
| `jarvis_core/memory/v2/importer.py` | 455 | VaultImporter: parse, validação, import pipeline |
| `jarvis_core/memory/v2/reconciler.py` | 210 | VaultReconciler: coordena watcher+importer+engine |
| `tests/test_jarvis_memory_v2_m16.py` | 650 | 30 testes cobrindo todos os cenários |

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `jarvis_core/memory/v2/__init__.py` | Novos exports: VaultWatcher, VaultImporter, etc. |

## Funcionalidades Implementadas

### File Watcher (`watcher.py`)
- Polling-based (sem dependência externa)
- Debounce configurável (default 500ms)
- SelfWriteToken: thread-local para marcar escritas Jarvis
- Detecta: created, modified, deleted, renamed

### Import Pipeline (`importer.py`)
- Parse seguro de Markdown com YAML frontmatter
- Validação de campos protegidos (id, managed_by, schema_version, created_at)
- Detecção de falsificação de YAML
- Rejeição de SECRET (nunca importa)
- Rejeição de SENSITIVE (política existente)
- Import via GoldenMemoryEngine.update() — nunca escreve direto no SQLite

### Reconciliador (`reconciler.py`)
- Coordena watcher + importer + engine
- Auto-import configurável
- Status completo com classificações
- Histórico de eventos (últimos 200)
- Resolve conflict: accept-canonical (reprojeta vault)

## Estados de Reconciliação

| Estado | Significado |
|--------|-------------|
| SYNCED | Arquivo e SQLite idênticos |
| DRIFT | Markdown mudou, SQLite não |
| CONFLICT | Ambos mudaram desde última sync |
| PENDING | SQLite atualizado, vault não |
| ERROR | Arquivo inválido ou operação falhou |
| IGNORED | Arquivo fora do gerenciamento Jarvis |

## Testes (30/30 pass)

- external_edit_normal
- no_change_accepted
- not_managed_ignored
- missing_id_error
- invalid_id_format_error
- self_write_not_looped
- debounce_coalesces
- drift_detected
- synced_when_unchanged
- conflict_both_changed
- invalid_frontmatter
- no_frontmatter
- protected_field_id_changed
- protected_field_managed_by_changed
- import_secret_yaml_rejected
- secret_rejected
- sensitive_not_projected_by_default
- rename_preserves_identity
- duplicate_note_id_finds_first
- delete_not_imported
- import_updates_projection_hash
- reconciler_survives_restart
- concurrent_edits_not_lost
- history_limit
- stats_tracking
- manual_import
- rebuild_vault
- start_stop
- status_when_stopped
- file_event_types

## Limitações Conhecidas

1. **Watcher é polling-based** — latência de ~2s, não usa watchdog/inotify
2. **Resolução manual de conflitos** — apenas accept-canonical implementado
3. **Vault production não populado** — apenas scaffold existe
4. **YAML parser mínimo** — não suporta objetos aninhados ou multi-line strings

## Validação

- `py_compile` OK: todos os arquivos
- 173 testes passam (M1.0-M1.6)
- 2 skipped (real Groq/Tavily smoke)
- Vault/DB de produção NÃO modificados
- Desktop V4 NÃO modificado
- Brain/Voice/Radar/MT5 NÃO modificados

## Próximo

- M1.7: aguardar autorização
- Possíveis melhorias: watchdog nativo, resolução automática de conflitos,
  vault production bootstrap
