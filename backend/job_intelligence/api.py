"""FastAPI routes for Pipeline 4 (mounted under /api/job-intelligence)."""
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from ..context import current_candidate
from pydantic import BaseModel, Field

from .service import JobIntelligenceService


class ReportIn(BaseModel):
    section: str = Field(min_length=1, max_length=60)
    message: str = Field(min_length=3, max_length=1000)
    stage_key: Optional[str] = None


def build_router(svc: JobIntelligenceService, job_loader: Callable[[str], Optional[Dict[str, Any]]],
                 profile_provider: Callable[[], Optional[Dict[str, Any]]]) -> APIRouter:
    r = APIRouter(prefix="/api/job-intelligence", tags=["job-intelligence"])

    def cid() -> str:
        return current_candidate()  # verified by the auth middleware; never taken from client input

    @r.get("/{job_id}/company")
    def company(job_id: str, refresh: bool = False):
        """Company facts only (no hiring-process research), so the job panel can show them quickly."""
        job = job_loader(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if not job.get("company"):
            raise HTTPException(status_code=422, detail="The job has no company name, so the employer cannot be researched.")
        return svc.company_intelligence(job["company"], job, refresh)

    @r.get("/{job_id}")
    def intelligence(job_id: str, refresh: bool = False):
        job = job_loader(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        result = svc.get(cid(), job, profile_provider(), refresh)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result

    @r.post("/{job_id}/report")
    def report(job_id: str, body: ReportIn):
        if not job_loader(job_id):
            raise HTTPException(status_code=404, detail="Job not found.")
        svc.report_issue(cid(), job_id, body.section, body.message, body.stage_key)
        return {"ok": True}

    return r
