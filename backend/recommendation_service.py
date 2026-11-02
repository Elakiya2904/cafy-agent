from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .skill_catalog import WEAK_MATCH_SKILLS, role_matches_title
from .skill_matching import stems, text_has_skill


EXPERIENCE_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:(?P<range_min>\d+)\s*(?:-|–|to)\s*(?P<range_max>\d+)"
    r"|(?P<minimum>\d+)\s*\+?"
    r"|(?:at least|minimum(?: of)?|no less than)\s+(?P<stated_minimum>\d+))"
    r"\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience\b",
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
        if not jobs:
            return []

        from .job_match_analysis_service import _job_skills, _norm

        threshold = max(85, min(100, int(min_score if min_score is not None else 85)))
        raw_years = resume_data.get("years_of_experience")
        try:
            candidate_years = max(0, int(raw_years)) if raw_years is not None else 0
        except (TypeError, ValueError):
            candidate_years = 0
        if raw_years is None:
            seniority = str(resume_data.get("seniority_level") or "").casefold()
            if "principal" in seniority or "lead" in seniority:
                candidate_years = 7
            elif "senior" in seniority:
                candidate_years = 5

        recommendations: List[Dict[str, Any]] = []
        candidate_skills = [str(skill) for skill in (resume_data.get("skills") or [])]
        profile_skill_keys = {_norm(skill) for skill in candidate_skills if _norm(skill)}
        seniority = str(resume_data.get("seniority_level") or "").casefold()
        for job in jobs:
            if platform_filter and platform_filter != "all":
                if job.get("platform", "").lower() != platform_filter.lower():
                    continue
            if not _experience_level_matches(job, candidate_years):
                continue

            title = str(job.get("title") or "")
            role_match = any(
                role_matches_title(str(role), title)
                for role in (resume_data.get("target_roles") or [])
            )
            job_skills = _job_skills(job)
            if not job.get("extracted_skills"):
                job["extracted_skills"] = job_skills

            matched_skills = [
                skill for skill in job_skills
                if _norm(skill) in profile_skill_keys and skill.casefold() not in WEAK_MATCH_SKILLS
            ]
            description = f"{title} {job.get('description') or ''}"
            description_stems = stems(description)
            matched_keys = {_norm(skill) for skill in matched_skills}
            for skill in candidate_skills:
                key = _norm(skill)
                if (
                    key
                    and key not in matched_keys
                    and text_has_skill(skill, description, description_stems)
                    and skill.casefold() not in WEAK_MATCH_SKILLS
                ):
                    matched_skills.append(skill)
                    matched_keys.add(key)

            if len(matched_skills) < 4 and not (role_match and len(matched_skills) >= 3):
                continue

            missing_skills = [
                skill for skill in job_skills
                if _norm(skill) not in matched_keys
            ]
            seniority_bonus = 0
            if (
                "senior" in seniority
                and any(word in title.casefold() for word in ("senior", "staff", "principal", "lead"))
            ) or (
                "lead" in seniority
                and any(word in title.casefold() for word in ("lead", "principal", "staff"))
            ) or (
                "junior" in seniority
                and any(word in title.casefold() for word in ("junior", "associate"))
            ):
                seniority_bonus = 2

            score = min(
                98,
                85
                + min(8, max(0, len(matched_skills) - 4) * 2)
                + (3 if role_match else 0)
                + seniority_bonus,
            )
            if score < threshold:
                continue

            reasons = []
            if matched_skills:
                reasons.append(f"Strong overlap on {', '.join(matched_skills[:4])}")
            if role_match:
                reasons.append("Matches your target job title")
            if seniority_bonus:
                reasons.append(f"Aligned with your {seniority.title()} seniority level")
            minimum_years, maximum_years = _job_experience_requirement(job)
            if minimum_years is not None:
                requirement = (
                    f"{minimum_years}-{maximum_years} years"
                    if maximum_years is not None
                    else f"{minimum_years}+ years"
                )
                reasons.append(f"Listing asks for {requirement} of experience")
            if job.get("is_remote"):
                reasons.append("Remote-friendly opportunity")

            recommendations.append({
                **job,
                "match_score": score,
                "fit_level": "Exceptional Match",
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "match_reasons": reasons,
            })

        recommendations.sort(key=lambda item: item["match_score"], reverse=True)
        return recommendations
