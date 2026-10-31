"""Optional AI interpretation of a role (Groq). Always labelled as interpretation by the caller."""
import json
import os
import re
from typing import Any, Dict, Optional

import requests


def interpret_role(job: Dict[str, Any], role: Dict[str, Any]) -> Optional[Dict[str, str]]:
    api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    system = ("You explain a job posting to a candidate in plain language. Use ONLY the posting text provided; do not add facts about the "
              "company, salary, tools or process that are not in it. Reply with JSON: {\"typical_day\": string (2-4 sentences, hedged with 'likely'), "
              "\"why_role_exists\": string (1-2 sentences, hedged)}.")
    user = f"Title: {job.get('title')}\nCompany: {job.get('company')}\nPosting:\n{(job.get('description') or '')[:5000]}"
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                      json={"model": os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                            "temperature": 0.2, "max_tokens": 500}, timeout=(5, 25))
    if r.status_code != 200:
        return None
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0)) if m else {}
    out = {k: str(data[k]).strip() for k in ("typical_day", "why_role_exists") if data.get(k)}
    return out or None
