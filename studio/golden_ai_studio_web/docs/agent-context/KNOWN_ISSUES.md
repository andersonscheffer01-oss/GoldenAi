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
- Computer Use 4D real remains blocked by browser-controlled external state: Bing may show a
  cookie-consent dialog and Google may show anti-bot verification. The Browser Use executor
  detects these states, records them in AuditLog, and stops without accepting, solving CAPTCHA,
  or bypassing the barrier. Three valid search-result titles therefore require an authorized
  benign consent decision or a permitted result page without that barrier.
