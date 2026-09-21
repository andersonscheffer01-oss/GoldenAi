# 📦 Guia de Instalação - Golden AI

## Requisitos

| Componente | Versão Mínima | Obrigatório |
|------------|---------------|-------------|
| Python | 3.11+ | ✅ |
| Ollama | Latest | ✅ |
| MetaTrader 5 | Latest | ❌ (opcional) |
| Node.js | 18+ | ❌ (para OpenCode) |

## Instalação Rápida

### Windows

```powershell
# 1. Clonar o repositório
git clone <url-do-repositorio>
cd GoldenAI

# 2. Criar ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Instalar Ollama (se não tiver)
winget install Ollama.Ollama

# 5. Baixar modelo
ollama pull qwen2.5-coder:14b

# 6. Iniciar servidor
cd studio\golden_ai_studio_web
python server_agent.py

# 7. Abrir no navegador
# Clique duas vezes em: ABRIR_GOLDEN_AI_STUDIO_WEB.vbs
```

### Linux/Mac

```bash
# 1. Clonar
git clone <url-do-repositorio>
cd GoldenAI

# 2. Ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Dependências
pip install -r requirements.txt

# 4. Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:14b

# 5. Servidor
cd studio/golden_ai_studio_web
python server_agent.py

# 6. Abrir http://localhost:8765
```

## Configuração

Edite os arquivos em `config/`:

| Arquivo | O que configura |
|---------|-----------------|
| `base.yaml` | Caminhos do projeto |
| `security.yaml` | Permissões de leitura/escrita |
| `ollama.yaml` | Modelos de IA |
| `tools.yaml` | Ferramentas e coding agent |

### Modelos Recomendados

| Modelo | RAM | Qualidade | Velocidade |
|--------|-----|-----------|------------|
| qwen2.5-coder:14b | 8GB | 🟢 Boa | 🟡 Média |
| qwen2.5-coder:32b | 20GB | 🟢 Excelente | 🟠 Lenta |
| Qwen3.8-27B-Uncensored | 16GB | 🟢 Excelente | 🟡 Média |

## Verificação

```bash
# Testar servidor
curl http://127.0.0.1:8765/api/status

# Rodar testes
python tests/test_agent_tools.py
python tests/test_modules.py
python tests/test_permissions.py
python tests/test_memory.py
```

## Solução de Problemas

| Erro | Solução |
|------|---------|
| `Ollama não encontrado` | Instale Ollama e rode `ollama serve` |
| `Modelo não encontrado` | Rode `ollama pull qwen2.5-coder:14b` |
| `Port 8765 em uso` | Mate o processo: `taskkill /F /IM python.exe` |
| `Permission denied` | Verifique `config/security.yaml` |
