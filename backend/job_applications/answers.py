"""Grounded AI answers for open-ended application questions (Groq)."""
import json
import os
from typing import Any, Dict, Optional

import requests


def groq_answer(question: str, profile: Dict[str, Any], job: Dict[str, Any]) -> Optional[str]:
    """Draft an answer from the candidate's real profile. Returns None when AI is not configured."""
    api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    facts = {
        "skills": (profile.get("skills") or [])[:25],
        "summary": profile.get("summary"),
        "experience": [{k: e.get(k) for k in ("title", "company", "dates", "bullets")} for e in (profile.get("experience") or [])[:4]],
        "education": (profile.get("education") or [])[:3],
        "projects": (profile.get("projects") or [])[:3],
    }
    system = (
        "You draft job-application answers on behalf of a candidate. Use ONLY the facts provided about the candidate. "
        "Never invent employers, dates, numbers, qualifications, work authorisation or personal details; if the facts do not support "
        "a claim, leave it out. Write in first person, 80-140 words, plain text, no headings or placeholders."
    )
    user = (f"Question: {question}\nCompany: {job.get('company')}\nRole: {job.get('title')}\n"
            f"Job description (excerpt): {(job.get('description') or '')[:1500]}\nCandidate facts: {json.dumps(facts, default=str)[:4000]}")
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b",
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
              "temperature": 0.2, "max_tokens": 500},
        timeout=(5, 25),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"AI service returned HTTP {resp.status_code}")
    return resp.json()["choices"][0]["message"]["content"].strip()
