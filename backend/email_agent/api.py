"""FastAPI routes for Pipeline 3 (mounted under /api/email-agent)."""
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from ..auth import require_cron_secret
from ..context import current_candidate
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .service import AgentError, EmailAgentService


class ApplicationIn(BaseModel):
    job_id: Optional[str] = None
    company: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    applied_at: Optional[str] = None
    recruiter_email: Optional[str] = None


class ApplicationsSync(BaseModel):
    applications: List[ApplicationIn]


class MatchConfirm(BaseModel):
    application_id: Optional[str] = None  # null = not related to any application


class ReplyRequest(BaseModel):
    mode: str
    slots: Optional[List[Dict[str, str]]] = None


class InterviewConfirm(BaseModel):
    interview_date: Optional[str] = None
    interview_time: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, gt=0, le=600)
    meeting_link: Optional[str] = None
    timezone: Optional[str] = None


class DraftEdit(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    to_email: Optional[str] = None


class TimezoneIn(BaseModel):
    timezone: str


def build_router(svc: EmailAgentService, monitor=None) -> APIRouter:
    router = APIRouter(prefix="/api/email-agent", tags=["email-agent"])

    def cid() -> str:
        return current_candidate()  # verified by the auth middleware; never taken from client input

    def run(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except AgentError as err:
            raise HTTPException(status_code=err.status, detail={"message": str(err), **err.data}) from err

    def redirect_uri(request: Request, provider: str) -> str:
        # Behind a proxy the request URL is the internal one; PUBLIC_BASE_URL must match the Google console exactly.
        base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
        if base:
            return f"{base}/api/email-agent/oauth/{provider}/callback"
        return str(request.url_for("email_oauth_callback", provider=provider))

    def frontend(path: str) -> str:
        return f"{(os.getenv('FRONTEND_URL') or '').rstrip('/')}{path}"

    @router.get("/dashboard")
    def dashboard():
        return svc.dashboard(cid())

    @router.get("/oauth/{provider}/start")
    def oauth_start(provider: str, request: Request):
        return {"auth_url": run(svc.start_oauth, cid(), provider, redirect_uri(request, provider))}

    @router.get("/oauth/{provider}/callback", name="email_oauth_callback")
    def oauth_callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
        if error or not code:
            return RedirectResponse(frontend(f"/?emailAgent=error&reason={error or 'missing_code'}"))
        try:
            svc.complete_oauth(provider, code, state, redirect_uri(request, provider))
        except AgentError as err:
            return RedirectResponse(frontend(f"/?emailAgent=error&reason={str(err)[:80]}"))
        return RedirectResponse(frontend("/?emailAgent=connected"))

    @router.delete("/accounts/{account_id}")
    def disconnect(account_id: str):
        return run(svc.disconnect_account, cid(), account_id)

    @router.put("/accounts/{account_id}/timezone")
    def set_tz(account_id: str, body: TimezoneIn):
        run(svc.set_timezone, cid(), account_id, body.timezone)
        return {"ok": True}

    @router.post("/accounts/{account_id}/sync")
    def sync(account_id: str):
        return run(svc.sync_account, cid(), account_id)

    @router.post("/applications/sync")
    def sync_applications(body: ApplicationsSync):
        c = cid()
        return [svc.upsert_application(c, a.company, a.job_title, a.job_id, a.applied_at, a.recruiter_email) for a in body.applications]

    @router.get("/applications")
    def applications():
        return svc.list_applications(cid())

    @router.post("/messages/{message_id}/confirm-match")
    def confirm_match(message_id: str, body: MatchConfirm):
        return run(svc.confirm_match, cid(), message_id, body.application_id)

    @router.post("/interviews/{interview_id}/reply")
    def prepare_reply(interview_id: str, body: ReplyRequest):
        return run(svc.prepare_interview_reply, cid(), interview_id, body.mode, body.slots)

    @router.post("/interviews/{interview_id}/confirm")
    def confirm_interview(interview_id: str, body: InterviewConfirm):
        return run(svc.confirm_interview, cid(), interview_id, body.model_dump(exclude_none=True))

    @router.put("/drafts/{draft_id}")
    def edit_draft(draft_id: str, body: DraftEdit):
        return run(svc.update_draft, cid(), draft_id, body.subject, body.body, body.to_email)

    @router.post("/drafts/{draft_id}/approve")
    def approve_draft(draft_id: str, body: DraftEdit = DraftEdit()):
        return run(svc.approve_and_send, cid(), draft_id, body.subject, body.body, body.to_email)

    @router.post("/drafts/{draft_id}/reject")
    def reject_draft(draft_id: str):
        return run(svc.reject_draft, cid(), draft_id)

    @router.post("/follow-ups/scan")
    def scan():
        return run(svc.scan_follow_ups, cid())

    @router.post("/follow-ups/{record_id}/calendar")
    def follow_up_calendar(record_id: str):
        return run(svc.schedule_follow_up_calendar, cid(), record_id)

    @router.api_route("/cron/poll", methods=["GET", "POST"])
    def cron_poll(request: Request):
        """Serverless replacement for the in-process monitor: a scheduler (e.g. Vercel Cron) calls this every few minutes."""
        require_cron_secret(request)
        if monitor is None:
            raise HTTPException(status_code=503, detail="Email monitor is not available.")
        return monitor.poll_once()

    @router.get("/logs")
    def logs(limit: int = Query(100, ge=1, le=500)):
        return svc.logs(cid(), limit)

    @router.post("/notifications/read")
    def read_notifications():
        svc.mark_notifications_read(cid())
        return {"ok": True}

    return router
