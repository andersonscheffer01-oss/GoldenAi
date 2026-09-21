# Ferramentas do Golden Jarvis

| Ferramenta | Risco | Confirmação | Função |
|---|---:|---:|---|
| `open_program` | LOW | Não | Abre programa da lista autorizada |
| `close_program` | MEDIUM | Não | Encerra programa autorizado |
| `open_path` | LOW | Não | Abre pasta ou arquivo existente |
| `system_status` | LOW | Não | Consulta CPU, memória e disco |
| `take_screenshot` | LOW | Não | Captura os monitores |
| `lock_windows` | MEDIUM | Sim | Bloqueia a sessão |
| `shutdown` | CRITICAL | Sim | Agenda desligamento |
| `restart` | CRITICAL | Sim | Agenda reinicialização |

Nenhuma ferramenta aceita código Python ou PowerShell produzido pelo modelo.
