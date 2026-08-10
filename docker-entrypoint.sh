#!/bin/sh
set -eu

if [ "${APP_RUN_MIGRATIONS:-true}" = "true" ]; then
    python run_database_setup.py
fi

exec "$@"
