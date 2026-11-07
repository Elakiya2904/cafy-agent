#!/usr/bin/env bash
# Restore a pg_dump backup into the Docker PostgreSQL container ("db" service). Never overwrites data.
# macOS / Linux version of docker/restore-into-docker.ps1.
#
# Starts the db service, waits until it is healthy, and refuses to continue if the target database already
# has tables in the public schema. The restore is a single transaction: it either fully succeeds or leaves
# the target database unchanged. The dump file itself is not modified.
#
#   ./docker/restore-into-docker.sh                                      # newest backups/*.dump
#   ./docker/restore-into-docker.sh backups/cafy_agent_20261106_101500.dump
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

dump_file="${1:-}"
if [ -z "$dump_file" ]; then
  dump_file="$(ls -t backups/*.dump 2>/dev/null | head -1 || true)"
  [ -n "$dump_file" ] || { echo "No backups/*.dump found. Run ./docker/backup-local-db.sh first." >&2; exit 1; }
fi
[ -f "$dump_file" ] || { echo "Not found: $dump_file" >&2; exit 1; }

if [ -f "$dump_file.sha256" ]; then
  expected="$(cut -d' ' -f1 "$dump_file.sha256" | tr '[:lower:]' '[:upper:]')"
  if command -v shasum >/dev/null 2>&1; then actual="$(shasum -a 256 "$dump_file" | cut -d' ' -f1)"; else actual="$(sha256sum "$dump_file" | cut -d' ' -f1)"; fi
  [ "$(printf '%s' "$actual" | tr '[:lower:]' '[:upper:]')" = "$expected" ] || { echo "Checksum mismatch for $dump_file" >&2; exit 1; }
  echo "Checksum OK"
fi

docker compose up -d db
echo "Waiting for the db container to be healthy..."
state=""
for _ in $(seq 1 60); do
  state="$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q db)")"
  [ "$state" = "healthy" ] && break
  sleep 2
done
[ "$state" = "healthy" ] || { echo "db container is not healthy (state: $state)" >&2; exit 1; }

existing="$(docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from information_schema.tables where table_schema = '"'"'public'"'"'"' | tr -d '[:space:]')"
if [ "${existing:-0}" -gt 0 ]; then
  echo "The Docker database already has $existing tables in public. Refusing to overwrite it." >&2
  echo "To start over, back it up first, then remove the volume deliberately (see docs/DOCKER.md)." >&2
  exit 1
fi

container="$(docker compose ps -q db)"
docker cp "$dump_file" "$container:/tmp/restore.dump" >/dev/null
echo "Restoring $(basename "$dump_file") into the Docker database (single transaction)..."
set +e
docker compose exec -T db sh -c 'pg_restore --no-owner --no-privileges --single-transaction --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
code=$?
set -e
docker compose exec -T db rm -f /tmp/restore.dump >/dev/null
[ "$code" -eq 0 ] || { echo "pg_restore failed (exit $code). The Docker database was left unchanged." >&2; exit 1; }
echo "Restore complete. Verify with: uv run docker/compare_databases.py"
