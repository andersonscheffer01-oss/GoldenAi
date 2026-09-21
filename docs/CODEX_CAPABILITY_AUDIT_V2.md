# Golden AI - Codex Capability Audit V2

Data: 2026-08-13

Escopo: reavaliacao parcial apos Programador Autonomo V2, focada nos gaps P0:

- Orquestrador de correcao multi-arquivo.
- Project Test Runner.
- Loop de correcao controlado em sandbox.

## Evidencias Novas

- Fixture seguro: `C:\GoldenAI\projetos\_capability_audit`.
- Baseline real: `unittest` detectou 3 falhas.
- Project map real: arquivos, manifests, testes, linguagens e imports locais.
- Dependency scan: `audit_app/pipeline.py` resolve `audit_app.inventory` e `audit_app.pricing`.
- Workspace multi-arquivo: `C:\GoldenAI\workspace\<task_id>\original|working|reports|diffs|tests|manifest.json`.
- Diff por arquivo: `pricing.py`, `inventory.py`, `config.py`, `tests/test_pipeline.py` em manifest rastreavel.
- Loop controlado: primeira iteracao parcial ainda falhou; segunda iteracao passou.
- Sandbox test: `PASSED`.
- Approval manifest atomico: hash liga task, project_root, source_hashes e diff_hashes.
- Aplicacao aprovada: checkpoints por arquivo, replace coordenado, post-test real.
- Rollback multi-arquivo: simulado em teste com post-validation failure.
- External change protection: hash mismatch bloqueia apply.
- Regressao Core final: `233 tests`, `OK`.

## Scores Atualizados

| Area | V1 | V2 | Evidencia |
|---|---:|---:|---|
| Debugging | 2 | 3 | Baseline unittest com 3 falhas capturadas e associadas ao fixture |
| Multi-file Work | 2 | 4 | `CodingProjectTask` corrige `pricing.py` e `inventory.py` em workspace multi-arquivo |
| Editing | 3 | 4 | Diffs por arquivo, manifest e approval hash atomico |
| Validation | 3 | 4 | Baseline, workspace e post-apply outputs persistidos |
| Testing | 3 | 4 | `ProjectTestRunner` detecta unittest e grava artefatos em reports |
| Autonomy | 2 | 3 | Loop controlado de ate 3 ciclos em sandbox, sem apply automatico |

Areas nao reavaliadas permanecem como em `CODEX_CAPABILITY_AUDIT_V1.md`.

## Status Dos Gaps P0

| Gap | Status V2 | Evidencia |
|---|---|---|
| Orquestrador de correcao multi-arquivo | SUPPORTED | `CodingProjectService.prepare_full_fix()` gera task, workspace, diffs e manifest |
| Runner de testes por projeto | SUPPORTED | `ProjectTestRunner` executa `python -m unittest discover -s tests -v` com output em reports |

## Limitacoes Mantidas

- O patch planner V2 e deterministico para o fixture Python desta fase; nao e ainda um planejador generico completo para qualquer projeto.
- Pytest e suportado somente se ja estiver instalado e indicado por config; nenhuma instalacao automatica foi feita.
- MQL5 nao foi expandido nesta fase alem de preservacao/regressao.
- Nao ha internet, downloads automaticos, shell irrestrito, Strategy Tester real ou ordens MT5 reais.
- Diff viewer visual ainda e simples; refinamento fica para P1.
