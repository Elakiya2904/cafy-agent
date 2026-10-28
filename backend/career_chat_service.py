import json
import logging
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger("cafy.career_chat")

EARLY_CAREER_TERMS = (
    "intern", "internship", "graduate", "junior", "entry-level", "entry level", "early career",
    "new grad", "new graduate", "fresh graduate", "fresher", "freshers", "0-2 years", "0 to 2 years",
    "associate", "apprentice"
)

UK_LOCATION_TERMS = (
    "united kingdom", "uk", "england", "scotland", "wales", "northern ireland",
    "london", "manchester", "edinburgh", "glasgow", "birmingham", "bristol",
    "cambridge", "oxford", "leeds", "dublin"
)

GENERIC_ROLE_WORDS = {
    "engineer", "developer", "software", "senior", "junior", "lead", "staff",
    "principal", "manager", "scientist", "specialist", "analyst", "associate",
}


class CareerChatError(RuntimeError):
    pass


def _detect_intent(query: str, mode: str) -> str:
    q = query.casefold().strip()
    if any(k in q for k in ("prioritise", "prioritize", "which jobs should i apply", "apply first", "application strategy", "strategy")):
        return "strategy"
    if any(k in q for k in ("why is this job", "explain", "explain match", "why am i a good", "match score", "why do i match", "why 85", "why 89", "why 82")):
        return "explain_match"
    if any(k in q for k in ("skill gap", "skills to learn", "what should i learn", "missing skills", "qualify for better", "improve my chances", "learning plan", "skills recur")):
        return "skill_gaps"
    if any(k in q for k in ("hiring freshers", "job market", "companies hiring", "market intelligence", "entry-level ai", "find new jobs", "uk roles", "which companies")):
        return "market"
    if any(k in q for k in ("progress", "how many jobs", "saved", "pipeline", "applications", "track", "show my progress")):
        return "progress"
    if any(k in q for k in ("what roles am i", "most qualified", "career profile", "analyse my opportunities", "opportunities", "strongest matches")):
        return "profile_opportunities"
    
    # Map from UI mode
    mode_map = {
        "opportunities": "strategy",
        "skills": "skill_gaps",
        "market": "market",
        "progress": "progress",
    }
    return mode_map.get(mode, "strategy")


def _role_matches(job: Dict[str, Any], roles: Sequence[str]) -> bool:
    title = (job.get("title") or "").casefold()
    for role in roles:
        role_text = role.casefold().strip()
        if role_text and role_text in title:
            return True
        role_terms = [
            term for term in role_text.split()
            if term not in GENERIC_ROLE_WORDS and len(term) > 2
        ]
        if role_terms and all(term in title for term in role_terms):
            return True
    return False


def _detect_experience_signal(job: Dict[str, Any]) -> str:
    text = f"{job.get('title', '')} {job.get('description', '')}".casefold()
    if any(t in text for t in ("fresher", "fresh graduate", "accepts freshers", "new grad", "graduate")):
        return "Graduate / early-career wording in listing"
    if any(t in text for t in ("junior", "entry-level", "entry level", "early career", "0-2 years")):
        return "Entry-level wording in listing"
    if any(t in text for t in ("lead", "principal", "staff", "head of", "director")):
        return "Lead / principal wording in listing"
    if "senior" in text:
        return "Senior-level wording in listing"
    return "Experience level not specified"


def _compact_job(
    job: Dict[str, Any],
    match_by_id: Dict[str, Dict[str, Any]],
    resume_skills: set[str],
    has_resume: bool,
) -> Dict[str, Any]:
    skills = job.get("extracted_skills") or []
    # If skills list is short, also check title & desc for common skills
    desc = f"{job.get('title', '')} {job.get('description', '')}".casefold()
    extra_matched = [s for s in resume_skills if s in desc and s not in [x.casefold() for x in skills]]
    
    matched = [skill for skill in skills if skill.casefold() in resume_skills] + extra_matched[:3]
    missing = [skill for skill in skills if skill.casefold() not in resume_skills] if has_resume else []
    match = match_by_id.get(job.get("id", ""), {})

    score = match.get("match_score")

    # Experience
    exp_signal = _detect_experience_signal(job)

    # Sponsorship
    is_sponsored = bool(job.get("visa_sponsored"))
    loc = job.get("location") or "Location not listed"
    is_uk = any(t in loc.casefold() for t in UK_LOCATION_TERMS)
    if is_sponsored and is_uk:
        sponsorship_str = "Yes (UK Sponsor Listed)"
    elif is_uk:
        sponsorship_str = "UK location / Sponsor check pending"
    else:
        sponsorship_str = "Not verified"

    # Priority recommendation
    if score is not None and score >= 85:
        recommendation = "High priority"
    elif score is not None and score >= 78:
        recommendation = "Recommended"
    elif score is not None:
        recommendation = "Review against your preferences"
    else:
        recommendation = "Not scored"

    bullets = []
    if matched:
        bullets.append(f"Skills also listed on your resume: {', '.join(matched[:3])}")

    if exp_signal != "Experience level not specified":
        bullets.append(exp_signal)

    if missing:
        bullets.append(f"Listing skills not detected on your resume: {', '.join(missing[:3])}")

    bullets.append(f"Location: {loc}")
    bullets.append(f"Sponsorship: {sponsorship_str}")

    return {
        "id": job.get("id"),
        "title": job.get("title"),
        "company": job.get("company") or "Unknown employer",
        "location": loc,
        "url": job.get("url"),
        "department": job.get("department"),
        "employment_type": job.get("employment_type") or "Not listed",
        "match_score": score,
        "matched_skills": match.get("matched_skills", matched),
        "missing_skills": match.get("missing_skills", missing),
        "experience_signal": exp_signal,
        "sponsorship_status": sponsorship_str,
        "recommendation": recommendation,
        "bullets": bullets,
        "visa_sponsored": is_sponsored,
        "visa_sponsor_registered_names": job.get("visa_sponsor_registered_names", []),
    }


def _select_diverse_cards(candidates: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    seen_companies = set()
    seen_titles = set()
    selected = []
    # First pass: 1 job per company to maximize company diversity
    for job in candidates:
        comp = (job.get("company") or "").strip().lower()
        title = (job.get("title") or "").strip().lower()
        if comp and comp in seen_companies:
            continue
        if title and title in seen_titles:
            continue
        if comp:
            seen_companies.add(comp)
        if title:
            seen_titles.add(title)
        selected.append(job)
        if len(selected) >= limit:
            return selected
    # Second pass if not enough: allow same company with different titles
    if len(selected) < limit:
        for job in candidates:
            if job in selected:
                continue
            title = (job.get("title") or "").strip().lower()
            if title and title in seen_titles:
                continue
            if title:
                seen_titles.add(title)
            selected.append(job)
            if len(selected) >= limit:
                return selected
    # Fallback to remaining candidates
    for job in candidates:
        if job not in selected:
            selected.append(job)
            if len(selected) >= limit:
                break
    return selected


def build_career_context(
    query: str,
    mode: str,
    resume: Optional[Dict[str, Any]],
    jobs: List[Dict[str, Any]],
    matched_jobs: List[Dict[str, Any]],
    pipeline_job_ids: Sequence[str],
    focus_job_id: Optional[str] = None,
) -> tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    intent = _detect_intent(query, mode)
    resume = resume or {}
    resume_skills = {skill.casefold() for skill in resume.get("skills", [])}
    target_roles = resume.get("target_roles", [])
    match_by_id = {job.get("id", ""): job for job in matched_jobs}
    jobs_by_id = {job.get("id", ""): job for job in jobs}

    role_jobs = [job for job in jobs if _role_matches(job, target_roles)]
    if not role_jobs:
        role_jobs = jobs

    # Recurring skill gaps
    skill_counts = Counter(
        skill
        for job in role_jobs
        for skill in job.get("extracted_skills", [])
    )
    skill_gaps = [
        {"skill": skill, "job_count": count}
        for skill, count in skill_counts.most_common()
        if skill.casefold() not in resume_skills
    ][:10] if resume else []

    # Fresher & early-career jobs in database
    early_career_jobs = [
        job for job in jobs
        if any(t in f"{job.get('title', '')} {job.get('description', '')}".casefold() for t in EARLY_CAREER_TERMS)
    ]

    # UK sponsor listed jobs
    uk_sponsor_jobs = [job for job in jobs if job.get("visa_sponsored")]

    # Match candidates
    match_candidates = sorted(
        matched_jobs,
        key=lambda job: job.get("match_score", 0),
        reverse=True,
    )

    focus_job = jobs_by_id.get(focus_job_id or "")
    if not focus_job and query:
        query_lower = query.casefold()
        focus_job = next(
            (
                job for job in jobs
                if (job.get("title") or "").casefold() in query_lower
                or (job.get("company") or "").casefold() in query_lower
            ),
            None,
        )

    pipeline_ids = set(pipeline_job_ids)
    pipeline_jobs = [job for job in jobs if job.get("id") in pipeline_ids]

    # Select appropriate job cards based on intent with company diversity
    if intent == "strategy":
        cards_source = [focus_job] if focus_job else _select_diverse_cards(match_candidates, 3)
    elif intent == "explain_match":
        cards_source = [focus_job] if focus_job else _select_diverse_cards(match_candidates, 2)
    elif intent == "skill_gaps":
        cards_source = _select_diverse_cards(role_jobs, 3)
    elif intent == "market":
        cards_source = _select_diverse_cards(early_career_jobs if early_career_jobs else role_jobs, 3)
    elif intent == "progress":
        cards_source = pipeline_jobs[:3] if pipeline_jobs else _select_diverse_cards(match_candidates, 3)
    elif intent == "profile_opportunities":
        cards_source = _select_diverse_cards(match_candidates, 3)
    else:
        cards_source = _select_diverse_cards(match_candidates, 3)

    cards = [_compact_job(job, match_by_id, resume_skills, bool(resume)) for job in cards_source]

    context = {
        "intent": intent,
        "mode": mode,
        "candidate": {
            "name": resume.get("candidate_name") or "Candidate",
            "skills": resume.get("skills", [])[:40],
            "target_roles": target_roles[:8],
            "seniority_level": resume.get("seniority_level") or "Early career / Graduate",
            "years_of_experience": resume.get("years_of_experience", 0),
        } if resume else None,
        "database_summary": {
            "analyzed_job_count": len(jobs),
            "matched_jobs_count": len(matched_jobs),
            "analyzed_early_career_count": len(early_career_jobs),
            "analyzed_uk_sponsor_count": len(uk_sponsor_jobs),
            "tracked_pipeline_count": len(pipeline_ids),
        },
        "top_skill_gaps": skill_gaps,
        "selected_cards": cards,
        "focused_job": _compact_job(focus_job, match_by_id, resume_skills, bool(resume)) if focus_job else None,
    }

    return context, cards, intent


class CareerChatService:
    def answer(
        self,
        query: str,
        mode: str,
        context: Dict[str, Any],
        cards: List[Dict[str, Any]],
        intent: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")

        if not api_key:
            raise CareerChatError(
                "Career Analyst is not configured. Add GROQ_API_KEY to the Vercel project environment variables and redeploy."
            )

        system_prompt = (
            "You are Cafy Agent, an AI Career Analyst and job search intelligence assistant. "
            "You help users make decisions by analyzing their resume, job market data, match scores, and application priorities. "
            "Guidelines:\n"
            "1. Ground every statement strictly in the provided Cafy evidence JSON. Never invent companies, match scores, job counts, skills, or job details.\n"
            "2. If evidence is missing or inconclusive, say so plainly instead of guessing. A skill not detected on a resume is not proof that the candidate lacks it.\n"
            "3. Only describe a role as a match when an evidence-backed match score or matched skills are provided. Do not invent a score.\n"
            "4. When the user asks which jobs to prioritize, explain the evidence-backed reasons for the selected jobs (match quality, experience wording, sponsorship status, or skills).\n"
            "5. For match explanation, distinguish listing skills from skills detected on the resume; do not claim a gap is a job requirement unless the evidence says so.\n"
            "6. Counts in database_summary describe only the supplied analyzed job set, not the entire database or market. For skill gaps and market questions, never extrapolate these counts or add employers not present in the evidence.\n"
            "7. Keep responses clean, insightful, professional, and concise. Use Markdown tables only when they materially improve readability.\n"
            "8. Do not repeat full card JSON in text because the UI automatically renders interactive job cards below your answer."
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in (history or [])[-6:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"][:1000]})

        evidence_payload = {
            "intent": intent,
            "candidate": context.get("candidate"),
            "database_summary": context.get("database_summary"),
            "top_skill_gaps": context.get("top_skill_gaps"),
            "recommended_cards_summary": [
                {
                    "title": c.get("title"),
                    "company": c.get("company"),
                    "match_score": c.get("match_score"),
                    "matched_skills": c.get("matched_skills"),
                    "missing_skills": c.get("missing_skills"),
                    "experience_signal": c.get("experience_signal"),
                    "sponsorship": c.get("sponsorship_status"),
                    "recommendation": c.get("recommendation"),
                    "location": c.get("location"),
                    "employment_type": c.get("employment_type"),
                    "url": c.get("url"),
                    "evidence_bullets": c.get("bullets"),
                }
                for c in cards
            ],
            "focused_job": context.get("focused_job"),
        }

        messages.append({
            "role": "user",
            "content": (
                f"Mode: {mode}\n"
                f"Evidence: {json.dumps(evidence_payload, ensure_ascii=True, separators=(',', ':'))}\n"
                f"User Question: {query}"
            ),
        })

        model = os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b"
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.25,
                    "max_tokens": 500,
                },
                timeout=(2, 6),
            )
        except requests.RequestException as err:
            logger.warning("Groq chat request failed: %s", err)
            raise CareerChatError(
                "Career Analyst is temporarily unreachable. Please try again shortly."
            ) from err

        if response.status_code != 200:
            logger.warning("Groq chat returned HTTP %s", response.status_code)
            raise CareerChatError(
                "Career Analyst could not complete the request. Check the Groq API key and model configuration."
            )

        try:
            payload = response.json()
        except ValueError as err:
            logger.warning("Groq chat returned invalid JSON")
            raise CareerChatError("Career Analyst returned an invalid response. Please try again.") from err

        choices = payload.get("choices") if isinstance(payload, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices else None
        answer = message.get("content") if isinstance(message, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            logger.warning("Groq chat response did not contain an answer")
            raise CareerChatError("Career Analyst returned an empty response. Please try again.")
        return answer.strip()
