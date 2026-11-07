"""Build a clean SQLite database (for deployment) from the jobs in PostgreSQL.

Copies only public job data — the ``jobs`` and ``scraper_runs`` tables. No users, résumés,
tailored versions, emails or applications are copied, so the file is safe to deploy.

    uv run backend/scripts/copy_jobs_to_sqlite.py                 # -> backend/cafy_jobs.db
    uv run backend/scripts/copy_jobs_to_sqlite.py --out other.db
    uv run backend/scripts/copy_jobs_to_sqlite.py --all-statuses  # also inactive jobs

Needs DATABASE_URL (the Postgres source) in .env. The previous target file is backed up to
backups/ first, and the new file replaces it only after it has been fully written.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


def read_postgres(all_statuses: bool):
    from backend import dbcore
    from backend.database import JobDatabase

    if not dbcore.is_postgres():
        sys.exit("DATABASE_URL is not set: there is no Postgres database to copy from.")
    db = JobDatabase()
    where = "" if all_statuses else " WHERE status = 'active'"
    with db._get_connection() as conn:
        jobs = [dict(r) for r in conn.execute(f"SELECT * FROM jobs{where}").fetchall()]
        runs = [dict(r) for r in conn.execute("SELECT * FROM scraper_runs").fetchall()]
    return jobs, runs


def build_sqlite(path: Path, jobs, runs) -> None:
    # The app's own schema, created on SQLite (DATABASE_URL must be absent for that).
    os.environ.pop("DATABASE_URL", None)
    from backend.database import JobDatabase

    JobDatabase(db_path=str(path))
    conn = sqlite3.connect(path)
    try:
        for table, rows in (("jobs", jobs), ("scraper_runs", runs)):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if table == "scraper_runs":
                cols = [c for c in cols if c != "id"]  # let SQLite number the runs
            for row in rows:
                values = [row.get(c) for c in cols]
                conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", values)
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "backend" / "cafy_jobs.db"))
    parser.add_argument("--all-statuses", action="store_true", help="copy inactive jobs too")
    args = parser.parse_args()
    target = Path(args.out).resolve()

    jobs, runs = read_postgres(args.all_statuses)
    print(f"Read {len(jobs)} jobs and {len(runs)} scraper runs from Postgres.")

    with tempfile.TemporaryDirectory() as tmp:
        new_db = Path(tmp) / "cafy_jobs.db"
        build_sqlite(new_db, jobs, runs)
        check = sqlite3.connect(new_db)
        copied = check.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        personal = sum(check.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                       for t in ("users", "user_profiles", "user_resume_files", "tailored_resumes", "tailored_resume_versions"))
        check.close()
        if copied != len(jobs) or personal:
            sys.exit(f"Check failed: {copied} of {len(jobs)} jobs copied, {personal} personal rows present. Target unchanged.")
        if target.exists():
            backup_dir = ROOT / "backups"
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / f"{target.stem}_{datetime.now():%Y%m%d_%H%M%S}.db"
            shutil.copy2(target, backup)
            print(f"Backed up the previous file to {backup}")
        shutil.copy2(new_db, target)
    print(f"Wrote {copied} jobs to {target} ({target.stat().st_size / 1e6:.1f} MB); no personal data included.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
