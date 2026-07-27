#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 path/to/backup.dump" >&2
  exit 2
fi

COMPOSE_FILE="${COMPOSE_FILE:-deploy/vps/docker-compose.yml}"
BACKUP_PATH="$1"
TEST_DATABASE="corelabtech_restore_test"
CONTAINER_PATH="/tmp/corelabtech_restore_test.dump"

test -s "${BACKUP_PATH}"

docker compose -f "${COMPOSE_FILE}" cp \
  "${BACKUP_PATH}" "db:${CONTAINER_PATH}"
docker compose -f "${COMPOSE_FILE}" exec -T db sh -lc \
  "dropdb -U \"\$POSTGRES_USER\" --if-exists ${TEST_DATABASE}"
docker compose -f "${COMPOSE_FILE}" exec -T db sh -lc \
  "createdb -U \"\$POSTGRES_USER\" ${TEST_DATABASE}"
docker compose -f "${COMPOSE_FILE}" exec -T db sh -lc \
  "pg_restore -U \"\$POSTGRES_USER\" -d ${TEST_DATABASE} --no-owner ${CONTAINER_PATH}"
docker compose -f "${COMPOSE_FILE}" exec -T db sh -lc \
  "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d ${TEST_DATABASE} -c \
  \"SELECT COUNT(*) AS users_count FROM users; \
   SELECT COUNT(*) AS sessions_count FROM full_sessions; \
   SELECT COUNT(*) AS migrations_count FROM schema_migrations;\""
docker compose -f "${COMPOSE_FILE}" exec -T db sh -lc \
  "dropdb -U \"\$POSTGRES_USER\" ${TEST_DATABASE}"
docker compose -f "${COMPOSE_FILE}" exec -T db rm -f "${CONTAINER_PATH}"

echo "Restore test passed and temporary database removed."
