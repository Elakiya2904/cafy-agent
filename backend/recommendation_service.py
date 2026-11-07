"""Rank job listings against candidate profiles using skill, role, and location evidence.

Provides candidate-to-vacancy matching and returns ordered recommendations with
the evidence used to calculate each match.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .skill_catalog import role_matches_title

# Minimum number of strong skill matches required to surface a recommendation.
_MIN_SKILL_MATCHES = 2

# Jobs below this match score are not listed for a candidate (uploads, chat, alerts).
MIN_MATCH_SCORE = 85

_FRESHER_TITLE_TERMS = ("intern", "graduate", "new grad", "fresher", "trainee", "apprentice",
                        "junior", "entry-level", "entry level")
_EXPERIENCED_TITLE_TERMS = ("senior", "staff", "principal", "lead", "director", "head of", "manager")


EXPERIENCE_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:(?P<range_min>\d+)\s*(?:-|–|to)\s*(?P<range_max>\d+)"
    r"|(?P<minimum>\d+)\s*\+?"
    r"|(?:at least|minimum(?: of)?|no less than)\s+(?P<stated_minimum>\d+))"
    # "5+ years of experience", "3 years of commercial Python experience" (up to 3 words between).
    # A word may contain an inner dot (Node.js) but never end a sentence.
    r"\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[A-Za-z][A-Za-z+#/-]*(?:\.[A-Za-z]+)?\s+){0,3}?experience\b",
    re.IGNORECASE,
)


def _job_experience_requirement(job: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    text = f"{job.get('title', '')} {job.get('description', '')}"
    requirements = list(EXPERIENCE_REQUIREMENT_PATTERN.finditer(text))
    if not requirements:
        return None, None

    match = requirements[0]
    min_raw = match.group("range_min") or match.group("minimum") or match.group("stated_minimum")
    if not min_raw:
        return None, None
    minimum = int(min_raw)
    max_raw = match.group("range_max")
    maximum = int(max_raw) if max_raw else None
    return minimum, maximum


def job_level(job: Dict[str, Any]) -> str:
    """Who the listing is for, from its title and stated years: fresher, experienced or any."""
    title = (job.get("title") or "").casefold()
    minimum_years, _ = _job_experience_requirement(job)
    if any(term in title for term in _FRESHER_TITLE_TERMS) or (minimum_years is not None and minimum_years <= 1):
        return "fresher"
    if any(term in title for term in _EXPERIENCED_TITLE_TERMS) or (minimum_years is not None and minimum_years >= 2):
        return "experienced"
    return "any"


def _experience_level_matches(job: Dict[str, Any], candidate_years: int) -> bool:
    title = (job.get("title") or "").casefold()
    minimum_years, maximum_years = _job_experience_requirement(job)

    if minimum_years is not None and minimum_years > candidate_years:
        return False
    if maximum_years is not None and candidate_years > maximum_years:
        return False

    fresher_role = any(term in title for term in ("intern", "graduate", "new grad", "fresher"))
    junior_role = any(term in title for term in ("junior", "entry-level", "entry level"))
    senior_role = any(term in title for term in ("senior", "staff", "principal", "lead", "director"))

    if candidate_years <= 1:
        if senior_role:
            return False
        if minimum_years is not None and minimum_years > 1:
            return False
    elif fresher_role:
        return False
    elif candidate_years > 3 and junior_role:
        return False

    if senior_role and candidate_years < 5:
        return False
    return True


class RecommendationService:
    """Rank verified jobs using the legacy high-confidence match score."""

    def recommend_jobs(
        self,
        resume_data: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        min_score: int = 0,
        platform_filter: str = "all",
    ) -> List[Dict[str, Any]]:
        """Score every job with the requirement-level model (``requirement_matching``).

        Jobs are first filtered by platform and by experience level (a fresher never sees roles
        for experienced hires, and vice versa); the rest are scored, and only those at or
        above ``min_score`` are returned, best first. Each result carries the full breakdown.
        """
        if not jobs:
            return []

        from .requirement_matching import ResumeContext, score_job

        threshold = max(0, int(min_score if min_score is not None else 0))
        ctx = ResumeContext(resume_data)
        candidate_years, candidate_level = ctx.years, ctx.level

        recommendations: List[Dict[str, Any]] = []
        for job in jobs:
            if platform_filter and platform_filter != "all":
                if job.get("platform", "").lower() != platform_filter.lower():
                    continue
            if not _experience_level_matches(job, candidate_years):
                continue
            if candidate_level == "fresher" and job_level(job) == "experienced":
                continue

            title = str(job.get("title") or "")
            role_match = any(
                role_matches_title(str(role), title)
                for role in (resume_data.get("target_roles") or [])
            )
            result = score_job(resume_data, job, ctx)
            matched_skills = result["matched_skills"]
            if not job.get("extracted_skills"):
                job["extracted_skills"] = [r["name"] for r in result["requirements"]]

            # Require at least _MIN_SKILL_MATCHES matched skills to surface the job.
            if len(matched_skills) < _MIN_SKILL_MATCHES and not role_match:
                continue
            score = result["score"]
            if score < threshold:
                continue

            if score >= 85:
                fit_level = "Exceptional Match"
            elif score >= 70:
                fit_level = "Strong Match"
            elif score >= 50:
                fit_level = "Good Match"
            elif score >= 35:
                fit_level = "Partial Match"
            else:
                fit_level = "Low Match"

            level = result["checks"]["experience"]["job_level"]
            essential, desirable = result["essential"], result["desirable"]
            reasons = []
            if level == "any":
                reasons.append(f"Open to {candidate_level}s")
            else:
                reasons.append(f"{level.title()} role - matches your {candidate_level} profile")
            if essential["count"]:
                reasons.append(
                    f"Essential skills: {essential['direct'] + essential['weak']} of {essential['count']} on your resume"
                    + (f" ({essential['direct']} shown in your work)" if essential["direct"] else "")
                )
            if desirable["count"]:
                reasons.append(f"Desirable skills: {desirable['direct'] + desirable['weak']} of {desirable['count']}")
            if matched_skills:
                reasons.append(f"Matched: {', '.join(matched_skills[:4])}")
            if role_match:
                reasons.append("Matches your target job title")
            reasons.append(result["checks"]["experience"]["detail"])
            for unmet in result["checks"]["qualifications"]["essential_unmet"]:
                reasons.append(f"Essential qualification not on your resume: {unmet}")
            reasons.extend(result["cap_reasons"])
            if job.get("is_remote"):
                reasons.append("Remote-friendly opportunity")

            recommendations.append({
                **job,
                "match_score": score,
                "fit_level": fit_level,
                "job_level": level,
                "candidate_level": candidate_level,
                "matched_skills": matched_skills,
                "transferable_skills": result["transferable_skills"],
                "missing_skills": result["missing_skills"],
                "match_reasons": reasons,
                "match_breakdown": result,
            })

        recommendations.sort(key=lambda item: item["match_score"], reverse=True)
        return recommendations


def match_jobs_for_candidate(
    profile: Dict[str, Any], jobs: List[Dict[str, Any]], min_score: int = 0
) -> List[Dict[str, Any]]:
    """Rank ``jobs`` for ``profile`` (thin wrapper used by scripts and tests)."""
    return RecommendationService().recommend_jobs(profile, jobs, min_score=min_score)
