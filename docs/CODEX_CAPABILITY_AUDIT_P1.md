# Golden AI - CODEX Capability Audit P1

Data: 2026-08-13

Escopo: Project Intelligence + Project Search/Read Tools + Dependency Graph + Diff Viewer V1 + Chat Attachments/Image Input V1.

## Capacidades Afetadas

| Capacidade | Antes | Depois | Evidencia |
| --- | ---: | ---: | --- |
| Project Understanding | 3 | 4 | `ProjectIntelligenceService.project_list`, metadata deterministica e grafo local Python. |
| Code Search | 2 | 4 | `project_search` usa `rg` quando disponivel e fallback Python seguro. |
| Code Reading | 3 | 4 | `project_read_range` le intervalos precisos sem carregar arquivo inteiro por pedido. |
| Multi-file Work | 4 | 4 | Coding V2 preservado e agora usa grafo/related files no mapeamento. |
| Debugging | 3 | 4 | Fluxo erro -> busca -> leitura -> grafo -> related files -> plano -> sandbox. |
| Auditability | 4 | 4 | Eventos reais em ExecutionService e AuditLogger para SEARCH/READ/ATTACHMENT. |
| Attachments | 0 | 3 | Storage controlado, SHA-256, preview, multiplos anexos, historico basico. |
| Multimodal Input | 0 | 2 | ATTACHMENT_SUPPORTED para imagens; VISION_SUPPORTED = NAO. |

## Status Multimodal

- ATTACHMENT_SUPPORTED: SIM.
- IMAGE_PREVIEW_SUPPORTED: SIM.
- IMAGE_STORAGE_SUPPORTED: SIM.
- VISION_SUPPORTED: NAO.
- OCR_SUPPORTED: NAO.
- PDF_ATTACHMENT_SUPPORTED: SIM.
- PDF_PARSER_SUPPORTED: NAO nesta fase.

## Limites e Politicas

- Imagens: 20 MB.
- Texto/codigo: 20 MB.
- PDF: 50 MB.
- Executaveis bloqueados: `.exe`, `.bat`, `.cmd`, `.ps1`, `.msi`, `.scr`, `.dll`.
- Arquivo anexado e tratado como dado nao confiavel.
- Anexos nao sao executados.
- Originais externos nao sao modificados; copia controlada fica em `C:\GoldenAI\data\attachments\<session_id>\`.

## Limitacoes Conhecidas

- Dependency Graph V1 cobre Python via AST; MQL5 permanece heuristico/textual.
- Diff Viewer V1 e legivel, mas ainda nao e editor interativo por hunk.
- A Golden recebe referencia estruturada e conteudo textual extraido; imagem nao e analisada visualmente sem adapter real.
- PDF e armazenado e identificado, mas parser seguro fica para fase futura.
- Market/Quant/Media podem receber anexos quando o usuario pedir explicitamente; nao ha execucao automatica por tipo de arquivo.
