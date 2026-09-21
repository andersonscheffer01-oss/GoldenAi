# Golden AI - Vision / Attachments / External Access Audit V1

Data: 2026-08-13

## INTENT_ROUTING

Status: IMPLEMENTED / TESTED

- Classificador deterministico `IntentRouter` criado.
- Distingue pedido de execucao de conversa sobre acao.
- Smoke "Certo vou corrigir isso porque eu estou criando voce" nao cria CodingTask.

## EXTERNAL_PATH_APPROVAL

Status: IMPLEMENTED / TESTED

- `ExternalAccessService` criado.
- Arquivo externo por path gera ApprovalRequest antes de leitura.
- Allow Once, Allow Task e Deny cobertos por teste.
- READ externo nao vira WRITE.
- Pedido original continua apos aprovacao.

## ATTACHMENTS

Status: IMPLEMENTED / TESTED

- Botao +, file picker, drag/drop, Ctrl+V imagem, multiplos anexos, preview, remover antes de enviar.
- Storage: `C:\GoldenAI\datattachments\<session_id>`.
- SHA-256 calculado.
- Executaveis bloqueados.
- Attachment e tratado como dado nao confiavel.
- Attachment concede READ somente para a copia controlada, nao WRITE.

## VISION

Status: PARTIAL / TESTED

- VisionService, VisionEnvironment e VisionResult criados.
- Runtime detectado: ollama; disponivel: True.
- Modelo coder preservado: qwen2.5-coder:14b.
- Modelos instalados: qwen2.5-coder:14b, qwen2.5-coder:7b.
- Vision model escolhido: nenhum.
- VISION_SUPPORTED: False.
- VISION_AVAILABLE: False.
- GPU: AMD Radeon RX 9060 XT; VRAM reportada: 4293918720 bytes.
- RAM total: 17097474048 bytes; RAM livre: 9908826112 bytes.

Observacao: nao ha modelo multimodal local instalado. Nenhum download/instalacao foi executado. Portanto upload/preview de imagem esta implementado, mas entendimento visual real permanece indisponivel ate instalacao aprovada de modelo multimodal compativel.

## SECURITY

- Nenhuma ordem MT5.
- Nenhum Strategy Tester real iniciado.
- Nenhum shell irrestrito habilitado.
- Nenhum executavel anexado executado.
- Nenhum arquivo externo lido antes de autorizacao nos testes.
- READ nao virou WRITE.
- Imagem nao concedeu permissao.
- Attachment nao concedeu WRITE.
- Prompt injection em arquivo/imagem tratado como dado.
