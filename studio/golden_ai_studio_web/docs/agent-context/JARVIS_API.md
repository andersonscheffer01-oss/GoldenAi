# API do Jarvis

- `POST /api/jarvis/chat`: interpreta com o Brain e executa somente via JarvisService.
- `POST /api/jarvis/brain/execute`: chamada direta, ainda passa por validação, segurança e auditoria.
- `POST /api/jarvis/brain/status`: estado, modelo, timeout e contagem de tools.
- `POST /api/jarvis/vision/analyze`: análise visual com timeout controlado.
- `POST /api/jarvis/voice/command`: comando de voz pelo fluxo Jarvis.
- `POST /api/desktop/status|action|confirm|speech`: compatibilidade da Central PC.

Nenhuma rota Jarvis executa handler diretamente.
