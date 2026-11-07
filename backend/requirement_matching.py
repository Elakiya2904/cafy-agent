"""Job-description-driven, evidence-based resume-to-job matching (UK listings).

How a job is scored (method ``requirement-coverage-v1``):

1. **Requirements come from the job description.** The description is split into lines
   (HTML is flattened) and grouped under its headings. Lines under headings such as
   "Essential", "Requirements", "What we're looking for", "About you" are *essential*; lines
   under "Desirable", "Nice to have", "Preferred", "Bonus" are *desirable*. Words on the line
   itself ("essential", "must", "ideally", "a plus") override the heading. Each skill the
   listing names becomes one requirement with the strongest importance of any line it is on.
   A skill only mentioned in the duties ("What you'll do") is *desirable* when the listing has
   its own requirement section, because the employer did not list it as a requirement. When
   the listing has no requirement structure at all, every skill is treated as essential.
2. **Each requirement is graded against the whole resume** - skills list, summary, education,
   full-time roles, internships, projects and certifications - as
   ``direct`` (used in a role, internship, project or certification), ``weak`` (only listed
   in the Skills section, summary or education), ``transferable`` (a related tool from the same
   family, e.g. Azure for AWS) or ``missing``. The exact resume line is kept as evidence.
3. **Score** = earned / possible over the skill requirements, where each requirement is worth
   its importance multiplier and earns its evidence credit (both in ``MATCH_CONFIG``). Each
   skill is counted once (aliases and synonyms collapse to one requirement).
4. **Separate checks, not blended into the score:** experience level and stated years,
   essential qualifications (degree level, professional qualifications), and eligibility
   items (right to work, security clearance, driving licence, DBS) which the candidate must
   confirm. UK visa sponsorship is never part of the score.
5. **Top band gate:** a score of ``top_band.min_score`` (85) or more needs at least
   ``top_band.min_matched_skills`` (4) matched skills and every essential qualification met;
   otherwise the score is capped just below the band and the reasons are listed. Experience
   level is applied earlier as a listing filter (a fresher is never shown roles for experienced
   hires, and vice versa); ``require_experience_match`` can also make it a score gate.

The multipliers and credits are a transparent starting point, not tuned values: calibrate them
with ``backend/scripts/calibrate_matching.py`` against reviewed resume-job pairs and real
application outcomes. Override them without code changes by pointing
``CAFY_MATCH_CONFIG`` at a JSON file with any subset of ``MATCH_CONFIG``.
"""
from __future__ import annotations

import copy
import html
import json
import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .job_match_analysis_service import TRANSFERABLE_CLUSTERS, _job_skills, _norm, _skill_extractor
from .resume_service import SKILL_ALIASES
from .recommendation_service import _experience_level_matches, _job_experience_requirement, job_level
from .skill_catalog import SYNONYMS, WEAK_MATCH_SKILLS
from .skill_matching import _phrase_literals, cached_stems, phrase_in_lowered, text_has_skill

logger = logging.getLogger("cafy.matching")

METHOD = "requirement-coverage-v1"

DEFAULT_MATCH_CONFIG: Dict[str, Any] = {
    # How much a requirement counts, by the importance the employer gave it.
    "importance": {"essential": 2.0, "desirable": 1.0},
    # How much of a requirement's value each kind of resume evidence earns.
    "evidence_credit": {"direct": 1.0, "weak": 0.5, "transferable": 0.4, "missing": 0.0},
    # Resume sections whose mention counts as direct evidence (the rest are weak evidence).
    "direct_sections": ["experience", "internships", "projects", "certifications"],
    # Conditions for a score in the top band; otherwise the score is capped at cap_score.
    "top_band": {
        "min_score": 85,
        "min_matched_skills": 4,
        # Experience level is a listing filter (fresher vs experienced roles), not a score gate.
        "require_experience_match": False,
        "require_essential_qualifications": True,
        "cap_score": 84,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_match_config() -> Dict[str, Any]:
    """Defaults, overridden by the JSON file named in ``CAFY_MATCH_CONFIG`` (if any)."""
    path = os.getenv("CAFY_MATCH_CONFIG")
    if not path:
        return copy.deepcopy(DEFAULT_MATCH_CONFIG)
    try:
        with open(path, encoding="utf-8") as fh:
            return _deep_merge(DEFAULT_MATCH_CONFIG, json.load(fh))
    except (OSError, ValueError) as error:
        logger.warning("Ignoring CAFY_MATCH_CONFIG=%s: %s", path, error)
        return copy.deepcopy(DEFAULT_MATCH_CONFIG)


MATCH_CONFIG = load_match_config()

# ---------------------------------------------------------------- job description parsing

_BLOCK_TAG = re.compile(r"(?i)<\s*/?\s*(?:br|p|li|ul|ol|div|h[1-6]|tr|section)\b[^>]*>")
_ANY_TAG = re.compile(r"<[^>]+>")

_DESIRABLE_HEADING = re.compile(
    r"^(?:[-•*]\s*)?(?:desirable|nice[- ]to[- ]haves?|preferred|bonus(?:\s+points)?|"
    r"(?:it(?:'|’)?s?\s+)?(?:great|good)\s+to\s+have|pluses|plus\s+points|advantageous|extra\s+credit|"
    r"would\s+be\s+(?:great|nice|a\s+plus)|ideally)\b",
    re.IGNORECASE,
)
_ESSENTIAL_HEADING = re.compile(
    r"\b(?:essential|requirements?|required|must[- ]haves?|minimum|what\s+(?:we(?:'|’)?re|we\s+are)\s+looking\s+for|"
    r"what\s+we\s+need|what\s+you(?:'|’)?(?:ll)?\s+(?:need|bring|have)|what\s+you\s+(?:need|bring|have)|"
    r"who\s+you\s+are|about\s+you|you\s+(?:will\s+)?have|you(?:'|’)ll\s+have|skills?\s*(?:and|&)\s*experience|"
    r"qualifications?|(?:the|your|relevant)\s+experience|^experience$|skillset|personal\s+attributes|"
    r"ideal\s+candidate|person\s+specification|key\s+skills|future\s+colleague|criteria)\b",
    re.IGNORECASE,
)
_CONTEXT_HEADING = re.compile(
    r"\b(?:responsibilit\w*|what\s+you(?:'|’)?(?:ll)?\s+(?:do|be\s+doing)|about\s+(?:the|this|our)\b|the\s+role|"
    r"role\s+summary|your\s+role|the\s+opportunity|day[- ]to[- ]day|key\s+duties|duties|what\s+we\s+offer|"
    r"benefits|perks|about\s+us|why\s+join|how\s+we\s+work|our\s+culture|job\s+details|job\s+category|"
    r"the\s+team|salary|location|working\s+pattern)\b",
    re.IGNORECASE,
)
_DESIRABLE_LINE = re.compile(
    r"\b(?:desirable|nice[- ]to[- ]have|ideally|preferabl[ey]|preferred|a\s+plus|is\s+a\s+bonus|bonus\s+if|"
    r"advantageous|beneficial|would\s+be\s+(?:great|helpful|useful|an?\s+advantage)|desired|not\s+essential)\b",
    re.IGNORECASE,
)
_ESSENTIAL_LINE = re.compile(
    r"\b(?:essential|must|required|mandatory|minimum|you\s+will\s+need|you(?:'|’)ll\s+need|need\s+to\s+have)\b",
    re.IGNORECASE,
)
_EQUIVALENT = re.compile(r"\bor\s+(?:an?\s+)?equivalent\b|\bequivalent\s+(?:experience|qualification)", re.IGNORECASE)

# Degree levels, highest first. Job text and resume text use slightly different patterns:
# a listing saying "university" or "graduate" is not asking for a degree.
_JOB_DEGREE_LEVELS: List[Tuple[int, str, re.Pattern]] = [
    (5, "PhD", re.compile(r"\b(?:ph\.?\s?d|doctorate|dphil)\b", re.I)),
    (4, "Master's degree", re.compile(r"\b(?:master(?:'|’)?s|msc|m\.sc|mba|meng|mres|postgraduate\s+degree)\b", re.I)),
    (3, "Bachelor's degree", re.compile(r"\b(?:bachelor(?:'|’)?s|bsc|b\.sc|beng|undergraduate\s+degree|degree(?!\s+of\b)|honours\s+degree)\b", re.I)),
    (2, "A-levels or equivalent", re.compile(r"\b(?:a[- ]levels?|btec|level\s+3\s+qualification)\b", re.I)),
    (1, "GCSEs", re.compile(r"\bgcses?\b", re.I)),
]
_RESUME_DEGREE_LEVELS: List[Tuple[int, re.Pattern]] = [
    (5, re.compile(r"\b(?:ph\.?\s?d|doctorate|dphil)\b", re.I)),
    (4, re.compile(r"\b(?:master(?:'|’)?s|msc|m\.sc|m\.?a\b|mba|meng|mres|m\.?tech|postgraduate)\b", re.I)),
    (3, re.compile(r"\b(?:bachelor(?:'|’)?s|bsc|b\.sc|b\.?a\b|beng|b\.?e\b|b\.?tech|b\.?s\b|bcom|llb|undergraduate|degree|hons|honours|university)\b", re.I)),
    (2, re.compile(r"\b(?:a[- ]levels?|btec|level\s+3|higher\s+secondary|hsc|12th)\b", re.I)),
    (1, re.compile(r"\b(?:gcses?|sslc|10th|secondary\s+school)\b", re.I)),
]

# Professional qualifications / registrations UK listings ask for by name.
PROFESSIONAL_QUALIFICATIONS: List[Tuple[str, str]] = [
    ("ACCA", r"\bacca\b"), ("CIMA", r"\bcima\b"), ("ACA / ICAEW", r"\b(?:aca|icaew)\b"),
    ("CFA", r"\bcfa\b"), ("AAT", r"\baat\b"), ("CIPD", r"\bcipd\b"), ("CIPS", r"\bcips\b"),
    ("PRINCE2", r"\bprince\s?2\b"), ("PMP", r"\bpmp\b"), ("CISSP", r"\bcissp\b"), ("CISM", r"\bcism\b"),
    ("CEH", r"\bceh\b"), ("CompTIA Security+", r"\bsecurity\+"), ("ITIL", r"\bitil\b"),
    ("NEBOSH", r"\bnebosh\b"), ("IOSH", r"\biosh\b"), ("CSCS card", r"\bcscs\b"),
    ("QTS", r"\bqts\b|qualified\s+teacher\s+status"), ("PGCE", r"\bpgce\b"),
    ("NMC registration", r"\bnmc\b"), ("HCPC registration", r"\bhcpc\b"), ("GMC registration", r"\bgmc\b"),
    ("GPhC registration", r"\bgphc\b"), ("SIA licence", r"\bsia\s+licen[cs]e"),
    ("Chartered Engineer", r"\bceng\b|chartered\s+engineer"), ("CKA", r"\bcka\b"), ("CKAD", r"\bckad\b"),
    ("AWS certification", r"\baws\s+certified\b|\baws\s+certification"),
    ("Azure certification", r"\baz-\d{3}\b|\bazure\s+certifi\w+"),
    ("Google Cloud certification", r"\b(?:gcp|google\s+cloud)\s+(?:professional|certifi\w+)"),
]
_PRO_QUALS = [(name, re.compile(pattern, re.I)) for name, pattern in PROFESSIONAL_QUALIFICATIONS]

# Application eligibility: shown as checks to confirm, never scored.
ELIGIBILITY_CHECKS: List[Tuple[str, re.Pattern]] = [
    ("Right to work in the UK", re.compile(
        r"right\s+to\s+work|eligib\w*\s+to\s+work|work\s+permit|(?:not|unable\s+to|cannot|can(?:'|’)t)\s+(?:offer|provide)\s+(?:visa\s+)?sponsorship|"
        r"no\s+(?:visa\s+)?sponsorship|sponsorship\s+(?:is\s+)?not\s+(?:available|offered)", re.I)),
    ("Security clearance", re.compile(
        r"\b(?:sc|dv|bpss|nppv\d?|security)\s+clear(?:ance|ed)\b|\bbpss\b|\b(?:sc|dv)\s+cleared\b|eligib\w*\s+for\s+(?:sc|dv|security)\b|"
        r"british\s+(?:citizen|national)|uk\s+national", re.I)),
    ("Driving licence", re.compile(r"driving\s+licen[cs]e|full\s+uk\s+licen[cs]e|own\s+(?:car|vehicle|transport)", re.I)),
    ("DBS check", re.compile(r"\b(?:enhanced\s+)?dbs\b|disclosure\s+and\s+barring", re.I)),
]


def job_lines(description: str) -> List[str]:
    """Plain-text lines of a (possibly HTML) job description."""
    text = _BLOCK_TAG.sub("\n", description or "")
    text = html.unescape(_ANY_TAG.sub(" ", text)).replace("\xa0", " ")
    return [re.sub(r"\s+", " ", line).strip(" \t-•*·") for line in text.split("\n") if line.strip(" \t-•*·")]


def _heading_kind(line: str) -> Optional[str]:
    """``essential`` / ``desirable`` / ``context`` for a heading line, ``None`` for body text."""
    if len(line) > 70 or len(line.split()) > 9 or line.endswith(".") and not line.endswith(":"):
        return None
    head = line.rstrip(":").strip()
    if _DESIRABLE_HEADING.search(head):
        return "desirable"
    if _CONTEXT_HEADING.search(head) and not _ESSENTIAL_HEADING.search(head):
        return "context"
    if _ESSENTIAL_HEADING.search(head):
        return "essential"
    return None


def classify_lines(description: str) -> Tuple[List[Tuple[str, str]], bool]:
    """``[(line, importance)]`` and whether the listing states its requirements explicitly.

    importance is ``essential``, ``desirable`` or ``context`` (duties, company blurb, benefits).
    """
    current = "context"
    structured = False
    out: List[Tuple[str, str]] = []
    for line in job_lines(description):
        kind = _heading_kind(line)
        if kind:
            current = kind
            structured = structured or kind in ("essential", "desirable")
            out.append((line, kind))
            continue
        if _DESIRABLE_LINE.search(line):
            importance = "desirable"
            structured = True
        elif _ESSENTIAL_LINE.search(line):
            importance = "essential"
            structured = True
        else:
            importance = current
        out.append((line, importance))
    return out, structured


_RANK = {"essential": 2, "desirable": 1, "context": 0}

# canonical (lowercase) -> every alias that normalises to it ("apache spark" -> ["spark"]).
_ALIASES_OF: Dict[str, List[str]] = {}
for _alias, _canonical in SKILL_ALIASES.items():
    _ALIASES_OF.setdefault(str(_canonical).lower(), []).append(_alias)


@lru_cache(maxsize=8192)
def skill_forms(skill: str) -> Tuple[str, ...]:
    """The skill and every alias wording of it, so "Spark" in a listing evidences Apache Spark."""
    forms = [skill] + [a for a in _ALIASES_OF.get(_norm(skill), []) if len(a) > 2]
    seen, out = set(), []
    for form in forms:
        if form.lower() not in seen:
            seen.add(form.lower())
            out.append(form)
    return tuple(out)


@lru_cache(maxsize=8192)
def _needles(skill: str) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """(form, substrings one of which any match must contain) - a cheap pre-check.

    ``phrase_in_lowered`` also matches a form's curated synonyms, so their wording counts too.
    """
    def first_literal(text: str) -> str:
        literals = _phrase_literals(text) if len(text) > 3 else (text.lower(),)
        return literals[0] if literals else ""

    out = []
    for form in skill_forms(skill):
        wordings = [form] + list(SYNONYMS.get(form.lower(), []))
        out.append((form, tuple(first_literal(w) for w in wordings)))
    return tuple(out)


@lru_cache(maxsize=8192)
def _exact_pattern(skill: str) -> "re.Pattern[str]":
    forms = list(skill_forms(skill)) + list(SYNONYMS.get(skill.lower(), []))
    alternatives = "|".join(re.escape(f.lower()) for f in sorted(forms, key=len, reverse=True))
    # Whole word/phrase; a plain plural is allowed ("dashboards" for Dashboard), other word
    # forms are not ("machine" is not Machining, "value" is not Valuation).
    return re.compile(r"(?<![a-z0-9])(?:" + alternatives + r")(?:s|es)?(?![a-z0-9])")


def _exact_in(skill: str, text: str) -> bool:
    """The skill, an alias or a curated synonym appears as a whole word/phrase in ``text``."""
    return bool(_exact_pattern(skill).search(str(text or "").lower()))


def _mentions(skill: str, lowered_padded: str) -> bool:
    return any(any(n in lowered_padded for n in needles) and phrase_in_lowered(form, lowered_padded)
               for form, needles in _needles(skill))


def _importance_in(skill: str, lines: List[Tuple[str, str]], title: str, structured: bool,
                   loose: bool = False) -> Tuple[str, str]:
    """Strongest importance of any line naming ``skill`` (a skill in the job title is essential).

    Skills found only in duties/blurb lines are desirable when the listing states its own
    requirements, essential when it does not (nothing tells them apart).
    """
    def has(text: str) -> bool:
        return text_has_skill(skill, text) if loose else _mentions(skill, f" {text.lower()} ")

    best, where = None, ""
    for raw, importance in lines:
        if importance == "context" and best is not None:
            continue  # a context line can never raise the importance already found
        if (best is None or _RANK[importance] > _RANK[best]) and has(raw):
            best, where = importance, raw
            if best == "essential":
                break
    if has(title):
        best, where = "essential", where or title
    if best is None or best == "context":
        best = "desirable" if structured else "essential"
    return best, where


@lru_cache(maxsize=8192)
def _requirements_cached(title: str, description: str, stored_skills: Tuple[str, ...]) -> Dict[str, Any]:
    job = {"title": title, "description": description, "extracted_skills": list(stored_skills)}
    lines, structured = classify_lines(description)

    skills: List[Dict[str, Any]] = []
    general: List[str] = []
    seen: set = set()
    listing_text = f"{title} " + " ".join(line for line, _ in lines)
    for skill in _job_skills(job):
        key = _norm(skill)
        if not key or key in seen:
            continue
        seen.add(key)
        if skill.casefold() in WEAK_MATCH_SKILLS:
            general.append(skill)  # soft skills a resume cannot evidence: listed, not scored
            continue
        if not _exact_in(skill, listing_text):
            # Found only through word-stem tolerance ("Machining" from "machine learning",
            # "Valuation" from "values") - also in skills stored at scrape time by the same
            # extractor: not something the employer asked for.
            continue
        best, where = _importance_in(skill, lines, title, structured)
        skills.append({"name": skill, "key": key, "importance": best, "job_text": where[:240]})

    # Experience: the first stated years requirement, with the importance of its line.
    min_years, max_years = _job_experience_requirement(job)
    exp_importance = "essential"
    exp_text = ""
    if min_years is not None:
        for raw, importance in lines:
            if re.search(r"\d+\s*\+?\s*(?:-|–|to)?\s*\d*\s*(?:years?|yrs?)", raw, re.I) and "experience" in raw.lower():
                exp_text = raw[:240]
                exp_importance = "desirable" if importance == "desirable" else "essential"
                break

    # Qualifications: degree level and named professional qualifications.
    qualifications: List[Dict[str, Any]] = []
    degree_req: Optional[Dict[str, Any]] = None
    for raw, importance in lines:
        # In a listing with requirement sections, a degree named in the company blurb or the
        # duties is not a requirement. Without sections, any line may state one.
        if structured and importance == "context" and not _ESSENTIAL_LINE.search(raw):
            continue
        levels = [(lvl, label) for lvl, label, pat in _JOB_DEGREE_LEVELS if pat.search(raw)]
        if levels:
            level, label = min(levels)
            imp = "desirable" if importance == "desirable" else "essential"
            candidate = {"type": "degree", "name": label, "level": level, "importance": imp,
                         "equivalent_accepted": bool(_EQUIVALENT.search(raw)), "job_text": raw[:240]}
            if degree_req is None or _RANK[imp] > _RANK[degree_req["importance"]]:
                degree_req = candidate
        for name, pattern in _PRO_QUALS:
            if pattern.search(raw) and not any(q["name"] == name for q in qualifications):
                qualifications.append({"type": "professional", "name": name,
                                       "importance": "desirable" if importance == "desirable" else "essential",
                                       "equivalent_accepted": bool(_EQUIVALENT.search(raw)),
                                       "job_text": raw[:240]})
    if degree_req:
        qualifications.insert(0, degree_req)

    eligibility = []
    for name, pattern in ELIGIBILITY_CHECKS:
        line = next((raw for raw, _ in lines if pattern.search(raw)), None)
        if line:
            eligibility.append({"check": name, "status": "to_confirm", "job_text": line[:240]})

    return {
        "structured": structured,
        "lines": tuple(lines),
        "skills": skills,
        "general_skills": general,
        "experience": {"min_years": min_years, "max_years": max_years, "importance": exp_importance,
                       "job_text": exp_text, "job_level": job_level(job)},
        "qualifications": qualifications,
        "eligibility": eligibility,
    }


def extract_requirements(job: Dict[str, Any]) -> Dict[str, Any]:
    """Essential/desirable skills, experience, qualifications and eligibility items of a job."""
    return _requirements_cached(
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        tuple(str(s) for s in (job.get("extracted_skills") or [])),
    )


# ---------------------------------------------------------------- resume side

def candidate_years(profile: Dict[str, Any]) -> int:
    """Full-time years the profile states (seniority words used only when none is stated)."""
    raw = profile.get("years_of_experience")
    try:
        return max(0, int(raw)) if raw is not None else _years_from_seniority(profile)
    except (TypeError, ValueError):
        return 0


def _years_from_seniority(profile: Dict[str, Any]) -> int:
    seniority = str(profile.get("seniority_level") or "").casefold()
    if "principal" in seniority or "lead" in seniority:
        return 7
    if "senior" in seniority:
        return 5
    return 0


def _entry_label(entry: Dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("name") or entry.get("degree") or "").strip()
    org = str(entry.get("organization") or entry.get("company") or entry.get("institution") or entry.get("issuer") or "").strip()
    return " at ".join(p for p in (title, org) if p) or "entry"


class ResumeContext:
    """A profile broken into quotable units, built once and reused for every job."""

    def __init__(self, profile: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        self.profile = profile or {}
        self.config = config or MATCH_CONFIG
        self.years = candidate_years(self.profile)
        self.level = self.profile.get("career_level") or ("experienced" if self.years >= 1 else "fresher")
        self.skill_keys = {_norm(s) for s in (self.profile.get("skills") or []) if str(s).strip()}
        self.units: List[Tuple[str, str, str]] = []  # (section, source label, text)
        summary = str(self.profile.get("summary") or self.profile.get("professional_summary") or "").strip()
        for sentence in re.split(r"(?<=[.!?])\s+", summary):
            if sentence.strip():
                self.units.append(("summary", "Professional summary", sentence.strip()))
        for section in ("experience", "internships", "projects", "education", "certifications"):
            for entry in self.profile.get(section) or []:
                if isinstance(entry, str):
                    self.units.append((section, entry[:80], entry))
                    continue
                if not isinstance(entry, dict):
                    continue
                label = _entry_label(entry)
                head = " ".join(str(entry.get(k) or "") for k in ("title", "name", "degree", "field", "technologies")
                                if not isinstance(entry.get(k), list)).strip()
                techs = entry.get("technologies")
                if isinstance(techs, list):
                    head = f"{head} {' '.join(map(str, techs))}".strip()
                if head:
                    self.units.append((section, label, head))
                for part in re.split(r"[\n•]+|(?<=[.!?])\s+", str(entry.get("description") or "")):
                    if part.strip():
                        self.units.append((section, label, part.strip()))
                for bullet in entry.get("bullets") or []:
                    if str(bullet).strip():
                        self.units.append((section, label, str(bullet).strip()))
        self._lowered = [(sec, label, text, f" {text.lower()} ") for sec, label, text in self.units]
        all_text = " ".join(t for _, _, t in self.units) + " " + " ".join(map(str, self.profile.get("skills") or []))
        self.found_keys = self.skill_keys | {_norm(s) for s in _skill_extractor.extract_skills(all_text)}
        self.degree_level = self._degree_level()
        self.qual_text = " ".join(t for sec, _, t in self.units if sec in ("certifications", "education", "summary")) \
            + " " + " ".join(map(str, self.profile.get("skills") or []))
        self._evidence_cache: Dict[str, List[Dict[str, str]]] = {}

    def _degree_level(self) -> int:
        level = 0
        for entry in self.profile.get("education") or []:
            text = entry if isinstance(entry, str) else " ".join(
                str(entry.get(k) or "") for k in ("degree", "title", "name", "institution", "organization", "field"))
            for lvl, pattern in _RESUME_DEGREE_LEVELS:
                if pattern.search(text):
                    level = max(level, lvl)
                    break
        return level

    def evidence_for(self, skill: str) -> List[Dict[str, str]]:
        """Every resume place that shows ``skill``, quoting the exact line."""
        key = _norm(skill)
        if key in self._evidence_cache:
            return self._evidence_cache[key]
        found: List[Dict[str, str]] = []
        if key in self.skill_keys:
            found.append({"section": "skills", "source": "Skills list", "text": skill})
        for section, label, text, lowered in self._lowered:
            if _mentions(skill, lowered):
                found.append({"section": section, "source": label, "text": text[:240]})
        self._evidence_cache[key] = found
        return found

    def transferable_for(self, skill: str) -> Optional[Dict[str, str]]:
        key = _norm(skill)
        for cluster, members in TRANSFERABLE_CLUSTERS.items():
            if key in members:
                alt = next((k for k in sorted(self.found_keys) if k in members and k != key), None)
                if alt:
                    original = next((s for s in self.profile.get("skills") or [] if _norm(s) == alt), alt)
                    return {"candidate_skill": str(original), "cluster": cluster}
        return None


# ---------------------------------------------------------------- scoring

def _check_experience(ctx: ResumeContext, job: Dict[str, Any], exp: Dict[str, Any]) -> Dict[str, Any]:
    level_ok = _experience_level_matches(job, ctx.years) and not (
        ctx.level == "fresher" and exp["job_level"] == "experienced")
    min_years, max_years = exp["min_years"], exp["max_years"]
    years_ok = min_years is None or ctx.years >= min_years or exp["importance"] == "desirable"
    passed = bool(level_ok and years_ok)
    if min_years is not None:
        wanted = f"{min_years}–{max_years} years" if max_years is not None else f"{min_years}+ years"
    else:
        wanted = {"fresher": "entry level", "experienced": "experienced hire"}.get(exp["job_level"], "any level")
    return {
        "passed": passed,
        "candidate_level": ctx.level,
        "candidate_years": ctx.years,
        "job_level": exp["job_level"],
        "required": wanted,
        "importance": exp["importance"],
        "job_text": exp["job_text"],
        "detail": (f"You are {'an' if ctx.level == 'experienced' else 'a'} {ctx.level} candidate "
                   f"({ctx.years} full-time years); the listing asks for {wanted}."),
    }


def _check_qualifications(ctx: ResumeContext, quals: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = []
    for q in quals:
        if q["type"] == "degree":
            met = ctx.degree_level >= q["level"]
            how = "Your education meets this level." if met else "No education entry at this level."
            if not met and q["equivalent_accepted"] and ctx.years >= 2:
                met, how = True, "Equivalent experience accepted and you have full-time experience."
        else:
            pattern = dict(_PRO_QUALS)[q["name"]]
            met = bool(pattern.search(ctx.qual_text))
            how = "Listed on your resume." if met else "Not found on your resume."
        items.append({**q, "met": met, "detail": how})
    essential_unmet = [i["name"] for i in items if i["importance"] == "essential" and not i["met"]]
    return {"passed": not essential_unmet, "items": items, "essential_unmet": essential_unmet}


def score_job(profile: Dict[str, Any], job: Dict[str, Any], ctx: Optional[ResumeContext] = None,
              config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Requirement-level match of one resume to one job, with the full breakdown."""
    config = config or MATCH_CONFIG
    ctx = ctx or ResumeContext(profile, config)
    reqs = extract_requirements(job)
    importance_w = config["importance"]
    credit_of = config["evidence_credit"]
    direct_sections = set(config["direct_sections"])

    # Resume skills the listing words differently ("care of patients" for Patient Care) are
    # requirements of this job too; the catalog scan above only finds catalog wordings.
    skill_reqs = list(reqs["skills"])
    known = {r["key"] for r in skill_reqs} | {_norm(s) for s in reqs["general_skills"]}
    listing = f"{job.get('title') or ''} " + " ".join(line for line, _ in reqs["lines"])
    listing_stems = list(cached_stems(listing))
    for skill in ctx.profile.get("skills") or []:
        key = _norm(skill)
        if not key or key in known or str(skill).casefold() in WEAK_MATCH_SKILLS:
            continue
        known.add(key)
        if text_has_skill(str(skill), listing, listing_stems):
            importance, where = _importance_in(str(skill), list(reqs["lines"]), str(job.get("title") or ""),
                                               reqs["structured"], loose=True)
            skill_reqs.append({"name": str(skill), "key": key, "importance": importance, "job_text": where[:240]})

    rows: List[Dict[str, Any]] = []
    earned = possible = 0.0
    for req in skill_reqs:
        evidence = ctx.evidence_for(req["name"])
        transfer = None
        if any(e["section"] in direct_sections for e in evidence):
            kind = "direct"
        elif evidence:
            kind = "weak"
        else:
            transfer = ctx.transferable_for(req["name"])
            kind = "transferable" if transfer else "missing"
        weight = float(importance_w[req["importance"]])
        credit = float(credit_of[kind])
        earned += weight * credit
        possible += weight
        rows.append({
            "type": "skill", "name": req["name"], "importance": req["importance"], "weight": weight,
            "evidence_type": kind, "credit": credit, "points": round(weight * credit, 2),
            # The skill's own wording (or an alias/synonym) is on the resume - not just a word form
            # ("account records" is a match for scoring tolerance, never proof of "Accounting").
            "exact_evidence": any(_exact_in(req["name"], e["text"]) for e in evidence),
            "job_text": req["job_text"],
            # Direct evidence first, so the strongest proof is shown first.
            "resume_evidence": sorted(evidence, key=lambda e: e["section"] not in direct_sections)[:4],
            "transferable_from": transfer,
        })

    raw_score = 100.0 * earned / possible if possible else 0.0
    matched = [r["name"] for r in rows if r["evidence_type"] in ("direct", "weak")]
    experience = _check_experience(ctx, job, reqs["experience"])
    qualifications = _check_qualifications(ctx, reqs["qualifications"])

    band = config["top_band"]
    skills_check = {"passed": len(matched) >= band["min_matched_skills"], "matched": len(matched),
                    "required": band["min_matched_skills"]}
    cap_reasons = []
    if not skills_check["passed"]:
        cap_reasons.append(f"Only {len(matched)} of the job's skills matched; {band['min_matched_skills']}+ needed.")
    if band["require_experience_match"] and not experience["passed"]:
        cap_reasons.append(f"Experience level does not match: {experience['detail']}")
    if band["require_essential_qualifications"] and not qualifications["passed"]:
        cap_reasons.append("Essential qualification not met: " + ", ".join(qualifications["essential_unmet"]) + ".")
    score = int(round(raw_score))
    capped = bool(cap_reasons) and score >= band["min_score"]
    if capped:
        score = band["cap_score"]
    if not rows:
        cap_reasons.append("No skill requirements could be read from this listing.")

    def summary(importance: str) -> Dict[str, Any]:
        part = [r for r in rows if r["importance"] == importance]
        return {
            "count": len(part),
            "points": round(sum(r["points"] for r in part), 2),
            "possible": round(sum(r["weight"] for r in part), 2),
            "direct": sum(r["evidence_type"] == "direct" for r in part),
            "weak": sum(r["evidence_type"] == "weak" for r in part),
            "transferable": sum(r["evidence_type"] == "transferable" for r in part),
            "missing": sum(r["evidence_type"] == "missing" for r in part),
        }

    return {
        "method": METHOD,
        "score": max(0, min(100, score)),
        "raw_score": round(raw_score, 1),
        "capped": capped,
        "top_band_eligible": not cap_reasons,
        "cap_reasons": cap_reasons,
        "listing_structured": reqs["structured"],
        "essential": summary("essential"),
        "desirable": summary("desirable"),
        "requirements": rows,
        "matched_skills": matched,
        "missing_skills": [r["name"] for r in rows if r["evidence_type"] == "missing"],
        "transferable_skills": [
            {"job_skill": r["name"], **r["transferable_from"]} for r in rows if r["evidence_type"] == "transferable"
        ],
        "checks": {"skills": skills_check, "experience": experience, "qualifications": qualifications},
        "general_skills_not_scored": list(reqs["general_skills"]),
        "eligibility": reqs["eligibility"],
        "visa_sponsorship": "Assessed separately (sponsor register); not part of this score.",
        "weights": {"importance": dict(importance_w), "evidence_credit": dict(credit_of)},
    }
