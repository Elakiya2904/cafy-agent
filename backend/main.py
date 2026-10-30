import json
import os
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
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .scrapers.scraper_manager import ScraperManager
from .database import JobDatabase
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
db = JobDatabase()
scraper_mgr = ScraperManager()
scheduler = ScrapingScheduler(scraper_manager=scraper_mgr, database=db, interval_hours=6.0)
resume_svc = ResumeService()
rec_svc = RecommendationService()
sponsor_registry = VisaSponsorRegistry.from_directory(
    PROJECT_ROOT / "sponsor-data"
)
career_chat_svc = CareerChatService()
resume_generation_svc = ResumeGenerationService(PROJECT_ROOT)

# In-memory session store for uploaded résumé
ACTIVE_SESSION = {
    "resume": None,
    "last_matched_jobs": []
}

@app.on_event("startup")
def startup_event():
    # Start the background scraping worker
    scheduler.start()
    logger.info("[Main] Background scheduler initiated.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.stop()
    logger.info("[Main] Background scheduler stopped.")

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

@app.post("/api/scrape")
@app.post("/api/scrapers/run")
def trigger_scrape(background_tasks: BackgroundTasks, platform: Optional[str] = "all"):
    """Trigger an asynchronous scraping run across one or all configured ATS platforms."""
    def do_scrape():
        if platform == "all":
            scheduler.run_now()
        else:
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

    background_tasks.add_task(do_scrape)
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

UPLOADED_RESUME_DIR = PROJECT_ROOT / "backend" / "uploaded_resumes"


def _store_uploaded_resume(
    filename: str, content_type: Optional[str], content: bytes, parsed: Optional[Dict[str, Any]] = None
) -> None:
    """Keep the most recently uploaded original file so it can be previewed and downloaded later."""
    UPLOADED_RESUME_DIR.mkdir(parents=True, exist_ok=True)
    for old in UPLOADED_RESUME_DIR.glob("latest.*"):
        old.unlink()
    suffix = Path(filename or "").suffix.lower() or ".bin"
    (UPLOADED_RESUME_DIR / f"latest{suffix}").write_bytes(content)
    meta = {
        "filename": filename,
        "content_type": content_type or "application/octet-stream",
        "stored_as": f"latest{suffix}",
        "size_bytes": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        # Parsed content in the tailored-resume shape, so it can be compared with generated versions.
        "resume": _profile_as_resume(parsed or {}),
    }
    (UPLOADED_RESUME_DIR / "latest.json").write_text(json.dumps(meta), encoding="utf-8")


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


def _uploaded_resume_meta() -> Optional[Dict[str, Any]]:
    meta_path = UPLOADED_RESUME_DIR / "latest.json"
    if not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return meta if (UPLOADED_RESUME_DIR / meta["stored_as"]).is_file() else None


@app.get("/api/resume/uploaded")
def get_uploaded_resume():
    """Metadata for the original uploaded resume file, if one was uploaded."""
    meta = _uploaded_resume_meta()
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
    meta = _uploaded_resume_meta()
    if not meta:
        raise HTTPException(status_code=404, detail="No uploaded resume file is stored.")
    return FileResponse(
        UPLOADED_RESUME_DIR / meta["stored_as"],
        media_type=meta["content_type"],
        filename=meta["filename"],
        content_disposition_type="attachment" if download else "inline",
    )


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Parse candidate résumé and match against verified jobs in database."""
    try:
        content = await file.read()
        parsed = resume_svc.parse_resume(file.filename, content)
        ACTIVE_SESSION["resume"] = parsed
        _store_uploaded_resume(file.filename, file.content_type, content, parsed)

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
    except Exception as e:
        logger.error(f"[API] Resume parsing error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process résumé: {str(e)}")

@app.get("/api/resume/current")
def get_current_resume():
    if not ACTIVE_SESSION["resume"]:
        return {"resume": None, "profile_strength": None, "matched_jobs": []}
    strength = ACTIVE_SESSION["resume"].get("profile_strength") or evaluate_profile_strength(ACTIVE_SESSION["resume"])
    ACTIVE_SESSION["resume"]["profile_strength"] = strength
    if ACTIVE_SESSION["last_matched_jobs"]:
        return {
            "resume": ACTIVE_SESSION["resume"],
            "profile_strength": strength,
            "matched_jobs": enrich_jobs_with_company_profiles(ACTIVE_SESSION["last_matched_jobs"])
        }
    stored_jobs = db.get_jobs(limit=3000)
    recs = rec_svc.recommend_jobs(ACTIVE_SESSION["resume"], stored_jobs, min_score=60)
    recs = enrich_jobs_with_company_profiles(sponsor_registry.annotate_jobs(recs))
    ACTIVE_SESSION["last_matched_jobs"] = recs
    return {
        "resume": ACTIVE_SESSION["resume"],
        "profile_strength": strength,
        "matched_jobs": recs
    }


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
    try:
        result = resume_generation_svc.generate(resume or {}, job or {})
        if result.get("resume_id") and result.get("resume"):
            db.save_tailored_resume(request.job_id, result["resume_id"], result["resume"])
            db.save_resume_version(
                result["resume_id"], request.job_id, result["resume"],
                job_title=(job or {}).get("title"), company=(job or {}).get("company"),
            )
        return result
    except ResumeGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _artifact_urls(resume_id: str) -> Dict[str, Optional[str]]:
    out_dir = resume_generation_svc.output_dir
    return {
        "pdf_url": f"/api/resumes/{resume_id}/pdf" if (out_dir / f"{resume_id}.pdf").exists() else None,
        "docx_url": f"/api/resumes/{resume_id}/docx" if (out_dir / f"{resume_id}.docx").exists() else None,
        "tex_url": f"/api/resumes/{resume_id}/latex" if (out_dir / f"{resume_id}.tex").exists() else None,
    }


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
    tex_path = resume_generation_svc.output_dir / f"{resume_id}.tex"
    pdf_path = resume_generation_svc.output_dir / f"{resume_id}.pdf"
    docx_path = resume_generation_svc.output_dir / f"{resume_id}.docx"
    return {
        "status": "found",
        "tailored_resume": rec["resume"],
        "resume_id": resume_id,
        "updated_at": rec.get("updated_at"),
        "tex_url": f"/api/resumes/{resume_id}/latex" if tex_path.exists() else None,
        "pdf_url": f"/api/resumes/{resume_id}/pdf" if pdf_path.exists() else None,
        "docx_url": f"/api/resumes/{resume_id}/docx" if docx_path.exists() else None,
        "pdf_available": pdf_path.exists(),
        "docx_available": docx_path.exists(),
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
    path = resume_generation_svc.output_dir / f"{resume_id}.tex"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Resume source was not found.")
    return FileResponse(path, media_type="application/x-tex", filename=f"{resume_id}.tex")


@app.get("/api/resumes/{resume_id}/docx")
def download_resume_docx(resume_id: str):
    path = resume_generation_svc.output_dir / f"{resume_id}.docx"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="DOCX version is not available.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{resume_id}.docx"
    )


@app.get("/api/resumes/{resume_id}/pdf")
def download_resume_pdf(resume_id: str):
    path = resume_generation_svc.output_dir / f"{resume_id}.pdf"
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
