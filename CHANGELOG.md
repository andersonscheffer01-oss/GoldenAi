# Changelog

Todas as mudanças notáveis no Golden AI são documentadas aqui.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/).

---

## [2.1.0] - 2026-08-20

### Adicionado
- **CI/CD** com GitHub Actions para testes automáticos
- **PWA** (Progressive Web App) — instalável como app no celular
- **Sistema de Plugins** — adicionar ferramentas sem modificar o engine
- Service Worker para cache offline
- Manifest.json para instalação PWA
- Plugin registry com carregamento dinâmico

### Infraestrutura
- `.github/workflows/test.yml` — pipeline de testes
- `plugins/` — diretório de plugins
- `plugins/plugin_loader.py` — carregador de plugins

---

## [2.0.0] - 2026-08-20

### Adicionado
- **19 módulos extraídos** do engine principal
- **56 testes automatizados** (100% passando)
- **24 ferramentas do agente** no server
- **30+ features** no studio web
- Canvas de código com editor integrado (7 linguagens)
- Backtest pelo chat (5 estratégias, 8 símbolos)
- Exportar conversa em PDF/Markdown
- Auto-read TTS (leitura automática de respostas)
- Dashboard de analytics (métricas de uso)
- Comparar 2 backtests lado a lado
- Multi-idioma automático (PT/EN)
- Dark/Light mode com persistência
- Favicon SVG inline
- Notificação sonora quando resposta está pronta
- Loading shimmer animado
- Mobile responsivo (768px e 480px)
- Docker + Docker Compose (dev e prod)
- docker-compose.prod.yml com backup automático
- main_loop.py extraído do engine
- Documentação completa (README, INSTALACAO, ARQUITETURA)
- requirements.txt com 35 dependências
- PermissionManager integrado no server
- Permissões READ/WRITE/EXECUTE por classe
- Auditoria de todas as operações
- Atalhos de teclado avançados (Ctrl+1/2/3/D)

### Corrigido
- Botão de envio ficava bloqueado após primeira mensagem
- check_tool_permission usando PermissionManager corretamente
- Target das market/quant tools retornando vazio quando não precisam de path

### Melhorado
- Layout profissional V7 (estilo ChatGPT/Claude)
- Streaming palavra por palavra
- Sidebar de histórico com busca
- Artifacts panel (Código, Canvas, Arquivos, Ferramentas)
- 24 ferramentas do agente (filesystem, código, sistema, web, PDF)

### Removido
- Backups desnecessários (184 arquivos limpos)
- Arquivos de debug antigos (_archive_debug organizado)

---

## [1.10.0] - 2026-08-18

### Adicionado
- V1.10 Router com roteamento de intenção
- Painel de comandos no terminal
- Auditoria determinística
- Autocorreção autônoma
- Autocorreção semântica

### Melhorado
- Motor determinístico de correção
- Parser de veredito final
- Estado persistente de auditoria

---

## [1.0.0] - 2026-08-15

### Adicionado
- Engine principal golden_ai.py
- Integração com Ollama (NVIDIA + local)
- Integração com MetaTrader 5
- Agentes: Market, Memory, Media, Quant
- Core V3: Permissions, Audit, Tools Registry
- Studio web básico
- Server Agent com tools básicas
- Configuração YAML
- Sistema de memória científica
- Análise de mercado
- Backtesting básico
- Ingestão de mídia (PDF, imagem, áudio, vídeo)
