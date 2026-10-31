"""FastAPI routes for Pipeline 2 (mounted under /api/job-applications)."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from ..context import current_candidate
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .service import ApplicationError, JobApplicationService


class StartIn(BaseModel):
    job_id: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    application_url: Optional[str] = None
    allow_duplicate: bool = False


class FormIn(BaseModel):
    url: Optional[str] = None
    ats: Optional[str] = None
    fields: List[Dict[str, Any]] = Field(default_factory=list)


class ValueIn(BaseModel):
    value: str = ""


class PermissionIn(BaseModel):
    document_type: str = "resume"
    granted: bool


class DocStatusIn(BaseModel):
    status: str
    detail: Optional[str] = None


class EventIn(BaseModel):
    event: str
    detail: Optional[str] = None


def build_router(svc: JobApplicationService) -> APIRouter:
    r = APIRouter(prefix="/api/job-applications", tags=["job-applications"])

    def cid() -> str:
        return current_candidate()  # verified by the auth middleware; never taken from client input

    def run(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ApplicationError as err:
            raise HTTPException(status_code=err.status, detail={"message": str(err), **err.data}) from err

    @r.post("/start")
    def start(body: StartIn):
        return run(svc.start, cid(), body.job_id, body.company, body.job_title, body.application_url, body.allow_duplicate)

    @r.get("")
    def list_all(company: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                 status: Optional[str] = None):
        return svc.list_applications(cid(), company, date_from, date_to, status)

    @r.get("/lookup")
    def lookup(url: str = Query(...)):
        return svc.lookup_by_url(cid(), url)

    @r.get("/{app_id}")
    def detail(app_id: str):
        return run(svc.detail, cid(), app_id)

    @r.get("/{app_id}/profile")
    def profile(app_id: str):
        return run(svc.profile_for_extension, cid(), app_id)

    @r.post("/{app_id}/form")
    def form(app_id: str, body: FormIn):
        return run(svc.detect_form, cid(), app_id, body.model_dump())

    @r.get("/{app_id}/review")
    def review(app_id: str):
        return run(svc.review, cid(), app_id)

    @r.put("/{app_id}/fields/{field_id}")
    def edit(app_id: str, field_id: str, body: ValueIn):
        return run(svc.edit_field, cid(), app_id, field_id, body.value)

    @r.post("/{app_id}/fields/{field_id}/approve")
    def approve_field(app_id: str, field_id: str):
        return run(svc.approve_field, cid(), app_id, field_id)

    @r.post("/{app_id}/fields/{field_id}/regenerate")
    def regenerate(app_id: str, field_id: str):
        return run(svc.regenerate_field, cid(), app_id, field_id)

    @r.post("/{app_id}/documents/permission")
    def permission(app_id: str, body: PermissionIn):
        return run(svc.set_document_permission, cid(), app_id, body.document_type, body.granted)

    @r.get("/{app_id}/documents/resume/file")
    def resume_file(app_id: str):
        f = run(svc.resume_file, cid(), app_id)
        return FileResponse(f["path"], media_type=f["content_type"], filename=f["filename"])

    @r.post("/{app_id}/documents/{doc_id}/status")
    def doc_status(app_id: str, doc_id: str, body: DocStatusIn):
        return run(svc.report_document, cid(), app_id, doc_id, body.status, body.detail)

    @r.post("/{app_id}/approve")
    def approve(app_id: str):
        return run(svc.approve, cid(), app_id)

    @r.get("/{app_id}/submit-permission")
    def submit_permission(app_id: str):
        return run(svc.submit_permission, cid(), app_id)

    @r.post("/{app_id}/submission")
    def submission(app_id: str, signals: Dict[str, Any]):
        return run(svc.record_submission, cid(), app_id, signals)

    @r.post("/{app_id}/events")
    def events(app_id: str, body: EventIn):
        return run(svc.report_event, cid(), app_id, body.event, body.detail)

    @r.post("/{app_id}/resume")
    def resume(app_id: str):
        return run(svc.resume_after_block, cid(), app_id)

    @r.post("/{app_id}/confirm-submitted")
    def confirm(app_id: str):
        return run(svc.confirm_submitted, cid(), app_id)

    @r.post("/{app_id}/retry")
    def retry(app_id: str):
        return run(svc.retry, cid(), app_id)

    @r.post("/{app_id}/cancel")
    def cancel(app_id: str):
        return run(svc.cancel, cid(), app_id)

    return r
