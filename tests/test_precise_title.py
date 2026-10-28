import sys
sys.path.insert(0, ".")
from backend.database import JobDatabase

db = JobDatabase()
stored_jobs = db.get_jobs(limit=3000)

GENERIC_TITLE_WORDS = {"engineer", "developer", "lead", "senior", "manager", "director", "intern", "specialist", "associate", "consultant"}

def is_meaningful_role_match(target_role: str, job_title: str) -> bool:
    target_lower = target_role.lower().strip()
    title_lower = job_title.lower().strip()
    
    # 1. Exact phrase match
    if target_lower in title_lower:
        return True
        
    # 2. Token overlap: require non-generic words to match
    t_tokens = [w for w in target_lower.split() if w not in GENERIC_TITLE_WORDS and len(w) > 2]
    if t_tokens and all(tok in title_lower for tok in t_tokens):
        return True
        
    return False

print("Testing role matching:")
print("Software Engineer vs CAD Engineer:", is_meaningful_role_match("Software Engineer", "CAD Engineer"))
print("Software Engineer vs Mechanical Engineer:", is_meaningful_role_match("Software Engineer", "Mechanical Engineer"))
print("Software Engineer vs Senior Software Engineer, Backend:", is_meaningful_role_match("Software Engineer", "Senior Software Engineer, Backend"))
print("DevOps Engineer vs Senior Security / DevOps Engineer:", is_meaningful_role_match("DevOps Engineer", "Senior Security / DevOps Engineer"))
print("DevOps Engineer vs Thermal Engineer:", is_meaningful_role_match("DevOps Engineer", "Thermal Engineer"))
