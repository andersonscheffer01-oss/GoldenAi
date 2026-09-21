#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then echo "Uso: restore.sh /caminho/do/backup" >&2; exit 1; fi
SOURCE="$1"
test -f "$SOURCE/database.dump"
test -f "$SOURCE/uploads.tar.gz"
(cd "$SOURCE" && sha256sum -c SHA256SUMS)
: "${POSTGRES_DB:?POSTGRES_DB ausente}"
: "${POSTGRES_USER:?POSTGRES_USER ausente}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD ausente}"
export PGPASSWORD="$POSTGRES_PASSWORD"

pg_restore --clean --if-exists --no-owner -h "${POSTGRES_HOST:-postgres}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$SOURCE/database.dump"
tar -xzf "$SOURCE/uploads.tar.gz" -C /opt/golden-jarvis
echo "Restauracao concluida. Execute a verificacao de contagens e /api/health."
