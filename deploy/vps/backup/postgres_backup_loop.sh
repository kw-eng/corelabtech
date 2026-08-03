#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

backup_once() {
    timestamp="$(date -u +%Y%m%d_%H%M%S)"
    final_path="$BACKUP_DIR/corelabtech_${timestamp}.dump"
    temporary_path="${final_path}.partial"

    PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
        --host=db \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --format=custom \
        --file="$temporary_path"
    test -s "$temporary_path"
    mv "$temporary_path" "$final_path"
    find "$BACKUP_DIR" -type f -name 'corelabtech_*.dump' \
        -mtime "+$RETENTION_DAYS" -delete
    echo "Backup created: $final_path"
}

while true; do
    backup_once
    sleep "$INTERVAL_SECONDS"
done
