"""Maps detected application-form fields to stored candidate data.

Nothing is invented: a field is only pre-filled from data the candidate actually
has. Eligibility/sensitive questions are never auto-answered, and open questions
are routed to the AI generator for mandatory candidate review.
"""
import re
from typing import Any, Dict, List, Optional

SENSITIVE = re.compile(
    r"(sponsor|visa|right to work|work(?:ing)? authori[sz]|legally (?:authori[sz]ed|entitled)|eligible to work|work permit|immigration|"
    r"salary|compensation|pay expectation|expected pay|notice period|gender|pronoun|ethnic|race\b|racial|disabilit|veteran|"
    r"sexual orientation|religio|criminal|convict|date of birth|\bdob\b|nationality|citizenship|marital|security clearance|relocat)", re.I)
OPEN_QUESTION = re.compile(
    r"(why (?:do you|are you|would you).{0,40}(?:want|interested|join|apply|work)|why .{0,30}(?:company|role|position|us\b)|"
    r"relevant experience|what makes you|why you|suitable|tell us (?:about|why)|describe (?:your|a time)|motivation|"
    r"cover letter|additional information|anything else|about yourself|how did you)", re.I)

_RULES = [  # (category, regex on label/name/autocomplete/placeholder)
    ("first_name", r"(first[\s_-]*name|given[\s_-]*name|forename|\bfname\b)"),
    ("last_name", r"(last[\s_-]*name|family[\s_-]*name|surname|\blname\b)"),
    ("full_name", r"(^|[\s_-])(full[\s_-]*name|your name|name)($|[\s_-])"),
    ("email", r"(e-?mail)"),
    ("phone", r"(phone|mobile|telephone|\btel\b|contact number)"),
    ("linkedin", r"linked-?in"),
    ("github", r"github"),
    ("portfolio", r"(portfolio|personal (?:web)?site|website|\burl\b)"),
    ("location", r"(current location|\bcity\b|\blocation\b|where are you based|town)"),
    ("address", r"(address|postcode|postal|zip|street)"),
    ("education", r"(school|university|college|institution|degree|education|qualification|field of study)"),
    ("experience", r"(current (?:company|employer)|employer|current (?:job )?title|job title|years of experience|work experience)"),
    ("skills", r"\bskills?\b"),
    ("certifications", r"certif"),
]
_RULES = [(c, re.compile(p, re.I)) for c, p in _RULES]
_DOC = [("resume", re.compile(r"(resume|résumé|\bcv\b|curriculum)", re.I)),
        ("cover_letter", re.compile(r"cover[\s_-]*letter", re.I)),
        ("portfolio", re.compile(r"portfolio", re.I)),
        ("certificate", re.compile(r"(certificate|transcript)", re.I))]


def field_text(field: Dict[str, Any]) -> str:
    return " ".join(str(field.get(k) or "") for k in ("label", "name", "autocomplete", "placeholder", "id")).strip()


def classify_field(field: Dict[str, Any]) -> str:
    """Return a category: a profile key, 'document:<type>', 'sensitive', 'open_question' or 'unknown'."""
    text = field_text(field)
    label_text = f"{field.get('label') or ''} {field.get('placeholder') or ''}"
    if field.get("type") == "file":
        for doc, rx in _DOC:
            if rx.search(text):
                return f"document:{doc}"
        return "document:other"
    if SENSITIVE.search(label_text) or SENSITIVE.search(str(field.get("name") or "")):
        return "sensitive"
    if field.get("type") == "textarea" or len(label_text) > 40:
        if OPEN_QUESTION.search(label_text):
            return "open_question"
    ac = (field.get("autocomplete") or "").lower()
    ac_map = {"given-name": "first_name", "family-name": "last_name", "name": "full_name", "email": "email", "tel": "phone"}
    if ac in ac_map:
        return ac_map[ac]
    for cat, rx in _RULES:
        if rx.search(text):
            if cat == "full_name" and re.search(r"(first|last|user|company|school|file)", text, re.I):
                continue
            return cat
    if OPEN_QUESTION.search(label_text):
        return "open_question"
    return "unknown"


def split_name(full: str) -> (str, str):
    parts = (full or "").split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def profile_value(category: str, profile: Dict[str, Any]) -> Optional[str]:
    first, last = split_name(profile.get("candidate_name", ""))
    edu = (profile.get("education") or [{}])[0] if profile.get("education") else {}
    exp = (profile.get("experience") or [{}])[0] if profile.get("experience") else {}
    values = {
        "first_name": first, "last_name": last, "full_name": profile.get("candidate_name"),
        "email": profile.get("email"), "phone": profile.get("phone"),
        "linkedin": profile.get("linkedin"), "github": profile.get("github"),
        "portfolio": profile.get("portfolio") or profile.get("github"),
        "location": profile.get("location"), "address": profile.get("address"),
        "education": edu.get("institution") or edu.get("school") or edu.get("organization") or edu.get("degree"),
        "experience": exp.get("company") or exp.get("organization"),
        "skills": ", ".join(profile.get("skills") or []),
        "certifications": ", ".join(str(c.get("name") if isinstance(c, dict) else c) for c in profile.get("certifications") or []),
    }
    v = values.get(category)
    return str(v).strip() if v and str(v).strip() else None


def _label_specific(category: str, field: Dict[str, Any], profile: Dict[str, Any]) -> Optional[str]:
    """Refine education/experience fields that ask for one specific piece."""
    text = field_text(field).lower()
    edu = (profile.get("education") or [{}])[0] if profile.get("education") else {}
    exp = (profile.get("experience") or [{}])[0] if profile.get("experience") else {}
    if category == "education":
        if "degree" in text or "qualification" in text:
            return edu.get("degree") or edu.get("title")
        if "field" in text:
            return edu.get("field") or edu.get("field_of_study")
    if category == "experience":
        if "title" in text:
            return exp.get("title")
    return None


def match_option(value: str, options: List[str]) -> Optional[str]:
    v = value.strip().lower()
    for o in options:
        if o.strip().lower() == v:
            return o
    for o in options:
        ol = o.strip().lower()
        if ol and (v in ol or ol in v) and len(ol) > 2:
            return o
    return None


def map_field(field: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Return {category, value, source, completion_status, approval_status, note}."""
    cat = classify_field(field)
    required = bool(field.get("required"))
    base = {"category": cat, "value": None, "source": "unknown", "completion_status": "needs_input",
            "approval_status": "pending", "note": None}
    if cat.startswith("document:"):
        return {**base, "source": "document", "completion_status": "needs_permission", "note": "Upload requires your permission."}
    if cat == "sensitive":
        return {**base, "note": "Eligibility/sensitive question – answer it yourself; Cafy never auto-answers these."}
    if cat == "open_question":
        return {**base, "source": "ai_suggestion", "completion_status": "needs_generation",
                "note": "AI-suggested answer – review before use."}
    if cat == "unknown":
        if not required:
            return {**base, "completion_status": "skipped", "approval_status": "not_required", "note": "Optional field Cafy does not recognise; left blank."}
        return {**base, "note": "Required field Cafy could not map; please fill it in."}
    value = _label_specific(cat, field, profile) or profile_value(cat, profile)
    if not value:
        return {**base, "note": f"Your profile has no {cat.replace('_', ' ')}; please enter it."}
    options = field.get("options") or []
    if options:
        chosen = match_option(value, [o if isinstance(o, str) else o.get("label", "") for o in options])
        if not chosen:
            return {**base, "note": f"No option matched '{value}'; please choose one."}
        value = chosen
    return {**base, "value": value, "source": "profile", "completion_status": "completed", "approval_status": "pending"}
