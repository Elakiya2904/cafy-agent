"""End-to-end smoke test for a running Cafy Agent backend (e.g. the Docker stack).

    .venv\\Scripts\\python.exe docker\\smoke_test.py                       # http://127.0.0.1:8000
    .venv\\Scripts\\python.exe docker\\smoke_test.py --base https://api.example.com

Checks: health + database, auth (config, rejected login, guest session, protected route), resume upload,
parsing and job matching, stored original file, job listing, Nango status. It signs in as a temporary
guest, so no real account is created; the uploaded test resume belongs to that throw-away guest account.
"""
from __future__ import annotations

import argparse
import io
import sys

import requests
from docx import Document

RESUME_LINES = [
    "Jordan Example",
    "jordan.example@example.com | +44 7700 900123 | London, UK",
    "Professional Summary",
    "Data engineer building Python and SQL data pipelines on AWS with Docker, Airflow and PostgreSQL.",
    "Experience",
    "Data Engineer, Example Analytics Ltd, Jan 2022 - Present",
    "- Built Python ETL pipelines loading data into PostgreSQL and Snowflake.",
    "- Deployed Docker services on AWS ECS with CI/CD in GitHub Actions.",
    "Education",
    "BSc Computer Science, University of Example, 2018 - 2021",
    "Skills",
    "Python, SQL, AWS, Docker, Airflow, PostgreSQL, FastAPI, Git",
]


def sample_docx() -> bytes:
    doc = Document()
    for line in RESUME_LINES:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    base = parser.parse_args().base.rstrip("/")
    s = requests.Session()
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")

    r = s.get(f"{base}/api/health", timeout=30)
    body = r.json() if r.ok else {}
    check("health + database", r.status_code == 200 and body.get("status") == "online",
          f"HTTP {r.status_code}, stats={ {k: v for k, v in body.items() if k not in ('status', 'app')} }")

    r = s.get(f"{base}/api/auth/config", timeout=15)
    check("auth config", r.status_code == 200, f"{r.json() if r.ok else r.status_code}")
    guest_allowed = r.ok and r.json().get("guest_mode")

    r = s.post(f"{base}/api/auth/login", json={"email": "nobody@example.invalid", "password": "wrong-password-123"},
               headers={"X-Cafy-Client": "web"}, timeout=15)
    check("login rejects bad credentials", r.status_code in (400, 401), f"HTTP {r.status_code}")

    r = s.get(f"{base}/api/resume/current", timeout=15)
    check("protected route needs auth", r.status_code == 401, f"HTTP {r.status_code}")

    if not guest_allowed:
        check("guest session", False, "guest mode is off on this server; enable ENABLE_GUEST_MODE to run the rest")
        return 1
    r = s.post(f"{base}/api/auth/guest", timeout=15)
    token = r.json().get("access_token") if r.ok else None
    check("guest session issued", bool(token), f"HTTP {r.status_code}")
    if not token:
        return 1
    auth = {"Authorization": f"Bearer {token}"}

    r = s.post(
        f"{base}/api/resume/upload",
        files={"file": ("smoke-test-resume.docx", sample_docx(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=auth, timeout=180,
    )
    up = r.json() if r.ok else {}
    resume = up.get("resume") or up.get("parsed") or {}
    skills = resume.get("skills") or []
    matched = up.get("matched_jobs") or []
    check("resume upload + parsing", r.status_code == 200 and len(skills) >= 3,
          f"HTTP {r.status_code}, {len(skills)} skills: {', '.join(map(str, skills[:6]))}")
    scored = [j for j in matched if isinstance(j.get("match_score"), (int, float))]
    check("job matching", len(scored) > 0,
          f"{len(matched)} jobs ranked; top: "
          + (f"{scored[0].get('title')} @ {scored[0].get('company')} ({scored[0].get('match_score')}%)" if scored else "none"))

    r = s.get(f"{base}/api/resume/current", headers=auth, timeout=60)
    check("resume persisted for this user", r.ok and bool((r.json() or {}).get("resume")), f"HTTP {r.status_code}")

    r = s.get(f"{base}/api/resume/uploaded", headers=auth, timeout=15)
    stored = (r.json() or {}).get("uploaded") if r.ok else None
    check("original file stored in PostgreSQL", bool(stored) and stored.get("filename") == "smoke-test-resume.docx",
          f"HTTP {r.status_code}")

    r = s.get(f"{base}/api/jobs", params={"limit": 5}, headers=auth, timeout=60)
    jobs = r.json() if r.ok else None
    jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    check("job listing", r.ok and isinstance(jobs, list) and len(jobs) > 0, f"HTTP {r.status_code}, {len(jobs or [])} jobs")

    r = s.get(f"{base}/api/integrations/nango/status", headers=auth, timeout=30)
    check("Nango integration status", r.status_code == 200, f"{r.json() if r.ok else r.status_code}")

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
