#!/usr/bin/env python3
"""One-off, idempotent copy of backend/cafy_jobs.db into the Postgres database in DATABASE_URL (Supabase).

    python scripts/migrate_sqlite_to_postgres.py --owner <supabase-user-uuid> [--sqlite PATH] [--dry-run]

* Rows stored under the old single-user id ("local") are re-assigned to --owner, so you see your data after signing in.
* Plain-text email tokens are encrypted on the way in.
* Safe to re-run: existing rows are left untouched (ON CONFLICT DO NOTHING).
* Finishes by comparing row counts per table; exits 1 on any mismatch.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BATCH = 500
SERIAL_TABLES = ("scraper_runs", "agent_logs", "agent_notifications", "application_events", "hiring_research_runs")
TOKEN_COLUMNS = {"connected_email_accounts": ("access_token", "refresh_token")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite", default=str(ROOT / "backend" / "cafy_jobs.db"))
    ap.add_argument("--owner", help="Supabase user id that should own rows created before accounts existed")
    ap.add_argument("--dry-run", action="store_true", help="read and report only; write nothing")
    args = ap.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set (put the Supabase connection string in .env).")
        return 2
    if not Path(args.sqlite).is_file():
        print(f"SQLite file not found: {args.sqlite}")
        return 2

    from backend.database import JobDatabase
    from backend.email_agent.crypto import encrypt

    pg_db = JobDatabase()  # creates / upgrades the Postgres schema
    src = sqlite3.connect(args.sqlite)
    src.row_factory = sqlite3.Row
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    failures = 0
    with pg_db._get_connection() as pg:
        for table in tables:
            pg_cols = [r["column_name"] for r in pg.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ?", (table,)).fetchall()]
            if not pg_cols:
                print(f"{table:32} SKIPPED (not in Postgres schema)")
                continue
            src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
            cols = [c for c in src_cols if c in pg_cols and c != "seq"]
            dropped = [c for c in src_cols if c not in cols]
            order = "rowid" if table != "sqlite_sequence" else "name"
            rows = src.execute(f"SELECT {','.join(cols)} FROM {table} ORDER BY {order}").fetchall()
            if not args.dry_run:
                sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) ON CONFLICT DO NOTHING"
                batch = []
                for row in rows:
                    values = list(row)
                    if args.owner and "candidate_id" in cols and values[cols.index("candidate_id")] == "local":
                        values[cols.index("candidate_id")] = args.owner
                    for tok in TOKEN_COLUMNS.get(table, ()):
                        if tok in cols and values[cols.index(tok)]:
                            v = values[cols.index(tok)]
                            values[cols.index(tok)] = v if v.startswith("enc:v1:") else encrypt(v)
                    batch.append(values)
                    if len(batch) >= BATCH:
                        pg.executemany(sql, batch)
                        batch = []
                if batch:
                    pg.executemany(sql, batch)
                if table in SERIAL_TABLES and "id" in cols:
                    pg.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))")
                pg.commit()
            n_pg = pg.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            ok = args.dry_run or n_pg >= len(rows)
            failures += 0 if ok else 1
            note = f" (columns not copied: {', '.join(dropped)})" if dropped else ""
            print(f"{table:32} sqlite={len(rows):7}  postgres={n_pg:7}  {'OK' if ok else 'MISMATCH'}{note}")
    src.close()
    print("\nDry run only; nothing was written." if args.dry_run else ("\nMigration complete." if not failures else f"\n{failures} table(s) did not match."))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
