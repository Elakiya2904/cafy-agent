#!/usr/bin/env bash
# Back up the existing (non-Docker) Cafy Agent PostgreSQL database to backups/*.dump. Read-only on the source.
# macOS / Linux version of docker/backup-local-db.ps1.
#
# Reads DATABASE_URL from .env (or the first argument), runs pg_dump in custom format, checks the dump
# can be read with pg_restore --list, and writes a SHA-256 checksum next to it.
#
#   ./docker/backup-local-db.sh
#   ./docker/backup-local-db.sh "postgresql://user:pass@localhost:5432/cafy_agent"
#   PG_BIN=/opt/homebrew/opt/postgresql@17/bin ./docker/backup-local-db.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out_dir="${OUT_DIR:-$root/backups}"
database_url="${1:-}"
if [ -z "$database_url" ]; then
  database_url="$(grep -E '^[[:space:]]*DATABASE_URL[[:space:]]*=' "$root/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
  [ -n "$database_url" ] || { echo "DATABASE_URL not found in .env; pass it as the first argument." >&2; exit 1; }
fi

pg_dump="${PG_BIN:+$PG_BIN/}pg_dump"
pg_restore="${PG_BIN:+$PG_BIN/}pg_restore"
for tool in "$pg_dump" "$pg_restore"; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Not found: $tool (install PostgreSQL client tools, e.g. brew install libpq, or set PG_BIN)" >&2; exit 1; }
done

# Split the URL with Python's parser so escaped characters in the password are handled correctly.
read -r db_host db_port db_user db_name < <(uv run --quiet python - "$database_url" <<'PY'
import sys
from urllib.parse import unquote, urlsplit
u = urlsplit(sys.argv[1].replace("postgresql+psycopg://", "postgresql://", 1))
print(u.hostname or "localhost", u.port or 5432, unquote(u.username or ""), u.path.lstrip("/"))
PY
)
export PGPASSWORD="$(uv run --quiet python -c 'import sys; from urllib.parse import unquote, urlsplit; print(unquote(urlsplit(sys.argv[1]).password or ""))' "$database_url")"
trap 'unset PGPASSWORD' EXIT

mkdir -p "$out_dir"
dump="$out_dir/${db_name}_$(date +%Y%m%d_%H%M%S).dump"
echo "Backing up $db_name on $db_host:$db_port as $db_user -> $dump"
"$pg_dump" --format=custom --compress=6 --no-password --host="$db_host" --port="$db_port" \
  --username="$db_user" --dbname="$db_name" --file="$dump"

tables="$("$pg_restore" --list "$dump" | grep -c ' TABLE DATA ' || true)"
if command -v shasum >/dev/null 2>&1; then hash="$(shasum -a 256 "$dump" | cut -d' ' -f1)"; else hash="$(sha256sum "$dump" | cut -d' ' -f1)"; fi
hash="$(printf '%s' "$hash" | tr '[:lower:]' '[:upper:]')"
printf '%s  %s\n' "$hash" "$(basename "$dump")" > "$dump.sha256"

echo "OK: $(du -h "$dump" | cut -f1), $tables tables with data, SHA-256 $hash"
echo "Dump: $dump"
