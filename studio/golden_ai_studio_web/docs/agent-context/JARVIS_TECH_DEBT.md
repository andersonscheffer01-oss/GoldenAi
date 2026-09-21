# Dívida Técnica do Jarvis

## P1

- Timeout de thread não consegue interromper instantaneamente handlers bloqueados pelo sistema operacional.
- Cancelamento é cooperativo e impede novas etapas; handlers já iniciados precisam aderir ao token no futuro.
- Uso normal da voz ainda depende da página aberta.

## P2

- Criar configuração persistente para timeouts e políticas.
- Ampliar descrições dos parâmetros das ferramentas.
- Adicionar streaming de estados por SSE ou WebSocket.
- Criar Task Manager somente na fase apropriada.
- Adicionar relacionamento explícito entre memórias substituídas (`superseded_by`).
- Avaliar índice vetorial quando o volume ultrapassar a busca limitada em memória.
