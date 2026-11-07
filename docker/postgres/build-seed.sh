#!/usr/bin/env bash
# Generate the seed files for the cafy-agent-db image. macOS / Linux version of build-seed.ps1.
# Reads an existing database (DATABASE_URL in .env by default) with pg_dump. Read-only on the source.
#
# Default (shareable, no personal data) -> docker/postgres/initdb/:
#   01-schema.sql   every table, index and constraint in the public schema, no rows
#   02-jobs.sql     rows of public.jobs (scraped job postings) and public.alembic_version
# Users, sign-in tokens, profiles, resumes, applications and email data are NOT included.
#
# --full (PRIVATE: contains personal data) -> docker/postgres/initdb-full/:
#   01-full.sql     the whole public schema with all rows. Push only to a PRIVATE repository.
#
#   ./docker/postgres/build-seed.sh
#   ./docker/postgres/build-seed.sh --full
#   PG_BIN=/opt/homebrew/opt/postgresql@17/bin ./docker/postgres/build-seed.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
full=false
database_url=""
for arg in "$@"; do
  case "$arg" in
    --full) full=true ;;
    *) database_url="$arg" ;;
  esac
done
out="$here/$([ "$full" = true ] && echo initdb-full || echo initdb)"

if [ -z "$database_url" ]; then
  database_url="$(grep -E '^[[:space:]]*DATABASE_URL[[:space:]]*=' "$root/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
  [ -n "$database_url" ] || { echo "DATABASE_URL not found in .env; pass it as an argument." >&2; exit 1; }
fi
pg_dump="${PG_BIN:+$PG_BIN/}pg_dump"
command -v "$pg_dump" >/dev/null 2>&1 || { echo "Not found: $pg_dump (install PostgreSQL client tools or set PG_BIN)" >&2; exit 1; }

read -r db_host db_port db_user db_name < <(cd "$root" && uv run --quiet python - "$database_url" <<'PY'
import sys
from urllib.parse import unquote, urlsplit
u = urlsplit(sys.argv[1].replace("postgresql+psycopg://", "postgresql://", 1))
print(u.hostname or "localhost", u.port or 5432, unquote(u.username or ""), u.path.lstrip("/"))
PY
)
export PGPASSWORD="$(cd "$root" && uv run --quiet python -c 'import sys; from urllib.parse import unquote, urlsplit; print(unquote(urlsplit(sys.argv[1]).password or ""))' "$database_url")"
trap 'unset PGPASSWORD' EXIT

mkdir -p "$out"
rm -f "$out"/*.sql   # only this script's own old output
common=(--no-owner --no-privileges --no-password "--host=$db_host" "--port=$db_port" "--username=$db_user" "--dbname=$db_name")

if [ "$full" = true ]; then
  echo "FULL copy of the public schema with all rows (personal data) -> 01-full.sql"
  schema_file="$out/01-full.sql"
  "$pg_dump" "${common[@]}" --schema=public "--file=$schema_file"
else
  echo "Schema (public, no rows) -> 01-schema.sql"
  schema_file="$out/01-schema.sql"
  "$pg_dump" "${common[@]}" --schema-only --schema=public "--file=$schema_file"
  echo "Job listings + migration version -> 02-jobs.sql"
  "$pg_dump" "${common[@]}" --data-only --table=public.jobs --table=public.alembic_version "--file=$out/02-jobs.sql"
fi

# A fresh PostgreSQL already has the public schema; make the dump's CREATE SCHEMA safe to run there.
sed -i.bak 's/^CREATE SCHEMA public;/CREATE SCHEMA IF NOT EXISTS public;/' "$schema_file" && rm -f "$schema_file.bak"

ls -lh "$out"
if [ "$full" = true ]; then
  echo "PRIVATE seed ready. Build: docker build --build-arg SEED_DIR=initdb-full -t cafy-agent-db:full docker/postgres"
  echo "Push it only to a PRIVATE Docker Hub repository."
else
  echo "Seed ready. Build: docker build -t cafy-agent-db:local docker/postgres"
fi
