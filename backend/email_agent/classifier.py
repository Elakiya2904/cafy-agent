"""Deterministic email understanding for Pipeline 3.

Detects job-related mail, classifies it, extracts structured details and
matches it to an application. Nothing is invented: absent details are reported
in ``missing_fields`` and low-confidence results are left for the candidate.
"""
import re
from datetime import date, datetime
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Tuple

CATEGORIES = (
    "application_received",
    "application_under_review",
    "interview_invitation",
    "assessment_invitation",
    "rejection",
    "additional_information",
    "interview_rescheduling",
    "offer_letter",
)

CATEGORY_STATUS = {
    "application_received": "applied",
    "application_under_review": "under_review",
    "assessment_invitation": "assessment",
    "interview_invitation": "interview",
    "interview_rescheduling": "interview",
    "rejection": "rejected",
    "offer_letter": "offer_received",
}

# Higher rank = later in the funnel; acknowledgements never overwrite later states.
STATUS_RANK = {
    "applied": 0, "under_review": 1, "assessment": 2, "interview": 3,
    "offer_received": 4, "rejected": 4,
}

CONFIDENCE_AUTO = 0.75   # minimum confidence to change application status automatically
MATCH_AUTO = 0.7         # minimum match score to link an email without asking

_PROMO_SENDER = re.compile(r"(newsletter|digest|promo|marketing|deals|offers@|no-?reply@(?:medium|linkedin|quora|substack))", re.I)
_PROMO_TEXT = re.compile(r"(unsubscribe|view in browser|limited time|% off|sale ends|weekly digest|jobs? you may like|recommended jobs|new jobs? (?:for you|matching))", re.I)
_JOB_TEXT = re.compile(
    r"(your application|applied (?:for|to)|application for|the .{0,40} (?:role|position)|"
    r"recruit|hiring|talent acquisition|interview|candidate|assessment|offer letter|job offer|"
    r"regret to inform|unfortunately|next steps|your candidacy|your cv|your resum)", re.I)

# (category, pattern, weight) – first strong signal wins by priority order below.
_RULES: List[Tuple[str, "re.Pattern[str]", float]] = [
    ("offer_letter", re.compile(r"(pleased to offer|offer of employment|job offer|offer letter|we(?:'| a)re delighted to offer|extend (?:you )?an offer)", re.I), 0.9),
    ("rejection", re.compile(r"(regret to inform|unfortunately,? (?:we|after)|not (?:be )?(?:moving|move) forward|decided to (?:move|proceed) (?:forward )?with other|will not be (?:progressing|proceeding)|unable to offer you|not selected|no longer (?:being )?considered|position has been filled)", re.I), 0.9),
    ("interview_rescheduling", re.compile(r"(re-?schedul|change the (?:interview|time)|need to move (?:our|the) (?:interview|call)|alternative (?:time|slot)|new time for (?:your|the) interview|postpone)", re.I), 0.85),
    ("assessment_invitation", re.compile(r"(online assessment|coding (?:test|challenge|assessment)|take-?home|hackerrank|codility|codesignal|complete (?:the|our|an?) (?:assessment|test)|technical assessment|assessment link)", re.I), 0.85),
    ("interview_invitation", re.compile(r"(invite you to (?:an? )?(?:\w+ )?interview|interview invitation|schedule (?:an? |your )?(?:\w+ )?interview|like to (?:invite|arrange|schedule).{0,40}(?:interview|call|chat)|phone screen|your interview|interview (?:is )?(?:scheduled|confirmed)|confirm your availability|availab\w+ for (?:an? )?(?:\w+ )?interview)", re.I), 0.85),
    ("additional_information", re.compile(r"(please (?:provide|send|share|upload|submit)|could you (?:please )?(?:provide|send|share)|we(?:'| a)re missing|additional information|further information|right to work|references? (?:details|contact)|notice period|salary expectation)", re.I), 0.78),
    ("application_under_review", re.compile(r"(under review|reviewing your (?:application|profile|cv)|currently (?:reviewing|being reviewed)|shortlist|review(?:ed)? your (?:application|profile)|in review)", re.I), 0.75),
    ("application_received", re.compile(r"(thank(?:s| you) for (?:applying|your application|your interest)|we(?:'ve| have) received your application|application (?:has been )?received|successfully (?:submitted|applied)|application confirmation)", re.I), 0.8),
]

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_MONTH_RE = "|".join(list(_MONTHS) + [m[:3] for m in _MONTHS])
_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(%s)\.?,?\s+(\d{4})\b" % _MONTH_RE, re.I),
    re.compile(r"\b(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b" % _MONTH_RE, re.I),
]
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![a-z])|\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*(?:am|pm))", re.I)
_DURATION_RE = re.compile(r"\b(\d{2,3})\s*(?:-|\s)?(?:minutes?|mins?)\b|\b(\d(?:\.5)?)\s*(?:-|\s)?hours?\b", re.I)
_LINK_RE = re.compile(r"https?://(?:[\w-]+\.)?(?:meet\.google\.com|zoom\.us|teams\.microsoft\.com|teams\.live\.com|webex\.com|whereby\.com)/[^\s<>\")]+", re.I)
_ASSESS_LINK_RE = re.compile(r"https?://[^\s<>\")]*(?:hackerrank|codility|codesignal|testgorilla|hirevue|assessment)[^\s<>\")]*", re.I)
_TZ_RE = re.compile(r"\b(UTC|GMT|BST|CET|CEST|EST|EDT|CST|CDT|PST|PDT|IST)(?:\s*([+-]\d{1,2}(?::?\d{2})?))?\b")
_PLATFORMS = (("google meet", "Google Meet"), ("meet.google", "Google Meet"), ("zoom", "Zoom"),
              ("microsoft teams", "Microsoft Teams"), ("teams.microsoft", "Microsoft Teams"),
              ("webex", "Webex"), ("phone", "Phone"), ("on-site", "On-site"), ("onsite", "On-site"),
              ("in person", "On-site"), ("in-person", "On-site"))
_TYPES = (("technical", "Technical Interview"), ("coding", "Technical Interview"),
          ("system design", "System Design Interview"), ("behavioural", "Behavioural Interview"),
          ("behavioral", "Behavioural Interview"), ("hr ", "HR Interview"), ("phone screen", "Phone Screen"),
          ("recruiter call", "Recruiter Call"), ("final", "Final Interview"), ("panel", "Panel Interview"))
_DOC_RE = re.compile(r"\b(cv|resume|résumé|cover letter|portfolio|transcript|passport|references?|proof of address|right to work|certificate)s?\b", re.I)
_DEADLINE_RE = re.compile(r"(?:by|before|deadline(?: is)?|within|due(?: by| on)?)\s*:?\s*([^.\n]{3,50})", re.I)
_REF_RE = re.compile(r"\b(?:ref(?:erence)?(?:\s*(?:no\.?|number|id|#))?|req(?:uisition)?(?:\s*id)?|job\s*id)\s*[:#]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
_JOB_TITLE_RE = re.compile(r"(?:for the|for a|for an|applying for|application for|interview invitation\s*[–—-]|position of|role of|role:)\s*:?\s*([A-Z][\w/&+.,' -]{3,60}?)(?=\s+(?:role|position|at|with|has|is|we|\.|,|\n|$)|[.\n]|$)", re.I)


# "we will get back to you within 2 weeks", "expect to hear from us in 5-7 business days"
_RESPONSE_WINDOW_RE = re.compile(
    r"(?:hear (?:back )?from us|get back to you|be in touch|contact you|respond|reply|let you know|update you|feedback|review(?:ing)? (?:process|applications?))"
    r"[^.\n]{0,60}?\b(?:within|in|after|over the next)\s+(?:the next\s+)?(\d{1,2})(?:\s*(?:-|to)\s*(\d{1,2}))?\s*"
    r"(business |working )?(days?|weeks?)\b", re.I)


def extract_response_window_days(text: str) -> Optional[int]:
    """Calendar days the employer says a reply will take (upper bound), else ``None``."""
    m = _RESPONSE_WINDOW_RE.search(text or "")
    if not m:
        return None
    amount = int(m.group(2) or m.group(1))
    if m.group(4).lower().startswith("week"):
        return amount * 7
    return round(amount * 1.4) if m.group(3) else amount


def clean_text(text: Optional[str]) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def parse_sender(raw: str) -> Tuple[str, str]:
    name, addr = parseaddr(raw or "")
    return name.strip().strip('"'), addr.strip().lower()


def is_job_related(sender: str, subject: str, body: str,
                   applications: List[Dict[str, Any]]) -> Tuple[bool, float]:
    """Return (job_related, confidence). Promotions/newsletters are rejected."""
    text = f"{subject}\n{body}"
    _, addr = parse_sender(sender)
    score = 0.0
    if _JOB_TEXT.search(text):
        score += 0.45
    if any(rule.search(text) for _, rule, _ in _RULES[:6]):
        score += 0.25
    low = text.lower()
    if any(a["company"].lower() in low or a["company"].lower().split()[0] in addr for a in applications if a.get("company")):
        score += 0.25
    promo = bool(_PROMO_SENDER.search(addr) or _PROMO_TEXT.search(text))
    if promo:
        # A newsletter that merely mentions "jobs" is not an application email.
        score -= 0.5
    score = max(0.0, min(1.0, score))
    return score >= 0.5, round(score, 2)


def classify(subject: str, body: str) -> Tuple[Optional[str], float]:
    text = f"{subject}\n{body}"
    hits = [(cat, w) for cat, rule, w in _RULES if rule.search(text)]
    if not hits:
        return None, 0.0
    cat, weight = hits[0]  # rules are ordered by priority
    # Corroboration (e.g. rescheduling + interview mention) raises confidence a little.
    conf = min(0.98, weight + (0.05 if len(hits) > 1 else 0.0) + (0.05 if rule_in_subject(cat, subject) else 0.0))
    return cat, round(conf, 2)


def rule_in_subject(cat: str, subject: str) -> bool:
    return any(c == cat and rule.search(subject) for c, rule, _ in _RULES)


def _parse_date(text: str) -> Optional[str]:
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            g = m.groups()
            if pat is _DATE_PATTERNS[0]:
                return date(int(g[0]), int(g[1]), int(g[2])).isoformat()
            if g[0].isdigit():
                day, mon, year = int(g[0]), g[1], int(g[2])
            else:
                mon, day, year = g[0], int(g[1]), int(g[2])
            mon_n = _MONTHS.get(mon.lower()) or next(v for k, v in _MONTHS.items() if k.startswith(mon.lower()[:3]))
            return date(year, mon_n, day).isoformat()
        except (ValueError, StopIteration):
            continue
    return None


def _parse_time(text: str) -> Optional[str]:
    m = _TIME_RE.search(text)
    if not m:
        return None
    if m.group(3):
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        pm = m.group(3).lower().startswith("p")
        if hour < 1 or hour > 12:
            return None
        hour = hour % 12 + (12 if pm else 0)
    else:
        hour, minute = int(m.group(4)), int(m.group(5))
    return f"{hour:02d}:{minute:02d}"


def extract_details(subject: str, body: str, category: str, sender: str,
                    received_at: Optional[str] = None) -> Dict[str, Any]:
    """Pull structured fields out of an email. Unknown values stay ``None``."""
    text = clean_text(f"{subject}\n{body}")
    name, addr = parse_sender(sender)
    low = text.lower()
    d: Dict[str, Any] = {
        "company": None, "job_title": None, "recruiter_name": name or None, "recruiter_email": addr or None,
        "email_date": received_at, "application_reference": None,
        "interview_date": None, "interview_time": None, "timezone": None, "duration_minutes": None,
        "interview_type": None, "platform": None, "meeting_link": None,
        "assessment_deadline": None, "assessment_link": None, "required_documents": [],
        "requests_availability": False, "proposed_changes": None,
        "response_window_days": extract_response_window_days(text),
    }
    m = _REF_RE.search(text)
    if m:
        d["application_reference"] = m.group(1)
    m = _JOB_TITLE_RE.search(subject) or _JOB_TITLE_RE.search(text)
    if m:
        d["job_title"] = m.group(1).strip(" -–—.,")

    if category in ("interview_invitation", "interview_rescheduling"):
        d["interview_date"] = _parse_date(text)
        d["interview_time"] = _parse_time(text)
        tz = _TZ_RE.search(text)
        if tz:
            d["timezone"] = tz.group(0)
        m = _DURATION_RE.search(text)
        if m:
            d["duration_minutes"] = int(m.group(1)) if m.group(1) else int(float(m.group(2)) * 60)
        for key, label in _TYPES:
            if key in low:
                d["interview_type"] = label
                break
        link = _LINK_RE.search(text)
        if link:
            d["meeting_link"] = link.group(0).rstrip(".,;")
        for key, label in _PLATFORMS:
            if key in low or (link and key in link.group(0).lower()):
                d["platform"] = label
                break
        d["requests_availability"] = bool(re.search(
            r"(your availability|are you available|when are you available|share (?:some )?(?:times|slots)|"
            r"provide (?:a few |some )?(?:times|slots)|let us know (?:what|which) (?:times?|days?) (?:work|suit)|confirm your availability)", low))
        if category == "interview_rescheduling":
            d["proposed_changes"] = text[:300]
    elif category == "assessment_invitation":
        link = _ASSESS_LINK_RE.search(text) or re.search(r"https?://[^\s<>\")]+", text)
        d["assessment_link"] = link.group(0).rstrip(".,;") if link else None
        m = _DEADLINE_RE.search(text)
        d["assessment_deadline"] = (_parse_date(m.group(1)) or m.group(1).strip()) if m else None
        m = _DURATION_RE.search(text)
        if m:
            d["duration_minutes"] = int(m.group(1)) if m.group(1) else int(float(m.group(2)) * 60)
    elif category == "additional_information":
        d["required_documents"] = sorted({x.lower() for x in _DOC_RE.findall(text)})
    return d


def missing_interview_fields(d: Dict[str, Any]) -> List[str]:
    missing = []
    for key in ("interview_date", "interview_time", "duration_minutes", "interview_type", "meeting_link"):
        if not d.get(key):
            missing.append(key)
    return missing


def match_application(sender: str, subject: str, body: str, thread_app_id: Optional[str],
                      applications: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score every application. Returns status matched / needs_confirmation / unmatched."""
    name, addr = parse_sender(sender)
    domain = addr.split("@")[-1] if "@" in addr else ""
    low_subject, low_body = (subject or "").lower(), (body or "").lower()
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for app in applications:
        s = 0.0
        company = (app.get("company") or "").lower().strip()
        title = (app.get("job_title") or "").lower().strip()
        tokens = [t for t in re.split(r"[^a-z0-9]+", company) if len(t) > 2]
        if thread_app_id and app["id"] == thread_app_id:
            s += 1.0
        if app.get("recruiter_email") and app["recruiter_email"].lower() == addr:
            s += 0.4
        if company:
            if company in domain.replace("-", " ") or (tokens and tokens[0] in domain):
                s += 0.4
            if company in name.lower():
                s += 0.3
            if company in low_subject:
                s += 0.3
            elif company in low_body:
                s += 0.2
        if title:
            if title in low_subject:
                s += 0.35
            elif title in low_body:
                s += 0.25
        ref = app.get("application_ref")
        if ref and ref.lower() in f"{low_subject} {low_body}":
            s += 0.5
        scored.append((round(s, 2), app))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 0.3:
        return {"status": "unmatched", "application_id": None, "score": scored[0][0] if scored else 0.0, "candidates": []}
    best, second = scored[0], (scored[1][0] if len(scored) > 1 else 0.0)
    candidates = [{"application_id": a["id"], "company": a["company"], "job_title": a["job_title"], "score": sc}
                  for sc, a in scored[:3] if sc >= 0.3]
    # Ambiguous when two applications (e.g. two roles at one company) score nearly alike.
    # A lone, clearly company-specific candidate is enough; near-ties are never auto-linked.
    if (best[0] >= MATCH_AUTO and best[0] - second >= 0.15) or (best[0] >= 0.5 and best[0] - second >= 0.4):
        return {"status": "matched", "application_id": best[1]["id"], "score": best[0], "candidates": candidates}
    return {"status": "needs_confirmation", "application_id": best[1]["id"], "score": best[0], "candidates": candidates}
