# Politica de backup

- Diario: manter 14 copias.
- Semanal: manter 8 copias.
- Mensal: manter 12 copias.
- Copia externa: enviar ao menos um backup criptografado para armazenamento fora da VPS.
- Nunca remover um backup antes de validar `SHA256SUMS`, listar o dump e executar `test_restore.sh`.
- Banco, uploads e configuracao entram no backup. Logs de auditoria residem no banco; logs tecnicos seguem a retencao rotativa.
- A senha do PostgreSQL deve ser fornecida por arquivo de credenciais protegido, nunca pela linha de comando ou logs.
- O `.env.production` real deve ter copia externa separada e criptografada; ele nao entra no arquivo de backup comum.
