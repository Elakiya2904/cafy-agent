import json
import sys
import urllib.request
sys.path.insert(0, ".")
from backend.database import JobDatabase
from backend.recommendation_service import RecommendationService

res = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/resume/current").read())
resume = res.get("resume")
print("Resume:", resume["candidate_name"], "Skills:", resume["skills"])

db = JobDatabase()
stored_jobs = db.get_jobs(limit=3000)
rec_svc = RecommendationService()
all_recs = rec_svc.recommend_jobs(resume, stored_jobs, min_score=0)
print("Top 10 match scores for this resume:")
for r in all_recs[:10]:
    print(f"Score: {r['match_score']}% | {r['title']} @ {r['company']} | Matched: {r['matched_skills']}")
