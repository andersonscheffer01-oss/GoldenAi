# Checklist de ativacao da Etapa 9

## Diagnostico pendente da MustHost

- [ ] Sistema operacional, versao, CPU, RAM e disco registrados.
- [ ] IP publico e acesso SSH/RDP confirmados.
- [ ] Docker, Python e PostgreSQL identificados.
- [ ] Dominio/subdominio definido e DNS propagado.

## Antes da migracao

- [ ] Hash do SQLite local registrado.
- [ ] Backup local copiado e `PRAGMA integrity_check` aprovado.
- [ ] Uploads copiados preservando nomes internos.
- [ ] PostgreSQL vazio e acessivel apenas na rede interna.

## Producao

- [ ] `.env.production` criado com segredos novos e permissao 600.
- [ ] `docker compose config` aprovado na VPS.
- [ ] Caddy obteve certificado valido e redireciona HTTP para HTTPS.
- [ ] Portas 8780, 5432 e 11434 inacessiveis externamente.
- [ ] `/api/health` responde sem segredos.
- [ ] Login, upload isolado e dashboard autenticada validados.
- [ ] PWA instalada e reaberta no Safari.
- [ ] Agente pareado por HTTPS, revogado e reconectado em teste.
- [ ] Backup diario criado e restaurado em banco temporario.

Nenhum item deve ser marcado por suposicao. Anexe evidencia (comando, horario e resultado) a cada validacao.
