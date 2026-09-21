#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then echo "Uso: test_restore.sh /caminho/do/backup" >&2; exit 1; fi
SOURCE="$1"
TEST_DB="jarvis_restore_test_$(date +%s)"
: "${POSTGRES_USER:?POSTGRES_USER ausente}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD ausente}"
export PGPASSWORD="$POSTGRES_PASSWORD"
HOST="${POSTGRES_HOST:-postgres}"

createdb -h "$HOST" -U "$POSTGRES_USER" "$TEST_DB"
cleanup() { dropdb -h "$HOST" -U "$POSTGRES_USER" --if-exists "$TEST_DB"; }
trap cleanup EXIT
pg_restore --no-owner -h "$HOST" -U "$POSTGRES_USER" -d "$TEST_DB" "$SOURCE/database.dump"
psql -h "$HOST" -U "$POSTGRES_USER" -d "$TEST_DB" -c "SELECT COUNT(*) AS usuarios FROM usuarios;"
psql -h "$HOST" -U "$POSTGRES_USER" -d "$TEST_DB" -c "SELECT COALESCE(SUM(valor_centavos),0) AS total_centavos FROM lancamentos_financeiros;"
echo "Restauracao de teste aprovada em banco temporario."
