"""Transparent CV content checks based on common career-site guidance.

This evaluates parsed profile content only. It cannot assess document layout,
ATS parsing, or predict an employer's screening decision.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .profile_strength_service import METRIC_PATTERN

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACTION_VERBS = {
    "achieved", "analyzed", "automated", "built", "collaborated", "created",
    "delivered", "designed", "developed", "drove", "established", "improved",
    "implemented", "increased", "launched", "led", "managed", "mentored",
    "optimized", "organized", "reduced", "resolved", "spearheaded", "streamlined",
}


def _entries(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _entry_value(entry: Any, *keys: str) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if not isinstance(entry, dict):
        return ""
    for key in keys:
        value = entry.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _bullets(entry: Any) -> List[str]:
    if isinstance(entry, str):
        return [entry.strip()] if entry.strip() else []
    if not isinstance(entry, dict):
        return []
    value = entry.get("bullets")
    if isinstance(value, list):
        lines = [str(line).strip(" -*•\t") for line in value if str(line).strip(" -*•\t")]
        if lines:
            return lines
    description = str(entry.get("description") or "").strip()
    if not description:
        return []
    return [
        line.strip(" -*•\t")
        for line in re.split(r"[\n•]+|(?<=[.!?])\s+", description)
        if line.strip(" -*•\t")
    ]


def _starts_with_action_verb(line: str) -> bool:
    match = re.match(r"^(?:[•*-]\s*)?([A-Za-z]+)", line)
    return bool(match and match.group(1).lower() in _ACTION_VERBS)


def evaluate_cv_quality(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Score common CV content checks equally, excluding optional empty sections."""
    profile = profile or {}
    checks: List[Dict[str, Any]] = []

    def add_check(key: str, section: str, label: str, passed: bool, advice: str) -> None:
        checks.append({
            "key": key,
            "section": section,
            "label": label,
            "passed": bool(passed),
            "status": "passed" if passed else "needs_work",
            "advice": "" if passed else advice,
        })

    name = str(profile.get("candidate_name") or "").strip()
    email = str(profile.get("email") or "").strip()
    add_check(
        "contact_details",
        "Contact",
        "Name and email are present",
        name.lower() not in {"", "candidate", "unknown", "uploaded_resume"} and bool(_EMAIL_PATTERN.match(email)),
        "Add your name and a valid email address.",
    )

    summary = str(profile.get("summary") or profile.get("professional_summary") or "").strip()
    add_check(
        "profile_summary",
        "Profile",
        "Profile summary is included",
        bool(summary),
        "Add a concise profile summary tailored to the roles you are applying for.",
    )

    skills = profile.get("skills")
    add_check(
        "skills_list",
        "Skills",
        "Skills are listed",
        isinstance(skills, list) and any(str(skill).strip() for skill in skills),
        "List relevant skills that you can support with examples.",
    )

    experience = _entries(profile.get("experience")) + _entries(profile.get("internships"))
    projects = _entries(profile.get("projects"))
    add_check(
        "work_history",
        "Experience",
        "Work history or relevant experience is included",
        bool(experience),
        "Add relevant employment, placement, internship, or other experience.",
    )

    if experience:
        has_role_details = all(
            _entry_value(entry, "title", "role", "position")
            and _entry_value(entry, "company", "organization", "employer")
            and _entry_value(entry, "dates", "start_date", "year", "end_date")
            for entry in experience
        )
        add_check(
            "role_details",
            "Experience",
            "Experience entries identify role, employer, and dates",
            has_role_details,
            "Add a role title, employer, and dates to each experience entry where available.",
        )

    evidence_entries = experience + projects
    evidence_lines = [line for entry in evidence_entries for line in _bullets(entry)]
    add_check(
        "achievement_evidence",
        "Experience",
        "Experience or projects include descriptive evidence",
        bool(evidence_lines),
        "Describe your contribution and what you did in experience or project entries.",
    )
    add_check(
        "action_led_bullets",
        "Experience",
        "At least one bullet starts with a clear action verb",
        any(_starts_with_action_verb(line) for line in evidence_lines),
        "Start an achievement bullet with a clear action verb, such as developed, led, or improved.",
    )
    add_check(
        "measurable_impact",
        "Experience",
        "At least one outcome includes a measurable result",
        any(METRIC_PATTERN.search(line) for line in evidence_lines),
        "Where accurate, add a measurable result or scope to an achievement.",
    )

    education = _entries(profile.get("education"))
    if education:
        has_education_details = all(
            _entry_value(entry, "degree", "title", "field")
            and _entry_value(entry, "institution", "organization", "school")
            for entry in education
        )
        add_check(
            "education_details",
            "Education",
            "Listed education includes qualification and institution",
            has_education_details,
            "Include the qualification or subject and institution for each education entry.",
        )

    if projects:
        has_project_details = all(
            _entry_value(entry, "title", "name")
            and bool(_bullets(entry) or _entry_value(entry, "description"))
            for entry in projects
        )
        add_check(
            "project_details",
            "Projects",
            "Listed projects have a title and description",
            has_project_details,
            "Give each listed project a title and a brief description of your contribution.",
        )

    certifications = _entries(profile.get("certifications"))
    if certifications:
        has_cert_details = all(
            _entry_value(entry, "name", "title", "certification")
            and _entry_value(entry, "issuer", "organization")
            for entry in certifications
        )
        add_check(
            "certification_details",
            "Certifications",
            "Listed certifications include their name and issuer",
            has_cert_details,
            "Add the certification name and issuing organisation to each listed certification.",
        )

    passed = sum(1 for check in checks if check["passed"])
    return {
        "score": int(round(passed / len(checks) * 100)) if checks else 0,
        "passed_checks": passed,
        "total_checks": len(checks),
        "checks": checks,
        "method": "Equal-weight content checks; empty optional sections are excluded.",
        "scope": "Checks parsed CV content only, not document layout, ATS parsing, or hiring outcomes.",
    }
