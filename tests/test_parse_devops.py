import sys
sys.path.insert(0, ".")
from backend.resume_service import ResumeService

svc = ResumeService()
with open("tests/sample_devops_resume.txt", "rb") as f:
    parsed = svc.parse_resume("sample_devops_resume.txt", f.read())

print("Candidate:", parsed["candidate_name"])
print("Target Roles:", parsed["target_roles"])
print("Seniority:", parsed["seniority_level"])
print("Skills (", parsed["total_skills"], "):", parsed["skills"])
