import json
import sys
sys.path.insert(0, ".")
from backend.database import JobDatabase
from backend.recommendation_service import RecommendationService

db = JobDatabase()
stored_jobs = db.get_jobs(limit=3000)
rec_svc = RecommendationService()

# Test with Marcus Vance (DevOps)
marcus_resume = {
    "candidate_name": "Marcus Vance",
    "skills": ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "Ansible", "CI/CD", "Prometheus", "Grafana", "Python", "Go", "Bash"],
    "target_roles": ["DevOps Engineer", "Site Reliability Engineer", "Infrastructure Engineer"],
    "seniority_level": "Senior",
    "total_skills": 12,
    "raw_text": "Marcus Vance Senior DevOps AWS Kubernetes Terraform CI/CD Docker"
}

# Test with Dhanush (Full Stack / Software Engineer)
dhanush_resume = {
    "candidate_name": "Dhanush",
    "skills": ['AWS', 'Docker', 'FastAPI', 'GitHub', 'Go', 'JavaScript', 'LangChain', 'NLP', 'NumPy', 'PostgreSQL', 'PyTorch', 'Python', 'React', 'SQL'],
    "target_roles": ["Software Engineer", "Full Stack Engineer"],
    "seniority_level": "Senior",
    "total_skills": 14,
    "raw_text": "Dhanush Senior Full Stack Software Engineer Python React FastAPI AWS Docker"
}

recs_m = rec_svc.recommend_jobs(marcus_resume, stored_jobs, min_score=85)
recs_d = rec_svc.recommend_jobs(dhanush_resume, stored_jobs, min_score=85)

print(f"Marcus Vance (>=85%): {len(recs_m)} jobs")
for r in recs_m[:5]:
    print(f"  {r['match_score']}% | {r['title']} @ {r['company']} (Matched: {r['matched_skills']})")

print(f"Dhanush (>=85%): {len(recs_d)} jobs")
for r in recs_d[:5]:
    print(f"  {r['match_score']}% | {r['title']} @ {r['company']} (Matched: {r['matched_skills']})")
