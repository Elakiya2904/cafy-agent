"""Pre-generation Job Match analysis for Cafy Agent.

Scores a candidate profile against one specific job description, section by
section, before a tailored resume is generated. This is deliberately separate
from Profile Completeness (profile_strength_service), which measures how
filled-in a profile is regardless of any job:

- Profile Completeness: "Is my profile well-formed?" (job independent)
- Job Match Score:      "How well does my profile evidence what THIS job asks for?"

Section weights for the Job Match Score:
    Skills 35, Work Experience 30, Professional Summary 10,
    Education 10, Projects 10, Certifications 5

Every section score is a graded weighted sum of real sub-criteria (see
``_graded``). 100 is only reachable when every applicable criterion is fully
met. Sections (and criteria) the job does not ask about are marked
"not applicable" (score ``None``) and are excluded from the overall score
instead of being given an assumed number.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .profile_strength_service import METRIC_PATTERN, evaluate_profile_strength
from .recommendation_service import _job_experience_requirement
from .resume_service import ResumeService, SKILL_ALIASES

SECTION_WEIGHTS = {
    "skills": 35,
    "experience": 30,
    "summary": 10,
    "education": 10,
    "projects": 10,
    "certifications": 5,
}

SECTION_NAMES = {
    "summary": "Professional Summary",
    "skills": "Skills",
    "experience": "Work Experience",
    "education": "Education",
    "projects": "Projects",
    "certifications": "Certifications",
}

DEGREE_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:bachelor'?s?|master'?s?|ph\.?d|degree|b\.?sc|m\.?sc|b\.?s\.?|m\.?s\.?|b\.?tech|m\.?tech|graduate of)\b",
    re.IGNORECASE,
)
RELEVANT_FIELD_PATTERN = re.compile(
    r"\b(?:computer|software|engineering|information|data|mathematics|maths|statistics|physics|science|technology|electronics|electrical|artificial intelligence|machine learning)\b",
    re.IGNORECASE,
)
CERT_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:certified|certification|certifications|certificate|cka|ckad|cissp|pmp|comptia|aws certified|azure certified|gcp certified)\b",
    re.IGNORECASE,
)
YEARS_PATTERN = re.compile(r"\b\d+\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
GENERIC_CERT_TERMS = {"certified", "certification", "certifications", "certificate"}
TITLE_STOPWORDS = {
    "senior", "junior", "lead", "staff", "principal", "head", "of", "and", "the", "i", "ii", "iii",
    "remote", "hybrid", "contract", "uk", "london", "-", "&", "/", "intern", "graduate", "associate",
}

# Summary length is graded against this ideal character range.
SUMMARY_IDEAL_MIN = 250
SUMMARY_IDEAL_MAX = 600
# Bullets per role needed for full "depth" credit.
TARGET_BULLETS_PER_ROLE = 2

_skill_extractor = ResumeService()

Criterion = Tuple[float, Optional[float]]


def _norm(skill: Any) -> str:
    cleaned = str(skill or "").strip().lower()
    return SKILL_ALIASES.get(cleaned, str(skill or "").strip()).lower()


def _entry_text(entries: Any, fields: Iterable[str]) -> str:
    if not isinstance(entries, list):
        return ""
    parts: List[str] = []
    for entry in entries:
        if isinstance(entry, str):
            parts.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        for field in fields:
            value = entry.get(field)
            if isinstance(value, list):
                parts.extend(str(v) for v in value)
            elif value:
                parts.append(str(value))
    return " ".join(parts)


def _entry_bullets(entry: Any) -> List[str]:
    """Bullet lines for one experience/project entry (falls back to description sentences)."""
    if isinstance(entry, str):
        return [entry.strip()] if entry.strip() else []
    if not isinstance(entry, dict):
        return []
    bullets = entry.get("bullets")
    if isinstance(bullets, list):
        lines = [str(b).strip() for b in bullets if str(b).strip()]
        if lines:
            return lines
    description = str(entry.get("description") or "").strip()
    if not description:
        return []
    parts = re.split(r"[\n•]+|(?<=[.!?])\s+", description)
    return [p.strip(" -*") for p in parts if p.strip(" -*")]


def _skills_in_text(job_skills: List[str], text: str) -> List[str]:
    """Return the job skills that are evidenced anywhere in ``text``."""
    if not text:
        return []
    lower = f" {text.lower()} "
    found_norm = {_norm(s) for s in _skill_extractor.extract_skills(text)}
    evidenced = []
    for skill in job_skills:
        key = _norm(skill)
        if key in found_norm or re.search(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])", lower):
            evidenced.append(skill)
    return evidenced


def _title_keywords(title: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z+#.]*", title or "")
    seen: List[str] = []
    for t in tokens:
        low = t.lower()
        if low not in TITLE_STOPWORDS and len(low) > 2 and low not in seen:
            seen.append(low)
    return seen


def _ratio(part: float, whole: float) -> Optional[float]:
    """``part / whole`` clamped to [0, 1]; ``None`` when there is nothing to measure against."""
    if not whole:
        return None
    return max(0.0, min(1.0, part / whole))


def _graded(criteria: Sequence[Criterion]) -> Optional[int]:
    """Weighted sum of ``(weight, fraction)`` criteria, scaled to 0-100.

    A fraction of ``None`` means the criterion does not apply to this job and is
    dropped (remaining weights are renormalised) - nothing is assumed. A score of
    100 therefore requires every applicable criterion to be fully met.
    """
    applicable = [(w, max(0.0, min(1.0, f))) for w, f in criteria if f is not None]
    total = sum(w for w, _ in applicable)
    if not total:
        return None
    return int(round(100 * sum(w * f for w, f in applicable) / total))


def _status_for(score: Optional[int]) -> str:
    if score is None:
        return "not_applicable"
    if score >= 75:
        return "strong"
    if score >= 45:
        return "partial"
    return "weak"


def _match_tier(score: int) -> str:
    if score >= 80:
        return "Strong Match"
    if score >= 65:
        return "Good Match"
    if score >= 45:
        return "Partial Match"
    return "Low Match"


def _job_skills(job: Dict[str, Any]) -> List[str]:
    skills = job.get("extracted_skills") or []
    if not skills:
        skills = _skill_extractor.extract_skills(f"{job.get('title', '')} {job.get('description', '')}")
    seen: Set[str] = set()
    ordered = []
    for skill in skills:
        key = _norm(skill)
        if key and key not in seen:
            seen.add(key)
            ordered.append(str(skill))
    return ordered


def _summary_length_fraction(length: int) -> float:
    """1.0 inside the ideal range; proportionally less when shorter or much longer."""
    if length <= 0:
        return 0.0
    if length < SUMMARY_IDEAL_MIN:
        return length / SUMMARY_IDEAL_MIN
    if length <= SUMMARY_IDEAL_MAX:
        return 1.0
    # Over-long summaries lose credit linearly, reaching 0 at twice the ideal maximum.
    return max(0.0, 1 - (length - SUMMARY_IDEAL_MAX) / SUMMARY_IDEAL_MAX)


def analyze_profile_for_job(profile: Optional[Dict[str, Any]], job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Score ``profile`` against ``job`` and return section scores, gaps and suggestions."""
    profile = profile or {}
    job = job or {}

    job_title = str(job.get("title") or "")
    job_description = str(job.get("description") or "")
    job_skills = _job_skills(job)
    job_skill_count = len(job_skills)
    title_words = _title_keywords(job_title)

    profile_skills = [str(s) for s in (profile.get("skills") or []) if str(s).strip()]
    profile_skill_keys = {_norm(s) for s in profile_skills}

    summary = str(profile.get("summary") or "").strip()
    experience = [e for e in (profile.get("experience") or []) if isinstance(e, (dict, str))]
    education = [e for e in (profile.get("education") or []) if isinstance(e, (dict, str))]
    projects = [p for p in (profile.get("projects") or []) if isinstance(p, (dict, str))]
    certifications = [c for c in (profile.get("certifications") or []) if isinstance(c, (dict, str))]

    experience_text = _entry_text(experience, ("title", "company", "organization", "description", "bullets"))
    project_text = _entry_text(projects, ("title", "name", "organization", "description", "bullets", "technologies"))
    education_text = _entry_text(education, ("degree", "title", "field", "institution", "organization", "description", "bullets"))
    cert_text = _entry_text(certifications, ("name", "title", "issuer"))

    missing_information: List[Dict[str, str]] = []
    suggestions: List[Dict[str, str]] = []

    def suggest(section: str, priority: str, text: str) -> None:
        suggestions.append({"section": section, "priority": priority, "text": text})

    def missing(section: str, text: str) -> None:
        missing_information.append({"section": section, "text": text})

    # --- Skills -----------------------------------------------------------
    # 80: coverage of the job's skills in the Skills list
    # 20: share of those listed skills that are also evidenced in experience/project text
    matched_skills = [s for s in job_skills if _norm(s) in profile_skill_keys]
    missing_skills = [s for s in job_skills if _norm(s) not in profile_skill_keys]
    evidence_text = f"{summary} {experience_text} {project_text}"
    evidenced_elsewhere = _skills_in_text(missing_skills, evidence_text)
    unevidenced = [s for s in missing_skills if s not in evidenced_elsewhere]
    work_evidence_text = f"{experience_text} {project_text}"
    matched_with_evidence = _skills_in_text(matched_skills, work_evidence_text)
    matched_without_evidence = [s for s in matched_skills if s not in matched_with_evidence]

    if job_skill_count:
        skills_score = _graded([
            (80, len(matched_skills) / job_skill_count),
            (20, len(matched_with_evidence) / len(matched_skills) if matched_skills else 0.0),
        ])
    else:
        skills_score = None  # the job lists no skills: nothing to measure
    if not profile_skills:
        missing("skills", "No skills listed in your profile.")
    if evidenced_elsewhere:
        suggest(
            "skills", "high",
            f"Add {', '.join(evidenced_elsewhere[:5])} to your Skills section - your experience or projects already show them.",
        )
    if unevidenced:
        suggest(
            "skills", "medium",
            f"The job asks for {', '.join(unevidenced[:5])}. Add them only if you genuinely have this experience.",
        )
    if matched_without_evidence:
        suggest(
            "skills", "medium",
            f"Back up {', '.join(matched_without_evidence[:4])} with a bullet in your experience or projects showing where you used it.",
        )

    # --- Work Experience ---------------------------------------------------
    # 30: share of job skills evidenced in experience text
    # 15: role-title relevance (share of target-title keywords found in past titles)
    # 20: share of bullets containing a measurable result
    # 20: years requirement met (proportional when short; n/a if the job states none)
    # 15: bullet depth (average bullets per role vs target of 2)
    min_years, max_years = _job_experience_requirement(job)
    try:
        candidate_years = int(profile.get("years_of_experience") or 0)
    except (TypeError, ValueError):
        candidate_years = 0
    exp_evidenced = _skills_in_text(job_skills, experience_text)
    exp_bullets = [_entry_bullets(e) for e in experience]
    all_exp_bullets = [b for bullets in exp_bullets for b in bullets]
    metric_bullets = [b for b in all_exp_bullets if METRIC_PATTERN.search(b)]
    role_titles = " ".join(str(e.get("title") or "") for e in experience if isinstance(e, dict)).lower()
    title_hits = [w for w in title_words if w in role_titles]
    avg_bullets = (len(all_exp_bullets) / len(experience)) if experience else 0.0

    if experience:
        exp_score = _graded([
            (30, _ratio(len(exp_evidenced), job_skill_count)),
            (15, _ratio(len(title_hits), len(title_words))),
            (20, len(metric_bullets) / len(all_exp_bullets) if all_exp_bullets else 0.0),
            (20, _ratio(candidate_years, min_years) if min_years else None),
            (15, min(1.0, avg_bullets / TARGET_BULLETS_PER_ROLE)),
        ])
        if exp_score is None:
            exp_score = 0
        if title_words and len(title_hits) < len(title_words):
            suggest("experience", "medium", f"Highlight the parts of your past roles closest to a {job_title or 'this'} position.")
        if not all_exp_bullets or len(metric_bullets) < len(all_exp_bullets):
            suggest(
                "experience", "high",
                f"{len(metric_bullets)} of {len(all_exp_bullets)} experience bullets show a measurable result - "
                "add outcomes where you have them (e.g. 'cut deployment time by 40%').",
            )
        if avg_bullets < TARGET_BULLETS_PER_ROLE:
            suggest("experience", "medium", f"Give each role at least {TARGET_BULLETS_PER_ROLE} bullets describing what you did.")
        if min_years and candidate_years < min_years:
            missing("experience", f"The listing asks for {min_years}+ years; your profile shows {candidate_years}.")
        missing_in_exp = [s for s in matched_skills if s not in exp_evidenced]
        if missing_in_exp:
            suggest(
                "experience", "medium",
                f"Show where you used {', '.join(missing_in_exp[:4])} in your work experience bullets.",
            )
    else:
        exp_score = 0
        missing("experience", "No work experience entries in your profile.")
        suggest("experience", "high", "Add your work history with company, dates and outcome-focused bullets.")

    # --- Professional Summary ---------------------------------------------
    # 25: length quality (ideal 250-600 chars, proportional otherwise)
    # 20: mentions the target role (share of title keywords)
    # 40: share of the job's top 6 skills mentioned
    # 15: concrete experience signal (years or a metric)
    summary_keywords: List[str] = []
    top_skills = job_skills[:6]
    if summary:
        summary_lower = summary.lower()
        summary_title_hits = [w for w in title_words if w in summary_lower]
        summary_keywords = _skills_in_text(top_skills, summary)
        has_signal = bool(YEARS_PATTERN.search(summary) or METRIC_PATTERN.search(summary))
        summary_score = _graded([
            (25, _summary_length_fraction(len(summary))),
            (20, _ratio(len(summary_title_hits), len(title_words))),
            (40, _ratio(len(summary_keywords), len(top_skills))),
            (15, 1.0 if has_signal else 0.0),
        ]) or 0
        if len(summary) < SUMMARY_IDEAL_MIN:
            suggest("summary", "medium", f"Expand your summary to 2-4 sentences (about {SUMMARY_IDEAL_MIN}-{SUMMARY_IDEAL_MAX} characters).")
        elif len(summary) > SUMMARY_IDEAL_MAX:
            suggest("summary", "low", f"Tighten your summary to under {SUMMARY_IDEAL_MAX} characters.")
        if title_words and not summary_title_hits:
            suggest("summary", "medium", f"Mention your fit for {job_title or 'the target role'} in your summary.")
        if not has_signal:
            suggest("summary", "low", "State your years of experience or a headline result in your summary.")
        if top_skills and len(summary_keywords) < len(top_skills):
            candidates = [s for s in top_skills if _norm(s) in profile_skill_keys and s not in summary_keywords]
            if candidates:
                suggest("summary", "medium", f"Work {', '.join(candidates[:3])} into your summary - they are key for this role.")
    else:
        summary_score = 0
        missing("summary", "No professional summary.")
        suggest("summary", "high", "Write a 2-3 sentence summary aimed at this role.")

    # --- Education --------------------------------------------------------
    # 25 degree present, 15 institution present, 10 dates present,
    # 25 field relevance (overlap with the fields the job names; n/a if none named),
    # 25 degree requirement met (n/a if the job does not mention a degree)
    degree_required = bool(DEGREE_REQUIREMENT_PATTERN.search(job_description))
    job_fields = {m.group(0).lower() for m in RELEVANT_FIELD_PATTERN.finditer(job_description)}
    edu_fields = {m.group(0).lower() for m in RELEVANT_FIELD_PATTERN.finditer(education_text)}
    if education:
        first = education[0] if isinstance(education[0], dict) else {"degree": education[0]}
        degree_text = str(first.get("degree") or first.get("title") or "").strip()
        has_degree = bool(degree_text)
        has_institution = bool(first.get("institution") or first.get("organization"))
        has_dates = bool(first.get("dates") or first.get("end_date") or first.get("year") or first.get("graduation_year"))
        field_fraction = _ratio(len(job_fields & edu_fields), len(job_fields))
        edu_score = _graded([
            (25, 1.0 if has_degree else 0.0),
            (15, 1.0 if has_institution else 0.0),
            (10, 1.0 if has_dates else 0.0),
            (25, field_fraction),
            (25, (1.0 if has_degree else 0.0) if degree_required else None),
        ]) or 0
        if not has_degree:
            missing("education", "Degree title is missing.")
        if not has_institution:
            missing("education", "Institution name is missing.")
        if not has_dates:
            missing("education", "Graduation dates are missing.")
        if field_fraction is not None and field_fraction < 1:
            suggest("education", "low", "Clarify how your field of study relates to this role (relevant modules or thesis).")
    elif degree_required:
        edu_score = 0
        missing("education", "The job mentions a degree but your profile has no education entry.")
        suggest("education", "high", "Add your degree, institution and graduation year.")
    else:
        edu_score = None  # job does not ask for a degree and the profile lists none
        suggest("education", "low", "Add your education to complete your profile.")

    # --- Projects -----------------------------------------------------------
    # 50: share of ALL job skills evidenced in project text
    # 30: share of projects with a description or bullets
    # 20: share of projects showing a measurable result
    proj_evidenced = _skills_in_text(job_skills, project_text)
    if projects:
        detailed = [p for p in projects if _entry_bullets(p)]
        with_metric = [p for p in projects if METRIC_PATTERN.search(_entry_text([p], ("description", "bullets")))]
        proj_score = _graded([
            (50, _ratio(len(proj_evidenced), job_skill_count)),
            (30, len(detailed) / len(projects)),
            (20, len(with_metric) / len(projects)),
        ]) or 0
        if job_skill_count and len(proj_evidenced) < job_skill_count:
            suggest("projects", "medium", "Describe the technologies used in your projects, prioritising those in this job.")
        if len(detailed) < len(projects):
            suggest("projects", "medium", "Add a short description or bullets to every project.")
        if len(with_metric) < len(projects):
            suggest("projects", "low", "Add a measurable result to your projects (users, latency, % improvement).")
    else:
        proj_score = 0
        missing("projects", "No projects listed.")
        suggest("projects", "medium", "Add 1-2 projects that use the technologies this job asks for.")

    # --- Certifications -----------------------------------------------------
    # n/a unless the job mentions certifications. Otherwise:
    # 25 any certification listed, 60 share of named certifications matched
    # (or relevance to job skills when none are named), 15 share with an issuer.
    job_cert_terms = {m.group(0).lower() for m in CERT_REQUIREMENT_PATTERN.finditer(job_description)}
    certs_required = bool(job_cert_terms)
    named_certs = sorted(job_cert_terms - GENERIC_CERT_TERMS)
    if not certs_required:
        certs_score = None
    elif not certifications:
        certs_score = 0
        missing("certifications", "The job mentions certifications but none are listed.")
        suggest("certifications", "medium", "Add relevant certifications (with issuer and date) if you hold any.")
    else:
        cert_lower = cert_text.lower()
        if named_certs:
            match_fraction = len([t for t in named_certs if t in cert_lower]) / len(named_certs)
        else:
            match_fraction = 1.0 if _skills_in_text(job_skills, cert_text) else (0.0 if job_skills else None)
        with_issuer = [c for c in certifications if isinstance(c, dict) and c.get("issuer")]
        certs_score = _graded([
            (25, 1.0),
            (60, match_fraction),
            (15, len(with_issuer) / len(certifications)),
        ])
        if match_fraction is not None and match_fraction < 1:
            suggest("certifications", "low", "The job names specific certifications; list any you hold or are pursuing.")
        if len(with_issuer) < len(certifications):
            suggest("certifications", "low", "Add the issuer for each certification.")

    # --- Gap analysis -------------------------------------------------------
    # "missing_from_profile": a skill the job wants that is not in the Skills list
    # (it may still be evidenced in experience/projects).
    # "missing_qualification": a requirement the profile does not satisfy.
    gaps: List[Dict[str, Any]] = []
    for skill in missing_skills:
        gaps.append({
            "type": "missing_from_profile",
            "section": "skills",
            "title": skill,
            "detail": "Used in your experience but not listed in your skills"
            if skill in evidenced_elsewhere else "Skill not found in your profile",
            "skill": skill,
        })
    if not experience:
        gaps.append({"type": "missing_qualification", "section": "experience",
                     "title": "Work experience", "detail": "No work experience in your profile"})
    elif min_years and candidate_years < min_years:
        gaps.append({"type": "missing_qualification", "section": "experience",
                     "title": f"{min_years}+ years experience",
                     "detail": f"Your profile shows {candidate_years} year{'s' if candidate_years != 1 else ''}"})
    if degree_required and not education:
        gaps.append({"type": "missing_qualification", "section": "education",
                     "title": "Degree", "detail": "Degree requirement not shown in your profile"})
    if certs_required and certs_score is not None and certs_score < 100:
        named_display = sorted({m.group(0) for m in CERT_REQUIREMENT_PATTERN.finditer(job_description)
                                if m.group(0).lower() not in GENERIC_CERT_TERMS})
        gaps.append({"type": "missing_qualification", "section": "certifications",
                     "title": f"Certification ({', '.join(named_display[:3])})" if named_display else "Certification",
                     "detail": "Certification not mentioned" if not certifications
                     else "Listed certifications do not fully match the ones requested"})

    section_scores: Dict[str, Optional[int]] = {
        "summary": summary_score,
        "skills": skills_score,
        "experience": exp_score,
        "education": edu_score,
        "projects": proj_score,
        "certifications": certs_score,
    }
    details = {
        "summary": {"matched_keywords": summary_keywords},
        "skills": {
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "evidenced_elsewhere": evidenced_elsewhere,
            "matched_with_evidence": matched_with_evidence,
        },
        "experience": {
            "matched_skills": exp_evidenced,
            "required_years": min_years,
            "candidate_years": candidate_years,
            "bullets_with_metrics": len(metric_bullets),
            "total_bullets": len(all_exp_bullets),
        },
        "education": {"degree_required": degree_required},
        "projects": {"matched_skills": proj_evidenced},
        "certifications": {"required": certs_required},
    }

    sections = {}
    for key in ("summary", "skills", "experience", "education", "projects", "certifications"):
        raw = section_scores[key]
        score = None if raw is None else int(max(0, min(100, raw)))
        section_scores[key] = score
        entry = {
            "name": SECTION_NAMES[key],
            "score": score,
            "weight": SECTION_WEIGHTS[key],
            "status": _status_for(score),
            "missing": [m["text"] for m in missing_information if m["section"] == key],
            "suggestions": [s["text"] for s in suggestions if s["section"] == key],
            **details[key],
        }
        if score is None:
            entry["not_applicable"] = True
        sections[key] = entry

    applicable = {k: v for k, v in section_scores.items() if v is not None}
    total_weight = sum(SECTION_WEIGHTS[k] for k in applicable)
    job_match_score = (
        int(round(sum(v * SECTION_WEIGHTS[k] for k, v in applicable.items()) / total_weight))
        if total_weight else 0
    )

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: (priority_rank.get(s["priority"], 3), -SECTION_WEIGHTS.get(s["section"], 0)))

    completeness = evaluate_profile_strength(profile or None)

    return {
        "job": {"id": job.get("id"), "title": job_title, "company": job.get("company")},
        "job_match_score": job_match_score,
        "match_tier": _match_tier(job_match_score),
        "sections": sections,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "job_skills": job_skills,
        "missing_information": missing_information,
        "gaps": gaps,
        "suggestions": suggestions,
        "profile_completeness": {
            "overall_score": completeness.get("overall_score", 0),
            "strength_tier": completeness.get("strength_tier"),
            "sections": {k: v.get("score", 0) for k, v in (completeness.get("sections") or {}).items()},
        },
    }
