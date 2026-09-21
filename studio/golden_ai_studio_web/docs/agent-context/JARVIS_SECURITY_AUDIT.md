# Auditoria de Segurança do Jarvis

- Parser do Brain opera fail-closed.
- Ferramentas inexistentes, campos extras, tipos errados e argumentos obrigatórios ausentes são rejeitados.
- `open_any_exe` bloqueia shells e hosts de script, valida o arquivo e classifica a localização.
- `kill_process` é HIGH, exige confirmação e bloqueia processos críticos.
- `delete_file` normaliza o caminho, exige confirmação e não remove diretórios.
- Confirmações expiram, são de uso único e guardam ferramenta mais argumentos normalizados.
- AuditLog sanitiza segredos recursivamente e resume payloads grandes/binários.
- Ações rejeitadas também são auditadas.
- Nenhum JSON do modelo usa `eval` ou `exec`.
