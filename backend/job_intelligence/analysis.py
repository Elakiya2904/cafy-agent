"""Role analysis, candidate compatibility and preparation guidance.

Facts parsed from the job description are tagged ``source: job_description``; anything
the model interprets is tagged ``ai_interpretation``. Compatibility only ever uses what
is in the stored candidate profile.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

_HEADINGS = {
    "responsibilities": re.compile(r"^(?:key |main |core )?(?:responsibilities|what you(?:'|’)ll do|what you will do|the role|about the role|your role|day[- ]to[- ]day|duties|what the job involves)\b", re.I),
    "qualifications": re.compile(r"^(?:requirements|qualifications|what you(?:'|’)ll need|what you will need|about you|who you are|must[- ]haves?|skills and experience|essential|what we(?:'|’)re looking for|you have)\b", re.I),
    "nice_to_have": re.compile(r"^(?:nice to haves?|bonus|desirable|preferred|it(?:'|’)s a plus|plus)\b", re.I),
    "other": re.compile(r"^(?:benefits|perks|about (?:us|the company|[A-Z]\w+)|who we are|our (?:mission|values|culture)|equal opportunit|how to apply|salary|compensation|what we offer|why join)\b", re.I),
}
_YEARS = re.compile(r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*\+?\s*years?(?:['’]s?)?\s*(?:of\s*)?(?:(?:relevant|professional|commercial|hands[- ]on|industry|work)\s*)*(?:experience|exp)?", re.I)
_DEGREE = re.compile(r"(bachelor|b\.?sc|b\.?s\.?|b\.?a\.?|master|m\.?sc|m\.?s\.?|ph\.?d|degree|diploma|equivalent (?:practical )?experience|computer science)", re.I)
_SALARY = re.compile(r"((?:£|€|\$)\s?\d[\d,.]*\s?(?:k|K)?(?:\s?(?:-|–|to)\s?(?:£|€|\$)?\s?\d[\d,.]*\s?(?:k|K)?)?(?:\s?(?:per|a|/)\s?(?:year|annum|yr|hour|hr|day))?)")
_SENIORITY = [("intern", r"\bintern(ship)?\b"), ("graduate", r"\b(graduate|early careers?|entry[- ]level|apprentice)\b"), ("junior", r"\b(junior|jr\.?|associate)\b"),
              ("lead/principal", r"\b(lead|principal|staff|head of|director|architect)\b"), ("senior", r"\b(?:senior|sr\.?)(?!\w)"), ("manager", r"\bmanager\b")]
TOPICS = ["system design", "cloud architecture", "distributed systems", "microservices", "ci/cd", "testing", "agile", "stakeholder management",
          "data modelling", "machine learning", "security", "api design", "monitoring", "performance optimisation", "mentoring"]
SOFT = ["communication", "teamwork", "leadership", "problem solving"]
DOMAIN_TOPICS: Dict[str, List[str]] = {
    "Sales & Business Development": ["pipeline management", "quota", "prospecting", "negotiation", "forecasting", "account management", "cold outreach", "discovery calls", "crm"],
    "Customer Success & Support": ["retention", "churn", "onboarding", "escalation", "nps", "renewals"],
    "Finance": ["financial modelling", "forecasting", "budgeting", "variance analysis", "valuation"],
    "Accounting": ["month-end close", "reconciliation", "accruals", "audit", "vat", "ifrs"],
    "Marketing & Communications": ["campaign", "seo", "content strategy", "brand", "analytics", "lead generation"],
    "Human Resources & Recruiting": ["sourcing", "employee relations", "onboarding", "stakeholder management"],
    "Operations & Supply Chain": ["inventory", "logistics", "process improvement", "procurement", "kpi"],
    "Product & Project Management": ["roadmap", "prioritisation", "stakeholder management", "risk management", "agile"],
    "Data & Analytics": ["dashboards", "data modelling", "a/b testing", "statistics", "reporting"],
}
DOMAIN_QUESTIONS: Dict[str, List[str]] = {
    "Sales & Business Development": [
        "Walk me through your sales process from first contact to closed deal.",
        "Tell me about a deal you almost lost and how you saved it.",
        "How do you build and manage your pipeline to hit quota?",
        "How do you qualify a lead, and what makes you walk away from one?",
        "Sell me a product you know well in two minutes."],
    "Customer Success & Support": [
        "Describe how you handled an angry customer and what the outcome was.",
        "How do you spot an at-risk account before it churns?",
        "How do you prioritise when several customers escalate at once?"],
    "Finance": [
        "Walk me through how you would build a forecast from scratch.",
        "How do you explain a significant budget variance to a non-finance stakeholder?"],
    "Accounting": [
        "Talk me through your month-end close process and where errors usually appear.",
        "How would you investigate a balance sheet account that does not reconcile?"],
    "Marketing & Communications": [
        "Describe a campaign you ran: goal, channels, results and what you would change.",
        "How do you decide where to spend a limited marketing budget?"],
    "Human Resources & Recruiting": [
        "How do you handle a hiring manager who keeps changing the brief?",
        "Describe a difficult employee-relations issue you resolved."],
    "Operations & Supply Chain": [
        "Describe a process you improved and how you measured the result.",
        "How do you respond to a sudden supplier delay?"],
    "Product & Project Management": [
        "How do you prioritise competing requests from stakeholders?",
        "Tell me about a project that slipped and how you recovered it."],
    "Data & Analytics": [
        "How would you investigate a sudden drop in a key metric?",
        "Explain a technical finding to a non-technical audience."],
}


def detect_domains(job_title: str, job_skills: List[str], limit: int = 2) -> List[str]:
    """Catalog domains that best fit a role, from its title phrases and required skills."""
    from ..skill_catalog import DOMAINS, title_has_phrase
    skills = {s.lower() for s in job_skills or []}
    scored = []
    for name, d in DOMAINS.items():
        score = len(skills & {x.lower() for x in d["skills"]})
        score += 3 * any(title_has_phrase(job_title or "", ph) for phrases in d["roles"].values() for ph in phrases)
        if score:
            scored.append((score, name))
    return [n for _, n in sorted(scored, reverse=True)[:limit]]


def _bullets(lines: List[str]) -> List[str]:
    out = []
    for l in lines:
        t = re.sub(r"^[\s\-\*•·▪●◦–]+", "", l).strip()
        if 12 <= len(t) <= 300:
            out.append(t)
    return out


def split_sections(description: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"responsibilities": [], "qualifications": [], "nice_to_have": [], "other": [], "intro": []}
    cur = "intro"
    for raw in re.split(r"\n+", re.sub(r"<[^>]+>", "\n", description or "")):
        line = raw.strip()
        if not line:
            continue
        head = re.sub(r"[:：\s]+$", "", line)
        hit = next((k for k, rx in _HEADINGS.items() if len(head) < 70 and rx.match(head)), None)
        if hit:
            cur = hit
            continue
        sections[cur].append(line)
    if not sections["responsibilities"] and not sections["qualifications"]:
        # Unstructured posting: fall back to sentence-level cues.
        for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", description or "")):
            if re.search(r"\b(you will|you'll|responsible for|will be (?:working|building|developing|leading))\b", s, re.I):
                sections["responsibilities"].append(s)
            elif re.search(r"\b(experience (?:in|with)|proficien|knowledge of|degree|ability to|must have|years)\b", s, re.I):
                sections["qualifications"].append(s)
    return sections


def seniority(title: str, description: str) -> Optional[str]:
    text = f"{title}"
    for label, rx in _SENIORITY:
        if re.search(rx, text, re.I):
            return label
    m = _YEARS.search(description or "")
    if m:
        y = int(m.group(1))
        return "junior" if y <= 2 else "mid-level" if y <= 4 else "senior"
    return None


def analyze_role(job: Dict[str, Any], job_skills: List[str]) -> Dict[str, Any]:
    desc = job.get("description") or ""
    sec = split_sections(desc)
    resp, qual, nice = _bullets(sec["responsibilities"])[:12], _bullets(sec["qualifications"])[:12], _bullets(sec["nice_to_have"])[:8]
    years = sorted({m.group(0).strip() for m in _YEARS.finditer(desc)})[:4]
    degrees = [q for q in qual if _DEGREE.search(q)][:3]
    salary = _SALARY.search(desc)
    low = desc.lower()
    domains = detect_domains(job.get("title") or "", job_skills)
    return {
        "title": job.get("title"), "company": job.get("company"), "location": job.get("location"), "employment_type": job.get("employment_type"),
        "industry": job.get("industry"), "department": job.get("department"), "seniority": seniority(job.get("title") or "", desc),
        "responsibilities": resp, "qualifications": qual, "nice_to_have": nice,
        "experience_requirements": years, "education_requirements": degrees,
        "required_skills": job_skills, "tools_and_technologies": [s for s in job_skills if s.lower() in low],
        "domains": domains,
        "topics_mentioned": [t for t in TOPICS + [x for d in domains for x in DOMAIN_TOPICS.get(d, [])] if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", low)], "soft_skills_mentioned": [t for t in SOFT if t in low],
        "salary": salary.group(1).strip() if salary else None,
        "has_description": bool(desc.strip()), "source": "job_description",
    }


# ------------------------------------------------------------------ stages
STAGE_GUIDE: Dict[str, Dict[str, Any]] = {
    "application_screening": {"purpose": "Check that your CV and application match the role's basic requirements.", "topics": ["Role requirements", "CV relevance"],
        "skills": ["Clear, evidence-based CV"], "prep": ["Mirror the posting's key skills where you genuinely have them", "Keep your CV to the most relevant achievements"]},
    "recruiter_screen": {"purpose": "A short conversation to confirm your background, motivation, availability and expectations.", "topics": ["Your background", "Why this company and role", "Availability and logistics"],
        "skills": ["Communication", "Motivation"], "prep": ["Prepare a 60-second summary of your experience", "Research the company and have a specific reason for applying", "Be ready to discuss location, notice period and right to work"]},
    "online_assessment": {"purpose": "A timed online test of aptitude or coding fundamentals, usually used to filter candidates.", "topics": ["Reasoning or core coding fundamentals"],
        "skills": ["Accuracy under time pressure"], "prep": ["Practise timed problems in the same style", "Check the format, time limit and allowed tools in the invitation"]},
    "technical_assessment": {"purpose": "A practical task that shows how you work on a realistic problem.", "topics": ["Role-relevant practical skills", "Code or solution quality", "Explaining trade-offs"],
        "skills": ["Practical problem solving", "Written communication"], "prep": ["Clarify scope and time expectations before starting", "Document assumptions and trade-offs in your submission"]},
    "technical_interview": {"purpose": "Assess depth in the technical skills the role needs and how you reason through problems.", "topics": ["Core skills from the job description", "Problem solving", "Past technical projects"],
        "skills": ["Technical depth", "Reasoning aloud"], "prep": ["Revise the required skills listed in the posting", "Prepare to walk through projects you built, including decisions and trade-offs", "Practise explaining your thinking while solving problems"]},
    "hiring_manager": {"purpose": "The future manager assesses team fit, how you work and what you would own.", "topics": ["Role scope and expectations", "Working style", "Examples of ownership"],
        "skills": ["Collaboration", "Ownership"], "prep": ["Prepare questions about the team, priorities and success measures", "Have examples that show impact in similar work"]},
    "behavioural_interview": {"purpose": "Explore how you have behaved in real situations, against the company's values or competencies.", "topics": ["Teamwork", "Conflict and feedback", "Handling pressure", "Learning from mistakes"],
        "skills": ["Communication", "Self-awareness"], "prep": ["Prepare 4–5 real stories using the STAR structure (Situation, Task, Action, Result)", "Review the company's published values and map stories to them"]},
    "presentation": {"purpose": "Present work or a solution and handle questions, showing communication and depth.", "topics": ["Structuring a presentation", "Handling questions"],
        "skills": ["Presenting", "Clarity"], "prep": ["Rehearse to the time limit", "Anticipate challenging questions on your choices"]},
    "final_interview": {"purpose": "A final decision-stage conversation or panel, often with senior staff.", "topics": ["Overall fit", "Motivation", "Remaining concerns from earlier rounds"],
        "skills": ["Consistency", "Motivation"], "prep": ["Revisit feedback and topics from earlier rounds", "Prepare questions for senior stakeholders"]},
    "offer": {"purpose": "Offer, references and any pre-employment checks.", "topics": ["Compensation and terms", "References and checks"],
        "skills": ["Negotiation"], "prep": ["Know your priorities before the offer call", "Line up referees in advance"]},
}

TECH_QUESTIONS: Dict[str, List[str]] = {
    "python": ["Explain the difference between a list and a tuple, and when you'd use each.", "How do generators work and when would you use one?"],
    "sql": ["Write a query to find the second-highest value in a column.", "Explain INNER vs LEFT JOIN with an example."],
    "javascript": ["Explain closures and a practical use of one.", "How does the event loop work?"],
    "typescript": ["What problems do generics solve? Give an example."],
    "react": ["When does a component re-render and how can you avoid unnecessary renders?", "Explain useEffect dependencies."],
    "java": ["Explain how garbage collection works at a high level.", "What's the difference between an interface and an abstract class?"],
    "aws": ["How would you design a highly available web application on AWS?", "When would you choose SQS over SNS?"],
    "docker": ["What's the difference between an image and a container?", "How do you keep Docker images small?"],
    "kubernetes": ["Explain pods, deployments and services.", "How would you debug a pod stuck in CrashLoopBackOff?"],
    "terraform": ["How do you manage Terraform state safely in a team?"],
    "git": ["Explain rebase vs merge and when you'd use each."],
    "system design": ["Design a URL shortener. What are the main components and trade-offs?", "How would you scale a read-heavy service?"],
    "linux": ["How do you investigate a process using too much CPU?"],
    "ci/cd": ["Describe a CI/CD pipeline you would set up for a new service."],
    "machine learning": ["How do you detect and handle overfitting?"],
}
BEHAVIOURAL = ["Tell me about a time you disagreed with a teammate. How did you resolve it?", "Describe a project you're proud of and your specific contribution.",
               "Tell me about a mistake you made and what you changed afterwards.", "Why do you want to work at this company and in this role?"]


# ----------------------------------------------------------- compatibility
def _years_experience(profile: Dict[str, Any]) -> Optional[float]:
    total, found = 0.0, False
    this_year = date.today().year
    for e in profile.get("experience") or []:
        if not isinstance(e, dict):
            continue
        yrs = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", str(e.get("dates") or ""))]
        if not yrs:
            continue
        end = this_year if re.search(r"present|current|now", str(e.get("dates")), re.I) else (yrs[1] if len(yrs) > 1 else yrs[0])
        total += max(0, end - yrs[0])
        found = True
    return total if found else None


def _entry_texts(entries: Any) -> List[Dict[str, str]]:
    out = []
    for e in entries or []:
        if isinstance(e, dict):
            out.append({"label": str(e.get("title") or e.get("name") or e.get("company") or "Entry"),
                        "text": " ".join(str(v) if not isinstance(v, list) else " ".join(map(str, v)) for v in e.values()).lower()})
        elif isinstance(e, str):
            out.append({"label": e[:60], "text": e.lower()})
    return out


def compatibility(profile: Optional[Dict[str, Any]], role: Dict[str, Any], match: Dict[str, Any], stage_keys: List[str]) -> Dict[str, Any]:
    if not profile:
        return {"available": False, "message": "Upload your résumé to compare your profile with this role."}
    skills = {str(s).lower(): str(s) for s in profile.get("skills") or []}
    exp, proj = _entry_texts(profile.get("experience")), _entry_texts(profile.get("projects"))
    rows, existing, missing, revise = [], [], [], []
    for sk in role["required_skills"]:
        k = sk.lower()
        in_exp = [e["label"] for e in exp if k in e["text"]]
        in_proj = [p["label"] for p in proj if k in p["text"]]
        if k in skills and (in_exp or in_proj):
            status, ev = "strong_match", f"Listed in your skills and evidenced in: {', '.join((in_exp + in_proj)[:3])}"
        elif k in skills:
            status, ev = "match", "Listed in your skills; no project or role in your profile demonstrates it yet"
        elif in_exp or in_proj:
            status, ev = "match", f"Mentioned in: {', '.join((in_exp + in_proj)[:3])} (not in your skills list)"
        else:
            status, ev = "missing_evidence", "Not found in your profile"
        rows.append({"requirement": sk, "kind": "skill", "status": status, "evidence": ev})
        (existing if status != "missing_evidence" else missing).append(sk)
        revise += [{"entry": n, "for_skill": sk} for n in (in_exp + in_proj)[:2]]
    full = " ".join(e["text"] for e in exp + proj) + " " + " ".join(skills)
    for t in role["topics_mentioned"]:
        has = t in full
        rows.append({"requirement": t.title(), "kind": "topic", "status": "match" if has else "needs_preparation",
                     "evidence": "Appears in your profile" if has else "The posting mentions this; your profile shows no evidence, so prepare it"})
        if not has:
            missing.append(t.title())
    cand_years = _years_experience(profile)
    for req in role["experience_requirements"]:
        n = int(re.match(r"\d+", req).group(0))
        if cand_years is None:
            rows.append({"requirement": req, "kind": "experience", "status": "unknown", "evidence": "Your profile has no dated experience to compare"})
        else:
            ok = cand_years >= n
            rows.append({"requirement": req, "kind": "experience", "status": "match" if ok else "needs_preparation",
                         "evidence": f"Your profile shows about {cand_years:.0f} year(s) of dated experience"})
    if role["education_requirements"]:
        edu = " ".join(_e["text"] for _e in _entry_texts(profile.get("education")))
        has_degree = bool(_DEGREE.search(edu))
        rows.append({"requirement": role["education_requirements"][0], "kind": "qualification",
                     "status": "match" if has_degree else "missing_evidence",
                     "evidence": "Education in your profile" if has_degree else "No matching education found in your profile"})
    if any(k in stage_keys for k in ("behavioural_interview", "hiring_manager", "recruiter_screen", "final_interview")) or role["soft_skills_mentioned"]:
        rows.append({"requirement": "Communication and examples", "kind": "behavioural", "status": "needs_preparation",
                     "evidence": "Prepare real examples; this can't be evidenced from a profile"})
    return {"available": True, "rows": rows, "existing_skills": existing, "missing_skills": missing, "revise_entries": revise[:6],
            "match_score": match.get("job_match_score"), "experience_years_estimated": cand_years}


def preparation_plan(role: Dict[str, Any], comp: Dict[str, Any], stages: List[Dict[str, Any]]) -> Dict[str, Any]:
    skills = role["required_skills"]
    questions = []
    for s in skills:
        for q in TECH_QUESTIONS.get(s.lower(), [])[:2]:
            questions.append({"question": q, "skill": s, "type": "technical"})
    for t in role["topics_mentioned"]:
        for q in TECH_QUESTIONS.get(t, [])[:1]:
            questions.append({"question": q, "skill": t, "type": "technical"})
    for d in role.get("domains") or []:
        questions += [{"question": q, "skill": d, "type": "role-specific"} for q in DOMAIN_QUESTIONS.get(d, [])[:3]]
    questions += [{"question": q, "skill": "behavioural", "type": "behavioural"} for q in BEHAVIOURAL]
    study = (comp.get("missing_skills") if comp.get("available") else role["required_skills"][:8]) or []
    return {
        "topics_to_study": study[:10],
        "projects_to_revise": comp.get("revise_entries", []) if comp.get("available") else [],
        "stage_preparation": [{"stage": s["stage"], "stage_key": s["stage_key"], "status": s["status"], **{k: STAGE_GUIDE[s["stage_key"]][k] for k in ("purpose", "topics", "skills", "prep")}}
                              for s in stages if s["stage_key"] in STAGE_GUIDE],
        "practice_questions": questions[:16],
        "practice_questions_note": "Practice questions are AI/curated examples for revision. They are NOT questions this company is known to ask.",
        "resources": [{"title": "STAR method for behavioural answers", "url": "https://www.themuse.com/advice/star-interview-method"},
                      {"title": "LeetCode – coding practice", "url": "https://leetcode.com/problemset/"},
                      {"title": "System Design Primer", "url": "https://github.com/donnemartin/system-design-primer"}],
        "resources_note": "General study resources, not company-specific material.",
    }
