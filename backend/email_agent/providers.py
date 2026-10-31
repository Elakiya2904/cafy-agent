"""Gmail and Microsoft Outlook providers (OAuth 2.0 + mail + calendar).

Providers only talk to the remote APIs; all decisions live in the service so
tests can swap in a fake provider.
"""
import base64
import os
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from .classifier import clean_text

TIMEOUT = 20


class ProviderError(Exception):
    """Remote API failure (send/calendar/list)."""


class ProviderAuthError(ProviderError):
    """Token expired, revoked or refresh failed – the account must be reconnected."""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    value = value.rstrip("Z") if value.endswith("Z") else value
    dt = datetime.fromisoformat(value.split(".")[0] if "." in value else value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class BaseProvider:
    name = ""
    scopes: List[str] = []
    required_scopes: List[str] = []  # must be granted for the agent to work (user can untick scopes on the consent screen)
    auth_url = ""
    token_url = ""

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        if not self.configured:
            raise ProviderError(f"{self.name} OAuth is not configured (missing client id/secret).")
        return f"{self.auth_url}?{urlencode(self._auth_params(redirect_uri, state))}"

    def missing_scopes(self, granted: Optional[str]) -> List[str]:
        have = set((granted or "").split())
        return [s for s in self.required_scopes if s not in have]

    def _auth_params(self, redirect_uri: str, state: str) -> Dict[str, str]:
        return {"client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
                "scope": " ".join(self.scopes), "state": state}

    def _token_request(self, data: Dict[str, str]) -> Dict[str, Any]:
        try:
            r = requests.post(self.token_url, data={**data, "client_id": self.client_id,
                                                    "client_secret": self.client_secret}, timeout=TIMEOUT)
        except requests.RequestException as err:
            raise ProviderError(f"Token endpoint unreachable: {err}") from err
        if r.status_code >= 400:
            msg = r.text[:200]
            if r.status_code in (400, 401) and "invalid_grant" in r.text:
                raise ProviderAuthError(f"OAuth grant rejected: {msg}")
            raise ProviderError(f"Token request failed ({r.status_code}): {msg}")
        body = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=int(body.get("expires_in", 3600)))
        return {"access_token": body["access_token"], "refresh_token": body.get("refresh_token"),
                "token_expires_at": expires.isoformat(), "scopes": body.get("scope", " ".join(self.scopes))}

    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        tokens = self._token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})
        tokens.update(self.fetch_profile(tokens["access_token"]))
        return tokens

    def refresh(self, refresh_token: str) -> Dict[str, Any]:
        if not refresh_token:
            raise ProviderAuthError("No refresh token stored; reconnect the account.")
        tokens = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        tokens["refresh_token"] = tokens.get("refresh_token") or refresh_token
        return tokens

    def _call(self, method: str, url: str, token: str, **kw) -> Any:
        try:
            r = requests.request(method, url, headers={"Authorization": f"Bearer {token}", **kw.pop("headers", {})},
                                 timeout=TIMEOUT, **kw)
        except requests.RequestException as err:
            raise ProviderError(f"{self.name} API unreachable: {err}") from err
        if r.status_code == 401:
            raise ProviderAuthError(f"{self.name} access token rejected")
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} API {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    # --- interface -----------------------------------------------------
    def fetch_profile(self, token: str) -> Dict[str, Any]: raise NotImplementedError
    def revoke(self, token: str) -> None: raise NotImplementedError
    def list_messages(self, token: str, since: datetime, limit: int = 50) -> List[Dict[str, Any]]: raise NotImplementedError
    def create_draft(self, token: str, to: str, subject: str, body: str, thread_id: Optional[str]) -> str: raise NotImplementedError
    def send_email(self, token: str, to: str, subject: str, body: str, thread_id: Optional[str]) -> str: raise NotImplementedError
    def busy_intervals(self, token: str, start: datetime, end: datetime, email: str) -> List[Dict[str, datetime]]: raise NotImplementedError
    def create_event(self, token: str, event: Dict[str, Any]) -> str: raise NotImplementedError
    def delete_event(self, token: str, event_id: str) -> None: raise NotImplementedError


class GmailProvider(BaseProvider):
    name = "gmail"
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    scopes = ["openid", "email", "profile",
              "https://www.googleapis.com/auth/gmail.readonly",
              "https://www.googleapis.com/auth/gmail.compose",
              "https://www.googleapis.com/auth/gmail.send",
              "https://www.googleapis.com/auth/calendar.freebusy",
              "https://www.googleapis.com/auth/calendar.events"]
    required_scopes = ["https://www.googleapis.com/auth/gmail.readonly",
                       "https://www.googleapis.com/auth/gmail.send",
                       "https://www.googleapis.com/auth/calendar.freebusy",
                       "https://www.googleapis.com/auth/calendar.events"]
    api = "https://gmail.googleapis.com/gmail/v1/users/me"
    cal = "https://www.googleapis.com/calendar/v3"

    def _auth_params(self, redirect_uri, state):
        return {**super()._auth_params(redirect_uri, state), "access_type": "offline", "prompt": "consent"}

    def fetch_profile(self, token):
        info = self._call("GET", "https://openidconnect.googleapis.com/v1/userinfo", token)
        return {"email": info.get("email"), "display_name": info.get("name")}

    def revoke(self, token):
        try:
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=TIMEOUT)
        except requests.RequestException as err:
            raise ProviderError(f"Revocation failed: {err}") from err

    @staticmethod
    def _body(payload: Dict[str, Any]) -> str:
        parts, stack = [], [payload]
        while stack:
            p = stack.pop(0)
            stack = p.get("parts", []) + stack
            data = (p.get("body") or {}).get("data")
            if data and p.get("mimeType", "").startswith("text/"):
                text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
                parts.append((0 if p["mimeType"] == "text/plain" else 1, text))
        parts.sort(key=lambda x: x[0])
        return clean_text(parts[0][1]) if parts else ""

    MAX_SYNC_MESSAGES = 500

    def _message_refs(self, token, since, limit):
        """Every message id since ``since``, following Gmail's page tokens (newest first)."""
        refs, page_token = [], None
        while len(refs) < max(limit, self.MAX_SYNC_MESSAGES):
            params = {"q": f"after:{int(since.timestamp())} -in:chats", "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token
            res = self._call("GET", f"{self.api}/messages", token, params=params)
            refs += res.get("messages", [])
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return refs

    def list_messages(self, token, since, limit=50):
        ids = self._message_refs(token, since, limit)
        out = []
        for ref in ids:
            m = self._call("GET", f"{self.api}/messages/{ref['id']}", token, params={"format": "full"})
            h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            out.append({"message_id": m["id"], "thread_id": m.get("threadId"), "sender": h.get("from", ""),
                        "to": h.get("to", ""), "subject": h.get("subject", ""), "body": self._body(m.get("payload", {})),
                        "received_at": _iso(datetime.fromtimestamp(int(m["internalDate"]) / 1000, tz=timezone.utc)),
                        "labels": m.get("labelIds", []), "list_unsubscribe": "list-unsubscribe" in h})
        return out

    @staticmethod
    def _raw(to, subject, body):
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        msg.set_content(body)
        return base64.urlsafe_b64encode(msg.as_bytes()).decode()

    def create_draft(self, token, to, subject, body, thread_id):
        msg = {"raw": self._raw(to, subject, body), **({"threadId": thread_id} if thread_id else {})}
        return self._call("POST", f"{self.api}/drafts", token, json={"message": msg}).get("id", "")

    def send_email(self, token, to, subject, body, thread_id):
        msg = {"raw": self._raw(to, subject, body), **({"threadId": thread_id} if thread_id else {})}
        return self._call("POST", f"{self.api}/messages/send", token, json=msg).get("id", "")

    def busy_intervals(self, token, start, end, email):
        res = self._call("POST", f"{self.cal}/freeBusy", token,
                         json={"timeMin": _iso(start), "timeMax": _iso(end), "items": [{"id": "primary"}]})
        busy = res.get("calendars", {}).get("primary", {}).get("busy", [])
        return [{"start": _parse_iso(b["start"]), "end": _parse_iso(b["end"])} for b in busy]

    def create_event(self, token, ev):
        body = {"summary": ev["title"], "description": ev["description"], "location": ev.get("location") or "",
                "start": {"dateTime": ev["start"], "timeZone": ev["timezone"]},
                "end": {"dateTime": ev["end"], "timeZone": ev["timezone"]},
                "reminders": {"useDefault": False, "overrides": [
                    {"method": "popup", "minutes": m} for m in ev.get("reminder_minutes", [60])]}}
        return self._call("POST", f"{self.cal}/calendars/primary/events", token, json=body).get("id", "")

    def delete_event(self, token, event_id):
        try:
            self._call("DELETE", f"{self.cal}/calendars/primary/events/{event_id}", token)
        except ProviderError as err:
            if " 404" in str(err) or " 410" in str(err):  # already gone
                return
            raise


class OutlookProvider(BaseProvider):
    name = "outlook"
    auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    scopes = ["offline_access", "User.Read", "Mail.Read", "Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite"]
    api = "https://graph.microsoft.com/v1.0/me"

    def _auth_params(self, redirect_uri, state):
        return {**super()._auth_params(redirect_uri, state), "response_mode": "query", "prompt": "select_account"}

    def fetch_profile(self, token):
        me = self._call("GET", self.api, token)
        return {"email": me.get("mail") or me.get("userPrincipalName"), "display_name": me.get("displayName")}

    def revoke(self, token):
        # Microsoft has no token revocation endpoint for v2 public flows; the app
        # deletes its stored tokens and the user can remove consent at account.microsoft.com.
        return None

    def list_messages(self, token, since, limit=50):
        res = self._call("GET", f"{self.api}/messages", token,
                         headers={"Prefer": 'outlook.body-content-type="text"'},
                         params={"$filter": f"receivedDateTime ge {_iso(since)}", "$top": limit,
                                 "$orderby": "receivedDateTime desc",
                                 "$select": "id,conversationId,from,toRecipients,subject,body,receivedDateTime"})
        out = []
        for m in res.get("value", []):
            frm = (m.get("from") or {}).get("emailAddress", {})
            to = ", ".join(r["emailAddress"]["address"] for r in m.get("toRecipients", []))
            out.append({"message_id": m["id"], "thread_id": m.get("conversationId"),
                        "sender": f'{frm.get("name", "")} <{frm.get("address", "")}>', "to": to,
                        "subject": m.get("subject", ""), "body": clean_text((m.get("body") or {}).get("content")),
                        "received_at": _iso(_parse_iso(m["receivedDateTime"])), "labels": [],
                        "list_unsubscribe": False})
        return out

    def _message(self, to, subject, body):
        return {"subject": subject, "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}]}

    def create_draft(self, token, to, subject, body, thread_id):
        return self._call("POST", f"{self.api}/messages", token, json=self._message(to, subject, body)).get("id", "")

    def send_email(self, token, to, subject, body, thread_id):
        self._call("POST", f"{self.api}/sendMail", token, json={"message": self._message(to, subject, body), "saveToSentItems": True})
        return ""

    def busy_intervals(self, token, start, end, email):
        res = self._call("POST", f"{self.api}/calendar/getSchedule", token, headers={"Prefer": 'outlook.timezone="UTC"'},
                         json={"schedules": [email], "startTime": {"dateTime": _iso(start), "timeZone": "UTC"},
                               "endTime": {"dateTime": _iso(end), "timeZone": "UTC"}, "availabilityViewInterval": 30})
        items = (res.get("value") or [{}])[0].get("scheduleItems", [])
        return [{"start": _parse_iso(i["start"]["dateTime"]), "end": _parse_iso(i["end"]["dateTime"])}
                for i in items if i.get("status", "busy") != "free"]

    def create_event(self, token, ev):
        body = {"subject": ev["title"], "body": {"contentType": "Text", "content": ev["description"]},
                "start": {"dateTime": ev["start"], "timeZone": ev["timezone"]},
                "end": {"dateTime": ev["end"], "timeZone": ev["timezone"]},
                "location": {"displayName": ev.get("location") or ""},
                "isReminderOn": True, "reminderMinutesBeforeStart": min(ev.get("reminder_minutes", [60]))}
        return self._call("POST", f"{self.api}/events", token, json=body).get("id", "")


def build_providers() -> Dict[str, BaseProvider]:
    return {
        "gmail": GmailProvider(os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")),
        "outlook": OutlookProvider(os.getenv("MICROSOFT_CLIENT_ID"), os.getenv("MICROSOFT_CLIENT_SECRET")),
    }
