# Golden Jarvis - implantacao segura

Este pacote nao publica nada sozinho. Execute `diagnose_vps.sh` (Linux) ou `diagnose_vps.ps1` (Windows) e registre o resultado antes de instalar.

## Pre-requisitos

- Subdominio com registro A/AAAA apontando para a VPS.
- Portas publicas 80 e 443; SSH/RDP restrito por IP/VPN.
- Portas 8780, 5432 e 11434 bloqueadas externamente.
- Docker Engine e Docker Compose (fluxo recomendado para Linux).

## Implantacao Docker

1. Copie o projeto para `/opt/golden-jarvis`.
2. Crie o usuario de aplicacao `jarvis` sem privilegios e ajuste a propriedade da pasta.
3. Copie `.env.production.example` para `.env.production` e substitua somente os marcadores `CHANGE_*` e o dominio.
4. Gere a chave com `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
5. Valide com `docker compose config`.
6. Inicie com `docker compose up -d --build`.
7. Confira com `docker compose ps`, `docker compose logs --tail=100 backend` e `curl https://SEU_DOMINIO/api/health`.

O backend e o PostgreSQL nao publicam portas no host. Somente o Caddy publica 80/443 e renova o certificado automaticamente.

## Operacao

- Iniciar: `docker compose up -d`
- Parar: `docker compose down`
- Reiniciar backend: `docker compose restart backend`
- Logs: `docker compose logs -f --tail=100 backend caddy`
- Estado: `docker compose ps`

## Agente do PC

No `pc_agent/.env`, use `JARVIS_SERVER_URL=https://SEU_DOMINIO`. Nao use IP nem HTTP. O Python valida o certificado do sistema por padrao. Nenhuma porta deve ser aberta no computador ou roteador.

## Windows VPS

Execute o diagnostico PowerShell. A implantacao Windows requer Docker Desktop/Engine ou um servico criado com NSSM/Agendador de Tarefas, proxy reverso Caddy e regras equivalentes no Windows Firewall. Nao use o roteiro Linux sem confirmar o sistema operacional.
