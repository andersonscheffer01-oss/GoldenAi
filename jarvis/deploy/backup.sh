#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB ausente}"
: "${POSTGRES_USER:?POSTGRES_USER ausente}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD ausente}"
export PGPASSWORD="$POSTGRES_PASSWORD"
BACKUP_ROOT="${JARVIS_BACKUP_DIR:-/opt/golden-jarvis/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_ROOT/$STAMP"
mkdir -p "$DEST"

pg_dump -Fc -h "${POSTGRES_HOST:-postgres}" -U "$POSTGRES_USER" "$POSTGRES_DB" -f "$DEST/database.dump"
tar -czf "$DEST/uploads.tar.gz" -C /opt/golden-jarvis uploads
tar -czf "$DEST/configuration.tar.gz" -C /opt/golden-jarvis .env.production.example deploy
sha256sum "$DEST"/* > "$DEST/SHA256SUMS"
pg_restore --list "$DEST/database.dump" >/dev/null
tar -tzf "$DEST/uploads.tar.gz" >/dev/null
tar -tzf "$DEST/configuration.tar.gz" >/dev/null
echo "Backup validado: $DEST"
