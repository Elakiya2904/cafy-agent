# Cafy Agent – Progress and Next Steps

Written for: the project owner, as a working log of this session and a to-do list.
Last updated: 2026-10-30.

## Done so far

### 1. "Error processing résumé: Load failed" (upload)
- **Cause:** the backend runs on `127.0.0.1:8080`, but the frontend sent API calls to port 8000 whenever the page was not on 8000.
- **Fix:** in all 8 `API_BASE` definitions under `frontend/src/` (`App.jsx`, `JobMatchScore.jsx`, `MyApplications.jsx`, `ApplicationAnalysis.jsx`, `DataExport.jsx`, `ResumeVersionHistory.jsx`, `EmailAgentDashboard.jsx`, `JobIntelligence.jsx`), the cross-port redirect now applies only on dev-server ports (5173, 5174, 3000). Everywhere else the frontend uses same-origin `/api`.
- Frontend rebuilt (`frontend/dist`).

### 2. "Not Found" on Email Agent and Job Intelligence
- **Cause:** the server on port 8080 was a stale process started before those routes existed, and it had no `--reload`. `/api/email-agent/*` and `/api/job-intelligence/*` returned 404.
- **Status: not yet fixed on your machine.** It needs a backend restart (see "Do first").

### 3. Wrong job ages ("205d ago", missing ages)
- **Greenhouse:** the scraper stored `updated_at`, which resets on every edit. It now stores `first_published` (falls back to `updated_at`). File: `backend/scrapers/greenhouse.py`.
- **Lever:** dates are epoch milliseconds the UI could not parse. **Workday:** relative text ("Posted Today", "Posted 30+ Days Ago"). `getPostedDate` and `formatJobAge` in `App.jsx` now handle epoch values, relative text and ISO dates.
- Long ages now read "2mo ago" / "1y ago" instead of "205d ago".
- Greenhouse jobs already in the database keep the old dates until the ATS feed is refreshed.

### 4. Sidebar grouped by pipeline
- Order and section labels now follow `pipeline.md`: Overview (Home), 1 · Discover (Find jobs, Companies, Job alerts), 2 · Apply (My applications, Résumé, Files), 3 · Follow up (Email Agent), Account (Insights, Settings).
- Files: `Sidebar` in `frontend/src/App.jsx`, `.nav-section-label` in `frontend/css/styles.css`.

### 5. Non-engineering résumés (sales, teaching, accounting, finance, hardware, and more)
- **Cause:** the skill and role lists were engineering-only, so a sales résumé produced zero skills and zero roles, and nothing could pass the 4-skill match gate. "Lead Generation" was also read as "Lead" seniority.
- **New `backend/skill_catalog.py`:** 17 domains with skills, roles and job-title phrases — Sales, Customer Success & Support, Teaching & Education, Accounting, Finance, Hardware & Electronics, Mechanical & Manufacturing, Civil & Construction, Healthcare & Nursing, HR & Recruiting, Marketing & Communications, Design & Creative, Operations & Supply Chain, Product & Project Management, Legal & Compliance, Administration, Data & Analytics.
- **`backend/resume_service.py`:**
  - uses the catalog;
  - reads skills listed under "Key Skills" and similar headings, so professions outside the catalog still work;
  - falls back to the résumé's own job titles when no role is recognised;
  - seniority uses whole-word matching.
- **`backend/recommendation_service.py`:**
  - catalog-based role-to-title matching for every field;
  - a job passes with 4 or more shared skills, or a title match plus 3 shared skills;
  - generic skills (Communication, Teamwork, and similar) no longer count toward a match.
- UI placeholders and profile-strength hints no longer assume engineering.
- **Result:** `dhanush_sales.pdf` went from 0 matches to 48 against the stored jobs.

### Tests
- New: `tests/test_multi_domain_resumes.py` (teacher, accountant, hardware engineer, nurse, financial analyst, a profession outside the catalog, the seniority bug). 3 tests pass.
- Still passing: `test_recommendations`, `test_profile_strength`, `test_normalizer`, `test_job_match_analysis`.
- `test_calibration` and `test_revised_formula` print results and ran without errors.
- Run tests as modules from the project root: `.venv/bin/python -m unittest tests.<name>`.

## Do first

1. **Restart the backend** (it is still the stale process, PID 7725). It was not restarted from here.
   ```
   .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload
   ```
   This fixes the Email Agent and Job Intelligence "Not Found" and loads the Greenhouse and matching changes. `--reload` picks up future backend edits.
2. Hard-refresh the browser (Cmd+Shift+R).
3. Click **Refresh ATS Feed** so Greenhouse jobs are re-scraped with correct dates.
4. Re-upload your résumé (the session still holds the old parse).

## Next

### Known problems
- `tests/test_career_chat.py::test_groq_http_error_does_not_return_a_fallback` fails. It checks a mocked Groq error message; career chat code was not changed in this session. Not investigated.
- `tests/test_no_invented_defaults.py` cannot run: `httpx2` is missing from `.venv`. Install it, then run the test.
- Not tested in a browser: the new sidebar, the date formatting, and a real résumé upload after the restart.

### Job supply (biggest limit for non-engineering users)
- The scrapers cover 8 ATS platforms and a fixed company list, mostly tech companies. A teacher or nurse will get few matches however good the matcher is.
- Add employers and boards for other fields (schools and education, hospitals and health systems, finance and accounting firms, hardware and manufacturing companies), or a general job source.

### Matching quality
- Skill matching is keyword-based. Consider synonym matching or embeddings for phrases worded differently in a résumé and a posting.
- The experience filter only reacts to years stated in a listing, so a fresher can still see titles like "Strategic Account Executive". Consider a seniority check against the title.
- Pinpoint jobs (43) have no posted date, so no age is shown.
- Old Ashby postings (65–277 days) may be stale listings. Consider an optional "hide jobs older than N days" filter.
- If a profession matches badly, add its skills and title phrases to `backend/skill_catalog.py`.

### Pipeline work (from `pipeline.md`)
- **P4 → P2/P3:** hiring-process knowledge from Job Intelligence is stored and available through the API, but Application Automation and the Email Agent do not read it yet.
- **Email Agent:** connecting Gmail or Outlook needs `GOOGLE_*` and `MICROSOFT_*` OAuth credentials. Not configured or tested yet.
- **Job Intelligence:** needs network access and likely API keys. Not tested after the restart.
