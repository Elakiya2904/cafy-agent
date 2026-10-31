"""Pipeline 3 orchestration: monitor → classify → match → status → interview →
calendar → human approval → send → schedule → remind → track.

Safety invariants (see pipeline-3.md §13):
* nothing is sent without an explicit candidate approval;
* the agent never accepts/declines/reschedules on its own – it only drafts;
* a send or calendar failure is never recorded as success;
* uncertain classification or matching leaves application status untouched.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import classifier as clf
from .crypto import CryptoConfigError, decrypt, encrypt
from .providers import BaseProvider, ProviderAuthError, ProviderError, build_providers

DEFAULT_TZ = "Europe/London"
OAUTH_STATE_TTL = 600
_TZ_ABBR = {"UTC": "UTC", "GMT": "Europe/London", "BST": "Europe/London", "CET": "Europe/Paris",
            "CEST": "Europe/Paris", "EST": "America/New_York", "EDT": "America/New_York",
            "CST": "America/Chicago", "CDT": "America/Chicago", "PST": "America/Los_Angeles",
            "PDT": "America/Los_Angeles"}  # "IST" is ambiguous (India/Ireland) and deliberately omitted


class AgentError(Exception):
    def __init__(self, message: str, status: int = 400, data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status, self.data = status, data or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _zone(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _uid() -> str:
    return uuid.uuid4().hex


def _dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class EmailAgentService:
    def __init__(self, database, providers: Optional[Dict[str, BaseProvider]] = None,
                 secret: Optional[str] = None, now: Callable[[], datetime] = _now):
        self.db = database
        self.providers = providers if providers is not None else build_providers()
        configured = secret or os.getenv("EMAIL_AGENT_SECRET")
        if not configured and (os.getenv("APP_ENV") or "").lower() in ("production", "prod"):
            raise RuntimeError("EMAIL_AGENT_SECRET must be set in production (OAuth state would not survive restarts or multiple workers).")
        self._secret = (configured or secrets.token_hex(32)).encode()
        self.now = now

    # ------------------------------------------------------------------ db
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
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

    def _update(self, table: str, row_id: str, **fields: Any) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE {table} SET {cols} WHERE id = ?", (*fields.values(), row_id))

    def log(self, candidate: str, action: str, entity: Optional[str], status: str, detail: Any = None) -> None:
        text = detail if isinstance(detail, str) or detail is None else json.dumps(detail, default=str)
        self._exec("INSERT INTO agent_logs (candidate_id, ts, action, entity, status, detail) VALUES (?,?,?,?,?,?)",
                   (candidate, self.now().isoformat(), action, entity, status, text))

    def notify(self, candidate: str, kind: str, message: str, application_id: Optional[str] = None) -> None:
        self._exec("INSERT INTO agent_notifications (candidate_id, kind, message, application_id, created_at) VALUES (?,?,?,?,?)",
                   (candidate, kind, message, application_id, self.now().isoformat()))

    # -------------------------------------------------------- applications
    def upsert_application(self, candidate: str, company: str, job_title: str, job_id: Optional[str] = None,
                           applied_at: Optional[str] = None, recruiter_email: Optional[str] = None,
                           application_ref: Optional[str] = None) -> Dict[str, Any]:
        existing = self._one("SELECT * FROM applications WHERE candidate_id=? AND job_id=?", (candidate, job_id)) if job_id else None
        existing = existing or self._one("SELECT * FROM applications WHERE candidate_id=? AND lower(company)=lower(?) AND lower(job_title)=lower(?)",
                                         (candidate, company, job_title))
        now = self.now().isoformat()
        if existing:
            self._update("applications", existing["id"], company=company, job_title=job_title, updated_at=now,
                         recruiter_email=recruiter_email or existing["recruiter_email"],
                         application_ref=application_ref or existing["application_ref"])
            return self._one("SELECT * FROM applications WHERE id=?", (existing["id"],))
        app_id = _uid()
        self._exec("INSERT INTO applications (id,candidate_id,job_id,company,job_title,status,applied_at,recruiter_email,application_ref,updated_at)"
                   " VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (app_id, candidate, job_id, company, job_title, "applied", applied_at or now, recruiter_email, application_ref, now))
        self.log(candidate, "application_recorded", app_id, "ok", f"{company} – {job_title}")
        return self._one("SELECT * FROM applications WHERE id=?", (app_id,))

    def list_applications(self, candidate: str) -> List[Dict[str, Any]]:
        return self._all("SELECT * FROM applications WHERE candidate_id=? ORDER BY applied_at DESC", (candidate,))

    def _application(self, candidate: str, app_id: Optional[str]) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM applications WHERE id=? AND candidate_id=?", (app_id, candidate)) if app_id else None

    # ------------------------------------------------------------- accounts
    @staticmethod
    def _seal(value: Optional[str]) -> Optional[str]:
        try:
            return encrypt(value)
        except CryptoConfigError as err:
            raise AgentError(str(err), 500) from err

    @staticmethod
    def _unseal(value: Optional[str]) -> Optional[str]:
        try:
            return decrypt(value)
        except CryptoConfigError as err:
            raise AgentError(str(err), 409) from err

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def start_oauth(self, candidate: str, provider: str, redirect_uri: str) -> str:
        prov = self._provider(provider)
        payload = base64.urlsafe_b64encode(json.dumps(
            {"c": candidate, "p": provider, "x": int(self.now().timestamp()) + OAUTH_STATE_TTL, "n": secrets.token_hex(8)}).encode()).decode()
        try:
            return prov.authorization_url(redirect_uri, f"{payload}.{self._sign(payload)}")
        except ProviderError as err:
            raise AgentError(str(err), 503) from err

    def complete_oauth(self, provider: str, code: str, state: str, redirect_uri: str) -> Dict[str, Any]:
        payload, _, sig = (state or "").partition(".")
        if not payload or not hmac.compare_digest(sig, self._sign(payload)):
            raise AgentError("Invalid OAuth state.", 400)
        try:
            data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        except ValueError as err:
            raise AgentError("Invalid OAuth state.", 400) from err
        if data["p"] != provider or data["x"] < self.now().timestamp():
            raise AgentError("OAuth state expired or for a different provider.", 400)
        candidate = data["c"]
        try:
            tokens = self._provider(provider).exchange_code(code, redirect_uri)
        except ProviderError as err:
            self.log(candidate, "oauth_connect", provider, "error", str(err))
            raise AgentError(f"Could not connect {provider}: {err}", 502) from err
        if not tokens.get("email"):
            raise AgentError("Provider did not return an email address.", 502)
        missing = self._provider(provider).missing_scopes(tokens.get("scopes"))
        if missing:
            short = ", ".join(m.rsplit("/", 1)[-1] for m in missing)
            self.log(candidate, "oauth_connect", provider, "error", f"missing scopes: {short}")
            raise AgentError(f"Permissions not granted: {short}. Reconnect and tick every box on the Google consent screen.", 403)
        now = self.now().isoformat()
        existing = self._one("SELECT id, refresh_token FROM connected_email_accounts WHERE candidate_id=? AND provider=? AND email=?",
                             (candidate, provider, tokens["email"]))
        fields = dict(display_name=tokens.get("display_name"), access_token=self._seal(tokens["access_token"]),
                      refresh_token=self._seal(tokens.get("refresh_token")) or (existing or {}).get("refresh_token"),
                      token_expires_at=tokens["token_expires_at"], scopes=tokens.get("scopes"),
                      status="connected", last_error=None, disconnected_at=None)
        if existing:
            self._update("connected_email_accounts", existing["id"], **fields)
            acc_id = existing["id"]
        else:
            acc_id = _uid()
            self._exec("INSERT INTO connected_email_accounts (id,candidate_id,provider,email,display_name,access_token,refresh_token,"
                       "token_expires_at,scopes,timezone,status,connected_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (acc_id, candidate, provider, tokens["email"], fields["display_name"], fields["access_token"],
                        fields["refresh_token"], fields["token_expires_at"], fields["scopes"], DEFAULT_TZ, "connected", now))
        self.log(candidate, "oauth_connect", acc_id, "ok", f"{provider}:{tokens['email']}")
        return self.public_account(self._one("SELECT * FROM connected_email_accounts WHERE id=?", (acc_id,)))

    @staticmethod
    def public_account(acc: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in acc.items() if k not in ("access_token", "refresh_token")}

    def connected_accounts(self) -> List[Dict[str, Any]]:
        """All accounts in 'connected' state across candidates (for the background monitor)."""
        return self._all("SELECT id, candidate_id, provider FROM connected_email_accounts WHERE status='connected'")

    def list_accounts(self, candidate: str) -> List[Dict[str, Any]]:
        return [self.public_account(a) for a in self._all(
            "SELECT * FROM connected_email_accounts WHERE candidate_id=? ORDER BY connected_at DESC", (candidate,))]

    def _provider(self, name: str) -> BaseProvider:
        if name not in self.providers:
            raise AgentError(f"Unsupported provider '{name}'. Use gmail or outlook.", 404)
        return self.providers[name]

    def _account(self, candidate: str, account_id: str) -> Dict[str, Any]:
        acc = self._one("SELECT * FROM connected_email_accounts WHERE id=? AND candidate_id=?", (account_id, candidate))
        if not acc:
            raise AgentError("Email account not found.", 404)
        return acc

    def set_timezone(self, candidate: str, account_id: str, tz: str) -> None:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as err:
            raise AgentError(f"Unknown time zone '{tz}'.", 422) from err
        self._account(candidate, account_id)
        self._update("connected_email_accounts", account_id, timezone=tz)

    def disconnect_account(self, candidate: str, account_id: str) -> Dict[str, Any]:
        acc = self._account(candidate, account_id)
        revoked = True
        try:
            token = self._unseal(acc.get("refresh_token")) or self._unseal(acc.get("access_token"))
            if token and acc["status"] != "disconnected":
                self._provider(acc["provider"]).revoke(token)
        except ProviderError as err:
            revoked = False
            self.log(candidate, "account_revoke", account_id, "error", str(err))
        self._update("connected_email_accounts", account_id, status="disconnected", access_token=None, refresh_token=None,
                     token_expires_at=None, disconnected_at=self.now().isoformat())
        self.log(candidate, "account_disconnect", account_id, "ok", {"remote_revoked": revoked})
        return {"disconnected": True, "remote_revoked": revoked}

    def _token(self, candidate: str, acc: Dict[str, Any]) -> str:
        if acc["status"] == "disconnected":
            raise AgentError("This email account is disconnected. Reconnect it to continue.", 409)
        expires = acc.get("token_expires_at")
        if acc.get("access_token") and expires and _dt(expires) - self.now() > timedelta(seconds=60):
            return self._unseal(acc["access_token"])
        try:
            tokens = self._provider(acc["provider"]).refresh(self._unseal(acc.get("refresh_token")) or "")
        except ProviderAuthError as err:
            self._update("connected_email_accounts", acc["id"], status="expired", last_error=str(err))
            self.log(candidate, "token_refresh", acc["id"], "error", str(err))
            raise AgentError("Email authorization expired. Please reconnect your account.", 401) from err
        except ProviderError as err:
            self.log(candidate, "token_refresh", acc["id"], "error", str(err))
            raise AgentError(f"Could not refresh email authorization: {err}", 502) from err
        sealed = self._seal(tokens["access_token"])
        self._update("connected_email_accounts", acc["id"], access_token=sealed,
                     refresh_token=self._seal(tokens["refresh_token"]), token_expires_at=tokens["token_expires_at"],
                     status="connected", last_error=None)
        acc.update(access_token=sealed)
        return tokens["access_token"]

    # ------------------------------------------------------------- monitor
    def sync_account(self, candidate: str, account_id: str, lookback_days: int = 14) -> Dict[str, Any]:
        acc = self._account(candidate, account_id)
        token = self._token(candidate, acc)
        since = _dt(acc["last_synced_at"]) - timedelta(minutes=5) if acc.get("last_synced_at") else self.now() - timedelta(days=lookback_days)
        started = self.now()
        try:
            raw = self._provider(acc["provider"]).list_messages(token, since)
        except ProviderAuthError as err:
            self._update("connected_email_accounts", account_id, status="expired", last_error=str(err))
            self.log(candidate, "sync", account_id, "error", str(err))
            raise AgentError("Email authorization expired. Please reconnect your account.", 401) from err
        except ProviderError as err:
            self._update("connected_email_accounts", account_id, last_error=str(err))
            self.log(candidate, "sync", account_id, "error", str(err))
            raise AgentError(f"Email sync failed: {err}", 502) from err
        stats = {"fetched": len(raw), "job_related": 0, "duplicates": 0, "needs_confirmation": 0, "ignored": 0}
        for msg in raw:
            res = self.ingest_message(candidate, acc, msg)
            if res.get("duplicate"):
                stats["duplicates"] += 1
            elif res.get("job_related"):
                stats["job_related"] += 1
                stats["needs_confirmation"] += int(res["processing_status"] == "needs_confirmation")
            else:
                stats["ignored"] += 1
        self._update("connected_email_accounts", account_id, last_synced_at=started.isoformat(), last_error=None)
        self.log(candidate, "sync", account_id, "ok", stats)
        return stats

    def ingest_message(self, candidate: str, acc: Dict[str, Any], raw: Dict[str, Any]) -> Dict[str, Any]:
        """Run one email through detection → matching → classification → effects."""
        sender, subject = raw.get("sender", ""), raw.get("subject", "")
        body, received = raw.get("body", "") or "", raw.get("received_at") or self.now().isoformat()
        _, sender_addr = clf.parse_sender(sender)
        digest = hashlib.sha256(f"{sender_addr}|{subject}|{received}|{body[:200]}".encode()).hexdigest()
        if self._one("SELECT id FROM email_messages WHERE candidate_id=? AND (dedupe_hash=? OR (account_id=? AND message_id=?))",
                     (candidate, digest, acc["id"], raw["message_id"])):
            return {"duplicate": True}

        apps = self.list_applications(candidate)
        outbound = bool(sender_addr) and sender_addr == (acc.get("email") or "").lower()
        job_related, rel_conf = clf.is_job_related(sender, subject, body, apps)
        if raw.get("list_unsubscribe") or "CATEGORY_PROMOTIONS" in raw.get("labels", []):
            job_related = False
        row_id = _uid()
        base = dict(id=row_id, candidate_id=candidate, account_id=acc["id"], message_id=raw["message_id"],
                    thread_id=raw.get("thread_id"), sender=sender, sender_email=sender_addr, subject=subject,
                    received_at=received, dedupe_hash=digest, created_at=self.now().isoformat())
        if outbound or not job_related:
            # Personal/promotional mail is recorded for dedupe only; its body is not retained.
            thread_app = self._thread_application(candidate, raw.get("thread_id")) if outbound else None
            self._insert_message({**base, "body": body if (outbound and thread_app) else None,
                                  "direction": "sent" if outbound else "received",
                                  "match_status": "matched" if thread_app else "not_job",
                                  "application_id": thread_app, "processing_status": "ignored"})
            return {"job_related": False, "message_row_id": row_id, "processing_status": "ignored"}

        thread_app = self._thread_application(candidate, raw.get("thread_id"))
        match = clf.match_application(sender, subject, body, thread_app, apps)
        category, conf = clf.classify(subject, body)
        details = clf.extract_details(subject, body, category, sender, received) if category else {}
        app_id = match["application_id"] if match["status"] == "matched" else None
        if match["status"] == "matched" and category and conf >= clf.CONFIDENCE_AUTO:
            processing = "processed"
        else:
            processing = "needs_confirmation" if match["status"] != "matched" else "needs_review"
        self._insert_message({**base, "body": body, "direction": "received", "category": category,
                              "application_id": app_id, "match_status": match["status"], "processing_status": processing})
        if app_id:
            self._stop_follow_ups(candidate, app_id, category)
        if category:
            self._exec("INSERT INTO email_classifications (id,candidate_id,message_row_id,category,extracted,confidence,application_id,processed_at)"
                       " VALUES (?,?,?,?,?,?,?,?)",
                       (_uid(), candidate, row_id, category, json.dumps({**details, "match": match}), conf, app_id, self.now().isoformat()))
        self.log(candidate, "classify_email", row_id, "ok",
                 {"category": category, "confidence": conf, "match": match["status"], "relevance": rel_conf})
        if processing == "needs_confirmation":
            who = details.get("recruiter_email") or sender_addr
            self.notify(candidate, "confirm_match", f"An email from {who} ('{subject[:60]}') may relate to one of your applications. Please confirm which.", None)
        elif processing == "needs_review":
            self.notify(candidate, "review_email", f"'{subject[:60]}' could not be classified confidently; no status was changed.", app_id)
        elif app_id:
            self._apply_effects(candidate, acc, row_id, app_id, category, details, conf)
        return {"job_related": True, "message_row_id": row_id, "category": category, "confidence": conf,
                "match": match, "processing_status": processing}

    def _insert_message(self, row: Dict[str, Any]) -> None:
        row.setdefault("category", None)
        row.setdefault("application_id", None)
        cols = ",".join(row)
        self._exec(f"INSERT INTO email_messages ({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))

    def _thread_application(self, candidate: str, thread_id: Optional[str]) -> Optional[str]:
        if not thread_id:
            return None
        r = self._one("SELECT application_id FROM email_messages WHERE candidate_id=? AND thread_id=? AND application_id IS NOT NULL "
                      "ORDER BY received_at DESC LIMIT 1", (candidate, thread_id))
        return r["application_id"] if r else None

    def confirm_match(self, candidate: str, message_row_id: str, application_id: Optional[str]) -> Dict[str, Any]:
        """Candidate resolves an uncertain association (or dismisses the email with ``None``)."""
        msg = self._one("SELECT * FROM email_messages WHERE id=? AND candidate_id=?", (message_row_id, candidate))
        if not msg:
            raise AgentError("Email not found.", 404)
        if msg["application_id"] and msg["processing_status"] == "processed":
            raise AgentError("This email is already linked to an application.", 409)
        if application_id is None:
            self._update("email_messages", message_row_id, match_status="not_job", processing_status="ignored", body=None)
            self.log(candidate, "match_dismissed", message_row_id, "ok")
            return {"processing_status": "ignored"}
        app = self._application(candidate, application_id)
        if not app:
            raise AgentError("Application not found.", 404)
        cls = self._one("SELECT * FROM email_classifications WHERE message_row_id=?", (message_row_id,))
        self._update("email_messages", message_row_id, application_id=application_id, match_status="matched",
                     processing_status="processed" if cls and cls["confidence"] >= clf.CONFIDENCE_AUTO else "needs_review")
        self.log(candidate, "match_confirmed", message_row_id, "ok", application_id)
        self._stop_follow_ups(candidate, application_id, cls["category"] if cls else None)
        if cls and cls["confidence"] >= clf.CONFIDENCE_AUTO:
            self._exec("UPDATE email_classifications SET application_id=? WHERE id=?", (application_id, cls["id"]))
            acc = self._account(candidate, msg["account_id"])
            self._apply_effects(candidate, acc, message_row_id, application_id, cls["category"], json.loads(cls["extracted"]), cls["confidence"])
            return {"processing_status": "processed", "category": cls["category"]}
        return {"processing_status": "needs_review"}

    # -------------------------------------------------------------- effects
    def _apply_effects(self, candidate, acc, row_id, app_id, category, details, conf) -> None:
        app = self._application(candidate, app_id)
        msg = self._one("SELECT * FROM email_messages WHERE id=?", (row_id,))
        new_email = details.get("recruiter_email")
        if new_email and category not in ("application_received",) and new_email != (app.get("recruiter_email") or ""):
            if app.get("recruiter_email"):
                self.log(candidate, "recruiter_email_changed", app_id, "ok", {"from": app["recruiter_email"], "to": new_email})
            self._update("applications", app_id, recruiter_email=new_email)
        if details.get("application_reference") and not app.get("application_ref"):
            self._update("applications", app_id, application_ref=details["application_reference"])
        self._apply_status(candidate, app, category, conf, row_id)
        if category in ("interview_invitation", "interview_rescheduling"):
            self._handle_interview(candidate, acc, msg, app, category, details)
        elif category == "assessment_invitation":
            self.notify(candidate, "assessment", f"{app['company']} sent an assessment invitation"
                        + (f" (deadline: {details['assessment_deadline']})" if details.get("assessment_deadline") else " (no deadline stated)") + ".", app_id)
        elif category == "additional_information":
            docs = ", ".join(details.get("required_documents") or []) or "details not clearly listed – check the email"
            self.notify(candidate, "info_requested", f"{app['company']} requested additional information: {docs}.", app_id)
        elif category == "offer_letter":
            self.notify(candidate, "offer", f"You received an offer from {app['company']} for {app['job_title']}. Open the email to review the details.", app_id)

    def _stop_follow_ups(self, candidate: str, app_id: str, category: Optional[str]) -> None:
        """A recruiter reply means no more follow-up nudges for this application."""
        if not category or category in ("application_received", "application_under_review"):
            return
        for d in self._all("SELECT id FROM email_drafts WHERE candidate_id=? AND application_id=? AND kind='follow_up' AND approval_status='pending'",
                           (candidate, app_id)):
            self._update("email_drafts", d["id"], approval_status="superseded")
            self._exec("UPDATE follow_up_records SET approval_status='superseded' WHERE draft_id=?", (d["id"],))
            self._clear_follow_up_event(candidate, d["id"])
            self.log(candidate, "follow_up_stopped", d["id"], "ok", "recruiter responded")

    def _apply_status(self, candidate, app, category, conf, row_id) -> None:
        target = clf.CATEGORY_STATUS.get(category)
        if not target or conf < clf.CONFIDENCE_AUTO:
            return
        current = app["status"]
        # Acknowledgement emails must never move an application backwards.
        if current != target and clf.STATUS_RANK.get(target, 0) < clf.STATUS_RANK.get(current, 0) and target not in ("rejected", "offer_received"):
            return
        if current in ("rejected", "offer_received") and target not in ("rejected", "offer_received"):
            return
        if current == target:
            return
        self._update("applications", app["id"], status=target, updated_at=self.now().isoformat())
        self.log(candidate, "status_update", app["id"], "ok", {"from": current, "to": target, "email": row_id, "confidence": conf})
        if target not in ("applied",):
            self.notify(candidate, "status_change", f"{app['company']} – {app['job_title']}: status changed to {target.replace('_', ' ')}.", app["id"])

    # ------------------------------------------------------------ interviews
    def _interview_window(self, iv: Dict[str, Any], default_tz: str) -> Optional[Dict[str, datetime]]:
        if not (iv.get("interview_date") and iv.get("interview_time")):
            return None
        zone = _zone(iv.get("timezone") or default_tz)
        start = datetime.combine(datetime.fromisoformat(iv["interview_date"]).date(),
                                 dtime.fromisoformat(iv["interview_time"]), tzinfo=zone)
        return {"start": start, "end": start + timedelta(minutes=iv.get("duration_minutes") or 60)}

    def _calendar_busy(self, candidate: str, acc: Dict[str, Any], start: datetime, end: datetime) -> Optional[List[Dict[str, datetime]]]:
        """Busy intervals, or ``None`` when the calendar could not be read (never assume free)."""
        try:
            token = self._token(candidate, acc)
            return self._provider(acc["provider"]).busy_intervals(token, start, end, acc["email"])
        except (AgentError, ProviderError) as err:
            self.log(candidate, "calendar_check", acc["id"], "error", str(err))
            return None

    @staticmethod
    def _overlaps(window: Dict[str, datetime], busy: List[Dict[str, datetime]]) -> List[Dict[str, str]]:
        return [{"start": b["start"].isoformat(), "end": b["end"].isoformat()} for b in busy
                if b["start"] < window["end"] and b["end"] > window["start"]]

    def generate_slots(self, candidate: str, acc: Dict[str, Any], duration: int, days: int = 7, limit: int = 6) -> Optional[List[Dict[str, str]]]:
        """Free working-hour slots (09:00–17:00 weekdays, candidate's time zone)."""
        zone = _zone(acc.get("timezone"))
        today = self.now().astimezone(zone).date()
        day_list = []
        d = today + timedelta(days=1)
        while len(day_list) < days:
            if d.weekday() < 5:
                day_list.append(d)
            d += timedelta(days=1)
        lo = datetime.combine(day_list[0], dtime(9), tzinfo=zone)
        hi = datetime.combine(day_list[-1], dtime(17), tzinfo=zone)
        busy = self._calendar_busy(candidate, acc, lo, hi)
        if busy is None:
            return None
        slots: List[Dict[str, str]] = []
        for day in day_list:
            picked = 0
            for anchor in (dtime(9), dtime(13)):
                cursor = datetime.combine(day, anchor, tzinfo=zone)
                end_of_block = datetime.combine(day, dtime(12) if anchor.hour == 9 else dtime(17), tzinfo=zone)
                while cursor + timedelta(minutes=duration) <= end_of_block:
                    window = {"start": cursor, "end": cursor + timedelta(minutes=duration)}
                    if not self._overlaps(window, busy):
                        slots.append({"start": window["start"].isoformat(), "end": window["end"].isoformat(),
                                      "label": window["start"].strftime("%A %d %B, %H:%M") + f" ({zone.key})"})
                        picked += 1
                        break
                    cursor += timedelta(minutes=30)
            if len(slots) >= limit:
                break
        return slots[:limit]

    def _handle_interview(self, candidate, acc, msg, app, category, d) -> None:
        tz_name, assumed = acc.get("timezone") or DEFAULT_TZ, True
        if d.get("timezone"):
            mapped = _TZ_ABBR.get(d["timezone"].split()[0].upper())
            if mapped:
                tz_name, assumed = mapped, False
        existing = self._one("SELECT * FROM interviews WHERE candidate_id=? AND application_id=? AND scheduling_status != 'cancelled' "
                             "ORDER BY created_at DESC LIMIT 1", (candidate, app["id"]))
        fields = dict(company=app["company"], job_title=d.get("job_title") or app["job_title"],
                      interview_date=d.get("interview_date"), interview_time=d.get("interview_time"),
                      timezone=tz_name, timezone_assumed=int(assumed), duration_minutes=d.get("duration_minutes"),
                      interview_type=d.get("interview_type"), platform=d.get("platform"), meeting_link=d.get("meeting_link"),
                      recruiter_name=d.get("recruiter_name"), recruiter_email=d.get("recruiter_email"),
                      requests_availability=int(bool(d.get("requests_availability"))))
        fields["missing_fields"] = json.dumps(clf.missing_interview_fields(d))
        now = self.now().isoformat()
        if existing:
            prev_scheduled = existing["scheduling_status"] == "scheduled"
            has_new_slot = bool(d.get("interview_date") and d.get("interview_time"))
            changed = has_new_slot and (existing["interview_date"], existing["interview_time"]) != (d["interview_date"], d["interview_time"])
            # Keep what we already know when the follow-up email omits a field.
            for k in ("interview_date", "interview_time", "timezone", "duration_minutes", "interview_type", "platform",
                      "meeting_link", "recruiter_name", "recruiter_email"):
                if not fields.get(k) and existing.get(k):
                    fields[k] = existing[k]
            if not d.get("interview_date") and existing["interview_date"]:
                fields["timezone_assumed"] = existing["timezone_assumed"]
            if category == "interview_rescheduling" or (prev_scheduled and changed):
                status = "rescheduled_by_recruiter"
            elif has_new_slot:
                status = "confirmation_received"
            else:
                status = existing["scheduling_status"]
            iv_id = existing["id"]
            self._update("interviews", iv_id, **fields, scheduling_status=status, message_row_id=msg["id"], updated_at=now)
            self.log(candidate, "interview_updated", iv_id, "ok", {"status": status, "was_scheduled": prev_scheduled})
            note = {"rescheduled_by_recruiter": "proposed a change to your interview", "confirmation_received": "confirmed interview details"}.get(status)
            if note:
                extra = " Your existing calendar event was not changed – review and confirm the new time." if prev_scheduled else ""
                self.notify(candidate, "interview", f"{app['company']} {note}. Review and confirm.{extra}", app["id"])
        else:
            iv_id = _uid()
            status = "awaiting_slot_approval" if fields["requests_availability"] and not fields["interview_date"] else "invitation_received"
            cols = {"id": iv_id, "candidate_id": candidate, "application_id": app["id"], "message_row_id": msg["id"],
                    "thread_id": msg["thread_id"], **fields, "scheduling_status": status, "created_at": now, "updated_at": now}
            self._exec(f"INSERT INTO interviews ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(cols.values()))
            self.log(candidate, "interview_extracted", iv_id, "ok", {"missing": json.loads(fields["missing_fields"])})
            self.notify(candidate, "interview", f"{app['company']} invited you to interview for {app['job_title']}.", app["id"])
        self._refresh_calendar_state(candidate, acc, iv_id)

    def _refresh_calendar_state(self, candidate: str, acc: Dict[str, Any], interview_id: str) -> None:
        iv = self._one("SELECT * FROM interviews WHERE id=?", (interview_id,))
        window = self._interview_window(iv, acc.get("timezone"))
        conflicts: List[Dict[str, str]] = []
        err = None
        if window:
            busy = self._calendar_busy(candidate, acc, window["start"], window["end"])
            if busy is None:
                err = "Calendar could not be checked; availability unknown."
            else:
                conflicts = self._overlaps(window, busy)
        slots: Optional[List[Dict[str, str]]] = json.loads(iv["proposed_slots"])
        if iv["requests_availability"] or conflicts:
            slots = self.generate_slots(candidate, acc, iv["duration_minutes"] or 45)
            if slots is None:
                err, slots = "Calendar could not be checked; availability unknown.", []
        status = iv["scheduling_status"]
        if conflicts and status not in ("scheduled", "rescheduled_by_recruiter"):
            status = "conflict"
            self.notify(candidate, "interview_conflict", f"The {iv['company']} interview clashes with an event in your calendar.", iv["application_id"])
        self._update("interviews", interview_id, conflicts=json.dumps(conflicts), proposed_slots=json.dumps(slots or []),
                     calendar_error=err, scheduling_status=status, updated_at=self.now().isoformat())

    def list_interviews(self, candidate: str) -> List[Dict[str, Any]]:
        rows = self._all("SELECT * FROM interviews WHERE candidate_id=? ORDER BY interview_date IS NULL, interview_date, interview_time", (candidate,))
        for r in rows:
            for k in ("missing_fields", "proposed_slots", "conflicts"):
                r[k] = json.loads(r[k] or "[]")
        return rows

    def _interview(self, candidate: str, interview_id: str) -> Dict[str, Any]:
        iv = self._one("SELECT * FROM interviews WHERE id=? AND candidate_id=?", (interview_id, candidate))
        if not iv:
            raise AgentError("Interview not found.", 404)
        return iv

    def _account_for_interview(self, candidate: str, iv: Dict[str, Any]) -> Dict[str, Any]:
        row = self._one("SELECT account_id FROM email_messages WHERE id=?", (iv["message_row_id"],)) if iv.get("message_row_id") else None
        if row:
            return self._account(candidate, row["account_id"])
        accs = self._all("SELECT * FROM connected_email_accounts WHERE candidate_id=? AND status='connected'", (candidate,))
        if not accs:
            raise AgentError("No connected email account.", 409)
        return accs[0]

    # ---------------------------------------------------------------- drafts
    def _candidate_name(self, acc: Dict[str, Any]) -> str:
        return acc.get("display_name") or (acc.get("email") or "").split("@")[0].replace(".", " ").title()

    def _create_draft(self, candidate: str, acc: Dict[str, Any], kind: str, subject: str, body: str, to_email: Optional[str],
                      application_id: Optional[str], interview_id: Optional[str] = None,
                      original_message_id: Optional[str] = None, thread_id: Optional[str] = None) -> Dict[str, Any]:
        draft_id = _uid()
        self._exec("INSERT INTO email_drafts (id,candidate_id,account_id,kind,original_message_id,application_id,interview_id,thread_id,"
                   "to_email,subject,body,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (draft_id, candidate, acc["id"], kind, original_message_id, application_id, interview_id, thread_id,
                    to_email, subject, body, self.now().isoformat()))
        self.log(candidate, "draft_generated", draft_id, "ok", {"kind": kind})
        return self._one("SELECT * FROM email_drafts WHERE id=?", (draft_id,))

    def prepare_interview_reply(self, candidate: str, interview_id: str, mode: str, slots: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Draft a reply for the candidate to approve. Nothing is sent or accepted here."""
        iv = self._interview(candidate, interview_id)
        acc = self._account_for_interview(candidate, iv)
        msg = self._one("SELECT * FROM email_messages WHERE id=?", (iv["message_row_id"],)) or {}
        name, recruiter = self._candidate_name(acc), (iv.get("recruiter_name") or "").split(" ")[0] or "there"
        role = iv["job_title"] or "the role"
        if mode == "availability":
            if not slots:
                raise AgentError("Select at least one available slot to propose.", 422)
            lines = "\n".join(f"- {s['label']}" for s in slots)
            body = (f"Hi {recruiter},\n\nThank you for the interview invitation for the {role} position. "
                    f"I am available at the following times:\n{lines}\n\nPlease let me know which time works best for you.\n\nKind regards,\n{name}")
        elif mode == "accept":
            if not (iv["interview_date"] and iv["interview_time"]):
                raise AgentError("The interview date/time is missing, so there is nothing to accept yet.", 422)
            if json.loads(iv["conflicts"] or "[]"):
                raise AgentError("This time conflicts with your calendar; use mode 'reschedule' instead.", 409)
            when = f"{iv['interview_date']} at {iv['interview_time']}" + (f" ({iv['timezone']})" if not iv["timezone_assumed"] else "")
            body = (f"Hi {recruiter},\n\nThank you for the invitation. I am happy to confirm my attendance for the {role} interview on {when}."
                    f"\n\nLooking forward to speaking with you.\n\nKind regards,\n{name}")
        elif mode == "reschedule":
            if not slots:
                raise AgentError("Select alternative slots to propose.", 422)
            lines = "\n".join(f"- {s['label']}" for s in slots)
            body = (f"Hi {recruiter},\n\nThank you for the invitation to interview for the {role} position. Unfortunately I am not available "
                    f"at the proposed time. Would any of these alternatives work?\n{lines}\n\nApologies for the inconvenience.\n\nKind regards,\n{name}")
        else:
            raise AgentError("mode must be 'availability', 'accept' or 'reschedule'.", 422)
        subject = msg.get("subject") or f"Interview – {role}"
        draft = self._create_draft(candidate, acc, "reply", subject if subject.lower().startswith("re:") else f"Re: {subject}", body,
                                   iv.get("recruiter_email"), iv["application_id"], iv["id"], iv.get("message_row_id"), iv.get("thread_id"))
        if slots is not None and mode in ("availability", "reschedule"):
            self._update("interviews", iv["id"], proposed_slots=json.dumps(slots))
        self._update("interviews", iv["id"], scheduling_status="reply_drafted", updated_at=self.now().isoformat())
        return draft

    def update_draft(self, candidate: str, draft_id: str, subject: Optional[str] = None, body: Optional[str] = None,
                     to_email: Optional[str] = None) -> Dict[str, Any]:
        d = self._draft(candidate, draft_id)
        if d["send_status"] == "sent":
            raise AgentError("This draft was already sent.", 409)
        if d["approval_status"] in ("rejected", "superseded"):
            raise AgentError(f"This draft is {d['approval_status']}.", 409)
        upd = {k: v for k, v in (("subject", subject), ("body", body), ("to_email", to_email)) if v is not None}
        if "body" in upd and not upd["body"].strip():
            raise AgentError("Draft body cannot be empty.", 422)
        if upd:
            self._update("email_drafts", draft_id, **upd, approval_status="pending", approved_at=None)
            self.log(candidate, "draft_edited", draft_id, "ok", list(upd))
        return self._draft(candidate, draft_id)

    def reject_draft(self, candidate: str, draft_id: str) -> Dict[str, Any]:
        d = self._draft(candidate, draft_id)
        if d["send_status"] == "sent":
            raise AgentError("This draft was already sent.", 409)
        self._update("email_drafts", draft_id, approval_status="rejected")
        self._exec("UPDATE follow_up_records SET approval_status='rejected' WHERE draft_id=?", (draft_id,))
        self._clear_follow_up_event(candidate, draft_id)
        self.log(candidate, "draft_rejected", draft_id, "ok")
        return self._draft(candidate, draft_id)

    def _draft(self, candidate: str, draft_id: str) -> Dict[str, Any]:
        d = self._one("SELECT * FROM email_drafts WHERE id=? AND candidate_id=?", (draft_id, candidate))
        if not d:
            raise AgentError("Draft not found.", 404)
        return d

    def approve_and_send(self, candidate: str, draft_id: str, subject: Optional[str] = None, body: Optional[str] = None,
                         to_email: Optional[str] = None) -> Dict[str, Any]:
        """The only code path that sends mail; it requires an explicit candidate approval call."""
        d = self._draft(candidate, draft_id)
        if d["send_status"] == "sent":
            return d  # idempotent: never send twice
        if d["approval_status"] in ("rejected", "superseded"):
            raise AgentError(f"This draft is {d['approval_status']} and cannot be sent.", 409)
        d = self.update_draft(candidate, draft_id, subject, body, to_email) if any(v is not None for v in (subject, body, to_email)) else d
        if not d.get("to_email"):
            raise AgentError("Add the recruiter's email address before sending.", 422)
        acc = self._account(candidate, d["account_id"])
        self._update("email_drafts", draft_id, approval_status="approved", approved_at=self.now().isoformat())
        try:
            token = self._token(candidate, acc)
            self._provider(acc["provider"]).send_email(token, d["to_email"], d["subject"], d["body"], d.get("thread_id"))
        except (AgentError, ProviderError) as err:
            self._update("email_drafts", draft_id, send_status="failed", send_error=str(err))
            self.log(candidate, "send_email", draft_id, "error", str(err))
            raise AgentError(f"Email was NOT sent: {err}", getattr(err, "status", 502),
                             {"draft": self._draft(candidate, draft_id)}) from err
        sent_at = self.now().isoformat()
        self._update("email_drafts", draft_id, send_status="sent", send_error=None, sent_at=sent_at)
        self._exec("UPDATE follow_up_records SET approval_status='approved', sent_at=? WHERE draft_id=?", (sent_at, draft_id))
        self._clear_follow_up_event(candidate, draft_id)
        self.log(candidate, "send_email", draft_id, "ok", {"to": d["to_email"], "kind": d["kind"]})
        if d.get("interview_id"):
            self._exec("UPDATE interviews SET scheduling_status='awaiting_recruiter', updated_at=? WHERE id=? AND scheduling_status='reply_drafted'",
                       (sent_at, d["interview_id"]))
        return self._draft(candidate, draft_id)

    def list_drafts(self, candidate: str) -> List[Dict[str, Any]]:
        return self._all("SELECT d.*, a.company, a.job_title FROM email_drafts d LEFT JOIN applications a ON a.id = d.application_id "
                         "WHERE d.candidate_id=? ORDER BY d.created_at DESC", (candidate,))

    # ------------------------------------------------- interview scheduling
    def confirm_interview(self, candidate: str, interview_id: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Candidate confirms the final details → re-check calendar → create event + reminders."""
        iv = self._interview(candidate, interview_id)
        if iv["scheduling_status"] == "scheduled" and not overrides:
            return {"scheduled": True, "interview": self._interview(candidate, interview_id)}
        allowed = ("interview_date", "interview_time", "duration_minutes", "meeting_link", "timezone", "interview_type", "platform")
        upd = {k: v for k, v in (overrides or {}).items() if k in allowed and v}
        if "timezone" in upd:
            _zone_ok = upd["timezone"]
            try:
                ZoneInfo(_zone_ok)
            except (ZoneInfoNotFoundError, ValueError) as err:
                raise AgentError(f"Unknown time zone '{_zone_ok}'.", 422) from err
            upd["timezone_assumed"] = 0
        iv.update(upd)
        missing = [k for k in ("interview_date", "interview_time", "duration_minutes") if not iv.get(k)]
        if missing:
            raise AgentError("Missing interview details: " + ", ".join(missing), 422, {"missing": missing})
        acc = self._account_for_interview(candidate, iv)
        window = self._interview_window(iv, acc.get("timezone"))
        busy = self._calendar_busy(candidate, acc, window["start"], window["end"])
        if busy is None:
            self._update("interviews", interview_id, **upd, calendar_error="Calendar could not be checked; event not created.")
            raise AgentError("Calendar could not be checked, so the interview was NOT scheduled.", 502)
        conflicts = self._overlaps(window, busy)
        if conflicts:
            self._update("interviews", interview_id, **upd, conflicts=json.dumps(conflicts), scheduling_status="conflict")
            slots = self.generate_slots(candidate, acc, iv["duration_minutes"]) or []
            self._update("interviews", interview_id, proposed_slots=json.dumps(slots))
            self.notify(candidate, "interview_conflict", f"The {iv['company']} interview conflicts with your calendar. Review alternative slots.", iv["application_id"])
            self.log(candidate, "calendar_event", interview_id, "conflict", conflicts)
            raise AgentError("This time conflicts with your calendar. Prepare a rescheduling reply for approval.", 409,
                             {"conflicts": conflicts, "proposed_slots": slots})
        local = window["start"].astimezone(_zone(iv.get("timezone") or acc.get("timezone")))
        local_end = window["end"].astimezone(local.tzinfo)
        lines = [f"Company: {iv['company']}", f"Role: {iv['job_title']}", f"Type: {iv.get('interview_type') or 'Interview'}"]
        if iv.get("platform"):
            lines.append(f"Platform: {iv['platform']}")
        if iv.get("meeting_link"):
            lines.append(f"Meeting link: {iv['meeting_link']}")
        if iv.get("recruiter_name") or iv.get("recruiter_email"):
            lines.append(f"Recruiter: {iv.get('recruiter_name') or ''} <{iv.get('recruiter_email') or 'unknown'}>")
        event = {"title": f"{iv.get('interview_type') or 'Interview'} – {iv['company']} ({iv['job_title']})",
                 "description": "\n".join(lines), "location": iv.get("meeting_link") or iv.get("platform"),
                 "start": local.replace(tzinfo=None).isoformat(), "end": local_end.replace(tzinfo=None).isoformat(),
                 "timezone": local.tzinfo.key, "reminder_minutes": [1440, 60]}
        try:
            event_id = self._provider(acc["provider"]).create_event(self._token(candidate, acc), event)
        except (AgentError, ProviderError) as err:
            self._update("interviews", interview_id, **upd, scheduling_status="calendar_failed", calendar_error=str(err))
            self.log(candidate, "calendar_event", interview_id, "error", str(err))
            raise AgentError(f"Calendar event was NOT created: {err}", 502) from err
        self._update("interviews", interview_id, **upd, conflicts="[]", scheduling_status="scheduled", calendar_event_id=event_id or "created",
                     calendar_error=None, updated_at=self.now().isoformat())
        app = self._application(candidate, iv["application_id"])
        if app and app["status"] not in ("offer_received", "rejected"):
            self._update("applications", app["id"], status="interview", updated_at=self.now().isoformat())
        self.log(candidate, "calendar_event", interview_id, "ok", {"event_id": event_id, "reminders_min": event["reminder_minutes"]})
        return {"scheduled": True, "interview": self._interview(candidate, interview_id)}

    # ------------------------------------------------------------ follow-ups
    def scan_follow_ups(self, candidate: str, min_days: int = 7, gap_days: int = 7, max_follow_ups: int = 2) -> List[Dict[str, Any]]:
        """Draft follow-ups (pending approval) for applications with no recruiter response."""
        created = []
        accs = self._all("SELECT * FROM connected_email_accounts WHERE candidate_id=? AND status='connected'", (candidate,))
        if not accs:
            return []
        acc, now = accs[0], self.now()
        for app in self.list_applications(candidate):
            # An employer who says "we'll reply within 2 weeks" is not chased after 7 days.
            wait = max(min_days, self._response_window(candidate, app["id"]) or 0)
            if app["status"] not in ("applied", "under_review") or now - _dt(app["applied_at"]) < timedelta(days=wait):
                continue
            responded = self._one("SELECT 1 AS x FROM email_messages WHERE candidate_id=? AND application_id=? AND direction='received' "
                                  "AND category IS NOT NULL AND category NOT IN ('application_received','application_under_review') LIMIT 1",
                                  (candidate, app["id"]))
            history = self._all("SELECT * FROM follow_up_records WHERE application_id=? AND candidate_id=? AND approval_status IN ('pending','approved')", (app["id"], candidate))
            sent = [h for h in history if h["sent_at"]]
            if responded or any(h["approval_status"] == "pending" for h in history) or len(sent) >= max_follow_ups:
                continue
            if sent and now - _dt(max(h["sent_at"] for h in sent)) < timedelta(days=gap_days):
                continue
            days = (now - _dt(app["applied_at"])).days
            name = self._candidate_name(acc)
            body = (f"Hi,\n\nI hope you are well. I applied for the {app['job_title']} position at {app['company']} {days} days ago and wanted to "
                    f"follow up on the status of my application. I remain very interested in the opportunity and would be happy to provide any "
                    f"further information you need.\n\nThank you for your time.\n\nKind regards,\n{name}")
            draft = self._create_draft(candidate, acc, "follow_up", f"Following up on my application – {app['job_title']}", body,
                                       app.get("recruiter_email"), app["id"])
            record_id = _uid()
            self._exec("INSERT INTO follow_up_records (id,candidate_id,application_id,draft_id,follow_up_date,draft,approval_status) VALUES (?,?,?,?,?,?,?)",
                       (record_id, candidate, app["id"], draft["id"], now.date().isoformat(), body, "pending"))
            try:  # a calendar problem must never block the follow-up draft itself
                self.schedule_follow_up_calendar(candidate, record_id)
            except AgentError:
                pass
            self.notify(candidate, "follow_up", f"No response from {app['company']} after {days} days. A follow-up draft is ready for your approval.", app["id"])
            created.append(draft)
        self.log(candidate, "follow_up_scan", None, "ok", {"drafts": len(created)})
        return created

    def _response_window(self, candidate: str, app_id: str) -> Optional[int]:
        """Longest reply time (days) any email for this application promised, if stated."""
        days = [json.loads(r["extracted"]).get("response_window_days") for r in self._all(
            "SELECT extracted FROM email_classifications WHERE candidate_id=? AND application_id=?", (candidate, app_id))]
        days = [d for d in days if d]
        return max(days) if days else None

    def _follow_up_record(self, candidate: str, record_id: str) -> Dict[str, Any]:
        rec = self._one("SELECT * FROM follow_up_records WHERE id=? AND candidate_id=?", (record_id, candidate))
        if not rec:
            raise AgentError("Follow-up not found.", 404)
        return rec

    def schedule_follow_up_calendar(self, candidate: str, record_id: str) -> Dict[str, Any]:
        """Put a 'follow up with <company>' reminder on the calendar, filled in from the application's emails.

        Only touches the candidate's own calendar and is idempotent (one event per follow-up).
        """
        rec = self._follow_up_record(candidate, record_id)
        if rec["calendar_event_id"]:
            return rec
        if rec["approval_status"] != "pending":
            raise AgentError(f"This follow-up is {rec['approval_status']}; no reminder needed.", 409)
        app = self._application(candidate, rec["application_id"])
        draft = self._one("SELECT * FROM email_drafts WHERE id=?", (rec["draft_id"],)) if rec["draft_id"] else None
        acc = self._account(candidate, draft["account_id"]) if draft and draft.get("account_id") else None
        if acc is None or acc["status"] != "connected":
            raise AgentError("No connected email account to add the reminder to.", 409)
        zone = _zone(acc.get("timezone"))
        local_now = self.now().astimezone(zone)
        day = local_now.date() + (timedelta(days=1) if local_now.time() >= dtime(9, 30) else timedelta())
        while day.weekday() >= 5:
            day += timedelta(days=1)
        start = datetime.combine(day, dtime(10), tzinfo=zone)

        last = self._one("SELECT subject, sender, received_at, category FROM email_messages WHERE candidate_id=? AND application_id=? "
                         "AND direction='received' ORDER BY received_at DESC LIMIT 1", (candidate, app["id"]))
        window = self._response_window(candidate, app["id"])
        days = (self.now() - _dt(app["applied_at"])).days
        lines = [f"Follow up on your application – {app['job_title']} at {app['company']}",
                 f"Applied: {app['applied_at'][:10]} ({days} days ago)", f"Status: {app['status'].replace('_', ' ')}"]
        if app.get("recruiter_email") or (draft or {}).get("to_email"):
            lines.append(f"Recruiter: {app.get('recruiter_email') or draft['to_email']}")
        if app.get("application_ref"):
            lines.append(f"Reference: {app['application_ref']}")
        if last:
            lines.append(f"Last email from them: \"{(last['subject'] or '')[:80]}\" on {last['received_at'][:10]}")
        else:
            lines.append("No email from them since you applied.")
        if window:
            lines.append(f"They said to expect a reply within ~{window} days.")
        lines.append("A follow-up email draft is waiting for your approval in Cafy → Email Agent. Nothing is sent until you approve it.")
        event = {"title": f"Follow up – {app['company']} ({app['job_title']})", "description": "\n".join(lines),
                 "location": "", "start": start.replace(tzinfo=None).isoformat(),
                 "end": (start + timedelta(minutes=15)).replace(tzinfo=None).isoformat(),
                 "timezone": zone.key, "reminder_minutes": [30]}
        try:
            event_id = self._provider(acc["provider"]).create_event(self._token(candidate, acc), event)
        except (AgentError, ProviderError) as err:
            self._update("follow_up_records", record_id, calendar_error=str(err))
            self.log(candidate, "follow_up_calendar", record_id, "error", str(err))
            raise AgentError(f"Follow-up reminder was NOT added to the calendar: {err}", 502) from err
        self._update("follow_up_records", record_id, calendar_event_id=event_id or "created", calendar_error=None,
                     reminder_at=start.isoformat())
        self.log(candidate, "follow_up_calendar", record_id, "ok", {"event_id": event_id, "at": start.isoformat()})
        return self._follow_up_record(candidate, record_id)

    def _clear_follow_up_event(self, candidate: str, draft_id: str) -> None:
        """Remove the reminder once its follow-up is sent, rejected or superseded (best effort)."""
        rec = self._one("SELECT * FROM follow_up_records WHERE draft_id=? AND candidate_id=?", (draft_id, candidate))
        if not rec or not rec["calendar_event_id"] or rec["calendar_event_id"] == "created":
            return
        try:
            draft = self._one("SELECT account_id FROM email_drafts WHERE id=?", (draft_id,))
            acc = self._account(candidate, draft["account_id"])
            self._provider(acc["provider"]).delete_event(self._token(candidate, acc), rec["calendar_event_id"])
        except (AgentError, ProviderError, NotImplementedError) as err:
            self.log(candidate, "follow_up_calendar_cleanup", rec["id"], "error", str(err))
            return
        self._update("follow_up_records", rec["id"], calendar_event_id=None, reminder_at=None)
        self.log(candidate, "follow_up_calendar_cleanup", rec["id"], "ok")

    # ------------------------------------------------------------- dashboard
    def dashboard(self, candidate: str) -> Dict[str, Any]:
        msgs = self._all(
            "SELECT m.id, m.subject, m.sender, m.sender_email, m.received_at, m.category, m.match_status, m.processing_status, m.direction, "
            "m.application_id, m.thread_id, a.company, a.job_title, a.status AS application_status, c.confidence, c.extracted "
            "FROM email_messages m LEFT JOIN applications a ON a.id = m.application_id "
            "LEFT JOIN email_classifications c ON c.message_row_id = m.id "
            "WHERE m.candidate_id=? AND (m.processing_status != 'ignored' OR (m.direction='sent' AND m.application_id IS NOT NULL)) "
            "ORDER BY m.received_at DESC LIMIT 200", (candidate,))
        for m in msgs:
            ex = json.loads(m.pop("extracted") or "{}")
            m["match_candidates"] = (ex.get("match") or {}).get("candidates", [])
        apps = self.list_applications(candidate)
        drafts = self.list_drafts(candidate)
        pending = [d for d in drafts if d["approval_status"] == "pending"]
        updates = {k: [a for a in apps if a["status"] == s] for k, s in
                   (("under_review", "under_review"), ("assessments", "assessment"), ("interviews", "interview"),
                    ("rejections", "rejected"), ("offers", "offer_received"))}
        interviews = self.list_interviews(candidate)
        return {
            "accounts": self.list_accounts(candidate),
            "providers": {k: v.configured for k, v in self.providers.items()},
            "inbox": [m for m in msgs if m["direction"] == "received"],
            "needs_confirmation": [m for m in msgs if m["processing_status"] in ("needs_confirmation", "needs_review")],
            "interviews": interviews,
            "pending_approvals": pending,
            "application_updates": updates,
            "applications": apps,
            "history": {"sent": [d for d in drafts if d["send_status"] == "sent"],
                        "failed": [d for d in drafts if d["send_status"] == "failed"],
                        "received": [m for m in msgs if m["direction"] == "received"][:50],
                        "follow_ups": self._all("SELECT * FROM follow_up_records WHERE candidate_id=? ORDER BY follow_up_date DESC", (candidate,)),
                        "threads": [m for m in msgs if m["thread_id"]][:50]},
            "notifications": self._all("SELECT * FROM agent_notifications WHERE candidate_id=? ORDER BY id DESC LIMIT 30", (candidate,)),
        }

    def logs(self, candidate: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self._all("SELECT * FROM agent_logs WHERE candidate_id=? ORDER BY id DESC LIMIT ?", (candidate, limit))

    def mark_notifications_read(self, candidate: str) -> None:
        self._exec("UPDATE agent_notifications SET is_read=1 WHERE candidate_id=?", (candidate,))
