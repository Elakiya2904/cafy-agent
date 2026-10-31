"""Pipeline 2 orchestration: select job → open application → detect form →
map profile → autofill → AI answers → resume upload → human review → submit →
verify → track → hand off to Pipeline 3.

Safety invariants (see pipeline_2.md §13):
* the backend only releases "submit" permission after an explicit candidate approval;
* any edit after approval revokes it;
* sensitive/eligibility questions are never auto-answered;
* the resume file is released only after the candidate grants permission;
* "submitted" requires a detected confirmation, never just a button click.
"""
import json
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import urlparse

from . import mapper
from .verifier import verify_submission

ACTIVE = ("draft", "in_progress", "ready_for_review")
SUBMITTED = ("submitted", "confirmation_pending")
ATS_LABELS = {"greenhouse": "Greenhouse", "ashby": "Ashby", "lever": "Lever", "workday": "Workday", "workable": "Workable",
              "oracle": "Oracle Cloud", "breezy": "BreezyHR", "pinpoint": "Pinpoint", "generic": "Generic"}


class ApplicationError(Exception):
    def __init__(self, message: str, status: int = 400, data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status, self.data = status, data or {}


def _uid() -> str:
    return uuid.uuid4().hex


def _norm_url(url: str) -> str:
    p = urlparse(url or "")
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}"


def _root_host(netloc: str) -> str:
    return ".".join(netloc.lower().split(":")[0].split(".")[-2:])


class JobApplicationService:
    def __init__(self, database, profile_provider: Callable[[], Optional[Dict[str, Any]]],
                 resume_file_provider: Callable[[], Optional[Dict[str, Any]]],
                 job_lookup: Callable[[str], Optional[Dict[str, Any]]],
                 answer_generator: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[str]]] = None,
                 on_submitted: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.db = database
        self.profile_provider, self.resume_file_provider = profile_provider, resume_file_provider
        self.job_lookup, self.answer_generator, self.on_submitted, self.now = job_lookup, answer_generator, on_submitted, now

    # ------------------------------------------------------------------ db
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

    def _one(self, sql: str, args: tuple = ()) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _all(self, sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def _exec(self, sql: str, args: tuple = ()) -> None:
        with self._conn() as c:
            c.execute(sql, args)

    def _set(self, table: str, row_id: str, **f: Any) -> None:
        self._exec(f"UPDATE {table} SET {', '.join(k + ' = ?' for k in f)} WHERE id = ?", (*f.values(), row_id))

    def _ts(self) -> str:
        return self.now().isoformat()

    def _event(self, app_id: str, candidate: str, event: str, detail: Any = None) -> None:
        text = detail if detail is None or isinstance(detail, str) else json.dumps(detail, default=str)
        self._exec("INSERT INTO application_events (application_id, candidate_id, ts, event, detail) VALUES (?,?,?,?,?)",
                   (app_id, candidate, self._ts(), event, text))

    def _app(self, candidate: str, app_id: str) -> Dict[str, Any]:
        app = self._one("SELECT * FROM job_applications WHERE id=? AND candidate_id=?", (app_id, candidate))
        if not app:
            raise ApplicationError("Application not found.", 404)
        return app

    def _touch(self, app_id: str, **f: Any) -> None:
        self._set("job_applications", app_id, updated_at=self._ts(), **f)

    # --------------------------------------------------------------- start
    def _find_duplicates(self, candidate: str, job_id: Optional[str], company: str, title: str) -> List[Dict[str, Any]]:
        rows = self._all("SELECT * FROM job_applications WHERE candidate_id=? AND status != 'cancelled' ORDER BY created_at DESC", (candidate,))
        return [r for r in rows if (job_id and r["job_id"] == job_id)
                or (r["company"].strip().lower() == company.strip().lower() and r["job_title"].strip().lower() == title.strip().lower())]

    def start(self, candidate: str, job_id: Optional[str] = None, company: Optional[str] = None, job_title: Optional[str] = None,
              application_url: Optional[str] = None, allow_duplicate: bool = False) -> Dict[str, Any]:
        job = self.job_lookup(job_id) if job_id else None
        if job_id and not job:
            raise ApplicationError("Job not found.", 404)
        company, title = (job or {}).get("company") or company, (job or {}).get("title") or job_title
        url = (job or {}).get("url") or application_url
        if not (company and title):
            raise ApplicationError("A job id, or company and job title, is required.", 422)
        if not self.profile_provider():
            raise ApplicationError("Upload your résumé first so Cafy has a profile to fill applications with.", 422)
        dupes = self._find_duplicates(candidate, job_id, company, title)
        submitted = [d for d in dupes if d["status"] in SUBMITTED]
        if submitted and not allow_duplicate:
            raise ApplicationError("You have already applied to this job through Cafy.", 409,
                                   {"duplicate": True, "existing": self.public(submitted[0])})
        open_ones = [d for d in dupes if d["status"] in ACTIVE + ("submission_failed",)]
        if open_ones and not allow_duplicate:
            existing = open_ones[0]
            self._event(existing["id"], candidate, "resumed", "Existing unfinished application reopened")
            return {"application": self.public(existing), "resumed": True}
        resume = self.resume_file_provider() or {}
        app_id = f"app_{_uid()[:12]}"
        now = self._ts()
        self._exec("INSERT INTO job_applications (id,candidate_id,job_id,company,job_title,location,job_description,application_url,status,"
                   "resume_version_id,ats_platform,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (app_id, candidate, job_id, company, title, (job or {}).get("location"), (job or {}).get("description"), url, "draft",
                    f"original:{resume.get('filename')}" if resume else None,
                    ATS_LABELS.get(((job or {}).get("platform") or "").lower(), (job or {}).get("platform")), now, now))
        self._event(app_id, candidate, "created", {"job_id": job_id, "url": url})
        return {"application": self.public(self._app(candidate, app_id)), "resumed": False}

    @staticmethod
    def public(app: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in app.items() if k != "job_description"}

    def lookup_by_url(self, candidate: str, url: str) -> List[Dict[str, Any]]:
        """Find unfinished applications whose application page matches the page the extension is on."""
        cur, p = _norm_url(url), urlparse(url)
        digits = set(re.findall(r"\d{5,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{12,}", url))
        out = []
        for a in self._all("SELECT * FROM job_applications WHERE candidate_id=? AND status IN ('draft','in_progress','ready_for_review','submission_failed','confirmation_pending') "
                           "ORDER BY updated_at DESC", (candidate,)):
            if not a["application_url"]:
                continue
            ap, an = urlparse(a["application_url"]), _norm_url(a["application_url"])
            same_job = digits & set(re.findall(r"\d{5,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{12,}", a["application_url"]))
            same_page = cur == an or cur.startswith(an + "/")
            same_path = _root_host(p.netloc) == _root_host(ap.netloc) and ap.path.rstrip("/") == p.path.rstrip("/")
            if same_page or same_path or same_job:
                out.append(self.public(a))
        return out

    # ------------------------------------------------------------ profile
    def profile_for_extension(self, candidate: str, app_id: str) -> Dict[str, Any]:
        self._app(candidate, app_id)
        profile = self.profile_provider()
        if not profile:
            raise ApplicationError("No candidate profile is stored. Upload your résumé first.", 422)
        first, last = mapper.split_name(profile.get("candidate_name", ""))
        data = {"first_name": first, "last_name": last, "email": profile.get("email"), "phone": profile.get("phone"),
                "location": profile.get("location"), "address": profile.get("address"), "linkedin": profile.get("linkedin"),
                "portfolio": profile.get("portfolio"), "github": profile.get("github"), "skills": profile.get("skills") or [],
                "education": profile.get("education") or [], "experience": profile.get("experience") or [],
                "certifications": profile.get("certifications") or []}
        return {"profile": data, "missing": [k for k in ("first_name", "last_name", "email", "phone", "location") if not data.get(k)]}

    # --------------------------------------------------------------- form
    _NUM = re.compile(r"\d[\d,.]*")

    def _grounded(self, answer: str, profile: Dict[str, Any], job: Dict[str, Any], question: str) -> bool:
        """Reject answers that introduce numbers (years, metrics) absent from the sources."""
        source = json.dumps(profile, default=str) + json.dumps(job, default=str) + question
        return all(n in source for n in self._NUM.findall(answer))

    def _generate(self, question: str, profile: Dict[str, Any], app: Dict[str, Any]) -> Dict[str, Optional[str]]:
        if not self.answer_generator:
            return {"value": None, "note": "AI suggestions are not configured; write your own answer."}
        job = {"company": app["company"], "title": app["job_title"], "description": app.get("job_description") or "", "location": app.get("location")}
        try:
            answer = (self.answer_generator(question, profile, job) or "").strip()
        except Exception as err:  # generator failure must never block the form
            return {"value": None, "note": f"Could not generate a suggestion ({err}); write your own answer."}
        if not answer:
            return {"value": None, "note": "No suggestion produced; write your own answer."}
        if not self._grounded(answer, profile, job, question):
            return {"value": None, "note": "The generated answer contained unsupported claims and was discarded; write your own answer."}
        return {"value": answer, "note": "AI-suggested from your profile – review, edit or replace."}

    def detect_form(self, candidate: str, app_id: str, form: Dict[str, Any]) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        if app["status"] in SUBMITTED or app["status"] == "cancelled":
            raise ApplicationError(f"This application is {app['status']}.", 409)
        profile = self.profile_provider()
        if not profile:
            raise ApplicationError("No candidate profile is stored. Upload your résumé first.", 422)
        fields = [f for f in form.get("fields", []) if f.get("key")]
        if not fields:
            self._touch(app_id, blocked_reason="unsupported_form")
            self._event(app_id, candidate, "unsupported_form", {"url": form.get("url")})
            raise ApplicationError("No fillable application fields were found on this page.", 422, {"blocked_reason": "unsupported_form"})
        existing = {r["field_key"]: r for r in self._all("SELECT * FROM application_form_data WHERE application_id=?", (app_id,))}
        changed_set = False
        ats = ATS_LABELS.get((form.get("ats") or "").lower())
        for f in fields:
            m = mapper.map_field(f, profile)
            prev = existing.get(f["key"])
            name = (f.get("label") or f.get("name") or f["key"]).strip()[:300]
            if prev and prev["field_source"] == "candidate":
                m = {"category": m["category"], "value": prev["field_value"], "source": "candidate", "completion_status": prev["completion_status"],
                     "approval_status": prev["approval_status"], "note": prev["note"]}
            elif prev and prev["field_value"] and prev["field_source"] == "ai_suggestion":
                m = {**m, "value": prev["field_value"], "source": "ai_suggestion", "completion_status": prev["completion_status"],
                     "approval_status": prev["approval_status"], "note": prev["note"]}
            elif m["completion_status"] == "needs_generation":
                g = self._generate(name, profile, app)
                m.update(value=g["value"], note=g["note"],
                         completion_status="awaiting_review" if g["value"] else "needs_input", source="ai_suggestion" if g["value"] else "unknown")
            if m["category"].startswith("document:"):
                self._upsert_document(candidate, app_id, f["key"], m["category"].split(":", 1)[1])
            if not prev:
                changed_set = True
            row = (_uid() if not prev else prev["id"], app_id, candidate, f["key"], name, f.get("type"), m["category"], int(bool(f.get("required"))),
                   json.dumps(f.get("options") or []), m["value"], m["source"], m["completion_status"], m["approval_status"], m["note"], self._ts())
            self._exec("INSERT INTO application_form_data (id,application_id,candidate_id,field_key,field_name,field_type,category,required,options,"
                       "field_value,field_source,completion_status,approval_status,note,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                       "ON CONFLICT(application_id, field_key) DO UPDATE SET field_name=excluded.field_name, field_type=excluded.field_type, "
                       "category=excluded.category, required=excluded.required, options=excluded.options, field_value=excluded.field_value, "
                       "field_source=excluded.field_source, completion_status=excluded.completion_status, approval_status=excluded.approval_status, "
                       "note=excluded.note, updated_at=excluded.updated_at", row)
        upd: Dict[str, Any] = {"blocked_reason": None if app["blocked_reason"] == "unsupported_form" else app["blocked_reason"]}
        if form.get("url") and not app["application_url"]:
            upd["application_url"] = form["url"]
        if ats and not app["ats_platform"]:
            upd["ats_platform"] = ats
        if changed_set:
            upd["approved_at"] = None
        self._touch(app_id, **upd)
        self._event(app_id, candidate, "form_detected", {"fields": len(fields), "ats": ats})
        return self.review(candidate, app_id)

    def _upsert_document(self, candidate: str, app_id: str, field_key: str, doc_type: str) -> None:
        resume = self.resume_file_provider() if doc_type == "resume" else None
        status = "permission_required" if doc_type == "resume" and resume else "not_available"
        self._exec("INSERT INTO application_documents (id,application_id,candidate_id,field_key,document_type,resume_version,filename,upload_status,updated_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(application_id, document_type, field_key) DO UPDATE SET updated_at=excluded.updated_at",
                   (_uid(), app_id, candidate, field_key, doc_type, "original" if doc_type == "resume" else None,
                    (resume or {}).get("filename"), status, self._ts()))

    # ------------------------------------------------------------- review
    def _fields(self, app_id: str) -> List[Dict[str, Any]]:
        rows = self._all("SELECT * FROM application_form_data WHERE application_id=? ORDER BY rowid", (app_id,))
        for r in rows:
            r["options"] = json.loads(r["options"] or "[]")
            r["required"] = bool(r["required"])
        return rows

    def blockers(self, app: Dict[str, Any], fields: List[Dict[str, Any]], docs: List[Dict[str, Any]]) -> List[str]:
        out = []
        if app["blocked_reason"]:
            out.append({"captcha": "A CAPTCHA/verification is waiting for you on the application page.",
                        "session_expired": "The application session expired; reopen the page.",
                        "unsupported_form": "This form is not supported."}.get(app["blocked_reason"], app["blocked_reason"]))
        if not fields:
            out.append("The application form has not been detected yet.")
        for f in fields:
            if f["category"].startswith("document:"):
                continue
            if f["completion_status"] == "skipped":
                continue
            if not f["field_value"]:
                if f["required"]:
                    out.append(f"'{f['field_name']}' is required and still needs your input.")
                continue
            if (f["field_source"] == "ai_suggestion" or f["category"] == "sensitive") and f["approval_status"] != "approved":
                out.append(f"'{f['field_name']}' needs your review and approval.")
        for d in docs:
            if d["document_type"] == "resume":
                if d["upload_status"] == "not_available":
                    out.append("No résumé is stored to upload.")
                elif not d["permission_granted"]:
                    out.append("Give permission to upload your résumé.")
                elif d["upload_status"] != "uploaded":
                    out.append("Your résumé has not been uploaded successfully yet." if d["upload_status"] != "failed"
                               else f"Résumé upload failed: {d['detail'] or 'try again'}.")
            elif d["upload_status"] != "uploaded":
                req = next((f for f in fields if f["field_key"] == d["field_key"] and f["required"]), None)
                if req:
                    out.append(f"A required '{d['document_type'].replace('_', ' ')}' document is needed and cannot be uploaded automatically.")
        return out

    def review(self, candidate: str, app_id: str) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        fields, docs = self._fields(app_id), self.documents(app_id)
        blockers = self.blockers(app, fields, docs)
        if app["status"] in ACTIVE:
            status = "ready_for_review" if fields and not blockers else "in_progress"
            if status != app["status"]:
                self._touch(app_id, status=status)
                app["status"] = status

        def label(f):
            if f["category"].startswith("document:"):
                d = next((d for d in docs if d["field_key"] == f["field_key"]), None)
                return {"uploaded": "Uploaded", "failed": "Upload failed", "not_available": "Not available"}.get(d["upload_status"] if d else "", "Awaiting permission")
            if f["completion_status"] == "skipped":
                return "Skipped (optional)"
            if not f["field_value"]:
                return "Needs input"
            if (f["field_source"] == "ai_suggestion" or f["category"] == "sensitive") and f["approval_status"] != "approved":
                return "Awaiting review"
            return "Completed"
        return {"application": self.public(app), "fields": fields, "documents": docs, "blockers": blockers,
                "summary": [{"field_id": f["id"], "field": f["field_name"], "status": label(f)} for f in fields],
                "can_approve": not blockers and app["status"] in ACTIVE, "approved": bool(app["approved_at"])}

    def documents(self, app_id: str) -> List[Dict[str, Any]]:
        return self._all("SELECT * FROM application_documents WHERE application_id=? ORDER BY rowid", (app_id,))

    def _revoke(self, app_id: str) -> None:
        self._touch(app_id, approved_at=None)

    def _field(self, candidate: str, app_id: str, field_id: str) -> Dict[str, Any]:
        self._app(candidate, app_id)
        f = self._one("SELECT * FROM application_form_data WHERE id=? AND application_id=?", (field_id, app_id))
        if not f:
            raise ApplicationError("Field not found.", 404)
        return f

    def _editable(self, app: Dict[str, Any]) -> None:
        if app["status"] in SUBMITTED or app["status"] == "cancelled":
            raise ApplicationError(f"This application is {app['status']} and can no longer be edited.", 409)

    def edit_field(self, candidate: str, app_id: str, field_id: str, value: str) -> Dict[str, Any]:
        self._editable(self._app(candidate, app_id))
        f = self._field(candidate, app_id, field_id)
        value = (value or "").strip()
        opts = json.loads(f["options"] or "[]")
        if value and opts:
            chosen = mapper.match_option(value, [o if isinstance(o, str) else o.get("label", "") for o in opts])
            if not chosen:
                raise ApplicationError("Value must be one of the available options.", 422, {"options": opts})
            value = chosen
        self._set("application_form_data", field_id, field_value=value or None, field_source="candidate",
                  completion_status="completed" if value else ("needs_input" if f["required"] else "skipped"),
                  approval_status="approved" if value else "pending", note="Entered by you.", updated_at=self._ts())
        self._revoke(app_id)
        self._event(app_id, candidate, "field_edited", f["field_name"])
        return self.review(candidate, app_id)

    def approve_field(self, candidate: str, app_id: str, field_id: str) -> Dict[str, Any]:
        self._editable(self._app(candidate, app_id))
        f = self._field(candidate, app_id, field_id)
        if not f["field_value"]:
            raise ApplicationError("There is no answer to approve yet.", 422)
        self._set("application_form_data", field_id, approval_status="approved", completion_status="completed", updated_at=self._ts())
        self._event(app_id, candidate, "field_approved", f["field_name"])
        return self.review(candidate, app_id)

    def regenerate_field(self, candidate: str, app_id: str, field_id: str) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        self._editable(app)
        f = self._field(candidate, app_id, field_id)
        if f["category"] != "open_question":
            raise ApplicationError("Only open-ended questions can be regenerated.", 422)
        g = self._generate(f["field_name"], self.profile_provider() or {}, app)
        self._set("application_form_data", field_id, field_value=g["value"], field_source="ai_suggestion" if g["value"] else "unknown",
                  completion_status="awaiting_review" if g["value"] else "needs_input", approval_status="pending", note=g["note"], updated_at=self._ts())
        self._revoke(app_id)
        self._event(app_id, candidate, "answer_regenerated", f["field_name"])
        return self.review(candidate, app_id)

    # ---------------------------------------------------------- documents
    def set_document_permission(self, candidate: str, app_id: str, document_type: str, granted: bool) -> Dict[str, Any]:
        self._editable(self._app(candidate, app_id))
        docs = [d for d in self.documents(app_id) if d["document_type"] == document_type]
        if not docs:
            raise ApplicationError("No such document field was detected on the form.", 404)
        for d in docs:
            if d["upload_status"] == "not_available":
                continue
            self._set("application_documents", d["id"], permission_granted=int(granted),
                      upload_status="pending" if granted else "permission_required", updated_at=self._ts())
        self._revoke(app_id)
        self._event(app_id, candidate, "document_permission", {"type": document_type, "granted": granted})
        return self.review(candidate, app_id)

    def resume_file(self, candidate: str, app_id: str) -> Dict[str, Any]:
        self._app(candidate, app_id)
        doc = next((d for d in self.documents(app_id) if d["document_type"] == "resume"), None)
        if not doc or not doc["permission_granted"]:
            raise ApplicationError("Permission to upload your résumé has not been granted.", 403)
        file = self.resume_file_provider()
        if not file:
            raise ApplicationError("No résumé file is stored.", 404)
        self._event(app_id, candidate, "resume_released", file.get("filename"))
        return file

    def report_document(self, candidate: str, app_id: str, document_id: str, status: str, detail: Optional[str]) -> Dict[str, Any]:
        self._app(candidate, app_id)
        d = self._one("SELECT * FROM application_documents WHERE id=? AND application_id=?", (document_id, app_id))
        if not d:
            raise ApplicationError("Document not found.", 404)
        if status not in ("uploaded", "failed"):
            raise ApplicationError("status must be 'uploaded' or 'failed'.", 422)
        if status == "uploaded" and not d["permission_granted"]:
            raise ApplicationError("Cannot record an upload without permission.", 403)
        self._set("application_documents", document_id, upload_status=status, detail=detail, updated_at=self._ts())
        self._event(app_id, candidate, "document_upload_" + status, {"type": d["document_type"], "detail": detail})
        return self.review(candidate, app_id)

    # ----------------------------------------------------------- approval
    def approve(self, candidate: str, app_id: str) -> Dict[str, Any]:
        """The candidate's explicit "Approve and Submit". The extension may only submit after this."""
        app = self._app(candidate, app_id)
        self._editable(app)
        rev = self.review(candidate, app_id)
        if rev["blockers"]:
            raise ApplicationError("The application is not ready to approve.", 409, {"blockers": rev["blockers"]})
        # Bulk-approve profile-sourced fields the candidate just reviewed.
        self._exec("UPDATE application_form_data SET approval_status='approved' WHERE application_id=? AND field_source='profile' AND approval_status='pending'", (app_id,))
        self._touch(app_id, approved_at=self._ts(), status="ready_for_review")
        self._event(app_id, candidate, "approved_for_submission")
        return self.review(candidate, app_id)

    def submit_permission(self, candidate: str, app_id: str) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        rev = self.review(candidate, app_id)
        allowed = bool(app["approved_at"]) and not rev["blockers"] and app["status"] in ACTIVE
        return {"allowed": allowed, "status": app["status"], "blocked_reason": app["blocked_reason"],
                "reason": None if allowed else ("Waiting for your approval in Cafy." if not app["approved_at"] else (rev["blockers"] or ["Not submittable."])[0])}

    # ---------------------------------------------------------- submission
    def report_event(self, candidate: str, app_id: str, event: str, detail: Optional[str] = None) -> Dict[str, Any]:
        self._app(candidate, app_id)
        blocking = {"captcha": "captcha", "session_expired": "session_expired", "unsupported_form": "unsupported_form"}
        if event in blocking:
            self._touch(app_id, blocked_reason=blocking[event], approved_at=None)
        elif event not in ("upload_failed", "validation_error", "network_error", "mapping_uncertain"):
            raise ApplicationError("Unknown event type.", 422)
        self._event(app_id, candidate, event, detail)
        return self.review(candidate, app_id)

    def resume_after_block(self, candidate: str, app_id: str) -> Dict[str, Any]:
        self._app(candidate, app_id)
        self._touch(app_id, blocked_reason=None)
        self._event(app_id, candidate, "block_cleared")
        return self.review(candidate, app_id)

    def record_submission(self, candidate: str, app_id: str, signals: Dict[str, Any]) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        if app["status"] == "submitted":
            self._event(app_id, candidate, "duplicate_submission_blocked", "Already submitted")
            return {"duplicate": True, "application": self.public(app)}
        if app["status"] == "cancelled":
            raise ApplicationError("This application was cancelled.", 409)
        if not app["approved_at"]:
            self._event(app_id, candidate, "unapproved_submission_reported", "Submit reported without candidate approval")
            raise ApplicationError("This application was not approved for submission.", 403)
        if signals.get("captcha"):
            self._touch(app_id, blocked_reason="captcha", approved_at=None)
            self._event(app_id, candidate, "captcha", "Paused: waiting for the candidate to complete verification")
            return {"paused": True, "reason": "captcha", "application": self.public(self._app(candidate, app_id))}
        verdict = verify_submission(signals)
        now = self._ts()
        self._exec("INSERT INTO application_submissions (id,application_id,candidate_id,submitted_at,result,confirmation_reference,error_details,signals) VALUES (?,?,?,?,?,?,?,?)",
                   (_uid(), app_id, candidate, signals.get("clicked_at") or now, verdict["result"], verdict["reference"], verdict["error"],
                    json.dumps({k: v for k, v in signals.items() if k != "confirmation_text"} | {"confirmation_text": (signals.get("confirmation_text") or "")[:500]}, default=str)))
        status = {"submitted": "submitted", "submission_failed": "submission_failed", "confirmation_pending": "confirmation_pending"}[verdict["result"]]
        upd: Dict[str, Any] = {"status": status}
        if verdict["result"] == "submitted":
            upd.update(applied_at=now, external_reference_id=verdict["reference"])
        else:
            upd["approved_at"] = None  # a retry needs a fresh approval
        if verdict["result"] == "confirmation_pending":
            upd["applied_at"] = None
        self._touch(app_id, **upd)
        self._event(app_id, candidate, "submission_" + verdict["result"], {"reason": verdict["reason"], "reference": verdict["reference"], "error": verdict["error"]})
        app = self._app(candidate, app_id)
        if status == "submitted":
            self._handoff(candidate, app)
        return {"result": verdict["result"], "reference": verdict["reference"], "error": verdict["error"], "application": self.public(app)}

    def confirm_submitted(self, candidate: str, app_id: str) -> Dict[str, Any]:
        """Candidate confirms (e.g. from the site's email) that an unconfirmed attempt went through."""
        app = self._app(candidate, app_id)
        if app["status"] not in ("confirmation_pending", "submission_failed"):
            raise ApplicationError("Only unconfirmed or failed attempts can be confirmed manually.", 409)
        now = self._ts()
        self._touch(app_id, status="submitted", applied_at=now)
        self._event(app_id, candidate, "submission_confirmed_by_candidate")
        app = self._app(candidate, app_id)
        self._handoff(candidate, app)
        return {"application": self.public(app)}

    def retry(self, candidate: str, app_id: str) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        if app["status"] not in ("submission_failed", "confirmation_pending"):
            raise ApplicationError("Only failed or unconfirmed applications can be retried.", 409)
        self._touch(app_id, status="in_progress", approved_at=None)
        self._event(app_id, candidate, "retry")
        return self.review(candidate, app_id)

    def cancel(self, candidate: str, app_id: str) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        if app["status"] == "submitted":
            raise ApplicationError("A submitted application cannot be cancelled.", 409)
        self._touch(app_id, status="cancelled", approved_at=None)
        self._event(app_id, candidate, "cancelled")
        return {"application": self.public(self._app(candidate, app_id))}

    def _handoff(self, candidate: str, app: Dict[str, Any]) -> None:
        payload = self.pipeline3_payload(app)
        if not self.on_submitted:
            return
        try:
            self.on_submitted(candidate, payload)
            self._event(app["id"], candidate, "handed_to_email_agent", payload)
        except Exception as err:  # tracker is already correct; hand-off can be repeated
            self._event(app["id"], candidate, "handoff_failed", str(err))

    @staticmethod
    def pipeline3_payload(app: Dict[str, Any]) -> Dict[str, Any]:
        return {"application_id": app["id"], "user_id": app["candidate_id"], "company": app["company"], "job_title": app["job_title"],
                "application_status": app["status"], "applied_at": app["applied_at"], "source": app["ats_platform"],
                "job_id": app["job_id"], "reference_id": app["external_reference_id"]}

    # ------------------------------------------------------------ dashboard
    def list_applications(self, candidate: str, company: Optional[str] = None, date_from: Optional[str] = None,
                          date_to: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self._all("SELECT * FROM job_applications WHERE candidate_id=? ORDER BY COALESCE(applied_at, created_at) DESC", (candidate,))
        live = [r for r in rows if r["status"] != "cancelled"]
        counts: Dict[Any, int] = {}
        for r in live:
            counts[(r["company"].lower(), r["job_title"].lower())] = counts.get((r["company"].lower(), r["job_title"].lower()), 0) + 1
        out = []
        for r in rows:
            day = (r["applied_at"] or r["created_at"])[:10]
            if company and company.lower() not in r["company"].lower():
                continue
            if status and r["status"] != status:
                continue
            if (date_from and day < date_from) or (date_to and day > date_to):
                continue
            r = self.public(r)
            r["is_duplicate"] = r["status"] != "cancelled" and counts.get((r["company"].lower(), r["job_title"].lower()), 0) > 1
            out.append(r)
        return out

    def detail(self, candidate: str, app_id: str) -> Dict[str, Any]:
        app = self._app(candidate, app_id)
        return {**self.review(candidate, app_id), "submissions": self._all("SELECT id, submitted_at, result, confirmation_reference, error_details FROM application_submissions WHERE application_id=? ORDER BY submitted_at DESC", (app_id,)),
                "history": self._all("SELECT ts, event, detail FROM application_events WHERE application_id=? ORDER BY id", (app_id,)),
                "pipeline3": self.pipeline3_payload(app) if app["status"] == "submitted" else None}
