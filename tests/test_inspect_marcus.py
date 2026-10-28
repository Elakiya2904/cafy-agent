import sys
sys.path.insert(0, ".")
from backend.database import JobDatabase
from backend.recommendation_service import RecommendationService

db = JobDatabase()
stored_jobs = db.get_jobs(limit=3000)
rec_svc = RecommendationService()

marcus_resume = {
    "candidate_name": "Marcus Vance",
    "skills": ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "Ansible", "CI/CD", "Prometheus", "Grafana", "Python", "Go", "Bash"],
    "target_roles": ["DevOps Engineer", "Site Reliability Engineer", "Infrastructure Engineer", "Systems Engineer"],
    "seniority_level": "Senior",
    "total_skills": 12,
}

all_recs = rec_svc.recommend_jobs(marcus_resume, stored_jobs, min_score=0)
print("Top 10 scores for Marcus Vance:")
for r in all_recs[:10]:
    print(f"  {r['match_score']}% | {r['title']} @ {r['company']} (Matched: {r['matched_skills']})")
