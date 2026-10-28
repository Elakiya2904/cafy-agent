import sys
sys.path.insert(0, ".")
from backend.database import JobDatabase

db = JobDatabase()
stored_jobs = db.get_jobs(limit=3000)

def calculate_score(job, resume, tfidf_score=0.15):
    job_skills = job.get("extracted_skills", [])
    resume_skills_set = {s.lower() for s in resume.get("skills", [])}
    target_roles = [r.lower() for r in resume.get("target_roles", [])]
    seniority = (resume.get("seniority_level") or "").lower()

    matched = [s for s in job_skills if s.lower() in resume_skills_set]
    missing = [s for s in job_skills if s.lower() not in resume_skills_set]

    # Skill match score
    if job_skills:
        ratio = len(matched) / len(job_skills)
        count_boost = min(0.25, len(matched) * 0.08)
        skill_score = min(1.0, (ratio * 0.75) + count_boost)
    else:
        desc_lower = (job.get("description") or "").lower()
        matched_in_desc = [s for s in resume.get("skills", []) if s.lower() in desc_lower]
        matched = matched_in_desc[:5]
        skill_score = min(0.90, max(0.40, len(matched_in_desc) * 0.15))

    # Role alignment
    title_lower = (job.get("title") or "").lower()
    role_score = 0.40
    for r in target_roles:
        words = [w for w in r.split() if len(w) > 3]
        if any(w in title_lower for w in words):
            role_score = 0.95
            break

    # Seniority bonus
    seniority_bonus = 0.05
    if "senior" in seniority and "senior" in title_lower:
        seniority_bonus = 0.10
    elif "lead" in seniority and any(w in title_lower for w in ["lead", "principal", "staff"]):
        seniority_bonus = 0.10

    # Semantic component
    semantic = min(1.0, tfidf_score * 3.0)

    # 55% skill + 30% role/seniority + 15% semantic
    raw = (skill_score * 0.55) + (min(1.0, role_score + seniority_bonus) * 0.30) + (semantic * 0.15)
    pct = min(98, max(30, int(round(raw * 100))))
    return pct, matched

marcus_resume = {
    "candidate_name": "Marcus Vance",
    "skills": ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "Ansible", "CI/CD", "Prometheus", "Grafana", "Python", "Go", "Bash"],
    "target_roles": ["DevOps", "Site Reliability", "Infrastructure", "Systems", "Platform"],
    "seniority_level": "Senior",
    "total_skills": 12,
}

high_matches = []
for j in stored_jobs:
    score, matched = calculate_score(j, marcus_resume)
    if score >= 85:
        high_matches.append((score, j['title'], j['company'], j['platform'], matched))

print(f"Total >=85% matches for Marcus Vance: {len(high_matches)}")
for s, t, c, p, m in high_matches[:8]:
    print(f"  {s}% | {t} @ {c} [{p}] (Matched: {m})")
