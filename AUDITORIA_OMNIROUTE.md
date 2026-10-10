# Auditoria Técnica: OmniRoute AI Gateway
## Avaliação de Integração com Golden AI + J.A.R.V.I.S.

**Data da Auditoria:** 21 de setembro de 2026
**Versão Avaliada:** OmniRoute v3.8.51
**Repositório:** https://github.com/diegosouzapw/OmniRoute
**Licença:** MIT

---

## 1. SUMÁRIO EXECUTIVO

### 1.1 Visão Geral
OmniRoute é um AI gateway/router de produção com **359 provedores de IA**, 110 ferramentas MCP, servidor A2A, compressão avançada de tokens (RTK+Caveman), e aplicativo desktop Electron. Oferece roteamento inteligente, fallback automático, circuit breakers, e orçamento gratuito calculado em ~1.62B tokens/mês através de 152 provedores com tier gratuito.

### 1.2 Recomendação Preliminar
**RECOMENDAÇÃO: INTEGRAÇÃO EXTERNA MODULAR (Cenário A com elementos do C)**

**Justificativa:**
- **Baixo risco**: Integração via HTTP preserva arquitetura atual de Golden/Jarvis
- **Alto benefício**: Acesso imediato a 359 provedores vs. 4 atuais (Ollama, Gemini, Tavily, Groq)
- **Compatibilidade**: OmniRoute já é compatível com Claude Code/Codex (ferramentas que Golden/Jarvis também usa)
- **Investimento controlado**: Não requer refatoração de Golden, apenas expansão de ToolRegistry
- **Token savings**: Compressão RTK+Caveman (15-95%, média 89.2%) pode reduzir custos significativamente

### 1.3 Riscos Identificados
1. **Dependência tecnológica**: Node.js ≥22.22.2 vs. Python 3.x de Golden/Jarvis
2. **Complexidade operacional**: Gerenciar dois processos (Golden na porta 8765-8766, OmniRoute na 20128)
3. **Overhead de comunicação**: Latência adicional HTTP localhost
4. **Curva de aprendizado**: 1700+ linhas README, 359 provedores, 19 estratégias de roteamento

---

## 2. ANÁLISE TÉCNICA DETALHADA

### 2.1 Arquitetura OmniRoute

#### 2.1.1 Stack Tecnológico
```
Runtime:      Node.js ≥22.22.2 <23 || ≥24.0.0 <27
Linguagem:    TypeScript 6.0.3 (100% tipado, zero `any` no core)
Framework:    Next.js 16.3.3 + React 19.2.8
Database:     SQLite (better-sqlite3 com WAL journaling)
              + LowDB (JSON legacy)
              + FTS5 full-text search
              + int8-quantized vector embeddings
Compressão:   12 engines (RTK, Caveman, LLMLingua-2 ONNX, Headroom, OmniGlyph, etc.)
Protocolos:   MCP (stdio/HTTP/SSE) + A2A v0.3 (JSON-RPC 2.0)
Auth:         OAuth 2.0 PKCE + JWT + API Keys + MCP scoped auth
              AES-256-GCM para credenciais em repouso
Segurança:    DOMPurify, wreq-js (JA3/JA4 TLS spoofing), 3-level proxy
Resiliência:  Circuit breaker, exponential backoff, anti-thundering-herd
Testes:       39,000+ declarações estáticas em 5,100+ arquivos rastreados
Plataformas:  Desktop (Electron), Android (Termux), PWA
CI/CD:        GitHub Actions → npm + Docker Hub automático
```

#### 2.1.2 Estrutura de Diretórios (~26,767 linhas TypeScript)
```
C:\OmniRoute/
├── src/
│   ├── app/                      # Next.js 16 App Router
│   │   ├── api/                  # API routes (/v1/* compatíveis OpenAI)
│   │   └── (dashboard)/          # 23 páginas dashboard (combos, providers, analytics, etc.)
│   ├── server/                   # 21 arquivos TypeScript (lógica servidor)
│   ├── domain/                   # 19 módulos (assessment, costRules, quotaCache, pipeline, policyEngine)
│   ├── lib/
│   │   ├── a2a/                  # A2A Protocol v0.3 (taskManager, streaming, skills)
│   │   ├── oauth/providers/      # 22 provedores OAuth modulares (Google, GitHub, Azure, etc.)
│   │   ├── db/                   # 122 módulos SQLite (providers, combos, settings, pricing)
│   │   └── ...                   # Auth, memory, compression, validation
│   └── sse/                      # Streaming core (provider execution, translation, fallback)
├── open-sse/
│   ├── mcp-server/               # MCP Server (110 tools, 33 scopes, stdio/HTTP/SSE)
│   └── executors/                # 108 provider executors + translation logic
├── electron/                     # Desktop App (236KB, main.js, preload, loginManager)
│   ├── main.js                   # Electron 44.3.0 main process
│   └── package.json              # Cross-platform builds (Win/Mac/Linux)
├── docs/
│   ├── architecture/             # ARCHITECTURE.md (3.8.40, diagrams Mermaid)
│   ├── guides/                   # 40+ guias (setup, deployment, compression)
│   └── diagrams/                 # Diagramas versionados (request-pipeline, resilience)
├── migrations/                   # 178 migrações SQLite
├── .env.example                  # Contrato ENV (JWT_SECRET, API_KEY_SECRET, DATA_DIR)
└── package.json                  # 80+ scripts (dev, build, electron:build, mcp:*)
```

**Pontos de destaque:**
- **src/domain/**: Módulos de negócio (policyEngine, costRules, quotaCache, pipeline) — lógica de roteamento, fallback e quota
- **src/lib/a2a/**: Protocolo A2A completo (taskManager, streaming, skills) — colaboração entre agentes via JSON-RPC 2.0
- **open-sse/mcp-server/**: 110 ferramentas MCP com 33 escopos — stdio/HTTP/SSE transports
- **open-sse/executors/**: 108 executores de provedores — tradução de requests/responses entre formatos
- **electron/**: App desktop 236KB — Electron 44.3.0, builds para Windows/Mac/Linux
- **migrations/**: 178 migrações SQLite — banco de dados versionado com WAL journaling

#### 2.1.3 Protocolos e APIs

**OpenAI-Compatible API** (`/v1/*`)
- Endpoint base: `http://localhost:20128/v1/chat/completions`
- Suporta: streaming SSE, function calling, multi-modal (text/image/audio)
- 108 executores traduzem requests para formatos específicos de cada provedor
- Response translation automática para formato OpenAI padrão

**MCP Server** (Model Context Protocol)
- 110 ferramentas organizadas em 33 escopos (compression, routing, quota, memory, etc.)
- 3 transportes: stdio (Claude Desktop/Cursor/Zed), HTTP, SSE (streaming)
- Autenticação scoped: cada ferramenta pode ter permissões granulares
- Integração: IDEs adicionam config JSON apontando para `node C:\OmniRoute\open-sse\mcp-server\index.js`

**A2A Protocol v0.3** (Agent-to-Agent)
- JSON-RPC 2.0 sobre SSE para colaboração entre agentes
- Task lifecycle: creation → progress updates → completion/failure
- Skills-based routing: smart-routing, quota-management, multi-model-combo
- Discovery endpoint: `/a2a/v0.3/discover` retorna capabilities e skills disponíveis

#### 2.1.4 Compressão de Tokens

**12 Engines de Compressão** (pipeline configurável por usuário)
```typescript
Session-Dedup      # Remove mensagens duplicadas na sessão (5-15%)
CCR                # Contextual Compression Rules (10-30%)
Lite               # Lightweight pattern matching (15-25%)
RTK                # Recursive Token Kompression — estado da arte (40-70%)
Responses          # Comprime respostas anteriores do assistente (20-40%)
Tool Output        # Comprime outputs de ferramentas (30-60%)
Headroom           # Mantém margem de segurança (5-10%)
Relevance          # Remove contexto irrelevante via embeddings (20-50%)
Caveman            # Agressiva simplificação sintática (50-80%)
Aggressive         # Combinação de heurísticas agressivas (60-85%)
LLMLingua-2        # ONNX runtime, state-of-the-art acadêmico (40-70%)
Ultra              # Modo máximo, pode degradar qualidade (70-90%)
OmniGlyph          # Unicode compression experimental (80-95%)
```

**Resultados Documentados:**
- Média geral: **89.2% de redução** (README.md linha 458)
- Range: 15% (conservador) até 95% (ultra-agressivo)
- Trade-off: maior compressão = maior risco de perda semântica

**Casos de Uso:**
- Long-context conversations (reduzir tokens de histórico)
- Tool-heavy workflows (outputs verbosos de ferramentas)
- Multi-turn sessions com contexto acumulado
- Budget optimization (maximizar uso de tiers gratuitos)

---

## 2.2 CENÁRIOS DE INTEGRAÇÃO COM GOLDEN/JARVIS

### Cenário A: AI Router Externo via API OpenAI-Compatible ⭐⭐⭐⭐⭐

**Arquitetura:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Golden AI (Python 3.x, FastAPI, porta 8765-8766)               │
│                                                                 │
│  ┌──────────────┐      ┌─────────────────┐                   │
│  │ JarvisService│─────▶│ ModelRouter     │                   │
│  │              │      │ (expandido)     │                   │
│  └──────────────┘      └─────────────────┘                   │
│                               │                                │
│                               │ HTTP POST                      │
│                               ▼                                │
└───────────────────────────────┼────────────────────────────────┘
                                │
                    localhost:20128/v1/chat/completions
                                │
┌───────────────────────────────▼────────────────────────────────┐
│ OmniRoute (Node.js 22+, Next.js, porta 20128)                 │
│                                                                 │
│  ┌──────────────┐      ┌─────────────────┐                   │
│  │ API Gateway  │─────▶│ Routing Engine  │──────┐            │
│  │ (/v1/*)      │      │ (19 strategies) │      │            │
│  └──────────────┘      └─────────────────┘      │            │
│                               │                   │            │
│                               ▼                   ▼            │
│                        ┌─────────────┐    ┌──────────────┐   │
│                        │ Compression │    │ Fallback     │   │
│                        │ Pipeline    │    │ Chain        │   │
│                        └─────────────┘    └──────────────┘   │
│                               │                   │            │
│                               ▼                   ▼            │
│                        ┌──────────────────────────────┐       │
│                        │ 359 AI Providers             │       │
│                        │ (152 com tier gratuito)      │       │
│                        └──────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

**Implementação no Golden:**
```python
# jarvis_core/gateway/model_router.py (expandir classe existente)

class ModelRouter:
    def __init__(self):
        self.ollama = OllamaProvider()
        self.gemini = GeminiProvider()
        self.groq = GroqProvider()
        self.omniroute = OmniRouteProvider()  # NOVO

    async def route_request(self, prompt: str, strategy: str = "best-quality"):
        if strategy == "omniroute-compressed":
            # Usar OmniRoute com compressão RTK+Caveman
            return await self.omniroute.complete(
                prompt=prompt,
                compression=["RTK", "Caveman"],
                fallback_chain=["gemini-2.0-flash", "claude-3.5-sonnet", "gpt-4o"]
            )
        elif strategy == "omniroute-free-budget":
            # Maximizar uso de tiers gratuitos
            return await self.omniroute.complete(
                prompt=prompt,
                quota_mode="free-only",
                routing="quota-weighted-p2c"
            )
        else:
            # Rotas existentes (Ollama, Gemini direto, etc.)
            return await self._legacy_routing(prompt, strategy)

# jarvis_core/providers/omniroute_provider.py (NOVO arquivo)

import httpx
from typing import List, Optional

class OmniRouteProvider:
    def __init__(self, base_url: str = "http://localhost:20128"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=120.0)

    async def complete(
        self,
        prompt: str,
        compression: Optional[List[str]] = None,
        fallback_chain: Optional[List[str]] = None,
        quota_mode: str = "balanced",
        routing: str = "quota-weighted-p2c"
    ):
        payload = {
            "model": fallback_chain[0] if fallback_chain else "auto",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "omniroute": {
                "compression": compression or [],
                "fallback": fallback_chain or [],
                "quotaMode": quota_mode,
                "routing": routing
            }
        }

        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OMNIROUTE_API_KEY}"}
        )
        response.raise_for_status()
        return response.json()
```

**Prós:**
- ✅ **Zero refatoração de Golden**: apenas adicionar um novo provider no ModelRouter existente
- ✅ **Acesso imediato a 359 provedores**: vs. 4 atuais (Ollama, Gemini, Tavily, Groq)
- ✅ **Compressão automática**: 15-95% economia de tokens sem mudança no código de chamada
- ✅ **Fallback inteligente**: multi-model chains configuráveis por request
- ✅ **Quota management**: P2C load balancing entre contas gratuitas
- ✅ **Sem conflito de portas**: 20128 (OmniRoute) vs. 8765/8766 (Golden)
- ✅ **Compatibilidade OpenAI**: formato padrão já usado por Jarvis em outros providers

**Contras:**
- ❌ **Dependência Node.js**: requer Node.js ≥22.22.2 instalado no ambiente de produção
- ❌ **1.5GB footprint**: repositório completo OmniRoute (vs. Golden mais leve)
- ❌ **Dois processos**: Golden (Python) + OmniRoute (Node) devem rodar simultaneamente
- ❌ **Latência HTTP localhost**: overhead adicional ~5-15ms por request
- ❌ **Configuração complexa**: 178 migrações SQLite, JWT_SECRET, API_KEY_SECRET, 359 provider credentials
- ❌ **Curva de aprendizado**: 1738 linhas README, 19 estratégias de roteamento, 12 engines de compressão

**Esforço de Implementação:** 🟢 **BAIXO** (4-8 horas)
1. Instalar Node.js 22.22.2+ e rodar `npm install` no OmniRoute
2. Configurar `.env` com JWT_SECRET, API_KEY_SECRET, INITIAL_PASSWORD
3. Rodar migrações: `npm run db:migrate`
4. Iniciar OmniRoute: `npm run dev` (porta 20128)
5. Adicionar `OmniRouteProvider` ao `jarvis_core/providers/`
6. Expandir `ModelRouter` com estratégias "omniroute-*"
7. Testar fallback chains e compression pipelines

**Recomendação:** ⭐⭐⭐⭐⭐ **ALTAMENTE RECOMENDADO**

---

### Cenário B: Integração via MCP Client ⭐⭐⭐

**Esforço:** 🟡 **MÉDIO-ALTO** (16-32 horas)

**Resumo:** Implementar cliente MCP completo em Python para acessar 110 ferramentas granulares. Oferece controle fino mas é overkill para necessidade atual de Golden (que precisa principalmente de acesso a providers, não de 110 ferramentas específicas).

**Recomendação:** Viável mas não prioritário. Melhor usar Cenário A agora e migrar para MCP se surgirem casos de uso para ferramentas granulares (quota inspection, routing analytics, compression tuning).

---

### Cenário C: Colaboração A2A (Agent-to-Agent Protocol) ⭐⭐

**Esforço:** 🟡 **MÉDIO** (12-20 horas)

**Resumo:** OmniRoute age como "agente especialista" em roteamento via A2A Protocol v0.3 (JSON-RPC 2.0 + SSE). Interessante para visão de longo prazo se Golden evoluir para multi-agent system, mas não prioridade para curto prazo.

**Recomendação:** Experimentar no futuro. Usar Cenário A agora, explorar A2A em FASE futura quando arquitetura de agentes estiver madura.

---

### Cenário D: Sem Integração ⭐

**Esforço:** 🟢 **ZERO** (0 horas)

**Resumo:** Manter Golden e OmniRoute separados. Única vantagem é simplicidade, mas custo de oportunidade é muito alto (perda de 359 providers, compressão, fallback automático, 1.62B tokens/mês gratuitos).

**Recomendação:** Não recomendado. Golden já tem arquitetura modular, adicionar um provider via Cenário A é baixo esforço com alto retorno.

---

## 2.3 AVALIAÇÃO DE SEGURANÇA

### 2.3.1 Autenticação e Autorização

**Métodos Suportados:**

1. **OAuth 2.0 com PKCE** (22 provedores modulares)
   - Google, GitHub, Microsoft Azure, Discord, Slack, etc.
   - Flow completo: authorization code + PKCE challenge
   - Tokens armazenados com AES-256-GCM encryption

2. **JWT (JSON Web Tokens)**
   - Dashboard sessions: signed com `JWT_SECRET`
   - Expiration configurável (default 7 dias)
   - Refresh token rotation

3. **API Keys**
   - Geradas por usuário no dashboard
   - Encrypted at rest com `API_KEY_SECRET` (AES-256-GCM)
   - Rate limiting por key

4. **MCP Scoped Auth**
   - 33 scopes granulares (compression:read, routing:write, quota:admin, etc.)
   - Cada ferramenta MCP pode exigir escopos específicos
   - Token-based: Bearer token no header Authorization

**Armazenamento de Credenciais:**
```typescript
// src/lib/db/providers.ts
export function storeProviderCredentials(
  userId: string,
  provider: string,
  credentials: { apiKey?: string; accessToken?: string; refreshToken?: string }
) {
  const encrypted = encrypt(JSON.stringify(credentials), API_KEY_SECRET);
  db.prepare(`
    INSERT INTO provider_credentials (user_id, provider, encrypted_data)
    VALUES (?, ?, ?)
  `).run(userId, provider, encrypted);
}
```

**Pontos de Atenção:**
- ⚠️ `.env` file contém secrets críticos: `JWT_SECRET`, `API_KEY_SECRET`, `INITIAL_PASSWORD`
- ⚠️ Migrações SQLite incluem schema para armazenar 359 provider API keys
- ⚠️ Se Golden integrar via HTTP API, precisa configurar API key no OmniRoute e passar no header
- ⚠️ `INITIAL_PASSWORD=CHANGEME` deve ser alterado antes do primeiro uso

### 2.3.2 Criptografia

**Em Repouso:**
- **AES-256-GCM** para API keys e OAuth tokens no SQLite
- **Derivação de chave**: `API_KEY_SECRET` (32 bytes hex) via PBKDF2
- **IV único** por registro encrypted
- **Authentication tag** para integridade

**Em Trânsito:**
- **TLS 1.3** para comunicação com providers externos
- **JA3/JA4 TLS fingerprint spoofing** (wreq-js) para evitar detecção de bot
- **HTTP localhost** entre Golden e OmniRoute (não requer TLS dentro da máquina)

**Secrets Management:**
```bash
# .env.example (CRITICAL)
JWT_SECRET=             # Generate: openssl rand -base64 48
API_KEY_SECRET=         # Generate: openssl rand -hex 32
INITIAL_PASSWORD=CHANGEME  # MUST change before first use
```

### 2.3.3 Proteções Implementadas

**Rate Limiting:**
- Por API key (configurável por usuário)
- Por IP address (dashboard)
- Per-provider quota tracking

**Circuit Breaker:**
- Detecta falhas repetidas em providers
- Open state: requests não são enviados ao provider falhando
- Half-open state: testa recovery gradualmente
- Configurável: failure threshold, timeout, retry backoff

**Anti-Thundering Herd:**
- Signature-based request deduplication
- Se N clients fazem requisição idêntica simultaneamente, apenas 1 vai ao provider
- Outros recebem response do cache ou aguardam completion da primeira

**Input Validation:**
- **DOMPurify** para sanitização de inputs HTML
- **Zod schemas** para validação TypeScript em runtime
- **SQL prepared statements** para prevenir SQL injection
- **Content Security Policy** no dashboard

**Audit Log:**
- Todas requests ao `/v1/*` API são logged
- Provider fallback decisions são tracked
- Quota usage é persistido por request

### 2.3.4 Vulnerabilidades Potenciais

⚠️ **Alto Risco:**
1. **Secrets no .env**: se `.env` vazar, toda segurança é comprometida
   - **Mitigação**: adicionar `.env` ao `.gitignore` (já está), usar secret manager em produção

2. **SQLite file access**: `~/.omniroute/omniroute.db` contém credenciais encrypted
   - **Mitigação**: filesystem permissions restrictivas (chmod 600), backup encrypted

3. **Node.js dependencies**: 80+ packages npm, supply chain attack risk
   - **Mitigação**: npm audit, Dependabot alerts, lockfile integrity

⚠️ **Médio Risco:**
4. **MITM proxy vulnerabilities**: 3-level proxy pode ser explorado se mal configurado
   - **Mitigação**: documentar configuração segura, desabilitar em produção se não necessário

5. **Electron security**: desktop app pode ter vulnerabilities se usar webview sem sandbox
   - **Mitigação**: revisar electron/main.js para nodeIntegration=false, contextIsolation=true

6. **OAuth redirect hijacking**: se redirect_uri não for validado estritamente
   - **Mitigação**: revisar src/lib/oauth/providers/* para whitelist de URLs

### 2.3.5 Recomendações de Segurança para Integração

**Se Golden adotar Cenário A (HTTP API):**

1. **Gerar secrets fortes**:
   ```bash
   JWT_SECRET=$(openssl rand -base64 48)
   API_KEY_SECRET=$(openssl rand -hex 32)
   INITIAL_PASSWORD=$(openssl rand -base64 24)
   ```

2. **Configurar API key dedicada** para Golden:
   - Criar key no dashboard OmniRoute
   - Adicionar key ao `.env` de Golden (não hardcodar no código)
   - Usar header `Authorization: Bearer <key>` em todas requests

3. **Network isolation**:
   - OmniRoute bind apenas em `127.0.0.1:20128` (não 0.0.0.0)
   - Firewall: bloquear porta 20128 de acesso externo
   - Se Golden e OmniRoute rodarem em máquinas separadas, usar VPN/SSH tunnel

4. **Monitoring**:
   - Alertar se OmniRoute process terminar (Golden ficará sem fallback)
   - Log anomalies: requests com API key inválida, rate limit exceeded
   - Track quota consumption para detectar vazamento de key

5. **Backup e Recovery**:
   - Backup diário de `~/.omniroute/omniroute.db` (contém configurações, não só credentials)
   - Testar restore procedure
   - Documentar secrets recovery se perder `.env`

---

## 2.4 ANÁLISE DE DEPENDÊNCIAS

### 2.4.1 Runtime Dependencies

**OmniRoute (Node.js):**
```json
{
  "node": ">=22.22.2 <23 || >=24.0.0 <27",
  "dependencies": {
    "next": "16.3.3",
    "react": "19.2.8",
    "better-sqlite3": "^12.1.0",
    "onnxruntime-node": "^1.22.1",  // LLMLingua-2 compression
    "sharp": "^0.34.3",             // Image processing
    "@anthropic-ai/sdk": "^1.17.2",
    "openai": "^4.95.3",
    "google-auth-library": "^9.18.0",
    // ... 80+ total packages
  }
}
```

**Golden/Jarvis (Python):**
```python
# requirements.txt
anthropic>=0.40.0
openai>=1.65.4
google-generativeai>=0.8.3
fastapi>=0.115.6
uvicorn[standard]>=0.34.0
httpx>=0.28.1
pydantic>=2.10.5
pillow>=11.1.0
# ... ~30 packages total
```

**Comparação:**
| Aspecto | OmniRoute | Golden/Jarvis |
|---------|-----------|---------------|
| Runtime | Node.js 22+ | Python 3.11+ |
| Package Manager | npm | pip |
| Dependencies Count | ~80 packages | ~30 packages |
| Repository Size | 1.5GB | ~200MB |
| Database | SQLite (better-sqlite3) | SQLite (aiosqlite) |
| Web Framework | Next.js 16 | FastAPI 0.115 |
| Async Runtime | Node.js event loop | asyncio |

### 2.4.2 Shared Dependencies

**Ambos usam:**
- SQLite (OmniRoute: better-sqlite3, Golden: aiosqlite)
- Anthropic SDK (OmniRoute: @anthropic-ai/sdk, Golden: anthropic)
- OpenAI SDK (OmniRoute: openai, Golden: openai)
- HTTP client (OmniRoute: fetch native, Golden: httpx)

**Potencial para conflitos:** ❌ **ZERO**
- Runtimes completamente separados (Node.js vs Python)
