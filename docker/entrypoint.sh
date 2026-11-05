#!/bin/sh
# Container entrypoint: apply database migrations, then start the given command (uvicorn by default).
# Set RUN_MIGRATIONS=false to skip migrations (for example when several containers share one database).
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] DATABASE_URL is not set; refusing to start without a database." >&2
  exit 1
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
  alembic -c backend/alembic.ini upgrade head
fi

exec "$@"
