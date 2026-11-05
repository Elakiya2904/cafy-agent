"""Rank job listings against candidate profiles using skill, role, and location evidence.

Provides candidate-to-vacancy matching and returns ordered recommendations with
the evidence used to calculate each match.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .skill_catalog import WEAK_MATCH_SKILLS, role_matches_title
from .skill_matching import stems, text_has_skill

# Minimum number of strong skill matches required to surface a recommendation.
_MIN_SKILL_MATCHES = 2


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

        # Use the caller's threshold directly; default 0 means show everything with ≥1 match.
        threshold = max(0, int(min_score if min_score is not None else 0))

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

        # Build a flat text blob of the candidate's experience + projects for broader matching.
        import json as _json
        experience_blob = " ".join(
            " ".join(filter(None, [
                str(e.get("title") or ""),
                str(e.get("organization") or e.get("company") or ""),
                str(e.get("description") or ""),
                " ".join(str(b) for b in (e.get("bullets") or [])),
            ]))
            for e in (resume_data.get("experience") or []) + (resume_data.get("projects") or [])
            if isinstance(e, dict)
        ).lower()

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

            # Skills matched in the profile's skills list.
            matched_skills = [
                skill for skill in job_skills
                if _norm(skill) in profile_skill_keys and skill.casefold() not in WEAK_MATCH_SKILLS
            ]
            description = f"{title} {job.get('description') or ''}"
            description_stems = stems(description)
            matched_keys = {_norm(skill) for skill in matched_skills}

            # Also match skills evidenced in experience/project text.
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

            # Require at least _MIN_SKILL_MATCHES strong matches to surface the job.
            if len(matched_skills) < _MIN_SKILL_MATCHES and not role_match:
                continue

            missing_skills = [
                skill for skill in job_skills
                if _norm(skill) not in matched_keys
            ]
            job_skill_count = len(job_skills)

            # ── Real score formula ──────────────────────────────────────────
            # 50 pts: skill coverage (matched / total job skills)
            # 20 pts: role-title alignment
            # 15 pts: seniority alignment
            # 15 pts: experience-text evidence (skills found in bullets/descriptions)
            skill_coverage = (len(matched_skills) / job_skill_count) if job_skill_count else 0.0

            title_words = [w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z+#.]*", title)
                           if len(w) > 2 and w.lower() not in {
                               "senior", "junior", "lead", "staff", "principal", "head",
                               "of", "and", "the", "remote", "hybrid", "uk", "london",
                           }]
            title_score = 0.0
            if role_match:
                title_score = 1.0
            elif title_words and experience_blob:
                hits = sum(1 for w in title_words if w in experience_blob)
                title_score = hits / len(title_words)

            seniority_score = 0.0
            if (
                "senior" in seniority
                and any(w in title.casefold() for w in ("senior", "staff", "principal", "lead"))
            ) or (
                "lead" in seniority
                and any(w in title.casefold() for w in ("lead", "principal", "staff"))
            ) or (
                "junior" in seniority
                and any(w in title.casefold() for w in ("junior", "associate"))
            ):
                seniority_score = 1.0
            elif not any(level in seniority for level in ("senior", "lead", "junior", "principal")):
                # No seniority info — treat as neutral (partial credit).
                seniority_score = 0.5

            # Experience-text evidence: how many job skills appear in the candidate's
            # experience/project text (beyond what's in the skills list).
            exp_evidenced = sum(
                1 for skill in job_skills
                if _norm(skill) not in profile_skill_keys
                and re.search(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])", experience_blob)
            ) if experience_blob and job_skills else 0
            exp_evidence_score = min(1.0, exp_evidenced / max(1, job_skill_count * 0.3))

            raw_score = (
                50 * skill_coverage
                + 20 * title_score
                + 15 * seniority_score
                + 15 * exp_evidence_score
            )
            score = max(1, min(99, int(round(raw_score))))

            if score < threshold:
                continue

            # ── Match tier ──────────────────────────────────────────────────
            if score >= 75:
                fit_level = "Strong Match"
            elif score >= 55:
                fit_level = "Good Match"
            elif score >= 35:
                fit_level = "Partial Match"
            else:
                fit_level = "Low Match"

            reasons = []
            if matched_skills:
                reasons.append(f"Matched {len(matched_skills)} of {job_skill_count} required skills: {', '.join(matched_skills[:4])}")
            if role_match:
                reasons.append("Matches your target job title")
            if seniority_score == 1.0:
                reasons.append(f"Aligned with your {seniority.title()} seniority level")
            minimum_years, maximum_years = _job_experience_requirement(job)
            if minimum_years is not None:
                requirement = (
                    f"{minimum_years}–{maximum_years} years"
                    if maximum_years is not None
                    else f"{minimum_years}+ years"
                )
                reasons.append(f"Listing asks for {requirement} of experience")
            if job.get("is_remote"):
                reasons.append("Remote-friendly opportunity")

            recommendations.append({
                **job,
                "match_score": score,
                "fit_level": fit_level,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "match_reasons": reasons,
            })

        recommendations.sort(key=lambda item: item["match_score"], reverse=True)
        return recommendations
