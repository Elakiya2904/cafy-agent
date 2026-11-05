import json
import urllib.request

res = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/resume/current").read())
resume = res.get("resume")
print("Candidate Name:", resume.get("candidate_name"))
print("Target Roles:", resume.get("target_roles"))
print("Seniority:", resume.get("seniority_level"))
print("Total skills:", resume.get("total_skills"))
