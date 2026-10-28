import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .scrapers.scraper_manager import ScraperManager
from .database import JobDatabase
from .scheduler import ScrapingScheduler
from .resume_service import ResumeService
from .recommendation_service import RecommendationService
from .sponsor_service import VisaSponsorRegistry
from .career_chat_service import CareerChatError, CareerChatService, build_career_context

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
    jobs = sponsor_registry.annotate_jobs(jobs)
    return {
        "count": len(jobs),
        "jobs": jobs
    }

@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Parse candidate résumé and match against verified jobs in database."""
    try:
        content = await file.read()
        parsed = resume_svc.parse_resume(file.filename, content)
        ACTIVE_SESSION["resume"] = parsed

        # Query database across all platforms (up to 3000 jobs)
        stored_jobs = db.get_jobs(limit=3000)
        recommendations = rec_svc.recommend_jobs(parsed, stored_jobs, min_score=85)
        recommendations = sponsor_registry.annotate_jobs(recommendations)
        ACTIVE_SESSION["last_matched_jobs"] = recommendations

        return {
            "status": "success",
            "resume": parsed,
            "matched_jobs": recommendations,
            "total_matches": len(recommendations)
        }
    except Exception as e:
        logger.error(f"[API] Resume parsing error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process résumé: {str(e)}")

@app.post("/api/resume/sample")
def load_sample_resume(sample_key: str = Form("fullstack")):
    """Load a demo profile and match against database listings."""
    sample_texts = {
        "dhanush": """
Dhanush D
AI Engineer & Machine Learning Specialist
dhanush.d@example.com | London, UK
Skills: Python, FastAPI, RAG, Machine Learning, Deep Learning, PyTorch, Docker, Kubernetes, SQL, LLMs, NLP, APIs, Git.
Experience: Early career AI Engineer / Graduate candidate with projects in RAG systems, FastAPI microservices, and LLM applications.
""",
        "fullstack": """
Alex Chen
Senior Full Stack Software Engineer
alex.chen@example.com | (555) 234-5678 | San Francisco, CA
Skills: TypeScript, JavaScript, Python, React, Next.js, Node.js, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, TailwindCSS, GraphQL, CI/CD, Git.
Experience: 6+ years building microservices and web apps. Deployed Kubernetes clusters on AWS EKS with Terraform.
""",
        "ml_ai": """
Dr. Sophia Martinez
Lead Machine Learning & AI Systems Engineer
sophia.martinez@example.com | (555) 987-6543 | New York, NY
Skills: Python, PyTorch, TensorFlow, Scikit-Learn, LLMs, Generative AI, RAG, LangChain, FastAPI, Docker, Kubernetes, AWS, BigQuery, Snowflake, Apache Spark, Airflow, SQL.
Built RAG inference microservices in Python & FastAPI. Deployed on Kubernetes GPU clusters.
""",
        "devops": """
Marcus Vance
Senior DevOps & Site Reliability Engineer (SRE)
marcus.vance@example.com | (555) 456-7890 | Austin, TX
Skills: AWS, Azure, GCP, Docker, Kubernetes, Terraform, Ansible, Linux, Prometheus, Grafana, CI/CD, GitHub Actions, Python, Go, Bash, SRE, System Design.
Managed production Kubernetes clusters on AWS with Terraform and automated CI/CD pipelines.
"""
    }
    text = sample_texts.get(sample_key, sample_texts["dhanush"])
    filename_map = {
        "dhanush": "Dhanush_D_AI_Engineer_Resume.pdf",
        "fullstack": "Alex_Chen_Senior_FullStack.pdf",
        "ml_ai": "Dr_Sophia_Martinez_Lead_AI.pdf",
        "devops": "Marcus_Vance_DevOps_SRE.pdf"
    }
    filename = filename_map.get(sample_key, "Dhanush_D_AI_Engineer_Resume.pdf")

    parsed = resume_svc.analyze_text(text, filename)
    ACTIVE_SESSION["resume"] = parsed

    stored_jobs = db.get_jobs(limit=3000)
    recommendations = rec_svc.recommend_jobs(parsed, stored_jobs, min_score=85)
    recommendations = sponsor_registry.annotate_jobs(recommendations)
    ACTIVE_SESSION["last_matched_jobs"] = recommendations

    return {
        "status": "success",
        "resume": parsed,
        "matched_jobs": recommendations,
        "total_matches": len(recommendations)
    }

@app.get("/api/resume/current")
def get_current_resume():
    if not ACTIVE_SESSION["resume"]:
        return {"resume": None, "matched_jobs": []}
    # Return cached matches if available — avoids re-running TF-IDF on every poll
    if ACTIVE_SESSION["last_matched_jobs"]:
        return {
            "resume": ACTIVE_SESSION["resume"],
            "matched_jobs": ACTIVE_SESSION["last_matched_jobs"]
        }
    stored_jobs = db.get_jobs(limit=3000)
    recs = rec_svc.recommend_jobs(ACTIVE_SESSION["resume"], stored_jobs, min_score=50)
    recs = sponsor_registry.annotate_jobs(recs)
    ACTIVE_SESSION["last_matched_jobs"] = recs
    return {
        "resume": ACTIVE_SESSION["resume"],
        "matched_jobs": recs
    }

@app.post("/api/jobs/match")
@app.post("/api/recommend")
def recommend_filtered(platform: str = "all", min_score: int = 85):
    if not ACTIVE_SESSION["resume"]:
        raise HTTPException(status_code=400, detail="No résumé uploaded yet.")
    stored_jobs = db.get_jobs(platform=platform, limit=3000)
    recs = rec_svc.recommend_jobs(ACTIVE_SESSION["resume"], stored_jobs, min_score=min_score, platform_filter=platform)
    recs = sponsor_registry.annotate_jobs(recs)
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
    jobs = sponsor_registry.annotate_jobs(db.get_jobs(limit=1500))

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
                min_score=50,
            )
            matched_jobs = sponsor_registry.annotate_jobs(matched_jobs)
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

# Mount static frontend
FRONTEND_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_PATH):
    app.mount("/", StaticFiles(directory=FRONTEND_PATH, html=True), name="frontend")
