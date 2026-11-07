"""Canonical resume structure shared by parsing, tailoring, scoring and every renderer.

One place decides:
- which sections exist, what they are called and in which order they print;
- which experience entries are internships (kept in their own ``internships`` list);
- when two entries are the same record (so duplicates are merged, never dropped blindly);
- how dates are written.

The LaTeX, DOCX, React-PDF and HTML renderers all read ``render_sections`` (or its
JavaScript mirror ``frontend/src/resumeSections.js``), so they cannot drift apart.
"""
from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

SECTION_TITLES: Dict[str, str] = {
    "summary": "About Me",
    "experience": "Work Experience",
    "internships": "Internship Experience",
    "education": "Education",
    "projects": "Projects",
    "skills": "Skills",
    "certifications": "Certifications",
    "publications": "Publications",
    "achievements": "Achievements",
}

# The UK template prints exactly these five sections, in this order. Full-time roles and
# internships share "Work Experience" (full-time first). Certifications, publications and
# achievements stay in the data and the editor but are not printed.
PRINTED_SECTIONS = ["summary", "education", "experience", "projects", "skills"]

ENTRY_SECTIONS = (
    "experience", "internships", "education", "projects",
    "certifications", "publications", "achievements",
)

_INTERNSHIP_TITLE = re.compile(
    r"\b(?:interns?|internship|industrial\s+placement|placement\s+(?:student|year)|"
    r"year\s+in\s+industry|co-?op|summer\s+(?:analyst|associate|intern|student|engineer)|"
    r"spring\s+(?:week|insight)|insight\s+programme|work\s+experience\s+(?:student|placement))\b",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def entry_title(entry: Dict[str, Any]) -> str:
    return _text(entry.get("title") or entry.get("role") or entry.get("name") or entry.get("degree"))


def entry_org(entry: Dict[str, Any]) -> str:
    return _text(
        entry.get("organization") or entry.get("company") or entry.get("institution")
        or entry.get("school") or entry.get("issuer") or entry.get("venue") or entry.get("publisher")
    )


def is_internship(entry: Any) -> bool:
    """True when the entry's own job title says it was an internship or placement."""
    if not isinstance(entry, dict):
        return False
    return bool(_INTERNSHIP_TITLE.search(entry_title(entry)))


# ---------------------------------------------------------------- dates

_MONTHS = {
    "jan": "Jan", "january": "Jan", "feb": "Feb", "february": "Feb", "mar": "Mar", "march": "Mar",
    "apr": "Apr", "april": "Apr", "may": "May", "jun": "Jun", "june": "Jun", "jul": "Jul", "july": "Jul",
    "aug": "Aug", "august": "Aug", "sep": "Sep", "sept": "Sep", "september": "Sep",
    "oct": "Oct", "october": "Oct", "nov": "Nov", "november": "Nov", "dec": "Dec", "december": "Dec",
}
_MONTH_BY_NUMBER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTH_WORD = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?(?=\s*'?\d)", re.IGNORECASE)
_NUMERIC_MONTH = re.compile(r"\b(0?[1-9]|1[0-2])\s*/\s*((?:19|20)\d{2})\b")
_ONGOING = re.compile(r"\b(?:present|currently|current|now|ongoing|date)\b", re.IGNORECASE)
_RANGE_SEPARATOR = re.compile(r"\s*(?:-{1,2}|–|—|\bto\b|\buntil\b)\s*", re.IGNORECASE)


def standardize_dates(value: Any) -> str:
    """Write dates one way: ``Sep 2023 – Present``, ``2019 – 2022``, ``Jun 2024``.

    Only reformats what is there; it never adds or guesses a date.
    """
    text = _text(value).strip("()[] ")
    if not text:
        return ""
    text = _NUMERIC_MONTH.sub(lambda m: f"{_MONTH_BY_NUMBER[int(m.group(1)) - 1]} {m.group(2)}", text)
    text = _MONTH_WORD.sub(lambda m: _MONTHS[m.group(1).lower()], text)
    text = _ONGOING.sub("Present", text)
    # Only treat a dash as a range when both sides look like dates.
    parts = _RANGE_SEPARATOR.split(text)
    if len(parts) == 2 and all(re.search(r"(?:19|20)\d{2}|Present", p) for p in parts):
        text = f"{parts[0].strip()} – {parts[1].strip()}"
    return re.sub(r"\s{2,}", " ", text).strip()


# ---------------------------------------------------------------- de-duplication

def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _same_dates(a: str, b: str) -> bool:
    return not a or not b or _key(standardize_dates(a)) == _key(standardize_dates(b))


def _is_same_record(a: Dict[str, Any], b: Dict[str, Any], section: str) -> bool:
    title_a, title_b = _key(entry_title(a)), _key(entry_title(b))
    org_a, org_b = _key(entry_org(a)), _key(entry_org(b))
    if not _same_dates(_text(a.get("dates")), _text(b.get("dates"))):
        return False
    if title_a and title_a == title_b and org_a == org_b:
        return True
    if section == "education":
        # A parser often emits the institution line and the degree line as two records.
        if org_a and org_a == org_b and (not title_a or not title_b):
            return True
        if title_a and title_a == title_b and (not org_a or not org_b):
            return True
    return False


_STOPWORDS = {
    "the", "and", "for", "with", "using", "via", "into", "from", "that", "this", "was", "were", "are",
    "its", "our", "their", "as", "of", "in", "on", "to", "at", "by", "an", "a", "well",
}


def _content_words(text: Any) -> set:
    words = set()
    for word in re.findall(r"[a-z0-9][a-z0-9.+#/-]*", str(text or "").lower()):
        word = word.strip(".-/")
        # Numbers always count ("thing 1" and "thing 2" differ); other 1-letter tokens do not.
        if not word or word in _STOPWORDS or (len(word) < 2 and not word.isdigit()):
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) - len(suffix) >= 4 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        words.add(word)
    return words


def _repeats(text: Any, other_text: Any, threshold: float) -> bool:
    """True when (almost) every content word of ``text`` already appears in ``other_text``.

    Short lines (under 4 content words) only count as repeats when every word matches, so
    brief but distinct bullets are never dropped.
    """
    words = _content_words(text)
    if not words:
        return False
    if len(words) < 4:
        threshold = 1.0
    return len(words & _content_words(other_text)) / len(words) >= threshold


def _same_point(a: Any, b: Any, threshold: float = 0.85) -> bool:
    """Two lines make the same point: they share most words in BOTH directions.

    Unlike ``_repeats`` (is one contained in the other), a short line that happens to use some
    of a longer line's words is not a copy of it.
    """
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return False
    shared = len(wa & wb)
    return shared / max(len(wa), len(wb)) >= (1.0 if min(len(wa), len(wb)) < 4 else threshold)


def without_repeats(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Drop text that only repeats what the entry already says.

    - a description that restates the heading line (e.g. "B.Tech in Information Technology,
      CGPA 8.1/10" under the heading "B.Tech / Information Technology, CGPA 8.1/10") or that
      merely summarises the entry's own bullets;
    - a bullet that repeats an earlier bullet or the description.
    Nothing new is ever added; only the duplicate copy is removed.
    """
    if not isinstance(entry, dict):
        return entry
    entry = dict(entry)
    heading = " ".join(_text(entry.get(k)) for k in (
        "title", "name", "degree", "organization", "company", "institution", "issuer", "location", "dates"))
    bullets = [b for b in (entry.get("bullets") or []) if _text(b)]
    description = _text(entry.get("description"))
    if description and (
        _repeats(description, heading, 0.8)
        or (bullets and _repeats(description, heading + " " + " ".join(bullets), 0.75))
    ):
        entry["description"] = ""
        description = ""
    kept: List[str] = []
    for bullet in bullets:
        if any(_same_point(bullet, earlier) for earlier in kept) or (
            description and _same_point(bullet, description)
        ) or _repeats(bullet, heading, 0.9):
            continue
        kept.append(bullet)
    if "bullets" in entry:
        entry["bullets"] = kept
    return entry


def same_record(a: Any, b: Any, section: str = "experience") -> bool:
    """True when two entries describe the same role, degree or item (dates must not conflict)."""
    return isinstance(a, dict) and isinstance(b, dict) and _is_same_record(a, b, section)


def _merge_into(kept: Dict[str, Any], dup: Dict[str, Any]) -> None:
    for field, value in dup.items():
        if field == "bullets":
            continue
        if not _text(kept.get(field)) and _text(value):
            kept[field] = value
    if len(_text(dup.get("description"))) > len(_text(kept.get("description"))):
        kept["description"] = dup.get("description")
    bullets = list(kept.get("bullets") or [])
    seen = {_key(b) for b in bullets}
    for bullet in dup.get("bullets") or []:
        if _key(bullet) and _key(bullet) not in seen:
            bullets.append(bullet)
            seen.add(_key(bullet))
    kept["bullets"] = bullets


def dedupe_entries(entries: Iterable[Any], section: str = "experience") -> List[Any]:
    """Merge repeated records (same role and organisation, or same degree and institution).

    Nothing is lost: missing fields and extra bullets from a duplicate are folded into the
    first copy. Records with different dates stay separate (e.g. two stints at one company).
    """
    result: List[Any] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            if isinstance(entry, str) and _key(entry) and _key(entry) not in {_key(r) for r in result if isinstance(r, str)}:
                result.append(entry)
            continue
        entry = copy.deepcopy(entry)
        for kept in result:
            if isinstance(kept, dict) and _is_same_record(kept, entry, section):
                _merge_into(kept, entry)
                break
        else:
            result.append(entry)
    return result


def split_internships(
    experience: Optional[List[Any]], internships: Optional[List[Any]]
) -> Tuple[List[Any], List[Any]]:
    """Move internship roles out of ``experience`` and drop experience copies of internships.

    Internships are never turned into full-time roles and never lost: every internship that
    was in either list ends up in the returned ``internships`` list exactly once.
    """
    exp_out: List[Any] = []
    interns = list(internships or [])
    for entry in experience or []:
        if is_internship(entry):
            interns.append(entry)
        else:
            exp_out.append(entry)
    interns = dedupe_entries(interns, "internships")
    exp_out = [
        e for e in dedupe_entries(exp_out, "experience")
        if not any(same_record(i, e, "internships") for i in interns)
    ]
    return exp_out, interns


# ---------------------------------------------------------------- rendering model

def section_order(resume: Dict[str, Any]) -> List[str]:
    return list(PRINTED_SECTIONS)


def entry_meta(subheading: str, location: str, dates: str) -> str:
    """The template's first entry line: ``Organisation, Location | dates``."""
    place = ", ".join(p for p in (subheading, location) if p)
    return " | ".join(p for p in (place, dates) if p)


def render_entry(entry: Any, section: str) -> Dict[str, Any]:
    """Map any entry shape to the lines every renderer prints (UK template):

    ``meta``    - ``Organisation, Location | dates`` (regular weight)
    ``heading`` - role / degree / project name (bold)
    then ``description`` and ``bullets``. ``subheading``, ``dates`` and ``location`` are
    kept separately too, for callers that need the parts.
    """
    if isinstance(entry, str):
        return {"heading": _text(entry), "subheading": "", "dates": "", "location": "", "meta": "",
                "description": "", "bullets": []}
    entry = without_repeats(entry or {})
    if section == "education":
        heading = _text(entry.get("degree") or entry.get("title"))
        sub = _text(entry.get("institution") or entry.get("organization") or entry.get("school"))
    elif section == "certifications":
        heading = _text(entry.get("name") or entry.get("title"))
        sub = _text(entry.get("issuer") or entry.get("organization"))
    elif section == "publications":
        heading = _text(entry.get("title") or entry.get("name"))
        sub = _text(entry.get("organization") or entry.get("venue") or entry.get("publisher"))
    elif section == "achievements":
        heading = _text(entry.get("title") or entry.get("name"))
        sub = _text(entry.get("organization") or entry.get("issuer"))
    elif section == "projects":
        heading = _text(entry.get("title") or entry.get("name"))
        sub = _text(entry.get("organization") or entry.get("company") or entry.get("role"))
    else:  # experience, internships
        heading = _text(entry.get("title") or entry.get("role"))
        sub = _text(entry.get("organization") or entry.get("company"))
    if not heading and sub:
        heading, sub = sub, ""
    dates = standardize_dates(entry.get("dates") or entry.get("date") or entry.get("year"))
    location = _text(entry.get("location"))
    return {
        "heading": heading,
        "subheading": sub,
        "dates": dates,
        "location": location,
        "meta": entry_meta(sub, location, dates),
        "description": _text(entry.get("description")),
        "bullets": [_text(b) for b in (entry.get("bullets") or []) if _text(b)],
    }


def render_sections(resume: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The five printed sections, in template order, skipping empty ones.

    Shared by the LaTeX and DOCX exports (and mirrored by ``resumeSections.js``).
    """
    sections: List[Dict[str, Any]] = []
    for key in section_order(resume):
        if key == "summary":
            text = _text(resume.get("professional_summary") or resume.get("summary"))
            if text:
                sections.append({"key": key, "title": SECTION_TITLES[key], "kind": "text", "text": text})
        elif key == "skills":
            skills = [_text(s) for s in (resume.get("skills") or []) if _text(s)]
            if skills:
                sections.append({"key": key, "title": SECTION_TITLES[key], "kind": "skills", "skills": skills,
                                 "text": ", ".join(skills)})
        else:
            raw = list(resume.get(key) or [])
            if key == "experience":
                raw += list(resume.get("internships") or [])
            entries = [render_entry(e, key) for e in raw]
            entries = [e for e in entries if e["heading"] or e["description"] or e["bullets"]]
            if entries:
                sections.append({"key": key, "title": SECTION_TITLES[key], "kind": "entries", "entries": entries})
    return sections


# ---------------------------------------------------------------- experience length

_MONTH_INDEX = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_DATE_RANGE = re.compile(
    r"(?:(?P<sm>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?(?P<sy>(?:19|20)\d{2})\s*"
    r"(?:-|–|—|to)\s*(?:(?:(?P<em>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?"
    r"(?P<ey>(?:19|20)\d{2})|(?P<now>present|current|now|date))",
    re.IGNORECASE,
)


def full_time_years(entries: Iterable[Any], today: Optional[date] = None) -> float:
    """Years covered by full-time roles' date ranges (overlapping roles are counted once).

    Internships are not passed in here: they are relevant experience, not years of employment.
    """
    today = today or date.today()
    now_index = today.year * 12 + today.month - 1
    covered: Set[int] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        match = _DATE_RANGE.search(str(entry.get("dates") or ""))
        if not match:
            continue
        start = int(match.group("sy")) * 12 + _MONTH_INDEX.get((match.group("sm") or "jan")[:3].lower(), 0)
        if match.group("now"):
            end = now_index
        else:
            end = int(match.group("ey")) * 12 + _MONTH_INDEX.get((match.group("em") or "jan")[:3].lower(), 0)
        if start <= end <= now_index + 12:
            covered.update(range(start, end))
    return round(len(covered) / 12, 1)
