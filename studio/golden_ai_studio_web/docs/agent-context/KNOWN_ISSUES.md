# Problemas Conhecidos

- O diretório atual não possui metadados Git.
- O handoff e os relatórios mencionados na entrada da fase 6.6 não existiam; foram criados nesta fase.
- Cancelamento de operação já entregue ao sistema operacional é apenas cooperativo.
- A captura de janela específica ainda usa captura de tela inteira.
- O endpoint Voice está operacional, mas `faster-whisper` não está disponível no Python 3.13 atual.
- Havia dois servidores na porta 8765; a instância antiga foi encerrada e somente o backend atualizado permanece.
- O diretório da aplicação continua sem metadados Git, portanto `git status/diff` não está disponível.
- O plugin opcional `system_info.py` requer `psutil`; sua ausência não afeta o Memory Core.
