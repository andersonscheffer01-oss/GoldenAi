# Golden AI - Dockerfile
# Multi-stage build para reduzir tamanho da imagem

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copia dependências do builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copia código do projeto
COPY . .

# Cria diretórios necessários
RUN mkdir -p /app/logs /app/data /app/backups /app/projetos

# Expõe porta do servidor
EXPOSE 8765

# Comando para iniciar o servidor
CMD ["python", "studio/golden_ai_studio_web/server_agent.py"]
