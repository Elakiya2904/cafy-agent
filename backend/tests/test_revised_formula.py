import sys
sys.path.insert(0, ".")
from backend.database import JobDatabase

db = JobDatabase()
stored_jobs = db.get_jobs(limit=3000)

from backend.recommendation_service import RecommendationService

rec_svc = RecommendationService()

marcus_resume = {
    "candidate_name": "Marcus Vance",
    "skills": ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "Ansible", "CI/CD", "Prometheus", "Grafana", "Python", "Go", "Bash"],
    "target_roles": ["DevOps", "Site Reliability", "Infrastructure", "Systems", "Platform"],
    "seniority_level": "Senior",
    "total_skills": 12,
}

# Uses the production (honest) scoring formula:
#   100 * (0.6 * skill_score + 0.25 * role_score + 0.15 * semantic) [+3 seniority], clamped 0-100.
high_matches = [
    (r["match_score"], r["title"], r["company"], r.get("platform"), r["matched_skills"])
    for r in rec_svc.recommend_jobs(marcus_resume, stored_jobs, min_score=60)
]

print(f"Total >=60% matches for Marcus Vance: {len(high_matches)}")
for s, t, c, p, m in high_matches[:8]:
    print(f"  {s}% | {t} @ {c} [{p}] (Matched: {m})")
