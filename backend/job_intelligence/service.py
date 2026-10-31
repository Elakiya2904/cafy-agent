"""Pipeline 4 orchestration: job → company research → role analysis → hiring-process
discovery → candidate compatibility → preparation plan.

Company intelligence is stored once per company and reused (30 days); role-specific
hiring information is stored per (company, job) and refreshed after 14 days or on request.
"""
import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from ..company_profiles import get_company_profile
from . import analysis
from .fetcher import parse_page
from .research import HiringResearcher

COMPANY_TTL_DAYS = 30
HIRING_TTL_DAYS = 14
UNAVAILABLE = "Hiring process information is currently unavailable."
STATUS_LABELS = {"officially_confirmed": "Officially confirmed", "publicly_reported": "Publicly reported", "estimated": "Estimated", "unknown": "Unknown"}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


class JobIntelligenceService:
    def __init__(self, database, researcher: HiringResearcher, match_fn: Callable[[Optional[Dict], Dict], Dict],
                 llm: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Optional[Dict[str, str]]]] = None,
                 profile_fn: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.db, self.researcher, self.match_fn, self.llm, self.now = database, researcher, match_fn, llm, now
        self.profile_fn = profile_fn

    # ------------------------------------------------------------------ db
    @contextmanager
    def _conn(self):
        conn = self.db._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _one(self, sql, args=()):
        with self._conn() as c:
            r = c.execute(sql, args).fetchone()
        return dict(r) if r else None

    def _all(self, sql, args=()):
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def _exec(self, sql, args=()):
        with self._conn() as c:
            c.execute(sql, args)

    def _fresh(self, ts: Optional[str], days: int) -> bool:
        return bool(ts) and self.now() - datetime.fromisoformat(ts) < timedelta(days=days)

    # ------------------------------------------------------------- company
    def company_intelligence(self, company: str, job: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
        cid = slugify(company)
        row = self._one("SELECT * FROM company_intelligence WHERE company_id=?", (cid,))
        if row and not refresh and self._fresh(row["last_researched"], COMPANY_TTL_DAYS) and (not self.profile_fn or row["industry"] or row["official_website"] or row["overview"]):
            return {**self._company_view(row), "reused": True}
        curated = get_company_profile(company)
        notes: List[str] = []
        public: Dict[str, Any] = {}
        if self.profile_fn:
            try:
                public = self.profile_fn(company) or {}
            except Exception as err:
                notes.append(f"Public company profile lookup failed: {err}")
        website, home, n = self.researcher.identify_website(company, job.get("company_website") or curated.get("website") or public.get("website"))
        notes += n
        verified = bool(website)
        if not website and public.get("website"):
            website = public["website"]  # named by Wikidata; the page itself could not be read (e.g. blocks bots)
            notes[:] = [x for x in notes if "official website" not in x.lower()]
            notes.append(f"Website taken from Wikidata ({public['source_url']}); the page could not be fetched to verify it.")
        meta: Dict[str, Any] = {}
        if home:
            page = parse_page(home.html, home.final_url)
            meta = {"description": page["meta"]["description"] or page["meta"]["org"].get("description"), "hq": page["meta"]["org"].get("address")}
        career = None
        if website:
            for res in self.researcher.company_pages(website, home)[:4]:
                if res.ok and re.search(r"career|jobs|join", res.final_url or res.url, re.I):
                    career = res.final_url or res.url
                    break
            if not career:
                notes.append("A careers page could not be confirmed on the company website.")
        overview = curated.get("description") or job.get("company_description") or meta.get("description") or public.get("overview")
        osrc = ("curated company profile" if (curated.get("description") or job.get("company_description"))
                else "company website" if meta.get("description") else "Wikipedia" if public.get("overview") else None)
        locations = [r["location"] for r in self._all("SELECT DISTINCT location FROM jobs WHERE company=? AND location IS NOT NULL AND location != '' LIMIT 12", (company,))]
        details = {"headquarters": curated.get("headquarters") or meta.get("hq") or public.get("headquarters"),
                   "company_size": curated.get("company_size") or public.get("company_size"),
                   "products_and_services": None, "business_model": None, "operating_locations": locations,
                   "overview_source": osrc, "website_verified": verified, "notes": notes}
        industry = curated.get("industry") or job.get("industry") or public.get("industry")
        if public and any(public.get(k) for k in ("industry", "headquarters", "company_size", "overview")):
            notes.append(f"Industry, headquarters, size and summary where not otherwise known come from Wikidata/Wikipedia ({public['source_url']}).")
        self._exec("INSERT INTO company_intelligence (company_id,company_name,industry,overview,official_website,career_page,details,last_researched) VALUES (?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(company_id) DO UPDATE SET industry=excluded.industry, overview=excluded.overview, official_website=excluded.official_website, "
                   "career_page=excluded.career_page, details=excluded.details, last_researched=excluded.last_researched",
                   (cid, company, industry, overview, website, career, json.dumps(details), self.now().isoformat()))
        return {**self._company_view(self._one("SELECT * FROM company_intelligence WHERE company_id=?", (cid,))), "reused": False}

    @staticmethod
    def _company_view(row: Dict[str, Any]) -> Dict[str, Any]:
        d = json.loads(row["details"] or "{}")
        fields = {"industry": row["industry"], "overview": row["overview"], "official_website": row["official_website"], "career_page": row["career_page"],
                  "headquarters": d.get("headquarters"), "company_size": d.get("company_size"), "products_and_services": d.get("products_and_services"),
                  "business_model": d.get("business_model"), "operating_locations": d.get("operating_locations") or []}
        return {"company_id": row["company_id"], "name": row["company_name"], **fields,
                "unavailable": [k for k, v in fields.items() if not v], "overview_source": d.get("overview_source"),
                "website_verified": d.get("website_verified", False), "notes": d.get("notes", []), "last_researched": row["last_researched"]}

    # ---------------------------------------------------------------- role
    def role_intelligence(self, job: Dict[str, Any], cid: str, match: Dict[str, Any]) -> Dict[str, Any]:
        role = analysis.analyze_role(job, match.get("job_skills") or [])
        h = hashlib.sha256((job.get("description") or "").encode()).hexdigest()[:16]
        prev = self._one("SELECT * FROM job_intelligence WHERE job_id=?", (job["id"],))
        interp = None
        if prev and prev["description_hash"] == h:
            interp = json.loads(prev["role_overview"] or "{}").get("interpretation")
        if interp is None and self.llm and role["has_description"]:
            try:
                interp = self.llm(job, role)
            except Exception:
                interp = None
        role["interpretation"] = ({**interp, "source": "ai_interpretation", "note": "AI interpretation of the posting, not stated by the employer."} if interp else None)
        self._exec("INSERT INTO job_intelligence (job_id,company_id,description_hash,role_overview,responsibilities,required_skills,experience_requirements,qualifications,updated_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET company_id=excluded.company_id, description_hash=excluded.description_hash, "
                   "role_overview=excluded.role_overview, responsibilities=excluded.responsibilities, required_skills=excluded.required_skills, "
                   "experience_requirements=excluded.experience_requirements, qualifications=excluded.qualifications, updated_at=excluded.updated_at",
                   (job["id"], cid, h, json.dumps(role), json.dumps(role["responsibilities"]), json.dumps(role["required_skills"]),
                    json.dumps(role["experience_requirements"]), json.dumps(role["qualifications"]), self.now().isoformat()))
        return role

    # -------------------------------------------------------------- hiring
    def hiring_process(self, company: Dict[str, Any], job: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
        cid = company["company_id"]
        run = self._one("SELECT * FROM hiring_research_runs WHERE company_id=? AND job_id=?", (cid, job["id"]))
        if run and not refresh and self._fresh(run["researched_at"], HIRING_TTL_DAYS):
            return {**self._load_stages(cid, job["id"], run), "reused": True}
        home = self.researcher.fetcher.get(company["official_website"]) if company.get("official_website") else None
        result = self.researcher.discover(company["name"], job, company.get("official_website"), home)
        ts = self.now().isoformat()
        with self._conn() as c:
            old = [r[0] for r in c.execute("SELECT id FROM hiring_processes WHERE company_id=? AND job_id=?", (cid, job["id"]))]
            for pid in old:
                c.execute("DELETE FROM hiring_process_sources WHERE hiring_process_id=?", (pid,))
            c.execute("DELETE FROM hiring_processes WHERE company_id=? AND job_id=?", (cid, job["id"]))
            for st in result["stages"]:
                pid = uuid.uuid4().hex
                from .analysis import STAGE_GUIDE
                c.execute("INSERT INTO hiring_processes (id,company_id,job_id,stage_key,stage_order,hiring_stage,stage_description,assessment_type,interview_format,confidence_status,scope,conflict,researched_at) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (pid, cid, job["id"], st["stage_key"], st["order"], st["stage"], STAGE_GUIDE.get(st["stage_key"], {}).get("purpose") or st.get("description"),
                           st["assessment_type"], st["interview_format"], st["status"], st["scope"], int(st["conflict"]), ts))
                for s in st["sources"]:
                    c.execute("INSERT INTO hiring_process_sources (id,hiring_process_id,source_url,source_type,is_official,evidence,publication_date,last_verified,link_status) VALUES (?,?,?,?,?,?,?,?,?)",
                              (uuid.uuid4().hex, pid, s["url"], s["source_type"], int(s["official"]), s["evidence"], s["published"], s["last_verified"], s["link_status"]))
            c.execute("INSERT INTO hiring_research_runs (company_id,job_id,researched_at,notes,sources_checked) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(company_id,job_id) DO UPDATE SET researched_at=excluded.researched_at, notes=excluded.notes, sources_checked=excluded.sources_checked",
                      (cid, job["id"], ts, json.dumps(result["notes"]), json.dumps(result["sources_checked"])))
        run = self._one("SELECT * FROM hiring_research_runs WHERE company_id=? AND job_id=?", (cid, job["id"]))
        return {**self._load_stages(cid, job["id"], run), "reused": False}

    def _load_stages(self, cid: str, job_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
        stages = []
        for r in self._all("SELECT * FROM hiring_processes WHERE company_id=? AND job_id=? ORDER BY stage_order", (cid, job_id)):
            srcs = self._all("SELECT source_url, source_type, is_official, evidence, publication_date, last_verified, link_status FROM hiring_process_sources WHERE hiring_process_id=?", (r["id"],))
            stages.append({"id": r["id"], "stage_key": r["stage_key"], "stage": r["hiring_stage"], "order": r["stage_order"], "description": r["stage_description"],
                           "assessment_type": r["assessment_type"], "interview_format": r["interview_format"], "status": r["confidence_status"],
                           "status_label": STATUS_LABELS[r["confidence_status"]], "scope": r["scope"], "conflict": bool(r["conflict"]),
                           "sources": [{"url": s["source_url"], "type": s["source_type"], "official": bool(s["is_official"]), "evidence": s["evidence"],
                                        "published": s["publication_date"], "last_verified": s["last_verified"], "link_status": s["link_status"]} for s in srcs]})
        return {"stages": stages, "notes": json.loads(run["notes"] or "[]"), "sources_checked": json.loads(run["sources_checked"] or "[]"),
                "researched_at": run["researched_at"], "available": bool(stages), "message": None if stages else UNAVAILABLE}

    # --------------------------------------------------------------- whole
    def get(self, candidate: str, job: Dict[str, Any], profile: Optional[Dict[str, Any]], refresh: bool = False) -> Dict[str, Any]:
        if not job.get("company"):
            return {"error": "The job has no company name, so the employer cannot be researched.", "job_id": job.get("id")}
        company = self.company_intelligence(job["company"], job, refresh)
        match = self.match_fn(profile, job) if profile else {"job_skills": analysis_skills(job)}
        role = self.role_intelligence(job, company["company_id"], match)
        hiring = self.hiring_process(company, job, refresh)
        comp = analysis.compatibility(profile, role, match, [s["stage_key"] for s in hiring["stages"]])
        plan = analysis.preparation_plan(role, comp, hiring["stages"])
        self._exec("INSERT INTO candidate_preparation (candidate_id,job_id,existing_skills,missing_skills,recommended_topics,preparation_plan,updated_at) VALUES (?,?,?,?,?,?,?) "
                   "ON CONFLICT(candidate_id,job_id) DO UPDATE SET existing_skills=excluded.existing_skills, missing_skills=excluded.missing_skills, "
                   "recommended_topics=excluded.recommended_topics, preparation_plan=excluded.preparation_plan, updated_at=excluded.updated_at",
                   (candidate, job["id"], json.dumps(comp.get("existing_skills", [])), json.dumps(comp.get("missing_skills", [])),
                    json.dumps(plan["topics_to_study"]), json.dumps(plan), self.now().isoformat()))
        sources = []
        seen = set()
        for st in hiring["stages"]:
            for s in st["sources"]:
                if s["url"] not in seen:
                    seen.add(s["url"])
                    sources.append({**s, "stages": [st["stage"]]})
                else:
                    next(x for x in sources if x["url"] == s["url"])["stages"].append(st["stage"])
        sponsor = {"employer_registered": job.get("visa_sponsor_registered"), "listed_for_job": job.get("visa_sponsored"),
                   "note": "Being on the UK sponsor register does not guarantee sponsorship for this vacancy; confirm with the employer."} if "visa_sponsor_registered" in job else None
        return {
            "job_id": job["id"], "generated_at": self.now().isoformat(),
            "company_overview": company,
            "role_overview": {**role, "sponsor": sponsor, "job_url": job.get("url")},
            "hiring_process": {"stages": hiring["stages"], "known_stage_count": len(hiring["stages"]), "available": hiring["available"], "message": hiring["message"],
                               "assessments": [s for s in hiring["stages"] if s["assessment_type"]], "researched_at": hiring["researched_at"], "notes": hiring["notes"],
                               "disclaimer": "Hiring processes vary by role, team, seniority and country. Only stages with a source are shown; labels show how well each is supported."},
            "interview_preparation": plan,
            "candidate_compatibility": comp,
            "sources": {"items": sources, "checked": hiring["sources_checked"], "labels": STATUS_LABELS},
            "reuse": {"company_reused": company["reused"], "hiring_reused": hiring["reused"]},
        }

    def report_issue(self, candidate: str, job_id: str, section: str, message: str, stage_key: Optional[str] = None) -> None:
        self._exec("INSERT INTO intelligence_reports (candidate_id,job_id,section,stage_key,message,created_at) VALUES (?,?,?,?,?,?)",
                   (candidate, job_id, section, stage_key, message.strip()[:1000], self.now().isoformat()))


def analysis_skills(job: Dict[str, Any]) -> List[str]:
    from ..job_match_analysis_service import _job_skills
    return _job_skills(job)
