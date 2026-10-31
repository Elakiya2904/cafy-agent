import json
import os
import re
import tempfile
import uuid

# Verify HTTPS against the operating system's certificate store instead of Python's bundled
# list. Antivirus HTTPS scanning (e.g. AVG) re-signs traffic with a root the OS trusts but
# certifi does not, which otherwise makes every Groq call fail with CERTIFICATE_VERIFY_FAILED.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
from fastapi.responses import FileResponse, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .scrapers.scraper_manager import ScraperManager
from .database import JobDatabase
from .auth import AuthMiddleware, auth_configured, is_production, require_cron_secret, validate_production_config
from .context import current_candidate
from .user_store import MAX_RESUME_BYTES, UserSession, UserStore
from .scheduler import ScrapingScheduler
from .resume_service import ResumeService
from .recommendation_service import RecommendationService
from .sponsor_service import VisaSponsorRegistry
from .career_chat_service import CareerChatError, CareerChatService, build_career_context
from .company_profiles import enrich_jobs_with_company_profiles
from .resume_generation_service import ResumeGenerationError, ResumeGenerationService
from .export_service import EXPORT_PARTS, build_export_zip
from .profile_strength_service import evaluate_profile_strength
from .job_match_analysis_service import analyze_profile_for_job
from .email_agent.service import EmailAgentService
from .email_agent.api import build_router as build_email_agent_router
from .email_agent.monitor import EmailMonitor
from .job_applications.service import JobApplicationService
from .job_applications.api import build_router as build_job_applications_router
from .job_applications.answers import groq_answer
from .job_intelligence.service import JobIntelligenceService
from .job_intelligence.research import HiringResearcher
from .job_intelligence.api import build_router as build_job_intelligence_router
from .job_intelligence.llm import interpret_role
from .job_intelligence.profile_lookup import lookup_company

logger = logging.getLogger("cafy.api")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class CareerChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=1200)


class CareerChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["opportunities", "skills", "market", "progress"] = "opportunities"
    history: List[CareerChatTurn] = Field(default_factory=list)
    resume_data: Optional[Dict[str, Any]] = None
    pipeline_job_ids: List[str] = Field(default_factory=list)
    focus_job_id: Optional[str] = None


class ResumeGenerationRequest(BaseModel):
    job_id: str
    resume_data: Optional[Dict[str, Any]] = None
    # Tailor flow inputs: a pasted/edited job description and free-text steering for the rewrite.
    job_description: Optional[str] = None
    additional_instructions: Optional[str] = None


class PreGenerationAnalysisRequest(BaseModel):
    job_id: str
    resume_data: Optional[Dict[str, Any]] = None


class ExportApplication(BaseModel):
    job_id: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    url: Optional[str] = None


class DataExportRequest(BaseModel):
    include: List[str] = Field(default_factory=list)
    applications: List[ExportApplication] = Field(default_factory=list)


class ResumeSaveRequest(BaseModel):
    job_id: str
    resume_id: Optional[str] = None
    resume: Dict[str, Any]



class ProfileUpdateRequest(BaseModel):
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[List[Dict[str, Any]]] = None
    education: Optional[List[Dict[str, Any]]] = None
    projects: Optional[List[Dict[str, Any]]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    seniority_level: Optional[str] = None
    target_roles: Optional[List[str]] = None

class ResumeRewriteSectionRequest(BaseModel):
    job_id: str
    section: str
    content: str
    resume_data: Optional[Dict[str, Any]] = None

app = FastAPI(
    title="Cafy Agent API",
    description="ATS job scraper with SQLite persistence, sponsor-register matching, and skill-based job recommendations.",
    version="2.1.0"
)

# Added first so CORS (added next, therefore outermost) also decorates 401 responses.
app.add_middleware(AuthMiddleware)
_cors_origins = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,  # auth is a Bearer token, never a cookie
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_frontend_html_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# Services initialization
validate_production_config()
db = JobDatabase()
user_store = UserStore(db)
scraper_mgr = ScraperManager()
scheduler = ScrapingScheduler(scraper_manager=scraper_mgr, database=db, interval_hours=6.0)
resume_svc = ResumeService()
rec_svc = RecommendationService()
sponsor_registry = VisaSponsorRegistry.from_directory(
    PROJECT_ROOT / "sponsor-data",
    PROJECT_ROOT / "ireland-data",
)
career_chat_svc = CareerChatService()
resume_generation_svc = ResumeGenerationService(PROJECT_ROOT)
email_agent_svc = EmailAgentService(db)
email_monitor = EmailMonitor(email_agent_svc)
app.include_router(build_email_agent_router(email_agent_svc, email_monitor))


def _stored_resume_file() -> Optional[Dict[str, Any]]:
    """The caller's uploaded résumé, written to a temp file because the job-application flow serves it by path."""
    file = user_store.file_content(current_candidate())
    if not file:
        return None
    suffix = Path(file["filename"]).suffix.lower() or ".bin"
    path = Path(tempfile.gettempdir()) / "cafy-resume-files" / f"{uuid.uuid4().hex}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file["content"])
    return {"path": str(path), "filename": file["filename"], "content_type": file["content_type"]}


def _hand_off_to_email_agent(candidate: str, payload: Dict[str, Any]) -> None:
    """Pipeline 2 → Pipeline 3: register the submitted application so recruiter emails can be matched."""
    email_agent_svc.upsert_application(
        candidate, payload["company"], payload["job_title"], payload.get("job_id"),
        payload.get("applied_at"), None, payload.get("reference_id"),
    )


job_application_svc = JobApplicationService(
    db,
    profile_provider=lambda: ACTIVE_SESSION.get("resume"),
    resume_file_provider=_stored_resume_file,
    job_lookup=db.get_job,
    answer_generator=groq_answer,
    on_submitted=_hand_off_to_email_agent,
)
app.include_router(build_job_applications_router(job_application_svc))


def _intelligence_job(job_id: str) -> Optional[Dict[str, Any]]:
    job = db.get_job(job_id)
    if not job:
        return None
    return enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs([job]))[0]


job_intelligence_svc = JobIntelligenceService(db, HiringResearcher(), analyze_profile_for_job, llm=interpret_role, profile_fn=lookup_company)
app.include_router(build_job_intelligence_router(job_intelligence_svc, _intelligence_job, lambda: ACTIVE_SESSION.get("resume")))

# Per-user résumé + match cache (current user comes from the verified auth token).
ACTIVE_SESSION = UserSession(user_store)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


@app.on_event("startup")
def startup_event():
    # Only run the background scheduler in standard server mode, not ephemeral serverless
    if not os.environ.get("VERCEL"):
        scheduler.start()
        email_monitor.start()
        logger.info("[Main] Background scheduler initiated.")
    else:
        logger.info("[Main] Vercel environment detected; scheduler thread omitted.")

@app.on_event("shutdown")
def shutdown_event():
    if scheduler.is_running:
        scheduler.stop()
        logger.info("[Main] Background scheduler stopped.")
    email_monitor.stop()

@app.get("/api/health")
def health():
    stats = db.get_stats()
    return {
        "status": "online",
        "app": "Cafy Agent",
        "total_active_jobs": stats["total_active_jobs"],
        "platforms_supported": len(scraper_mgr.scrapers),
        "scheduler_active": scheduler.is_running
    }

@app.get("/api/platforms")
def get_platforms():
    platforms = scraper_mgr.get_supported_platforms()
    stats = db.get_stats()
    by_plat = stats.get("by_platform", {})
    for p in platforms:
        p["stored_jobs_count"] = by_plat.get(p["id"], 0)
    return {
        "platforms": platforms,
        "total_jobs": stats["total_active_jobs"]
    }

@app.get("/api/scrapers/status")
def get_scrapers_status():
    stats = db.get_stats()
    platforms = scraper_mgr.get_supported_platforms()
    return {
        "platforms": platforms,
        "recent_runs": stats.get("recent_runs", []),
        "total_active_jobs": stats.get("total_active_jobs", 0)
    }

def _scrape_and_store(platform: str) -> Dict[str, Any]:
    """Scrape one platform (or all) and persist the real listings plus run telemetry."""
    if platform == "all":
        scheduler.run_now()
        return {"platform": "all"}
    res = scraper_mgr.scrape_platform(platform)
    jobs = res.get("jobs", [])
    stats = db.save_or_update_jobs(jobs)
    db.record_scraper_run(
        platform=platform,
        started_at=res.get("timestamp"),
        finished_at=res.get("timestamp"),
        duration=res.get("duration_seconds", 0.0),
        jobs_found=len(jobs),
        new_jobs=stats.get("new", 0),
        updated_jobs=stats.get("updated", 0),
        status=res.get("status", "unknown"),
        error_msg=res.get("error")
    )
    return {"platform": platform, "status": res.get("status"), "found": len(jobs), **stats}


@app.get("/api/cron/scrape")
def cron_scrape(request: Request, platform: str):
    """Scheduled scrape for serverless hosting, where the in-process scheduler cannot run (one platform per call)."""
    require_cron_secret(request)
    return _scrape_and_store(platform)


@app.post("/api/scrape")
@app.post("/api/scrapers/run")
def trigger_scrape(background_tasks: BackgroundTasks, platform: Optional[str] = "all"):
    """Trigger an asynchronous scraping run across one or all configured ATS platforms."""
    background_tasks.add_task(_scrape_and_store, platform or "all")
    return {
        "status": "started",
        "message": f"Scraping run dispatched for {platform}.",
        "platform": platform
    }

@app.get("/api/jobs")
def get_jobs(
    platform: Optional[str] = None,
    search: Optional[str] = None,
    remote_only: bool = False,
    limit: int = 3000,
    offset: int = 0
):
    """Retrieve stored jobs from database with optional filters."""
    jobs = db.get_jobs(platform=platform, search=search, remote_only=remote_only, limit=limit, offset=offset)
    jobs = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(jobs))
    return {
        "count": len(jobs),
        "jobs": jobs
    }

def _store_uploaded_resume(
    filename: str, content_type: Optional[str], content: bytes, parsed: Optional[Dict[str, Any]] = None
) -> None:
    """Keep the caller's most recently uploaded original file so it can be previewed and downloaded later."""
    user_store.save_file(current_candidate(), filename, content_type, content, _profile_as_resume(parsed or {}))


def _profile_as_resume(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "personal_info": {
            "name": profile.get("candidate_name") or "",
            "email": profile.get("email") or "",
            "phone": profile.get("phone") or "",
            "linkedin": profile.get("linkedin") or "",
            "github": profile.get("github") or "",
        },
        "professional_summary": profile.get("summary") or "",
        "skills": profile.get("skills") or [],
        "experience": profile.get("experience") or [],
        "projects": profile.get("projects") or [],
        "education": profile.get("education") or [],
        "certifications": profile.get("certifications") or [],
    }


@app.get("/api/resume/uploaded")
def get_uploaded_resume():
    """Metadata for the original uploaded resume file, if one was uploaded."""
    meta = user_store.file_meta(current_candidate())
    if not meta:
        return {"uploaded": None}
    return {
        "uploaded": {
            "filename": meta["filename"],
            "content_type": meta["content_type"],
            "size_bytes": meta["size_bytes"],
            "uploaded_at": meta["uploaded_at"],
            "resume": meta.get("resume") or {},
            "preview_url": "/api/resume/uploaded/file",
            "download_url": "/api/resume/uploaded/file?download=true",
        }
    }


@app.get("/api/resume/uploaded/file")
def get_uploaded_resume_file(download: bool = False):
    file = user_store.file_content(current_candidate())
    if not file:
        raise HTTPException(status_code=404, detail="No uploaded resume file is stored.")
    safe_name = re.sub(r'[^\w.\- ]', "_", file["filename"])
    return Response(
        content=file["content"],
        media_type=file["content_type"],
        headers={"Content-Disposition": f'{"attachment" if download else "inline"}; filename="{safe_name}"'},
    )


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Parse candidate résumé and match against verified jobs in database."""
    try:
        content = await file.read()
        if len(content) > MAX_RESUME_BYTES:
            raise HTTPException(status_code=413, detail="Résumé file is larger than 10 MB.")
        parsed = resume_svc.parse_resume(file.filename, content)
        ACTIVE_SESSION["resume"] = parsed
        try:
            _store_uploaded_resume(file.filename, file.content_type, content, parsed)
        except Exception as error:
            # Parsing and matching still work if only the original-file copy could not be stored.
            logger.warning("[API] Could not store original resume file: %s", error)

        # Query database across all platforms (up to 3000 jobs)
        stored_jobs = db.get_jobs(limit=3000)
        recommendations = rec_svc.recommend_jobs(parsed, stored_jobs, min_score=60)
        recommendations = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(recommendations))
        ACTIVE_SESSION["last_matched_jobs"] = recommendations

        return {
            "status": "success",
            "resume": parsed,
            "profile_strength": parsed.get("profile_strength") or evaluate_profile_strength(parsed),
            "matched_jobs": recommendations,
            "total_matches": len(recommendations)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Resume parsing error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process résumé: {str(e)}")

@app.get("/api/resume/current")
def get_current_resume():
    resume = ACTIVE_SESSION["resume"]
    if not resume:
        return {"resume": None, "profile_strength": None, "matched_jobs": []}
    strength = resume.get("profile_strength") or evaluate_profile_strength(resume)
    resume["profile_strength"] = strength
    matched = ACTIVE_SESSION["last_matched_jobs"]
    if not matched:
        stored_jobs = db.get_jobs(limit=3000)
        matched = rec_svc.recommend_jobs(resume, stored_jobs, min_score=60)
        matched = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(matched))
        ACTIVE_SESSION["last_matched_jobs"] = matched
    return {"resume": resume, "profile_strength": strength, "matched_jobs": enrich_jobs_with_company_profiles(matched)}


@app.post("/api/resume/update")
def update_resume_profile(request: ProfileUpdateRequest):
    """Update candidate profile fields and immediately re-evaluate profile completeness."""
    curr = ACTIVE_SESSION.get("resume")
    if not curr:
        raise HTTPException(status_code=400, detail="Upload a résumé first.")
    data = request.dict(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            curr[k] = v

    if "skills" in data and curr.get("skills"):
        from .resume_service import SKILL_TAXONOMY
        categorized = {}
        for cat, cat_skills in SKILL_TAXONOMY.items():
            cat_lower = {s.lower() for s in cat_skills}
            matches = [s for s in curr["skills"] if s.lower() in cat_lower]
            if matches:
                categorized[cat] = matches
        curr["categorized_skills"] = categorized
        curr["total_skills"] = len(curr["skills"])

    strength = evaluate_profile_strength(curr)
    curr["profile_strength"] = strength
    ACTIVE_SESSION["resume"] = curr

    return {
        "status": "success",
        "resume": curr,
        "profile_strength": strength
    }


@app.post("/api/profile/strength")
def get_profile_strength(resume_data: Optional[Dict[str, Any]] = None):
    """Evaluate profile completeness score and suggestions for given or active resume."""
    target = resume_data or ACTIVE_SESSION.get("resume")
    return evaluate_profile_strength(target)


@app.post("/api/resumes/pre-analysis")
def pre_generation_analysis(request: PreGenerationAnalysisRequest):
    """Score a (possibly job-specific, unsaved) profile against a job before generating a resume.

    ``resume_data`` lets the client send its working copy so edits that have not been
    synced to the Master Profile are still reflected in the scores.
    """
    profile = request.resume_data or ACTIVE_SESSION.get("resume")
    if not profile:
        raise HTTPException(status_code=400, detail="Upload a résumé before analysing a job match.")
    job = db.get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The selected job could not be found.")
    return analyze_profile_for_job(profile, job)


@app.post("/api/resumes/generate")
def generate_resume(request: ResumeGenerationRequest):
    resume = request.resume_data or ACTIVE_SESSION.get("resume")
    job = db.get_job(request.job_id)
    if job:
        job = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs([job]))[0]
    if (request.job_description or "").strip():
        job = {**(job or {}), "description": request.job_description.strip()}
    try:
        result = resume_generation_svc.generate(
            resume or {}, job or {}, resume_svc, instructions=request.additional_instructions
        )
        if result.get("resume_id") and result.get("resume"):
            db.save_tailored_resume(request.job_id, result["resume_id"], result["resume"])
            db.save_resume_version(
                result["resume_id"], request.job_id, result["resume"],
                job_title=(job or {}).get("title"), company=(job or {}).get("company"),
            )
        return result
    except ResumeGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


_RESUME_ID = re.compile(r"^[0-9a-f]{32}$")


def _artifact_urls(resume_id: str) -> Dict[str, Optional[str]]:
    out_dir = resume_generation_svc.output_dir
    return {
        "pdf_url": f"/api/resumes/{resume_id}/pdf" if (out_dir / f"{resume_id}.pdf").exists() else None,
        "docx_url": f"/api/resumes/{resume_id}/docx",
        "tex_url": f"/api/resumes/{resume_id}/latex",
    }


def _owned_artifact(resume_id: str, ext: str) -> Path:
    """Path to a generated file, only for the version's owner; re-rendered from stored data if the disk copy is gone."""
    version = db.get_resume_version(resume_id) if _RESUME_ID.match(resume_id) else None
    if not version:
        raise HTTPException(status_code=404, detail="Resume was not found.")
    path = resume_generation_svc.output_dir / f"{resume_id}.{ext}"
    if not path.is_file():
        try:
            resume_generation_svc.update_artifacts(resume_id, version["resume"])
        except Exception as error:
            logger.warning("[API] Could not re-render %s.%s: %s", resume_id, ext, error)
    return path


@app.get("/api/resumes/versions")
def list_resume_versions():
    """Every generated tailored resume, newest first."""
    versions = [{**v, **_artifact_urls(v["resume_id"])} for v in db.list_resume_versions()]
    return {"count": len(versions), "versions": versions}


@app.post("/api/export")
def export_data(request: DataExportRequest):
    include = [part for part in request.include if part in EXPORT_PARTS]
    if not include:
        raise HTTPException(status_code=400, detail="Choose at least one item to export.")
    applications = [a.model_dump() if hasattr(a, "model_dump") else a.dict() for a in request.applications]
    payload = build_export_zip(
        include=include,
        profile=ACTIVE_SESSION.get("resume"),
        applications=applications,
        versions=db.list_resume_versions() if "resumes" in include else [],
        resume_dir=resume_generation_svc.output_dir,
    )
    filename = f"cafy-export-{datetime.now(timezone.utc):%Y%m%d}.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/resumes/job/{job_id}")
def get_job_tailored_resume(job_id: str):
    rec = db.get_tailored_resume(job_id)
    if not rec:
        return {"status": "not_found", "tailored_resume": None}
    resume_id = rec.get("resume_id")
    urls = _artifact_urls(resume_id)
    return {
        "status": "found",
        "tailored_resume": rec["resume"],
        "resume_id": resume_id,
        "updated_at": rec.get("updated_at"),
        **urls,
        "pdf_available": bool(urls["pdf_url"]),
        "docx_available": True,
    }


@app.post("/api/resumes/save")
def save_tailored_resume(request: ResumeSaveRequest):
    job = db.get_job(request.job_id) or {}
    master_resume = ACTIVE_SESSION.get("resume") or {}
    normalized = resume_generation_svc._validate_and_normalize(request.resume, master_resume, job)

    # Manual edits are stored in the current version; new versions come only from AI
    # generation and full AI rewrites.
    resume_id = request.resume_id or uuid.uuid4().hex
    artifacts = resume_generation_svc.update_artifacts(resume_id, normalized)
    db.save_tailored_resume(request.job_id, resume_id, normalized)
    db.save_resume_version(resume_id, request.job_id, normalized, job_title=job.get("title"), company=job.get("company"))
    return {
        "status": "saved",
        "resume_id": resume_id,
        "resume": normalized,
        **artifacts,
    }


@app.post("/api/resumes/rewrite-full")
def rewrite_full_resume(request: ResumeSaveRequest):
    """Rewrite the whole tailored resume for the job with AI and store it as a new version.

    The rewrite cannot add facts (see ResumeGenerationService.merge_rewrite). Job skills the
    resume lacks are returned as recommendations for the user to add themselves.
    """
    job = db.get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The selected job could not be found.")
    master_resume = ACTIVE_SESSION.get("resume") or {}
    current = resume_generation_svc._validate_and_normalize(request.resume, master_resume, job)
    try:
        outcome = resume_generation_svc.rewrite_full(current, job, resume_svc)
    except ResumeGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    rewritten = resume_generation_svc._validate_and_normalize(outcome["resume"], master_resume, job)

    resume_id = uuid.uuid4().hex
    artifacts = resume_generation_svc.update_artifacts(resume_id, rewritten)
    db.save_tailored_resume(request.job_id, resume_id, rewritten)
    db.save_resume_version(
        resume_id, request.job_id, rewritten,
        job_title=job.get("title"), company=job.get("company"),
        kind="ai_rewrite", based_on=request.resume_id,
    )

    have = {str(s).lower() for s in rewritten.get("skills") or []}
    job_skills = job.get("extracted_skills") or resume_svc.extract_skills(f"{job.get('title', '')} {job.get('description', '')}")
    recommended = [s for s in job_skills if str(s).lower() not in have]
    return {
        "status": "rewritten",
        "resume_id": resume_id,
        "resume": rewritten,
        "rejected_lines": outcome["rejected_lines"],
        "recommended_skills": recommended,
        **artifacts,
    }


@app.post("/api/resumes/rewrite-section")
def rewrite_resume_section(request: ResumeRewriteSectionRequest):
    job = db.get_job(request.job_id) or {}
    resume_data = request.resume_data or ACTIVE_SESSION.get("resume") or {}
    try:
        rewritten = resume_generation_svc.rewrite_section(
            section=request.section,
            content=request.content,
            job=job,
            resume_data=resume_data
        )
    except ResumeGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "status": "success",
        "section": request.section,
        "rewritten": rewritten,
    }


@app.get("/api/resumes/{resume_id}/latex")
def download_resume_latex(resume_id: str):
    path = _owned_artifact(resume_id, "tex")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Resume source was not found.")
    return FileResponse(path, media_type="application/x-tex", filename=f"{resume_id}.tex")


@app.get("/api/resumes/{resume_id}/docx")
def download_resume_docx(resume_id: str):
    path = _owned_artifact(resume_id, "docx")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="DOCX version is not available.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{resume_id}.docx"
    )


@app.get("/api/resumes/{resume_id}/pdf")
def download_resume_pdf(resume_id: str):
    path = _owned_artifact(resume_id, "pdf")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF is unavailable. Download the DOCX or LaTeX source instead.")
    return FileResponse(path, media_type="application/pdf", filename=f"{resume_id}.pdf")

@app.post("/api/jobs/match")
@app.post("/api/recommend")
def recommend_filtered(platform: str = "all", min_score: int = 60):
    if not ACTIVE_SESSION["resume"]:
        raise HTTPException(status_code=400, detail="No résumé uploaded yet.")
    stored_jobs = db.get_jobs(platform=platform, limit=3000)
    recs = rec_svc.recommend_jobs(ACTIVE_SESSION["resume"], stored_jobs, min_score=min_score, platform_filter=platform)
    recs = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(recs))
    return {
        "count": len(recs),
        "matched_jobs": recs
    }

@app.post("/api/companies/add")
@app.post("/api/companies")
def add_company(
    platform: str = Form(...),
    token: str = Form(...),
    name: str = Form(...),
    host: Optional[str] = Form(""),
    site: Optional[str] = Form("")
):
    comp_data = {"token": token, "name": name}
    if host:
        comp_data["host"] = host
    if site:
        comp_data["site"] = site

    success = scraper_mgr.add_company_source(platform, comp_data)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to add company to {platform}")

    # Immediately scrape this single company
    p_res = scraper_mgr.scrape_platform(platform)
    jobs = p_res.get("jobs", [])
    stats = db.save_or_update_jobs(jobs)

    return {
        "status": "success",
        "message": f"Added {name} to {platform}. Indexed {stats.get('new', 0)} new jobs.",
        "scraped_count": len(jobs)
    }

@app.get("/api/stats")
def get_stats():
    return db.get_stats()


@app.post("/api/career-chat")
def career_chat(request: CareerChatRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Enter a question for the Career Analyst.")

    resume = request.resume_data

    # Cap at 1500 jobs for chat context — enough signal, avoids TF-IDF timeout
    jobs = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(db.get_jobs(limit=1500)))

    matched_jobs = []
    if resume:
        active_resume = ACTIVE_SESSION.get("resume") or {}
        same_profile = (
            set(active_resume.get("skills", [])) == set(resume.get("skills", []))
            and active_resume.get("target_roles", []) == resume.get("target_roles", [])
        )
        # Reuse cached matches if same profile — avoids re-running TF-IDF
        if same_profile and ACTIVE_SESSION.get("last_matched_jobs"):
            matched_jobs = ACTIVE_SESSION["last_matched_jobs"]
        else:
            matched_jobs = rec_svc.recommend_jobs(
                resume,
                [dict(job) for job in jobs],
                min_score=60,
            )
            matched_jobs = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(matched_jobs))
            ACTIVE_SESSION["last_matched_jobs"] = matched_jobs

    context, job_cards, intent = build_career_context(
        query=query,
        mode=request.mode,
        resume=resume,
        jobs=jobs,
        matched_jobs=matched_jobs,
        pipeline_job_ids=request.pipeline_job_ids[:300],
        focus_job_id=request.focus_job_id,
    )
    history = [turn.model_dump() if hasattr(turn, "model_dump") else turn.dict() for turn in request.history[-8:]]

    try:
        answer = career_chat_svc.answer(query, request.mode, context, job_cards, intent, history)
    except CareerChatError as error:
        status_code = 503 if "not configured" in str(error).casefold() else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error

    return {
        "answer": answer,
        "job_cards": job_cards,
        "evidence": {
            "profile_loaded": bool(resume),
            "profile_match_count": len(matched_jobs),
            "analyzed_job_count": len(jobs),
            "pipeline_job_count": len(request.pipeline_job_ids),
        },
    }

# Mount static frontend: prefer the Vite production build when present, otherwise
# fall back to the source frontend directory during local development.
FRONTEND_PATH = PROJECT_ROOT / "frontend" / "dist"
if not FRONTEND_PATH.exists():
    FRONTEND_PATH = PROJECT_ROOT / "frontend"

if FRONTEND_PATH.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_PATH), html=True), name="frontend")
