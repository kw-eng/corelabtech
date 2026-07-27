#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-deploy/vps/docker-compose.yml}"
OUTPUT_DIR="${1:-backups/postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUTPUT_PATH="${OUTPUT_DIR}/corelabtech_${TIMESTAMP}.dump"

mkdir -p "${OUTPUT_DIR}"

docker compose -f "${COMPOSE_FILE}" exec -T db sh -lc \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "${OUTPUT_PATH}"

test -s "${OUTPUT_PATH}"
find "${OUTPUT_DIR}" -type f -name 'corelabtech_*.dump' \
  -mtime "+${RETENTION_DAYS}" -delete

echo "Backup created: ${OUTPUT_PATH}"
