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
- Computer Use 6D real validation is intentionally partial at the Save As boundary. The mission
  paused and resumed durably, completed Python and Ollama research, and verified the Notepad
  summary, but `C:\Users\Anderson\Documents\resumo_pesquisa.txt` was not authorized or created.
  A future continuation must obtain explicit authorization for that exact target and must not
  auto-resume or write another path.
- The Codex CUA helper failed to initialize in this session because its kernel asset path was
  unavailable; the product mission was nevertheless validated through the canonical
  `JarvisService` UIA/Playwright path.
