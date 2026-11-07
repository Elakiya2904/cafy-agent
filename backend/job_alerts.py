"""Per-user résumé job-alert preferences, matches, notifications, and daily delivery.

Stores alert settings, finds matching vacancies, and creates or sends alert
notifications for each candidate.
"""
import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import require_cron_secret
from .context import current_candidate
from .recommendation_service import MIN_MATCH_SCORE

logger = logging.getLogger("cafy.job_alerts")

JOB_ALERTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_alert_preferences (
    candidate_id TEXT PRIMARY KEY,
    roles_json TEXT NOT NULL DEFAULT '[]',
    locations_json TEXT NOT NULL DEFAULT '[]',
    employment_types_json TEXT NOT NULL DEFAULT '[]',
    experience_levels_json TEXT NOT NULL DEFAULT '[]',
    sponsorship_only INTEGER NOT NULL DEFAULT 0,
    daily_enabled INTEGER NOT NULL DEFAULT 0,
    email_enabled INTEGER NOT NULL DEFAULT 0,
    last_run_date TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_alert_matches (
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    match_score REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (candidate_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_job_alert_matches_candidate
    ON job_alert_matches(candidate_id, created_at);
CREATE TABLE IF NOT EXISTS job_alert_notifications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (candidate_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_job_alert_notifications_candidate
    ON job_alert_notifications(candidate_id, is_read, created_at);
"""

_EXPERIENCE_TERMS = {
    "graduate": re.compile(r"\b(?:graduate|grad scheme|new grad|early careers?|campus|trainee|apprentice)\b", re.I),
    "entry": re.compile(r"\b(?:entry[- ]level|junior|intern(ship)?|assistant|coordinator)\b", re.I),
    "mid": re.compile(r"\b(?:mid[- ]level|intermediate)\b", re.I),
    "senior": re.compile(r"\b(?:senior|staff|principal|lead|director|head of)\b", re.I),
}


def _clean_terms(values: List[str], limit: int = 20) -> List[str]:
    result: List[str] = []
    seen = set()
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()[:100]
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
        if len(result) >= limit:
            break
    return result


class JobAlertPreferencesIn(BaseModel):
    roles: List[str] = Field(default_factory=list, max_length=20)
    locations: List[str] = Field(default_factory=list, max_length=20)
    employment_types: List[str] = Field(default_factory=list, max_length=10)
    experience_levels: List[str] = Field(default_factory=list, max_length=10)
    sponsorship_only: bool = False
    daily_enabled: bool = False
    email_enabled: bool = False


class JobAlertsService:
    def __init__(self, database, user_store, recommendations, annotate_jobs: Callable,
                 email_agent, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.db = database
        self.user_store = user_store
        self.recommendations = recommendations
        self.annotate_jobs = annotate_jobs
        self.email_agent = email_agent
        self.now = now

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        conn = self.db._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def preferences(self, candidate: str) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM job_alert_preferences WHERE candidate_id = ?", (candidate,)
            ).fetchone()
        if not row:
            return self._default_preferences()
        return {
            "roles": json.loads(row["roles_json"] or "[]"),
            "locations": json.loads(row["locations_json"] or "[]"),
            "employment_types": json.loads(row["employment_types_json"] or "[]"),
            "experience_levels": json.loads(row["experience_levels_json"] or "[]"),
            "sponsorship_only": bool(row["sponsorship_only"]),
            "daily_enabled": bool(row["daily_enabled"]),
            "email_enabled": bool(row["email_enabled"]),
            "last_run_date": row["last_run_date"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _default_preferences() -> Dict[str, Any]:
        return {
            "roles": [],
            "locations": [],
            "employment_types": [],
            "experience_levels": [],
            "sponsorship_only": False,
            "daily_enabled": False,
            "email_enabled": False,
            "last_run_date": None,
            "updated_at": None,
        }

    def save_preferences(self, candidate: str, values: Dict[str, Any]) -> Dict[str, Any]:
        clean = {
            "roles": _clean_terms(values.get("roles") or []),
            "locations": _clean_terms(values.get("locations") or []),
            "employment_types": _clean_terms(values.get("employment_types") or [], 10),
            "experience_levels": _clean_terms(values.get("experience_levels") or [], 10),
        }
        allowed_levels = {"graduate", "entry", "junior", "mid", "senior"}
        invalid_levels = {level for level in clean["experience_levels"] if level.casefold() not in allowed_levels}
        if invalid_levels:
            raise ValueError(f"Unknown experience level: {', '.join(sorted(invalid_levels))}")

        email_enabled = bool(values.get("email_enabled"))
        if email_enabled and not self.email_agent.list_accounts(candidate):
            raise ValueError("Connect Gmail or Outlook before enabling email digests.")

        now = self.now().astimezone(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO job_alert_preferences "
                "(candidate_id, roles_json, locations_json, employment_types_json, experience_levels_json, "
                "sponsorship_only, daily_enabled, email_enabled, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(candidate_id) DO UPDATE SET roles_json=excluded.roles_json, "
                "locations_json=excluded.locations_json, employment_types_json=excluded.employment_types_json, "
                "experience_levels_json=excluded.experience_levels_json, sponsorship_only=excluded.sponsorship_only, "
                "daily_enabled=excluded.daily_enabled, email_enabled=excluded.email_enabled, updated_at=excluded.updated_at",
                (
                    candidate,
                    json.dumps(clean["roles"]),
                    json.dumps(clean["locations"]),
                    json.dumps(clean["employment_types"]),
                    json.dumps(clean["experience_levels"]),
                    int(bool(values.get("sponsorship_only"))),
                    int(bool(values.get("daily_enabled"))),
                    int(email_enabled),
                    now,
                ),
            )
        return self.preferences(candidate)

    def matches(self, candidate: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT j.*, m.match_score, m.created_at AS matched_at FROM job_alert_matches m "
                "JOIN jobs j ON j.id = m.job_id WHERE m.candidate_id = ? AND j.status = 'active' "
                "ORDER BY m.match_score DESC, m.created_at DESC LIMIT ?",
                (candidate, max(1, min(limit, 200))),
            ).fetchall()
        results = []
        for row in rows:
            job = dict(row)
            try:
                job["extracted_skills"] = json.loads(job.get("extracted_skills") or "[]")
            except (TypeError, ValueError):
                job["extracted_skills"] = []
            job["is_remote"] = bool(job.get("is_remote"))
            results.append(job)
        return self.annotate_jobs(results)

    def notifications(self, candidate: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT n.id, n.job_id, n.message, n.is_read, n.created_at, j.title, j.company, j.location, j.url "
                "FROM job_alert_notifications n JOIN jobs j ON j.id=n.job_id "
                "WHERE n.candidate_id=? AND j.status='active' ORDER BY n.created_at DESC LIMIT ?",
                (candidate, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_notifications_read(self, candidate: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE job_alert_notifications SET is_read=1 WHERE candidate_id=?", (candidate,)
            )

    @staticmethod
    def _matches_preferences(job: Dict[str, Any], preferences: Dict[str, Any]) -> bool:
        title = str(job.get("title") or "")
        location = str(job.get("location") or "")
        job_type = str(job.get("employment_type") or "")
        job_text = f"{title} {job.get('description') or ''}"

        roles = preferences["roles"]
        if roles and not any(role.casefold() in title.casefold() for role in roles):
            return False
        locations = preferences["locations"]
        if locations and not any(term.casefold() in location.casefold() for term in locations):
            return False
        types = preferences["employment_types"]
        if types and not any(term.casefold() in job_type.casefold() for term in types):
            return False
        levels = preferences["experience_levels"]
        if levels and not any(_EXPERIENCE_TERMS[level.casefold()].search(job_text) for level in levels):
            return False
        if preferences["sponsorship_only"] and not job.get("visa_sponsored"):
            return False
        return True

    def run_for_candidate(self, candidate: str, send_email: bool = False) -> Dict[str, Any]:
        preferences = self.preferences(candidate)
        resume = self.user_store.get_resume(candidate)
        if not resume:
            return {"candidate_id": candidate, "status": "needs_resume", "new_matches": 0}
        jobs = self.db.get_jobs(limit=10000)
        if preferences["sponsorship_only"]:
            jobs = self.annotate_jobs(jobs)
        ranked = self.recommendations.recommend_jobs(resume, jobs, min_score=MIN_MATCH_SCORE)
        filtered = [job for job in ranked if self._matches_preferences(job, preferences)]
        now = self.now().astimezone(timezone.utc).isoformat()
        new_matches: List[Dict[str, Any]] = []

        with self._conn() as conn:
            for job in filtered:
                score = float(job.get("match_score") or 0)
                cursor = conn.execute(
                    "INSERT INTO job_alert_matches (candidate_id, job_id, match_score, created_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(candidate_id, job_id) DO NOTHING",
                    (candidate, job["id"], score, now),
                )
                if cursor.rowcount:
                    new_matches.append(job)
                    message = f"{job.get('title', 'New role')} at {job.get('company', 'an employer')} matches your job alert."
                    conn.execute(
                        "INSERT INTO job_alert_notifications (id, candidate_id, job_id, message, created_at) "
                        "VALUES (?,?,?,?,?) ON CONFLICT(candidate_id, job_id) DO NOTHING",
                        (uuid.uuid4().hex, candidate, job["id"], message, now),
                    )
                else:
                    conn.execute(
                        "UPDATE job_alert_matches SET match_score=? WHERE candidate_id=? AND job_id=?",
                        (score, candidate, job["id"]),
                    )

            if send_email:
                conn.execute(
                    "UPDATE job_alert_preferences SET last_run_date=?, updated_at=? WHERE candidate_id=?",
                    (self.now().date().isoformat(), now, candidate),
                )

        if send_email and preferences["email_enabled"] and new_matches:
            try:
                self.email_agent.send_job_alert_digest(candidate, self._digest_body(new_matches))
            except Exception:
                logger.exception("Could not send job alert digest for candidate %s", candidate)

        return {
            "candidate_id": candidate,
            "status": "complete",
            "matching_jobs": len(filtered),
            "new_matches": len(new_matches),
        }

    @staticmethod
    def _digest_body(jobs: List[Dict[str, Any]]) -> str:
        lines = ["Your daily Cafy Agent job matches:", ""]
        for job in jobs[:10]:
            lines.extend(
                [
                    f"{job.get('title', 'Role')} — {job.get('company', 'Employer')}",
                    f"Location: {job.get('location') or 'Not specified'} | Match: {job.get('match_score', 0)}%",
                    str(job.get("url") or ""),
                    "",
                ]
            )
        if len(jobs) > 10:
            lines.append(f"Plus {len(jobs) - 10} more new matches in Job Alerts.")
        return "\n".join(lines)

    def run_daily(self) -> Dict[str, Any]:
        today = self.now().astimezone(timezone.utc).date().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT candidate_id, email_enabled, last_run_date FROM job_alert_preferences "
                "WHERE daily_enabled=1"
            ).fetchall()
        results = []
        for row in rows:
            if row["last_run_date"] == today:
                continue
            try:
                results.append(self.run_for_candidate(row["candidate_id"], send_email=True))
            except Exception:
                logger.exception("Daily job alert run failed for candidate %s", row["candidate_id"])
                results.append({"candidate_id": row["candidate_id"], "status": "failed"})
        return {"date": today, "processed": len(results), "results": results}

    def build_router(self, email_agent) -> APIRouter:
        router = APIRouter(prefix="/api/job-alerts", tags=["job-alerts"])

        @router.get("/preferences")
        def get_preferences():
            candidate = current_candidate()
            return {
                "preferences": self.preferences(candidate),
                "resume": self.user_store.get_resume(candidate),
                "email_accounts": email_agent.list_accounts(candidate),
                "email_providers": {name: provider.configured for name, provider in email_agent.providers.items()},
            }

        @router.put("/preferences")
        def put_preferences(body: JobAlertPreferencesIn):
            try:
                return {"preferences": self.save_preferences(current_candidate(), body.model_dump())}
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

        @router.get("/matches")
        def get_matches(limit: int = 100):
            return {"matches": self.matches(current_candidate(), limit)}

        @router.get("/notifications")
        def get_notifications(limit: int = 30):
            return {"notifications": self.notifications(current_candidate(), limit)}

        @router.post("/notifications/read")
        def read_notifications():
            self.mark_notifications_read(current_candidate())
            return {"ok": True}

        @router.post("/run")
        def run_now():
            return self.run_for_candidate(current_candidate())

        @router.post("/cron/daily")
        def cron_daily(request: Request):
            require_cron_secret(request)
            return self.run_daily()

        return router
