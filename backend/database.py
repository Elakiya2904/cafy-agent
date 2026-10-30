import sqlite3
import json
import os
import shutil
from pathlib import Path
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("cafy.database")
DB_PATH = os.path.join(os.path.dirname(__file__), "cafy_jobs.db")

class JobDatabase:
    """
    Persistent SQLite storage and tracking for real scraped job listings,
    deduplication, listing updates, and scraper execution history.
    """

    def __init__(self, db_path: str = DB_PATH):
        if os.environ.get("VERCEL"):
            tmp_db = Path("/tmp/cafy_jobs.db")
            orig_db = Path(db_path)
            if not tmp_db.exists():
                if orig_db.exists():
                    try:
                        shutil.copy2(orig_db, tmp_db)
                        logger.info("Copied SQLite DB to %s for serverless write support", tmp_db)
                    except Exception as err:
                        logger.warning("Could not copy SQLite DB to /tmp: %s", err)
            if tmp_db.exists():
                self.db_path = str(tmp_db)
            else:
                self.db_path = db_path
        else:
            self.db_path = db_path

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
            
            # 1. Stored Job Listings
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                source_job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                platform TEXT NOT NULL,
                location TEXT,
                is_remote INTEGER DEFAULT 0,
                url TEXT NOT NULL,
                description TEXT,
                department TEXT,
                employment_type TEXT,
                posted_at TEXT,
                extracted_skills TEXT,
                first_seen TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            )
            """)

            # Indices for rapid querying & filtering
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_platform ON jobs(platform)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(is_remote)")

            # 2. Scraper Runs & Telemetry
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraper_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                duration_seconds REAL,
                jobs_found INTEGER DEFAULT 0,
                new_jobs INTEGER DEFAULT 0,
                updated_jobs INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT
            )
            """)

            # 3. Tailored Resumes Persistence
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tailored_resumes (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                resume_id TEXT NOT NULL,
                structured_data TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tailored_resumes_job_id ON tailored_resumes(job_id)")

            # 4. Tailored Resume Version History (one row per generated resume)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tailored_resume_versions (
                id TEXT PRIMARY KEY,
                resume_id TEXT NOT NULL UNIQUE,
                job_id TEXT NOT NULL,
                job_title TEXT,
                company TEXT,
                structured_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            # kind: "generated" (AI tailoring) or "edited" (user saved changes);
            # based_on: resume_id of the version an edit started from.
            version_columns = {row[1] for row in cursor.execute("PRAGMA table_info(tailored_resume_versions)")}
            if "kind" not in version_columns:
                cursor.execute("ALTER TABLE tailored_resume_versions ADD COLUMN kind TEXT NOT NULL DEFAULT 'generated'")
            if "based_on" not in version_columns:
                cursor.execute("ALTER TABLE tailored_resume_versions ADD COLUMN based_on TEXT")

            # Backfill versions for tailored resumes saved before version history existed.
            cursor.execute("""
            INSERT INTO tailored_resume_versions (id, resume_id, job_id, job_title, company, structured_data, created_at, updated_at)
            SELECT lower(hex(randomblob(16))), t.resume_id, t.job_id, j.title, j.company, t.structured_data, t.created_at, t.updated_at
            FROM tailored_resumes t
            LEFT JOIN jobs j ON j.id = t.job_id
            WHERE t.resume_id NOT IN (SELECT resume_id FROM tailored_resume_versions)
            """)

            conn.commit()
            logger.info(f"[JobDatabase] Initialized SQLite schema at {self.db_path}")
        except sqlite3.OperationalError as err:
            logger.warning("[JobDatabase] Could not run _init_db (read-only SQLite): %s", err)

    def save_or_update_jobs(self, jobs: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Deduplicates, inserts new listings, and updates changed listings.
        Preserves original `first_seen` timestamp and updates `last_checked`.
        """
        if not jobs:
            return {"new": 0, "updated": 0, "total": 0}

        now_iso = datetime.now(timezone.utc).isoformat()
        new_count = 0
        updated_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            for job in jobs:
                job_id = job.get("id")
                if not job_id:
                    continue

                skills_json = json.dumps(job.get("extracted_skills", []))
                is_remote_int = 1 if job.get("is_remote") else 0

                # Check if job already exists
                cursor.execute("SELECT id, title, description, url, status FROM jobs WHERE id = ?", (job_id,))
                existing = cursor.fetchone()

                if existing:
                    # Update existing record
                    cursor.execute("""
                    UPDATE jobs SET
                        title = ?,
                        company = ?,
                        platform = ?,
                        location = ?,
                        is_remote = ?,
                        url = ?,
                        description = ?,
                        department = ?,
                        employment_type = ?,
                        posted_at = ?,
                        extracted_skills = ?,
                        last_checked = ?,
                        status = 'active'
                    WHERE id = ?
                    """, (
                        job.get("title"),
                        job.get("company"),
                        job.get("platform"),
                        job.get("location"),
                        is_remote_int,
                        job.get("url"),
                        job.get("description"),
                        job.get("department"),
                        job.get("employment_type"),
                        job.get("posted_at"),
                        skills_json,
                        now_iso,
                        job_id
                    ))
                    updated_count += 1
                else:
                    # Insert new record
                    cursor.execute("""
                    INSERT INTO jobs (
                        id, source_job_id, title, company, platform, location, is_remote,
                        url, description, department, employment_type, posted_at,
                        extracted_skills, first_seen, last_checked, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """, (
                        job_id,
                        job.get("source_job_id", job_id),
                        job.get("title"),
                        job.get("company"),
                        job.get("platform"),
                        job.get("location"),
                        is_remote_int,
                        job.get("url"),
                        job.get("description"),
                        job.get("department"),
                        job.get("employment_type"),
                        job.get("posted_at"),
                        skills_json,
                        now_iso,
                        now_iso
                    ))
                    new_count += 1

            conn.commit()

        logger.info(f"[JobDatabase] Processed {len(jobs)} jobs: {new_count} new, {updated_count} updated.")
        return {"new": new_count, "updated": updated_count, "total": len(jobs)}

    def get_jobs(
        self,
        platform: Optional[str] = None,
        search: Optional[str] = None,
        remote_only: bool = False,
        status: str = "active",
        limit: int = 200,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Query verified stored jobs with filtering and pagination."""
        query = "SELECT * FROM jobs WHERE status = ?"
        params: List[Any] = [status]

        if platform and platform.lower() != "all":
            query += " AND platform = ?"
            params.append(platform.lower())

        if remote_only:
            query += " AND is_remote = 1"

        if search:
            query += " AND (title LIKE ? OR company LIKE ? OR description LIKE ? OR extracted_skills LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term])

        query += " ORDER BY last_checked DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for r in rows:
                try:
                    skills = json.loads(r["extracted_skills"]) if r["extracted_skills"] else []
                except Exception:
                    skills = []

                results.append({
                    "id": r["id"],
                    "source_job_id": r["source_job_id"],
                    "title": r["title"],
                    "company": r["company"],
                    "platform": r["platform"],
                    "location": r["location"],
                    "is_remote": bool(r["is_remote"]),
                    "url": r["url"],
                    "description": r["description"],
                    "department": r["department"],
                    "employment_type": r["employment_type"],
                    "posted_at": r["posted_at"],
                    "extracted_skills": skills,
                    "first_seen": r["first_seen"],
                    "last_checked": r["last_checked"],
                    "status": r["status"]
                })
            return results

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
        if not row:
            return None
        try:
            skills = json.loads(row["extracted_skills"]) if row["extracted_skills"] else []
        except Exception:
            skills = []
        return {
            "id": row["id"],
            "source_job_id": row["source_job_id"],
            "title": row["title"],
            "company": row["company"],
            "platform": row["platform"],
            "location": row["location"],
            "is_remote": bool(row["is_remote"]),
            "url": row["url"],
            "description": row["description"],
            "department": row["department"],
            "employment_type": row["employment_type"],
            "posted_at": row["posted_at"],
            "extracted_skills": skills,
            "first_seen": row["first_seen"],
            "last_checked": row["last_checked"],
            "status": row["status"],
        }

    def save_tailored_resume(self, job_id: str, resume_id: str, structured_data: Dict[str, Any]) -> str:
        now_iso = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(structured_data, ensure_ascii=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tailored_resumes WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                rec_id = row["id"]
                cursor.execute("""
                    UPDATE tailored_resumes
                    SET resume_id = ?, structured_data = ?, updated_at = ?
                    WHERE id = ?
                """, (resume_id, serialized, now_iso, rec_id))
            else:
                import uuid
                rec_id = uuid.uuid4().hex
                cursor.execute("""
                    INSERT INTO tailored_resumes (id, job_id, resume_id, structured_data, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (rec_id, job_id, resume_id, serialized, now_iso, now_iso))
            conn.commit()
            return rec_id

    def get_tailored_resume(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tailored_resumes WHERE job_id = ? ORDER BY updated_at DESC LIMIT 1", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            try:
                data = json.loads(row["structured_data"])
            except Exception:
                data = {}
            return {
                "id": row["id"],
                "job_id": row["job_id"],
                "resume_id": row["resume_id"],
                "resume": data,
                "updated_at": row["updated_at"],
                "created_at": row["created_at"],
            }

    def save_resume_version(
        self,
        resume_id: str,
        job_id: str,
        structured_data: Dict[str, Any],
        job_title: Optional[str] = None,
        company: Optional[str] = None,
        kind: str = "generated",
        based_on: Optional[str] = None,
    ) -> None:
        """Insert a version for ``resume_id``, or update its content if it already exists."""
        now_iso = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(structured_data, ensure_ascii=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tailored_resume_versions WHERE resume_id = ?", (resume_id,))
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE tailored_resume_versions
                    SET structured_data = ?, updated_at = ?,
                        job_title = COALESCE(?, job_title), company = COALESCE(?, company)
                    WHERE resume_id = ?
                    """,
                    (serialized, now_iso, job_title, company, resume_id),
                )
            else:
                import uuid
                cursor.execute(
                    """
                    INSERT INTO tailored_resume_versions
                        (id, resume_id, job_id, job_title, company, structured_data, created_at, updated_at, kind, based_on)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, resume_id, job_id, job_title, company, serialized, now_iso, now_iso, kind, based_on),
                )
            conn.commit()

    def get_resume_version(self, resume_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tailored_resume_versions WHERE resume_id = ?", (resume_id,)).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["structured_data"])
        except Exception:
            data = {}
        return {"resume_id": row["resume_id"], "job_id": row["job_id"], "kind": row["kind"], "resume": data}

    def list_resume_versions(self) -> List[Dict[str, Any]]:
        """All generated resume versions, newest first, numbered from 1 (oldest)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tailored_resume_versions ORDER BY created_at ASC, rowid ASC"
            ).fetchall()
        versions = []
        for number, row in enumerate(rows, start=1):
            try:
                data = json.loads(row["structured_data"])
            except Exception:
                data = {}
            versions.append({
                "version_number": number,
                "resume_id": row["resume_id"],
                "job_id": row["job_id"],
                "job_title": row["job_title"],
                "company": row["company"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "kind": row["kind"],
                "based_on": row["based_on"],
                "resume": data,
            })
        number_by_id = {v["resume_id"]: v["version_number"] for v in versions}
        for version in versions:
            version["based_on_version_number"] = number_by_id.get(version["based_on"])
        versions.reverse()
        for idx, version in enumerate(versions):
            version["is_current"] = idx == 0
        return versions

    def record_scraper_run(
        self,
        platform: str,
        started_at: str,
        finished_at: str,
        duration: float,
        jobs_found: int,
        new_jobs: int,
        updated_jobs: int,
        status: str,
        error_msg: Optional[str] = None
    ) -> int:
        """Records telemetry for an ATS scraping execution."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO scraper_runs 
            (platform, started_at, finished_at, duration_seconds, jobs_found, new_jobs, updated_jobs, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (platform, started_at, finished_at, duration, jobs_found, new_jobs, updated_jobs, status, error_msg))
            conn.commit()
            return cursor.lastrowid

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate stats across all platforms and listings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM jobs WHERE status = 'active'")
            total_active = cursor.fetchone()[0]

            cursor.execute("SELECT platform, count(*) FROM jobs WHERE status = 'active' GROUP BY platform")
            by_platform = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("""
            SELECT platform, status, finished_at, jobs_found, duration_seconds, error_message
            FROM scraper_runs
            ORDER BY id DESC LIMIT 10
            """)
            recent_runs = [dict(r) for r in cursor.fetchall()]

            # Skill frequency
            cursor.execute("SELECT extracted_skills FROM jobs WHERE status = 'active'")
            all_skill_rows = cursor.fetchall()
            skill_counts = {}
            for row in all_skill_rows:
                if row[0]:
                    try:
                        for sk in json.loads(row[0]):
                            skill_counts[sk] = skill_counts.get(sk, 0) + 1
                    except Exception:
                        pass
            top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:15]

            return {
                "total_active_jobs": total_active,
                "by_platform": by_platform,
                "recent_runs": recent_runs,
                "top_skills": [{"skill": s[0], "count": s[1]} for s in top_skills]
            }
